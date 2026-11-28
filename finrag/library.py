from functools import lru_cache
from .extract import financial, narratives, fields
from .search import Search, chunks
from .store import documents, pages, DB


@lru_cache(maxsize=2)
def _engine(database, signature, strategy):
    return Search(chunks(pages(database),strategy))


def engine(database=DB, strategy="structure"):
    # Metadata edits, including titles, change the signature used by lexical and vector search.
    state = tuple((d["id"],d["sha256"],d["title"]) for d in documents(database))
    return _engine(database,state,strategy)


def query_library(question, mode="bm25", generate=False, allowed=None, k=5, strategy="structure", database=DB):
    from time import perf_counter
    from .answer import ask
    from .series import annual_yoy
    started = perf_counter()
    if "同比" in question:
        calculation = annual_yoy(question, documents(database), allowed, database)
        if calculation is not None:
            return dict(status="insufficient" if "reason" in calculation else "calculated",
                        calculation=calculation, claims=[], hits=[], usage=None, api_cost_usd=0,
                        rejected_claims=0, generation="本地计算", latency_ms=round((perf_counter()-started)*1000, 2))
    return ask(engine(database, strategy), question, mode, generate, allowed, k)


def records(doc=None, kind="financial", database=DB):
    statement = {}
    for meta,page,layout in pages(database, doc):
        if kind == "financial":
            yield from financial(meta,page,layout,statement=statement)
        elif kind == "narrative":
            yield from narratives(meta,page,layout)
        elif kind == "rows":
            for line in layout.splitlines():
                cells = fields(line)
                if len(cells)>=2 and any(any(c.isdigit() for c in s) for s in cells):
                    yield dict(doc=meta["id"],page=page,cells=cells,quote=line.strip(),
                               status="版面候选行，需核对表头")
        else:
            raise ValueError("unknown record type")

