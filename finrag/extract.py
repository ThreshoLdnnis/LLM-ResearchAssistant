"""Conservative disclosure extraction. Keep observed units, exact row titles and source page."""
import re

LABELS = {
    "营业收入": "revenue", "营业利润": "operating_profit", "利润总额": "pretax_profit",
    "净利润": "net_profit", "归属于本行股东的净利润": "parent_profit",
    "归属于母公司股东的净利润": "parent_profit", "归属于上市公司股东的净利润": "parent_profit",
    "经营活动产生的现金流量净额": "operating_cash_flow",
    "归属于本行普通股股东的平均净资产收益率": "roe_average",
    "归属于本行普通股股东的加权平均净资产收益率": "roe_weighted",
    "归属于本行股东的平均总资产收益率": "roa_average",
    "毛利率": "gross_margin", "资产负债率": "liabilities_to_assets", "资本开支": "capex",
}
MONEY = re.compile(r"(?:人民币|单位[：:]\s*)(百万元|亿元|万元|元)")
CELL = re.compile(r"[-−]?(?:\d[\d,]*)(?:\.\d+)?%?|\([\d,.]+\)")
INLINE = re.compile(r"(营业收入|归属于本行股东的净利润|净利润|毛利率|资产负债率|资本开支)"
                    r"(?:为|达|约为)?\s*([-−]?[\d,]+(?:\.\d+)?)\s*(百万元|亿元|万元|元|%)")
CATEGORIES = {"风险": r"面临|风险上升|压力|不确定性|风险提示", "经营": r"市场份额|营业收入|客户数|业务增长",
              "管理层讨论": r"主要是|主要由于|主要为|展望|未来将", "关键事件": r"实施公告|股东大会|签署|并购|重大合同"}


def number(cell):
    raw = cell.replace(",", "").replace("−", "-").rstrip("%")
    return float("-" + raw[1:-1] if raw.startswith("(") else raw)


def fields(line):
    return [x.strip() for x in re.split(r"\s{2,}|\t|\s*\|\s*", line.strip()) if x.strip()]


def period_columns(line):
    # Only accept fully identified year / change columns with their actual order.
    parts = fields(line)
    columns = []
    for c in parts:
        c = re.sub(r"\s+", "", c)
        if re.fullmatch(r"(?:19|20)\d{2}年", c):
            columns.append(c[:-1])
        elif re.fullmatch(r"(?:19|20)\d{2}年\d{1,2}[-至]\d{1,2}月", c):
            columns.append(c)
        elif "增减" in c or "同比" in c:
            columns.append(None)
        elif columns:
            return []
    periods = [x for x in columns if x is not None]
    return columns if len(periods)>=2 and len(set(periods))==len(periods) else []


def financial(meta, page, layout, tables=True):
    columns, currency, scope = [], None, None
    output = []
    for line in layout.splitlines():
        line = line.strip()
        compact = re.sub(r"\s+", "", line)
        if "本集团" in compact or re.search(r"合并(?:利润|现金流量|资产负债)表",compact):
            scope = "集团"
        if "本公司主要" in compact or "母公司利润表" in compact:
            scope = "母公司"
        unit_match = MONEY.search(compact)
        if unit_match:
            currency = unit_match[1]
        parts = fields(line)
        if len(re.findall(r"(?:19|20)\d{2}年",compact)) >= 2:
            columns = period_columns(line)
            if meta["type"]=="季报" and any(p and len(p)==4 for p in columns):
                columns = []
            header = line
        if "按季度" in compact or "季度" in compact and any(c in compact for c in "一二三四"):
            columns = []
        base = {"doc": meta["id"], "page": page, "company": meta["company"], "source_type": meta["type"],
                "scope": scope, "quote": line}
        if tables and columns and len(parts) == len(columns) + 1 and parts[0] in LABELS:
            label = parts[0]
            percent = "率" in label
            for period, cell in zip(columns, parts[1:]):
                if period is None or not CELL.fullmatch(cell) or not (percent or currency):
                    continue
                output.append(dict(base, metric=LABELS[label], label=label, period=period,
                                   value=number(cell), unit="%" if percent else currency,
                                   evidence_type="table", header=header))
        elif len(parts) == 1 or "，" in line:
            # Keep period unresolved unless the sentence itself states a period.
            for match in INLINE.finditer(line):
                before = line[:match.start()]
                if before and not re.search(r"(?:实现|录得|集团|公司|本行|其中|[，。；：、])$", before):
                    continue
                periods = re.findall(r"20\d{2}年(?:\d{1,2}[-至]\d{1,2}月|第[一二三四]季度|度)?", before)
                output.append(dict(base, metric=LABELS[match[1]], label=match[1],
                                   period=periods[-1] if periods else None, value=number(match[2]),
                                   unit=match[3], evidence_type="inline"))
    return output


def narratives(meta, page, layout):
    for sentence in re.split(r"(?<=[。！？；])|\n\s*\n", layout):
        sentence = re.sub(r"\s+", " ", sentence).strip()
        if 12 <= len(sentence) <= 800:
            for category, pattern in CATEGORIES.items():
                if re.search(pattern, sentence):
                    yield dict(doc=meta["id"], page=page, company=meta["company"],
                               source_type=meta["type"], category=category, quote=sentence,
                               status="候选原文，待复核")

