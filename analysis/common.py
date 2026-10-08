"""Общие пути, загрузчики и статистические утилиты пилота.

Пилот: ресторан RIGA (Архангельское / Новая Рига, в Вендоре — «деревня Воронки, 1к4»).
Все файлы данных лежат в data/raw/ под именами из FILES (см. README).
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

FILES = {
    "vendor_orders": "vendor_orders.xlsx",       # Яндекс Еда Вендор → отчёт по заказам
    "promo_weekly": "vendor_promo_weekly.xlsx",  # Вендор → продвижение: витрина × неделя
    "rk_hourly": "fact_rk7_hourly.csv",          # витрина r_keeper: ресторан × день × час × канал
    "rk_payments": "fact_rk7_payments_daily.csv",  # витрина r_keeper: ресторан × день × вид оплаты
    "orders": "riga_orders.parquet",             # чеки RIGA с 2025 года (build_riga_pilot.py)
    "lines": "riga_lines.parquet",               # позиции чеков RIGA
    "dishes": "dim_dish.parquet",
    "sh_daily": "riga_sh_daily.parquet",         # StoreHouse: день × склад × вид оплаты
}

REST = "RIGA"


def path(key):
    p = RAW / FILES[key]
    if not p.exists():
        raise FileNotFoundError(f"нет файла {p}: положите выгрузку в data/raw (см. README)")
    return p


# ---------------------------------------------------------------- Вендор

VENDOR_COLUMNS = {
    "Сервис": "service",                          # Яндекс Еда / Деливери
    "Сумма заказа": "amount",
    "Статус": "status",
    "Тип доставки": "delivery_type",              # Доставка ресторана / Доставка сервиса / Самовывоз
    "Время создания заказа": "created",
    "Дата и время подтверждения заказа": "confirmed",
    "Заказ готов": "ready",
    "Заказ передан курьеру": "handed",
}


def load_vendor_orders():
    """Заказы агрегаторов. prep_min = готов − создан, courier_wait_min = передан курьеру − готов."""
    v = pd.read_excel(path("vendor_orders"), dtype=str).fillna("")
    v = v.drop_duplicates("Номер заказа").rename(columns=VENDOR_COLUMNS)
    for c in ["created", "confirmed", "ready", "handed"]:
        v[c] = pd.to_datetime(v[c].replace("", None), errors="coerce")
    v["amount"] = pd.to_numeric(v["amount"])
    v["completed"] = v["status"] == "Завершен"
    v["prep_min"] = (v["ready"] - v["created"]).dt.total_seconds() / 60
    v["courier_wait_min"] = (v["handed"] - v["ready"]).dt.total_seconds() / 60
    return v


PROMO_COLUMNS = {
    "Показы": "impressions", "Клики": "clicks", "Заказы": "orders",
    "Выручка от продвижения": "revenue", "Затраты на продвижение": "cost", "Потрачено бонусов": "bonus",
}


def load_promo_weekly():
    """Недельный отчёт продвижения по 4 витринам (Еда / Деливери × своя доставка / курьеры сервиса).

    «Заказы» — то, что Яндекс приписывает продвижению, включая повторные заказы без клика.
    """
    r = pd.read_excel(path("promo_weekly"))
    r = r[r["Ресторан"] != "Итого"].rename(columns=PROMO_COLUMNS)
    r["week"] = pd.to_datetime(r["Период"].str[:10])
    return r


# ---------------------------------------------------------------- r_keeper

def _read_mart_csv(key):
    df = pd.read_csv(path(key), sep=";", decimal=",", encoding="utf-8-sig")
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_rk_hourly():
    return _read_mart_csv("rk_hourly")


def load_rk_payments():
    return _read_mart_csv("rk_payments")


def load_orders():
    return pd.read_parquet(path("orders"))


def load_lines():
    return pd.read_parquet(path("lines"))


def load_dishes():
    return pd.read_parquet(path("dishes"))


def load_sh_daily():
    return pd.read_parquet(path("sh_daily"))


def pay_channel(pay_type):
    """Канал продаж по виду оплаты r_keeper / StoreHouse."""
    p = str(pay_type)
    if "Яндекс" in p:
        return "Яндекс Еда"
    if "Деливери" in p or "Delivery" in p:
        return "Деливери"
    if "Доставка" in p or "(соб.)" in p:
        return "своя доставка"
    return "зал"


BAR_PATTERN = (r"НАПИТ|БАР|АЛКО|ВИН|КОФЕ|ЧАЙ|МОЛОК|ПИВ|КОКТ|ЛИМОНАД|СОК|ВОДА|Б/А|ВИСКИ|КОНЬЯК|ВОДК"
               r"|ИГРИСТ|ШАМПАН")


NOT_KITCHEN = {"бар", "бар зал", "лавка"}  # бар и розничная лавка не грузят поваров


def stations(cook_place):
    """Цеха из места приготовления кассы: «Горячий + мангал» → ['горячий', 'мангал']."""
    if not isinstance(cook_place, str) or not cook_place.strip():
        return []
    return [s.strip().lower() for s in cook_place.split("+")]


def kitchen_lines(since="2026-05-01"):
    """Позиции-блюда кухни (без бара, лавки, добавок и служебных) с каналом чека и цехами.

    Цех берётся из места приготовления (cook_place, текущая настройка кассы); у блюд без него —
    по названию категории. units — количество, обрезанное до 10: платная доставка и весовой
    товар вбиваются количеством, которое не отражает работу повара.
    """
    d = load_dishes()
    d["stations"] = d["cook_place"].map(stations) if "cook_place" in d else [[] for _ in range(len(d))]
    text = d["category_parent"].fillna("") + " " + d["category"].fillna("")
    by_name = np.where(text.str.contains(BAR_PATTERN, case=False, regex=True), "бар", "кухня")
    d["stations"] = [st if st else [fallback] for st, fallback in zip(d["stations"], by_name)]
    d["stations"] = d["stations"].map(lambda st: [s for s in st if s not in NOT_KITCHEN])
    d = d[d["stations"].map(len) > 0]
    o = load_orders()[["order_id", "channel"]]
    x = load_lines().merge(d[["dish_id", "item_type", "stations"]], on="dish_id", how="inner")
    x = x[(x["item_type"] == "Блюдо") & (x["qty"] > 0) & (x["add_time"] >= since)]
    x = x.merge(o, on="order_id", how="left")
    x["units"] = x["qty"].clip(upper=10)
    return x


def station_lines(since="2026-05-01"):
    """То же по цехам: блюдо из нескольких цехов засчитывается каждому из них."""
    return kitchen_lines(since).explode("stations").rename(columns={"stations": "station"})


HALLS = ["Зал 1эт", "Зал 2эт", "Веранда1", "Веранда2"]


def hall_visits(since="2026-05-01"):
    """Визиты зала со столом. 10 минут – 6 часов: короче — навынос, длиннее — забытые открытые чеки.

    table — физический стол: «28,1» — дополнительный чек стола 28.
    """
    o = load_orders()
    h = o[(o["is_visit"] == 1) & o["hall"].isin(HALLS) & (o["date"] >= since)
          & o["duration_min"].between(10, 360) & o["table_name"].notna()].copy()
    h["table"] = h["hall"] + " / " + h["table_name"].str.split(",").str[0].str.strip()
    return h


def table_occupancy(h, freq="15min"):
    """Занятые и работающие столы по залам на сетке 10:00–22:45.

    Стол занят, пока на нём открыт хотя бы один чек. Работающие столы зала — сколько разных столов
    было в чеках в этом месяце; веранды считаются только в дни, когда на них были гости.
    Возвращает (occ, cap, capacity_month), у occ и cap есть колонка total.
    """
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

    first = h["open_time"].min().normalize()
    grid = pd.date_range(first + pd.Timedelta("09:00:00"), h["close_time"].max().floor("D") + pd.Timedelta("23:45:00"),
                         freq=freq)
    grid = grid[(grid.hour >= 10) & (grid.hour <= 22)]
    occ = pd.DataFrame(index=grid)
    for hall, g in busy.groupby("hall"):
        s, e = np.sort(g["start"].values), np.sort(g["end"].values)
        occ[hall] = np.searchsorted(s, grid.values, side="right") - np.searchsorted(e, grid.values, side="right")

    capacity_month = h.groupby([h["date"].dt.to_period("M"), "hall"])["table"].nunique().unstack()
    open_days = h.groupby([h["date"], "hall"]).size().unstack().notna()
    cap = pd.DataFrame(index=grid, columns=HALLS, dtype=float)
    for hall in HALLS:
        per_month = capacity_month[hall].reindex(grid.to_period("M")).to_numpy()
        is_open = open_days[hall].reindex(grid.normalize(), fill_value=False).to_numpy()
        cap[hall] = np.where(is_open, per_month, 0)
    occ = occ.reindex(columns=HALLS, fill_value=0)
    occ["total"], cap["total"] = occ[HALLS].sum(axis=1), cap[HALLS].sum(axis=1)
    return occ, cap, capacity_month


# ---------------------------------------------------------------- статистика

def window_sum(times, values, at, minutes):
    """Сумма values с times в окне (at − minutes, at] для каждого момента at."""
    times = np.asarray(times, dtype="datetime64[ns]")
    at = np.asarray(at, dtype="datetime64[ns]")
    order = np.argsort(times)
    ts = times[order]
    cs = np.concatenate([[0.0], np.cumsum(np.asarray(values, dtype=float)[order])])
    hi = np.searchsorted(ts, at, side="right")
    lo = np.searchsorted(ts, at - np.timedelta64(minutes, "m"), side="left")
    return cs[hi] - cs[lo]


def ols(df, y, cols):
    """МНК с робастными ошибками HC1. Возвращает таблицу coef / se / t."""
    m = df[[y] + cols].notna().all(axis=1)
    X = np.column_stack([np.ones(m.sum())] + [df.loc[m, c].to_numpy(float) for c in cols])
    Y = df.loc[m, y].to_numpy(float)
    b = np.linalg.lstsq(X, Y, rcond=None)[0]
    e = Y - X @ b
    xtx_inv = np.linalg.inv(X.T @ X)
    meat = (X * e[:, None]).T @ (X * e[:, None])
    n, k = X.shape
    se = np.sqrt(np.diag(xtx_inv @ meat @ xtx_inv) * n / (n - k))
    return pd.DataFrame({"coef": b, "se": se, "t": b / se}, index=["const"] + cols).round(3)


def days_per_arm(residual_var, effect, z_alpha=1.96, z_beta=0.84):
    """Дней на группу для двухвыборочного сравнения средних дневных заказов."""
    return 2 * (z_alpha + z_beta) ** 2 * residual_var / effect ** 2
