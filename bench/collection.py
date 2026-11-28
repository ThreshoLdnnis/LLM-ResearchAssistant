"""Reproduce the public collection inventory and retrieval/extraction coverage."""
import argparse
from collections import Counter
import csv
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import json
from pathlib import Path

from finrag.library import query_library, records
from finrag.search import Search, chunks
from finrag.store import DB, ROOT, connection, documents, pages
from scripts.import_collection import collection


METRICS = ("营业收入", "归母净利润", "经营现金流净额")
QUARTER_METRICS = {"revenue", "parent_profit", "operating_cash_flow"}
SCALES = {"元": 1, "千元": 1000, "万元": 10000, "百万元": 1000000, "亿元": 100000000}


def matches_reference(calc, ref):
    reference_scale = SCALES[ref["原单位"].removeprefix("人民币")]
    for key, column, year_offset in (("current","本期值",0), ("previous","上年同期比较值",-1)):
        value = calc[key]
        if (value["currency"] != "CNY" or value["scope"] != "集团"
                or int(value["year"]) != int(ref["报告年度"]) + year_offset):
            return False
        if Decimal(str(value["value"])) * SCALES[value["unit"]] != Decimal(ref[column]) * reference_scale:
            return False
    return True


def inspect_reports(database):
    docs = {d["sha256"]: d for d in documents(database)}
    reference_path = ROOT / "results/collection-reference.csv"
    with reference_path.open(encoding="utf-8-sig", newline="") as stream:
        reference = {(r["SHA256"], r["指标"]): r for r in csv.DictReader(stream) if r["文件类型"] == "年报"}
    output = []
    for source in collection():
        digest = source["sha256"]
        doc = docs[digest]
        key = doc["id"]
        with connection(database) as db:
            original = db.execute("SELECT pdf FROM documents WHERE id=?", (key,)).fetchone()[0]
        if sha256(original).hexdigest() != digest:
            raise ValueError(f"Stored PDF differs from the manifest: {key}")
        rows = pages(database, key)
        if [p for _, p, _ in rows] != list(range(1, source["pages"] + 1)):
            raise ValueError(f"Incomplete page sequence: {key}")
        item = dict(company=source["company"], year=source["year"], kind=doc["type"],
                    split=source["split"], title=source["title"], url=source["url"], sha256=digest,
                    pages=source["pages"], text_pages=sum(bool(t.strip()) for _, _, t in rows),
                    review_pages=doc["review_pages"])
        if doc["type"] == "年报":
            item["annual_yoy"] = {}
            for metric in METRICS:
                q = f"{doc['company']}{doc['year']}年合并{metric}同比增长了多少？"
                result = query_library(q, allowed=[key], database=database)
                calc = result["calculation"]
                if "reason" in calc:
                    item["annual_yoy"][metric] = {"status": result["status"], "reason": calc["reason"]}
                else:
                    fields = ("year", "value", "unit", "currency", "scope", "pages")
                    ref = reference[digest, metric]
                    reported = ref["披露同比(%)"]
                    displayed = Decimal(str(calc["change"])).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
                    item["annual_yoy"][metric] = {
                        "status": result["status"], "change_pct": calc["change"],
                        "reference_amounts_match": matches_reference(calc, ref),
                        "reference_yoy_match": displayed == Decimal(reported) if reported else None,
                        **{k: {f: calc[k][f] for f in fields} for k in ("current", "previous")}}
        else:
            if doc["type"] == "季报":
                item["quarter_observations"] = [
                    {k: r.get(k) for k in ("metric","label","scope","period","period_kind","unit","currency",
                                            "value","reported_yoy_pct","page")}
                    for r in records(key, database=database)
                    if r["evidence_type"] == "table" and r["metric"] in QUARTER_METRICS and "月" in r["period"]]
                query = "主要会计数据和财务指标 营业收入 本报告期 年初至报告期末"
            else:
                query = "利润分配 每股 每10股 现金红利 含税 股权登记日 除权除息日"
            hits = Search(chunks(rows)).rank(query, "bm25", k=3)
            item["retrieval"] = {"query": query, "pages": list(dict.fromkeys(h.page for h in hits))}
        output.append(item)
    status = Counter(entry["status"] for d in output for entry in d.get("annual_yoy", {}).values())
    return {"document_count":len(output), "page_count":sum(d["pages"] for d in output),
            "text_pages":sum(d["text_pages"] for d in output), "annual_status":dict(status),
            "documents":output}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DB)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = inspect_reports(args.database)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print({k:v for k,v in report.items() if k != "documents"})
