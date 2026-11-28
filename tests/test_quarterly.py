import unittest

from finrag.extract import financial


META = dict(id="quarter", company="样例", type="季报", title="2024年第三季度报告",
            year=2024, published="2024-10-31")
WRAPPED = ("2024年第三季度报告\n"
           "                 本报告期比上年同          年初至报告期末比上年\n"
           "       本报告期                 年初至报告期末\n"
           "                 期增减                    同期增减\n")


class QuarterlySummaryTests(unittest.TestCase):
    def test_staggered_headers_wrapped_units_and_missing_cells(self):
        layout = (WRAPPED + "营业收入（千元）   15   -4%   80   8%\n"
                  "经营活动产生的现金流量净额（千\n——   ——   0   0%\n元）\n"
                  "本报告期末     上年度末\n营业收入（千元）   2   1%   3   2%")
        rows = financial(META, 8, layout)
        self.assertEqual([(r["period"], r["value"], r["reported_yoy_pct"]) for r in rows], [
            ("2024年7-9月",15,-4), ("2024年1-9月",80,8),
            ("2024年7-9月",None,None), ("2024年1-9月",0,0)])
        self.assertEqual(rows[2]["value_status"], "not_disclosed")
        self.assertEqual(rows[3]["value_status"], "disclosed")
        self.assertTrue(all(r["page"] == 8 and r["unit"] == "千元" for r in rows))
        self.assertIn("——", rows[2]["quote"])
        self.assertIn("年初至报告期末", rows[2]["header"])
        self.assertEqual(financial(META, 8, layout, tables=False), [])

    def test_column_reordering_and_ambiguous_periods(self):
        head = "年初至报告期末  本报告期  本报告期比上年同期增减  年初至报告期末比上年同期增减"
        layout = head + "\n营业收入（元）   80   15   4%   8%"
        rows = financial(META, 1, layout)
        self.assertEqual([(r["value"],r["reported_yoy_pct"]) for r in rows], [(15,4),(80,8)])
        self.assertEqual(financial(META, 1, layout.replace("4%", "4")), [])
        self.assertEqual(financial(META, 1, layout.replace("本报告期比上年同期增减", "同比")), [])
        self.assertEqual(financial(dict(META,year=2023), 1, layout), [])
        self.assertEqual(financial(dict(META,title="报告"), 1, layout), [])
        self.assertEqual(financial(dict(META,type="年报"), 1, layout), [])
