# voteview_pull.py
# Downloads the three core VoteView datasets from UCLA and filters them down
# to House-only rows from the 99th Congress onward (1985 to present),
# matching the project's Canada Health Act anchor date.
# VoteView is the standard academic dataset for legislative voting behavior
# research and underlies DW-NOMINATE, the gold standard for political
# classification referenced in the Giovanni et al. methodology paper.
# This source was chosen over Congress.gov's own vote API because that
# endpoint was only introduced in 2025 and only covers the 118th Congress
# onward (2023+), making it unusable for historical work.
# The three output files are:
#   house_rollcalls_1985_present.csv  one row per recorded vote
#   house_votes_1985_present.csv      one row per member per vote
#   house_members_1985_present.csv    biographical data per member
# Note: the votes file exceeds GitHub's 100MB file size limit and is
# excluded from the repository via .gitignore. It lives locally only.

import requests
import os
import csv
import io

# Where the three filtered VoteView files will be saved
OUTPUT_DIR = "data/us/voteview"

# The 99th Congress ran 1985 to 1986, matching our project's start date
MIN_CONGRESS = 99

# VoteView publishes combined House and Senate files covering all Congresses
# back to 1789. We download these in full and filter in memory since there
# is no partial download option and the files are large.
FILES = {
    "house_rollcalls": "https://voteview.com/static/data/out/rollcalls/HSall_rollcalls.csv",
    "house_votes": "https://voteview.com/static/data/out/votes/HSall_votes.csv",
    "house_members": "https://voteview.com/static/data/out/members/HSall_members.csv",
}

def download_and_filter(name, url):
    # Downloading the full historical file into memory, then filtering to
    # House only and Congress 99 onward before writing to disk
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
        # Keeping only House rows from Congress 99 onward
        # Senate data is excluded since the comparison is House-only
        if congress >= MIN_CONGRESS and row.get("chamber") == "House":
            filtered_rows.append(row)

    # Writing the filtered subset to a clearly dated output file
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