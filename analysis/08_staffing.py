"""Смены курьеров и официантов (BioTime) против нагрузки, май–август 2026.

Курьеры: сколько человек на смене в каждый час, сколько доставок своими курьерами (заказы
агрегаторов «Доставка ресторана» + своя доставка из кассы), доставок на курьеро-час, и как
ожидание курьера зависит от числа курьеров на смене.
Официанты: занятые столы на одного официанта по часам.
"""
import numpy as np
import pandas as pd

from biotime import headcount, load_shifts
from common import hall_visits, load_orders, load_vendor_orders, ols, pay_channel, table_occupancy, window_sum

pd.set_option("display.width", 220)

FROM, TO = "2026-05-01", "2026-09-01"
s = load_shifts()
s = s[(s["date"] >= FROM) & (s["date"] < TO)]
grid = pd.date_range(f"{FROM} 00:00", f"{TO} 00:00", freq="15min", inclusive="left")
grid = grid[(grid.hour >= 9) & (grid.hour <= 23)]
days = grid.normalize().nunique()

# --- курьеры ---
crew = {p: headcount(s[s["position"] == p], grid) for p in ["Курьер", "Курьер авто", "Менеджер доставки"]}
crew = pd.DataFrame(crew)

v = load_vendor_orders()
v = v[v["completed"] & (v["delivery_type"] == "Доставка ресторана") & (v["created"] >= FROM) & (v["created"] < TO)]
o = load_orders()
own = o[(o["is_visit"] == 1) & (o["pay_type"].map(pay_channel) == "своя доставка")
        & (o["open_time"] >= FROM) & (o["open_time"] < TO)]
deliveries = pd.concat([v["created"], own["open_time"]]).sort_values()

hour = grid.hour
courier_hours = crew["Курьер"].groupby(hour).sum() / 4          # 15-минутные отсчёты → часы
deliv_by_hour = deliveries.groupby(deliveries.dt.hour).size().reindex(courier_hours.index, fill_value=0)
prof = pd.DataFrame({
    "курьеров": crew["Курьер"].groupby(hour).mean(),
    "курьер авто": crew["Курьер авто"].groupby(hour).mean(),
    "менеджер": crew["Менеджер доставки"].groupby(hour).mean(),
    "доставок в час": deliv_by_hour / days,
    "доставок на курьеро-час": deliv_by_hour / courier_hours.replace(0, np.nan),
})
print(f"Курьеры, среднее за {days} дней ({FROM} – {TO}), по часам:")
print(prof.round(2).T.to_string())

month = deliveries.dt.to_period("M")
shifts_m = s[s["position"] == "Курьер"].groupby(s["date"].dt.to_period("M")).agg(смен=("emp", "size"), часов=("hours", "sum"))
shifts_m["доставок"] = deliveries.groupby(month).size()
shifts_m["доставок на смену"] = shifts_m["доставок"] / shifts_m["смен"]
shifts_m["доставок на курьеро-час"] = shifts_m["доставок"] / shifts_m["часов"]
print("\nПо месяцам (только «Курьер»):")
print(shifts_m.round(2).to_string())

# ожидание курьера: заказы агрегаторов своими курьерами с отметками (до ~11.09)
w = load_vendor_orders()
w = w[w["completed"] & (w["delivery_type"] == "Доставка ресторана") & w["courier_wait_min"].notna()
      & (w["created"] >= FROM) & (w["created"] < TO)].copy()
w["couriers"] = headcount(s[s["position"] == "Курьер"], pd.DatetimeIndex(w["created"])).to_numpy()
w["deliv60"] = window_sum(deliveries, np.ones(len(deliveries)), w["created"], 60)
w["log_check"] = np.log(w["amount"])
hours = []
for h in range(11, 22):
    w[f"h{h}"] = (w["created"].dt.hour == h).astype(int)
    hours.append(f"h{h}")
g = w.groupby(w["couriers"].clip(upper=4))["courier_wait_min"]
print("\nОжидание курьера (мин) по числу курьеров на смене в момент заказа:")
print(pd.DataFrame({"n": g.size(), "median": g.median(), "p90": g.quantile(.9)}).round(1).to_string())
cols = ["couriers", "deliv60", "log_check"]
print(f"\nОжидание курьера ~ курьеров на смене + доставок за 60 мин + чек + час дня (n = {len(w)}):")
print(ols(w, "courier_wait_min", cols + hours).loc[cols].to_string())

# --- официанты ---
waiters = headcount(s[s["position"].isin(["Официант", "Помощник Официанта"])], grid)
occ, cap, _ = table_occupancy(hall_visits(FROM))
occ = occ[occ.index < TO]
both = pd.DataFrame({"waiters": waiters.reindex(occ.index), "tables": occ["total"]})
both["weekend"] = both.index.dayofweek >= 5
both = both[both["waiters"] > 0]
both["tables_per_waiter"] = both["tables"] / both["waiters"]
pw = both.groupby(["weekend", both.index.hour]).agg(waiters=("waiters", "mean"), tables=("tables", "mean"),
                                                     tables_per_waiter=("tables_per_waiter", "mean"))
print("\nОфицианты: на смене, занятых столов и столов на официанта (среднее по часам):")
print(pw.round(1).unstack(0).T.to_string())
