# wm_snapshot_AK_enhanced.py
# Download an existing Bright Data snapshot (CSV if ready; else stream JSON/JSONL)
# and write an Alaska-only, normalized CSV with smarter nested-field extraction.

import os
import sys
import csv
import json
from pathlib import Path
import requests

# ---------- EDIT THESE ----------
TOKEN = "fb96b4c9c28b985bae9a68e2c98c69dff4b4f8f362d53a6d463cd285319adfaf"             # e.g., "fb96b4..."
SNAPSHOT_ID = "sd_mhfr47vk60rzhvcxy"    # e.g., "sd_mhfr47vk60rzhvcxy"
OUT_DIR = r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA_PULL_SCRIPTS\WM\Bright_Data\Outputs"
# ---------------------------------

BASE = "https://api.brightdata.com/datasets/v3"
AK_PREFIXES = ("995", "996", "997", "998", "999")

# Preferred column order for the Alaska-only CSV
FINAL_COLS = [
    "address", "city", "zipcode",
    "product_name", "product_description",
    "price", "upc", "product_id"
]

def is_ak_zip(z):
    if not z:
        return False
    z = str(z).strip()
    return any(z.startswith(p) for p in AK_PREFIXES)

def first_nonempty(*vals):
    for v in vals:
        if v is None:
            continue
        if isinstance(v, str):
            vv = v.strip()
            if vv:
                return vv
        else:
            # accept non-empty non-strings
            if v not in ("", [], {}, ()):
                return v
    return ""

def pick_path(obj, path):
    """
    Resolve a dotted path in a dict that may include lists.
    Examples: "store.address.city", "offers.0.price", "priceInfo.currentPrice.price"
    If a list is encountered and the next token isn't an int, use the first element.
    """
    cur = obj
    for token in path.split("."):
        if isinstance(cur, list):
            # try integer index if provided, else use first element
            idx = 0
            try:
                idx = int(token)
                if idx < 0 or idx >= len(cur):
                    return ""
                cur = cur[idx]
                continue
            except ValueError:
                if not cur:
                    return ""
                cur = cur[0]
                # continue to use current token on the dict we just selected
        if isinstance(cur, dict):
            if token in cur:
                cur = cur[token]
            else:
                return ""
        else:
            return ""
    return cur

def pick_any(obj, paths):
    """
    Try many dotted paths; return the first non-empty scalar/string-ish result.
    """
    for p in paths:
        val = pick_path(obj, p) if "." in p else obj.get(p, "")
        val = first_nonempty(val)
        if val != "":
            return val
    return ""

def extract_zip(rec):
    # try common flat keys then nested store/address structures
    return pick_any(rec, [
        "zipcode", "zip", "postal_code", "store_zip",
        "store.address.postal_code", "store.address.zip",
        "store.zip", "store.postal_code",
        "store_info.zipcode", "store_info.zip"
    ])

def extract_address(rec):
    return pick_any(rec, [
        "store_address", "address", "storeAddress",
        "store.address.street", "store.address.address1",
        "store.address1", "store.street_address"
    ])

def extract_city(rec):
    return pick_any(rec, [
        "store_city", "city", "storeCity",
        "store.address.city", "store.city",
        "store_info.city"
    ])

def extract_name(rec):
    return pick_any(rec, [
        "product_name", "title", "name", "product.title"
    ])

def extract_desc(rec):
    return pick_any(rec, [
        "product_description", "description", "short_description", "product.description"
    ])

def extract_price(rec):
    # Search common price shapes
    return pick_any(rec, [
        "price", "price_current", "price_num", "current_price", "final_price", "price_text",
        "primary.price",
        "buyBox.winner.price",
        "offers.0.price",                   # first offer
        "priceInfo.currentPrice.price",     # Walmart internal-ish
        "pricing.current.price"             # another variant sometimes seen
    ])

def extract_upc(rec):
    return pick_any(rec, [
        "upc", "gtin", "universal_product_code", "wupc",
        "product.upc", "product.gtin"
    ])

def extract_product_id(rec):
    return pick_any(rec, [
        "product_id", "item_id", "us_item_id", "id", "sku",
        "product.id"
    ])

def row_to_normalized(rec):
    return {
        "address": first_nonempty(extract_address(rec)),
        "city": first_nonempty(extract_city(rec)),
        "zipcode": first_nonempty(extract_zip(rec)),
        "product_name": first_nonempty(extract_name(rec)),
        "product_description": first_nonempty(extract_desc(rec)),
        "price": first_nonempty(extract_price(rec)),
        "upc": first_nonempty(extract_upc(rec)),
        "product_id": first_nonempty(extract_product_id(rec)),
    }

