# deliverymaxxing

Сколько поваров и курьеров ставить на смену и сколько тратить на продвижение доставки, чтобы
максимизировать прибыль ресторана. Пилот — «Сыроварня», Архангельское / Новая Рига
(в r_keeper `RIGA`, в Яндекс Еда Вендор — «деревня Воронки, 1к4»).

- [docs/model.md](docs/model.md) — математическая постановка задачи.
- [docs/findings.md](docs/findings.md) — что уже показали данные, открытые вопросы и запросы данных.

## Структура

```
analysis/
  common.py              пути, загрузчики, OLS с робастными ошибками, окна по времени
  01_vendor_orders.py    заказы агрегаторов: спрос, дисперсия, каналы, пропуски отметок
  02_promo.py            промо в Еде: атрибуция, безубыточность, естественный эксперимент, мощность теста
  03_rkeeper_checks.py   сверка Вендора с r_keeper, проверка разметки каналов, структура заказов RIGA
  04_food_cost.py        фудкост по каналам (StoreHouse)
  05_kitchen_load.py     нагрузка кухни по часам, время готовки и ожидание курьера vs нагрузка
  06_hall_occupancy.py   одновременно открытые чеки зала, закон Литтла, признаки насыщения
  yandex_api.py          Директ и Метрика: цели кампаний, конверсии, посадочные, заказы с сайта
data/raw/                выгрузки (в git не попадают)
```

## Данные

Положите файлы в `data/raw/` под этими именами:

| Файл | Откуда |
|---|---|
| `vendor_orders.xlsx` | Яндекс Еда Вендор → Заказы → выгрузка отчёта по заказам |
| `fact_rk7_hourly.csv`, `fact_rk7_payments_daily.csv` | витрины r_keeper (`marts/`) |
| `riga_orders.parquet`, `riga_lines.parquet`, `dim_dish.parquet`, `dim_category.parquet`, `riga_sh_daily.parquet` | `build_riga_pilot.py` из витрин `marts/` |

Данные коммерческие: в репозиторий их не кладём, `data/` в `.gitignore`.

## Запуск

```
pip install -r requirements.txt
python analysis/01_vendor_orders.py
...
YANDEX_OAUTH_TOKEN=... python analysis/yandex_api.py conversions 713315432
```

Токен Яндекса берётся только из переменной окружения `YANDEX_OAUTH_TOKEN` и видит только
аккаунт Директа своего логина.
