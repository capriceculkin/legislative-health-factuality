import requests
import json
import os
import time
from dotenv import load_dotenv

load_dotenv()
KEY = os.getenv("LEGISCAN_KEY")

def search_health_bills(state="US", page=1):
    url = "https://api.legiscan.com/"
    params = {
        "key": KEY,
        "op": "getSearch",
        "state": state,
        "query": "health",
        "page": page
    }
    response = requests.get(url, params=params)
    return response.json()

if __name__ == "__main__":
    all_results = {}
    page = 1
    while True:
        print(f"Pulling page {page}")
        data = search_health_bills(page=page)
        results = data.get("searchresult", {})

        if not results or all(k == "summary" for k in results):
            print("No more results, stopping.")
            break

        new_count = 0
        for k, v in results.items():
            if k == "summary":
                continue
            bill_id = v.get("bill_id")
            if bill_id and str(bill_id) not in all_results:
                all_results[str(bill_id)] = v
                new_count += 1

        print(f"  +{new_count} new bills (total: {len(all_results)})")

        summary = results.get("summary", {})
        page_total = summary.get("page_total", page)
        if page >= page_total:
            print("Reached last page.")
            break

        page += 1
        time.sleep(1)

    output_path = "data/us/legiscan_health_search.json"
    with open(output_path, "w") as f:
        json.dump({"searchresult": all_results}, f, indent=2)
    print(f"Saved {len(all_results)} total unique bills to {output_path}")