# Walmart_Bright_Data10.py
# Bright Data Walmart pipeline:
#  - trigger snapshot (with limited retry)
#  - poll until ready (bounded)
#  - download CSV/JSON
#  - normalize to compact schema (+PULL_DATE)
#  - optional Alaska-only CSV
#  - optional month-folder merger (JSON/NDJSON -> one CSV)
#
# Examples:
#   python Walmart_Bright_Data10.py
#   python Walmart_Bright_Data10.py --max-wait 15 --poll-every 20
#   python Walmart_Bright_Data10.py --snapshot-id s_abcdef123
#   python Walmart_Bright_Data10.py --month-dir "G:/path/to/WM_2025_10"

from __future__ import annotations

import os
import sys
import csv
import json
import gzip
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Iterable, Optional

import requests

# ─────────────────────────────── Utility helpers ───────────────────────────────

def die(msg: str) -> None:
    """Print message to stderr and exit(1)."""
    print(msg, file=sys.stderr, flush=True)
    sys.exit(1)

def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ─────────────────────────────── Config (env/CLI) ───────────────────────────────

# API key: prefer env var set by your .BAT or scheduler.
API_KEY = os.getenv("BRIGHTDATA_API_KEY", "").strip()
if not API_KEY:
    die("Set BRIGHTDATA_API_KEY environment variable with your Bright Data API key.")

# Dataset ID can be overridden via env.
DATASET_ID: str = os.getenv("BRIGHTDATA_DATASET_ID", "gd_m693oc1r1gebnayxq").strip()

# Path to the CSV you POST to Bright Data (store list / queries).
INPUT_CSV: str = os.getenv(
    "BRIGHTDATA_INPUT_CSV",
    r"G:/.shortcut-targets-by-id/10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg/Drones_MV/GITHUB/ISER/MJones/FOOD_SECURITY/FOOD_PRICING/DATA_PULL_SCRIPTS/WM/Bright_Data/input_list_WM_test.csv",
)

# Output directory (defaults to current working directory).
OUT_DIR = Path(os.getenv("BRIGHTDATA_OUT_DIR", ".")).resolve()

# Include error rows in Bright Data output (their server option).
INCLUDE_ERRORS = True

# Default poll timing; override with CLI flags.
DEFAULT_MAX_WAIT_MIN = 90
DEFAULT_POLL_EVERY_S = 30

# ─────────────────────────────── HTTP/session constants ────────────────────────

BASE = "https://api.brightdata.com/datasets/v3"
SESSION = requests.Session()
SESSION.headers.update({"Authorization": f"Bearer {API_KEY}"})
HEADERS_JSON = {"Authorization": f"Bearer {API_KEY}", "Accept": "application/json"}

# ─────────────────────────────── Normalization helpers ─────────────────────────

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

def extract_loc(row: Dict[str, Any]):
    address = first(row.get("store_address"), row.get("address"), row.get("storeAddress"))
    city    = first(row.get("store_city"), row.get("city"), row.get("storeCity"))
    zipcode = first(row.get("store_zip"), row.get("zip"), row.get("zipcode"), row.get("postal_code"))
    return address, city, zipcode

def extract_name(row: Dict[str, Any]): return first(row.get("product_name"), row.get("title"), row.get("name"))
def extract_desc(row: Dict[str, Any]): return first(row.get("product_description"), row.get("description"), row.get("short_description"))

def extract_price(row: Dict[str, Any]):
    return first(row.get("price"), row.get("price_current"), row.get("price_num"),
                 row.get("current_price"), row.get("final_price"),
                 row.get("priceString"), row.get("price_text"))

def extract_weight(row: Dict[str, Any]):
    return first(row.get("size"), row.get("size_text"), row.get("weight"),
                 row.get("unit_size"), row.get("package_size"))

def extract_upc(row: Dict[str, Any]): return first(row.get("upc"), row.get("universal_product_code"), row.get("gtin"))

def extract_pid(row: Dict[str, Any]):
    return first(row.get("product_id"), row.get("item_id"), row.get("us_item_id"),
                 row.get("id"), row.get("sku"), row.get("wupc"), row.get("gtin"))

FIELDNAMES = [
    "address", "city", "zipcode",
    "product_name", "product_description",
    "product_price", "product_weight",
    "upc", "product_id"
]

def normalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
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

# ─────────────────────────────── Bright Data API helpers ───────────────────────

