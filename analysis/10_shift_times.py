"""Во сколько повара приходят и уходят: BioTime, кухня Архангельского, май–август 2026.

Источник — data/raw/biotime/kitchen_2026-0{5..8}.csv, «Табель учёта рабочего времени», строки
«Приход» и «Уход» (подпись в конце файла: «Сформировано из системы учета рабочего времени BioTime 8»).
Для каждой должности: квантили прихода и ухода, доля смен с приходом 9:00–10:59 и уходом 22:00–23:59,
гистограмма прихода по получасам. В конце — несколько случайных смен со ссылкой на файл, строку и
столбец, чтобы проверить разбор по исходному CSV.

    python analysis/10_shift_times.py [должность ...]
"""
import sys

import pandas as pd

from biotime import load_shifts

pd.set_option("display.width", 220)

FROM, TO = "2026-05-01", "2026-09-01"
LINE = ["Повар ГЦ", "Повар ХЦ", "Повар-Мангал", "Бригадир ГЦ", "Бригадир ХЦ", "Су-Шеф ГЦ", "Пиццейло"]


def clock(hours):
    h = int(hours)
    return f"{h % 24:02d}:{round((hours - h) * 60):02d}"


def summary(s):
    a, d = s["arrive"], s["leave"]
    return pd.Series({
        "людей": s["emp"].nunique(),
        "смен": len(s),
        "приход p10": clock(a.quantile(.1)), "приход медиана": clock(a.median()), "приход p90": clock(a.quantile(.9)),
        "уход p10": clock(d.quantile(.1)), "уход медиана": clock(d.median()), "уход p90": clock(d.quantile(.9)),
        "часов медиана": round(s["hours"].median(), 1),
        "приход 9–11": a.between(9, 11, inclusive="left").mean(),
        "приход ≥11": (a >= 11).mean(),
        "уход 22–24": d.between(22, 24, inclusive="left").mean(),
        "оба условия": (a.between(9, 11, inclusive="left") & d.between(22, 24, inclusive="left")).mean(),
    })


s = load_shifts("kitchen_*.csv")
s = s[(s["date"] >= FROM) & (s["date"] < TO)].copy()
s["arrive"] = (s["start"] - s["date"]).dt.total_seconds() / 3600
s["leave"] = (s["end"] - s["date"]).dt.total_seconds() / 3600          # после полуночи — 24+
s["weekend"] = s["date"].dt.dayofweek >= 5
positions = sys.argv[1:] or None

print(f"Источник: data/raw/biotime/kitchen_*.csv, {s['dept'].iloc[0]}, {FROM} – {TO}: "
      f"{len(s)} смен, {s['emp'].nunique()} человек")

def percent(table):
    shares = ["приход 9–11", "приход ≥11", "уход 22–24", "оба условия"]
    table = table.copy()
    table[shares] = (table[shares].astype(float) * 100).round(0).astype(int).astype(str) + "%"
    return table


by_pos = s.groupby("position").apply(summary, include_groups=False).sort_values("смен", ascending=False)
if positions:
    by_pos = by_pos.loc[[p for p in positions if p in by_pos.index]]
print("\nПо должностям (доли — от смен):")
print(percent(by_pos).to_string())

line = s[s["position"].isin(LINE)]
both = pd.concat({"все дни": summary(line)}, axis=1).T
both = pd.concat([both, line.groupby("weekend").apply(summary, include_groups=False)
                  .rename(index={False: "будни", True: "выходные"})])
print("\nЛиния (повара ГЦ, ХЦ, мангал, бригадиры, су-шеф ГЦ, пиццейло):")
print(percent(both).T.to_string())

print("\nПриход по получасам, линия (доля смен):")
bins = (line["arrive"] * 2).astype(int) / 2
hist = bins.value_counts(normalize=True).sort_index()
for b, p in hist[hist >= .005].items():
    print(f"  {clock(b)}–{clock(b + .5)}  {'█' * round(p * 100):<40} {p:.0%}")

print("\nУход по получасам, линия (доля смен):")
bins = (line["leave"] * 2).astype(int) / 2
hist = bins.value_counts(normalize=True).sort_index()
for b, p in hist[hist >= .005].items():
    print(f"  {clock(b)}–{clock(b + .5)}  {'█' * round(p * 100):<40} {p:.0%}")

print("\nСлучайные смены для проверки по исходному файлу (псевдоним вместо ФИО):")
check = line.sample(8, random_state=1).sort_values("start")
print(check.assign(приход=check["start"].dt.strftime("%H:%M"), уход=check["end"].dt.strftime("%H:%M"),
                   дата=check["date"].dt.strftime("%d.%m"))
      [["emp", "position", "дата", "приход", "уход", "src"]].to_string(index=False))
