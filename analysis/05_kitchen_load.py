"""Нагрузка кухни и время доставки.

Нагрузка — блюда кухни (без бара), добавленные в чеки r_keeper, по каналам.
Время — отметки Вендора по заказам агрегаторов, которые везут свои курьеры
(«Заказ готов» есть только до ~11.09.2026).
"""
import numpy as np
import pandas as pd

from common import kitchen_lines, load_vendor_orders, ols, station_lines, window_sum

pd.set_option("display.width", 220)

k = kitchen_lines(since="2026-05-01")
days = k["add_time"].dt.normalize().nunique()
prof = k.pivot_table(index=k["add_time"].dt.hour, columns="channel", values="units", aggfunc="sum").fillna(0) / days
prof["delivery_share_%"] = (100 * prof["Доставка"] / prof.sum(axis=1)).round(0)
print(f"Блюд кухни в час (среднее за {days} дней с 01.05.2026):")
print(prof.round(1).T.to_string())
units = k.groupby("channel")["units"].sum()
print(f"Доля доставки в нагрузке кухни: {units['Доставка'] / units.sum():.1%}")

v = load_vendor_orders()
o = v[v["completed"] & (v["delivery_type"] == "Доставка ресторана") & v["prep_min"].notna()].copy()
for channel, col in [("Зал и навынос", "hall30"), ("Доставка", "deliv30")]:
    s = k[k["channel"] == channel]
    o[col] = window_sum(s["add_time"], s["units"], o["created"], 30)
o["log_check"] = np.log(o["amount"])
hours = []
for h in range(11, 22):
    o[f"h{h}"] = (o["created"].dt.hour == h).astype(int)
    hours.append(f"h{h}")

o["hall_bin"] = pd.cut(o["hall30"], [-1, 10, 20, 30, 40, 60, 500])
g = o.groupby("hall_bin", observed=True)
print("\nЗаказы агрегаторов своими курьерами: время vs блюда зала за 30 минут до заказа")
print(pd.DataFrame({"n": g.size(), "prep_med": g["prep_min"].median(), "prep_p90": g["prep_min"].quantile(.9),
                    "courier_wait_med": g["courier_wait_min"].median()}).round(1).to_string())

base = ["hall30", "deliv30", "log_check"]
print(f"\nВремя готовки ~ нагрузка + чек + час дня (n = {len(o)}):")
print(ols(o, "prep_min", base + hours).loc[base].to_string())
print("\nОжидание курьера ~ нагрузка + чек + час дня:")
print(ols(o, "courier_wait_min", base + hours).loc[base].to_string())

# --- по цехам (место приготовления из кассы) ---
st = station_lines(since="2026-05-01")
hour = st["add_time"].dt.hour
by = st.pivot_table(index="station", columns="channel", values="units", aggfunc="sum").fillna(0) / days
by["delivery_share_%"] = (100 * by["Доставка"] / by.sum(axis=1)).round(0)
peak = st.pivot_table(index="station", columns=hour, values="units", aggfunc="sum").fillna(0) / days
by["peak_hour"] = peak.idxmax(axis=1)
by["peak_per_hour"] = peak.max(axis=1).round(1)
q15 = st.set_index("add_time").groupby("station")["units"].resample("15min").sum()
by["p95_per_15min"] = q15.groupby(level=0).quantile(.95)
print("\nПо цехам: блюд в день по каналам, доля доставки, пиковый час и блюд в пиковый час, p95 за 15 минут:")
print(by.sort_values("Зал и навынос", ascending=False).round(1).to_string())

for name in ["горячий", "холодный", "пицца", "паста", "мангал"]:
    s30 = st[st["station"] == name]
    o[name] = window_sum(s30["add_time"], s30["units"], o["created"], 30)
cols = ["горячий", "холодный", "пицца", "паста", "мангал", "log_check"]
print(f"\nВремя готовки ~ блюда каждого цеха за 30 минут + чек + час дня (n = {len(o)}):")
print(ols(o, "prep_min", cols + hours).loc[cols].to_string())