def trigger_snapshot() -> str:
    """
    Trigger a new snapshot with limited retry on 5xx.
    Returns the snapshot_id.
    """
    if not DATASET_ID:
        die("Missing DATASET_ID. Set BRIGHTDATA_DATASET_ID or edit the script.")

    url = f"{BASE}/trigger"
    params = {
        "dataset_id": DATASET_ID,
        "include_errors": str(INCLUDE_ERRORS).lower(),
        "type": "discover_new",
        "discover_by": "keyword",
    }

    attempts = 3
    for attempt in range(1, attempts + 1):
        try:
            with open(INPUT_CSV, "rb") as fh:
                files = {"data": ("data.csv", fh, "text/csv")}
                r = SESSION.post(url, params=params, files=files, timeout=90)
            r.raise_for_status()
            payload = r.json()
            sid = payload.get("snapshot_id")
            if not sid:
                raise RuntimeError(f"No snapshot_id in response: {payload}")
            print(f"[{_ts()}] [OK] Triggered snapshot_id: {sid}")
            return sid
        except requests.HTTPError as e:
            code = getattr(e.response, "status_code", None)
            body = (e.response.text[:200] + "...") if e.response is not None else str(e)
            print(f"[{_ts()}] [WARN] Trigger failed (attempt {attempt}/{attempts}) "
                  f"status={code} body={body}")
            if code and code >= 500 and attempt < attempts:
                time.sleep(15)
                continue
            raise
        except Exception as e:
            print(f"[{_ts()}] [ERROR] Trigger exception: {e}")
            if attempt < attempts:
                time.sleep(10)
                continue
            raise

def _csv_available(snapshot_id: str) -> bool:
    """HEAD the CSV endpoint; 200 implies file present."""
    try:
        r = SESSION.head(f"{BASE}/snapshot/{snapshot_id}/file.csv",
                         allow_redirects=True, timeout=30)
        return r.status_code == 200
    except Exception:
        return False

def get_snapshot_status(snapshot_id: str) -> str:
    """
    Returns one of: 'ready', 'running', 'failed', 'error'.
    If CSV is already available, treat as 'ready'.
    """
    url = f"{BASE}/snapshot/{snapshot_id}"
    try:
        r = SESSION.get(url, headers=HEADERS_JSON, timeout=60)
        try:
            payload: Dict[str, Any] = r.json()
        except Exception:
            payload = {"__raw": r.text}

        status = str(payload.get("status", "")).lower()
        if status in {"ready", "running", "failed", "error"}:
            return status

        if _csv_available(snapshot_id):
            return "ready"

        if isinstance(payload, dict) and payload and "status" not in payload:
            return "running"

        return "running"
    except requests.HTTPError:
        return "error"
    except Exception:
        return "error"

def poll_until_ready(snapshot_id: str, max_wait_minutes: int, poll_every: int) -> None:
    """Poll snapshot until ready or timeout; die on failure/timeout."""
    deadline = time.time() + max_wait_minutes * 60
    last_status = ""
    while True:
        now = time.time()
        if now > deadline:
            die("Timeout: snapshot did not become ready within the polling window.")

        status = get_snapshot_status(snapshot_id)
        if status != last_status:
            print(f"[{_ts()}] [POLL] snapshot={snapshot_id} status={status} "
                  f"remaining={int((deadline-now)/60)}m")
            last_status = status

        if status == "ready":
            return
        if status in {"failed", "error"}:
            die(f"Snapshot failed with status={status}")
        time.sleep(poll_every)

# ─────────────────────────────── Download + normalize ──────────────────────────

def download_bytes(url: str) -> bytes:
    r = SESSION.get(url, timeout=240)
    r.raise_for_status()
    return r.content

