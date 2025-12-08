#!/usr/bin/env python3
"""
Prebuild missing store-month CSVs for ACC, FM, and WM.

Fixes:
- ACC: merge all CSVs in ACC_RAW/ACC_YY_MM -> CLEANED_DATA/ACC_YY_MM.csv
- FM: flatten JSON in FM_RAW/FM_YY_MM -> CLEANED_DATA/FM_YY_MM.csv
- WM: merge CSVs in WM_RAW/WM_YY_MM -> CLEANED_DATA/WM_YY_MM.csv

CS is not touched.

This version contains NO unicode characters (→) because Windows CP1252 cannot print them.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
import re
from typing import List, Dict, Tuple, Set

# ---------------------------------------------------------------
# PATH CONFIG
# ---------------------------------------------------------------
RAW_ROOT = Path(
    r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg"
    r"\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA\RAW_DATA"
)

CLEAN_ROOT = Path(
    r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg"
    r"\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA\CLEANED_DATA"
)

ACC_ROOT = RAW_ROOT / "ACC_RAW"
FM_ROOT = RAW_ROOT / "FM_RAW"
WM_ROOT = RAW_ROOT / "WM_RAW"

ACC_RE = re.compile(r"^ACC_(\d{2})[_-](\d{2})$", re.IGNORECASE)
FM_RE  = re.compile(r"^FM_(\d{2})[_-](\d{2})$", re.IGNORECASE)
WM_RE  = re.compile(r"^WM_(\d{2})[_-](\d{2})$", re.IGNORECASE)


# ---------------------------------------------------------------
# UTILITIES
# ---------------------------------------------------------------
def csv_has_data(path: Path) -> bool:
    """Return True if CSV has >0 data rows."""
    try:
        with path.open("r", encoding="utf-8") as f:
            next(f, None)  # skip header
            for line in f:
                if line.strip():
                    return True
    except Exception:
        return False
    return False


def get_existing_cleaned_months() -> Set[Tuple[str, str, str]]:
    """Return set of (STORE, YY, MM) for non-empty CSVs in CLEANED_DATA."""
    keys = set()
    for csv_file in CLEAN_ROOT.glob("*.csv"):
        parts = csv_file.stem.split("_")
        if len(parts) < 3:
            continue
        store, yy, mm = parts[0], parts[1], parts[2]
        if yy.isdigit() and mm.isdigit() and csv_has_data(csv_file):
            keys.add((store.upper(), yy, mm))
    return keys


# ---------------------------------------------------------------
# MERGE CSV FOLDERS
# ---------------------------------------------------------------
def merge_csv_folder(folder: Path, out_path: Path) -> None:
    """Merge all CSVs in folder and write as out_path."""
    csv_files = list(folder.glob("*.csv"))
    if not csv_files:
        print("[WARN] No CSV files in folder:", folder)
        return

    all_rows: List[Dict[str, str]] = []
    fields = set()

    for csv_file in sorted(csv_files):
        print("    reading CSV:", csv_file.name)
        with csv_file.open("r", encoding="utf-8", newline="") as f:
            rdr = csv.DictReader(f)
            if rdr.fieldnames:
                fields.update(rdr.fieldnames)
            for row in rdr:
                all_rows.append(row)

    if not all_rows:
        print("[WARN] No rows from CSVs in:", folder)
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted(fields)

    print("    writing merged CSV:", out_path, f"({len(all_rows)} rows)")
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in all_rows:
            w.writerow({col: r.get(col, "") for col in fields})


# ---------------------------------------------------------------
# FLATTEN JSON FOLDER
# ---------------------------------------------------------------
def json_folder_to_csv(folder: Path, out_path: Path) -> None:
    """Flatten JSON files into CSV."""
    json_files = list(folder.glob("*.json"))
    if not json_files:
        print("[WARN] No JSON files in folder:", folder)
        return

    all_rows = []
    fields = set()

    for jf in sorted(json_files):
        print("    reading JSON:", jf.name)
        with jf.open("r", encoding="utf-8") as f:
            data = json.load(f)

        rows = []
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            for k in ("data", "rows", "items", "records"):
                if isinstance(data.get(k), list):
                    rows = data[k]
                    break

        for r in rows:
            if isinstance(r, dict):
                fields.update(r.keys())
                all_rows.append({k: "" if v is None else str(v) for k, v in r.items()})

    if not all_rows:
        print("[WARN] No rows from JSON in:", folder)
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted(fields)

    print("    writing JSON->CSV:", out_path, f"({len(all_rows)} rows)")
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in all_rows:
            w.writerow({col: r.get(col, "") for col in fields})


# ---------------------------------------------------------------
# BUILDERS FOR EACH STORE
# ---------------------------------------------------------------
def build_missing_acc(existing):
    if not ACC_ROOT.exists():
        print("[ACC][SKIP] ACC_RAW folder missing.")
        return

    for folder in ACC_ROOT.iterdir():
        if not folder.is_dir():
            continue
        m = ACC_RE.match(folder.name)
        if not m:
            continue

        yy, mm = m.group(1), m.group(2)
        key = ("ACC", yy, mm)
        out_path = CLEAN_ROOT / f"ACC_{yy}_{mm}.csv"

        if key in existing and csv_has_data(out_path):
            continue

        print("[ACC][BUILD] Month folder", folder.name, "->", out_path.name)
        merge_csv_folder(folder, out_path)


def build_missing_fm(existing):
    if not FM_ROOT.exists():
        print("[FM][SKIP] FM_RAW folder missing.")
        return

    for folder in FM_ROOT.iterdir():
        if not folder.is_dir():
            continue
        m = FM_RE.match(folder.name)
        if not m:
            continue

        yy, mm = m.group(1), m.group(2)
        key = ("FM", yy, mm)
        out_path = CLEAN_ROOT / f"FM_{yy}_{mm}.csv"

        if key in existing and csv_has_data(out_path):
            continue

        print("[FM][BUILD] Month folder", folder.name, "->", out_path.name)
        json_folder_to_csv(folder, out_path)


def build_missing_wm(existing):
    if not WM_ROOT.exists():
        print("[WM][SKIP] WM_RAW folder missing.")
        return

    for folder in WM_ROOT.iterdir():
        if not folder.is_dir():
            continue
        m = WM_RE.match(folder.name)
        if not m:
            continue

        yy, mm = m.group(1), m.group(2)
        key = ("WM", yy, mm)
        out_path = CLEAN_ROOT / f"WM_{yy}_{mm}.csv"

        if key in existing and csv_has_data(out_path):
            continue

        print("[WM][BUILD] Month folder", folder.name, "->", out_path.name)
        merge_csv_folder(folder, out_path)


# ---------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------
def main():
    print("[PREBUILD] Starting ACC/FM/WM month creation")
    print("           RAW_ROOT   =", RAW_ROOT)
    print("           CLEAN_ROOT =", CLEAN_ROOT)

    existing = get_existing_cleaned_months()
    print("[PREBUILD] Found", len(existing), "existing non-empty months.")

    build_missing_acc(existing)
    build_missing_fm(existing)
    build_missing_wm(existing)

    print("[PREBUILD] Done prebuilding missing months.")


if __name__ == "__main__":
    main()
