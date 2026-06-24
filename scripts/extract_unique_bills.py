import csv

ROLLCALLS_PATH = "data/us/voteview/house_rollcalls_1985_present.csv"
OUTPUT_PATH = "data/us/unique_voted_bills.csv"

if __name__ == "__main__":
    seen = set()
    with open(ROLLCALLS_PATH) as f:
        reader = csv.DictReader(f)
        for row in reader:
            bill = row.get("bill_number", "").strip()
            congress = row.get("congress", "").strip()
            if bill and congress:
                seen.add((congress, bill))

    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["congress", "bill_number"])
        for congress, bill in sorted(seen):
            writer.writerow([congress, bill])

    print(f"Found {len(seen)} unique (congress, bill) pairs with recorded votes, 1985-present")