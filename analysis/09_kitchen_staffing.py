"""Повара на смене (BioTime) против потока блюд по цехам, май–август 2026.

Цех повара — по должности; блюда — по месту приготовления в кассе (паста и мангал готовит горячий
цех: повар мангала выходит редко). Производительность цеха — 95-й процентиль блюд за 15 минут на
одного повара: раз время готовки доставки от нагрузки не растёт (05), это нижняя оценка мощности.
Нужно поваров = max(1, ⌈p90 блюд в час / мощность⌉) по каждому часу и типу дня.
Оговорка: в спокойные часы повара делают заготовки — блюда в чеках это не учитывают.
"""
import numpy as np
import pandas as pd

from biotime import headcount, load_shifts
from common import station_lines

pd.set_option("display.width", 220)

FROM, TO = "2026-05-01", "2026-09-01"
COOKS = {"горячий": ["Повар ГЦ", "Бригадир ГЦ", "Су-Шеф ГЦ", "Повар-Мангал"],
         "холодный": ["Повар ХЦ", "Бригадир ХЦ"],
         "пицца": ["Пиццейло"]}
DISHES = {"горячий": ["горячий", "паста", "мангал"], "холодный": ["холодный"], "пицца": ["пицца"]}
HOURLY_COST = 440   # ₽ за час повара, табель июня

s = load_shifts("kitchen_*.csv")
s = s[(s["date"] >= FROM) & (s["date"] < TO)]
print("Часы кухни по должностям за 4 месяца:", s.groupby("position")["hours"].sum().round(0).sort_values(ascending=False).to_dict())

grid = pd.date_range(FROM, TO, freq="15min", inclusive="left")
grid = grid[(grid.hour >= 10) & (grid.hour <= 22)]
st = station_lines(since=FROM)
st = st[st["add_time"] < TO]

rows, summary = [], []
for station in COOKS:
    cooks = headcount(s[s["position"].isin(COOKS[station])], grid)
    d = st[st["station"].isin(DISHES[station])].set_index("add_time")["units"].resample("15min").sum()
    d = d.reindex(grid, fill_value=0)
    x = pd.DataFrame({"cooks": cooks, "dishes": d})
    x["weekend"] = x.index.dayofweek >= 5
    busy = x[x["cooks"] > 0]
    capacity = (busy["dishes"] / busy["cooks"]).quantile(.95) * 4          # блюд в час на повара
    hourly = x.groupby([x["weekend"], x.index.hour]).agg(cooks=("cooks", "mean"),
                                                         dishes=("dishes", lambda v: v.mean() * 4),
                                                         dishes_p90=("dishes", lambda v: v.quantile(.9) * 4))
    hourly["needed"] = np.maximum(1, np.ceil(hourly["dishes_p90"] / capacity))
    hourly["station"] = station
    rows.append(hourly)
    days = x.index.normalize().to_series().groupby(x["weekend"].values).nunique()
    n_days = pd.Series([days[w] for w, _ in hourly.index], index=hourly.index)
    actual_h = (hourly["cooks"] * n_days).sum()
    excess_h = ((hourly["cooks"] - hourly["needed"]).clip(lower=0) * n_days).sum()
    short_h = ((hourly["needed"] - hourly["cooks"]).clip(lower=0) * n_days).sum()
    summary.append({"цех": station, "мощность, блюд/час на повара": capacity, "повар-часов 10–23": actual_h,
                    "лишних": excess_h, "не хватает": short_h, "доля лишних": excess_h / actual_h})

prof = pd.concat(rows).reset_index().rename(columns={"level_1": "hour", "add_time": "hour"})
for station, g in prof.groupby("station"):
    t = g.set_index(["weekend", g.columns[1]])[["cooks", "dishes", "dishes_p90", "needed"]]
    print(f"\n{station}: поваров на смене, блюд в час (среднее и p90), нужно поваров — по часам")
    print(t.round(1).unstack(0).T.to_string())

sm = pd.DataFrame(summary).set_index("цех")
print("\nИтог за 4 месяца (линия 10–23, без заготовщиков, сыровара и шефов):")
print(sm.round(2).to_string())
excess = sm["лишних"].sum()
print(f"Лишних повар-часов: {excess:.0f} за 4 месяца ≈ {excess / 4:.0f} в месяц ≈ {excess / 4 * HOURLY_COST / 1000:.0f} тыс.₽ в месяц")
