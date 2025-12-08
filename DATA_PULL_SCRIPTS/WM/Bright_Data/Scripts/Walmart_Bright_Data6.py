

# Configure Environment----

import os, time, sys, csv, json
from pathlib import Path
import requests

BRIGHTDATA_API_KEY = "fb96b4c9c28b985bae9a68e2c98c69dff4b4f8f362d53a6d463cd285319adfaf"  # keep secret



# --------------------- USER SETTINGS --------------------- #
API_KEY = os.getenv("BRIGHTDATA_API_KEY") or BRIGHTDATA_API_KEY

DATASET_ID = "gd_m693oc1r1gebnayxq"  # your Bright Data dataset id
INPUT_CSV = r"G:/.shortcut-targets-by-id/10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg/Drones_MV/GITHUB/ISER/MJones/FOOD_SECURITY/FOOD_PRICING/DATA_PULL_SCRIPTS/WM/Bright_Data/input_list_WM_test.csv"
OUT_DIR = Path(".")
INCLUDE_ERRORS = True
DISCOVER_TYPE = "discover_new"       # or "recrawl", etc., per your plan
DISCOVER_BY = "keyword"              # because we're uploading a keyword list
# --------------------------------------------------------- #

BASE = "https://api.brightdata.com/datasets/v3"
HEADERS_JSON = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json",
}
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

def die(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)

def trigger_snapshot():
    """Trigger a new snapshot and return snapshot_id."""
    url = f"{BASE}/trigger"
    params = {
        "dataset_id": DATASET_ID,
        "include_errors": str(INCLUDE_ERRORS).lower(),
        "type": DISCOVER_TYPE,
        "discover_by": DISCOVER_BY,
    }
    files = {"data": ("G:/.shortcut-targets-by-id/10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg/Drones_MV/GITHUB/ISER/MJones/FOOD_SECURITY/FOOD_PRICING/DATA_PULL_SCRIPTS/WM/Bright_Data/input_list_WM.csv", open(INPUT_CSV, "rb"), "text/csv")}
    r = requests.post(url, headers=HEADERS, params=params, files=files)
    try:
        r.raise_for_status()
    finally:
        files["data"][1].close()
    try:
        payload = r.json()
    except Exception:
        die(f"Non-JSON trigger response ({r.status_code}): {r.text[:300]}")
    snapshot_id = payload.get("snapshot_id")
    if not snapshot_id:
        die(f"No snapshot_id in trigger response: {payload}")
    print(f"[OK] Triggered snapshot_id: {snapshot_id}")
    return snapshot_id

def get_status(snapshot_id):
    url = f"{BASE}/snapshot/{snapshot_id}"
    r = requests.get(url, headers=HEADERS_JSON)
    # 202 means “running/not ready” but still returns JSON
    try:
        payload = r.json()
    except Exception:
        return r.status_code, {"message": r.text[:300]}
    return r.status_code, payload

def _looks_like_data_payload(payload: dict) -> bool:
    # Heuristic: no "status" key and we see typical Walmart fields
    keys = set(payload.keys())
    likely = {"sku", "url", "gtin", "final_price", "product_id", "title", "name"}
    return ("status" not in keys) and (len(keys & likely) > 0)

def _csv_available(snapshot_id: str) -> bool:
    try:
        r = requests.head(f"{BASE}/snapshot/{snapshot_id}/file.csv", headers=HEADERS, allow_redirects=True)
        return r.status_code == 200
    except Exception:
        return False

