import requests

API_KEY = "5470de471903618d2dd462633e022234e47d1a8257a1db9f615abda30cb047d3"
SNAPSHOT_ID = "sd_mjhtgrhv9fv9rjron"

url = f"https://api.brightdata.com/datasets/v3/snapshot/{SNAPSHOT_ID}/file.csv"

headers = {
    "Authorization": f"Bearer {API_KEY}",
}

response = requests.head(
    url,
    headers=headers,
    allow_redirects=True,
    timeout=30,
)

print("Status code:", response.status_code)
print("Headers:", dict(response.headers))




from pathlib import Path

paths = [
    Path(r"C:\Users\vlcollier\Downloads\sd_mjc2uwzoro56qxt8e.csv"),
    Path(r"C:\Users\vlcollier\Downloads\sd_mjc2uwzoro56qxt8e.json"),
]

for p in paths:
    print(f"\n=== {p.name} ===")
    print("Exists:", p.exists())
    print("Size (MB):", round(p.stat().st_size / 1024 / 1024, 2))

    with p.open("rb") as f:
        head = f.read(200)

    print("First 200 bytes:")
    print(head)
