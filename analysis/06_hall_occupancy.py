"""Загрузка зала по столам (см. common.table_occupancy).

Вместимость — столы из чеков, а не план зала: сверить с управляющим.
"""
import pandas as pd

from common import HALLS, hall_visits, table_occupancy

pd.set_option("display.width", 220)

SINCE = "2026-05-01"

h = hall_visits(SINCE)
occ, cap, capacity_month = table_occupancy(h)
print("Столов по месяцам (разные столы в чеках):")
print(capacity_month.to_string())

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
