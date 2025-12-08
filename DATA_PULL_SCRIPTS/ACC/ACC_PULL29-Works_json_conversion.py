import os
import time
import json
import pandas as pd
from datetime import datetime
import requests

# Selenium imports
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --------------------------------------------------------------------
# 1. RETRIEVE TOKEN VIA SELENIUM (ENTER ZIP CODE)
# --------------------------------------------------------------------
def retrieve_token(driver, zip_code):
    """
    Navigate to shopalaskacommercial.com, enter the ZIP code, and retrieve the JWT token from localStorage.
    """
    try:
        driver.get("https://shopalaskacommercial.com/")
        time.sleep(5)  # Allow page to load

        wait = WebDriverWait(driver, 10)
        # Locate the ZIP code input field
        zip_input_xpath = "/html/body/p-dynamicdialog/div/div/div/app-store-location/div/div/div[2]/input"
        zip_input = wait.until(EC.presence_of_element_located((By.XPATH, zip_input_xpath)))
        zip_input.clear()
        zip_input.send_keys(zip_code)

        # Use special XPath if needed; otherwise, default
        special_xpaths = {
            '99574': "/html/body/p-dynamicdialog/div/div/div/app-store-location/div/div/div[3]/div/button/span"
        }
        select_xpath = special_xpaths.get(zip_code, "/html/body/p-dynamicdialog/div/div/div/app-store-location/div/div/div[3]/div/button/span")
        select_button = wait.until(EC.element_to_be_clickable((By.XPATH, select_xpath)))
        select_button.click()

        # Click the Save button to confirm location
        save_button_xpath = "/html/body/p-dynamicdialog/div/div/div/app-store-location/div/div/button"
        save_button = wait.until(EC.element_to_be_clickable((By.XPATH, save_button_xpath)))
        save_button.click()

        time.sleep(10)  # Wait for token to be stored in localStorage
        token = driver.execute_script("return window.localStorage.getItem('token');")
        if token:
            token = token.replace('"', '')
            print("Token retrieved:", token)
            return token
        else:
            print("Token not found in localStorage.")
            return None
    except Exception as e:
        print("Error retrieving token:", e)
        return None

# --------------------------------------------------------------------
# 2. CALL THE API FOR EACH KEYWORD USING "SEARCH_STRING" PARAMETER
# --------------------------------------------------------------------
def search_keyword_payload(token, keyword, store="235"):
    """
    Calls the /storeItem/algolia endpoint with a POST request.
    The search string is passed in the JSON payload.
    """
    url = "https://backend.shopalaskacommercial.com/storeItem/algolia"
    
    params = {
        "STORE": store,
        "DEPT_ID": "",
        "CLASS_ID": "",
        "PAGE": "1",
        "LIMIT": "30",
        "SORT": "",
        "ORDER": "",
        "TRENDING_SEARCH": "false",
        "SKU": "",
        "PARTY_TRAY_FLAG": "false"
    }
    
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "Mozilla/5.0"
    }
    
    payload = {
        "SEARCH_STRING": keyword
    }

    req = requests.Request("POST", url, params=params, headers=headers, json=payload)
    prepped = req.prepare()
    print("Request URL:", prepped.url)

    response = requests.post(url, params=params, headers=headers, json=payload)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error for keyword '{keyword}': {response.status_code} {response.text}")
        return None

# --------------------------------------------------------------------
# 3. SAVE THE ORIGINAL JSON DATA
# --------------------------------------------------------------------
def save_original_json(json_data, store):
    """
    Saves the original JSON data to a file under the folder structure:
      [Base Path]\ACC\ACC_YY_MM\ACC_<STORE>_MM_YY.json
    """
    now = datetime.now()
    year_last2 = now.strftime("%y")  # e.g., "25"
    month_str = now.strftime("%m")     # e.g., "03"

    base_path = r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\UAV Rural Essential Goods Delivery\FOOD_PRICING\Data_Scraping\ACC"
    folder_name = f"ACC_{year_last2}_{month_str}"  # Folder name in ACC_YY_MM format
    folder_path = os.path.join(base_path, folder_name)
    os.makedirs(folder_path, exist_ok=True)

    file_name = f"ACC_{store}_{month_str}_{year_last2}.json"  # Filename: ACC_<STORE>_MM_YY.json
    file_path = os.path.join(folder_path, file_name)

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=4)
        print(f"Original JSON data saved to {file_path}")
    except Exception as e:
        print(f"Error saving JSON data: {e}")

