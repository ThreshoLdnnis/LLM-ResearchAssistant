import json
from finrag.store import MANIFEST,pages


def frozen_pages():
    expected={d["id"]:d["sha256"] for d in json.loads(MANIFEST.read_text(encoding="utf8"))}
    rows=[r for r in pages() if r[0]["id"] in expected]
    actual={m["id"]:m["sha256"] for m,_,_ in rows}
    if actual!=expected or len(rows)!=51:
        raise ValueError("运行 python -m finrag demo 还原来源清单中的四份文档")
    return rows
