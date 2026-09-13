"""
extract_quebec_bill_segmenkts.py

Extracts bill-specific text segments from Quebec National Assembly
transcript files using "Étude du projet de loi n° X" section markers.

Instead of using the full sitting-day transcript as the factuality denominator,
this script extracts only the text directly associated with each health bill's
debate, making Quebec directly comparable to the US bill-specific corpus.

Output: data/canada/quebec_assembly/bill_segments/
  One .txt file per bill-date combination containing only the bill debate text.

Also outputs: data/canada/quebec_bills/quebec_bill_segments_index.json
  Maps bill number + date to segment file path and word count.

Usage: python3 scripts/extract_quebec_bill_segments.py
"""
import os, re, json
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRANSCRIPT_DIR = os.path.join(REPO_ROOT, "data/canada/quebec_assembly")
TRANSCRIPT_DIR_PRE1994 = os.path.join(REPO_ROOT, "data/canada/quebec_assembly/transcripts")
OUTPUT_DIR = os.path.join(REPO_ROOT, "data/canada/quebec_assembly/bill_segments")
INDEX_PATH = os.path.join(REPO_ROOT, "data/canada/quebec_bills/quebec_bill_segments_index.json")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Pattern for bill study section headers
# Matches: "Étude du projet de loi n° 52" or "Étude du projet de loi no 52"
BILL_HEADER_RE = re.compile(
    r'(?:'
    r'(?:Auditions\s+et\s+)?(?:[ÉE]tude\s+(?:d[ée]taill[ée]e\s+)?(?:du\s+|de\s+la\s+)?)'
    r'|Adoption\s+du\s+principe\s+(?:et\s+\w+\s+)?(?:du\s+|de\s+la\s+)?'
    r'|Reprise\s+du\s+d[ée]bat\s+sur\s+l\'adoption\s+du\s+principe\s+du\s+'
    r'|Prise\s+en\s+consid[ée]ration\s+du\s+rapport\s+sur\s+le\s+'
    r'|Adoption\s+(?:du\s+|de\s+la\s+)?'
    r'|[Dd]euxième\s+lecture\s+(?:du\s+)?(?:projet\s+de\s+loi\s+(?:n[°o]?\s*)?)?'
    r'|[Tt]roisième\s+lecture\s+(?:du\s+)?(?:projet\s+de\s+loi\s+(?:n[°o]?\s*)?)?'
    r'|[Dd][ée]bat\s+(?:ajourné\s+)?sur\s+(?:la\s+)?(?:motion\s+portant\s+)?(?:deuxième|troisième)\s+lecture\s+(?:du\s+)?(?:projet\s+de\s+loi\s+(?:n[°o]?\s*)?)?'
    r')projet\s+de\s+loi\s+(?:n[°o]?\s*)?(\d+)',
    re.IGNORECASE
)

# For files where bill number is on the next line
BILL_HEADER_MULTILINE_RE = re.compile(
    r'(?:Auditions\s+et\s+)?(?:[ÉE]tude\s+(?:d[ée]taill[ée]e\s+)?(?:du\s+|de\s+la\s+)?|'
    r'Adoption\s+du\s+principe\s+(?:et\s+\w+\s+)?(?:du\s+|de\s+la\s+)?|'
    r'Reprise\s+du\s+d[ée]bat\s+sur\s+l\'adoption\s+du\s+principe\s+du\s+|'
    r'Prise\s+en\s+consid[ée]ration\s+du\s+rapport\s+sur\s+le\s+|'
    r'Adoption\s+(?:du\s+|de\s+la\s+)?)projet\s+de\s+loi\s*\n\s*(\d+)',
    re.IGNORECASE
)

# Other section headers that mark the END of a bill debate section
SECTION_END_RE = re.compile(
    r'^(Étude du projet de loi|Projet de loi|Mise aux voix|Adoption du principe|'
    r'Renseignements sur les travaux|Ajournement|Reprise du débat|'
    r'Motion de censure|Questions et réponses|Affaires courantes|'
    r'Présentation de projets de loi|Dépôt de documents|'
    r'Déclarations de députés|Questions orales)',
    re.IGNORECASE | re.MULTILINE
)

