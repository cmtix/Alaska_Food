from pathlib import Path

RAW_ROOT = Path(r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA\RAW_DATA")

targets = {
    "ACC_2024_11": ["2024", "11", "24", "11"],
    "ACC_2025_11": ["2025", "11", "25", "11"],
    "FM_2025_11":  ["2025", "11", "25", "11"]
}

for label, parts in targets.items():
    print(f"\n===== Checking {label} =====")
    found = []
    for ext in ("*.json", "*.csv"):
        for f in RAW_ROOT.rglob(ext):
            name = f.name.lower()
            if any(p in name for p in parts):
                found.append(str(f))
    if found:
        print("FOUND RAW FILES:")
        for f in found:
            print("   ", f)
    else:
        print("NO RAW FILE FOUND matching month/year patterns")
