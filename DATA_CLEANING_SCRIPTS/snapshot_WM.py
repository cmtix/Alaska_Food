#!/usr/bin/env python3
# 
# "PYTHON_EXE=C:\Users\vlcollier\env\Scripts\python.exe"

import json
import pandas as pd

# ---- EXACT JSON PATH (preserved) ----
json_path = r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA\RAW_DATA\WM_RAW\WM_25_11\sd_mi22bapp1tq3zv26sv.json"

# ---- CSV output path (same folder, same filename) ----
csv_path = r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA\RAW_DATA\WM_RAW\WM_25_11\sd_mi22bapp1tq3zv26sv.csv"

# ---- LOAD JSON ----
with open(json_path, "r", encoding="utf-8") as f:
    data = json.load(f)

# ---- NORMALIZE / FLATTEN ----
df = pd.json_normalize(data)

# ---- SAVE TO CSV ----
df.to_csv(csv_path, index=False)