def extract_bill_segments(text, date):
    """
    Extract all bill debate segments from a transcript.
    Returns list of (bill_number, segment_text) tuples.
    """
    segments = []
    lines = text.split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i]
        m = BILL_HEADER_RE.search(line)
        if m:
            bill_num = m.group(1)
            # Collect text from this header until next section header
            segment_lines = [line]
            j = i + 1
            while j < len(lines):
                next_line = lines[j]
                # Check if this is a new major section
                if j > i + 5 and SECTION_END_RE.match(next_line.strip()):
                    # But not if it's a continuation of same bill
                    next_m = BILL_HEADER_RE.search(next_line)
                    if next_m and next_m.group(1) == bill_num:
                        segment_lines.append(next_line)
                        j += 1
                        continue
                    else:
                        break
                segment_lines.append(next_line)
                j += 1
            
            segment_text = '\n'.join(segment_lines).strip()
            if len(segment_text) > 200:  # Skip trivially short segments
                segments.append((bill_num, segment_text))
            i = j
        else:
            i += 1
    
    return segments

def main():
    print(f"Scanning {TRANSCRIPT_DIR}...")
    txt_files = sorted([
        f for f in os.listdir(TRANSCRIPT_DIR)
        if f.endswith('.txt') and re.match(r'\d{8}\.txt', f)
    ])
    # Add pre-1994 transcripts
    pre1994_files = sorted([
        f for f in os.listdir(TRANSCRIPT_DIR_PRE1994)
        if f.endswith('.txt') and re.match(r'\d{8}\.txt', f)
    ])
    txt_files = txt_files + pre1994_files
    print(f"Found {len(txt_files)} transcript files ({len(pre1994_files)} pre-1994)")
    
    index = {}  # {bill_num: {date: {path, word_count, char_count}}}
    total_segments = 0
    files_with_segments = 0
    
    for fname in txt_files:
        date_str = fname.replace('.txt', '')
        date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        fpath = os.path.join(TRANSCRIPT_DIR, fname)
        if not os.path.exists(fpath):
            fpath = os.path.join(TRANSCRIPT_DIR_PRE1994, fname)
        
        try:
            with open(fpath, encoding='utf-8', errors='replace') as f:
                text = f.read()
            # Join cases where bill number is on next line after header
            text = re.sub(
                r'(projet\s+de\s+loi)\s*\n\s*(\d+)',
                r'\1 n° \2',
                text,
                flags=re.IGNORECASE
            )
        except Exception as e:
            print(f"  Error reading {fname}: {e}")
            continue
        
        segments = extract_bill_segments(text, date)
        
        if segments:
            files_with_segments += 1
            for bill_num, segment_text in segments:
                # Save segment to file
                out_fname = f"{date_str}_bill{bill_num}.txt"
                out_path = os.path.join(OUTPUT_DIR, out_fname)
                with open(out_path, 'w', encoding='utf-8') as f:
                    f.write(segment_text)
                
                # Add to index
                if bill_num not in index:
                    index[bill_num] = {}
                index[bill_num][date] = {
                    'path': out_path,
                    'word_count': len(segment_text.split()),
                    'char_count': len(segment_text),
                    'segment_file': out_fname
                }
                total_segments += 1
    
    print(f"\nResults:")
    print(f"  Files with bill segments: {files_with_segments}/{len(txt_files)}")
    print(f"  Total bill-date segments: {total_segments}")
    print(f"  Unique bills found: {len(index)}")
    
    # Show sample
    print(f"\nSample bills found:")
    for bill_num, dates in list(index.items())[:5]:
        dates_list = sorted(dates.keys())
        avg_words = sum(d['word_count'] for d in dates.values()) / len(dates)
        print(f"  Bill {bill_num}: {len(dates)} debate dates, avg {avg_words:.0f} words/date")
        print(f"    Dates: {dates_list[:3]}{'...' if len(dates_list) > 3 else ''}")
    
    # Save index
    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"\nIndex saved to {INDEX_PATH}")
    
    # Compare denominators
    print(f"\nDenominator comparison:")
    print(f"  Current: full sitting-day transcripts (~{8264319 // len(txt_files):.0f} lines/day avg)")
    print(f"  New: bill-specific segments only")
    total_words_new = sum(
        d['word_count'] 
        for dates in index.values() 
        for d in dates.values()
    )
    print(f"  Total words in bill segments: {total_words_new:,}")

if __name__ == "__main__":
    main()
