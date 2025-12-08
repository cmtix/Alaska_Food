#!/usr/bin/env python3
"""
ensure_cleaned_store_months.py

Detects RAW files (json/csv) that do not yet have a corresponding
cleaned STORE_YY_MM.csv, loads & normalizes them, and writes the
cleaned file into CLEAN_ROOT before the normal runners are called.
"""

from __future__ import annotations

import json
import csv
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Any


# --------------------------------------------------------------------
# Store folder → store code map
# --------------------------------------------------------------------
STORE_FOLDER_MAP = {
    "ACC_RAW": "ACC",
    "CS_RAW": "CS",
    "FM_RAW": "FM",
    "WM_RAW": "WM",
}


def log(line: str, log_path: Path) -> None:
    """Write to both STDOUT and the central log."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"{ts} {line}"
    print(msg)
    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        # Don't crash if logging fails
        pass


# --------------------------------------------------------------------
# Infer store code from path
# --------------------------------------------------------------------
def infer_store_from_path(path: Path) -> str:
    parts = [p.lower() for p in path.parts]
    for folder, code in STORE_FOLDER_MAP.items():
        if folder.lower() in parts:
            return code
    # fallback: try file prefix
    stem = path.stem
    token = stem.split("_")[0]
    return token.upper()


# --------------------------------------------------------------------
# Determine (yy, mm) from a raw file
# --------------------------------------------------------------------
def peek_month_year_from_raw(path: Path) -> Tuple[str, str]:
    """
    Determine (yy, mm) from:
      1. Folder name (e.g. ACC_24_11, FM_25_11)
      2. File name (e.g. ACC_185_11_24.csv → 11_24)
      3. File contents (YEAR/MONTH or PULL_DATE)
    """

    # ----- 1. FOLDER NAME (primary method for your layout) ----------
    for part in reversed(path.parts):
        # match e.g. ACC_24_11, FM_25_11, CS_23-02, etc.
        m = re.search(r"(\d{2})[_\-](\d{2})$", part)
        if m:
            yy, mm = m.group(1), m.group(2)
            if 1 <= int(mm) <= 12:
                return yy, mm

    # ----- 2. FILE NAME (fallback) ---------------------------------
    # e.g. ACC_185_11_24.csv → last match is 11_24 (mm=11, yy=24)
    pairs = re.findall(r"(\d{2})[_\-](\d{2})", path.stem)
    if pairs:
        mm, yy = pairs[-1]
        if 1 <= int(mm) <= 12:
            return yy, mm

    # ----- 3. CONTENT (last resort) --------------------------------
    first_row: Dict[str, Any] = {}

    if path.suffix.lower() == ".json":
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list) and data:
            first_row = data[0]
        elif isinstance(data, dict):
            for key in ("data", "rows", "items", "records"):
                if key in data and isinstance(data[key], list) and data[key]:
                    first_row = data[key][0]
                    break
    else:
        # CSV
        with path.open("r", encoding="utf-8", newline="") as f:
            rdr = csv.DictReader(f)
            try:
                first_row = next(rdr)
            except StopIteration:
                first_row = {}

    # YEAR / MONTH fields
    if "YEAR" in first_row and "MONTH" in first_row:
        yy = str(first_row["YEAR"]).strip()[-2:]
        mm = f"{int(first_row['MONTH']):02d}"
        return yy, mm

    # PULL_DATE fallback
    if "PULL_DATE" in first_row:
        pd = str(first_row["PULL_DATE"]).strip()
        for fmt in ("%d-%m-%y", "%m-%d-%y", "%Y-%m-%d", "%m/%d/%Y"):
            try:
                dt = datetime.strptime(pd, fmt)
                return dt.strftime("%y"), dt.strftime("%m")
            except ValueError:
                continue

    raise ValueError(f"No usable YEAR/MONTH or PULL_DATE in {path}")


# --------------------------------------------------------------------
# Read raw structures
# --------------------------------------------------------------------
def load_rows_from_raw(path: Path) -> List[Dict[str, Any]]:
    # JSON
    if path.suffix.lower() == ".json":
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            for key in ["data", "rows", "items", "records"]:
                if key in data and isinstance(data[key], list):
                    return data[key]
            raise ValueError(f"No rows found in JSON {path}")
        elif isinstance(data, list):
            return data
        else:
            raise ValueError(f"Unexpected JSON structure in {path}")

    # CSV
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            rows.append(r)
    return rows


# --------------------------------------------------------------------
# MASTER schema fields (mirror central_runner)
# --------------------------------------------------------------------
MASTER_COLS = [
    "PULL_DATE",
    "HOME_STORE_NAME",
    "STORE_ID",
    "STORE_NAME",
    "ADDRESS",
    "CITY",
    "STATE",
    "ZIP",
    "STORE_REGION",
    "LONGITUDE",
    "LATITUDE",
    "PRIMARY_STORE_KEY",
    "PRIMARY_KEY",
    "UPC",
    "SKU",
    "SKU_DESCRIPTION",
    "SIZE",
    "PRICE",
    "INTERNAL_PROD_CODE",
    "MONTH",
    "YEAR",
    "MONTH_YEAR",
    "SALES_TAX_CITY_FLAG",
    "SALES_TAX_FED_FLAG",
    "SALES_TAX_MUNI_FLAG",
    "SALES_TAX_FLAT_FLAG",
    "SNAP_FLAG",
    "ITEM_WEIGHT",
    "FREIGHT_TYPE",
]


# --------------------------------------------------------------------
# Normalize raw → MASTER schema
# --------------------------------------------------------------------
def normalize_rows_to_master(
    rows: List[Dict[str, Any]],
    store_code: str,
    yy: str,
    mm: str,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    # choose pull date mid-month convention
    pull_date = f"{yy}-{mm}-15"

    for raw in rows:
        new_r = {col: "" for col in MASTER_COLS}

        # copy any matching fields (case-insensitive)
        for k, v in raw.items():
            k2 = k.strip().upper()
            if k2 in MASTER_COLS:
                new_r[k2] = v

        new_r["HOME_STORE_NAME"] = store_code
        new_r["PULL_DATE"] = pull_date

        # MONTH / YEAR
        new_r["MONTH"] = mm
        new_r["YEAR"] = f"20{yy}"
        new_r["MONTH_YEAR"] = f"{yy}-{mm}"

        out.append(new_r)

    return out


# --------------------------------------------------------------------
# Write cleaned CSV
# --------------------------------------------------------------------
def write_cleaned_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MASTER_COLS)
        w.writeheader()
        for r in rows:
            w.writerow(r)


# --------------------------------------------------------------------
# MAIN ENTRY
# --------------------------------------------------------------------
def ensure_cleaned_for_all_raw(
    RAW_ROOT: Path,
    CLEAN_ROOT: Path,
    LOG_PATH: Path,
) -> None:
    """
    1. Build set of (store, yy, mm) that already exist in CLEANED_DATA
       as STORE_YY_MM.csv.
    2. Scan RAW_ROOT/*_RAW recursively for *.json / *.csv and group
       them by (store, yy, mm).
    3. For each group that does NOT yet have a cleaned file, load ALL
       of the group's files, normalize, and write a single merged
       STORE_YY_MM.csv.
    """

    log("[PRECHECK] scanning RAW folders", LOG_PATH)

    # --- 1. Existing cleaned keys ---------------------------------
    existing_keys = set()
    for csv_path in CLEAN_ROOT.glob("*.csv"):
        stem = csv_path.stem
        parts = stem.split("_")
        if len(parts) < 3 or not parts[1].isdigit() or not parts[2].isdigit():
            continue

        # Only treat as "existing" if there is at least one data row
        has_data = False
        try:
            with csv_path.open("r", encoding="utf-8") as f:
                # header
                _header = next(f, None)
                # first data row
                first_data = next(f, None)
                if first_data is not None and first_data.strip():
                    has_data = True
        except Exception:
            has_data = False

        if not has_data:
            # Leave this store-month out of existing_keys so it will be rebuilt
            continue

        store = parts[0].upper()
        yy = parts[1]
        mm = parts[2]
        existing_keys.add((store, yy, mm))


    # --- 2. Group RAW files by (store, yy, mm) ---------------------
    groups: Dict[Tuple[str, str, str], List[Path]] = {}

    # Scan ACC_RAW, CS_RAW, FM_RAW, WM_RAW recursively
    for store_root in RAW_ROOT.glob("*_RAW"):
        for ext in ("*.json", "*.csv"):
            for raw_path in store_root.rglob(ext):
                try:
                    store_code = infer_store_from_path(raw_path)
                    yy, mm = peek_month_year_from_raw(raw_path)
                    key = (store_code.upper(), yy, mm)
                except Exception as e:
                    log(
                        f"[PRECHECK][WARN] skipping {raw_path} "
                        f"(cannot infer store/month): {e}",
                        LOG_PATH,
                    )
                    continue

                groups.setdefault(key, []).append(raw_path)

    # --- 3. For each group, create merged cleaned file if missing ---
    for (store_code, yy, mm), file_list in groups.items():
        if (store_code, yy, mm) in existing_keys:
            continue  # already have STORE_YY_MM.csv

        target_name = f"{store_code}_{yy}_{mm}.csv"
        out_path = CLEAN_ROOT / target_name

        log(
            f"[PRECHECK] Creating merged cleaned file {target_name} "
            f"from {len(file_list)} raw file(s)",
            LOG_PATH,
        )

        all_rows: List[Dict[str, Any]] = []
        for raw_path in file_list:
            try:
                raw_rows = load_rows_from_raw(raw_path)
                norm_rows = normalize_rows_to_master(
                    rows=raw_rows,
                    store_code=store_code,
                    yy=yy,
                    mm=mm,
                )
                all_rows.extend(norm_rows)
            except Exception as e:
                log(
                    f"[PRECHECK][ERROR] Failed processing {raw_path}: {e}",
                    LOG_PATH,
                )

        if not all_rows:
            log(
                f"[PRECHECK][WARN] No rows produced for {target_name}; "
                f"skipping write.",
                LOG_PATH,
            )
            continue

        write_cleaned_csv(out_path, all_rows)
        existing_keys.add((store_code, yy, mm))

    log("[PRECHECK] complete", LOG_PATH)
