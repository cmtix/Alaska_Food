# Bright Data Walmart pipeline (store_id-optimized):
# Trigger snapshot → poll until ready → download → normalize → Alaska filter
# NOTE: This version also supports merging a month folder of JSON/NDJSON into
# a single CSV with inclusion-based column selection and a PULL_DATE field.

import os
import time
import sys
import csv
import json
import gzip
import argparse
import re
from pathlib import Path
from datetime import datetime
import requests

# --------------------- USER SETTINGS --------------------- #
BRIGHTDATA_API_KEY = "fb96b4c9c28b985bae9a68e2c98c69dff4b4f8f362d53a6d463cd285319adfaf"  # consider env var
API_KEY = os.getenv("BRIGHTDATA_API_KEY") or BRIGHTDATA_API_KEY

DATASET_ID = "gd_m693oc1r1gebnayxq"
INPUT_CSV = r"G:/.shortcut-targets-by-id/10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg/Drones_MV/GITHUB/ISER/MJones/FOOD_SECURITY/FOOD_PRICING/DATA_PULL_SCRIPTS/WM/Bright_Data/input_list_WM_test.csv"
OUT_DIR = Path(".")
INCLUDE_ERRORS = True

# Use 'discover_new' to expand coverage
DISCOVER_TYPE_DEFAULT = "discover_new"
DISCOVER_BY_DEFAULT = "keyword"

# Inclusion words (case-insensitive) used to select final columns before export.
# Augmented a bit from your R list to ensure normalized names are retained.
INCLUSION_WORDS = [
    "product.title", "name", "description",
    "Zip_Code", "zip",  # keep zipcode
    "primary.price",
    "location", "address", "city", "state", "store",
    "upc", "itemId", "product_id"  # include product_weight
]
INCLUSION_REGEX = re.compile("|".join(map(re.escape, INCLUSION_WORDS)), flags=re.IGNORECASE)

# --------------------------------------------------------- #
BASE = "https://api.brightdata.com/datasets/v3"
SESSION = requests.Session()
SESSION.headers.update({"Authorization": f"Bearer {API_KEY}"})
HEADERS_JSON = {"Authorization": f"Bearer {API_KEY}", "Accept": "application/json"}

def die(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)

# ---------------- Normalization helpers ---------------- #

def first(*vals):
    for v in vals:
        if v is None:
            continue
        if isinstance(v, str):
            vs = v.strip()
            if vs:
                return vs
        elif v not in ("", [], {}, ()):
            return v
    return ""

def extract_loc(row: dict):
    address = first(row.get("store_address"), row.get("address"), row.get("storeAddress"))
    city    = first(row.get("store_city"), row.get("city"), row.get("storeCity"))
    zipcode = first(row.get("store_zip"), row.get("zip"), row.get("zipcode"), row.get("postal_code"))
    return address, city, zipcode

def extract_name(row): return first(row.get("product_name"), row.get("title"), row.get("name"))

def extract_desc(row): return first(row.get("product_description"), row.get("description"), row.get("short_description"))

def extract_price(row):
    return first(row.get("price"), row.get("price_current"), row.get("price_num"),
                 row.get("current_price"), row.get("final_price"),
                 row.get("priceString"), row.get("price_text"))

def extract_weight(row):
    return first(row.get("size"), row.get("size_text"), row.get("weight"),
                 row.get("unit_size"), row.get("package_size"))

def extract_upc(row): return first(row.get("upc"), row.get("universal_product_code"), row.get("gtin"))

def extract_pid(row):
    return first(row.get("product_id"), row.get("item_id"), row.get("us_item_id"),
                 row.get("id"), row.get("sku"), row.get("wupc"), row.get("gtin"))

FIELDNAMES = [
    "address", "city", "zipcode",
    "product_name", "product_description",
    "product_price", "product_weight",
    "upc", "product_id"
]

def normalize_row(row: dict) -> dict:
    address, city, zipcode = extract_loc(row)
    return {
        "address": address,
        "city": city,
        "zipcode": zipcode,
        "product_name": extract_name(row),
        "product_description": extract_desc(row),
        "product_price": extract_price(row),
        "product_weight": extract_weight(row),
        "upc": extract_upc(row),
        "product_id": extract_pid(row),
    }

# ---------------- Bright Data snapshot (unchanged core) ---------------- #

def trigger_snapshot():
    """Trigger a new snapshot and return snapshot_id."""
    url = f"{BASE}/trigger"
    params = {
        "dataset_id": DATASET_ID,
        "include_errors": str(INCLUDE_ERRORS).lower(),
        "type": "discover_new",
        "discover_by": "keyword",
    }
    files = {"data": ("data.csv", open(INPUT_CSV, "rb"), "text/csv")}
    r = SESSION.post(url, params=params, files=files, timeout=60)
    try:
        r.raise_for_status()
    finally:
        files["data"][1].close()

    payload = r.json()
    snapshot_id = payload.get("snapshot_id")
    if not snapshot_id:
        die(f"No snapshot_id in trigger response: {payload}")
    print(f"[OK] Triggered snapshot_id: {snapshot_id}")
    return snapshot_id

