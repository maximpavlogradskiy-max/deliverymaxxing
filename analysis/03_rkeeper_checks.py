"""Сверка Вендора с r_keeper и проверка разметки каналов.

1. Какой ресторан r_keeper соответствует точке Вендора (корреляция дневной выручки агрегаторов).
2. Поле channel в fact_rk7_hourly: доля «Доставки» по кварталам.
3. Структура заказов RIGA по виду оплаты (чеки из riga_orders).
"""
import numpy as np
import pandas as pd

from common import REST, load_orders, load_rk_hourly, load_rk_payments, load_vendor_orders, pay_channel

pd.set_option("display.width", 220)

v = load_vendor_orders()
v = v[v["completed"] & (v["created"] < v["created"].dt.normalize().max())]
vd = v.groupby(v["created"].dt.normalize())["amount"].sum()

pay = load_rk_payments()
agg = pay[(pay["category"] == "sale") & pay["currency"].str.contains("Яндекс|Деливери|Delivery", regex=True)]
rows = []
for rest, g in agg.groupby("rest"):
    s = g.groupby("date")["amount"].sum().reindex(vd.index, fill_value=0)
    rows.append({"rest": rest, "corr": np.corrcoef(s, vd)[0, 1] if s.std() > 0 else np.nan,
                 "rk / vendor": s.sum() / vd.sum()})
print("Дневная выручка агрегаторов r_keeper vs Вендор:")
print(pd.DataFrame(rows).sort_values("corr", ascending=False).round(3).to_string(index=False))

h = load_rk_hourly()
q = h["date"].dt.to_period("Q")
total = h.groupby(["rest", q])["orders"].sum()
share = h[h["channel"] == "Доставка"].groupby(["rest", q])["orders"].sum().reindex(total.index, fill_value=0) / total
print("\nfact_rk7_hourly: доля «Доставки» в заказах по кварталам (0 и 1 = поле канала сломано):")
print(share.unstack().round(2).iloc[:, -6:].to_string())

o = load_orders()
vis = o[(o["is_visit"] == 1) & (o["date"] >= "2026-05-01")].copy()
vis["pay_channel"] = vis["pay_type"].map(pay_channel)
days = vis["date"].nunique()
mix = vis.groupby("pay_channel").agg(per_day=("order_id", "size"), paid=("paid_sale", "sum"))
mix["per_day"] = (mix["per_day"] / days).round(1)
mix["paid"] = mix["paid"].round(0).astype(int)
mix["share_%"] = (100 * mix["per_day"] / mix["per_day"].sum()).round(1)
print(f"\n{REST} с 01.05.2026: визиты по каналу (по виду оплаты), в день:")
print(mix.to_string())
print("Совпадение channel чека с каналом по оплате:",
      f"{((vis['channel'] == 'Доставка') == (vis['pay_channel'] != 'зал')).mean():.1%}")