# --------------------------------------------------------------------
# 4. COLLAPSE THE "response" COLUMN (FLATTEN JSON TO CSV)
# --------------------------------------------------------------------
def collapse_response_column(json_data):
    """
    Flattens the JSON data using pandas.json_normalize.
    It first flattens the 'response' list (while retaining selected top-level metadata),
    then, if an 'item' field is present (which is a list with one dictionary), it extracts
    and expands it into separate columns.
    """
    if not json_data:
        print("No data to flatten.")
        return pd.DataFrame()
    
    # Choose only top-level keys that are simple (ignore 'response' and 'algoliaResponse')
    meta_keys = [k for k in json_data[0].keys() if k not in ['response', 'algoliaResponse']]
    
    try:
        # Flatten the "response" records and include meta keys
        df_flat = pd.json_normalize(
            json_data,
            record_path='response',
            meta=meta_keys,
            sep='_',
            errors='ignore'
        )
        
        # If the 'item' field is present and is a list, extract its first (or only) element
        if 'item' in df_flat.columns:
            df_flat['item'] = df_flat['item'].apply(lambda x: x[0] if isinstance(x, list) and len(x) > 0 else {})
            # Normalize the extracted dictionary from 'item'
            df_item = pd.json_normalize(df_flat['item'], sep='_')
            # Drop the original 'item' column and concatenate the expanded item columns
            df_flat = pd.concat([df_flat.drop(columns=['item']), df_item], axis=1)
        
        return df_flat
    except Exception as e:
        print("Error flattening JSON:", e)
        return pd.DataFrame()

# --------------------------------------------------------------------
# 5. SAVE RESULTS TO CSV UNDER "ACC_YY_MM" FOLDER WITH FILENAME "ACC_<STORE>_MM_YY.csv"
# --------------------------------------------------------------------
def save_payload_results(df, store):
    """
    Saves the flattened DataFrame to a CSV file under the folder structure:
      [Base Path]\ACC\ACC_YY_MM\ACC_<STORE>_MM_YY.csv
    """
    now = datetime.now()
    year_last2 = now.strftime("%y")  # e.g., "25"
    month_str = now.strftime("%m")     # e.g., "03"

    base_path = r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\UAV Rural Essential Goods Delivery\FOOD_PRICING\Data_Scraping\ACC"
    folder_name = f"ACC_{year_last2}_{month_str}"
    folder_path = os.path.join(base_path, folder_name)
    os.makedirs(folder_path, exist_ok=True)

    file_name = f"ACC_{store}_{month_str}_{year_last2}.csv"
    file_path = os.path.join(folder_path, file_name)

    df.to_csv(file_path, index=False)
    print(f"Payload results saved to {file_path}")

# --------------------------------------------------------------------
# 6. MAIN EXECUTION FLOW
# --------------------------------------------------------------------
def main():
    zip_code = "99574"  # Set your ZIP code here.
    store_id = "235"    # Store ID (as used in the API calls)

    # 6.1 Start Selenium and retrieve token.
    options = Options()
    # Uncomment the next line to run headless if desired:
    # options.add_argument("--headless")
    driver_service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=driver_service, options=options)

    token = retrieve_token(driver, zip_code)
    if not token:
        driver.quit()
        return
    driver.quit()

    # 6.2 Load keywords from CSV (expects a column named "ACC_Keywords")
    keywords_csv_path = r"G:/.shortcut-targets-by-id/10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\UAV Rural Essential Goods Delivery\FOOD_PRICING\Data_Scraping\ACC\ACC_Keywords.csv"
    try:
        keywords_df = pd.read_csv(keywords_csv_path)
        keywords = keywords_df["ACC_Keywords"].iloc[:10].tolist()
    except Exception as e:
        print("Error loading keywords from CSV:", e)
        return

    all_payload_results = []
    # 6.3 For each keyword, call the API to retrieve the payload.
    for keyword in keywords:
        print(f"Searching for keyword: {keyword}")
        data = search_keyword_payload(token, keyword, store=store_id)
        if data:
            # Add metadata to the payload for reference
            data["searched_keyword"] = keyword
            data["zip_code"] = zip_code
            all_payload_results.append(data)
        else:
            print(f"No data returned for keyword: {keyword}")

    if not all_payload_results:
        print("No payload data collected.")
        return

    # 6.4 Save the original JSON data.
    save_original_json(all_payload_results, store_id)

    # 6.5 Flatten the JSON data to produce a CSV-friendly DataFrame.
    df_flat = collapse_response_column(all_payload_results)
    if df_flat.empty:
        print("Flattened DataFrame is empty. Exiting.")
        return

    # 6.6 Save the flattened results to CSV.
    save_payload_results(df_flat, store_id)

if __name__ == "__main__":
    main()
