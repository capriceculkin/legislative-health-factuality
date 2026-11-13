import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()
KEY = os.getenv("CONGRESS_KEY")

def get_bills(congress=118, limit=20):
    url = f"https://api.congress.gov/v3/bill/{congress}"
    params = {
        "api_key": KEY,
        "limit": limit
    }
    response = requests.get(url, params=params)
    return response.json()

if __name__ == "__main__":
    results = get_bills()
    output_path = "data/us/congress_bills_118.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Saved results to {output_path}")