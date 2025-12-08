from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path
from typing import Iterable

import requests

# ----------------- CONFIG: set these three and run -----------------
TOKEN = os.getenv("BRIGHTDATA_API_KEY") or "fb96b4c9c28b985bae9a68e2c98c69dff4b4f8f362d53a6d463cd285319adfaf"
SNAPSHOT_ID = "sd_mhfv3f3f9c8hong92"  # <- your Oct snapshot id (update if needed)
OUT_DIR = r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA_PULL_SCRIPTS\WM\Bright_Data\Outputs"
# -------------------------------------------------------------------

BASE = "https://api.brightdata.com/datasets/v3"
AK_PREFIXES = ("995", "996", "997", "998", "999")
ZIP_KEYS = ("zipcode", "zip", "postal_code", "store_zip")

# Columns we’ll keep in the final CSV (if present)
FINAL_COLS = [
    "address", "city", "zipcode",
    "product_name", "title", "name",
    "product_description", "description",
    "price", "final_price", "current_price",
    "upc", "gtin",
    "product_id", "item_id", "us_item_id", "id", "sku"
]


def die(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)
    sys.exit(1)


def session() -> requests.Session:
    if not TOKEN or TOKEN.startswith("REPLACE_WITH_"):
        die("Set TOKEN at top of the script to your Bright Data API key.")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"})
    return s


def csv_ready(s: requests.Session, sid: str) -> bool:
    try:
        r = s.head(f"{BASE}/snapshot/{sid}/file.csv", allow_redirects=True, timeout=30)
        return r.status_code == 200
    except Exception:
        return False


def stream_to_file(s: requests.Session, url: str, out_path: Path) -> None:
    with s.get(url, stream=True, timeout=900) as r:
        r.raise_for_status()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                if chunk:
                    f.write(chunk)


def detect_zip(row: dict) -> str:
    for k in ZIP_KEYS:
        v = row.get(k)
        if v:
            return str(v).strip()
    return ""


def is_ak_zip(z: str) -> bool:
    return any(z.startswith(p) for p in AK_PREFIXES)


def write_row_subset(writer: csv.DictWriter, row: dict) -> None:
    # Build a small, readable record from what we find
    norm = {
        "address": row.get("store_address") or row.get("address") or row.get("storeAddress") or "",
        "city": row.get("store_city") or row.get("city") or row.get("storeCity") or "",
        "zipcode": detect_zip(row) or "",
        "product_name": row.get("product_name") or row.get("title") or row.get("name") or "",
        "product_description": row.get("product_description") or row.get("description") or "",
        "price": row.get("price") or row.get("final_price") or row.get("current_price") or "",
        "upc": row.get("upc") or row.get("gtin") or "",
        "product_id": row.get("product_id") or row.get("item_id") or row.get("us_item_id") or row.get("id") or row.get("sku") or "",
    }
    writer.writerow(norm)


def filter_csv_to_ak(src_csv: Path, out_csv: Path) -> int:
    # autodetect a zipcode column from header
    with open(src_csv, "r", encoding="utf-8", newline="") as fin, \
         open(out_csv, "w", encoding="utf-8", newline="") as fout:
        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=[
            "address","city","zipcode","product_name","product_description","price","upc","product_id"
        ])
        writer.writeheader()

        kept = 0
        for row in reader:
            z = detect_zip(row)
            if z and is_ak_zip(z):
                write_row_subset(writer, row)
                kept += 1
    return kept


def iter_jsonl_records(s: requests.Session, sid: str) -> Iterable[dict]:
    url = f"{BASE}/snapshot/{sid}/file.json"
    with s.get(url, stream=True, timeout=1800) as r:
        if r.status_code != 200:
            die(f"JSON endpoint not available (status {r.status_code}).")
        for raw in r.iter_lines(decode_unicode=True):
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except Exception:
                # ignore bad lines
                continue


def filter_jsonl_to_csv(s: requests.Session, sid: str, out_csv: Path) -> int:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "address","city","zipcode","product_name","product_description","price","upc","product_id"
        ])
        writer.writeheader()
        kept = 0
        for rec in iter_jsonl_records(s, sid):
            z = detect_zip(rec)
            if z and is_ak_zip(z):
                write_row_subset(writer, rec)
                kept += 1
    return kept


def main() -> None:
    s = session()
    out_dir = Path(OUT_DIR)
    raw_csv = out_dir / "walmart_brightdata_raw.csv"
    ak_csv = out_dir / "walmart_brightdata_AK.csv"

    if csv_ready(s, SNAPSHOT_ID):
        print("[INFO] CSV is ready → downloading raw CSV…")
        stream_to_file(s, f"{BASE}/snapshot/{SNAPSHOT_ID}/file.csv", raw_csv)
        print(f"[OK] Saved raw CSV: {raw_csv}")
        print("[INFO] Filtering to Alaska ZIPs…")
        n = filter_csv_to_ak(raw_csv, ak_csv)
        print(f"[OK] Saved AK-only CSV → {ak_csv} (rows kept: {n})")
        return

    print("[INFO] CSV not ready; falling back to JSONL stream…")
    n = filter_jsonl_to_csv(s, SNAPSHOT_ID, ak_csv)
    print(f"[OK] Saved AK-only CSV (from JSONL) → {ak_csv} (rows kept: {n})")


if __name__ == "__main__":
    main()
