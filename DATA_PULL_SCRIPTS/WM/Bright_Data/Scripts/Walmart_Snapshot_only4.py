# wm_snapshot_dual_export.py
# Download an existing Bright Data snapshot and write BOTH CSV and JSON
# into two target directories, under a subfolder named MM_YY derived from
# the snapshot response headers. Filenames auto-version as Walmart_YY_MM_v.[i].ext

import os
import sys
import csv
import json
import re
import pathlib
import requests
import datetime
import itertools
import email.utils

# ------------- EDIT THESE -------------
TOKEN = os.getenv("BRIGHTDATA_API_KEY") or "REPLACE_WITH_API_KEY"
SNAPSHOT_ID = "REPLACE_WITH_SNAPSHOT_ID"

DEST1 = r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA\RAW_DATA\WM_RAW"
DEST2 = r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\UAV Rural Essential Goods Delivery\FOOD_PRICING\Data_Scraping\Walmart"
# -------------------------------------

BASE = "https://api.brightdata.com/datasets/v3"

def ensure_token():
    if not TOKEN or TOKEN.startswith("REPLACE_WITH_"):
        print("Set TOKEN (or BRIGHTDATA_API_KEY) and SNAPSHOT_ID.", file=sys.stderr)
        sys.exit(1)

def make_session():
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"})
    return s

def parse_http_dt(header_value):
    """Parse RFC 2822/7231 date to datetime (UTC)."""
    try:
        dt = email.utils.parsedate_to_datetime(header_value)
        if dt.tzinfo:
            dt = dt.astimezone(datetime.timezone.utc)
        else:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt
    except Exception:
        return None

def infer_mm_yy_from_headers(headers):
    # Prefer Last-Modified, else Date, else now
    lm = headers.get("last-modified") or headers.get("Last-Modified")
    dt = parse_http_dt(lm) if lm else None
    if not dt:
        dh = headers.get("date") or headers.get("Date")
        dt = parse_http_dt(dh) if dh else None
    if not dt:
        dt = datetime.datetime.now(datetime.timezone.utc)
    mm = f"{dt.month:02d}"
    yy = f"{dt.year % 100:02d}"
    return mm, yy

def subfolder_for(mm, yy):
    return f"{mm}_{yy}"

def next_version_path(dirpath, yy, mm, ext):
    """
    Find Walmart_YY_MM_v.[i].ext (i starts at 1) that does not yet exist.
    """
    base = f"Walmart_{yy}_{mm}_v."
    for i in itertools.count(1):
        candidate = pathlib.Path(dirpath) / f"{base}{i}.{ext}"
        if not candidate.exists():
            return candidate

def write_bytes_to_both(paths, data_bytes):
    for p in paths:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data_bytes)

def write_json_to_both(paths, records):
    data = json.dumps(records, ensure_ascii=False)
    data_bytes = data.encode("utf-8")
    write_bytes_to_both(paths, data_bytes)

def csv_rows_from_records(records):
    # Build a union of keys for CSV header (stable order: common keys first)
    common = ["address","city","zipcode","product_name","product_description","price","upc","product_id","url","sku","gtin","product_id_raw"]
    key_set = set()
    for r in records:
        if isinstance(r, dict):
            key_set.update(r.keys())
    # move common to front, others sorted
    rest = sorted(k for k in key_set if k not in common)
    header = [k for k in common if k in key_set] + rest
    # Yield header + rows
    yield header
    for r in records:
        if not isinstance(r, dict):
            continue
        yield [r.get(k, "") for k in header]

def write_csv_to_both(paths, records):
    for p in paths:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8", newline="") as f:
            writer = None
            # stream write from generator
            gen = csv_rows_from_records(records)
            header = next(gen, None)
            if header is None:
                # no rows; write empty file with no header
                continue
            writer = csv.writer(f)
            writer.writerow(header)
            for row in gen:
                writer.writerow(row)

