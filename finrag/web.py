from io import BytesIO
import json
from pathlib import Path
import pymupdf
import requests
from flask import Flask, Response, abort, jsonify, render_template, request, send_file
from .answer import ask
from .library import engine, records
from .search import MODEL, MODES
from .store import connection, documents, ingest

app=Flask(__name__)
app.config["MAX_CONTENT_LENGTH"]=64*1024*1024
app.json.ensure_ascii=False


def view(**state):
    return render_template("index.html", docs=documents(), modes=MODES,
                           dense=(MODEL/"model_quantized.onnx").exists(), **state)


@app.get("/")
def home():
    return view()


@app.post("/upload")
def upload():
    file=request.files.get("file")
    if not file or not file.filename:
        return view(error="请选择 PDF"),400
    try:
        meta={key:request.form.get(key,"").strip() for key in ("company","year","type","published","title")}
        meta["title"]=meta["title"] or Path(file.filename).stem
        doc=ingest(file.read(),meta)
        return view(message=f"已入库 {doc['title']} · {doc['pages']} 页 · 需复核页 {doc['review_pages']}")
    except (ValueError, RuntimeError, pymupdf.FileDataError) as e:
        return view(error=str(e)),400


@app.post("/ask")
def question():
    q=request.form.get("question","").strip()
    doc=request.form.get("doc") or None
    mode=request.form.get("mode","bm25")
    generate=request.form.get("generate")=="on"
    try:
        if not q or len(q)>2000:
            raise ValueError("问题限 1 至 2000 字")
        result=ask(engine(),q,mode,generate,[doc] if doc else None)
        return view(result=result,q=q,selected=doc,selected_mode=mode,generate=generate)
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
    return view(series=panel(doc,set(LABELS.values())),series_doc=doc)


@app.get("/extract/<doc>/<kind>")
def extract(doc,kind):
    if kind not in ("financial","narrative","rows") or doc not in {d["id"] for d in documents()}:
        abort(404)
    return Response(json.dumps(list(records(doc,kind)),ensure_ascii=False,indent=2),
                    mimetype="application/json",headers={"Content-Disposition":f'attachment; filename="{doc}-{kind}.json"'})

