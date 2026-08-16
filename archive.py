import json
import os
from datetime import datetime, timedelta

DATA_DIR = os.path.join(os.path.dirname(__file__), "docs", "data")
INDEX_PATH = os.path.join(DATA_DIR, "index.json")


def _day_path(date_str):
    return os.path.join(DATA_DIR, f"{date_str}.json")


def load_recent_enriched_situations(days=2):
    """Special situations from the last `days` days that were successfully
    enriched already (summary is not None), keyed by (company, headline) —
    used to skip re-running the LLM on something already processed when the
    lookback window overlaps with a previous run."""
    if not os.path.exists(INDEX_PATH):
        return {}

    with open(INDEX_PATH) as f:
        index = json.load(f)

    cutoff = datetime.now() - timedelta(days=days)
    cache = {}
    for date_str in index.get("dates", []):
        try:
            if datetime.strptime(date_str, "%Y-%m-%d") < cutoff:
                continue
        except ValueError:
            continue

        path = _day_path(date_str)
        if not os.path.exists(path):
            continue
        with open(path) as f:
            record = json.load(f)

        for s in record.get("special_situations", []):
            if s.get("summary") is None:
                continue  # never got enriched, don't cache a miss
            key = (s.get("company"), s.get("headline"))
            if key not in cache:
                cache[key] = s

    return cache


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
