"""Заказы агрегаторов из Вендора: спрос, дисперсия, каналы доставки, качество отметок времени."""
import pandas as pd

from common import load_vendor_orders

pd.set_option("display.width", 200)

v = load_vendor_orders()
done = v[v["completed"]]
print(f"Период {v['created'].min():%d.%m.%Y} – {v['created'].max():%d.%m.%Y}, заказов {len(v)}, "
      f"отмен {(v['status'] == 'Отменён').mean():.1%}")

print("\nЗавершённые заказы по сервису и типу доставки:")
print(done.groupby(["service", "delivery_type"])["amount"].agg(["count", "mean", "median"]).round(0).to_string())

# Последний день выгрузки обычно неполный — не берём его в дневную статистику.
last_full = done["created"].dt.normalize().max() - pd.Timedelta(days=1)
daily = done.groupby(done["created"].dt.normalize()).size()
daily = daily[daily.index <= last_full]
daily = daily.reindex(pd.date_range(daily.index.min(), daily.index.max()), fill_value=0)
print(f"\nЗаказов в день: среднее {daily.mean():.1f}, дисперсия {daily.var():.1f}, "
      f"дисперсия/среднее {daily.var() / daily.mean():.2f} (Пуассон дал бы 1)")
print("Среднее по дням недели (0 = пн):", daily.groupby(daily.index.dayofweek).mean().round(1).to_dict())
print("Доля заказов по часу создания, %:",
      (done["created"].dt.hour.value_counts(normalize=True).sort_index() * 100).round(1).to_dict())

own = done[done["delivery_type"] == "Доставка ресторана"]
week = own["created"].dt.to_period("W")
print("\nДоля заказов своих курьеров без отметки «Заказ готов», по неделям (последние 8):")
print(own.groupby(week)["ready"].apply(lambda s: s.isna().mean()).round(2).tail(8).to_string())
print("…и без отметки «Заказ передан курьеру»:")
print(own.groupby(week)["handed"].apply(lambda s: s.isna().mean()).round(2).tail(8).to_string())
