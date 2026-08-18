from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "catalog.db"

HF_DATASET = "McAuley-Lab/Amazon-Reviews-2023"

CATEGORIES = [
    "All_Beauty",
    "Amazon_Fashion",
    "Appliances",
    "Arts_Crafts_and_Sewing",
    "Automotive",
    "Baby_Products",
    "Beauty_and_Personal_Care",
    "Books",
    "CDs_and_Vinyl",
    "Cell_Phones_and_Accessories",
    "Clothing_Shoes_and_Jewelry",
    "Digital_Music",
    "Electronics",
    "Gift_Cards",
    "Grocery_and_Gourmet_Food",
    "Handmade_Products",
    "Health_and_Household",
    "Health_and_Personal_Care",
    "Home_and_Kitchen",
    "Industrial_and_Scientific",
    "Kindle_Store",
    "Magazine_Subscriptions",
    "Movies_and_TV",
    "Musical_Instruments",
    "Office_Products",
    "Patio_Lawn_and_Garden",
    "Pet_Supplies",
    "Software",
    "Sports_and_Outdoors",
    "Subscription_Boxes",
    "Tools_and_Home_Improvement",
    "Toys_and_Games",
    "Video_Games",
]

SAMPLE_PER_CATEGORY = 750

SOLR_URL = "http://localhost:8983/solr"
SOLR_CORE = "items"

# Phase 3 — synthetic demographic-preference bootstrap
# Minimal/extensible demographic schema: a "segment" is one (age_bracket, gender, region) triple.
AGE_BRACKETS = ["13-17", "18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
GENDERS = ["female", "male", "nonbinary"]
REGIONS = ["US-Northeast", "US-South", "US-Midwest", "US-West"]

NUM_SYNTHETIC_USERS = 500
SESSIONS_PER_USER_RANGE = (8, 40)  # simulated suggest queries per synthetic user
SYNTHETIC_SELECT_PROBABILITY = 0.65  # chance a simulated suggest query ends in a select
SYNTHETIC_RANDOM_SEED = 42
