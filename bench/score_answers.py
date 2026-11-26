"""Aggregate reference annotations only for the exact reviewed output."""
import json
from hashlib import sha256
from statistics import median
from finrag.store import ROOT


def summary():
    review=json.loads((ROOT/"bench/review.json").read_text(encoding="utf8"))
    out=[]
    for model,labels in review.items():
        trace=(ROOT/f"results/{model}.json").read_text(encoding="utf8")
        if sha256(trace.encode()).hexdigest()!=labels["sha256"]:
            raise ValueError("输出已变更，请对新的答案重新标注")
        runs=json.loads(trace)
        assert [r["id"] for r in runs]==[x["id"] for x in labels["rows"]]
        votes=labels["rows"]
        total=sum(len(r["claims"]) for r in runs)
        for run,vote in zip(runs,votes):
            assert len(run["claims"])==len(vote["faithful"])==len(vote["citation"])
        out.append(dict(model=model,questions=len(runs),correct=sum(v["correct"] for v in votes),
                    answerable_correct=sum(v["correct"] for v in votes if v["id"]!="a05"),
                    answerable_count=5, claims=total,faithful=sum(sum(v["faithful"]) for v in votes),
                    citation_supported=sum(sum(v["citation"]) for v in votes),
                    correct_abstentions=int(votes[4]["correct"]),unanswerable_count=1,
                    median_ms=median(r["latency_ms"] for r in runs),
                    prompt_tokens=sum(r["usage"]["prompt_tokens"] for r in runs),
                    completion_tokens=sum(r["usage"]["completion_tokens"] for r in runs),
                    api_cost_usd=sum(r["api_cost_usd"] for r in runs)))
    return out


if __name__=="__main__":
    print(json.dumps(summary(),ensure_ascii=False,indent=2))

