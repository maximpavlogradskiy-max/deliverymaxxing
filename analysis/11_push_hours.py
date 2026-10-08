"""В какие часы есть свободная мощность для дополнительных заказов доставки, май–август 2026.

По часам будней и выходных: заказы агрегаторов и своей доставки (среднее за день), загрузка цехов
(блюд в час / (поваров на смене × мощность повара из 09_kitchen_staffing.py)) — средняя и в 90-й
процентиль 15-минуток часа, доставок на курьера на смене. «Запас» — средняя загрузка всех цехов
ниже 50% и меньше одной доставки на курьера в час: туда дополнительный заказ почти ничего не стоит,
кроме себестоимости и комиссии. Порог условный; время на одну доставку неизвестно, поэтому
«одна доставка на курьера в час» — грубая граница насыщения курьеров.

Вторая часть — сколько дополнительных заказов должна дать скидка, действующая только в выбранные
часы: она достаётся и заказам, которые пришли бы без неё.
"""
import numpy as np
import pandas as pd

from biotime import headcount, load_shifts
from common import days_per_arm, load_orders, load_vendor_orders, pay_channel, station_lines

pd.set_option("display.width", 240)

FROM, TO = "2026-05-01", "2026-09-01"
HOURS = range(10, 23)
CAPACITY = {"горячий": 38, "холодный": 20, "пицца": 24}       # блюд в час на повара, 09_kitchen_staffing.py
COOKS = {"горячий": ["Повар ГЦ", "Бригадир ГЦ", "Су-Шеф ГЦ", "Повар-Мангал"],
         "холодный": ["Повар ХЦ", "Бригадир ХЦ"],
         "пицца": ["Пиццейло"]}
DISHES = {"горячий": ["горячий", "паста", "мангал"], "холодный": ["холодный"], "пицца": ["пицца"]}
CHECK, MARGIN = 3566, 0.5            # средний чек агрегатора, ₽; доля маржи заказа после комиссии и себестоимости (02)

s = load_shifts()
s = s[(s["date"] >= FROM) & (s["date"] < TO)]
grid = pd.date_range(FROM, TO, freq="15min", inclusive="left")
grid = grid[(grid.hour >= min(HOURS)) & (grid.hour <= max(HOURS))]
key = [grid.dayofweek >= 5, grid.hour]
days = pd.Series(grid.normalize()).groupby(grid.dayofweek >= 5).nunique()


def per_day(times):
    """Среднее число событий в час дня по будням и выходным."""
    times = pd.Series(times)
    times = times[(times >= FROM) & (times < TO) & times.dt.hour.isin(HOURS)]
    n = times.groupby([times.dt.dayofweek >= 5, times.dt.hour]).size()
    return n / n.index.get_level_values(0).map(days).to_numpy()


v = load_vendor_orders()
v = v[v["completed"]]
o = load_orders()
own = o[(o["is_visit"] == 1) & (o["pay_type"].map(pay_channel) == "своя доставка")]
t = pd.DataFrame({
    "агрегаторы": per_day(v["created"]),
    "из них свои курьеры": per_day(v.loc[v["delivery_type"] == "Доставка ресторана", "created"]),
    "своя доставка": per_day(own["open_time"]),
})

st = station_lines(since=FROM)
st = st[st["add_time"] < TO]
for station in COOKS:
    cooks = headcount(s[s["position"].isin(COOKS[station])], grid)
    dishes = st[st["station"].isin(DISHES[station])].set_index("add_time")["units"].resample("15min").sum()
    load = dishes.reindex(grid, fill_value=0) * 4 / (cooks.replace(0, np.nan) * CAPACITY[station])
    t[f"{station} ср"] = load.groupby(key).mean()
    t[f"{station} p90"] = load.groupby(key).quantile(.9)

couriers = headcount(s[s["position"] == "Курьер"], grid).groupby(key).mean()
t["курьеров"] = couriers
t["доставок на курьера"] = (t["из них свои курьеры"] + t["своя доставка"]) / couriers.replace(0, np.nan)
loads = [c for c in t.columns if c.endswith(" ср")]
t["запас"] = np.where((t[loads].max(axis=1) < .5) & (t["доставок на курьера"] < 1), "да", "")
t.index = t.index.set_names(["выходной", "час"])

for weekend, name in [(False, "Будни"), (True, "Выходные")]:
    x = t.loc[weekend].copy()
    for c in [c for c in x.columns if c.endswith((" ср", " p90"))]:
        x[c] = (x[c] * 100).round(0).map(lambda p: "" if np.isnan(p) else f"{p:.0f}%")
    print(f"\n{name}: заказов в час (среднее за день), загрузка цехов, доставок на курьера")
    print(x.round(2).T.to_string())

print(f"\nСкидка d только в часы окна. Пусть N0 — заказов в окне без скидки, ΔN — дополнительных.\n"
      f"Скидка достаётся всем N0 + ΔN заказам, поэтому окупается при ΔN / N0 ≥ d / (r − d), r = {MARGIN:.0%} — маржа заказа:")
for d in [.10, .15, .20]:
    print(f"  скидка {d:.0%}: нужен прирост заказов в окне ≥ {d / (MARGIN - d):.0%}")
print("Если часть ΔN — заказы, перенесённые из других часов, их маржа уже была бы получена: окупаемость ещё хуже.")

# мощность почасового теста: заказы агрегаторов и своей доставки в окне будних 14–17, разброс между днями после поправки
# на день недели и месяц; сколько будних дней на группу нужно, чтобы заметить прирост
WINDOW = range(14, 18)
orders = pd.concat([v["created"], own["open_time"]])
orders = orders[(orders >= FROM) & (orders < TO) & orders.dt.hour.isin(WINDOW) & (orders.dt.dayofweek < 5)]
n = orders.dt.normalize().value_counts()
n = n.reindex(pd.bdate_range(FROM, TO, inclusive="left"), fill_value=0)
resid = n - n.groupby([n.index.dayofweek, n.index.month]).transform("mean")
var = resid.var() * len(n) / (len(n) - 20)              # 20 средних групп
print(f"\nПочасовой тест в окне будних 14–17: {n.mean():.1f} заказа (агрегаторы + своя доставка) за окно, дисперсия остатков {var:.1f} "
      f"(пуассоновская была бы {n.mean():.1f}). Будних дней на группу, чтобы заметить прирост:")
for lift in [.2, .3, .5]:
    print(f"  +{lift:.0%} (+{lift * n.mean():.1f} заказа за окно): {days_per_arm(var, lift * n.mean()):.0f}")
