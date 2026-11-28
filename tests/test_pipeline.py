import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import pymupdf
from finrag.answer import ask
from finrag.extract import financial
from finrag.search import Chunk,Search
from finrag.store import documents,ingest,pages
from bench.evaluate import measure

META=dict(id="example",company="样例",title="年度报告",type="年报",year=2024,published="2025-03-25")


class PipelineTests(unittest.TestCase):
    def test_parallel_annual_statement(self):
        layout = ("2024年度合并及公司利润表\n金额单位为人民币千元\n"
                  "项目  附注  2024 年度  2023年度  2024年度  2023年度\n"
                  "公司  公司  合并  合并\n"
                  "一、营业总收入  25  20  99  98\n"
                  "其中：营业收入  十八(3)  23  18  90  82\n"
                  "归属于母公司股东的\n净利润  -  (2)  9  8")
        rows = financial(META, 11, layout)
        self.assertEqual([(r["scope"], r["period"], r["value"]) for r in rows if r["metric"]=="revenue"],
                         [("母公司","2024",23),("母公司","2023",18),("集团","2024",90),("集团","2023",82)])
        profits = [r for r in rows if r["metric"]=="parent_profit"]
        self.assertEqual([r["value"] for r in profits], [-2,9,8])
        self.assertTrue(all(r["currency"]=="CNY" and r["unit"]=="千元" and r["page"]==11 for r in rows))
        self.assertIn("归属于母公司股东的\n净利润", profits[0]["quote"])
        self.assertEqual(financial(META, 11, layout.replace("公司  公司  合并  合并","合并  公司")), [])
        self.assertEqual(financial(META, 11, layout, tables=False), [])

    def test_period_order_and_changes(self):
        layout="本集团主要会计数据\n（人民币百万元）  2024年  2023年  增减(%)  2022年\n净利润  104  100  4  (20)"
        rows=financial(META,1,layout)
        self.assertEqual([(r["period"],r["value"],r["scope"]) for r in rows],
                         [("2024",104,"集团"),("2023",100,"集团"),("2022",-20,"集团")])

    def test_quarterly_period_not_full_year(self):
        layout="合并现金流量表\n人民币百万元\n项目  2024 年1-9 月  2023 年1-9 月\n经营活动产生的现金流量净额  18  8"
        r=financial(dict(META,type="季报"),23,layout)
        self.assertEqual([(a["period"],a["value"]) for a in r],[("2024年1-9月",18),("2023年1-9月",8)])
        ambiguous=layout.replace("2024 年1-9 月  2023 年1-9 月","2024年  2024年")
        self.assertEqual(financial(META,1,ambiguous),[])

    def test_db_atomic_reimport(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/"sample.sqlite"
            with pymupdf.open() as pdf:
                pdf.new_page().insert_text((30,50),"Revenue reached one hundred.")
                data=pdf.tobytes()
            ingest(data,META,db)
            ingest(data,META,db)
            with self.assertRaises(ValueError):
                ingest(data,dict(META,sha256="bad"),db)
            self.assertEqual(len(documents(db)),1)
            self.assertEqual(pages(db)[0][1],1)

    def test_empty_scanned_pdf(self):
        with pymupdf.open() as pdf:
            pdf.new_page()
            with self.assertRaisesRegex(ValueError,"OCR"):
                ingest(pdf.tobytes(),META)

    def test_multi_evidence_and_filter(self):
        a=Chunk("annual",1,1,"年报","营业收入")
        b=Chunk("q3",1,1,"三季报","营业收入")
        self.assertEqual(measure([a,a],[["annual:1"],["q3:1"]]),(.5,1,False))
        self.assertEqual(Search([a,b]).rank("营业收入",allowed={"q3"}),[b])

    @patch("finrag.answer.requests.post")
    def test_citations_and_usage(self,post):
        import os
        result=Mock()
        result.json.return_value={"choices":[{"message":{"content":
            '{"claims":[{"answer":"25户","evidence":1},{"answer":"错误","evidence":7}]}'}}],
            "usage":{"prompt_tokens":100,"completion_tokens":10}}
        post.return_value=result
        h=Chunk("doc",8,1,"年报","优先股股东25户。")
        with patch.dict(os.environ,{"FINRAG_INPUT_USD_PER_M":"2","FINRAG_OUTPUT_USD_PER_M":"4"}):
            record=ask(Search([h]),"优先股股东",generate=True)
        self.assertEqual(record["claims"][0]["quote"],h.text)
        self.assertEqual(record["rejected_claims"],1)
        self.assertAlmostEqual(record["api_cost_usd"],0.00024)


if __name__=="__main__":
    unittest.main()

