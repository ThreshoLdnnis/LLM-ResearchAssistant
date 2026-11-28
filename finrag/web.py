from io import BytesIO
import json
import pymupdf
import requests
from flask import Flask, Response, abort, jsonify, redirect, render_template, request, send_file, url_for
from .library import query_library, records
from .notebook import list_runs, load_run, save_run
from .search import MODEL, MODES
from .store import connection, documents, ingest

app=Flask(__name__)
app.config["PLATFORM_NAME"] = "杀猪台"
app.config["MAX_CONTENT_LENGTH"]=64*1024*1024
app.json.ensure_ascii=False


MODE_LABELS = {"bm25":"关键词检索", "vector":"语义检索", "hybrid":"混合检索", "rerank":"混合检索与重排"}
STATUS_LABELS = {"calculated":"年度同比", "evidence":"原文证据", "answered":"模型草稿",
                 "insufficient":"证据不足", "invalid_model_output":"模型输出格式异常"}
app.jinja_env.globals.update(mode_labels=MODE_LABELS, status_labels=STATUS_LABELS)


def view(screen="ask", **state):
    docs = sorted(documents(), key=lambda d: (d.get("published") or "", d["title"]), reverse=True)
    samples = {}
    for d in docs:
        if d.get("company") and d.get("year"):
            samples.setdefault(d.get("type"), d)
    return render_template("index.html", docs=docs, modes=MODES, screen=screen, samples=samples,
                           companies=len({d["company"] for d in docs if d.get("company")}),
                           dense=(MODEL/"model_quantized.onnx").exists(), **state)


@app.get("/")
def home():
    return view()


@app.get("/library")
def library_view():
    return view("library")


@app.get("/import")
def import_view():
    return view("import")


@app.get("/history")
def history():
    return view("history", runs=list_runs())


def find_run(key):
    run = load_run(key)
    if run is None:
        abort(404)
    return run


@app.get("/research/<key>")
def research(key):
    run = find_run(key)
    return view("result", run=run, result=run["result"])


@app.get("/research/<key>/export")
def export_research(key):
    run = find_run(key)
    note = render_template("research.txt", run=run, r=run["result"])
    return Response(note, mimetype="text/plain",
                    headers={"Content-Disposition": f'attachment; filename="research-{key}.txt"'})


@app.post("/upload")
def upload():
    files = [f for f in request.files.getlist("file") if f.filename]
    manual = {k:request.form[k].strip() for k in ("company","year","type","published","title")
              if request.form.get(k,"").strip()}
    messages, errors = [], []
    if not files:
        errors.append("请选择 PDF 文件")
    elif len(files) > 1 and manual:
        errors.append("手工补充信息仅适用于单份文档")
    else:
        for file in files:
            try:
                doc = ingest(file.read(), manual, filename=file.filename)
                messages.append(f"已入库 · {doc['title']} · {doc['pages']} 页")
            except (ValueError, RuntimeError, pymupdf.FileDataError) as exc:
                errors.append(f"{file.filename} · {exc}")
    status = 400 if errors and not messages else 200
    if request.accept_mimetypes.best == "application/json":
        return jsonify(messages=messages, errors=errors), status
    return view("import", message="；".join(messages + errors)), status


@app.post("/ask")
def question():
    q=request.form.get("question","").strip()
    doc=request.form.get("doc") or None
    mode=request.form.get("mode","bm25")
    generate=request.form.get("generate")=="on"
    try:
        if not q or len(q)>2000:
            raise ValueError("问题限 1 至 2000 字")
        result=query_library(q,mode,generate,[doc] if doc else None)
        run = save_run(q, result, doc, mode, generate, documents())
        return redirect(url_for("research", key=run["id"]), code=303)
    except (ValueError,requests.RequestException) as e:
        return view(error=str(e),q=q,selected=doc,selected_mode=mode,generate=generate),400


@app.get("/pdf/<doc>")
def pdf(doc):
    with connection() as db:
        row=db.execute("SELECT pdf FROM documents WHERE id=?",(doc,)).fetchone()
    if row is None:
        abort(404)
    return send_file(BytesIO(row[0]),mimetype="application/pdf",download_name=doc+".pdf")


@app.get("/series/<doc>")
def annual_series(doc):
    from .extract import LABELS
    from .series import panel
    report = next((d for d in documents() if d["id"] == doc), None)
    if report is None:
        abort(404)
    if report["type"] == "季报":
        rows = [r for r in records(doc) if r["evidence_type"] == "table"
                and r["period"] and "月" in r["period"]]
        return view("metrics", report=report, quarter_report=report, quarter_rows=rows, selected=doc)
    return view("metrics", report=report, series=panel(doc,set(LABELS.values())),series_doc=doc)


@app.get("/extract/<doc>/<kind>")
def extract(doc,kind):
    if kind not in ("financial","narrative","rows") or doc not in {d["id"] for d in documents()}:
        abort(404)
    return Response(json.dumps(list(records(doc,kind)),ensure_ascii=False,indent=2),
                    mimetype="application/json",headers={"Content-Disposition":f'attachment; filename="{doc}-{kind}.json"'})

