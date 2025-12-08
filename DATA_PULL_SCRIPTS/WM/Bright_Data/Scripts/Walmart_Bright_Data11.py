#!/usr/bin/env python3

# Walmart_Bright_Data11.py
# Bright Data Walmart pipeline:
#  - reuse existing snapshot (env/CLI) OR
#  - build a fresh "data.csv" from a search-list file or CLI lists, then trigger snapshot
#  - poll until ready (bounded)
#  - download CSV/JSON
#  - normalize to compact schema (+PULL_DATE)
#  - optional Alaska-only CSV
#  - optional month-folder merger (JSON/NDJSON -> single CSV)
#
# Env vars honored (handy when called from R/reticulate):
#   BRIGHTDATA_API_KEY           (required)
#   BRIGHTDATA_DATASET_ID        (default "gd_m693oc1r1gebnayxq")
#   BRIGHTDATA_OUT_DIR           (root for Walmart output; YY_MM subfolder auto-created)
#   BRIGHTDATA_SNAPSHOT_ID       (reuse instead of trigger)
#   BRIGHTDATA_USE_LAST=1        (reuse last_snapshot.txt if present and no explicit id)
#   BRIGHTDATA_MAX_WAIT_MIN      (default 90)
#   BRIGHTDATA_POLL_EVERY_S      (default 30)
#   BRIGHTDATA_SEARCH_FILE       (path to WM_search_list.txt)
#   BRIGHTDATA_ALASKA_ONLY=1     (filter zip codes to 995–999)
#
# CLI examples:
#   python Walmart_Bright_Data11.py --snapshot-id sd_abcdef123
#   python Walmart_Bright_Data11.py --search-file "G:/.../WM_search_list.txt" --alaska-only
#   python Walmart_Bright_Data11.py --items "milk,bread,eggs" --zips "99503,99504" --max-wait 240 --poll-every 120

from __future__ import annotations

import os
import sys
import csv
import json
import gzip
import time
import re
import ast
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Iterable, Optional, List, Tuple
import requests

# ─────────────────────────────── Utility helpers ───────────────────────────────

def die(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)
    sys.exit(1)

def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ─────────────────────────────── Config (env + defaults) ───────────────────────