def try_get_csv(session):
    url = f"{BASE}/snapshot/{SNAPSHOT_ID}/file.csv"
    head = session.head(url, allow_redirects=True, timeout=30)
    if head.status_code == 200:
        getr = session.get(url, stream=True, timeout=900)
        getr.raise_for_status()
        content = getr.content
        return content, getr.headers
    return None, {}

def try_get_json(session):
    # Try file.json then file.ndjson
    for suffix in ["file.json", "file.ndjson"]:
        url = f"{BASE}/snapshot/{SNAPSHOT_ID}/{suffix}"
        r = session.get(url, stream=True, timeout=900)
        if r.status_code == 200 and "json" in (r.headers.get("content-type","").lower()):
            return r, r.headers
    # Fallback: status endpoint (often JSONL)
    url = f"{BASE}/snapshot/{SNAPSHOT_ID}"
    r = session.get(url, stream=True, timeout=900)
    if r.status_code == 200 and "json" in (r.headers.get("content-type","").lower()):
        return r, r.headers
    return None, {}

def records_from_csv_bytes(csv_bytes):
    # Convert CSV bytes to list of dicts (for JSON parity)
    text = csv_bytes.decode("utf-8", errors="replace")
    lines = text.splitlines()
    recs = []
    rdr = csv.DictReader(lines)
    for row in rdr:
        recs.append(dict(row))
    return recs

def records_from_json_stream(response):
    # Accept JSON array or JSONL/NDJSON
    ctype = response.headers.get("content-type","").lower()
    text_like = "json" in ctype
    if not text_like:
        return []

    # Try as a full JSON (array or object)
    try:
        # only if server is not using chunked JSONL
        content = response.content
        data = json.loads(content.decode("utf-8", errors="replace"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
    except Exception:
        pass

    # Stream JSONL
    recs = []
    for line in response.iter_lines(decode_unicode=True):
        if not line:
            continue
        try:
            rec = json.loads(line)
            if isinstance(rec, dict):
                recs.append(rec)
        except Exception:
            continue
    return recs

def main():
    ensure_token()
    session = make_session()

    # Priority: use CSV if ready (fastest). Otherwise use JSON/JSONL stream.
    csv_bytes, csv_headers = try_get_csv(session)
    if csv_bytes is not None:
        mm, yy = infer_mm_yy_from_headers(csv_headers)
        sub = subfolder_for(mm, yy)
    else:
        json_resp, json_headers = try_get_json(session)
        if json_resp is None:
            print("[ERROR] Snapshot not available as CSV/JSON yet. Check the ID or try later.", file=sys.stderr)
            sys.exit(2)
        mm, yy = infer_mm_yy_from_headers(json_headers)
        sub = subfolder_for(mm, yy)

    # Prepare destination paths
    dests = [pathlib.Path(DEST1) / sub, pathlib.Path(DEST2) / sub]
    for d in dests:
        d.mkdir(parents=True, exist_ok=True)

    # File paths with versioning
    csv_paths = [next_version_path(d, yy, mm, "csv") for d in dests]
    json_paths = [next_version_path(d, yy, mm, "json") for d in dests]

    # Fetch/convert data and write both formats
    if csv_bytes is not None:
        # Write CSV as-is
        write_bytes_to_both(csv_paths, csv_bytes)
        # Also convert CSV -> JSON and write
        recs = records_from_csv_bytes(csv_bytes)
        write_json_to_both(json_paths, recs)
        print(f"[OK] Wrote CSV and JSON to:\n  {csv_paths[0]}\n  {csv_paths[1]}")
        print(f"  {json_paths[0]}\n  {json_paths[1]}")
        return

    # JSON route
    recs = records_from_json_stream(json_resp)
    if not recs:
        print("[ERROR] JSON stream yielded no records.", file=sys.stderr)
        sys.exit(3)

    # Write JSON directly
    write_json_to_both(json_paths, recs)
    # Also create CSV from records
    write_csv_to_both(csv_paths, recs)
    print(f"[OK] Wrote JSON and CSV to:\n  {json_paths[0]}\n  {json_paths[1]}")
    print(f"  {csv_paths[0]}\n  {csv_paths[1]}")

if __name__ == "__main__":
    main()
