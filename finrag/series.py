"""Annual panel assembled only from attributed and aligned table observations."""
from collections import defaultdict
import re
from .extract import LABELS
from .library import records


def panel(doc, metrics, database=None):
    if not doc or not metrics or not set(metrics) <= set(LABELS.values()):
        raise ValueError("必须指定一份文档和支持的指标")
    kwargs = {} if database is None else {"database":database}
    observations = defaultdict(list)
    for r in records(doc,**kwargs):
        if r["metric"] in metrics and r["evidence_type"]=="table" and r["scope"] and len(r["period"])==4:
            observations[(r["metric"],r["scope"],r["unit"],r["currency"] or "",r["period"])].append(r)
    rows=[]
    previous={}
    for (metric,scope,unit,currency,year), group in sorted(observations.items()):
        values={r["value"] for r in group}
        value=next(iter(values)) if len(values)==1 else None
        key=(metric,scope,unit,currency)
        prior_year,prior=previous.get(key,("",None))
        change=None
        change_unit=None
        if value is not None and prior is not None and int(year)-1==int(prior_year):
            if unit=="%":
                change=round(value-prior,4)
                change_unit="百分点"
            elif prior>0:
                change=round(100*(value/prior-1),4)
                change_unit="%"
        previous[key]=(year,value)
        rows.append(dict(doc=doc,label=group[0]["label"],metric=metric,scope=scope,unit=unit,
                         currency=currency or None,published=group[0]["published"],
                         year=year,value=value,change=change,change_unit=change_unit,
                         status="ok" if value is not None else "conflict",
                         pages=sorted({r["page"] for r in group})))
    return rows


YOY_METRICS = {
    "营业收入": "revenue", "归母净利润": "parent_profit", "归属于母公司股东的净利润": "parent_profit",
    "经营现金流净额": "operating_cash_flow", "经营活动产生的现金流量净额": "operating_cash_flow",
}
YOY_QUESTION = re.compile(
    r"(?P<company>[^\d，。！？?]{0,60}?)(?P<year>(?:19|20)\d{2})年(?:度)?(?:的)?"
    r"(?P<scope>合并|集团|母公司)(?:口径)?(?:的)?(?P<metric>" + "|".join(YOY_METRICS) + r")"
    r"(?:的)?同比(?:增速|增幅|增长率|变动率|增长)?(?:是|为|了)?(?:多少)?[？?。]?"
)


def annual_yoy(question, documents, allowed, database):
    match = YOY_QUESTION.fullmatch("".join(question.split()))
    if not match:
        return None
    company, year, scope, label = match.group("company", "year", "scope", "metric")
    if not company and not allowed:
        return {"reason": "请在检索范围中选择一份年报，或在年份前写明公司名称。"}
    candidates = [d for d in documents if d["type"] in {"年报", "年报摘要"}
                  and (not company or d["company"] == company)
                  and (d["id"] in allowed if allowed else str(d["year"]) == year)]
    if not allowed and any(d["type"] == "年报" for d in candidates):
        candidates = [d for d in candidates if d["type"] == "年报"]
    if len(candidates) != 1:
        return {"reason": "未能唯一确定出处。请选定一份与公司相符的年报。"}
    doc = candidates[0]
    scope = "母公司" if scope == "母公司" else "集团"
    prior_year = str(int(year) - 1)
    rows = panel(doc["id"], {YOY_METRICS[label]}, database)
    current = [r for r in rows if r["scope"] == scope and r["year"] == year]
    previous = [r for r in rows if r["scope"] == scope and r["year"] == prior_year]
    if len(current) != 1 or len(previous) != 1:
        return {"reason": "系统未能从所选年报中确定两期同口径金额。请核对原表的年份、主体和单位。"}
    now, prior = current[0], previous[0]
    if (not now["currency"] or (now["currency"], now["unit"]) != (prior["currency"], prior["unit"])
            or now["value"] is None or prior["value"] is None or now["change"] is None):
        return {"reason": "两期金额、币种、单位或比较基数未通过校验，无法计算同比。"}
    return dict(company=doc["company"], title=doc["title"], doc=doc["id"], scope=scope,
                label=label, current=now, previous=prior, change=now["change"])

