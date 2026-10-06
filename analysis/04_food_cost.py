"""Фудкост по каналам из StoreHouse: себестоимость по техкартам / продажа по ценам меню.

Оговорка: не проверено, одинаково ли учтён НДС в cost и price. Если price с НДС 22%, а cost без,
сопоставимый фудкост выше примерно в 1.22 раза.
"""
import pandas as pd

from common import load_sh_daily, pay_channel

pd.set_option("display.width", 200)

sh = load_sh_daily()
sale = sh[sh["category"] == "sale"].copy()
sale["channel"] = sale["paytype"].map(pay_channel)

recent = sale[sale["date"] >= "2026-04-01"]
by = recent.groupby(["channel", "store_type"])[["cost", "price"]].sum()
by["foodcost_%"] = (100 * by["cost"] / by["price"]).round(1)
print("Апрель–октябрь 2026, продажи: фудкост по каналу и складу")
print(by.round(0).to_string())

tot = recent.groupby("channel")[["cost", "price"]].sum()
tot["foodcost_%"] = (100 * tot["cost"] / tot["price"]).round(1)
tot["kitchen_share_%"] = (100 * recent[recent["store_type"] == "Кухня"].groupby("channel")["price"].sum()
                          / tot["price"]).round(1)
print("\nПо каналу всего:")
print(tot.round(0).to_string())

monthly = sale.groupby([sale["date"].dt.to_period("M"), "channel"])[["cost", "price"]].sum()
print("\nФудкост по месяцам, %:")
print((100 * monthly["cost"] / monthly["price"]).unstack().round(1).tail(10).to_string())