def download_outputs(snapshot_id: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "walmart_brightdata_raw.csv"
    json_path = out_dir / "walmart_brightdata_raw.json"

    csv_bytes = download_bytes(f"{BASE}/snapshot/{snapshot_id}/file.csv")
    csv_path.write_bytes(csv_bytes)
    print(f"[{_ts()}] [OK] Saved raw CSV → {csv_path}")

    try:
        json_bytes = download_bytes(f"{BASE}/snapshot/{snapshot_id}/file.json")
        json_path.write_bytes(json_bytes)
        print(f"[{_ts()}] [OK] Saved raw JSON → {json_path}")
    except requests.HTTPError as e:
        print(f"[{_ts()}] [WARN] JSON download not available: {e}")

    return csv_path

def normalize_csv(raw_csv_path: Path, out_dir: Path) -> Path:
    norm_csv_path = out_dir / "walmart_brightdata_normalized.csv"
    pull_date = datetime.now().strftime("%m-%d-%Y")

    with open(raw_csv_path, "r", encoding="utf-8", newline="") as f_in, \
         open(norm_csv_path, "w", encoding="utf-8", newline="") as f_out:
        reader = csv.DictReader(f_in)
        final_cols = FIELDNAMES + ["PULL_DATE"]
        writer = csv.DictWriter(f_out, fieldnames=final_cols)
        writer.writeheader()

        for row in reader:
            norm = normalize_row(row)
            norm["PULL_DATE"] = pull_date
            writer.writerow({k: norm.get(k, "") for k in final_cols})

    print(f"[{_ts()}] [OK] Saved normalized CSV → {norm_csv_path}")
    return norm_csv_path

def alaska_filter(csv_path: Path, out_path: Optional[Path] = None) -> Optional[Path]:
    """Filter by Alaska ZIP prefixes (995–999) if 'zipcode' exists."""
    try:
        import pandas as pd
    except Exception:
        print(f"[{_ts()}] [WARN] pandas not installed; skipping Alaska-only export.")
        return None

    out_path = out_path or csv_path.with_name(csv_path.stem + "_AK.csv")
    try:
        df = pd.read_csv(csv_path, dtype=str)
        if "zipcode" not in df.columns:
            print(f"[{_ts()}] [WARN] Alaska filter skipped: 'zipcode' missing.")
            return None
        df["zipcode"] = df["zipcode"].fillna("").astype(str)
        df_ak = df[df["zipcode"].str.startswith(("995", "996", "997", "998", "999"))]
        df_ak.to_csv(out_path, index=False)
        print(f"[{_ts()}] [OK] Saved Alaska-only CSV → {out_path} (rows: {len(df_ak)})")
        return out_path
    except Exception as e:
        print(f"[{_ts()}] [WARN] Alaska filter error: {e}")
        return None

# ───────────────────────── Month-folder merger (JSON/NDJSON → CSV) ─────────────

def _open_text(path: Path):
    if str(path).lower().endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return open(path, "r", encoding="utf-8", newline="")

def _each_record_from_json_file(path: Path) -> Iterable[Dict[str, Any]]:
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
                print(f"[{_ts()}] [WARN] JSON array parse failed {path.name}: {e}")
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
                        print(f"[{_ts()}] [WARN] Bad JSON line {i} in {path.name}: {e}")

def merge_month_json_to_csv(month_dir: Path) -> Path:
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
    final_cols = FIELDNAMES + ["PULL_DATE"]

    count_written = 0
    with open(out_csv, "w", encoding="utf-8", newline="") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=final_cols)
        writer.writeheader()

        for jf in json_files:
            print(f"[{_ts()}] [READ] {jf}")
            for rec in _each_record_from_json_file(jf):
                norm = normalize_row(rec)
                norm["PULL_DATE"] = pull_date
                writer.writerow({k: norm.get(k, "") for k in final_cols})
                count_written += 1

    print(f"[{_ts()}] [OK] Wrote merged CSV → {out_csv} (rows: {count_written})")
    alaska_filter(out_csv)
    return out_csv

# ─────────────────────────────── Orchestrator ──────────────────────────────────

def run_pipeline(existing_snapshot_id: Optional[str],
                 max_wait_min: int,
                 poll_every_s: int) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if existing_snapshot_id:
        snapshot_id = existing_snapshot_id
        print(f"[{_ts()}] [INFO] Using existing snapshot_id: {snapshot_id}")
    else:
        snapshot_id = trigger_snapshot()
        try:
            (OUT_DIR / "last_snapshot.txt").write_text(snapshot_id, encoding="utf-8")
            print(f"[{_ts()}] [INFO] Saved snapshot id → {(OUT_DIR / 'last_snapshot.txt').resolve()}")
        except Exception as e:
            print(f"[{_ts()}] [WARN] Could not save snapshot id: {e}")

    poll_until_ready(snapshot_id, max_wait_minutes=max_wait_min, poll_every=poll_every_s)

    raw_csv = download_outputs(snapshot_id, OUT_DIR)
    norm_csv = normalize_csv(raw_csv, OUT_DIR)
    alaska_filter(norm_csv, None)

def main():
    ap = argparse.ArgumentParser(description="Walmart Bright Data pipeline + month-folder merger")
    ap.add_argument("--snapshot-id", help="Use an existing snapshot id (skip trigger).")
    ap.add_argument("--month-dir", help="Merge all JSON/NDJSON in this folder to ONE normalized CSV.")
    ap.add_argument("--max-wait", type=int, default=DEFAULT_MAX_WAIT_MIN, help="Max wait minutes (default 90).")
    ap.add_argument("--poll-every", type=int, default=DEFAULT_POLL_EVERY_S, help="Polling interval seconds (default 30).")
    args = ap.parse_args()

    if args.month_dir:
        merge_month_json_to_csv(Path(args.month_dir))
        return

    run_pipeline(existing_snapshot_id=args.snapshot_id,
                 max_wait_min=args.max_wait,
                 poll_every_s=args.poll_every)

if __name__ == "__main__":
    main()
