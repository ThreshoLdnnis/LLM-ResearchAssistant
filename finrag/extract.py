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
MONEY = re.compile(r"(?:人民币|单位[：:]\s*)(百万元|亿元|万元|千元|元)")
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


ANNUAL_STATEMENT = re.compile(r"(?:\d{4}年度?)?合并及(?:母)?公司(?:利润表|现金流量表)(?:[（(]续[）)])?$")
ANNUAL_YEAR = re.compile(r"((?:19|20)\d{2})年(?:度)?")
STATEMENT_SCOPES = {"合并": "集团", "公司": "母公司", "母公司": "母公司"}
SINGLE_STATEMENT = re.compile(r"(?:(?:19|20)\d{2}年度?)?(合并|母公司|公司)(利润表|现金流量表)(?:[（(]续[）)])?")
INCOME_YEARS = re.compile(r"项目(附注)?((?:19|20)\d{2})年度?((?:19|20)\d{2})年度?")
REVENUE_LINE = re.compile(r"^(?:[一二三四五六七八九十]+、\s*)?(?:其中[：:]\s*)?营业收入\s+(.+)$")
PARENT_LINE = re.compile(r"^(?:\d+[.、])?归属于母公司股东的净利润(?:[（(]净?亏损以[^）)]*[）)])?(?:\s+(.+))?$")
CASH_LINE = re.compile(r"^经营活动产生的现金流量净额\s+(.+)$")
NOTE_REFERENCE = re.compile(r"[一二三四五六七八九十\d]+(?:[（(][一二三四五六七八九十\da-zA-Z]+[）)])*")


def statement_cells(text, has_note):
    cells = text.split()
    if has_note and len(cells) == 3 and NOTE_REFERENCE.fullmatch(cells[0]):
        cells = cells[1:]
    elif has_note and len(cells) == 2 and "," not in cells[0]:
        # Without a visible note, an ungrouped first number can itself be a note reference.
        return []
    if len(cells) != 2 or not all(CELL.fullmatch(c) and not c.endswith("%") for c in cells):
        return []
    return cells


def parallel_statement(meta, page, lines):
    """Read adjacent year/scope headers on group and parent annual statements."""
    raw = [line.strip() for line in lines if line.strip()]
    units, currency, columns, header = None, None, [], ""
    previous = ""
    for index, line in enumerate(raw):
        compact = re.sub(r"\s+", "", line)
        unit = MONEY.search(compact)
        if unit:
            units = unit[1]
            currency = "CNY" if "人民币" in compact else None
        year_text = re.sub(r"^(?:项目)?(?:附注)?", "", compact)
        years = ANNUAL_YEAR.findall(year_text)
        if len(years) >= 2:
            columns = []
            if index + 1 >= len(raw) or ANNUAL_YEAR.sub("", year_text):
                continue
            scope_text = re.sub(r"^(?:项目\s*)?(?:附注\s*)?", "", raw[index + 1])
            scopes = [STATEMENT_SCOPES.get(word) for word in scope_text.split()]
            pairs = list(zip(years, scopes))
            if (len(years) == len(scopes) and set(scopes) == {"集团", "母公司"}
                    and len(pairs) == len(set(pairs))):
                columns = pairs
                header = line + "\n" + raw[index + 1]
            continue
        if not columns or not units:
            continue
        parts = line.rsplit(None, len(columns))
        if len(parts) != len(columns) + 1:
            previous = compact
            continue
        row_title, *cells = parts
        label = re.sub(r"\s+[一二三四五六七八九十\d]+(?:[（(][\da-zA-Z]+[）)])+$", "", row_title)
        label = re.sub(r"^(?:[一二三四五六七八九十]+、|其中[：:])", "", label.strip())
        quote = line
        if previous + label in LABELS:
            label = previous + label
            quote = raw[index - 1] + "\n" + line
        elif previous.endswith("的"):
            label = ""
        previous = compact
        if label not in LABELS or "率" in label:
            continue
        if not all((CELL.fullmatch(c) and not c.endswith("%")) or c in {"-", "—"} for c in cells):
            continue
        for (period, scope), cell in zip(columns, cells):
            if CELL.fullmatch(cell):
                yield dict(doc=meta["id"], page=page, company=meta["company"], source_type=meta["type"],
                           report_year=meta["year"], published=meta["published"], scope=scope,
                           quote=quote, metric=LABELS[label], label=label, period=period,
                           value=number(cell), unit=units, currency=currency, evidence_type="table", header=header)


QUARTER_TITLE = re.compile(r"((?:19|20)\d{2})年第?([一二三四1-4])季(?:度)?(?:报告|报)")
QUARTER_HEADINGS = ("本报告期", "年初至报告期末")
YOY_SUFFIX = "比上年同期增减"
QUARTER_LABEL = re.compile(
    r"(营业收入|归属于上市公司股东的净利润|经营活动产生的现金流量净额)"
    r"[（(](人民币)?(百万元|亿元|万元|千元|元)[）)]")
