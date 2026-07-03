# Legislative Health Factuality Project

A computational analysis of health-related legislative speech and vote outcomes across three legislative bodies: the US House of Representatives, the Ontario Legislative Assembly, and the Quebec National Assembly. The central research question is whether legislators who make more factually supported health claims are more likely to be on the winning side of health-related votes, and whether this relationship differs across political systems.

**Collaborators:** Caprice Culkin (Yale School of Public Health), David Chartash (Yale), Joanie Bouchard (Université de Sherbrooke)

---

## Repository Structure

```
legislative-health-factuality/
├── scripts/            Python scripts for data collection and processing
│   └── archive/        Superseded scripts kept for the documented debugging trail
├── data/
│   ├── us/             US bills, votes, policy areas, and Congressional Record metadata
│   ├── canada/
│   │   ├── ontario/    Ontario Hansard transcripts, 1985-present
│   │   └── quebec/     Quebec Health and Social Services Committee transcripts
│   └── politifact/     Labeled health claims for factuality scoring calibration
└── .env                API keys, not committed to GitHub
```

Large raw data files including the VoteView votes CSV and full transcript directories are excluded from the repository via `.gitignore`. These live locally on Caprice's machine and can be shared via Google Drive on request.

---

## Scripts

### US Data Collection

**`voteview_pull.py`**
Downloads the three core VoteView datasets from UCLA and filters them down to House-only rows from the 99th Congress onward (1985 to present). VoteView is the standard academic dataset for legislative voting behavior research and underlies DW-NOMINATE, the gold standard for political classification. It was chosen over Congress.gov's own vote API because that endpoint was introduced in 2025 and only covers the 118th Congress onward, making it unusable for historical work. The three output files are `house_rollcalls_1985_present.csv` (one row per recorded vote), `house_votes_1985_present.csv` (one row per member per vote), and `house_members_1985_present.csv` (member biographical data). The votes file exceeds GitHub's 100MB file size limit and is excluded from the repository.

**`extract_unique_bills.py`**
Reads the VoteView rollcalls file and extracts every unique Congress number and bill number pair that had at least one recorded vote between 1985 and present. Produces `unique_voted_bills.csv` with 10,430 entries. This flips the bill-identification approach: instead of starting from a keyword search and hoping it accurately captures health legislation, the pipeline starts from every bill that actually got voted on and labels each one with its official policy area in the next step.

**`fetch_policy_areas.py`**
For each of the 10,430 unique bills, calls Congress.gov's subjects API endpoint and saves the official CRS policy area classification to a local cache file called `policy_areas.json`. Congress.gov assigns every bill exactly one policy area from a controlled vocabulary used consistently since 1979, chosen by a human CRS analyst who read the actual bill. This replaced LegiScan's keyword relevance score, which was producing false positives by sweeping in large omnibus bills that happened to mention "health" once in hundreds of pages. The script takes several hours to run and saves progress every 50 bills so it can be interrupted and resumed without losing work.

**`retry_blank_policy_areas.py`**
A cleanup script that retries any bills that came back blank in the original `fetch_policy_areas.py` run due to transient API failures. It correctly distinguishes between a genuine network failure (leaves the entry blank so it can be retried) and a bill that truly has no policy area assigned in Congress.gov's system (marks it as `NONE_CONFIRMED`). After two passes over the full 10,430 bills, only 2 entries remained blank, both confirmed as real data gaps rather than failures.

**`match_by_policy_area.py`**
Joins the VoteView rollcalls data with the policy area labels from `policy_areas.json` and filters to bills where the CRS officially classified the policy area as "Health." Produces `health_bills_final_matched.csv` with 384 unique health bills and 663 total vote events across 1985 to present. VoteView only contains recorded roll call votes, not voice votes or unanimous consent votes, so bills that passed without a recorded individual tally are not in this dataset. For this project's research question, that is the appropriate population since a voice vote has no real winning or losing side to measure.

**`congressional_record_pull.py`**
Pulls the full paginated list of daily Congressional Record issues from Congress.gov and saves each issue's article metadata (titles and links to speech text) to disk. This is the production version that loops through all available issues. Skips issues already saved so it can be safely stopped and restarted. For a lightweight test pull of 20 issues, see `congressional_record_pull_test.py`.

**`congressional_record_pull_test.py`**
Lightweight version of `congressional_record_pull.py` that pulls only 20 issues. Used to verify the API connection and inspect the article metadata structure before running the full pull.

**`congressional_record_fulltext_pull.py`**
Reads the article metadata files produced by `congressional_record_pull.py`, filters to health-keyword-related articles, and fetches the actual floor speech text behind each article link. This is the step that gets the actual words legislators said, which is what the factuality scoring method will eventually run on. Still in progress.

