#!/usr/bin/env python3

import json
import csv
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

def iso_timestamp_to_pull_date(ts: str) -> str:
    """
    Convert ISO timestamp like '2025-11-16T18:43:28.048Z'
    to '25-11-16' (YY-MM-DD).
    """
    if not ts:
        return ""
    ts = ts.strip()
    if not ts:
        return ""
    if "T" in ts:
        date_part = ts.split("T", 1)[0]
    else:
        date_part = ts
    parts = date_part.split("-")
    if len(parts) != 3:
        return ""
    year = parts[0][-2:]
    month = parts[1]
    day = parts[2]
    return f"{year}-{month}-{day}"

OUTPUT_COLUMNS = [
    "PULL_DATE",
    "error",
    "error_code",
    "input.name",
    "input.zip_code",
    "input.store_id",
    "final_price",
    "sku",
    "product_id",
    "product_name",
    "upc",
    "unit",
    "zip_code",
    "store_id",
    "brand_walmart_url",
    "condition",
    "pickup_address",
    "pickup_store_id",
    "pickup_zipcode",
]

def load_records(json_path: Path) -> List[Dict[str, Any]]:
    """
    Load Bright Data JSON.
    Supports:
      - top-level list
      - top-level dict with 'results' / 'data' / 'items' / 'docs'
      - NDJSON (one JSON object per line)
    """
    text = json_path.read_text(encoding="utf-8").strip()
    if not text:
        print(f"[INFO] JSON file is empty: {json_path}")
        return []

    # Try regular JSON first
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            for key in ["results", "data", "items", "docs"]:
                if key in data and isinstance(data[key], list):
                    print(f"[INFO] Loaded {len(data[key])} records from key '{key}'")
                    return [r for r in data[key] if isinstance(r, dict)]
            print("[INFO] Loaded 1 top-level dict record")
            return [data]
        if isinstance(data, list):
            print(f"[INFO] Loaded list with {len(data)} records")
            return [r for r in data if isinstance(r, dict)]
    except Exception:
        # Fall through to NDJSON attempt
        pass

    # NDJSON fallback
    records = []
    with json_path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if isinstance(rec, dict):
                    records.append(rec)
            except Exception as e:
                if i <= 5:
                    print(f"[WARN] Bad JSON line {i}: {e}")
    print(f"[INFO] Loaded {len(records)} records from NDJSON")
    return records

def normalize_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    inp = rec.get("input") or {}

    ts = rec.get("timestamp", "")
    pull_date = iso_timestamp_to_pull_date(ts)

    out_row = {
        "PULL_DATE": pull_date,
        "error": rec.get("error", ""),
        "error_code": rec.get("error_code", ""),
        "input.name": inp.get("name", ""),
        "input.zip_code": inp.get("zip_code", ""),
        "input.store_id": inp.get("store_id", ""),
        "final_price": rec.get("final_price", ""),
        "sku": rec.get("sku", ""),
        "product_id": rec.get("product_id", ""),
        "product_name": rec.get("product_name", ""),
        "upc": rec.get("upc", ""),
        "unit": rec.get("unit", ""),
        "zip_code": rec.get("zip_code", ""),
        "store_id": rec.get("store_id", ""),
        "brand_walmart_url": rec.get("brand_walmart_url", ""),
        "condition": rec.get("condition", ""),
        "pickup_address": rec.get("pickup_address", ""),
        "pickup_store_id": rec.get("pickup_store_id", ""),
        "pickup_zipcode": rec.get("pickup_zipcode", ""),
    }

    return out_row

def normalize_and_split_json(json_path: Path, out_dir: Optional[Path] = None) -> None:
    if out_dir is None:
        out_dir = json_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Normalizing JSON: {json_path}")

    base = json_path.stem
    good_path = out_dir / f"{base}_GOOD.csv"
    err_path = out_dir / f"{base}_ERRORS.csv"

    records = load_records(json_path)
    if not records:
        print("[INFO] No records found; nothing to write.")
        return

    good_count = 0
    err_count = 0

    with good_path.open("w", encoding="utf-8", newline="") as f_good, \
         err_path.open("w", encoding="utf-8", newline="") as f_err:

        good_writer = csv.DictWriter(f_good, fieldnames=OUTPUT_COLUMNS)
        good_writer.writeheader()

        err_writer = csv.DictWriter(f_err, fieldnames=OUTPUT_COLUMNS)
        err_writer.writeheader()

        for rec in records:
            row = normalize_record(rec)
            err_msg = str(row.get("error", "")).strip()
            err_code = str(row.get("error_code", "")).strip()
            is_error = bool(err_msg or err_code)

            if is_error:
                err_writer.writerow(row)
                err_count += 1
            else:
                good_writer.writerow(row)
                good_count += 1

    print(f"[INFO] GOOD rows  → {good_path} (rows: {good_count})")
    print(f"[INFO] ERROR rows → {err_path} (rows: {err_count})")

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description="Normalize Walmart BrightData JSON and split into GOOD / ERROR CSVs."
    )
    ap.add_argument(
        "--json",
        required=True,
        help="Path to BrightData Walmart JSON snapshot.",
    )
    ap.add_argument(
        "--out-dir",
        help="Optional output directory (default: same as JSON).",
    )

    args = ap.parse_args()
    json_path = Path(args.json)
    out_dir = Path(args.out_dir) if args.out_dir else None
    normalize_and_split_json(json_path, out_dir)

