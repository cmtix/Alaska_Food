
# MONITOR WM BRIGHT DATA PROGRESS

import requests

snapshot_id = {"sd_mhgd6frk25ycbl39ky"}
token = {"fb96b4c9c28b985bae9a68e2c98c69dff4b4f8f362d53a6d463cd285319adfaf"}

url = "https://api.brightdata.com/datasets/v3/progress/{snapshot_id}"

headers = {"Authorization": "Bearer <token>"}

response = requests.get(url, headers=headers)

print(response.json())