import requests
import os
import csv
import io

OUTPUT_DIR = "data/us/voteview"
MIN_CONGRESS = 99  # 99th Congress = 1985-86, our project start

FILES = {
    "house_rollcalls": "https://voteview.com/static/data/out/rollcalls/HSall_rollcalls.csv",
    "house_votes": "https://voteview.com/static/data/out/votes/HSall_votes.csv",
    "house_members": "https://voteview.com/static/data/out/members/HSall_members.csv",
}

def download_and_filter(name, url):
    print(f"Downloading {name}...")
    resp = requests.get(url, timeout=120)
    if resp.status_code != 200:
        print(f"Failed to get {name}: status {resp.status_code}")
        return

    reader = csv.DictReader(io.StringIO(resp.text))
    fieldnames = reader.fieldnames

    filtered_rows = []
    for row in reader:
        try:
            congress = int(row.get("congress", 0))
        except (ValueError, TypeError):
            continue
        if congress >= MIN_CONGRESS and row.get("chamber") == "House":
            filtered_rows.append(row)

    out_path = os.path.join(OUTPUT_DIR, f"{name}_1985_present.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(filtered_rows)

    print(f"Saved {len(filtered_rows)} House rows (Congress {MIN_CONGRESS}+) to {out_path}")

if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for name, url in FILES.items():
        download_and_filter(name, url)