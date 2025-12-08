
# This script is to pull food cost data from Kroger Fred Meyer stores. 
# This version is from Nov 2024, modified by CMT 

# Updates for Nov include: 
    # Updaing store location IDs, it appears 2 location IDs were invalid 
    # Updating two product IDs, it appears they are still valid in lower 48 but different in AK now 
    
# Update for Jan 2025 include: 
    # Added in 15 items for the Nome Grocery Cart article list based on Mike's email 
    # UPC list is now up to 80 items, expected to grow in Feb as well from GeoDiffSurvey list 
    
# UPDATE Feb 2025: 
    # Added a lot more items from GeoDiffSurvey, up to 135 items 
    
# UPDATE May 2025: 
    # Added two new stores to location list, Portland and Seattle



import requests
import pandas as pd
import numpy as np
import os
from datetime import datetime


# suppress scientific notation
np.set_printoptions(suppress=True)

# set the float format to suppress scientific notation and remove trailing zeros
pd.options.display.float_format = lambda x: '{:.15f}'.format(x).rstrip('0').rstrip('.')

####################################################################################

# API endpoint for obtaining the token
url = "https://api.kroger.com/v1/connect/oauth2/token"

# Your client ID and client secret
client_id = 'uaaeconomicresearch-1c9930e136aa1ca8bdee7c8f336ed77a5021264682018960484'
client_secret = '5bmyn0oVBwaNevpdUrPIaTmQBBISjKU1DTDEOmp6'

# Parameters for the POST request
data = {
  'grant_type': 'client_credentials',
  'scope': 'product.compact'  # Change the scope according to your access needs
}

# Headers including the content type
headers = {
  'Content-Type': 'application/x-www-form-urlencoded'
}

# Basic Authentication setup
response = requests.post(url, auth=(client_id, client_secret), data=data, headers=headers)

# Check if the request was successful, hit enter in console after running this section for print to activate 
if response.status_code == 200:
  token = response.json()['access_token']
  print("Token:", token)
else:
  print("Failed to retrieve token:", response.text)   

################################################################################################

# AS JSON

# CMT edit, use line above without the longer pandas name, latest pandas made name shroter, just need "from pandas" 

# NOTE: don't forget to refresh your token in Postman app prior to running code. # code expires in 30 minutes
access_token = token

# Define a list of Kroger/FredMeyer location IDs (should be 11 locations in AK, 1 Portland, 1 Seattle) 
location_ids =   [ "70100011"  # Anch Midtown    99508
                 , "70100017"  # Soldotna        99669
                 , "70100018"  # Anch Muldoon    99504
                 , "70100071"  # Anch Dimond     99515
                 , "70100158"  # Juneau          99801
                 , "70100224"  # East Fairbanks  99701
                 , "70100485"  # West Fairbanks  99709
                 , "70100649"  # Palmer          99645
                 , "70100653"  # Wasilla         99654
                 , "70100656"  # Anch SE         99507
                 , "70100668"  # Eagle River     99577
                 , "70100600"  # Portland        97232 
                 , "70100122"  # Seattle         98117 
                 ]