def download_if_csv_ready(session, out_dir):
    raw_csv = out_dir / "walmart_brightdata_raw.csv"
    head = session.head(f"{BASE}/snapshot/{SNAPSHOT_ID}/file.csv",
                        allow_redirects=True, timeout=30)
    if head.status_code == 200:
        print("[INFO] CSV is ready — downloading…")
        with session.get(f"{BASE}/snapshot/{SNAPSHOT_ID}/file.csv",
                         stream=True, timeout=900) as r:
            r.raise_for_status()
            with open(raw_csv, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    if chunk:
                        f.write(chunk)
        print(f"[OK] Saved raw CSV: {raw_csv}")
        return raw_csv
    return None

def stream_any_json(session, out_dir):
    """
    Stream JSON/NDJSON from whichever endpoint is available first.
    Writes Alaska-only normalized CSV directly while streaming.
    Returns output AK path or None if no JSON endpoint available.
    """
    ak_csv = out_dir / "walmart_brightdata_AK.csv"
    candidates = [
        f"{BASE}/snapshot/{SNAPSHOT_ID}/file.json",
        f"{BASE}/snapshot/{SNAPSHOT_ID}/file.ndjson",
        f"{BASE}/snapshot/{SNAPSHOT_ID}",  # often JSONL "status" feed with records
    ]

    kept = 0
    wrote_header = False
    with open(ak_csv, "w", encoding="utf-8", newline="") as fout:
        writer = csv.DictWriter(fout, fieldnames=FINAL_COLS)
        writer.writeheader()
        wrote_header = True

        for url in candidates:
            try:
                with session.get(url, stream=True, timeout=1800) as r:
                    if r.status_code != 200:
                        continue
                    ctype = r.headers.get("content-type", "").lower()
                    if "json" not in ctype:
                        continue
                    print(f"[INFO] Streaming from {url} ({ctype}) …")
                    for line in r.iter_lines(decode_unicode=True):
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                        except Exception:
                            continue
                        z = extract_zip(rec)
                        if not is_ak_zip(z):
                            continue
                        norm = row_to_normalized(rec)
                        writer.writerow(norm)
                        kept += 1
                    print(f"[OK] Saved AK-only CSV (from JSON stream) → {ak_csv} (rows kept: {kept})")
                    return ak_csv
            except requests.RequestException:
                # try next candidate
                continue

    print("[ERROR] No JSON stream available (all endpoints 404/invalid).", file=sys.stderr)
    return None

def filter_raw_csv_to_ak(raw_csv_path, out_dir):
    ak_csv = out_dir / "walmart_brightdata_AK.csv"
    kept = 0
    with open(raw_csv_path, "r", encoding="utf-8", newline="") as fin, \
         open(ak_csv, "w", encoding="utf-8", newline="") as fout:
        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=FINAL_COLS)
        writer.writeheader()
        for row in reader:
            # Map the raw CSV row to our normalized schema
            rec = row_to_normalized(row)
            if is_ak_zip(rec.get("zipcode", "")):
                writer.writerow(rec)
                kept += 1
    print(f"[OK] Saved AK-only CSV → {ak_csv} (rows kept: {kept})")
    return ak_csv

def write_sample(ak_csv_path, out_dir, n=50):
    sample_path = out_dir / "walmart_brightdata_SAMPLE50.csv"
    try:
        with open(ak_csv_path, "r", encoding="utf-8", newline="") as fin, \
             open(sample_path, "w", encoding="utf-8", newline="") as fout:
            reader = csv.DictReader(fin)
            writer = csv.DictWriter(fout, fieldnames=reader.fieldnames)
            writer.writeheader()
            i = 0
            for row in reader:
                writer.writerow(row)
                i += 1
                if i >= n:
                    break
        print(f"[INFO] Also wrote SAMPLE{n} → {sample_path}")
    except Exception:
        pass

def main():
    token = os.getenv("BRIGHTDATA_API_KEY") or TOKEN
    if not token or token.startswith("REPLACE_WITH_"):
        print("Set TOKEN at top of script or BRIGHTDATA_API_KEY in env.", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/json"})

    # 1) Use final CSV if Bright Data has produced it
    raw_csv = download_if_csv_ready(session, out_dir)
    if raw_csv:
        ak_path = filter_raw_csv_to_ak(raw_csv, out_dir)
        write_sample(ak_path, out_dir, n=50)
        return

    # 2) Fall back to streaming JSON/NDJSON
    print("[INFO] CSV not ready; falling back to JSON/JSONL stream…")
    ak_path = stream_any_json(session, out_dir)
    if not ak_path:
        sys.exit(1)
    write_sample(ak_path, out_dir, n=50)

if __name__ == "__main__":
    main()
