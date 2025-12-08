#!/usr/bin/env python3
# Walmart_Snapshot_only5.py
# ----------------------------------------------------------
# Download an existing Bright Data Walmart snapshot and export
# both CSV and JSON to two mirrored destinations:
#   1) DATA\RAW_DATA\WM_RAW
#   2) UAV Rural Essential Goods Delivery\Data_Scraping\Walmart
#
# Uses snapshot HTTP date to create MM_YY subfolder.
# Filenames auto-increment: Walmart_YY_MM_v.[i].csv/.json
# Writes a manifest.json in each destination with run metadata.
# Positron-safe: one import per line.
# ----------------------------------------------------------

import os  
import sys
import csv
import json
import pathlib
import requests
import datetime
import itertools
import email.utils
from typing import List, Dict, Tuple, Optional

# ---------- CONFIGURE THESE ----------
TOKEN = os.getenv("BRIGHTDATA_API_KEY") or ("fb96b4c9c28b985bae9a68e2c98c69dff4b4f8f362d53a6d463cd285319adfaf")
SNAPSHOT_ID = os.getenv("BRIGHTDATA_SNAPSHOT_ID") or ("sd_mhfr47vk60rzhvcxy")

DEST1 = r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA\RAW_DATA\WM_RAW"
DEST2 = r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\UAV Rural Essential Goods Delivery\FOOD_PRICING\Data_Scraping\Walmart"
# -------------------------------------

BASE = "https://api.brightdata.com/datasets/v3"

def ensure_token_and_id() -> None:
    if not TOKEN or TOKEN.startswith("REPLACE_WITH_"):
        print("Set TOKEN or BRIGHTDATA_API_KEY.", file=sys.stderr)
        sys.exit(1)
    if not SNAPSHOT_ID or SNAPSHOT_ID.startswith("REPLACE_WITH_"):
        print("Set SNAPSHOT_ID or BRIGHTDATA_SNAPSHOT_ID.", file=sys.stderr)
        sys.exit(1)

def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"})
    return s

def parse_http_dt(header_value: Optional[str]) -> Optional[datetime.datetime]:
    if not header_value:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(header_value)
        if dt is None:
            return None
        if dt.tzinfo:
            dt = dt.astimezone(datetime.timezone.utc)
        else:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt
    except Exception:
        return None

def infer_mm_yy_from_headers(headers: Dict[str, str]) -> Tuple[str, str, Optional[str]]:
    lower = {k.lower(): v for k, v in headers.items()}
    lm = lower.get("last-modified")
    dh = lower.get("date")
    dt = parse_http_dt(lm) or parse_http_dt(dh) or datetime.datetime.now(datetime.timezone.utc)
    mm = f"{dt.month:02d}"
    yy = f"{dt.year % 100:02d}"
    # return ISO string for manifest
    dt_iso = dt.replace(tzinfo=datetime.timezone.utc).isoformat()
    return mm, yy, dt_iso

def subfolder_for(mm: str, yy: str) -> str:
    return f"{mm}_{yy}"

def next_version_path(dirpath: pathlib.Path, yy: str, mm: str, ext: str) -> Tuple[pathlib.Path, int]:
    base = f"Walmart_{yy}_{mm}_v."
    for i in itertools.count(1):
        candidate = dirpath / f"{base}{i}.{ext}"
        if not candidate.exists():
            return candidate, i

def write_bytes_to(p: pathlib.Path, data: bytes) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)