def _getenv(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()

def _getenv_int(name: str, default: int) -> int:
    v = _getenv(name, "")
    try:
        return int(v) if v else default
    except Exception:
        return default

API_KEY = _getenv("BRIGHTDATA_API_KEY")              # required, but validated later
DATASET_ID = _getenv("BRIGHTDATA_DATASET_ID", "gd_m693oc1r1gebnayxq")

# Walmart root path (where everything goes) + YY_MM subfolder
WALMART_ROOT_DEFAULT = (
    r"G:/.shortcut-targets-by-id/10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg/"
    r"Drones_MV/UAV Rural Essential Goods Delivery/FOOD_PRICING/Data_Scraping/Walmart"
)
OUT_ROOT = Path(_getenv("BRIGHTDATA_OUT_DIR", WALMART_ROOT_DEFAULT)).resolve()
RUN_SUBDIR = "WM_" + datetime.now().strftime("%y_%m")  # WM_YY_MM, e.g. WM_25_11
OUT_DIR = OUT_ROOT / RUN_SUBDIR

USE_LAST = _getenv("BRIGHTDATA_USE_LAST", "0") in {"1", "true", "TRUE", "yes", "YES"}

DEFAULT_MAX_WAIT_MIN = _getenv_int("BRIGHTDATA_MAX_WAIT_MIN", 90)
DEFAULT_POLL_EVERY_S = _getenv_int("BRIGHTDATA_POLL_EVERY_S", 30)

SEARCH_FILE_ENV = _getenv("BRIGHTDATA_SEARCH_FILE", "")
ALASKA_ONLY_ENV = _getenv("BRIGHTDATA_ALASKA_ONLY", "0") in {"1","true","TRUE","yes","YES"}

# ─────────────────────────────── HTTP/session constants ────────────────────────

BASE = "https://api.brightdata.com/datasets/v3"
SESSION = requests.Session()  # authorization header set later (after API_KEY validation)

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

def extract_name(row: Dict[str, Any]):
    return first(row.get("product_name"), row.get("title"), row.get("name"))

def extract_desc(row: Dict[str, Any]):
    return first(row.get("product_description"), row.get("description"), row.get("short_description"))

def extract_price(row: Dict[str, Any]):
    return first(
        row.get("price"),
        row.get("price_current"),
        row.get("price_num"),
        row.get("current_price"),
        row.get("final_price"),
        row.get("priceString"),
        row.get("price_text"),
    )

def extract_weight(row: Dict[str, Any]):
    return first(
        row.get("size"),
        row.get("size_text"),
        row.get("weight"),
        row.get("unit_size"),
        row.get("package_size"),
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
        row.get("gtin"),
    )

def extract_store_id(row: Dict[str, Any]) -> str:
    """
    Try to pull a store identifier from common Walmart-style fields.
    This is used for naming files like WM_<store_id>_MM_YY.csv.
    """
    raw = first(
        row.get("store_id"),
        row.get("storeId"),
        row.get("store_number"),
        row.get("storeNumber"),
        row.get("storeNo"),
        row.get("fulfillment_store_id"),
        row.get("seller_id"),
    )
    if not raw:
        return "UNKNOWN"
    # Make it filesystem-safe
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
    "product_id",
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

# ─────────────────────────────── Search-list ingestion ─────────────────────────

_LIST_RE = re.compile(r"^\s*(item_list|zip_codes)\s*=\s*(\[.*)$", flags=re.I)
_BRACKET_BLOCK_RE = re.compile(r"\[(?:.|\n)*?\]", flags=re.M)

def _parse_search_file(path: Path) -> Tuple[List[str], List[int]]:
    """
    Accepts your WM_search_list.txt:
      item_list = [ "milk", "bread", ... ]
      zip_codes = [ 99503, 99504, ... ]
    Returns (items, zips).
    """
    text = path.read_text(encoding="utf-8")
    items_src, zips_src = None, None

    # Find the first 'item_list = [ ... ]' block
    m_items_line = re.search(r"item_list\s*=\s*\[", text, flags=re.I)
    if m_items_line:
        m_items_block = _BRACKET_BLOCK_RE.search(text, pos=m_items_line.start())
        if m_items_block:
            items_src = m_items_block.group(0)

    # Find the first 'zip_codes = [ ... ]' block
    m_zips_line = re.search(r"zip_codes\s*=\s*\[", text, flags=re.I)
    if m_zips_line:
        m_zips_block = _BRACKET_BLOCK_RE.search(text, pos=m_zips_line.start())
        if m_zips_block:
            zips_src = m_zips_block.group(0)

    if items_src is None or zips_src is None:
        die(f"Could not parse item_list/zip_codes from: {path}")

    try:
        items = ast.literal_eval(items_src)
        zips = ast.literal_eval(zips_src)
    except Exception as e:
        die(f"Parse error in {path.name}: {e}")

    # Normalize
    items = [str(s).strip() for s in items if str(s).strip()]
    zips = [int(str(z).strip()) for z in zips if str(z).strip()]

    return items, zips

def _filter_alaska_zips(zips: List[int]) -> List[int]:
    return [z for z in zips if str(z).startswith(("995","996","997","998","999"))]

def _build_input_csv(items: List[str], zips: List[int], dest_csv: Path) -> Path:
    """
    Build a Bright Data input CSV for this Walmart dataset.

    The dataset expects columns:
      - keyword
      - store_id
      - zip_code

    We leave store_id blank and let Bright Data resolve stores by zip_code.
    """
    dest_csv.parent.mkdir(parents=True, exist_ok=True)
    with dest_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        # Match Bright Data's expected schema
        w.writerow(["keyword", "store_id", "zip_code"])
        for kw in items:
            for z in zips:
                w.writerow([kw, "", z])
    print(f"[{_ts()}] [OK] Built input CSV → {dest_csv} (rows: {len(items)*len(zips)})")
    return dest_csv

# ─────────────────────────────── Bright Data API helpers ───────────────────────

def trigger_snapshot(input_csv: Path) -> str:
    """
    Trigger a new snapshot using the provided input CSV.
    """
    if not DATASET_ID:
        die("Missing DATASET_ID. Set BRIGHTDATA_DATASET_ID or edit the script.")

    url = f"{BASE}/trigger"
    params = {
        "dataset_id": DATASET_ID,
        "include_errors": "true",
        "type": "run",
        
    }

    attempts = 3
    for attempt in range(1, attempts + 1):
        try:
            with input_csv.open("rb") as fh:
                files = {"data": ("data.csv", fh, "text/csv")}
                r = SESSION.post(url, params=params, files=files, timeout=120)
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
            print(
                f"[{_ts()}] [WARN] Trigger failed (attempt {attempt}/{attempts}) "
                f"status={code} body={body}"
            )
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
    try:
        r = SESSION.head(
            f"{BASE}/snapshot/{snapshot_id}/file.csv",
            allow_redirects=True,
            timeout=30,
        )
        return r.status_code == 200
    except Exception:
        return False

def get_snapshot_status(snapshot_id: str) -> str:
    """
    Returns: 'ready', 'running', 'failed', or 'error'.
    If HEAD for CSV returns 200, we treat as 'ready'.
    """
    url = f"{BASE}/snapshot/{snapshot_id}"
    try:
        r = SESSION.get(url, headers={"Accept":"application/json"}, timeout=60)
        try:
            payload = r.json()
        except Exception:
            # payload can be a data record; if CSV exists, call it ready
            return "ready" if _csv_available(snapshot_id) else "running"

        status = str(payload.get("status", "")).lower()
        if status in {"ready","running","failed","error"}:
            return status
        return "ready" if _csv_available(snapshot_id) else "running"
    except requests.HTTPError:
        return "error"
    except Exception:
        return "error"

def poll_until_ready(snapshot_id: str, max_wait_minutes: int, poll_every: int) -> None:
    deadline = time.time() + max_wait_minutes * 60
    last = ""
    while True:
        if time.time() > deadline:
            die("Timeout: snapshot did not become ready within the polling window.")
        status = get_snapshot_status(snapshot_id)
        if status != last:
            print(
                f"[{_ts()}] [POLL] snapshot={snapshot_id} status={status} "
                f"remaining={int((deadline-time.time())/60)}m"
            )
            last = status
        if status == "ready":
            return
        if status in {"failed","error"}:
            die(f"Snapshot failed with status={status}")
        time.sleep(poll_every)

# ─────────────────────────────── Download + normalize ─────────────────────────

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
    """
    Normalize the Bright Data CSV into:
      - One combined file for all *good* records: WM_ALL_MM_YY.csv
      - One file per store (only good records): WM_<store_id>_MM_YY.csv
      - One file for rows with Bright Data errors: WM_ERRORS_MM_YY.csv

    All files live in OUT_DIR = <Walmart root>/YY_MM.
    """

    out_dir.mkdir(parents=True, exist_ok=True)

    pull_date = datetime.now().strftime("%m-%d-%Y")
    month_tag = datetime.now().strftime("%m_%y")  # MM_YY, e.g. 11_25

    final_cols = FIELDNAMES + ["PULL_DATE"]

    all_path = out_dir / f"WM_ALL_{month_tag}.csv"
    err_path = out_dir / f"WM_ERRORS_{month_tag}.csv"

    # Per-store writers and file handles
    store_files: Dict[str, Any] = {}
    store_writers: Dict[str, csv.DictWriter] = {}

    good_count = 0
    err_count = 0

    with raw_csv_path.open("r", encoding="utf-8", newline="") as f_in, \
         all_path.open("w", encoding="utf-8", newline="") as f_all:

        reader = csv.DictReader(f_in)
        if not reader.fieldnames:
            die(f"No header row detected in raw CSV: {raw_csv_path}")

        all_writer = csv.DictWriter(f_all, fieldnames=final_cols)
        all_writer.writeheader()

        # Prepare error writer lazily (only if we actually hit any errors)
        err_writer: Optional[csv.DictWriter] = None
        err_file_handle = None

        for row in reader:
            # ----------------- classify row: error vs good -----------------
            has_error_field = "error" in reader.fieldnames or "error_code" in reader.fieldnames

            is_error = False
            if has_error_field:
                err_msg = str(row.get("error", "")).strip()
                err_code = str(row.get("error_code", "")).strip()
                if err_msg or err_code:
                    is_error = True

            if is_error:
                # Initialize error CSV on first error row
                if err_writer is None:
                    # Error CSV keeps all original columns + PULL_DATE
                    err_cols = list(reader.fieldnames) + ["PULL_DATE"]
                    err_file_handle = err_path.open("w", encoding="utf-8", newline="")
                    err_writer = csv.DictWriter(err_file_handle, fieldnames=err_cols)
                    err_writer.writeheader()

                row_with_date = dict(row)
                row_with_date["PULL_DATE"] = pull_date
                err_writer.writerow(row_with_date)
                err_count += 1
                continue

            # ----------------- good row → normalize -----------------
            norm = normalize_row(row)
            norm["PULL_DATE"] = pull_date

            out_row = {k: norm.get(k, "") for k in final_cols}

            # Write to combined file
            all_writer.writerow(out_row)
            good_count += 1

            # Per-store file
            store_id = extract_store_id(row)
            if store_id not in store_files:
                store_csv = out_dir / f"WM_{store_id}_{month_tag}.csv"
                fh = store_csv.open("w", encoding="utf-8", newline="")
                writer = csv.DictWriter(fh, fieldnames=final_cols)
                writer.writeheader()
                store_files[store_id] = fh
                store_writers[store_id] = writer

            store_writers[store_id].writerow(out_row)

    # Close all store files
    for fh in store_files.values():
        try:
            fh.close()
        except Exception:
            pass

    if err_count > 0 and err_path.exists():
        print(
            f"[{_ts()}] [OK] Saved error CSV → {err_path} "
            f"(rows: {err_count})"
        )
    else:
        print(f"[{_ts()}] [INFO] No Bright Data error rows found in {raw_csv_path}")

    print(
        f"[{_ts()}] [OK] Saved combined normalized CSV → {all_path} "
        f"(good rows: {good_count})"
    )
    print(
        f"[{_ts()}] [OK] Saved {len(store_writers)} store-level CSV files in {out_dir}"
    )

    return all_path


def alaska_filter(csv_path: Path, out_path: Optional[Path] = None) -> Optional[Path]:
    try:
        import pandas as pd
    except Exception:
        print(f"[{_ts()}] [WARN] pandas not installed; skipping Alaska-only export.")
        return None

    if out_path is None:
        out_path = csv_path.with_name(csv_path.stem + "_AK.csv")

    try:
        df = pd.read_csv(csv_path, dtype=str)
        if "zipcode" not in df.columns:
            print(f"[{_ts()}] [WARN] Alaska filter skipped: 'zipcode' missing.")
            return None
        df["zipcode"] = df["zipcode"].fillna("").astype(str)
        df_ak = df[df["zipcode"].str.startswith(("995","996","997","998","999"))]
        df_ak.to_csv(out_path, index=False)
        print(f"[{_ts()}] [OK] Saved Alaska-only CSV → {out_path} (rows: {len(df_ak)})")
        return out_path
    except Exception as e:
        print(f"[{_ts()}] [WARN] Alaska filter error: {e}")
        return None

# ─────────────────────────────── Month-folder merger ───────────────────────────

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

    json_files = sorted(
        [
            p for p in month_dir.rglob("*")
            if p.is_file() and p.name.lower().endswith((".json", ".json.gz"))
        ]
    )
    if not json_files:
        die(f"No JSON/NDJSON files found in: {month_dir}")

    out_csv = month_dir / f"{month_dir.name}_walmart_brightdata_normalized.csv"
    pull_date = datetime.now().strftime("%m-%d-%Y")
    final_cols = FIELDNAMES + ["PULL_DATE"]

    count_written = 0
    with out_csv.open("w", encoding="utf-8", newline="") as f_out:
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

# ─────────────────────────────── Orchestrator ─────────────────────────────────

def run_pipeline(
    existing_snapshot_id: Optional[str],
    max_wait_min: int,
    poll_every_s: int,
    search_file: Optional[Path],
    alaska_only: bool,
    items_cli: Optional[List[str]],
    zips_cli: Optional[List[int]],
) -> None:

    if not API_KEY:
        die("Set BRIGHTDATA_API_KEY (env) with your Bright Data API key.")
    SESSION.headers.update({"Authorization": f"Bearer {API_KEY}"})

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Reuse snapshot if supplied
    if existing_snapshot_id:
        snapshot_id = existing_snapshot_id
        print(f"[{_ts()}] [INFO] Using existing snapshot_id: {snapshot_id}")
    else:
        # Build or choose the input CSV
        if search_file is not None and search_file.exists():
            items, zips = _parse_search_file(search_file)
            if alaska_only:
                zips = _filter_alaska_zips(zips)
            if not items or not zips:
                die("No items or zip codes after parsing/filtering.")
            input_csv_path = OUT_DIR / "data_from_search_file.csv"
            _build_input_csv(items, zips, input_csv_path)
        elif items_cli or zips_cli:
            items = items_cli or []
            zips  = zips_cli or []
            if alaska_only:
                zips = _filter_alaska_zips(zips)
            if not items or not zips:
                die("Provide both --items and --zips when using CLI lists.")
            input_csv_path = OUT_DIR / "data_from_cli.csv"
            _build_input_csv(items, zips, input_csv_path)
        else:
            die(
                "No search-file provided and no --items/--zips specified. "
                "This script only builds its own CSV from a search list or CLI items/zips."
            )

        # Debug: confirm the input CSV we are about to send
        if not input_csv_path.exists():
            die(f"Internal error: input CSV does not exist at: {input_csv_path}")

        try:
            size_bytes = input_csv_path.stat().st_size
        except OSError:
            size_bytes = -1

        print(f"[{_ts()}] [DEBUG] Input CSV path: {input_csv_path.resolve()} (size={size_bytes} bytes)")

        try:
            with input_csv_path.open("r", encoding="utf-8", newline="") as f_dbg:
                print(f"[{_ts()}] [DEBUG] First 5 lines of input CSV:")
                for i, line in enumerate(f_dbg, start=1):
                    print(f"    {line.rstrip()}")
                    if i >= 5:
                        break
        except Exception as e:
            print(f"[{_ts()}] [WARN] Could not read preview of input CSV: {e}")

        snapshot_id = trigger_snapshot(input_csv_path)
        try:
            last_path = OUT_DIR / "last_snapshot.txt"
            last_path.write_text(snapshot_id, encoding="utf-8")
            print(f"[{_ts()}] [INFO] Saved snapshot id → {last_path.resolve()}")
        except Exception as e:
            print(f"[{_ts()}] [WARN] Could not save snapshot id: {e}")

    poll_until_ready(snapshot_id, max_wait_minutes=max_wait_min, poll_every=poll_every_s)
    raw_csv = download_outputs(snapshot_id, OUT_DIR)
    norm_csv = normalize_csv(raw_csv, OUT_DIR)
    alaska_filter(norm_csv, None)

def main():
    ap = argparse.ArgumentParser(
        description="Walmart Bright Data pipeline + snapshot-builder from search list"
    )
    ap.add_argument("--snapshot-id", help="Use an existing snapshot id (skip trigger).")
    ap.add_argument(
        "--month-dir",
        help="Merge all JSON/NDJSON in this folder to ONE normalized CSV.",
    )
    ap.add_argument(
        "--max-wait",
        type=int,
        default=DEFAULT_MAX_WAIT_MIN,
        help="Max wait minutes (default env/90).",
    )
    ap.add_argument(
        "--poll-every",
        type=int,
        default=DEFAULT_POLL_EVERY_S,
        help="Polling interval seconds (default env/30).",
    )

    # Fresh-snapshot build options
    ap.add_argument(
        "--search-file",
        help="Path to WM_search_list.txt containing item_list and zip_codes.",
    )
    ap.add_argument(
        "--alaska-only",
        action="store_true",
        help="Filter zip_codes to 995–999.",
    )
    ap.add_argument(
        "--items",
        help="Comma-separated keywords (alternative to --search-file).",
    )
    ap.add_argument(
        "--zips",
        help="Comma-separated zip codes (alternative to --search-file).",
    )

    args = ap.parse_args()

    # Month merger path
    if args.month_dir:
        merge_month_json_to_csv(Path(args.month_dir))
        return

    # Derive snapshot id precedence: CLI > ENV > last_snapshot.txt (if USE_LAST)
    snapshot_id = None
    if args.snapshot_id:
        snapshot_id = args.snapshot_id.strip()
    else:
        env_sid = _getenv("BRIGHTDATA_SNAPSHOT_ID", "")
        if env_sid:
            snapshot_id = env_sid
        elif USE_LAST:
            last_path = OUT_DIR / "last_snapshot.txt"
            if last_path.exists():
                snapshot_id = last_path.read_text(encoding="utf-8").strip()

    # Search-file from CLI or env
    search_file = None
    path_cli = args.search_file.strip() if args.search_file else ""
    path_env = SEARCH_FILE_ENV
    if path_cli:
        search_file = Path(path_cli)
    elif path_env:
        search_file = Path(path_env)

    alaska_only = args.alaska_only or ALASKA_ONLY_ENV

    items_cli = [s.strip() for s in args.items.split(",")] if args.items else None
    zips_cli = [int(s.strip()) for s in args.zips.split(",")] if args.zips else None

    run_pipeline(
        existing_snapshot_id=snapshot_id,
        max_wait_min=args.max_wait,
        poll_every_s=args.poll_every,
        search_file=search_file,
        alaska_only=alaska_only,
        items_cli=items_cli,
        zips_cli=zips_cli,
    )

if __name__ == "__main__":
    main()
