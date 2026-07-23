"""
ocr_pre1993_speeches.py

OCRs the pre-1993 voice vote speech files where the GovInfo HTML endpoint
returns 400 (old GPO-CRECB format). Falls back to PDF with pytesseract.

Usage: python3 scripts/ocr_pre1993_speeches.py
"""
import os, json, io, time, requests
from dotenv import load_dotenv

load_dotenv()
KEY = os.getenv("GOVINFO_KEY")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRANULE_INDEX = os.path.join(REPO_ROOT, "data/us/congressional_record_granule_index.json")
VOICE_STATUS = os.path.join(REPO_ROOT, "data/us/voice_vote_speeches_status.json")
SPEECH_DIR = os.path.join(REPO_ROOT, "data/us/congressional_record_speeches")
BASE = "https://api.govinfo.gov"
HEADERS = {"User-Agent": "Mozilla/5.0 (research; Yale)"}


def ocr_pdf(pdf_bytes):
    try:
        from pdf2image import convert_from_bytes
        import pytesseract
        images = convert_from_bytes(pdf_bytes, dpi=200)
        text = "\n\n".join(pytesseract.image_to_string(img) for img in images)
        return text
    except Exception as e:
        print(f"  OCR error: {e}")
        return None


def main():
    with open(GRANULE_INDEX) as f:
        granule_index = json.load(f)
    with open(VOICE_STATUS) as f:
        voice_status = json.load(f)

    # find bills that need OCR - granule exists but no speech
    need_ocr = {}
    for key, v in voice_status.items():
        if not v.get("has_speech") and v.get("passage_date"):
            date = v["passage_date"]
            if date in granule_index:
                need_ocr[date] = granule_index[date]

    # deduplicate by date
    print(f"Dates needing OCR: {len(need_ocr)}")

    done = 0
    for date, granule in sorted(need_ocr.items()):
        out_path = os.path.join(SPEECH_DIR, f"{date}.txt")
        if os.path.exists(out_path):
            print(f"  {date}: already exists, skipping")
            done += 1
            continue

        pkg_id = granule["packageId"]
        gran_id = granule["granuleId"]
        gran_ids = gran_id if isinstance(gran_id, list) else [gran_id]

        print(f"  OCR {date} ({pkg_id})...", end=" ", flush=True)
        parts = []
        for gid in gran_ids:
            pdf_url = f"{BASE}/packages/{pkg_id}/granules/{gid}/pdf"
            try:
                resp = requests.get(pdf_url, params={"api_key": KEY},
                                   headers=HEADERS, timeout=60)
                if resp.status_code != 200:
                    print(f"PDF 404 for {gid}")
                    continue
                text = ocr_pdf(resp.content)
                if text:
                    parts.append(f"--- {gid} ---\n{text}")
            except Exception as e:
                print(f"  Error: {e}")
            time.sleep(0.5)

        if parts:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("\n\n".join(parts))
            print(f"done ({len(parts[0])} chars)")
            done += 1
        else:
            print("failed")

        time.sleep(1.0)

    print(f"\nDone: {done}/{len(need_ocr)}")

    # update status
    speech_files = set(f.replace(".txt","") for f in os.listdir(SPEECH_DIR)
                      if f.endswith(".txt") and "_notes" not in f)
    for key, v in voice_status.items():
        date = v.get("passage_date","")
        if date in speech_files:
            v["has_speech"] = True

    with open(VOICE_STATUS, "w") as f:
        json.dump(voice_status, f, indent=2)
    print("Status updated.")


if __name__ == "__main__":
    main()
