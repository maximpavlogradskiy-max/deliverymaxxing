"""Профиль загрузки ресторана по получасам: будни и выходные отдельно.

1. Заказы за полчаса (в среднем за день) по каналам: зал (визиты со столом), агрегаторы (выполненные
   заказы Вендора по времени создания), своя доставка (чеки r_keeper).
2. Посадка зала: доля занятых столов от работающих (06_hall_occupancy), среднее и 10–90-й процентили
   по 15-минутным отсчётам внутри получаса.

    from load_profile import half_hour_profile, hourly_by_restaurant
    p = half_hour_profile()          # Архангельское: индекс (weekend, slot)
    r = hourly_by_restaurant()       # все рестораны: rest, weekend, hour, checks

Для всех ресторанов есть только витрина r_keeper по часам: оплаченные чеки (зал, навынос и доставка
вместе — поле канала в витрине сломано) по часу открытия чека. Посадку зала по столам можно посчитать
только там, где есть выгрузка чеков со столами (сейчас — Архангельское).

    python analysis/load_profile.py [out.csv]
"""
import sys

import pandas as pd

from common import hall_visits, load_orders, load_rk_hourly, load_vendor_orders, pay_channel, table_occupancy

CHANNELS = ["зал", "агрегаторы", "своя доставка"]


def half_hour_profile(since="2026-05-01", until="2026-10-01", first="10:00", last="22:30"):
    def slots(times):
        t = pd.Series(pd.DatetimeIndex(times))
        t = t[(t >= since) & (t < until)]
        return pd.DataFrame({"weekend": t.dt.dayofweek >= 5, "slot": t.dt.floor("30min").dt.strftime("%H:%M")})

    h = hall_visits(since)
    v = load_vendor_orders()
    o = load_orders()
    own = o[(o["is_visit"] == 1) & (o["pay_type"].map(pay_channel) == "своя доставка")]
    times = {"зал": h["open_time"], "агрегаторы": v.loc[v["completed"], "created"], "своя доставка": own["open_time"]}

    days = pd.Series(pd.date_range(since, until, inclusive="left"))
    n_days = days.groupby(days.dt.dayofweek >= 5).size()
    orders = []
    for name in CHANNELS:
        s = slots(times[name]).value_counts().rename("orders").reset_index()
        s["channel"] = name
        orders.append(s)
    orders = pd.concat(orders)
    orders["per_day"] = orders["orders"] / orders["weekend"].map(n_days)
    orders = orders[(orders["slot"] >= first) & (orders["slot"] <= last)]
    table = orders.pivot_table(index=["weekend", "slot"], columns="channel", values="per_day", fill_value=0)[CHANNELS]
    table["всего"] = table.sum(axis=1)

    occ, cap, _ = table_occupancy(h)
    occ, cap = occ[occ.index < until], cap[cap.index < until]
    pct = (occ["total"] / cap["total"]).dropna() * 100
    key = [pct.index.dayofweek >= 5, pct.index.floor("30min").strftime("%H:%M")]
    seat = pct.groupby(key).agg(mean="mean", p10=lambda x: x.quantile(.1), p90=lambda x: x.quantile(.9))
    seat.index = seat.index.set_names(["weekend", "slot"])
    seat.columns = ["посадка, %", "p10, %", "p90, %"]
    return table.join(seat, how="outer")


def hourly_by_restaurant(since="2026-05-01", until="2026-10-01", first=9, last=23):
    """Оплаченных чеков в час (в среднем за день) по ресторанам, будни и выходные отдельно.

    Дни считаются от первого дня с чеками в ресторане (PERM открылся 10.06.2026).
    """
    h = load_rk_hourly()
    h["date"] = pd.to_datetime(h["date"])
    h = h[(h["date"] >= since) & (h["date"] < until)]
    h["weekend"] = h["date"].dt.dayofweek >= 5
    first_day = h.groupby("rest")["date"].min()
    days = pd.DataFrame([(rest, d) for rest, start in first_day.items()
                         for d in pd.date_range(start, until, inclusive="left")], columns=["rest", "date"])
    n_days = days.groupby(["rest", days["date"].dt.dayofweek >= 5]).size()
    out = h.groupby(["rest", "weekend", "hour"])["paid_orders"].sum().rename("checks").reset_index()
    out["checks"] = out["checks"] / pd.MultiIndex.from_frame(out[["rest", "weekend"]]).map(n_days)
    out = out[out["hour"].between(first, last)]
    grid = pd.MultiIndex.from_product([first_day.index, [False, True], range(first, last + 1)], names=["rest", "weekend", "hour"])
    return out.set_index(["rest", "weekend", "hour"])["checks"].reindex(grid, fill_value=0).reset_index()


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    out = half_hour_profile().round(2)
    for weekend, name in [(False, "Будни"), (True, "Выходные")]:
        print(f"\n{name}: заказов за полчаса (в среднем за день) и посадка зала")
        print(out.loc[weekend].to_string())
    if len(sys.argv) > 1:
        out.reset_index().assign(weekend=lambda d: d["weekend"].map({False: "будни", True: "выходные"})).to_csv(sys.argv[1], index=False)
