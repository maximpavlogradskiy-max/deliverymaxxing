"""Разбор выгрузок «Табель учёта рабочего времени» из BioTime 8 (CSV через «;»).

На сотрудника — два блока по шесть строк (Код, Норма, Факт, итог, Приход, Уход): дни 1–15 и 16–31.
ФИО сразу заменяются псевдонимом (первые 8 знаков sha1), в результат не попадают.

    from biotime import load_shifts
    s = load_shifts()   # смена = сотрудник × день: emp, dept, position, date, start, end, hours
"""
import hashlib
import re
from pathlib import Path

import pandas as pd

from common import RAW

BIOTIME = RAW / "biotime"
TIME = re.compile(r"^\d{1,2}:\d{2}$")


def _pseudonym(name):
    return hashlib.sha1(name.strip().lower().encode()).hexdigest()[:8]


def _day_columns(header):
    return {i: int(v) for i, v in enumerate(header) if v.strip().isdigit()}


def parse_file(path):
    lines = [l.rstrip("\r\n").split(";") for l in Path(path).read_text(encoding="utf-8").splitlines()]
    dept = lines[3][1].strip()
    month_start = pd.to_datetime(next(v for v in lines[4] if re.match(r"^01\.\d{2}\.\d{4}$", v)), dayfirst=True)
    halves = [_day_columns(lines[9]), _day_columns(lines[10])]   # дни 1–15 и 16–31

    blocks, current = [], None
    for row in lines[11:]:
        if row and row[0].startswith("Ответственное") or (len(row) > 1 and row[1].startswith("Ответственное")):
            break
        kind = row[7].strip() if len(row) > 7 else ""
        if kind == "Код":
            current = {"labels": [], "rows": {}}
            blocks.append(current)
        if current is None:
            continue
        label = row[3].strip() if len(row) > 3 else ""
        if label:
            current["labels"].append(label)
        if kind in ("Факт", "Приход", "Уход"):
            current["rows"][kind] = row

    shifts = []
    for k in range(0, len(blocks) - 1, 2):
        labels = [l for b in blocks[k:k + 2] for l in b["labels"] if not l.isupper()]
        if not labels:
            continue
        emp, position = _pseudonym(labels[0]), (labels[1] if len(labels) > 1 else "")
        for half, block in zip(halves, blocks[k:k + 2]):
            rows = block["rows"]
            for col, day in half.items():
                cell = lambda kind: rows.get(kind, [""] * (col + 1))[col].strip() if col < len(rows.get(kind, [])) else ""
                arrive, leave = cell("Приход"), cell("Уход")
                if not (TIME.match(arrive) and TIME.match(leave)):
                    continue
                date = month_start + pd.Timedelta(days=day - 1)
                start = date + pd.to_timedelta(arrive + ":00")
                end = date + pd.to_timedelta(leave + ":00")
                if end <= start:            # ушёл после полуночи
                    end += pd.Timedelta(days=1)
                shifts.append({"emp": emp, "dept": dept, "position": position, "date": date,
                               "start": start, "end": end})
    s = pd.DataFrame(shifts)
    if len(s):
        s["hours"] = (s["end"] - s["start"]).dt.total_seconds() / 3600
    return s


def load_shifts(pattern="*.csv"):
    files = sorted(BIOTIME.glob(pattern))
    if not files:
        raise FileNotFoundError(f"нет выгрузок BioTime в {BIOTIME}")
    return pd.concat([parse_file(f) for f in files], ignore_index=True).drop_duplicates(["emp", "start"])


def headcount(shifts, index):
    """Сколько человек на смене в каждый момент index (DatetimeIndex)."""
    starts, ends = shifts["start"].sort_values().values, shifts["end"].sort_values().values
    at = index.values
    return pd.Series(starts.searchsorted(at, side="right") - ends.searchsorted(at, side="right"), index=index)
