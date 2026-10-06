"""Расписание эксперимента со ставками продвижения: случайные дни «выкл» и «вкл».

Каждый день недели получает поровну дней «выкл» и «вкл» за весь эксперимент,
в каждой неделе 3–4 дня «выкл». Так день недели и сезон не смешиваются с эффектом.

    python analysis/experiment_schedule.py 2026-10-12 6     # старт (понедельник) и число недель
"""
import sys

import numpy as np
import pandas as pd

from common import days_per_arm

start = pd.Timestamp(sys.argv[1] if len(sys.argv) > 1 else "2026-10-12")
weeks = int(sys.argv[2]) if len(sys.argv) > 2 else 6
assert start.dayofweek == 0, "старт — понедельник"
rng = np.random.default_rng(20261012)

while True:  # случайный план с ровно weeks/2 «выкл» на каждый день недели
    plan = np.zeros((weeks, 7), dtype=int)
    for dow in range(7):
        plan[rng.choice(weeks, weeks // 2, replace=False), dow] = 1
    if set(plan.sum(axis=1)) <= {3, 4}:
        break

days = pd.date_range(start, periods=weeks * 7)
names = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
print("| Неделя | " + " | ".join(names) + " |")
print("|---|" + "---|" * 7)
for w in range(weeks):
    cells = [f"{days[w * 7 + d]:%d.%m} {'**выкл**' if plan[w, d] else 'вкл'}" for d in range(7)]
    print(f"| {w + 1} | " + " | ".join(cells) + " |")

n = weeks * 7 // 2
mde = (days_per_arm(25, 1) / n) ** 0.5  # days_per_arm ∝ 1/δ², σ² = 25 — остаточная дисперсия заказов в день
print(f"\nДней на группу: {n}. Минимальный различимый эффект (мощность 80%, α = 5%): {mde:.1f} заказа в день")
