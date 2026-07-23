import requests, os, json
from dotenv import load_dotenv
load_dotenv()
KEY = os.getenv("GOVINFO_KEY")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

pkg = "GPO-CRECB-1990-pt24"
resp = requests.get(
    f"https://api.govinfo.gov/packages/{pkg}/granules",
    params={"api_key": KEY, "pageSize": 100, "offsetMark": "*"},
    timeout=20
)
granules = resp.json().get("granules", [])
house = [g for g in granules if g.get("granuleId","").endswith("-2")]
print("House granules:", [g.get("granuleId") for g in house[:3]])

idx_path = os.path.join(REPO, "data/us/congressional_record_granule_index.json")
with open(idx_path) as f:
    idx = json.load(f)

if house:
    idx["1990-10-26"] = {"packageId": pkg, "granuleId": house[0]["granuleId"]}
    with open(idx_path, "w") as f:
        json.dump(idx, f, indent=2)
    print("Added 1990-10-26 to index:", house[0]["granuleId"])
