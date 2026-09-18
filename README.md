# Legislative Health Factuality

Does the factual accuracy of legislative health floor debate predict bill passage outcomes? This project builds a pipeline to score factuality of health bill debates in the US House of Representatives, Ontario Legislative Assembly, and Quebec National Assembly from 1985 to 2026.

**Investigators:** Caprice Culkin (Yale School of Public Health) with David Chartash and Joanie Bouchard.

---

## Pipeline

\`\`\`mermaid
flowchart TD
    A["GovInfo API\nUS Congressional Record\n145 health bill-dates"] --> D["US Floor Debate\n448 files\n584K sentences"]
    B["OLA Azure Search API\nOrders of the Day filter\nbill number verified in text"] --> E["Ontario Bill Segments\n249 verified bills\n83K paragraphs"]
    C["assnat.qc.ca\nJournal des debats\nsection marker extraction"] --> F["Quebec Bill Segments\n11K bill-date files\n924K sentences"]
    D --> G["spaCy SVO Extraction\nUS 215K predi    D --> G["spaCy SVO Extraction\nUS 215K predi    D --> G["spaCy SVO Extraction\nUS 215K predi   H    D --> G["spaCy SVO Extractubj    D --> G["spaCy SVO Extraction\nUS 215K predi    D --> G["spaCy SVO Extraction\nUS 215K predi    D --> G["spaCy SVO Extraction\nUS 215K predi   H    D --> G["spaCy SVO Extractubj    D --> G["spaCy SVO Extraction\nUS 215K predi    D --> G["spaCy SVO Extraction\nUS 215K predi 
[Interactive pipeline diagram](https://capriceculkin.github.io/legislative-health-factuality/pipeline_diagram.html[Interactik a[Innode to see file paths, example text, GitHub links, and access notes.

[DATA_README.md](https://github.com/capriceculkin/legislative-health-factu[DATA_README.md](https://github.com/capriceculkin/legislative-health-factu[DATA_README.md](https://github.com/capriceculkin/legislative-health-factu[DAan[DATA_README.md](https://github.com/capriceculkin/legislative-health-factu[DATA_README.md](https://github.com/capriceculkin/legislativyy[DATA_README.md](https://github.com/capriceculkin/legislative-health-factu[DATA_README.md](https://github.com/capriceculkin/legislative-health-factu[DATA_README.md](https://github.com/capriceculkin/legislative-health-factu[DAan[DATA_README.md](https://github.com/capriceculkin/legislative-health-factu[DATA_README.md](https://github.com/capriceculkin/legislativyy[DATA_README.md](https://github.com/capriceculkin/legislative-health-factu[DATA_README.md](http regression on US and Quebec combined: factuality coefficient +0.0467 (p less than 0.05).

COVID natural experiment: US factuality decreased 0.036 post-March 2020. Quebec decreased 0.053.
