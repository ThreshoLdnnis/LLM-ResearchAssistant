from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from finrag import notebook, web


class NotebookTests(unittest.TestCase):
    def test_saved_evidence_and_export_use_original_snapshot(self):
        source = dict(id="sample", title="核对样本", company="样例", year=2024, sha256="a"*64)
        hit = dict(doc="sample", title=source["title"], page=8, text="可核对的原文。")
        result = dict(status="evidence", hits=[hit], claims=[], generation="off", latency_ms=1)
        with TemporaryDirectory() as temp:
            db = Path(temp)/"test.sqlite"
            def save(*args):
                return notebook.save_run(*args, database=db)
            with patch.object(web,"documents",return_value=[source]), patch.object(web,"save_run",save), \
                 patch.object(web,"query_library",return_value=result), web.app.test_client() as client:
                response = client.post("/ask", data={"question":"核对样本","doc":"sample","mode":"bm25"})
                self.assertEqual(response.status_code,303)
                path = response.headers["Location"]
                self.assertEqual(len(notebook.list_runs(db)),1)
                source["title"] = "后续修改"
                with patch.object(web,"load_run",side_effect=lambda key:notebook.load_run(key,db)):
                    self.assertIn("命中原文", client.get(path).get_data(as_text=True))
                    export = client.get(path+"/export")
                    self.assertIn("attachment", export.headers["Content-Disposition"])
                    text = export.get_data(as_text=True)
                    for expected in ("可核对的原文。","核对样本","/pdf/sample#page=8","a"*64):
                        self.assertIn(expected,text)
                    self.assertNotIn("后续修改",text)
                    self.assertEqual(client.get("/research/missing").status_code,404)
