"""Загрузка зала по столам.

Стол занят, пока на нём открыт хотя бы один чек; «28,1» — дополнительный чек стола 28.
Вместимость зала — сколько разных столов работало в этом месяце; веранды считаются только в дни,
когда на них были гости. Это столы из чеков, а не план зала: сверить с управляющим.
"""
import numpy as np
import pandas as pd

from common import load_orders

pd.set_option("display.width", 220)

HALLS = ["Зал 1эт", "Зал 2эт", "Веранда1", "Веранда2"]
SINCE = "2026-05-01"

o = load_orders()
# 10 минут – 6 часов: короче — навынос, длиннее — забытые открытые чеки
h = o[(o["is_visit"] == 1) & o["hall"].isin(HALLS) & (o["date"] >= SINCE)
      & o["duration_min"].between(10, 360) & o["table_name"].notna()].copy()
h["table"] = h["hall"] + " / " + h["table_name"].str.split(",").str[0].str.strip()

# интервалы занятости стола: пересекающиеся чеки одного стола сливаются
busy = []
for table, g in h.sort_values("open_time").groupby("table"):
    start, end = None, None
    for a, b in zip(g["open_time"], g["close_time"]):
        if start is None or a > end:
            if start is not None:
                busy.append((table, start, end))
            start, end = a, b
        else:
            end = max(end, b)
    busy.append((table, start, end))
busy = pd.DataFrame(busy, columns=["table", "start", "end"])
busy["hall"] = busy["table"].str.split(" / ").str[0]

grid = pd.date_range(f"{SINCE} 09:00", h["close_time"].max().floor("D") + pd.Timedelta("23:45:00"), freq="15min")
grid = grid[(grid.hour >= 10) & (grid.hour <= 22)]
occ = pd.DataFrame(index=grid)
for hall, g in busy.groupby("hall"):
    s, e = np.sort(g["start"].values), np.sort(g["end"].values)
    occ[hall] = np.searchsorted(s, grid.values, side="right") - np.searchsorted(e, grid.values, side="right")

month = h["date"].dt.to_period("M")
capacity_month = h.groupby([month, "hall"])["table"].nunique().unstack()
open_days = h.groupby([h["date"], "hall"]).size().unstack().notna()   # был ли зал открыт в этот день
cap = pd.DataFrame(index=grid, columns=HALLS, dtype=float)
for hall in HALLS:
    per_month = capacity_month[hall].reindex(grid.to_period("M")).to_numpy()
    is_open = open_days[hall].reindex(grid.normalize(), fill_value=False).to_numpy()
    cap[hall] = np.where(is_open, per_month, 0)
print("Столов по месяцам (разные столы в чеках):")
print(capacity_month.to_string())

occ["total"] = occ[HALLS].sum(axis=1)
cap["total"] = cap[HALLS].sum(axis=1)
share = (occ["total"] / cap["total"]).rename("occupancy")
share = share[cap["total"] > 0]
weekend = share.index.dayofweek >= 5
prof = share.groupby([weekend, share.index.hour]).agg(mean="mean", p90=lambda s: s.quantile(.9))
print("\nЗанято столов от работающих, весь ресторан (май–октябрь 2026):")
print((100 * prof).unstack(0).round(0).T.to_string())

peak = share[weekend & (share.index.hour >= 13) & (share.index.hour <= 19)]
print(f"\nВыходные 13–20: занято в среднем {peak.mean():.0%}; доля времени ≥ 85% — {(peak >= .85).mean():.0%}, "
      f"≥ 95% — {(peak >= .95).mean():.0%}")

by_hall = pd.DataFrame({hall: occ[hall][cap[hall] > 0] / cap[hall][cap[hall] > 0] for hall in HALLS})
wk_peak = by_hall[(by_hall.index.dayofweek >= 5) & (by_hall.index.hour >= 13) & (by_hall.index.hour <= 19)]
print("По залам в выходные 13–20, средняя загрузка и p90:")
print(pd.DataFrame({"mean_%": 100 * wk_peak.mean(), "p90_%": 100 * wk_peak.quantile(.9)}).round(0).to_string())

# Признак насыщения: растёт ли длительность визита, когда занято больше столов
h["occ_at_arrival"] = share.reindex(h["open_time"].dt.floor("15min")).to_numpy()
g = h.groupby(pd.cut(h["occ_at_arrival"], [0, .3, .5, .7, .85, 1.5]), observed=True)["duration_min"]
print("\nДлительность визита (медиана, мин) по загрузке зала при приходе:")
print(pd.DataFrame({"n": g.size(), "duration_med": g.median().round(0)}).to_string())
