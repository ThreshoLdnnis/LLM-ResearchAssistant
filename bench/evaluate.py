"""Paired retrieval and layout ablations on one frozen corpus; no API usage."""
import argparse
import json
import platform
from importlib.metadata import version
from statistics import mean, median
from time import perf_counter
import numpy as np
from finrag.extract import financial
from finrag.search import Search, chunks, MODES, REV, encoder
from finrag.store import ROOT
from .corpus import frozen_pages


def measure(hits, groups):
    labels = [f"{h.doc}:{h.page}" for h in hits]
    found = sum(any(p in labels for p in group) for group in groups)
    rr = next((1/rank for rank,p in enumerate(labels,1) if any(p in g for g in groups)),0)
    return found/len(groups),rr,found==len(groups)


def run(folder):
    folder.mkdir(exist_ok=True,parents=True)
    qs = json.loads((ROOT/"bench/questions.json").read_text(encoding="utf8"))
    rows = frozen_pages()
    details, summary = [], []
    for strategy,tables in [("structure",True),("fixed",True),("semantic",True),("structure",False)]:
        engine = Search(chunks(rows,strategy,tables))
        engine.prepare_dense()
        # Query embedding time is included in each dense query. Exclude initialization/indexing.
        for mode in MODES:
            sample = []
            for q in qs:
                encoder().query.cache_clear()
                t = perf_counter()
                hits = engine.rank(q["question"],mode,5)
                latency = (perf_counter()-t)*1000
                recall,rr,complete = measure(hits,q["evidence"])
                sample.append(dict(id=q["id"],chunks=[c.key for c in hits],recall=recall,rr=rr,
                                   complete=complete,ms=round(latency,3)))
            tag = dict(strategy=strategy,tables=tables,mode=mode)
            details.extend({**tag,**row} for row in sample)
            ms=[row["ms"] for row in sample]
            summary.append(dict(**tag, chunks=len(engine.items), recall5=mean(x["recall"] for x in sample),
                                mrr5=mean(x["rr"] for x in sample),complete5=mean(x["complete"] for x in sample),
                                p50_ms=median(ms),p95_ms=float(np.percentile(ms,95))))
    gold = json.loads((ROOT/"bench/extraction.json").read_text(encoding="utf8"))
    meta,pg,layout=next(r for r in rows if r[0]["id"]==gold["doc"] and r[1]==gold["page"])
    target={(gold["scope"],m,y,u,v) for m,u,*vs in gold["observations"] for y,v in zip(gold["periods"],vs)}
    extraction=[]
    for tables in (False,True):
        preds={(r["scope"],r["metric"],r["period"],r["unit"],r["value"]) for r in financial(meta,pg,layout,tables)}
        tp=len(preds & target)
        extraction.append(dict(tables=tables,tp=tp,fp=len(preds-target),fn=len(target-preds),
                               precision=tp/len(preds) if preds else None, recall=tp/len(target),
                               f1=2*tp/(len(preds)+len(target))))
    record=dict(questions=len(qs),pages=len(rows),documents=4,encoder_revision=REV,
                python=platform.python_version(),packages={p:version(p) for p in
                ("PyMuPDF","numpy","onnxruntime","tokenizers")},retrieval=summary,extraction=extraction)
    for file,data in [("metrics",record),("retrieval-traces",details)]:
        (folder/(file+".json")).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf8")


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=type(ROOT),default=ROOT/"results")
    run(p.parse_args().output)

