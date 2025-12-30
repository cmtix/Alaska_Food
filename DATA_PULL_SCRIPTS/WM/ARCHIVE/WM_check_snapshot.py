import requests

# Set Authorization headers
headers = {
	"Authorization": "Bearer 5470de471903618d2dd462633e022234e47d1a8257a1db9f615abda30cb047d3",
}

# Set snapshot id----

# Paste here -----
# Snapshot_id can be queried via code or by logging into BrightData.org: From Main User Dashboard: 
# Web Scrapers --> Logs


snapshot_id = "sd_mjhtgrhv9fv9rjron"


# UNIFIED SCRIPT - CHECK SNAPSHOT

import os
import sys
import time
import requests
from pathlib import Path
from datetime import datetime

# ---------------- CONFIG ----------------

API_KEY = os.getenv("WM_API_KEY")
SNAPSHOT_ID = os.getenv("WM_SNAPSHOT_ID") or "sd_mjc2uwzoro56qxt8e"

BASE_URL = "https://api.brightdata.com/datasets/v3"
POLL_EVERY_SECONDS = 30
MAX_WAIT_MINUTES = 10

# Build output filename: WM_YY_MM.csv
YY_MM = datetime.now().strftime("%y_%m")
OUT_FILE = Path(f"WM_{YY_MM}.csv")

# ---------------------------------------


def die(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)
    sys.exit(1)


def headers() -> dict:
    if not API_KEY:
        die("Missing WM_API_KEY environment variable.")
    return {
        "Authorization": f"Bearer {API_KEY}",
    }


def csv_exists(snapshot_id: str) -> bool:
    """
    Authoritative readiness check.
    """
    url = f"{BASE_URL}/snapshot/{snapshot_id}/file.csv"
    try:
        r = requests.head(
            url,
            headers=headers(),
            allow_redirects=True,
            timeout=30,
        )
        return r.status_code == 200
    except Exception:
        return False


def poll_until_csv_available(snapshot_id: str) -> None:
    """
    Poll ONLY for CSV existence.
    Ignore snapshot status entirely.
    """
    deadline = time.time() + MAX_WAIT_MINUTES * 60

    while True:
        if csv_exists(snapshot_id):
            print(f"[OK] CSV is available for snapshot {snapshot_id}")
            return

        if time.time() > deadline:
            die(
                f"Timeout: CSV never appeared for snapshot {snapshot_id}. "
                "Bright Data likely produced no output."
            )

        print(f"[WAIT] CSV not available yet for {snapshot_id}")
        time.sleep(POLL_EVERY_SECONDS)


def download_csv(snapshot_id: str, out_path: Path) -> None:
    """
    Download snapshot CSV to disk.
    """
    url = f"{BASE_URL}/snapshot/{snapshot_id}/file.csv"

    r = requests.get(
        url,
        headers=headers(),
        timeout=240,
    )
    r.raise_for_status()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(r.content)

    print(f"[OK] Downloaded CSV → {out_path.resolve()}")


def main() -> None:
    if not SNAPSHOT_ID:
        die("No snapshot id provided (WM_SNAPSHOT_ID).")

    print(f"[INFO] Using snapshot_id: {SNAPSHOT_ID}")
    print(f"[INFO] Output file will be: {OUT_FILE.name}")

    poll_until_csv_available(SNAPSHOT_ID)
    download_csv(SNAPSHOT_ID, OUT_FILE)


if __name__ == "__main__":
    main()
