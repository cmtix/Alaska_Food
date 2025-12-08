#!/usr/bin/env python3

from __future__ import annotations

import json
import re
from pathlib import Path


# ===== ROOTS =====

ROOT_DIR = Path(
    r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA\RAW_DATA"
)

FM_ROOT = ROOT_DIR / "FM_RAW"
WM_ROOT = ROOT_DIR / "WM_RAW"


# =========================
# FM SECTION (folders + files)
# =========================

FM_PAT_YM = re.compile(
    r"^FM_(\d{4})_(\d{2})(?:\.(json|csv))?$",
    re.IGNORECASE,
)

FM_PAT_YMD = re.compile(
    r"^FM_(\d{4})-(\d{2})-(\d{2})(?:\.(json|csv))?$",
    re.IGNORECASE,
)


def normalize_fm_name(path: Path) -> str | None:
    name = path.name

    m1 = FM_PAT_YM.match(name)
    if m1 is not None:
        yyyy = m1.group(1)
        mm = m1.group(2)
        yy = yyyy[-2:]
        ext = path.suffix
        return f"FM_{yy}_{mm}{ext}"

    m2 = FM_PAT_YMD.match(name)
    if m2 is not None:
        yyyy = m2.group(1)
        mm = m2.group(2)
        yy = yyyy[-2:]
        ext = path.suffix
        return f"FM_{yy}_{mm}{ext}"

    return None


def rename_fm(root: Path) -> None:
    if not root.exists():
        print(f"[WARN] FM root does not exist: {root}")
        return

    all_paths = list(root.rglob("*"))
    all_paths_sorted = sorted(
        all_paths,
        key=lambda p: len(p.parts),
        reverse=True,
    )

    for p in all_paths_sorted:
        new_name = normalize_fm_name(p)
        if new_name is None:
            continue

        new_path = p.with_name(new_name)

        if new_path.exists():
            print(f"[SKIP] FM would overwrite: {new_path}")
            continue

        print(f"[FM RENAME] {p} -> {new_path}")
        p.rename(new_path)


# =========================
# WM SECTION (files only)
# =========================

# We want:
#   CSV:  WM_YY_MM.csv
#   JSON: WM_YY_MM_<store_id>.json

STORE_KEY_CANDIDATES = [
    "store_id",
    "storeId",
    "storeID",
    "store_number",
    "storeNumber",
    "store",
]


def sanitize_store_id(store_id: str) -> str:
    return re.sub(
        r"[^0-9A-Za-z_-]+",
        "",
        store_id,
    )


def _search_store_id_in_obj(obj) -> str | None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in STORE_KEY_CANDIDATES:
                if value is not None:
                    return str(value)

        for key, value in obj.items():
            key_lower = key.lower()
            if "store" in key_lower and "id" in key_lower:
                if value is not None:
                    return str(value)

        for value in obj.values():
            found = _search_store_id_in_obj(value)
            if found is not None:
                return found

    if isinstance(obj, list):
        for item in obj:
            found = _search_store_id_in_obj(item)
            if found is not None:
                return found

    return None


def get_store_id_from_json(path: Path) -> str | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[WM WARN] Could not read JSON {path}: {e}")
        return None

    store_id = _search_store_id_in_obj(data)
    if store_id is None:
        return None

    store_id_clean = sanitize_store_id(store_id)
    if store_id_clean == "":
        return None

    return store_id_clean


def extract_wm_yy_mm(name: str) -> tuple[str | None, str | None]:
    """
    Extract (YY, MM) from a WM-related filename.

    Strategy:
      1) Look for YYYY[-_]MM -> use last two digits of year.
      2) If not found, look for any NN_MM pattern -> treat as YY_MM.
    """
    m1 = re.search(r"(\d{4})[-_](\d{2})", name)
    if m1 is not None:
        yyyy = m1.group(1)
        mm = m1.group(2)
        yy = yyyy[-2:]
        return yy, mm

    m2 = re.search(r"(\d{2})_(\d{2})", name)
    if m2 is not None:
        yy = m2.group(1)
        mm = m2.group(2)
        return yy, mm

    return None, None


def normalize_wm_csv(path: Path) -> str | None:
    name = path.name

    m_norm = re.match(r"^WM_(\d{2})_(\d{2})\.csv$", name, re.IGNORECASE)
    if m_norm is not None:
        return None

    yy, mm = extract_wm_yy_mm(name)
    if yy is None or mm is None:
        print(f"[WM DEBUG] CSV has no usable YY_MM pattern, skipping: {name}")
        return None

    new_name = f"WM_{yy}_{mm}{path.suffix}"
    return new_name


def normalize_wm_json(path: Path) -> str | None:
    name = path.name

    m_norm = re.match(r"^WM_(\d{2})_(\d{2})_.+\.json$", name, re.IGNORECASE)
    if m_norm is not None:
        return None

    yy, mm = extract_wm_yy_mm(name)
    if yy is None or mm is None:
        print(f"[WM DEBUG] JSON has no usable YY_MM pattern, skipping: {name}")
        return None

    store_id = get_store_id_from_json(path)
    if store_id is None:
        print(f"[WM DEBUG] No store_id found in JSON, skipping: {name}")
        return None

    new_name = f"WM_{yy}_{mm}_{store_id}{path.suffix}"
    return new_name


def rename_wm(root: Path) -> None:
    if not root.exists():
        print(f"[WARN] WM root does not exist: {root}")
        return

    for p in root.rglob("*"):
        if not p.is_file():
            continue

        suffix_lower = p.suffix.lower()
        new_name = None

        if suffix_lower == ".csv":
            new_name = normalize_wm_csv(p)
        elif suffix_lower == ".json":
            new_name = normalize_wm_json(p)

        if new_name is None:
            continue

        new_path = p.with_name(new_name)

        if new_path.exists():
            print(f"[SKIP] WM would overwrite: {new_path}")
            continue

        print(f"[WM RENAME] {p} -> {new_path}")
        p.rename(new_path)


def main() -> None:
    print(f"[INFO] FM root: {FM_ROOT}")
    rename_fm(FM_ROOT)

    print(f"[INFO] WM root: {WM_ROOT}")
    rename_wm(WM_ROOT)


if __name__ == "__main__":
    main()


from pathlib import Path
import re

WM_ROOT = Path(
    r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA\RAW_DATA\WM_RAW"
)

# Pattern: WM_25_11_4359.json → (25, 11)
PAT = re.compile(r"^WM_(\d{2})_(\d{2})_[^/\\]+\.json$", re.IGNORECASE)


def remove_storeid_suffix(root: Path):
    for p in root.rglob("*.json"):
        m = PAT.match(p.name)
        if m is None:
            continue

        yy = m.group(1)
        mm = m.group(2)

        new_name = f"WM_{yy}_{mm}.json"
        new_path = p.with_name(new_name)

        if new_path.exists():
            print(f"[SKIP] Would overwrite: {new_path}")
            continue

        print(f"[RENAME] {p.name} -> {new_name}")
        p.rename(new_path)


if __name__ == "__main__":
    remove_storeid_suffix(WM_ROOT)
