"""Annual panel assembled only from attributed and aligned table observations."""
from collections import defaultdict
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

