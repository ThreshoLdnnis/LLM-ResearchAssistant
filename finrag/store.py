"""Atomic document replacement; all page numbers are one-based PDF positions."""
from contextlib import contextmanager
from datetime import date
from hashlib import sha256
from pathlib import Path
import json
import re
import sqlite3

import pymupdf
import requests

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "data/local"
DB = LOCAL / "library.sqlite"
MANIFEST = ROOT / "data/sources.json"


@contextmanager
def connection(path=DB):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        with db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS documents(
                    id TEXT PRIMARY KEY, meta TEXT NOT NULL, pdf BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS pages(
                    doc TEXT REFERENCES documents(id) ON DELETE CASCADE,
                    page INTEGER, layout TEXT, quality TEXT, PRIMARY KEY(doc,page));
            """)
            yield db
    finally:
        db.close()


def ingest(pdf, meta, database=DB):
    digest = sha256(pdf).hexdigest()
    if "id" not in meta:
        known = json.loads(MANIFEST.read_text(encoding="utf8"))
        meta = next((d for d in known if d["sha256"]==digest),meta)
    key = meta.get("id", digest[:20])
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", key):
        raise ValueError("无效文档 ID")
    if meta.get("sha256", digest) != digest:
        raise ValueError(f"{key} 文件哈希与来源清单不符")
    for field in ("company", "title", "type", "year", "published"):
        if not str(meta.get(field, "")).strip():
            raise ValueError(f"缺少元数据 {field}")
    date.fromisoformat(meta["published"])
    if not 1900 <= int(meta["year"]) <= 2200:
        raise ValueError("年份应为四位数")
    pages = []
    with pymupdf.open(stream=pdf, filetype="pdf") as document:
        if document.needs_pass:
            raise ValueError("PDF 已加密")
        for index, pg in enumerate(document, 1):
            layout = pg.get_text(sort=True).replace("\x00", "").strip()
            quality = "needs_review" if len(layout) < 35 or "�" in layout else "ok"
            pages.append((key, index, layout, quality))
    if not any(p[2] for p in pages):
        raise ValueError("没有可检索文字，请先进行 OCR")
    meta = dict(meta, id=key, sha256=digest, pages=len(pages),
                review_pages=[p[1] for p in pages if p[3] != "ok"])
    with connection(database) as db:
        db.execute("DELETE FROM documents WHERE id=?", (key,))
        db.execute("INSERT INTO documents VALUES(?,?,?)",
                   (key, json.dumps(meta, ensure_ascii=False), pdf))
        db.executemany("INSERT INTO pages VALUES(?,?,?,?)", pages)
    return meta


def download_samples(database=DB):
    for meta in json.loads(MANIFEST.read_text(encoding="utf8")):
        file = ROOT / "data/raw" / (meta["id"] + ".pdf")
        file.parent.mkdir(exist_ok=True, parents=True)
        if file.exists() and sha256(file.read_bytes()).hexdigest() == meta["sha256"]:
            pdf = file.read_bytes()
        else:
            response = requests.get(meta["url"], timeout=(10, 90))
            response.raise_for_status()
            pdf = response.content
        result = ingest(pdf, meta, database)
        file.write_bytes(pdf)
        yield result


def documents(database=DB):
    with connection(database) as db:
        return [json.loads(row[0]) for row in db.execute("SELECT meta FROM documents ORDER BY id")]


def pages(database=DB):
    with connection(database) as db:
        rows = db.execute("""SELECT d.meta,p.page,p.layout FROM pages p JOIN documents d
                             ON p.doc=d.id ORDER BY p.doc,p.page""")
        return [(json.loads(r[0]), r[1], r[2]) for r in rows]