# Define a list of UPCs, should be 135 UPC codes as on Feb 2025
upcs =  [ '0000000003082'	# Broccoli Crowns
        , '0000000003110'	# Cara Cara Navel Oranges
        , '0000000003151'	# Fresh Red Tomato 
        , '0000000003283'	# Large Honeycrisp Apple - Each
        , '0000000003421'	# Mini Seedless Whole Watermelon
        , '0000000004011'	# Fresh Banana - Single
        , '0000000004012'	# Large Heirloom Navel Oranges
        , '0000000004017'	# Large Granny Smith Apple - Each
        , '0000000004022'	# Green White Seedless Grapes
        , '0000000004048'	# Fresh Limes
        , '0000000004050'	# Cantaloupe
        , '0000000004053'	# Fresh Lemon - Each
        , '0000000004061'	# Iceberg Lettuce
        , '0000000004062'	# Cucumber
        , '0000000004065'	# Fresh Large Green Bell Pepper
        , '0000000004066'	# Fresh Green Beans-Order by the Pound
        , '0000000004067'	# Zucchini
        , '0000000004069'	# Green Cabbage
        , '0000000004070'	# Celery
        , '0000000004072'	# Russet Potato
        , '0000000004076'	# Green Leaf Lettuce
        , '0000000004079'	# Cauliflower
        , '0000000004080'	# Green Asparagus
        , '0000000004087'	# Fresh Roma Tomato
        , '0000000004093'	# Medium Yellow Onions
        , '0000000004281'	# Large Ruby Red Grapefruit
        , '0000000004430'	# Fresh Ripe Whole Pineapple
        , '0000000004550'	# Brussel Sprouts by the pound 
        , '0000000004554'	# Red Cabbage
        , '0000000004562'	# Carrots
        , '0000000004608'	# Garlic
        , '0000000004640'	# Romaine Lettuce
        , '0000000004662'	# Shallots
        , '0000000004664'	# Fresh On the Vine Red Tomatoes-Order by the Bunch (4-5 tomatoes per bunch)
        , '0000000004688'	# Fresh Red Hothouse Bell Pepper
        , '0000000004784'	# Squash Yellow
        , '0000000004799'	# Fresh Large Red Beefsteak Tomato
        , '0000000004800'	# Fresh Red Tomato
        , '0000000004816'	# Sweet Potato
        , '0000000094011'	# Organic Fresh Banana - Each
        , '0001111000454'	# Private Selection® Vanilla Bean Ice Cream Tub
        , '0001111003931'	# Private SelectionÂ® Fresh Colossal Blueberries
        , '0001111008415'	# Private Selection® White Bread Rustic Wide Pan
        , '0001111008450'	# Kroger® Soft Wheat Bread
        , '0001111008963'	# Kroger® Cage Free Large White Eggs
        , '0001111010491'	# Kroger® Soft & Strong Toilet Paper Double Roll
        , '0001111013198'	# Kroger White Bread
        , '0001111013199'	# Kroger® Soft Wheat Bread
        , '0001111013204'	# Private Selection® 100% Whole Wheat Bread Wide Pan
        , '0001111014186'	# Kroger® Ultra Paper Towels With Absorbing Power
        , '0001111018170'	# Kale Bag
        , '0001111018183'	# Fresh Sweet Corn on the Cob - 4 Count
        , '0001111018189'	# Honeycrisp Apples - 3 Pound Bag
        , '0001111040190'	# Fred Meyer Vitamin D Whole Milk Gallon
        , '0001111041491'	# Fred Meyerâ„¢ 2% Reduced Fat Milk Half Gallon
        , '0001111041550'	# Fred Meyer™ 2% Reduced Fat Milk Gallon
        , '0001111061375'	# Clamshell Seedless Green Grapes
        , '0001111078773'	# Kroger® Butter Sticks
        , '0001111084703'	# Kroger Long Grain Rice
        , '0001111085004'	# Kroger® Spaghetti Pasta, Barilla Spaghetti Pasta
        , '0001111085605'	# Kroger® Pure Vegetable Oil
        , '0001111087703'	# Kroger® Frozen Orange Juice Concentrate
        , '0001111089875'	# Kroger® Enriched Long Grain White Rice
        , '0001111090406'	# Kroger Grade AA Large Cage Free White Eggs
        , '0001111091011'	# White Whole Mushrooms
        , '0001111091013'	# Whole Baby Bella Mushrooms
        , '0001111091620'	# KrogerÂ® Peeled Baby Carrots Bag
        , '0001111091622'	# Kroger Whole Carrots Bag
        , '0001111091629'	# Romaine Lettuce Hearts Kroger brand 18oz 
        , '0001111091649'	# KrogerÂ® Tender Spinach Bag
        , '0001111091754'	# Kroger® Russet Potatoes Big Deal in 10 lb Bag
        , '0001111091871'	# Kroger Yukon Gold Potatoes
        , '0001111096920'	# Kroger 93/7 Ground Beef Tray 1 LB
        , '0001111096968'	# Kroger® 85/15 Ground Beef Tray 1 LB
        , '0001111097191'	# Kroger Hardwood Smoked Sliced Bacon
        , '0001111097209'	# Kroger® Thick Cut Naturally Hardwood Smoked Bacon
        , '0001200000017'	# Pepsi Cola® Soda Cans
        , '0001300000640'	# Heinz Tomato Ketchup
        , '0001580003061'	# C&H Premium Pure Cane Granulated Sugar 10 lb
        , '0001580003062'	# C&H Premium Pure Cane Granulated Sugar 4 lb Bag
        , '0001590013401'	# Classic Franks Hot Dogs
        , '0001600010610'	# Gold Medal™ All Purpose Flour
        , '0001700001840'	# Dial® Refresh & Renew™ Bar Soap Spring Water® Scent Antibacterial
        , '0002020008511'	# Sailor Boy Pilot Bread Crackers
        , '0002100060464'	# Kraft Singles American Sliced Cheese
        , '0002400016286'	# Del Monte Blue Lake Cut Green Beans
        , '0002400055078'	# Del Monte® Fresh Cut Golden Sweet Whole Kernel Corn Canned Vegetables
        , '0002550030445'	# Folgers® Classic Medium Roast Ground Coffee
        , '0002640022300'	# Darigold Original Sour Cream
        , '0003000001020'	# Quaker® Old Fashioned Whole Grain Oatmeal
        , '0003077209398'	# Dawn Ultra Original Scent, Liquid Dish Soap
        , '0003338314616'	# Seedless Mandarin Clementine Oranges in 3lb Bag
        , '0003338320027'	# Fresh Strawberries
        , '0003338321000'	# Fresh Red Raspberries
        , '0003338324000'	# Fresh Blackberries
        , '0003338370154'	# Brussels Sprouts
        , '0003600049695'	# Huggies Little Snugglers Baby Diapers Size 1 (8-14 lbs)
        , '0003600051472'	# Huggies Snug & Dry Baby Diapers Size 4 (22-37 lbs)
        , '0003700077307'	# Pampers Swaddlers Baby Diapers Size 4 (22-37 lbs)
        , '0003700084997'	# Tide Original Scent Powder Laundry Detergent
        , '0003760013872'	# SPAM® Canned Luncheon Meat, Classic
        , '0003800000110'	# Kellogg's® Corn Flakes Large Size Cereal
        , '0003890004215'	# Dole® Canned Mandarin Oranges Fruit In Light Syrup
        , '0004100000287'	# Lipton® Black Tea Bags
        , '0004400004483'	# Premium Original Saltine Crackers
        , '0004470007505'	# Oscar Mayer Classic Beef Franks Hot Dogs
        , '0004740024040'	# Gillette Foamy Classic Men's Original Signature Scent Shave Foam
        , '0004740066181'	# Gillette Mach3 Men's 3-Blade Razor Blades Refills Cartridges
        , '0004800000195'	# Chicken of the Sea Chunk Light Tuna in Oil
        , '0004800121351'	# Best Foods Real Mayo
        , '0004900002890'	# Coca-Cola Original Taste Soda Cans
        , '0005000001011'	# Nestle Carnation Evaporated Milk with Vitamin D Added
        , '0005150001229'	# Smucker's® Seedless Strawberry Jam
        , '0005150025516'	# Jif® Creamy Peanut Butter Spread
        , '0005410722101'	# CutiesÂ® Seedless California Mandarin Clementine Oranges in 3lb Bag
        , '0007007455958'	# SimilacÂ® AdvanceÂ® Milk Based Infant Powder
        , '0007007458586'	# SimilacÂ® AdvanceÂ® OptiGro Powder Infant Formula with Iron
        , '0007040400282'	# Pompeian Smooth Extra Virgin Olive Oil
        , '0007047000302'	# Yoplait Original Low Fat Mountain Blueberry Yogurt Cup
        , '0007066202603'	# Nissin Top Ramen Chicken Flavor Ramen Noodle Soup
        , '0007283000201'	# Tillamook® Medium Cheddar Block Cheese
        , '0007283000401'	# Tillamook Medium Cheddar Block Cheese
        , '0007373100415'	# Mission® Soft Taco Flour Tortillas
        , '0007800001180'	# 7UP Lemon Lime Caffeine-Free Soda Cans
        , '0007940049594'	# Suave Essentials Daily Clarifying Cleansing Shampoo
        , '0019600570834'	# Crisco Pure Canola Oil, Gluten-Free
        , '0020236600000'	# Beef Choice Top Round Roast (1 Roast)
        , '0021190600000'	# Private Selection™ Beef Choice Chuck Roast (1 Roast)
        , '0021386300000'	# Kroger® Fully Cooked Boneless Half Ham
        , '0028334850000'	# Heritage Farm® Bone In Skin On Whole Young Chicken
        , '0028334900000'	# Heritage Farm® Boneless Skinless Chicken Breasts
        , '0029315150000'	# Kroger® Bone-In Pork Loin Center Cut Chop
        , '0082785400183'	# Colgate Total Active Prevention Clean Mint Toothpaste
        , '0088828900051'	# Large Red Delicious Apples
        , '0212236000000'	# Private Selection™ Angus Beef Boneless Strip Steak
        ]
        