def poll_until_ready(snapshot_id, max_wait_minutes=120):
    """Poll Bright Data until ready/completed, or data is directly returned, or CSV is available."""
    deadline = time.time() + max_wait_minutes * 60
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        r = requests.get(f"{BASE}/snapshot/{snapshot_id}", headers=HEADERS_JSON)
        retry_after = r.headers.get("Retry-After")
        try:
            payload = r.json()
        except Exception:
            payload = {"message": r.text[:300]}

        status = (payload.get("status") or payload.get("state") or "").lower()
        msg = payload.get("message") or payload.get("status_description") or ""
        print(f"[Poll {attempt}] {r.status_code=} {status=} {msg=}")

        # Success case 1: normal "ready"
        if status in {"ready", "completed"}:
            print("[OK] Snapshot is ready (status).")
            return

        # Success case 2: payload looks like data
        if r.status_code == 200 and isinstance(payload, dict) and _looks_like_data_payload(payload):
            print("[OK] Snapshot is ready (data payload detected).")
            return

        # Success case 3: CSV already available
        if _csv_available(snapshot_id):
            print("[OK] Snapshot is ready (CSV available).")
            return

        time.sleep(int(retry_after) if (retry_after and retry_after.isdigit()) else 30)

    # Last ditch: try the CSV anyway
    if _csv_available(snapshot_id):
        print("[O]()


def download_bytes(url):
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    return r.content

def download_outputs(snapshot_id, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "walmart_brightdata_raw.csv"
    json_path = out_dir / "walmart_brightdata_raw.json"

    # CSV is primary
    csv_bytes = download_bytes(f"{BASE}/snapshot/{snapshot_id}/file.csv")
    csv_path.write_bytes(csv_bytes)
    print(f"[OK] Saved raw CSV → {csv_path.resolve()}")

    # JSON is optional
    try:
        json_bytes = download_bytes(f"{BASE}/snapshot/{snapshot_id}/file.json")
        json_path.write_bytes(json_bytes)
        print(f"[OK] Saved raw JSON → {json_path.resolve()}")
    except requests.HTTPError as e:
        print(f"[WARN] JSON download not available: {e}")

    return csv_path

# ---------------- Normalization Helpers ---------------- #

def first(*vals):
    for v in vals:
        if v is None:
            continue
        if isinstance(v, str) and v.strip():
            return v.strip()
        if v not in ("", [], {}, ()):
            return v
    return ""

def extract_loc(row):
    address = first(row.get("store_address"), row.get("address"), row.get("storeAddress"))
    city    = first(row.get("store_city"), row.get("city"), row.get("storeCity"))
    zipcode = first(row.get("store_zip"), row.get("zip"), row.get("zipcode"), row.get("postal_code"))
    return address, city, zipcode

def extract_name(row):
    return first(row.get("product_name"), row.get("title"), row.get("name"))

def extract_desc(row):
    return first(row.get("product_description"), row.get("description"), row.get("short_description"))

def extract_price(row):
    return first(row.get("price"), row.get("price_current"), row.get("price_num"),
                 row.get("current_price"), row.get("priceString"), row.get("price_text"))

def extract_weight(row):
    return first(row.get("size"), row.get("size_text"), row.get("weight"),
                 row.get("unit_size"), row.get("package_size"))

def extract_upc(row):
    return first(row.get("upc"), row.get("universal_product_code"))

def extract_pid(row):
    return first(row.get("product_id"), row.get("item_id"), row.get("us_item_id"),
                 row.get("id"), row.get("gtin"), row.get("wupc"))

def normalize_csv(raw_csv_path: Path, out_dir: Path):
    norm_csv_path = out_dir / "walmart_brightdata_normalized.csv"
    fieldnames = [
        "address", "city", "zipcode",
        "product_name", "product_description",
        "product_price", "product_weight",
        "upc", "product_id"
    ]

    with open(raw_csv_path, "r", encoding="utf-8", newline="") as f_in, \
         open(norm_csv_path, "w", encoding="utf-8", newline="") as f_out:
        reader = csv.DictReader(f_in)
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()

        for row in reader:
            address, city, zipcode = extract_loc(row)
            writer.writerow({
                "address": address,
                "city": city,
                "zipcode": zipcode,
                "product_name": extract_name(row),
                "product_description": extract_desc(row),
                "product_price": extract_price(row),
                "product_weight": extract_weight(row),
                "upc": extract_upc(row),
                "product_id": extract_pid(row),
            })
    print(f"[OK] Saved normalized CSV → {norm_csv_path.resolve()}")
    return norm_csv_path

def alaska_filter(norm_csv_path: Path, out_dir: Path):
    """Filter by Alaska ZIP prefixes (995–999)."""
    ak_path = out_dir / "walmart_brightdata_normalized_AK.csv"
    try:
        import pandas as pd
        df = pd.read_csv(norm_csv_path, dtype=str)
        df["zipcode"] = df["zipcode"].fillna("").astype(str)
        df_ak = df[df["zipcode"].str.startswith(("995", "996", "997", "998", "999"))]
        df_ak.to_csv(ak_path, index=False)
        print(f"[OK] Saved Alaska-only CSV → {ak_path.resolve()} (rows: {len(df_ak)})")
        return ak_path
    except Exception as e:
        print(f"[WARN] Alaska filter skipped: {e}")
        return None

# ----------------------------- MAIN ----------------------------- #

def main():
    if not API_KEY or API_KEY == "PASTE_YOUR_KEY_HERE":
        die("Set BRIGHTDATA_API_KEY or paste API_KEY in the script.")

    # 1) Trigger snapshot
    snapshot_id = trigger_snapshot()

    # 2) Poll until ready
    poll_until_ready(snapshot_id, max_wait_minutes=30)

    # 3) Download raw outputs
    raw_csv = download_outputs(snapshot_id, OUT_DIR)

    # 4) Normalize to your required schema
    norm_csv = normalize_csv(raw_csv, OUT_DIR)

    # 5) Optional: Alaska-only filter
    alaska_filter(norm_csv, OUT_DIR)

if __name__ == "__main__":
    main()




