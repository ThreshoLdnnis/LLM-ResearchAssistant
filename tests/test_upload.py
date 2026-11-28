from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pymupdf

from finrag import web
from finrag.metadata import infer_metadata
from finrag.store import documents, ingest


class UploadTest(unittest.TestCase):
    def test_batch_with_unknown_metadata_duplicate_and_bad_pdf(self):
        with TemporaryDirectory() as temp, pymupdf.open() as source:
            database = Path(temp) / "library.sqlite"
            source.new_page().insert_text((40, 50), "Research text")
            pdf = source.tobytes()

            def upload(data, meta, *, filename):
                return ingest(data, meta, database, filename=filename)

            with patch.object(web, "ingest", upload):
                client = web.app.test_client()
                response = client.post("/upload", headers={"Accept": "application/json"},
                                       data={"file": [(BytesIO(pdf), "sample.pdf"),
                                                      (BytesIO(b"invalid"), "bad.pdf")]})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.json["messages"]), 1)
                self.assertEqual(len(response.json["errors"]), 1)
                saved, = documents(database)
                self.assertEqual(saved["title"], "sample")
                for key in ("company", "year", "published", "type"):
                    self.assertIsNone(saved[key])
                response = client.post("/upload", headers={"Accept": "application/json"},
                                       data={"file": (BytesIO(pdf), "renamed.pdf")})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(documents(database), [saved])

    def test_reporting_period_and_explicit_publication_date(self):
        cover = "示例股份有限公司\n2024 年度报告\n2025 年 3 月"
        meta = infer_metadata("report.pdf", cover)
        self.assertEqual((meta["company"], meta["year"], meta["type"]),
                         ("示例股份有限公司", 2024, "年报"))
        self.assertIsNone(meta["published"])
        dated = infer_metadata("report.pdf", cover + "\n披露日期：2025 年 3 月 29 日")
        self.assertEqual(dated["published"], "2025-03-29")