**`politifact_pull.py`**
Scrapes PolitiFact's health care fact-check listings and saves each claim with the speaker, claim text, truth rating, context, and source URL to `data/politifact/health_claims.csv`. The 300 resulting claims serve as a calibration set for the factuality scoring method, since they already come with professional fact-checker verdicts that can be used as a ground truth baseline before applying any scoring to unlabeled legislative speech.

---

### Canadian Data Collection

**`ontario_hansard_pull.py`**
Crawls the Ontario Legislative Assembly Hansard backward from a known recent sitting day, following each page's built-in "previous sitting day" navigation link all the way back to June 1985. Saves each sitting day's full transcript as a plain text file in `data/canada/ontario/` named by date. This approach avoids guessing parliament or session numbers entirely since the site's own navigation handles all transitions between parliaments automatically. Produced 3,429 sitting day files covering June 1985 through present. If the script hits a temporary server error it waits 10 seconds and retries rather than stopping.

**`quebec_cheminement_pull.py`**
Pulls bill stage data from Quebec's Cheminement des projets de loi across all legislature sessions back to 1985. The Cheminement is a per-bill tracking page that lists every formal stage a bill passes through, with direct links to the specific Assembly debate transcripts associated with each stage. This was chosen over committee-level transcripts because votes in Quebec happen at the Assembly level, not the committee level: committee work covers amendments to specific clauses, while the two votes that matter for this project (adoption du principe and adoption finale) both happen in the full Assembly. Uses playwright-stealth to bypass the site's WAF bot detection. Saves progress after each session to `data/canada/quebec_bills/cheminement_all_sessions.json`. Currently running.

---

### Archive

Scripts in `scripts/archive/` are superseded earlier versions kept for the documented debugging trail. Three methodological problems were caught and fixed during development and are worth understanding before extending any of the current scripts.

**Bill number collision:** House bill numbers reset every two years, so "HR 2493" in 2026 and "HR 2493" in 1987 are completely unrelated bills. Any matching logic must use the Congress number together with the bill number, not the bill number alone.

**Type code collision:** LegiScan uses "HR" as a prefix for House Resolutions, while Congress.gov uses "HR" as the type code for House Bills. The same label means two different things across the two systems. A corrected type-code mapping is used in all current matching scripts.

**LegiScan relevance score limitation:** LegiScan's keyword relevance score measures how strongly the word "health" appears in a bill's text, not whether the bill is substantively about health policy. Even at relevance 90 or higher, large omnibus bills containing one incidental mention of health funding still matched as health bills, including the National Defense Authorization Act and the Coast Guard Authorization Act. This led to the switch from keyword-based identification to Congress.gov's official CRS policy area classification.

---

## Data Sources

| Source | What It Provides | Access |
|---|---|---|
| VoteView (UCLA) | House roll call votes, 1789-present | Public download at voteview.com/data |
| Congress.gov API | Bill metadata, policy area classification, Congressional Record | Free API key at api.data.gov/signup |
| LegiScan API | Health-tagged bill search, bill text links | Free API key at legiscan.com/legiscan |
| Ontario Legislative Assembly | Hansard transcripts, 1985-present | Public at ola.org |
| Assemblée nationale du Québec | Bill cheminement, Assembly debate transcripts | Public at assnat.qc.ca |
| PolitiFact | Labeled health fact-checks | Public scrape |

---

## Key Methodological Notes

**Why VoteView instead of Congress.gov's vote API:** Congress.gov's house-vote endpoint was introduced in 2025 and only covers the 118th Congress onward (2023+). VoteView provides the same data back to 1789 and is the standard academic source for roll call voting research.

**Why CRS policy area instead of keyword search:** Congress.gov assigns each bill exactly one official policy area, chosen by a human CRS analyst who read the actual bill, from a controlled vocabulary used consistently since 1979. This is substantially more reliable than keyword relevance scoring, which sweeps in large omnibus bills containing one incidental health mention.

**Why Ontario uses full Assembly debate while Quebec uses Cheminement:** Ontario's Hansard is collected as full sitting-day transcripts since there is no confirmed bill-level tracking structure equivalent to Quebec's Cheminement. Quebec's Cheminement provides direct links from each bill's stage to the specific Assembly debate transcript for that stage, enabling cleaner bill-level linkage. Whether this structural difference between the two provinces requires methodological adjustment is an open question being discussed with the team.

**On voice votes:** VoteView only contains recorded roll call votes. Many bills pass by voice vote with no individual tally recorded. These cannot be added to the dataset since no record of individual votes was ever created. The 384 health bills in the final matched dataset are those contested enough to warrant a recorded vote, which is the appropriate population for a question about winning and losing sides.

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

Python scripts for data collection and processing were developed with assistance from Claude (Anthropic). All API calls, data cleaning logic, and bug fixes were reviewed and run by Caprice Culkin. The methodological bugs documented in the archive section were identified through manual inspection of matched output rather than automated detection.