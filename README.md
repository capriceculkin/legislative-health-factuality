# Legislative Health Factuality

Does the factual accuracy of legislative health floor debate predict bill passage outcomes? This project scores factuality of health bill debates in the US House of Representatives, Ontario Legislative Assembly, and Quebec National Assembly from 1985 to 2026.

**Investigators:** Caprice Culkin (Yale School of Public Health) with David Chartash and Joanie Bouchard.

---

## Pipeline

```mermaid
flowchart TD
    A["GovInfo API"] --> D["US Floor Debate
448 files, 584K sentences"]
    B["OLA Azure Search API"] --> E["Ontario Bill Segments
249 bills, 83K paragraphs"]
    C["assnat.qc.ca"] --> F["Quebec Bill Segments
11K files, 924K sentences"]
    D --> G["spaCy SVO Extraction
US 215K | Quebec 178K | Ontario pending"]
    E --> G
    F --> G
    G --> H["DBpedia Spotlight
Subject and object strings only"]
    H --> I["SPARQL Verification
Local Virtuoso"]
    I --> J["Factuality Scores
supported / total claim-bearing"]
\\\
############################################ram############################################ram############################################ram############################################ram############################################ram############################################ram#######################.md############################################ram############################################ram##########ll segme#####n Yale OneDrive](https###########my############################################ram##########################1erpw############################################ram############################################
VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV meaVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVn VVVtuality 0.1387. Passed 0.1266 (n=767).

Ontario: pipeline running.

Logistic regression on US and Quebec combined: factuality coefficient +0.046Logistic regression on US and Quebec combined: factuality coefficie post-March 2020. Quebec decreased 0.053.
