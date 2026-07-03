# Legislative Health Factuality Project

A computational analysis of health-related legislative speech and vote outcomes in the US House of Representatives, the Ontario Legislative Assembly, and the Quebec National Assembly. The central research question: are legislators who make more factually supported health claims more likely to be on the winning side of health-related votes, and does this relationship differ across political systems?

**Collaborators:** Caprice Culkin, David Chartash, Joanie Bouchard

---

## Repository Structure

```
legislative-health-factuality/
├── scripts/          Python scripts for data collection and 
│   └── archive/      Superseded scripts kept for the documented 
├── data/
│   ├── us/           US bills, votes, policy areas, 
│   ├── canada/
│   │   ├── ontario/  Ontario Hansard transcripts
│   │   └── quebec/   Quebec committee transcripts and bill 
│   └── politifact/   Labeled health claims for calibration
└── .env              API keys (not committed to GitHub)
```

Note: large raw data files (VoteView votes CSV, full transcript directories) are excluded from GitHub via `.gitignore`. 
---

## Scripts

### US Data Collection

**`voteview_pull.py`**
Downloads House roll call vote data from VoteView (UCLA), the standard academic dataset for legislative voting behavior research. Filters to House only, 1985 to present. Produces three files: `house_rollcalls_1985_present.csv` (one row per vote), `house_votes_1985_present.csv` (one row per member per vote), and `house_members_1985_present.csv` (member biographical data). The VoteView votes file exceeds GitHub's 100MB file limit and is excluded from the repo.

**`extract_unique_bills.py`**
Reads the VoteView rollcalls file and pulls out every unique (Congress number, bill number) pair that had a recorded vote between 1985 and now. Produces `unique_voted_bills.csv` with 10,430 entries. This flips the bill-identification approach: rather than starting from a keyword search and hoping it's accurate, we start from every bill that actually got voted on and label each one with its real policy area next.

**`fetch_policy_areas.py`**
For each of the 10,430 unique bills, calls Congress.gov's subjects API endpoint and saves the official CRS policy area classification to a cache file (`policy_areas.json`). Congress.gov assigns every bill exactly one policy area term from a controlled vocabulary used consistently since 1979, a human-assigned, mutually exclusive classification rather than a keyword score. This script takes several hours to run and saves progress every 50 bills so it can be interrupted and resumed without losing work.

**`retry_blank_policy_areas.py`**
A cleanup pass that retries any bills that came back blank in the original `fetch_policy_areas.py` run due to transient API failures. Distinguishes between a genuine API failure (leaves blank, try again) and a bill that truly has no policy area assigned (`NONE_CONFIRMED`). After two passes, only 2 of 10,430 bills remained blank, both confirmed real API gaps rather than failures.

**`match_by_policy_area.py`**
Joins the VoteView rollcalls data back up with the policy area labels and filters to bills classified as "Health" by CRS. Produces `health_bills_final_matched.csv` with 384 unique health bills and 663 total vote events across 1985 to present. Note: VoteView only contains recorded roll call votes, not voice votes or unanimous consent votes. Bills that passed without a recorded tally are not in this dataset. For this project's research question, that is actually the right population, since a voice vote has no real winning or losing side to measure.

**`congress_pull.py`** (see also archive)
Pulls bill metadata from Congress.gov for the current Congress. Superseded for vote data by VoteView but still useful for pulling bill text, summaries, and subject data.

**`congressional_record_pull.py`**
Pulls daily issue-level data from the Congressional Record via the Congress.gov API. Each issue contains article titles and links to the actual floor speech text. This script pulls the metadata layer, not the speech text itself.

**`congressional_record_fulltext_pull.py`**
Follows the article links from `congressional_record_pull.py` and fetches the actual floor speech text for health-keyword-filtered articles. Still in progress. This is the step that gets the actual words legislators said, which is what the factuality scoring will eventually run on.

**`politifact_pull.py`**
Scrapes PolitiFact's health-tagged fact-checks: speaker, claim text, rating, and source context. Produces `data/politifact/health_claims.csv` with 300 labeled claims. These serve as a calibration set for the factuality scoring method, since they come with existing human expert verdicts to check against.

---

### Canadian Data Collection

