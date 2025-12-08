
# wm_snapshot_ak_filter_posixafe.py
# Stream an existing Bright Data snapshot → filter to Alaska → CSV
# Positron/Ruff friendly: one import per line, no one-line statements.

import os
import sys
import csv
import json
import re
from pathlib import Path
import requests

# --------- CONFIG ---------
# Prefer env var; if not set, use the fallback literal.
TOKEN_FALLBACK = "fb96b4c9c28b985bae9a68e2c98c69dff4b4f8f362d53a6d463cd285319adfaf"  # e.g., "fb96b4c9c..."; leave blank if using env
TOKEN = os.getenv("BRIGHTDATA_API_KEY") or TOKEN_FALLBACK

SNAPSHOT_ID = "sd_mhfr47vk60rzhvcxy"
OUT_DIR = r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA_PULL_SCRIPTS\WM\Bright_Data\Outputs"
# --------------------------

BASE = "https://api.brightdata.com/datasets/v3"
AK_PREFIXES = ("995", "996", "997", "998", "999")
ZIP_RE = re.compile(r"\b(\d{5})(?:-\d{4})?\b")


def flatten(node, parent_key="", out=None):
    """Flatten nested dict/list so we can scan all keys/values easily."""
    if out is None:
        out = {}
    if isinstance(node, dict):
        for k, v in node.items():
            nk = f"{parent_key}.{k}" if parent_key else k
            flatten(v, nk, out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            nk = f"{parent_key}[{i}]"
            flatten(v, nk, out)
    else:
        out[parent_key] = node
    return out


def first_addr(row):
    return (
        row.get("store_address")
        or row.get("address")
        or row.get("storeAddress")
        or ""
    )


def first_city(row):
    return (
        row.get("store_city")
        or row.get("city")
        or row.get("storeCity")
        or ""
    )


def first_name(row):
    return row.get("product_name") or row.get("title") or row.get("name") or ""


def first_desc(row):
    return row.get("product_description") or row.get("description") or ""


def first_price(row):
    return (
        row.get("price")
        or row.get("final_price")
        or row.get("current_price")
        or row.get("price_num")
        or row.get("price_text")
        or ""
    )


def first_upc(row):
    return row.get("upc") or row.get("gtin") or ""


def first_pid(row):
    return (
        row.get("product_id")
        or row.get("item_id")
        or row.get("us_item_id")
        or row.get("id")
        or row.get("sku")
        or ""
    )


def extract_zip_and_state(row):
    """Search widely for ZIP & state in any nested field."""
    flat = flatten(row)
    zip_val = ""
    state_val = ""

    # Pass 1: scan likely zip keys
    for k, v in flat.items():
        if not isinstance(v, (str, int)):
            continue
        kl = k.lower()
        if "zip" in kl or "postalcode" in kl or "postal_code" in kl:
            m = ZIP_RE.search(str(v))
            if m:
                zip_val = m.group(1)
                break

    # Pass 2: regex across any string value if still missing
    if not zip_val:
        for v in flat.values():
            if not isinstance(v, str):
                continue
            m = ZIP_RE.search(v)
            if m:
                zip_val = m.group(1)
                break

    # State: prefer exact "AK" near state-like keys
    for k, v in flat.items():
        if isinstance(v, str) and v.strip().upper() == "AK":
            if "state" in k.lower() or "region" in k.lower():
                state_val = "AK"
                break

    # Fallback: " AK " in address-like fields
    if not state_val:
        addr_like = f"{first_addr(row)} {flat.get('store.address', '')}"
        if f" AK " in f" {addr_like.upper()} ":
            state_val = "AK"

    return zip_val, state_val


def is_alaska(zip_val, state_val):
    if state_val == "AK":
        return True
    if zip_val:
        for p in AK_PREFIXES:
            if zip_val.startswith(p):
                return True
    return False


def write_subset(writer, row, zip_val):
    writer.writerow(
        {
            "address": first_addr(row),
            "city": first_city(row),
            "zipcode": zip_val,
            "product_name": first_name(row),
            "product_description": first_desc(row),
            "price": first_price(row),
            "upc": first_upc(row),
            "product_id": first_pid(row),
        }
    )


def main():
    if not TOKEN:
        print("ERROR: No Bright Data API token provided.", file=sys.stderr)
        sys.exit(1)
    if not SNAPSHOT_ID or not SNAPSHOT_ID.startswith("sd_"):
        print("ERROR: Set SNAPSHOT_ID to an existing snapshot id.", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    ak_csv = out_dir / "walmart_brightdata_AK.csv"
    sample_csv = out_dir / "walmart_brightdata_SAMPLE50.csv"

    session = requests.Session()
    session.headers.update(
        {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}
    )

    url = f"{BASE}/snapshot/{SNAPSHOT_ID}"
    try:
        resp = session.get(url, stream=True, timeout=3600)
    except requests.RequestException as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if resp.status_code != 200:
        print(f"ERROR: snapshot GET {resp.status_code}", file=sys.stderr)
        sys.exit(1)

    kept = 0
    sampled = 0
    fields = [
        "address",
        "city",
        "zipcode",
        "product_name",
        "product_description",
        "price",
        "upc",
        "product_id",
    ]

    with open(ak_csv, "w", encoding="utf-8", newline="") as f_out, open(
        sample_csv, "w", encoding="utf-8", newline=""
    ) as f_samp:
        writer = csv.DictWriter(f_out, fieldnames=fields)
        writer.writeheader()

        sample_writer = csv.DictWriter(
            f_samp, fieldnames=["_zip", "_state", "keys", "example_title"]
        )
        sample_writer.writeheader()

        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue

            try:
                rec = json.loads(line)
            except Exception:
                continue

            # write first 50 samples to help inspect fields if needed
            if sampled < 50:
                z_samp, st_samp = extract_zip_and_state(rec)
                top_keys = list(rec.keys())[:12]
                sample_writer.writerow(
                    {
                        "_zip": z_samp,
                        "_state": st_samp,
                        "keys": ",".join(top_keys),
                        "example_title": str(first_name(rec))[:80],
                    }
                )
                sampled += 1

            z, st = extract_zip_and_state(rec)
            if is_alaska(z, st):
                write_subset(writer, rec, z)
                kept += 1

    print(f"[OK] Saved AK-only CSV → {ak_csv} (rows kept: {kept})")
    print(f"[INFO] Also wrote SAMPLE50 → {sample_csv}")


if __name__ == "__main__":
    main()