QUARTER_CELL = r"(?:[+−-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?|[-—–－]{1,2})"
FOUR_CELLS = re.compile(r"(?<!\S)" + r"\s+".join([QUARTER_CELL] * 4) + r"(?!\S)")


def quarter_columns(lines):
    """Identify the actual four headings, including the staggered PDF layout."""
    names = set(QUARTER_HEADINGS)
    expected = names | {name + YOY_SUFFIX for name in names}
    text = "".join("".join(lines).split()).removeprefix("项目")
    pattern = "|".join(sorted(expected, key=len, reverse=True))
    pieces = re.findall(pattern, text)
    if len(pieces) == 4 and set(pieces) == expected and "".join(pieces) == text:
        return pieces

    # In a wrapped header the two amounts occupy one line. The two YoY
    # headings wrap above/below it, in the same horizontal coordinate space.
    cells = [list(re.finditer(r"\S+(?: \S+)*", line)) for line in lines]
    if not cells or any(len(row) != 2 for row in cells):
        return []
    amount_rows = [i for i, row in enumerate(cells) if {c[0].replace(" ", "") for c in row} == names]
    if len(amount_rows) != 1:
        return []
    amounts = cells.pop(amount_rows[0])
    if not cells:
        return []
    changes = ["".join(row[j][0].replace(" ", "") for row in cells) for j in range(2)]
    if set(changes) != {name + YOY_SUFFIX for name in names}:
        return []
    positioned = [(cell.start(), cell[0].replace(" ", "")) for cell in amounts]
    positioned += [(cell.start(), name) for cell, name in zip(cells[0], changes)]
    if len({pos for pos, _ in positioned}) != 4:
        return []
    return [name for _, name in sorted(positioned)]


def quarterly_summary(meta, page, lines):
    raw = [line for line in lines if line.strip()]
    titles = "".join(str(meta.get("title") or "").split()) + "\n" + "\n".join(
        "".join(line.split()) for line in raw[:3])
    periods = {(year, int(q.translate(str.maketrans("一二三四", "1234")))) for year, q in QUARTER_TITLE.findall(titles)}
    if len(periods) != 1:
        return
    year, quarter = periods.pop()
    if meta.get("year") and str(meta["year"]) != year:
        return
    # Scan one contiguous header at a time. Require both YoY headings and both period headings.
    header_lines, columns = [], []
    for i, line in enumerate(raw):
        compact = "".join(line.split())
        if re.fullmatch(r"[项目本报告期比上年同初至末增减]+", compact):
            header_lines.append(line)
            columns = []
            continue
        if header_lines:
            columns = quarter_columns(header_lines)
            header = "\n".join(header_lines)
            header_lines = []
        if compact.startswith(("本报告期末", "上年度末", "单位：", "单位:")) or re.match(r"^[（(][一二三四五六七八九十]+[）)]", compact):
            columns = []
        if not columns or not compact.startswith(("营业收入", "归属于上市公司股东", "经营活动产生的现金流量")):
            continue
        # A long row name or its unit can wrap onto either side of the number line.
        for length in range(1, min(3, len(raw) - i) + 1):
            quote = "\n".join(raw[i:i + length]).strip()
            values = FOUR_CELLS.search(quote)
            if not values:
                continue
            label_text = "".join((quote[:values.start()] + quote[values.end():]).split())
            label_match = QUARTER_LABEL.fullmatch(label_text)
            if not label_match:
                continue
            cells = dict(zip(columns, values[0].split()))
            pairs = [(cells[name], cells[name + YOY_SUFFIX]) for name in QUARTER_HEADINGS]
            if any(amount.endswith("%") or (re.search(r"\d", yoy) and not yoy.endswith("%"))
                   for amount, yoy in pairs):
                break
            label, currency, unit = label_match.groups()
            for j, (amount, yoy) in enumerate(pairs):
                start = 3 * quarter - 2 if j == 0 else 1
                value = number(amount) if re.search(r"\d", amount) else None
                yield dict(doc=meta["id"], page=page, company=meta["company"], source_type=meta["type"],
                           report_year=meta.get("year") or int(year), published=meta["published"], scope=None,
                           metric=LABELS[label], label=label, period=f"{year}年{start}-{3 * quarter}月",
                           period_kind=("quarter", "year_to_date")[j], period_label=QUARTER_HEADINGS[j],
                           value=value, unit=unit, currency="CNY" if currency else None,
                           reported_yoy_pct=number(yoy) if yoy.endswith("%") else None,
                           value_status="disclosed" if value is not None else "not_disclosed",
                           quote=quote, header=header, evidence_type="table")
            break


