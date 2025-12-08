#!/usr/bin/env python3

import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from typing import Dict
from typing import Iterable
from typing import Optional
from typing import List

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
    city = first(row.get("store_city"), row.get("city"), row.get("storeCity"))
    zipcode = first(
        row.get("store_zip"),
        row.get("zip"),
        row.get("zipcode"),
        row.get("postal_code")
    )
    return address, city, zipcode

def extract_name(row: Dict[str, Any]):
    return first(row.get("product_name"), row.get("title"), row.get("name"))

def extract_desc(row: Dict[str, Any]):
    return first(
        row.get("product_description"),
        row.get("description"),
        row.get("short_description")
    )

def extract_price(row: Dict[str, Any]):
    return first(
        row.get("price"),
        row.get("price_current"),
        row.get("price_num"),
        row.get("current_price"),
        row.get("final_price"),
        row.get("priceString"),
        row.get("price_text")
    )

def extract_weight(row: Dict[str, Any]):
    return first(
        row.get("size"),
        row.get("size_text"),
        row.get("weight"),
        row.get("unit_size"),
        row.get("package_size")
    )

def extract_upc(row: Dict[str, Any]):
    return first(row.get("upc"), row.get("universal_product_code"), row.get("gtin"))

def extract_pid(row: Dict[str, Any]):
    return first(
        row.get("product_id"),
        row.get("item_id"),
        row.get("us_item_id"),
        row.get("id"),
        row.get("sku"),
        row.get("wupc"),
        row.get("gtin")
    )

def extract_store_id(row: Dict[str, Any]) -> str:
    raw = first(
        row.get("store_id"),
        row.get("storeId"),
        row.get("store_number"),
        row.get("storeNumber"),
        row.get("storeNo"),
        row.get("fulfillment_store_id"),
        row.get("seller_id")
    )
    if not raw:
        return "UNKNOWN"
    safe = re.sub(r"[^\w\-]", "_", str(raw))
    return safe or "UNKNOWN"

FIELDNAMES = [
    "address",
    "city",
    "zipcode",
    "product_name",
    "product_description",
    "product_price",
    "product_weight",
    "upc",
    "product_id"
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
        "product_id": extract_pid(row)
    }

def normalize_csv_once(raw_csv_path: Path, out_dir: Optional[Path] = None) -> Path:
    if out_dir is None:
        out_dir = raw_csv_path.parent

    out_dir.mkdir(parents=True, exist_ok=True)

    pull_date = datetime.now().strftime("%m-%d-%Y")
    month_tag = datetime.now().strftime("%m_%y")  # MM_YY, e.g. 11_25

    final_cols = FIELDNAMES + ["PULL_DATE"]

    all_path = out_dir / f"WM_ALL_{month_tag}.csv"
    err_path = out_dir / f"WM_ERRORS_{month_tag}.csv"

    store_files: Dict[str, Any] = {}
    store_writers: Dict[str, csv.DictWriter] = {}

    good_count = 0
    err_count = 0

    with raw_csv_path.open("r", encoding="utf-8", newline="") as f_in, \
         all_path.open("w", encoding="utf-8", newline="") as f_all:

        reader = csv.DictReader(f_in)
        if not reader.fieldnames:
            raise RuntimeError(f"No header row detected in raw CSV: {raw_csv_path}")

        all_writer = csv.DictWriter(f_all, fieldnames=final_cols)
        all_writer.writeheader()

        err_writer: Optional[csv.DictWriter] = None
        err_file_handle = None

        for row in reader:
            has_error_field = "error" in reader.fieldnames or "error_code" in reader.fieldnames

            is_error = False
            if has_error_field:
                err_msg = str(row.get("error", "")).strip()
                err_code = str(row.get("error_code", "")).strip()
                if err_msg or err_code:
                    is_error = True

            if is_error:
                if err_writer is None:
                    err_cols = list(reader.fieldnames) + ["PULL_DATE"]
                    err_file_handle = err_path.open("w", encoding="utf-8", newline="")
                    err_writer = csv.DictWriter(err_file_handle, fieldnames=err_cols)
                    err_writer.writeheader()

                row_with_date = dict(row)
                row_with_date["PULL_DATE"] = pull_date
                err_writer.writerow(row_with_date)
                err_count += 1
                continue

            norm = normalize_row(row)
            norm["PULL_DATE"] = pull_date

            out_row = {k: norm.get(k, "") for k in final_cols}

            all_writer.writerow(out_row)
            good_count += 1

            store_id = extract_store_id(row)
            if store_id not in store_files:
                store_csv = out_dir / f"WM_{store_id}_{month_tag}.csv"
                fh = store_csv.open("w", encoding="utf-8", newline="")
                writer = csv.DictWriter(fh, fieldnames=final_cols)
                writer.writeheader()
                store_files[store_id] = fh
                store_writers[store_id] = writer

            store_writers[store_id].writerow(out_row)

    for fh in store_files.values():
        try:
            fh.close()
        except Exception:
            pass

    if err_count > 0 and err_path.exists():
        print(f"[INFO] Saved error CSV → {err_path} (rows: {err_count})")
    else:
        print("[INFO] No Bright Data error rows found.")

    print(
        f"[INFO] Saved combined normalized CSV → {all_path} "
        f"(good rows: {good_count})"
    )
    print(
        f"[INFO] Saved {len(store_writers)} store-level CSV files in {out_dir}"
    )

    return all_path

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description="Normalize a single Walmart Bright Data CSV (no API call)."
    )
    ap.add_argument(
        "--raw-csv",
        required=True,
        help="Path to raw Bright Data CSV (e.g. walmart_brightdata_raw.csv)"
    )
    ap.add_argument(
        "--out-dir",
        help="Optional output directory (default: same as raw CSV)."
    )

    args = ap.parse_args()

    raw_path = Path(args.raw_csv)
    if args.out_dir:
        out_dir = Path(args.out_dir)
    else:
        out_dir = raw_path.parent

    normalize_csv_once(raw_path, out_dir)

