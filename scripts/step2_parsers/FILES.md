# Step 2: parsers (was scripts/v4)

The parsers (spaCy, Stanza, the Berkeley parser for French, the discourse parser) and the concept step for DBpedia, from Oct 15 to 19. Step 3 still loads the parsers from here.

## Used by the full run

Step 3 loads the parsers through these.

- `benepar_fix.py`: Loads the Berkeley parser (benepar 0.2) so it works with current torch and transformers. Three known breakages are handled here: 1. torch 2 removed torch._six, which older helper packages still import. 2.
- `parse_corpus_v5.py`: Every predication from every sentence of a jurisdiction, the way the 100-sentence sample was done on Oct 15: two dependency parses (spaCy, Stanza) and a constituency parse (Stanza for English, the Berkeley parser's French ...

## Used by the DBpedia check

The concept step: which DBpedia page a phrase is.

- `concept_check.json`: 43 phrases whose DBpedia page was checked by hand on Oct 13 (right or wrong).
- `concepts_v3.py`: Concepts in DBpedia for every stated predication, then the Ciampaglia path score over the whole 2022 infobox graph (built by the full-graph run, kept in ~/.kg_dump).
- `full_graph_inputs.json`: The facts used to calibrate the walk score, and the debate claims scored on the full graph.
- `rel_linker.py`: The relational knowledge linker (KL-REL, Shiralkar, Tyagi, Flammini, Menczer and Ciampaglia 2017) on the full 2022 DBpedia graph, next to the plain knowledge linker (KL, Ciampaglia et al. 2015) we have used so far.

## Parser setup and the October runs

How the parsers were set up on the Mac and the runs of Oct 15, 16 and 19, from David's notes of the Oct 8 meeting.

- `build_update_wb2.py`: Workbook for David (next steps from the Oct 8 meeting): every step laid out plainly, with yes/no review columns. Times New Roman 11, black text, grey header boxes, yellow review columns.
- `ev_common.py`: Shared pieces for the Oct 16 evidence step: the full 2022 DBpedia graph from ~/.kg_dump (factual links only), the 300 judged facts, the debate statements from the Oct 15e concept run, and AUC computed two ways.
- `fr_const_run.py`: French constituency trees for the French sentences (the 50 in the sample and the held-out ones), with the Berkeley Neural Parser's French model (benepar_fr2, trained on the French Treebank).
- `fr_setup.py`: Checks, one by one, what the Berkeley parser needs, installs only what is missing, and says exactly what went wrong if something cannot be installed. Exit 0 means the parser imports and part 1 can run.
- `fr_side_env.sh`: Second route for part 1. Builds a small side environment (~/.benepar_side_venv) that sees every package of the venv you run from, but with transformers 4.30.2 in front of it: the last version from before the changes that broke ...
- `rst_run.py`: Discourse parse (RST for English, SDRT for French) of the 100 spot-check sentences with the IsaNLP UniRST parser (one multilingual model; English uses the RST-DT relation set, French the ANNODIS SDRT set). Reads only.
- `run_compare.py`: (reads only; writes ~/Desktop/parser_comparison.xlsx and ~/Desktop/parser_comparison.json) Every predication in the 100 spot-check sentences, four ways: spaCy dependency parse, Stanza dependency parse, Stanza constituency tree, ...
- `run_full_parse.sh`: The whole corpus through the three parses, the two-of-three vote and the discourse re-read. For after the Oct 19 meeting. Writes data/dbpedia_pipeline/{us,ontario,quebec}/statements_v5.jsonl, one line per sentence, as it goes.
- `run_oct15.sh`: David's Oct 8 notes, the parts still open. Reads only; writes ~/Desktop/next_steps/oct15/. 1. French constituency trees (Berkeley parser, benepar_fr2), so French also has all three parses 2.
- `run_oct16.sh`: Two other groups' methods, tried on our data. Reads only; writes ~/Desktop/next_steps/oct16/. 1. relation-aware path score (KL-REL, Shiralkar et al.
- `run_oct19.sh`: Overnight, before the Oct 19 meeting. Reads only; writes ~/Desktop/next_steps/oct19/. 1.
- `statements_v4.py`: Predications from all three parses together (David, Oct 8): spaCy dependency, Stanza dependency and the constituency parse (Stanza for English, the Berkeley parser for French), kept when at least two agree, with the discourse ...
- `text_evidence.py`: Checking claims against Wikipedia text instead of DBpedia's links (the FEVER-style approach; Chen et al. 2023 do the same for PolitiFact claims with web search). For each claim: 1.
- `text_evidence_v2.py`: Checking claims against Wikipedia text (the FEVER-style approach), second version with the retrieval fix from the Oct 16 workbook: a Wikipedia sentence only counts as evidence when it mentions BOTH ends of the claim (or comes ...

## Older copies of the rules and answer keys

The rules as they were on Oct 19 (v5). Step 3 has the current ones. Kept because the Oct 19 corpus parse used these.

- `combine_lib.py`: All three parses together (David, Oct 8): keep a predication when at least two of the syntactic parses produce it (spaCy dependency, Stanza dependency, constituency), then use the discourse (RST) parse to decide how each one is ...
- `const_fr.py`: Predications from a French Treebank (FTB) constituency tree, as produced by the Berkeley parser's French model (benepar_fr2).
- `discourse.json`: The saved discourse parses of the 100 sample sentences.
- `gold.py`: Answer key: every predication in 20 sentences from the v19 sample, drafted with Claude, to be checked by Caprice (English) and Joanie (French).
- `gold2.py`: Answer key, part 2: the other 80 sentences of the v19 sample, drafted with Claude from the sentence text alone (before looking at any method's output for them), same rules as gold.py.
- `gold_heldout.py`: Held-out answer key: 30 sentences drawn at random (seed 20261012) from the 1,380 tested parses, none in the 100-sentence sample, written from the sentence alone before any output was looked at.
- `heldout.json`: The 30 held-out test sentences, never looked at while the rules were written.
- `pc.json`: The 100 sample sentences with their saved parses.
- `preds.py`: Every predication in a sentence, from a dependency parse (spaCy or Stanza) or a constituency tree (Stanza).