def financial(meta, page, layout, tables=True, *, statement=None):
    columns, scale, denomination, scope = [], None, None, None
    title_scope = table_kind = table_years = None
    table_header = ""
    if statement and statement.get("next") == (meta["id"], page):
        title_scope, table_kind, table_years, table_header, scale, denomination = statement["context"]
    if statement is not None:
        statement.clear()
    output = []
    lines = layout.splitlines()
    if tables and meta["type"] == "季报" and "年初至报告期末" in "".join(layout.split()):
        output.extend(quarterly_summary(meta, page, lines))
    if tables and meta["type"] != "季报" and "合并及" in layout and any(
            ANNUAL_STATEMENT.fullmatch("".join(line.split())) for line in lines):
        output.extend(parallel_statement(meta, page, lines))
    for index, line in enumerate(lines):
        line = line.strip()
        compact = re.sub(r"\s+", "", line)
        title = SINGLE_STATEMENT.fullmatch(compact)
        if title and meta["type"] in {"年报", "年报摘要"}:
            title_scope, table_kind = STATEMENT_SCOPES[title[1]], title[2]
            scope = title_scope
            table_years = scale = denomination = None
            columns = []
        elif title_scope and (compact.endswith(("表", "报表附注")) or compact.startswith(("公司负责人", "法定代表人"))):
            title_scope = table_years = None
        if "本集团" in compact or re.search(r"合并(?:利润|现金流量|资产负债)表",compact):
            scope = "集团"
        if "本公司主要" in compact or "母公司利润表" in compact:
            scope = "母公司"
        unit_match = MONEY.search(compact)
        if unit_match:
            scale = unit_match[1]
            denomination = "CNY" if "人民币" in compact else None
        parts = fields(line)
        if title_scope and (compact.startswith("项目") or len(ANNUAL_YEAR.findall(compact)) >= 2):
            table_years = INCOME_YEARS.fullmatch(compact)
            table_header = line
            if table_years and table_years[2] == table_years[3]:
                table_years = None
        if len(re.findall(r"(?:19|20)\d{2}年",compact)) >= 2:
            columns = period_columns(line)
            if meta["type"]=="季报" and any(p and len(p)==4 for p in columns):
                columns = []
            header = line
        if "按季度" in compact or "季度" in compact and any(c in compact for c in "一二三四"):
            columns = []
        base = {"doc": meta["id"], "page": page, "company": meta["company"], "source_type": meta["type"],
                "report_year": meta["year"],"published":meta["published"],"scope": scope, "quote": line}
        row_columns = columns
        row_header = line if not columns else header
        if tables and table_years and title_scope:
            label, cell_text = None, None
            if table_kind == "现金流量表" and (match := CASH_LINE.fullmatch(line)):
                label, cell_text = "经营活动产生的现金流量净额", match[1]
            elif table_kind == "利润表" and (match := REVENUE_LINE.fullmatch(line)):
                label, cell_text = "营业收入", match[1]
            elif table_kind == "利润表" and (match := PARENT_LINE.fullmatch(line)):
                label, cell_text = "归属于母公司股东的净利润", match[1]
            elif (table_kind == "利润表" and re.fullmatch(r"(?:\d+[.、])?归属于母公司股东的净利润[（(](?:净|净?亏损以.*)?", compact)
                  and index + 1 < len(lines)):
                label, cell_text = "归属于母公司股东的净利润", lines[index + 1].strip()
                base["quote"] = line + "\n" + cell_text
            if label:
                parts = [label, *statement_cells(cell_text or "", bool(table_years[1]))]
                row_columns = [table_years[2], table_years[3]]
                row_header = table_header
                base["scope"] = title_scope
        if tables and row_columns and len(parts) == len(row_columns) + 1 and parts[0] in LABELS:
            label = parts[0]
            percent = "率" in label
            for period, cell in zip(row_columns, parts[1:]):
                if period is None or not CELL.fullmatch(cell) or not (percent or scale):
                    continue
                output.append(dict(base, metric=LABELS[label], label=label, period=period,
                                   value=number(cell), unit="%" if percent else scale,
                                   currency=None if percent else denomination,
                                   evidence_type="table", header=row_header))
        elif len(parts) == 1 or "，" in line:
            # Keep period unresolved unless the sentence itself states a period.
            for match in INLINE.finditer(line):
                before = line[:match.start()]
                if before and not re.search(r"(?:实现|录得|集团|公司|本行|其中|[，。；：、])$", before):
                    continue
                periods = re.findall(r"20\d{2}年(?:\d{1,2}[-至]\d{1,2}月|第[一二三四]季度|度)?", before)
                output.append(dict(base, metric=LABELS[match[1]], label=match[1],
                                   period=periods[-1] if periods else None, value=number(match[2]),
                                   unit=match[3],currency=None if match[3]=="%" else denomination,
                                   evidence_type="inline"))
    if statement is not None and title_scope and table_years and denomination:
        statement.update(next=(meta["id"], page + 1),
                         context=(title_scope, table_kind, table_years, table_header, scale, denomination))
    return output


def narratives(meta, page, layout):
    for sentence in re.split(r"(?<=[。！？；])|\n\s*\n", layout):
        sentence = re.sub(r"\s+", " ", sentence).strip()
        if 12 <= len(sentence) <= 800:
            for category, pattern in CATEGORIES.items():
                if re.search(pattern, sentence):
                    yield dict(doc=meta["id"], page=page, company=meta["company"],
                               source_type=meta["type"],report_year=meta["year"],published=meta["published"],
                               category=category, quote=sentence,
                               status="候选原文，待复核")

