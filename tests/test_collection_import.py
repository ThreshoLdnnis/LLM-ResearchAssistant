from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

import pymupdf

from finrag.store import documents
from scripts.import_collection import import_collection


class CollectionImportTests(unittest.TestCase):
    def test_zip_is_complete_before_import_and_duplicate_members_are_reused(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive, db, catalog = root/"bundle.zip", root/"library.sqlite", root/"sources.json"
            with pymupdf.open() as document:
                document.new_page().insert_text((30, 50), "Sample disclosure with a text layer.")
                raw = document.tobytes()
            row = dict(id="example", company="样例", year=2024, title="年度报告", type="年报",
                       published="2025-03-25", pages=1, sha256=sha256(raw).hexdigest())
            catalog.write_text(json.dumps([row]), encoding="utf8")
            with ZipFile(archive, "w") as z:
                z.writestr("one.pdf",raw)
                z.writestr("copies/two.pdf",raw)
                z.writestr("notes.xlsx",b"private")
            with patch("scripts.import_collection.collection", return_value=[row, dict(row,sha256="0"*64)]):
                with self.assertRaisesRegex(ValueError, "缺少"):
                    import_collection(archive, db)
                self.assertEqual(documents(db), [])
            with patch("scripts.import_collection.collection", return_value=[row]), patch("finrag.store.MANIFEST",catalog):
                self.assertEqual(import_collection(archive, db), {"verified":1,"added":1,"existing":0})
                self.assertEqual(import_collection(archive, db), {"verified":1,"added":0,"existing":1})
                self.assertEqual([doc["id"] for doc in documents(db)], ["example"])