def get_status(snapshot_id):
    url = f"{BASE}/snapshot/{snapshot_id}"
    r = SESSION.get(url, headers=HEADERS_JSON, timeout=60)
    try:
        payload = r.json()
    except Exception:
        return r.status_code, {"message": r.text[:300]}, r.headers
    return r.status_code, payload, r.headers

def _looks_like_data_payload(payload: dict) -> bool:
    if not isinstance(payload, dict):
        return False
    keys = set(payload.keys())
    likely = {"sku", "url", "gtin", "final_price", "product_id", "title", "name"}
    return ("status" not in keys) and (len(keys & likely) > 0)

def _csv_available(snapshot_id: str) -> bool:
    try:
        r = SESSION.head(f"{BASE}/snapshot/{snapshot_id}/file.csv",
                         allow_redirects=True, timeout=30)
        return r.status_code == 200
    except Exception:
        return False

def poll_until_ready(snapshot_id, max_wait_minutes=90):
    deadline = time.time() + max_wait_minutes * 60
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        code, payload, headers = get_status(snapshot_id)
        status = (payload.get("status") or payload.get("state") or "").lower()
        msg = payload.get("message") or payload.get("status_description") or ""
        print(f"[Poll {attempt}] status_code={code} status={status} msg={msg}")

        if status in {"ready", "completed"}:
            print("[OK] Snapshot is ready (status).")
            return
        if code == 200 and _looks_like_data_payload(payload):
            print("[OK] Snapshot is ready (data payload detected).")
            return
        if _csv_available(snapshot_id):
            print("[OK] Snapshot is ready (CSV available).")
            return

        retry_after = headers.get("Retry-After")
        wait_s = int(retry_after) if (retry_after and retry_after.isdigit()) else 30
        time.sleep(wait_s)

    if _csv_available(snapshot_id):
        print("[OK] Snapshot appears ready after timeout; proceeding to download.")
        return
    die("Timeout: snapshot did not become ready within the polling window.")

def download_bytes(url):
    r = SESSION.get(url, timeout=120)
    r.raise_for_status()
    return r.content

