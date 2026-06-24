#!/usr/bin/env python3
"""统计云南客户时间分表：按业务日(2026-06-01~22)与跨夜小时(22:00-05:00)汇总。"""

import csv
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

INPUT_FILE = Path("/Users/dmm/Desktop/云南客户时间分表.xlsx")
OUTPUT_FILE = Path("/Users/dmm/Desktop/开沃/统计结果_22to05.csv")

TIME_FIELDS = ["创建时间", "派车时间", "装到达时间", "装离开时间", "卸到达时间", "卸离开时间"]
# 22:00-05:00 跨夜区间，按自然顺序排列
TARGET_HOURS = [22, 23, 0, 1, 2, 3, 4, 5]
DATE_START = datetime(2026, 6, 1).date()
DATE_END = datetime(2026, 6, 22).date()
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
EXCEL_EPOCH = datetime(1899, 12, 30)


def read_xlsx_rows(path: Path, sheet_name: str = "Sheet1"):
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall(".//m:si", NS):
                texts = si.findall(".//m:t", NS)
                shared.append("".join(t.text or "" for t in texts))

        wb = ET.fromstring(z.read("xl/workbook.xml"))
        sheet_id = None
        for sheet in wb.findall(".//m:sheet", NS):
            if sheet.attrib.get("name") == sheet_name:
                sheet_id = sheet.attrib[
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                ]
                break
        if sheet_id is None:
            raise ValueError(f"未找到工作表: {sheet_name}")

        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        target = None
        for rel in rels:
            if rel.attrib.get("Id") == sheet_id:
                target = "xl/" + rel.attrib["Target"].lstrip("/")
                break
        if target is None:
            raise ValueError(f"无法定位工作表文件: {sheet_name}")

        root = ET.fromstring(z.read(target))
        rows_out = []
        for row in root.findall(".//m:sheetData/m:row", NS):
            row_vals = {}
            for cell in row.findall("m:c", NS):
                ref = cell.attrib.get("r", "")
                col = "".join(ch for ch in ref if ch.isalpha())
                v_el = cell.find("m:v", NS)
                if v_el is None or v_el.text is None:
                    val = None
                elif cell.attrib.get("t") == "s":
                    val = shared[int(v_el.text)]
                else:
                    val = v_el.text
                row_vals[col] = val
            if row_vals:
                rows_out.append(row_vals)
        return rows_out


def col_letter(index: int) -> str:
    """0 -> A, 1 -> B, ..."""
    result = ""
    n = index + 1
    while n:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def to_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def excel_serial_to_datetime(date_serial, time_serial):
    d = to_float(date_serial)
    t = to_float(time_serial)
    if d is None and t is None:
        return None
    total = (d or 0) + (t or 0)
    return EXCEL_EPOCH + timedelta(days=total)


def event_to_business_key(dt: datetime):
    """将事件时间映射到业务日及小时区间。

    业务日 D 对应窗口：D 日 22:00 ~ D+1 日 05:59
    """
    hour = dt.hour
    if hour in (22, 23):
        business_date = dt.date()
    elif 0 <= hour <= 5:
        business_date = dt.date() - timedelta(days=1)
    else:
        return None
    if business_date < DATE_START or business_date > DATE_END:
        return None
    return business_date, hour


def row_to_dict(row_vals):
    record = {}
    for i, field in enumerate(TIME_FIELDS):
        date_col = col_letter(i * 2)
        time_col = col_letter(i * 2 + 1)
        record[field] = excel_serial_to_datetime(row_vals.get(date_col), row_vals.get(time_col))
    return record


def main():
    raw_rows = read_xlsx_rows(INPUT_FILE, "Sheet1")
    if not raw_rows:
        raise SystemExit("Excel 文件为空")

    # 跳过表头（第一行通常是字段名）
    data_rows = []
    for row_vals in raw_rows[1:]:
        rec = row_to_dict(row_vals)
        if any(v is not None for v in rec.values()):
            data_rows.append(rec)

    all_dates = []
    d = DATE_START
    while d <= DATE_END:
        all_dates.append(d)
        d += timedelta(days=1)

    counts = defaultdict(lambda: defaultdict(int))
    for rec in data_rows:
        for field in TIME_FIELDS:
            dt = rec[field]
            if dt is None:
                continue
            key = event_to_business_key(dt)
            if key is None:
                continue
            counts[key][field] += 1

    rows = []
    for date in all_dates:
        for hour in TARGET_HOURS:
            key = (date, hour)
            row = {
                "日期": date.isoformat(),
                "小时区间": f"{hour:02d}:00-{hour:02d}:59",
            }
            total = 0
            for field in TIME_FIELDS:
                cnt = counts[key][field]
                row[field] = cnt
                total += cnt
            row["总数"] = total
            rows.append(row)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["日期", "小时区间"] + TIME_FIELDS + ["总数"]
    with OUTPUT_FILE.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"已生成 {OUTPUT_FILE}，共 {len(rows)} 行")
    print("预览前10行：")
    for r in rows[:10]:
        print(r)


if __name__ == "__main__":
    main()
