import json
import os
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), "docs", "data")
INDEX_PATH = os.path.join(DATA_DIR, "index.json")


def _day_path(date_str):
    return os.path.join(DATA_DIR, f"{date_str}.json")


def write_daily_record(situations, fallen_ipos):
    os.makedirs(DATA_DIR, exist_ok=True)
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")

    record = {
        "date": date_str,
        "generated_at": now.isoformat(),
        "special_situations": situations,
        "fallen_ipos": fallen_ipos,
    }
    with open(_day_path(date_str), "w") as f:
        json.dump(record, f, indent=2, default=str)

    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH) as f:
            index = json.load(f)
    else:
        index = {"dates": []}

    if date_str not in index["dates"]:
        index["dates"].append(date_str)
    index["dates"].sort(reverse=True)

    with open(INDEX_PATH, "w") as f:
        json.dump(index, f, indent=2)

    print(f"  [archive] wrote {_day_path(date_str)} ({len(situations)} situations, {len(fallen_ipos)} fallen IPOs)")
