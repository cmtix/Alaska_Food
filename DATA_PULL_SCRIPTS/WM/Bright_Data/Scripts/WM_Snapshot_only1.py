
# MONITOR WM BRIGHT DATA PROGRESS

# ---- EDIT THESE ----
TOKEN = "fb96b4c9c28b985bae9a68e2c98c69dff4b4f8f362d53a6d463cd285319adfaf"
SNAPSHOT_ID = "sd_mhfr47vk60rzhvcxy"
OUT_DIR = r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA_PULL_SCRIPTS\WM\Bright_Data\Outputs"
# # --------------------

# BASE = "https://api.brightdata.com/datasets/v3"
# AK_PREFIXES = ("995","996","997","998","999")
# ZIP_RE = re.compile(r"\b(\d{5})(?:-\d{4})?\b")

# def flatten(d, parent_key="", out=None):
#     """Flatten nested dict/list so we can scan all keys/values easily."""
#     if out is None: out = {}
#     if isinstance(d, dict):
#         for k, v in d.items():
#             nk = f"{parent_key}.{k}" if parent_key else k
#             flatten(v, nk, out)
#     elif isinstance(d, list):
#         for i, v in enumerate(d):
#             nk = f"{parent_key}[{i}]"
#             flatten(v, nk, out)
#     else:
#         out[parent_key] = d
#     return out

# def first_addr(row):
#     return (
#         row.get("store_address") or
#         row.get("address") or
#         row.get("storeAddress") or
#         ""
#     )

# def first_city(row):
#     return (
#         row.get("store_city") or
#         row.get("city") or
#         row.get("storeCity") or
#         ""
#     )

# def first_name(row):
#     return row.get("product_name") or row.get("title") or row.get("name") or ""

# def first_desc(row):
#     return row.get("product_description") or row.get("description") or ""

# def first_price(row):
#     return (
#         row.get("price") or row.get("final_price") or row.get("current_price") or
#         row.get("price_num") or row.get("price_text") or ""
#     )

# def first_upc(row):
#     return row.get("upc") or row.get("gtin") or ""

# def first_pid(row):
#     return (
#         row.get("product_id") or row.get("item_id") or row.get("us_item_id") or
#         row.get("id") or row.get("sku") or ""
#     )

# def extract_zip_and_state(row: dict):
#     """Search widely for zip & state in any nested field."""
#     flat = flatten(row)
#     zip_val, state_val = "", ""

#     # pass 1: look at likely keys
#     for k, v in flat.items():
#         kl = k.lower()
#         if any(tok in kl for tok in ("zip", "postalcode", "postal_code")) and isinstance(v, (str, int)):
#             m = ZIP_RE.search(str(v))
#             if m:
#                 zip_val = m.group(1); break

#     # pass 2: regex across any string value if not found yet
#     if not zip_val:
#         for v in flat.values():
#             if isinstance(v, str):
#                 m = ZIP_RE.search(v)
#                 if m:
#                     zip_val = m.group(1); break

#     # state: prefer exact "AK"
#     for k, v in flat.items():
#         if isinstance(v, str) and v.strip().upper() == "AK" and any(s in k.lower() for s in ("state","region")):
#             state_val = "AK"; break

#     # fallback: detect " AK " in address-like fields
#     if not state_val:
#         addr = (first_addr(row) or "") + " " + (flat.get("store.address","") or "")
#         if " AK " in f" {addr.upper()} ":
#             state_val = "AK"

#     return zip_val, state_val

# def is_alaska(zip_val: str, state_val: str) -> bool:
#     if state_val == "AK":
#         return True
#     if zip_val and any(zip_val.startswith(p) for p in AK_PREFIXES):
#         return True
#     return False

# def write_subset(w: csv.DictWriter, row: dict, zip_val: str):
#     w.writerow({
#         "address": first_addr(row),
#         "city": first_city(row),
#         "zipcode": zip_val,
#         "product_name": first_name(row),
#         "product_description": first_desc(row),
#         "price": first_price(row),
#         "upc": first_upc(row),
#         "product_id": first_pid(row),
#     })

# def main():
#     out_dir = Path(OUT_DIR); out_dir.mkdir(parents=True, exist_ok=True)
#     ak_csv  = out_dir / "walmart_brightdata_AK.csv"
#     sample_csv = out_dir / "walmart_brightdata_SAMPLE50.csv"

#     S = requests.Session()
#     S.headers.update({"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"})

#     # We’ll stream from the status endpoint (works for your snapshot).
#     url = f"{BASE}/snapshot/{SNAPSHOT_ID}"
#     r = S.get(url, stream=True, timeout=3600)
#     if r.status_code != 200:
#         print(f"[ERROR] snapshot GET {r.status_code}", file=sys.stderr); sys.exit(1)

#     kept = 0
#     sampled = 0
#     with open(ak_csv, "w", encoding="utf-8", newline="") as fout, \
#          open(sample_csv, "w", encoding="utf-8", newline="") as fsamp:

#         fields = ["address","city","zipcode","product_name","product_description","price","upc","product_id"]
#         w = csv.DictWriter(fout, fieldnames=fields); w.writeheader()
#         ws = csv.DictWriter(fsamp, fieldnames=["_zip","_state","keys","example_title"]); ws.writeheader()

#         for line in r.iter_lines(decode_unicode=True):
#             if not line: continue
#             try:
#                 rec = json.loads(line)
#             except Exception:
#                 continue

#             # write out a tiny sample of rows (helps you verify fields later)
#             if sampled < 50:
#                 z, st = extract_zip_and_state(rec)
#                 ws.writerow({
#                     "_zip": z, "_state": st,
#                     "keys": ",".join(list(rec.keys())[:12]),
#                     "example_title": str(first_name(rec))[:80],
#                 })
#                 sampled += 1

#             z, st = extract_zip_and_state(rec)
#             if is_alaska(z, st):
#                 write_subset(w, rec, z); kept += 1

#     print(f"[OK] Saved AK-only CSV → {ak_csv} (rows kept: {kept})")
#     print(f"[INFO] Also wrote SAMPLE50 for quick inspection → {sample_csv}")

# if __name__ == "__main__":
#     main()





