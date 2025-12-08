#!/usr/bin/env python3

import csv
from pathlib import Path
from typing import List, Dict

# ---- CONFIG: adjust ONLY if your paths change ----
ACC_RAW_ROOT = Path(
    r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA\RAW_DATA\ACC_RAW"
)

MONTH_FOLDERS = [
    "ACC_24_11",
    "ACC_25_11",
]


def merge_month_folder(month_folder: Path) -> None:
    if not month_folder.exists():
        print(f"[WARN] Month folder does not exist: {month_folder}")
        return

    # All CSVs except any existing *_merged.csv to avoid double-counting
    csv_files: List[Path] = [
        p for p in month_folder.glob("*.csv")
        if "merged" not in p.name.lower()
    ]

    if not csv_files:
        print(f"[WARN] No CSV files found in {month_folder}")
        return

    print(f"[INFO] Merging {len(csv_files)} CSV files in {month_folder.name}")

    all_rows: List[Dict[str, str]] = []
    fieldnames_set = set()

    # Read all rows and collect unified fieldnames
    for f in sorted(csv_files):
        print(f"   - reading {f.name}")
        with f.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            # Update fieldnames union
            fieldnames_set.update(reader.fieldnames or [])
            for row in reader:
                all_rows.append(row)

    if not all_rows:
        print(f"[WARN] No data rows found in {month_folder}")
        return

    # Create a stable fieldname order (sorted for reproducibility)
    fieldnames = sorted(fieldnames_set)

    out_name = f"{month_folder.name}_merged.csv"
    out_path = month_folder / out_name

    print(f"[INFO] Writing merged file: {out_path} ({len(all_rows)} rows)")

    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in all_rows:
            # Ensure all columns present
            out_row = {col: row.get(col, "") for col in fieldnames}
            writer.writerow(out_row)

    print(f"[DONE] {out_path} written.")


def main() -> None:
    print(f"[START] ACC merge for November months under: {ACC_RAW_ROOT}")

    for folder_name in MONTH_FOLDERS:
        month_folder = ACC_RAW_ROOT / folder_name
        merge_month_folder(month_folder)

    print("[DONE] ACC merge script complete.")


if __name__ == "__main__":
    main()
