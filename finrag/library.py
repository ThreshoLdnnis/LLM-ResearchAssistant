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


def records(doc=None, kind="financial", database=DB):
    for meta,page,layout in pages(database):
        if doc and meta["id"] != doc:
            continue
        if kind == "financial":
            yield from financial(meta,page,layout)
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