# Some UPCs are doubled up, since different stores use different UPCs 
  # '0001111008450' and '0001111013199' are both for Kroger® Soft Wheat Bread 
  # '0005410722101' and '0003338314616' are both Seedless Mandarin Clementine Oranges in 3lb Bag 
  # '0000000003151' and '0000000004800' are both Fresh Red Tomato 
  # '0000000004550' and '0003338370154' are both Brussel Sprouts by the pound 

base_url = "https://api.kroger.com/v1/products"

# Create an empty list to collect the results
results_list = []

for location_id in location_ids:
    for upc in upcs:
        # Construct the API endpoint URL
        url = f"{base_url}?filter.term={upc}&filter.locationId={location_id}"

        # Set the authorization header with the access token
        headers = {'Authorization': f'Bearer {access_token}'}

        # Make the API request
        response = requests.get(url, headers=headers)

        # Check if the response is successful and parse JSON
        # try:
        #     response_json = response.json()
        # except ValueError:
        #     response_json = {}

        # Collect the results in the list
        results_list.append({
            'Location ID': location_id,
            'UPC': upc,
            'Response status code': response.status_code,
            'Response content': response.json(),
            'Date': datetime.now().strftime('%Y-%m-%d')
        })


# Convert the list to a DataFrame using pd.concat
results = pd.concat([pd.DataFrame(results_list)], ignore_index=True)


################################################################################################ 

# Get the current year and month
now = datetime.now()
year = now.strftime("%Y")
month = now.strftime("%m")

# Define the filename
filename = f"FM_{year}_{month}.json"

# Get today's date
today = datetime.today()
foldername = today.strftime('FM_%Y_%m')  # Formats date as string in 'FM_YYYY_MM' format

# Specify the directory where you want to create the new folder
dir_path = 'G:/.shortcut-targets-by-id/13TRPt8_RZFrfmQt9TVmdpJNyl7kRtluH/Data_Scraping/FredMeyer/'  # CMT directory path 

# Combine the directory with the new folder name
folder_path = os.path.join(dir_path, foldername)

# Create the new directory
os.makedirs(folder_path, exist_ok=True)

# Change the working directory
new_directory = folder_path
os.chdir(new_directory)

# Write the results to a JSON file
results.to_json(filename, orient='records')

# Print the filename
print(f"Results saved to {filename}")

##################################################
