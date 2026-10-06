"""Реклама сайта в Директе → своя доставка RIGA. Наблюдательная оценка, не эксперимент.

Расход — data/raw/direct_daily_e-17392980.csv (python analysis/yandex_api.py daily e-17392980 2023-12-01).
Заказы своей доставки — чеки RIGA с видами оплаты «Доставка …» кроме агрегаторов (витрина оплат r_keeper).
Контроли: заказы Яндекс Еды (общий спрос на доставку), день недели, месяц.
"""
import pandas as pd

from common import RAW, load_rk_payments, ols

pd.set_option("display.width", 200)

p = load_rk_payments()
p = p[(p["rest"] == "RIGA") & (p["category"] == "sale")]
aggregator = p["currency"].str.contains("Яндекс|Деливери|Delivery", regex=True)
own = p[p["currency"].str.contains("Доставка") & ~aggregator].groupby("date")["checks"].sum()
ya = p[p["currency"].str.contains("Яндекс")].groupby("date")["checks"].sum()

d = pd.read_csv(RAW / "direct_daily_e-17392980.csv", parse_dates=["Date"])
# кампании доставки, ведущие на сайт; «Доставка Яндекс» вела в Яндекс Еду
site = d["CampaignName"].str.contains("Доставка") & ~d["CampaignName"].str.contains("Яндекс")
spend = pd.DataFrame({"site_spend": d[site].groupby("Date")["Cost"].sum(),
                      "other_spend": d[~site].groupby("Date")["Cost"].sum()})

days = pd.date_range("2024-01-01", min(own.index.max(), spend.index.max()))
x = pd.DataFrame({"own": own, "ya": ya}).reindex(days).fillna(0).join(spend.reindex(days).fillna(0))
x["site_k7"] = x["site_spend"].rolling(7, min_periods=1).mean() / 1000
x["other_k"] = x["other_spend"] / 1000

print("По кварталам, в день: заказы своей доставки, заказы Яндекс Еды, расход на рекламу сайта и прочую, ₽")
print(x.groupby(x.index.to_period("Q"))[["own", "ya", "site_spend", "other_spend"]].mean().round(1).to_string())

fe = []
for k in range(1, 7):
    x[f"dow{k}"] = (x.index.dayofweek == k).astype(int)
    fe.append(f"dow{k}")
for m in pd.period_range(days[0].to_period("M") + 1, days[-1].to_period("M"), freq="M"):
    x[f"m{m}"] = (x.index.to_period("M") == m).astype(int)
    fe.append(f"m{m}")

cols = ["site_k7", "other_k", "ya"]
r = ols(x, "own", cols + fe).loc[cols]
print("\nЗаказы своей доставки в день ~ расход на рекламу сайта (тыс.₽/день, среднее за 7 дней)"
      " + прочая реклама + заказы Еды + день недели + месяц:")
print(r.to_string())
b, se = r.loc["site_k7", "coef"], r.loc["site_k7", "se"]
hi = b + 1.96 * se
print(f"95% интервал: {b - 1.96 * se:.2f} … {hi:.2f} заказа на 1 000₽/день → "
      f"даже на верхней границе {1000 / hi:.0f}₽ за дополнительный заказ" if hi > 0 else "")
print("Отрицательный значимый коэффициент у прочей рекламы — признак смешения факторов:"
      " бюджеты ставили не случайно, поэтому оценка предварительная.")
