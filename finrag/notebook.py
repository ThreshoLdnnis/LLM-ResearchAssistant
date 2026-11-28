"""Local snapshots of the evidence and settings actually used by a research query."""
from datetime import datetime
import json
from uuid import uuid4

from .store import DB, connection


def save_run(question, result, selected, mode, generate, docs, database=DB):
    source_ids = {r["doc"] for r in result["hits"] + result["claims"]}
    calc = result.get("calculation") or {}
    if calc.get("doc"):
        source_ids.add(calc["doc"])
    if selected:
        source_ids.add(selected)
    source_fields = ("id", "company", "title", "year", "type", "published", "sha256", "url")
    sources = {d["id"]: {k: d.get(k) for k in source_fields} for d in docs if d["id"] in source_ids}
    run = dict(id=uuid4().hex, created=datetime.now().astimezone().isoformat(timespec="seconds"),
               question=question, result=result, selected=selected, mode=mode, generate=generate,
               library_count=len(docs), sources=sources)
    with connection(database) as db:
        db.execute("INSERT INTO research_runs VALUES (?,?,?,?)",
                   (run["id"], run["created"], question, json.dumps(run, ensure_ascii=False)))
    return run


def list_runs(database=DB):
    with connection(database) as db:
        return [dict(row) for row in db.execute(
            "SELECT id,created,question FROM research_runs ORDER BY created DESC,rowid DESC")]


def load_run(key, database=DB):
    with connection(database) as db:
        row = db.execute("SELECT snapshot FROM research_runs WHERE id=?", (key,)).fetchone()
    return json.loads(row[0]) if row else None