def download_outputs(snapshot_id, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "walmart_brightdata_raw.csv"
    json_path = out_dir / "walmart_brightdata_raw.json"

    # CSV
    csv_bytes = download_bytes(f"{BASE}/snapshot/{snapshot_id}/file.csv")
    csv_path.write_bytes(csv_bytes)
    print(f"[OK] Saved raw CSV → {csv_path.resolve()}")

    # JSON (optional)
    try:
        json_bytes = download_bytes(f"{BASE}/snapshot/{snapshot_id}/file.json")
        json_path.write_bytes(json_bytes)
        print(f"[OK] Saved raw JSON → {json_path.resolve()}")
    except requests.HTTPError as e:
        print(f"[WARN] JSON download not available: {e}")

    return csv_path

def normalize_csv(raw_csv_path: Path, out_dir: Path):
    norm_csv_path = out_dir / "walmart_brightdata_normalized.csv"
    with open(raw_csv_path, "r", encoding="utf-8", newline="") as f_in, \
         open(norm_csv_path, "w", encoding="utf-8", newline="") as f_out:
        reader = csv.DictReader(f_in)
        # Build final columns using inclusion regex + PULL_DATE
        pull_date = datetime.now().strftime("%m-%d-%Y")
        # Start from normalized fieldnames + PULL_DATE
        candidate_cols = FIELDNAMES + ["PULL_DATE"]
        final_cols = [c for c in candidate_cols if INCLUSION_REGEX.search(c) or c == "PULL_DATE"]
        writer = csv.DictWriter(f_out, fieldnames=final_cols)
        writer.writeheader()

        for row in reader:
            norm = normalize_row(row)
            norm["PULL_DATE"] = pull_date
            # restrict to final columns
            writer.writerow({k: norm.get(k, "") for k in final_cols})

    print(f"[OK] Saved normalized CSV → {norm_csv_path.resolve()}")
    return norm_csv_path

def alaska_filter(csv_path: Path, out_path: Path | None = None):
    """Filter by Alaska ZIP prefixes (995–999). Writes sibling file if out_path is None."""
    if out_path is None:
        out_path = csv_path.with_name(csv_path.stem + "_AK.csv")
    try:
        import pandas as pd
        df = pd.read_csv(csv_path, dtype=str)
        # if zipcode col was filtered out accidentally, skip AK filter
        if "zipcode" not in df.columns:
            print("[WARN] Alaska filter skipped: 'zipcode' column not present after inclusion filter.")
            return None
        df["zipcode"] = df["zipcode"].fillna("").astype(str)
        df_ak = df[df["zipcode"].str.startswith(("995", "996", "997", "998", "999"))]
        df_ak.to_csv(out_path, index=False)
        print(f"[OK] Saved Alaska-only CSV → {out_path.resolve()} (rows: {len(df_ak)})")
        return out_path
    except Exception as e:
        print(f"[WARN] Alaska filter skipped: {e}")
        return None

# ---------------- Month folder merger (JSON/NDJSON -> single CSV) ---------------- #

def _open_text(path: Path):
    """Open JSON or JSON.GZ in text mode with utf-8."""
    if str(path).lower().endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return open(path, "r", encoding="utf-8", newline="")

def _each_record_from_json_file(path: Path):
    """
    Yield dict records from either:
      - a JSON array file
      - NDJSON/JSONL file (one JSON per line)
    """
    with _open_text(path) as f:
        first_chunk = f.read(2048)
        if not first_chunk:
            return
        first_non_ws = next((ch for ch in first_chunk if not ch.isspace()), None)
        f.seek(0)

        if first_non_ws == "[":
            try:
                data = json.load(f)
                if isinstance(data, list):
                    for rec in data:
                        if isinstance(rec, dict):
                            yield rec
                elif isinstance(data, dict):
                    yield data
            except Exception as e:
                print(f"[WARN] Failed to parse JSON array in {path.name}: {e}")
        else:
            for i, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if isinstance(rec, dict):
                        yield rec
                except Exception as e:
                    if i <= 3:
                        print(f"[WARN] Bad JSON line {i} in {path.name}: {e}")

def merge_month_json_to_csv(month_dir: Path):
    """
    Merge all *.json / *.json.gz files in month_dir, normalize to target columns,
    apply inclusion words to choose final columns, add PULL_DATE, and write ONE CSV.
    """
    if not month_dir.is_dir():
        die(f"Not a directory: {month_dir}")

    json_files = sorted([
        p for p in month_dir.rglob("*")
        if p.is_file() and p.name.lower().endswith((".json", ".json.gz"))
    ])
    if not json_files:
        die(f"No JSON/NDJSON files found in: {month_dir}")

    out_csv = month_dir / f"{month_dir.name}_walmart_brightdata_normalized.csv"
    pull_date = datetime.now().strftime("%m-%d-%Y")

    # Determine final columns using inclusion regex + PULL_DATE
    candidate_cols = FIELDNAMES + ["PULL_DATE"]
    final_cols = [c for c in candidate_cols if INCLUSION_REGEX.search(c) or c == "PULL_DATE"]

    count_written = 0
    with open(out_csv, "w", encoding="utf-8", newline="") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=final_cols)
        writer.writeheader()

        for jf in json_files:
            print(f"[Read] {jf}")
            for rec in _each_record_from_json_file(jf):
                norm = normalize_row(rec)
                norm["PULL_DATE"] = pull_date
                writer.writerow({k: norm.get(k, "") for k in final_cols})
                count_written += 1

    print(f"[OK] Wrote merged normalized CSV → {out_csv.resolve()} (rows: {count_written})")
    # Alaska-only CSV (if zipcode present after inclusion)
    alaska_filter(out_csv)
    return out_csv

# ---------------- Main CLI ---------------- #

def run_pipeline(existing_snapshot_id: str | None = None):
    if not API_KEY or API_KEY == "PASTE_YOUR_KEY_HERE":
        die("Set BRIGHTDATA_API_KEY or paste API_KEY in the script.")

    if existing_snapshot_id:
        snapshot_id = existing_snapshot_id
        print(f"[Info] Using existing snapshot_id: {snapshot_id}")
    else:
        snapshot_id = trigger_snapshot()
        try:
            Path("last_snapshot.txt").write_text(snapshot_id)
            print(f"[Info] Saved snapshot id → {Path('last_snapshot.txt').resolve()}")
        except Exception as e:
            print(f"[WARN] Could not save snapshot id: {e}")

    poll_until_ready(snapshot_id, max_wait_minutes=90)

    # Download raw outputs (CSV + optional JSON)
    raw_csv = download_outputs(snapshot_id, OUT_DIR)

    # Normalize + inclusion filter + PULL_DATE
    norm_csv = normalize_csv(raw_csv, OUT_DIR)

    # Alaska-only
    alaska_filter(norm_csv, None)

def main():
    ap = argparse.ArgumentParser(description="Walmart Bright Data pipeline + month-folder merger")
    ap.add_argument("--snapshot-id", help="Use an existing snapshot id (skips trigger).")
    ap.add_argument("--month-dir", help="Merge all JSON/NDJSON in this folder into a SINGLE normalized CSV with inclusion filter + PULL_DATE.")
    args = ap.parse_args()

    if args.month_dir:
        month_dir = Path(args.month_dir)
        merge_month_json_to_csv(month_dir)
    else:
        run_pipeline(existing_snapshot_id=args.snapshot_id)

if __name__ == "__main__":
    main()

