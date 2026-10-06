"""Промо в Яндекс Еде: атрибуция Яндекса, точка безубыточности, естественный эксперимент, мощность теста.

Цифры продвижения взяты со страницы «Статистика» Вендора за 29.09–05.10.2026
(понедельник 05.10 в статистике продвижения ещё не появился).
"""
import pandas as pd

from common import REST, days_per_arm, load_rk_payments, load_vendor_orders

pd.set_option("display.width", 200)

# --- атрибуция Яндекса за неделю 29.09–04.10 ---
COST = 33_450
NEW, NEW_REV = 32, 103_689                  # новые пользователи по клику продвижения
REPEAT_CLICK, REPEAT_CLICK_REV = 27, 106_717  # повторные по клику продвижения
REPEAT_FREE, REPEAT_FREE_REV = 31, 120_161    # повторные без продвижения (засчитаны Яндексом)
BID_RANGE = (530, 610)                       # ставки оплаты за заказ, страница «Продвижение»

v = load_vendor_orders()
done = v[v["completed"]]
week = done[(done["created"] >= "2026-09-29") & (done["created"] < "2026-10-05")]
ye = week[week["service"] == "Яндекс Еда"]
attributed = NEW + REPEAT_CLICK + REPEAT_FREE
paid = NEW + REPEAT_CLICK
print(f"Неделя 29.09–04.10: заказов Яндекс Еды {len(ye)}, всех агрегаторов {len(week)}; "
      f"Яндекс приписывает промо {attributed} ({attributed / len(ye):.0%} заказов Еды)")
print(f"Цена за оплаченный заказ: {COST} / {paid} = {COST / paid:.0f}₽ (ставки {BID_RANGE[0]}–{BID_RANGE[1]}₽)")
print(f"«Средняя стоимость» Яндекса: {COST / attributed:.0f}₽, ДРР {COST / (NEW_REV + REPEAT_CLICK_REV + REPEAT_FREE_REV):.1%}")
print(f"Пессимистично (дополнительны только новые): {COST / NEW:.0f}₽ за заказ, ДРР {COST / NEW_REV:.1%}")

# --- безубыточность: q · r · чек ≥ ставка ---
check = (NEW_REV + REPEAT_CLICK_REV) / paid
cpo = COST / paid
print(f"\nСредний чек оплаченного промо-заказа {check:.0f}₽. Нужная доля дополнительных заказов q* = "
      f"{cpo / check:.3f} / r:")
for r in (0.25, 0.30, 0.35, 0.40, 0.45):
    print(f"   r = {r:.0%}:  q* = {cpo / (r * check):.2f}")
print(f"Доля новых среди оплаченных: {NEW / paid:.0%} → при q = {NEW / paid:.2f} нужна r ≥ {cpo / (NEW / paid * check):.0%}")

# --- естественный эксперимент: ставки снижены 31.08–13.09 ---
ye_all = done[done["service"] == "Яндекс Еда"]
periods = {
    "17–30.08 (до)": ("2026-08-17", "2026-08-31"),
    "31.08–13.09 (промо урезано)": ("2026-08-31", "2026-09-14"),
    "14.09–04.10 (после)": ("2026-09-14", "2026-10-05"),
}
print("\nЗаказов Яндекс Еды в день:")
for name, (a, b) in periods.items():
    n = ((ye_all["created"] >= a) & (ye_all["created"] < b)).sum()
    print(f"   {name:30s} {n / (pd.Timestamp(b) - pd.Timestamp(a)).days:5.1f}")
weekly = ye_all.groupby(ye_all["created"].dt.to_period("W")).size()
print("По неделям (сезонный спад начался раньше урезания):",
      {str(w.start_time.date()): n for w, n in weekly.loc["2026-07-27":"2026-10-04"].items()})

# --- те же календарные окна в прошлые годы (заказы Яндекса по оплатам r_keeper) ---
pay = load_rk_payments()
pay = pay[(pay["rest"] == REST) & (pay["category"] == "sale") & pay["currency"].str.contains("Яндекс")]
ya_rk = pay.groupby("date")["checks"].sum()
ya_rk = ya_rk.reindex(pd.date_range(ya_rk.index.min(), ya_rk.index.max()), fill_value=0)
print("\nЗаказов Яндекса в день по r_keeper в те же окна (провал = «во время» к среднему соседних окон):")
for y in (2024, 2025, 2026):
    before, during, after = (ya_rk[f"{y}-08-17":f"{y}-08-30"].mean(), ya_rk[f"{y}-08-31":f"{y}-09-13"].mean(),
                             ya_rk[f"{y}-09-14":f"{y}-10-04"].mean())
    dip = during / ((14 * before + 21 * after) / 35) - 1
    print(f"   {y}: до {before:5.1f}  во время {during:5.1f}  после {after:5.1f}  провал {dip:+.0%}")

# --- мощность эксперимента с чередованием по дням ---
daily = done[done["created"] < "2026-10-05"].groupby(done["created"].dt.normalize()).size()
daily = daily[daily.index >= "2026-08-01"]
resid_var = (daily - daily.groupby(daily.index.dayofweek).transform("mean")).var()
print(f"\nОстаточная дисперсия дневных заказов после дня недели: {resid_var:.1f}")
for effect in (3, 5, 10, 15):
    print(f"   эффект {effect:2d} заказов/день → {days_per_arm(resid_var, effect):5.1f} дней на группу")
