#!/usr/bin/env python3
import requests

API_KEY = "5470de471903618d2dd462633e022234e47d1a8257a1db9f615abda30cb047d3"  # Replace with your API key
SNAPSHOT_ID = "sd_mi2q7qcpxhdyzxkml"  # Replace with your snapshot ID



url = f"https://api.brightdata.com/datasets/snapshots/{SNAPSHOT_ID}/download"
headers = {
    "Authorization": f"Bearer {API_KEY}"
}

response = requests.get(url, headers=headers)

if response.status_code == 200:
    with open("dataset_snapshot.zip", "wb") as f:
        f.write(response.content)
    print("Download complete: dataset_snapshot.zip")
else:
    print(f"Failed to download snapshot. Status code: {response.status_code}")
    print(response.text)
