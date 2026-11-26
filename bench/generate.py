"""Run actual model inference; retain full claims locally and a compact public trace."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from finrag.answer import ask
from finrag.search import Search, chunks
from finrag.store import ROOT, LOCAL
from .corpus import frozen_pages


def run(output):
    engine = Search(chunks(frozen_pages()))
    engine.prepare_dense()
    questions = json.loads((ROOT/"bench/qa.json").read_text(encoding="utf8"))
    rows, details = [], []
    for q in questions:
        r = ask(engine,q["question"],"hybrid",True,k=4)
        details.append(dict(id=q["id"], **r))
        claims = [{**{k:c[k] for k in ("answer","doc","page","key")},
                   "quote_sha256":sha256(c["quote"].encode()).hexdigest()} for c in r["claims"]]
        rows.append(dict(id=q["id"], **{k:r[k] for k in ("generation","status","latency_ms","usage",
                         "api_cost_usd","rejected_claims")}, claims=claims,
                         retrieved=[h["key"] for h in r["hits"]]))
        print(q["id"],r["status"],r["latency_ms"], flush=True)
    LOCAL.mkdir(parents=True,exist_ok=True)
    (LOCAL/(output.stem+"-details.json")).write_text(json.dumps(details,ensure_ascii=False,indent=2),encoding="utf8")
    output.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf8")


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("output",type=Path)
    run(p.parse_args().output)

