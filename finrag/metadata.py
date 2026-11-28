"""Resolve upload metadata locally, keeping archive dates distinct from disclosure dates."""
from pathlib import Path
import re
from datetime import date


def infer_metadata(filename, cover):
    title = Path(filename.replace("\\", "/")).stem.strip() or "研究文档"
    lines = ["".join(line.split()) for line in cover.splitlines() if line.strip()][:20]
    heading = "\n".join(lines)
    kinds = [
        ("券商研报", r"研究报告|年报点评|季报点评|深度研究|公司点评"),
        ("公告", r"公告(?:[（(].*?[）)])?$|分红派息实施|权益分派实施"),
        ("半年报", r"半年度报告|半年报|中期报告"),
        ("季报", r"季度报告|季度报|季报"),
        ("年报摘要", r"(?:年度报告|年报)摘要"),
        ("年报", r"年度报告|年报"),
    ]
    kind = next((kind for kind, pattern in kinds if re.search(pattern, heading, re.M)), None)
    if not kind:
        kind = next((kind for kind, pattern in kinds if re.search(pattern, title)), None)
    fiscal_year = re.compile(r"(?<!\d)((?:19|20)\d{2})(?=年?(?:年度|年报|半年|第?[一二三四1234]季|季报|中期|权益分派|分红))")
    year = fiscal_year.search(heading) or fiscal_year.search("".join(title.split()))
    company = None
    if kind != "券商研报":
        for line in lines:
            match = re.fullmatch(r"([\u4e00-\u9fffA-Za-z（）()·]{2,45}(?:股份有限公司|集团有限公司))", line)
            if match:
                company = match[1]
                break
    published = None
    stamp = re.search(r"(?:披露日期|发布日期|公告日期)[：:]?(\d{4})[年./-](\d{1,2})[月./-](\d{1,2})(?!\d)", heading)
    if stamp:
        try:
            published = date(*map(int, stamp.groups())).isoformat()
        except ValueError:
            pass
    return dict(title=title, type=kind, company=company,
                year=int(year[1]) if year else None, published=published)
