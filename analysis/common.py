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


def kitchen_lines(since="2026-05-01"):
    """Позиции-блюда кухни (без бара, добавок и служебных) с каналом чека.

    units — количество, обрезанное до 10: платная доставка и весовой товар вбиваются
    количеством, которое не отражает работу повара.
    """
    d = load_dishes()
    text = d["category_parent"].fillna("") + " " + d["category"].fillna("")
    d["station"] = np.where(text.str.contains(BAR_PATTERN, case=False, regex=True), "bar", "kitchen")
    o = load_orders()[["order_id", "channel"]]
    x = load_lines().merge(d[["dish_id", "item_type", "station"]], on="dish_id", how="left")
    x = x[(x["item_type"] == "Блюдо") & (x["station"] == "kitchen") & (x["qty"] > 0)
          & (x["add_time"] >= since)]
    x = x.merge(o, on="order_id", how="left")
    x["units"] = x["qty"].clip(upper=10)
    return x


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
