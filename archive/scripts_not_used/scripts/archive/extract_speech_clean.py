"""
extract_speech_clean.py

Fixes the interleaving bug found this morning: pdfplumber reads words by
y-position, so footnotes/citations sharing a line height with body text
get braided into the same sentence. Fix: extract words in two separate
streams by font size, sort each stream independently by (page, y, x), and
save both, nothing is discarded.

Output per date: two files instead of one
  {date}.txt          - body text only, clean for sentence segmentation
  {date}_notes.txt     - smaller-font text (footnotes/citations), kept for
                          reference but excluded from claim extraction

Usage: python3 scripts/extract_speech_clean.py <packageId> <granuleId> <date>
Example:
  python3 scripts/extract_speech_clean.py CRECB-2006-pt18 CRECB-2006-pt18-Pg23369 2006-12-09
"""

import sys
import os
import io
import requests
import pdfplumber
from collections import Counter
from dotenv import load_dotenv

load_dotenv()
KEY = os.getenv("GOVINFO_KEY")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO_ROOT, "data", "us", "congressional_record_speeches")


def fetch_pdf_bytes(package_id, granule_id):
    url = f"https://api.govinfo.gov/packages/{package_id}/granules/{granule_id}/pdf"
    resp = requests.get(url, params={"api_key": KEY}, timeout=30)
    resp.raise_for_status()
    return resp.content


def extract_streams(pdf_bytes):
    """
    Returns (body_text, notes_text). Body text is built only from the
    single most common font size per page (the main column of speech).
    Everything else (footnotes, citations, headers) goes to notes_text,
    preserved, not thrown away.
    """
    body_lines = []
    notes_lines = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(extra_attrs=["size"])
            if not words:
                continue

            sizes = Counter(round(w["size"], 1) for w in words)
            body_size = sizes.most_common(1)[0][0]

            body_words = [w for w in words if abs(w["size"] - body_size) < 0.3]
            note_words = [w for w in words if abs(w["size"] - body_size) >= 0.3]

            def words_to_text(word_list):
                if not word_list:
                    return ""
                # detect a column split: find the biggest gap between
                # consecutive sorted x0 values. If that gap is wide
                # (empty gutter between columns), split there.
                xs = sorted(w["x0"] for w in word_list)
                gaps = [(xs[i + 1] - xs[i], xs[i]) for i in range(len(xs) - 1)]
                biggest_gap, gap_start = max(gaps, default=(0, None))

                page_width = max(xs) - min(xs) if len(xs) > 1 else 0
                if biggest_gap > 40 and page_width > 0:
                    split_x = gap_start + biggest_gap / 2
                    left_col = [w for w in word_list if w["x0"] < split_x]
                    right_col = [w for w in word_list if w["x0"] >= split_x]
                else:
                    left_col = word_list
                    right_col = []

                def column_to_lines(col):
                    col = sorted(col, key=lambda w: (round(w["top"]), w["x0"]))
                    lines = []
                    current_line_y = None
                    current_line = []
                    for w in col:
                        y = round(w["top"])
                        if current_line_y is not None and abs(y - current_line_y) > 2:
                            lines.append(" ".join(current_line))
                            current_line = []
                        current_line_y = y
                        current_line.append(w["text"])
                    if current_line:
                        lines.append(" ".join(current_line))
                    return lines

                # left column read fully top-to-bottom, then right column,
                # so real sentence order is preserved within each column
                return "\n".join(column_to_lines(left_col) + column_to_lines(right_col))

            body_lines.append(words_to_text(body_words))
            notes_lines.append(words_to_text(note_words))

    return "\n\n".join(body_lines), "\n\n".join(notes_lines)


def main():
    if len(sys.argv) != 4:
        print("Usage: python3 scripts/extract_speech_clean.py <packageId> <granuleId> <date>")
        sys.exit(1)

    package_id, granule_id, date = sys.argv[1], sys.argv[2], sys.argv[3]
    print(f"Fetching {package_id}/{granule_id} for {date}...")

    pdf_bytes = fetch_pdf_bytes(package_id, granule_id)
    body_text, notes_text = extract_streams(pdf_bytes)

    os.makedirs(OUT_DIR, exist_ok=True)
    body_path = os.path.join(OUT_DIR, f"{date}.txt")
    notes_path = os.path.join(OUT_DIR, f"{date}_notes.txt")

    with open(body_path, "w", encoding="utf-8") as f:
        f.write(body_text)
    with open(notes_path, "w", encoding="utf-8") as f:
        f.write(notes_text)

    print(f"Body text saved:  {body_path} ({len(body_text)} chars)")
    print(f"Notes text saved: {notes_path} ({len(notes_text)} chars)")
    print("\nNothing discarded, footnotes/citations kept separately")
    print("for reference but excluded from sentence-level claim extraction.")


if __name__ == "__main__":
    main()
