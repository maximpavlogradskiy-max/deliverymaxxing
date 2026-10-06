"""Запросы к API Яндекс Директа и Метрики (только чтение).

Токен — переменная окружения YANDEX_OAUTH_TOKEN (видит только аккаунт Директа своего логина).

    python analysis/yandex_api.py goals 713315432          # стратегия и ключевые цели кампании
    python analysis/yandex_api.py conversions 713315432    # конверсии кампании по целям за 30 дней
    python analysis/yandex_api.py landing                  # кампании Директа → посадочные страницы и цели
    python analysis/yandex_api.py site-orders novaya_riga  # заказы с сайта по ресторану
"""
import csv
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

DIRECT = "https://api.direct.yandex.com/json/v5/"
METRIKA = "https://api-metrika.yandex.net/stat/v1/data"
COUNTER = 65956783  # syrovarnya.com

GOALS = {  # цели счётчика сайта, по которым смотрим результат
    "purchase": 3065956783,      # Ecommerce: покупка
    "order_done": 174783430,     # Заказ оформлен (событие success_order_target)
    "call": 139736020,           # Звонок в ресторан (общая цель) — клик по номеру, не сам звонок
    "booking": 251480679,        # Бронирование стола (общая цель)
}
# цель «переход на страницу с доставкой <ресторан>» — отбор визитов ресторана
DELIVERY_PAGE_GOALS = {"novaya_riga": 490734752, "zelenograd": 490693613}

TOKEN = os.environ.get("YANDEX_OAUTH_TOKEN", "")


def direct(service, body, extra_headers=None):
    headers = {"Authorization": "Bearer " + TOKEN, "Accept-Language": "ru", **(extra_headers or {})}
    req = urllib.request.Request(DIRECT + service, data=json.dumps(body).encode(), headers=headers)
    return urllib.request.urlopen(req, timeout=120)


def metrika(params):
    req = urllib.request.Request(METRIKA + "?" + urllib.parse.urlencode(params),
                                 headers={"Authorization": "OAuth " + TOKEN})
    return json.load(urllib.request.urlopen(req, timeout=120))


def period(days=30):
    return str(date.today() - timedelta(days=days)), str(date.today() - timedelta(days=1))


def get_campaign(campaign_id):
    body = {"method": "get", "params": {
        "SelectionCriteria": {"Ids": [int(campaign_id)]},
        "FieldNames": ["Id", "Name", "State", "StartDate"],
        "TextCampaignFieldNames": ["BiddingStrategy", "PriorityGoals", "CounterIds"]}}
    return json.load(direct("campaigns", body))["result"]["Campaigns"][0]


def campaign_goals(campaign_id):
    print(json.dumps(get_campaign(campaign_id), ensure_ascii=False, indent=1))


def campaign_conversions(campaign_id):
    """Показы, клики, расход (с НДС) и конверсии кампании по её ключевым целям и целям сайта, атрибуция AUTO."""
    priority = get_campaign(campaign_id).get("TextCampaign", {}).get("PriorityGoals") or {}
    goal_ids = list(dict.fromkeys([g["GoalId"] for g in priority.get("Items", [])] + list(GOALS.values())))
    d1, d2 = period()
    body = {"params": {
        "SelectionCriteria": {"DateFrom": d1, "DateTo": d2,
                              "Filter": [{"Field": "CampaignId", "Operator": "EQUALS", "Values": [str(campaign_id)]}]},
        "Goals": [str(g) for g in goal_ids], "AttributionModels": ["AUTO"],
        "FieldNames": ["CampaignId", "Impressions", "Clicks", "Cost", "Conversions"],
        "ReportName": f"conv_{campaign_id}_{int(time.time())}", "ReportType": "CUSTOM_REPORT",
        "DateRangeType": "CUSTOM_DATE", "Format": "TSV", "IncludeVAT": "YES", "IncludeDiscount": "NO"}}
    headers = {"processingMode": "auto", "returnMoneyInMicros": "false",
               "skipReportHeader": "true", "skipReportSummary": "true"}
    while True:
        resp = direct("reports", body, headers)
        if resp.status == 200:
            break
        time.sleep(int(resp.headers.get("retryIn", 5)))  # 201/202: отчёт строится
    print(f"{d1} – {d2}")
    for row in csv.DictReader(io.StringIO(resp.read().decode()), delimiter="\t"):
        for k, val in row.items():
            print(f"  {k:40s} {val}")


def landing():
    """Визиты из Директа по кампаниям и посадочным страницам, с целями (последний значимый источник)."""
    d1, d2 = period()
    metrics = ["ym:s:visits"] + [f"ym:s:goal{g}reaches" for g in GOALS.values()]
    r = metrika({"ids": COUNTER, "date1": d1, "date2": d2, "accuracy": "full", "limit": 40,
                 "dimensions": "ym:s:lastsignDirectClickOrder,ym:s:lastsignDirectClickOrderName,ym:s:startURLPath",
                 "metrics": ",".join(metrics), "filters": "ym:s:lastsignTrafficSource=='ad'",
                 "sort": "-ym:s:visits"})
    print(f"{d1} – {d2}; колонки: visits, " + ", ".join(GOALS))
    for row in r["data"]:
        cid, name, page = (x.get("id") or x.get("name") for x in row["dimensions"])
        print(f"  {cid:>10} {name[:40]:40s} {page[:35]:35s}", [round(m) for m in row["metrics"]])


def site_orders(restaurant):
    """Покупки в визитах, где посетитель дошёл до страницы доставки ресторана."""
    d1, d2 = period()
    goal = DELIVERY_PAGE_GOALS[restaurant]
    r = metrika({"ids": COUNTER, "date1": d1, "date2": d2, "accuracy": "full",
                 "metrics": "ym:s:visits,ym:s:ecommercePurchases,ym:s:ecommerceRevenue,"
                            f"ym:s:goal{GOALS['order_done']}reaches",
                 "filters": f"ym:s:goal{goal}IsReached=='yes'"})
    visits, purchases, revenue, done = (round(x) for x in r["totals"])
    print(f"{d1} – {d2}, {restaurant}: визитов {visits}, покупок {purchases} на {revenue}₽, "
          f"«Заказ оформлен» {done}")


if __name__ == "__main__":
    if not TOKEN:
        sys.exit("нет YANDEX_OAUTH_TOKEN")
    cmd, *args = sys.argv[1:] or ["landing"]
    try:
        {"goals": campaign_goals, "conversions": campaign_conversions,
         "landing": landing, "site-orders": site_orders}[cmd](*args)
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode()[:300]}")