**`ontario_hansard_pull.py`**
Crawls the Ontario Legislative Assembly Hansard backward from the most recent sitting day, following each page's "previous sitting day" navigation link, all the way to June 1985. Saves each sitting day's full transcript as a `.txt` file in `data/canada/ontario/`. Reached the 1985 boundary and produced 3,429 sitting day files. Avoids guessing parliament or session numbers entirely by using the site's own navigation links.

**`quebec_cheminement_pull.py`**
Pulls bill stage data from Quebec's Cheminement des projets de loi for all legislature sessions back to 1985. For each bill, collects the title, and links to all Assembly-level debate transcripts and committee-level debate transcripts associated with each stage of the bill's progress. Uses playwright-stealth to bypass the site's WAF bot detection. Saves progress after each session to `data/canada/quebec_bills/cheminement_all_sessions.json`. Currently running.

---

### Archive

Scripts in `scripts/archive/` are superseded earlier versions kept for the documented debugging trail. Two important bugs were caught and fixed during development:

**Bill number collision bug:** House bill numbers reset every two years. "HR 2493" in 2026 and "HR 2493" in 1987 are unrelated bills. Any matching logic must use Congress number together with bill number, not bill number alone.

**Type code collision bug:** LegiScan uses "HR" as a prefix for House Resolutions, while Congress.gov uses "HR" as a type code for House Bills. The same label means two different things across the two systems. A corrected type-code mapping is used in all current matching scripts.

**LegiScan relevance score limitation:** LegiScan's keyword relevance score measures how strongly the word "health" appears in a bill's text, not whether the bill is substantively about health policy. Even at relevance 90+, large omnibus bills containing one incidental mention of health funding matched as "health" bills. This led to the switch from keyword-based identification to Congress.gov's official CRS policy area classification.

---

## Data Sources

| Source | What It Provides | Access |
|---|---|---|
| VoteView (UCLA) | House roll call votes, 1789-present | Public download at voteview.com/data |
| Congress.gov API | Bill metadata, policy area classification, Congressional Record | Free API key at api.data.gov/signup |
| LegiScan API | Health-tagged bill search, bill text links | Free API key at legiscan.com/legiscan |
| Ontario Legislative Assembly | Hansard transcripts, 1985-present | Public at ola.org |
| Assemblée nationale du Québec | Bill cheminement, debate transcripts | Public at assnat.qc.ca |
| PolitiFact | Labeled health fact-checks | Public scrape |

---

## Key Methodological Notes

**Why VoteView instead of Congress.gov's vote API:** Congress.gov's house-vote endpoint was only introduced in 2025 and only covers the 118th Congress onward (2023+). VoteView provides the same data back to 1789 and is the standard academic source for roll call voting research.

**Why CRS policy area instead of keyword search:** Congress.gov assigns each bill exactly one official policy area, chosen by a human CRS analyst who read the actual bill, from a controlled vocabulary used consistently since 1979. This is a more reliable identifier than keyword relevance, which sweeps in large omnibus bills containing one incidental health mention.

**Why Ontario uses full Assembly debate while Quebec uses Cheminement:** Ontario's Hansard is collected as full sitting-day transcripts since there is no confirmed bill-level tracking structure equivalent to Quebec's Cheminement. Quebec's Cheminement provides direct links from each bill's stage to the specific Assembly debate transcript for that stage, enabling a cleaner bill-level linkage. Whether this structural difference between the two provinces requires methodological adjustment is an open question.

**On voice votes:** VoteView only contains recorded roll call votes. Many bills pass by voice vote with no individual tally. These are not in the dataset and cannot be added since no record of individual votes was ever created. The 384 health bills in the final matched dataset are those that were contested enough to warrant a recorded vote, which is the right population for a question about winning and losing sides.

---

## Environment Setup

```
python3 -m venv venv
source venv/bin/activate
pip install requests python-dotenv beautifulsoup4 lxml playwright playwright-stealth
python -m playwright install chromium
```

Create a `.env` file in the project root with your API keys:

```
LEGISCAN_KEY=your_key_here
CONGRESS_KEY=your_key_here
```

---

## AI Tool Usage

Python scripts for data collection and processing were developed with assistance from Claude (Anthropic). All API calls, data cleaning logic, and bug fixes were reviewed and run by Caprice Culkin. The two methodological bugs documented in the archive section (bill number collision and type code collision) were identified through manual inspection of matched output rather than automated detection.