def write_text_to(p: pathlib.Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")

def records_from_csv_bytes(csv_bytes: bytes) -> List[Dict[str, str]]:
    text = csv_bytes.decode("utf-8", errors="replace")
    lines = text.splitlines()
    recs: List[Dict[str, str]] = []
    rdr = csv.DictReader(lines)
    for row in rdr:
        recs.append(dict(row))
    return recs

def records_from_json_stream(resp: requests.Response) -> List[Dict]:
    ctype = (resp.headers.get("content-type") or "").lower()
    # Try full JSON first
    try:
        if "json" in ctype and "jsonl" not in ctype and "ndjson" not in ctype:
            data = resp.json()
            if isinstance(data, list):
                return [r for r in data if isinstance(r, dict)]
            if isinstance(data, dict):
                return [data]
    except Exception:
        pass
    # Fallback: JSONL/NDJSON
    recs: List[Dict] = []
    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                recs.append(obj)
        except Exception:
            continue
    return recs

def try_get_csv(session: requests.Session) -> Tuple[Optional[bytes], Dict[str, str]]:
    url = f"{BASE}/snapshot/{SNAPSHOT_ID}/file.csv"
    head = session.head(url, allow_redirects=True, timeout=30)
    if head.status_code == 200:
        r = session.get(url, stream=True, timeout=900)
        r.raise_for_status()
        return r.content, dict(r.headers)
    return None, {}

def try_get_json(session: requests.Session) -> Tuple[Optional[requests.Response], Dict[str, str], str]:
    # Try JSON endpoints in order, keep note of which worked for manifest
    candidates = [
        (f"{BASE}/snapshot/{SNAPSHOT_ID}/file.json", "file.json"),
        (f"{BASE}/snapshot/{SNAPSHOT_ID}/file.ndjson", "file.ndjson"),
        (f"{BASE}/snapshot/{SNAPSHOT_ID}", "snapshot.jsonl"),
    ]
    for url, label in candidates:
        r = session.get(url, stream=True, timeout=1800)
        if r.status_code == 200 and "json" in (r.headers.get("content-type") or "").lower():
            return r, dict(r.headers), label
    return None, {}, ""

def mask_token(tok: str) -> str:
    if not tok or len(tok) < 8:
        return "<masked>"
    return tok[:6] + "…" + tok[-4:]

def write_manifest(
    dest_dir: pathlib.Path,
    snapshot_id: str,
    source_kind: str,
    headers: Dict[str, str],
    yy: str,
    mm: str,
    version_num: int,
    csv_path: Optional[pathlib.Path],
    json_path: Optional[pathlib.Path],
    records_count: int
) -> None:
    lower = {k.lower(): v for k, v in headers.items()}
    last_modified = lower.get("last-modified")
    date_hdr = lower.get("date")
    ctype = lower.get("content-type")
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    manifest = {
        "snapshot_id": snapshot_id,
        "source": source_kind,                      # "file.csv" | "file.json" | "file.ndjson" | "snapshot.jsonl"
        "http_content_type": ctype,
        "http_last_modified": last_modified,
        "http_date": date_hdr,
        "snapshot_month": mm,
        "snapshot_year_yy": yy,
        "version": version_num,
        "records_count": records_count,
        "csv_path": str(csv_path) if csv_path else None,
        "json_path": str(json_path) if json_path else None,
        "created_at_utc": now_iso,
        "api_base": BASE,
        "token_masked": mask_token(TOKEN),
    }
    write_text_to(dest_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

def main() -> None:
    ensure_token_and_id()
    session = make_session()

    # Prefer CSV if available
    csv_bytes, csv_headers = try_get_csv(session)
    used_kind = ""
    headers_for_dt: Dict[str, str] = {}

    if csv_bytes is not None:
        used_kind = "file.csv"
        headers_for_dt = csv_headers
    else:
        json_resp, json_headers, json_kind = try_get_json(session)
        if json_resp is None:
            print("[ERROR] Snapshot not available as CSV/JSON. Check ID or try later.", file=sys.stderr)
            sys.exit(2)
        used_kind = json_kind
        headers_for_dt = json_headers

    mm, yy, dt_iso = infer_mm_yy_from_headers(headers_for_dt)
    sub = subfolder_for(mm, yy)

    dest_dirs = [pathlib.Path(DEST1) / sub, pathlib.Path(DEST2) / sub]
    for d in dest_dirs:
        d.mkdir(parents=True, exist_ok=True)

    # Reserve version numbers per destination (same v.[i] across CSV/JSON)
    csv_paths: List[Optional[pathlib.Path]] = [None, None]
    json_paths: List[Optional[pathlib.Path]] = [None, None]
    version_nums: List[int] = [0, 0]

    # We compute version based on CSV target (or JSON if no CSV).
    for idx, d in enumerate(dest_dirs):
        if csv_bytes is not None:
            csv_p, ver = next_version_path(d, yy, mm, "csv")
            json_p, _ = next_version_path(d, yy, mm, "json")
        else:
            json_p, ver = next_version_path(d, yy, mm, "json")
            csv_p, _ = next_version_path(d, yy, mm, "csv")
        csv_paths[idx] = csv_p
        json_paths[idx] = json_p
        version_nums[idx] = ver

    # Export + manifest
    if csv_bytes is not None:
        # Write CSV and JSON (JSON derived from CSV rows)
        records = records_from_csv_bytes(csv_bytes)
        records_count = len(records)
        for idx in range(2):
            if csv_paths[idx] is not None:
                write_bytes_to(csv_paths[idx], csv_bytes)
            if json_paths[idx] is not None:
                write_text_to(json_paths[idx], json.dumps(records, ensure_ascii=False))
            write_manifest(
                dest_dir=dest_dirs[idx],
                snapshot_id=SNAPSHOT_ID,
                source_kind=used_kind,
                headers=headers_for_dt,
                yy=yy,
                mm=mm,
                version_num=version_nums[idx],
                csv_path=csv_paths[idx],
                json_path=json_paths[idx],
                records_count=records_count
            )
        print(f"[OK] Wrote CSV + JSON to:\n  {csv_paths[0]}\n  {csv_paths[1]}")
        return

    # JSON path (CSV not ready)
    records = records_from_json_stream(json_resp)  # type: ignore[arg-type]
    records_count = len(records)
    if records_count == 0:
        print("[ERROR] JSON stream yielded no records.", file=sys.stderr)
        sys.exit(3)

    # Write JSON + CSV synthesized from records
    header_keys = sorted({k for r in records if isinstance(r, dict) for k in r.keys()})
    for idx in range(2):
        if json_paths[idx] is not None:
            write_text_to(json_paths[idx], json.dumps(records, ensure_ascii=False))
        if csv_paths[idx] is not None:
            # synthesize CSV
            csv_path = csv_paths[idx]
            if csv_path is not None:
                with csv_path.open("w", encoding="utf-8", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=header_keys)
                    w.writeheader()
                    for rec in records:
                        if isinstance(rec, dict):
                            w.writerow(rec)
        write_manifest(
            dest_dir=dest_dirs[idx],
            snapshot_id=SNAPSHOT_ID,
            source_kind=used_kind,
            headers=headers_for_dt,
            yy=yy,
            mm=mm,
            version_num=version_nums[idx],
            csv_path=csv_paths[idx],
            json_path=json_paths[idx],
            records_count=records_count
        )

    print(f"[OK] Wrote JSON + CSV to:\n  {json_paths[0]}\n  {json_paths[1]}")

if __name__ == "__main__":
    main()
