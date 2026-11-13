# extract_unique_bills.py
# Reads the VoteView house rollcalls file and extracts every unique (congress, bill number)
# pair that had at least one recorded vote between 1985 and present.
# This flips the bill-identification approach: instead of starting from a keyword search,
# we start from every bill that actually got voted on and label each one afterward.
# Output: data/us/unique_voted_bills.csv with 10,430 unique pairs.

import csv

# Reading from the VoteView rollcalls file, which has one row per recorded vote
ROLLCALLS_PATH = "data/us/voteview/house_rollcalls_1985_present.csv"

# Writing the deduplicated list of unique bills to a clean CSV
OUTPUT_PATH = "data/us/unique_voted_bills.csv"

if __name__ == "__main__":
    seen = set()
    with open(ROLLCALLS_PATH) as f:
        reader = csv.DictReader(f)
        for row in reader:
            bill = row.get("bill_number", "").strip()
            congress = row.get("congress", "").strip()

            # Storing congress number alongside bill number because bill numbers
            # reset every two years, so HR 2493 in 2026 and HR 2493 in 1987
            # are completely unrelated bills that happen to share a number
            if bill and congress:
                seen.add((congress, bill))

    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["congress", "bill_number"])
        for congress, bill in sorted(seen):
            writer.writerow([congress, bill])

    print(f"Found {len(seen)} unique (congress, bill) pairs with recorded votes, 1985-present")