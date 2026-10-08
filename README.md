# deliverymaxxing

Сколько поваров и курьеров ставить на смену и сколько тратить на продвижение доставки, чтобы
максимизировать прибыль ресторана. Пилот — «Сыроварня», Архангельское / Новая Рига
(в r_keeper `RIGA`, в Яндекс Еда Вендор — «деревня Воронки, 1к4»).

- [docs/model.md](docs/model.md) — математическая постановка задачи.
- [docs/findings.md](docs/findings.md) — что уже показали данные, открытые вопросы и запросы данных.
- [docs/data_requests.md](docs/data_requests.md) — какие данные запросить и у кого.
- [docs/experiment.md](docs/experiment.md) — дизайн и расписание эксперимента со ставками продвижения.
- [docs/handoff.md](docs/handoff.md) — как продолжить работу в новой сессии.

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
  07_direct_vs_own_delivery.py  расход Директа на рекламу сайта vs заказы своей доставки
  08_staffing.py         смены курьеров и официантов (BioTime) против доставок и занятых столов
  09_kitchen_staffing.py повара по цехам (BioTime) против потока блюд, сколько нужно по часам
  biotime.py             разбор выгрузок BioTime, ФИО сразу заменяются псевдонимами
  experiment_schedule.py расписание эксперимента со ставками (сбалансированные случайные дни)
  yandex_api.py          Директ и Метрика: цели кампаний, конверсии, посадочные, заказы с сайта
data/raw/                выгрузки (в git не попадают)
```

## Данные

Положите файлы в `data/raw/` под этими именами:

| Файл | Откуда |
|---|---|
| `vendor_orders.xlsx` | Яндекс Еда Вендор → Финансы → «История заказов» |
| `vendor_promo_weekly.xlsx` | Яндекс Еда Вендор → продвижение: отчёт по неделям и витринам |
| `fact_rk7_hourly.csv`, `fact_rk7_payments_daily.csv` | витрины r_keeper (`marts/`) |
| `riga_orders.parquet`, `riga_lines.parquet`, `dim_dish.parquet`, `dim_category.parquet`, `riga_sh_daily.parquet` | `build_riga_pilot.py` из витрин `marts/` |
| `biotime/<отдел>_<ГГГГ-ММ>.csv` (`delivery_`, `waiters_`, `kitchen_2026-06.csv`) | BioTime 8 → «Табель учёта рабочего времени», CSV |

Данные коммерческие: в репозиторий их не кладём, `data/` в `.gitignore`.

## Запуск

```
pip install -r requirements.txt
python analysis/01_vendor_orders.py
...
YANDEX_OAUTH_TOKEN=... python analysis/yandex_api.py conversions 713315432
```

Токены Яндекса берутся только из переменных окружения: `YANDEX_OAUTH_TOKEN` (Метрика и
аккаунт Директа своего логина) и `YANDEX_DIRECT_TOKENS` — JSON `{"логин": "токен"}` для других
аккаунтов Директа. В файлы и в репозиторий токены не кладём.
