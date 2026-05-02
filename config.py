import json
import os

_watchlist_path = os.path.join(os.path.dirname(__file__), "watchlist.json")

with open(_watchlist_path) as f:
    COMPANIES = json.load(f)

WHATSAPP_NUMBER = "+919500055366"
SCHEDULE_TIME_IST = "20:00"
