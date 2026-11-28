import unittest
from unittest.mock import patch
from finrag.series import annual_yoy


class AnnualYoyTests(unittest.TestCase):
    @patch("finrag.series.panel")
    def test_scope_period_and_fallback(self, panel):
        doc = dict(id="sample", company="样例", type="年报", year=2024, title="年度报告")
        base = dict(scope="集团", unit="千元", currency="CNY")
        panel.return_value = [
            dict(base, year="2024", value=110, change=10, pages=[9]),
            dict(base, year="2023", value=100, change=None, pages=[9]),
            dict(base, scope="母公司", year="2024", value=90, change=-10, pages=[9]),
            dict(base, scope="母公司", year="2023", value=100, change=None, pages=[9]),
        ]
        def query(text):
            return annual_yoy(text, [doc], ["sample"], None)
        self.assertEqual(query("样例 2024 年合并营业收入同比增长了多少？")["change"], 10)
        summary = dict(doc, id="summary", type="年报摘要")
        text = "样例2024年合并营业收入同比增长多少？"
        self.assertEqual(annual_yoy(text,[summary,doc],None,None)["doc"], "sample")
        self.assertEqual(annual_yoy(text,[summary,doc],["summary"],None)["doc"], "summary")
        self.assertEqual(query("2024年母公司营业收入同比增长多少？")["change"], -10)
        self.assertIn("reason", query("其他公司2024年合并营业收入同比增速是多少？"))
        self.assertIsNone(query("样例2024年合并营业收入同比增长的原因是什么？"))
        panel.return_value[0]["currency"] = "USD"
        self.assertIn("reason", query("2024年合并营业收入同比增长多少"))
