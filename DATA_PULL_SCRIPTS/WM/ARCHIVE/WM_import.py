#!/usr/bin/env python3

import requests
from pathlib import Path


url = "https://api.brightdata.com/datasets/v3/snapshot/sd_mjc2uwzoro56qxt8e?format=csv"

headers = {
    "Authorization": "Bearer 5470de471903618d2dd462633e022234e47d1a8257a1db9f615abda30cb047d3"
}

# ----- OUTPUT PATH (ONLY CHANGE) -----

out_dir = Path(
    r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg"
    r"\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING"
    r"\DATA\RAW_DATA\WM_RAW\WM_25_12"
)

out_dir.mkdir(parents=True, exist_ok=True)

out_file = out_dir / "WM_25_12.csv"

# ----- DOWNLOAD + VALIDATE DATASET -----

try:
    response = requests.get(
        url,
        headers=headers,
        timeout=900,
    )
    response.raise_for_status()

    text = response.text.strip()

    # ---- HARD GUARD: Bright Data status payload ----
    if text.startswith("{") and '"status"' in text:
        raise RuntimeError(
            f"Snapshot not deliverable.\nResponse:\n{text}"
        )

    # Write only real CSV data
    with open(out_file, "w", encoding="utf-8", newline="") as f:
        f.write(text)

    size_mb = out_file.stat().st_size / (1024 * 1024)
    print(f"Dataset written successfully ({size_mb:.2f} MB)")
    print(f"Saved to: {out_file}")

except Exception as e:
    print(f"WM_import FAILED: {e}")
    raise




