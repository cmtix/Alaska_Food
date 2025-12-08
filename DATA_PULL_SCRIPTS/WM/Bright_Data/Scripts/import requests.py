import requests
from pathlib import Path

url = "https://api.brightdata.com/datasets/v3/trigger"

headers = {
    "Authorization": "Bearer 5470de471903618d2dd462633e022234e47d1a8257a1db9f615abda30cb047d3",
}

params = {
    "dataset_id": "gd_m693oc1r1gebnayxq",
    "include_errors": "true",
    "type": "discover_new",
    "discover_by": "keyword",
}

# *** USE YOUR REAL CSV PATH HERE ***
csv_path = Path(
    r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA\RAW_DATA\WM_RAW\WM_25_11\data_from_search_file.csv"
)

if not csv_path.exists():
    raise FileNotFoundError(f"CSV not found: {csv_path}")

with csv_path.open("rb") as fh:
    files = {"data": ("data.csv", fh, "text/csv")}
    resp = requests.post(url, headers=headers, params=params, files=files, timeout=120)

print("Status:", resp.status_code)
try:
    print("JSON:", resp.json())
except Exception:
    print("Raw response:", resp.text[:500])
