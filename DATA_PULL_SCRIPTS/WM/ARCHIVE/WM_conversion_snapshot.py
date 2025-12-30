import pandas as pd

path = r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA\RAW_DATA\WM_RAW\WM_25_12\sd_mjc2uwzoro56qxt8e.csv"

df = pd.read_csv(
    path,
    engine="python",          # more forgiving than C engine
    on_bad_lines="skip",      # skip malformed rows
)

print(df.shape)
print(df.head())
