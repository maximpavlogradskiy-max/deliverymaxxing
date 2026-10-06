"""Загрузка зала: сколько чеков зала открыто одновременно.

Чек ≠ стол: раздельный счёт даёт несколько чеков на стол, поэтому это оценка сверху.
Загрузка = одновременно открытые чеки / число столов (число столов нужно узнать у ресторана).
"""
import numpy as np
import pandas as pd

from common import load_orders

pd.set_option("display.width", 220)

o = load_orders()
# 10 минут – 6 часов: короче — навынос, длиннее — забытые открытые чеки
hall = o[(o["is_visit"] == 1) & (o["channel"] == "Зал и навынос") & (o["date"] >= "2026-05-01")
         & o["duration_min"].between(10, 360)]

grid = pd.date_range("2026-05-01 09:00", hall["close_time"].max().floor("D") + pd.Timedelta("23:45:00"), freq="15min")
grid = grid[(grid.hour >= 9) & (grid.hour <= 23)]
opens, closes = np.sort(hall["open_time"].values), np.sort(hall["close_time"].values)


def open_checks(at):
    at = np.asarray(at, dtype="datetime64[ns]")
    return np.searchsorted(opens, at, side="right") - np.searchsorted(closes, at, side="right")


c = pd.DataFrame({"t": grid, "open_checks": open_checks(grid.values)})
c["weekend"] = c["t"].dt.dayofweek >= 5
prof = c.groupby(["weekend", c["t"].dt.hour])["open_checks"].agg(mean="mean", p90=lambda s: s.quantile(.9))
print("Одновременно открытых чеков зала (май–октябрь 2026):")
print(prof.unstack(0).round(1).T.to_string())

daily_max = c.groupby(c["t"].dt.date)["open_checks"].max()
print("\nМаксимум за день, квантили:", daily_max.quantile([.5, .75, .9, .95]).round(0).to_dict())
print("Самые загруженные дни:", {str(k): int(v) for k, v in daily_max.nlargest(5).items()})

# Закон Литтла L = λ·W как проверка согласованности данных
wk = hall[(hall["open_time"].dt.dayofweek >= 5) & hall["open_time"].dt.hour.between(12, 20)]
lam = len(wk) / (wk["open_time"].dt.date.nunique() * 9 * 60)
measured = c[c["weekend"] & c["t"].dt.hour.between(12, 20)]["open_checks"].mean()
print(f"\nВыходные 12–21: λ = {lam:.3f} чека/мин × W = {wk['duration_min'].mean():.0f} мин = "
      f"L = {lam * wk['duration_min'].mean():.1f}; измерено {measured:.1f}")

# Признак насыщения: растёт ли длительность визита, когда зал полон
hall = hall.assign(open_at_arrival=open_checks(hall["open_time"].values))
g = hall.groupby(pd.cut(hall["open_at_arrival"], [0, 10, 20, 30, 40, 60, 500]), observed=True)["duration_min"]
print("\nДлительность визита (медиана, мин) по числу открытых чеков при приходе:")
print(pd.DataFrame({"n": g.size(), "duration_med": g.median().round(0)}).to_string())
