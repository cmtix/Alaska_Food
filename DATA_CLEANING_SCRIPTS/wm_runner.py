#!/usr/bin/env python3

import re
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

from central_runner import read_csv_rows
from central_runner import read_json_rows
from central_runner import write_csv
from central_runner import upper_headers
from central_runner import ensure_pull_date
from central_runner import pull_date_from_folder_tag
from central_runner import read_crosswalk_generic
from central_runner import finalize_common_fields
from central_runner import log_line

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
    "FREIGHT_TYPE"
]

def _p(s: str) -> re.Pattern:
    return re.compile(s, re.IGNORECASE)

WM_MAP = {}
WM_MAP["ZIP"] = _p(r"^ZIP$|^request_parameters\.customer_zipcode$|^Zip_Code$")
WM_MAP["SKU_DESCRIPTION"] = _p(r"^SKU_DESCRIPTION$|^Product_Title$|^title$|^search_results\.product\.title$|^product\.title$")
WM_MAP["SKU"] = _p(r"^SKU$|^item_id$|^search_results\.product\.item_id$|^Item_ID$|^product\.item_id$")
WM_MAP["PRICE"] = _p(r"^PRICE$|^price$|^Primary_Price$|^search_results\.offers\.primary\.price$|^offers\.primary\.price$")
WM_MAP["PULL_DATE"] = _p(r"^PULL_DATE$|^pull_date$|^Pull_Date$|^Date$")
WM_MAP["UPC"] = _p(r"^UPC$|^upc$")

FOLDER_TAG = re.compile(r"^WM_(\d{2})_(\d{2})$", re.IGNORECASE)

def choose_source_file(folder: Path) -> Optional[Path]:
    cands = []
    for p in folder.iterdir():
        if p.is_file():
            if p.suffix.lower() in [".csv", ".json"]:
                cands.append(p)
    if len(cands) == 0:
        return None
    cands.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return cands[0]

def yy_mm_from_name(name: str) -> Optional[str]:
    m = FOLDER_TAG.match(name)
    if m is None:
        return None
    return f"{m.group(1)}_{m.group(2)}"

def reduce_with_map(rows: List[Dict[str, Any]], mapping: Dict[str, re.Pattern]) -> List[Dict[str, Any]]:
    if len(rows) == 0:
        return rows
    headers = list(rows[0].keys())
    picked = {}
    for tgt, patt in mapping.items():
        src = None
        for h in headers:
            if patt.match(h):
                src = h
                break
        picked[tgt] = src
    out = []
    for r in rows:
        new_r = {}
        for k in MASTER_COLS:
            new_r[k] = ""
        new_r["PULL_DATE"] = r.get("PULL_DATE", "")
        new_r["HOME_STORE_NAME"] = "WM"


        for tgt, src in picked.items():
            if tgt == "HOME_STORE_NAME":
                continue
            if tgt == "PULL_DATE":
                continue
            if src is not None:
                val = r.get(src, "")
                new_r[tgt] = "" if val is None else str(val)
        out.append(new_r)
    return out

def process_subfolder(sub: Path,
                      mapping: Dict[str, re.Pattern],
                      crosswalk: Dict[Tuple[str, str], Dict[str, str]],
                      monthly: Dict[Tuple[str, str], List[Dict[str, Any]]],
                      log_path: Path) -> Optional[str]:
    tag = sub.name
    yy_mm = yy_mm_from_name(tag)
    if yy_mm is None:
        log_line(log_path, "[WM][SKIP] " + tag)
        return None
    src = choose_source_file(sub)
    if src is None:
        log_line(log_path, "[WM][SKIP] No file in " + tag)
        return yy_mm
    if src.suffix.lower() == ".csv":
        rows = read_csv_rows(src)
    else:
        rows = read_json_rows(src)
    rows = upper_headers(rows)
    override_pd = pull_date_from_folder_tag(tag)
    rows = ensure_pull_date(rows, src, override_pd)
    for r in rows:
        if not r.get("HOME_STORE_NAME"):
            r["HOME_STORE_NAME"] = "WM"
    mapped = reduce_with_map(rows, mapping)
    for r in mapped:
        finalize_common_fields(r, list(rows[0].keys()), "WM", crosswalk, "AK")
    key = ("WM", yy_mm)
    if key not in monthly:
        monthly[key] = []
    monthly[key].extend(mapped)
    log_line(log_path, f"[WM][ACCUM] {tag}: +{len(mapped)}")
    return yy_mm

def run_wm(log_root: Path,
           raw_root: Path,
           clean_root: Path,
           crosswalk_path: Path,
           central_log_path: Path) -> None:
    wm_root = raw_root / "WM_RAW"
    if not wm_root.exists():
        log_line(central_log_path, "[WM][SKIP] Missing WM_RAW")
        return
    crosswalk = read_crosswalk_generic(crosswalk_path, central_log_path)
    monthly = {}
    for sub in wm_root.iterdir():
        if not sub.is_dir():
            continue
        yy_mm = process_subfolder(sub, WM_MAP, crosswalk, monthly, central_log_path)
        if yy_mm is None:
            continue
        key = ("WM", yy_mm)
        rows = monthly.get(key, [])
        out_path = clean_root / f"WM_{yy_mm}.csv"
        write_csv(out_path, rows, MASTER_COLS)
        log_line(central_log_path, f"[WM][WRITE] {out_path} ({len(rows)})")
