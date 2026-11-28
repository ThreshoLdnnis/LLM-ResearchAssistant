"""Import the six-company public collection from a ZIP or the pinned issuer URLs."""
import argparse
from hashlib import file_digest, sha256
import json
from pathlib import Path
from zipfile import ZipFile

import requests

from finrag.store import DB, ROOT, documents, ingest


def collection():
    return json.loads((ROOT / "docs/collection-manifest.json").read_text(encoding="utf8"))["documents"]


def import_collection(archive=None, database=DB):
    expected = {row["sha256"]: row for row in collection()}
    existing = {doc["sha256"]: doc for doc in documents(database)}
    added = 0

    def import_one(digest, pdf):
        nonlocal added
        row = expected[digest]
        if digest not in existing:
            if sha256(pdf).hexdigest() != digest:
                raise ValueError(f"文件哈希不符：{row['title']}")
            existing[digest] = ingest(pdf, {}, database, filename=row["title"] + ".pdf")
            added += 1
        saved = existing[digest]
        if saved["pages"] != row["pages"] or (saved["company"], saved["year"]) != (row["company"], row["year"]):
            raise ValueError(f"入库信息与采集清单不一致：{row['title']}")

    if archive:
        # Use content hashes as identities. ZIP entry names never become filesystem paths.
        with ZipFile(archive) as source:
            members = {}
            for member in source.infolist():
                if not member.is_dir() and member.filename.lower().endswith(".pdf"):
                    with source.open(member) as stream:
                        members[file_digest(stream, "sha256").hexdigest()] = member
            missing = set(expected) - members.keys()
            if missing:
                raise ValueError("压缩包缺少清单版本：" + "、".join(sorted(expected[h]["title"] for h in missing)))
            for digest in expected:
                import_one(digest, None if digest in existing else source.read(members[digest]))
    else:
        with requests.Session() as session:
            for digest, row in expected.items():
                pdf = None
                if digest not in existing:
                    response = session.get(row["url"], timeout=(10, 120))
                    response.raise_for_status()
                    pdf = response.content
                import_one(digest, pdf)
    return {"verified": len(expected), "added": added, "existing": len(expected) - added}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?")
    parser.add_argument("--database", type=Path, default=DB)
    args = parser.parse_args()
    print(json.dumps(import_collection(args.archive, args.database), ensure_ascii=False))
