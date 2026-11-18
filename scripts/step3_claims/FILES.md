# Step 3: claims (was scripts/v6)

Discourse first, the design from the Oct 22 meeting with David and Joanie: each sentence is cut into discourse units, each unit gets a constituency tree, and the claims (subject, verb, object) are read from the trees. This folder has the rules, the tests, the DBpedia check on the sample, and the full run. Every file is listed below with what it does.

## The full run (current)

Start here. The whole corpus, discourse first, then claims, then exports. David asked on Nov 13 for an export at each step, which is what export_steps.py writes.

- `export_steps.py`: Plain CSV files for each step of the full run, for sharing.
- `run_full.sh`: The full parse for one legislature. Keeps the Mac awake, writes a log, and starts again by itself after a crash (finished chunks are kept).
- `run_full_corpus.py`: Discourse first, on the whole corpus, in chunks that can be stopped and restarted.

## The rules that read claims

The code the full run uses to turn parses into claims.

- `combine_lib.py`: All three parses together (proposed in the Oct 8 meeting): keep a predication when at least two of the syntactic parses produce it (spaCy dependency, Stanza dependency, constituency), then use the discourse (RST) parse to decide ...
- `const_fr.py`: Predications from a French Treebank (FTB) constituency tree, as produced by the Berkeley parser's French model (benepar_fr2).
- `edu_pipeline.py`: Discourse first (design agreed Oct 22): the discourse parse cuts each sentence into elementary discourse units (EDUs); the constituency tree of each unit gives the subject | verb | object lines inside it; the discourse relations ...
- `frames.py`: PropBank-style frames from a UD tree, one mapping for English and French (design 2, step 4).
- `full.py`: Full predications from the kept lines of the two-of-three vote (design 1), the same way in English and French.
- `lexicon.py`: Every word list the rules use, written once, as English-French pairs.
- `preds.py`: Every predication in a sentence, from a dependency parse (spaCy or Stanza) or a constituency tree (Stanza).

## Parsing on the Mac

These load the real parsers, so they only run on the Mac with the venv.

- `edu_collect.py`: Discourse first, on this Mac, with the real parsers (design from the Oct 22 meeting).
- `machine_info.py`: What machine and software the parses ran on (asked in the Oct 20 meeting). Writes outputs/machine.txt. Reads only.
- `parity_collect.py`: Runs every parser on three sets of sentences and saves the raw parses, so English and French can be scored side by side with any version of the rules (parity_score.py), without parsing again.
- `udpipe_parse.py`: UDPipe 1.4 (UD 2.5 models: English EWT, French GSD) on the backbone's own words (Stanza), one sentence per line, so both parses have the same tokens and can be compared word by word.
- `wsj_collect.py`: Parses the Penn Treebank sample's sentences with the pipeline's own parsers (spaCy en_core_web_lg, Stanza English with its constituency parser), in the same row format as parity_parses.json, so wsj_score.py can score every method ...

## Answer keys and saved test sentences

Claims written out for test sentences, and the saved parses the tests read.

- `discourse.json`: The saved discourse parses of the 100 sample sentences.
- `fr_trees.json`: The saved Berkeley parser trees for the French sample sentences.
- `gold.py`: Answer key: every predication in 20 sentences from the v19 sample, drafted with Claude, to be checked by Caprice (English) and Joanie (French).
- `gold2.py`: Answer key, part 2: the other 80 sentences of the v19 sample, drafted with Claude from the sentence text alone (before looking at any method's output for them), same rules as gold.py.
- `gold_heldout.py`: Held-out answer key: 30 sentences drawn at random (seed 20261012) from the 1,380 tested parses, none in the 100-sentence sample, written from the sentence alone before any output was looked at.
- `hand_check_score.py`: A person's check of the claim sample (docs/hand_check_sample.xlsx, filled in) set beside the two AI readers' verdicts (outputs/edu/hand_check_sample_key.json, kept apart so the person does not see them).
- `heldout.json`: The 30 held-out test sentences, never looked at while the rules were written.
- `pc.json`: The 100 sample sentences with their saved parses.
- `ptb_gold.py`: A gold standard made by people, before AI: the Penn Treebank (Marcus, Santorini and Marcinkiewicz 1993; function tags and traces from Treebank II, Marcus et al. 1994).
- `split_check_make.py`: Builds the hand check of sentence breaks (the step 2 gold standard).
- `split_check_template.html`: The page layout that split_check_make.py fills in.

## Tests and scores

Each one measures the rules against the answer keys or compares two versions.

- `compare3.py`: How each of the three parsers does alone, against the vote, on the same sentences and the same keys.
- `dep_disagree.py`: Question from the Oct 20 meeting: "Are the differences between the two dependency parses useful?"
- `edu_keydiff.py`: Every answer-key line whose result changed between two runs of edu_pipeline.py (found or exact, on the 100-sentence key, the held-out key and the simple test pairs), with the output line before and after, and a count of how many ...
- `edu_rule_effects.py`: What each repair rule changes. For every sentence: the claims with all rules on, the claims with each rule switched off one at a time (kept only when they differ), and the claims at each stage of the rules (no rules, rounds 1 to ...
- `edu_score.py`: The discourse-first lines (edu_pipeline.py) against the same answer keys as the earlier designs, scored the same way for every method: found = the vote's loose match test (preds.py align); exact = subject, verb and object word ...
- `edu_trace_stages.py`: For the sentences named, the full output at each stage of the rules (no repair rules, rounds 1 to 5, round 6, 6b, 7), so a claim can be followed step by step.
- `eval_roles.py`: The design-2 frame mapping (frames.py) scored against Universal Proposition Bank 1.0 test sets, the same way in both languages.
- `keydiff.py`: Answer-key lines found by A but not by B (and the reverse), and lines whose label changed, at every stage, on the held-out key and the 100-sentence key.
- `parallel_tests.py`: The same sentence in English and French, one construction at a time, with the lines the pipeline should produce. Every construction has both languages, so a pass rate in one can be set beside the other.
- `parity_score.py`: Scores saved parses against an answer key, the way the full run treats a sentence.
- `pronouns.py`: How often a claim's subject or object is a pronoun or a stand-in instead of a name, so the size of the entity problem raised in review (names hidden behind pronouns and replacements) is measured before any coreference step is ...
- `score.py`: what the vote leaves for review, the stated/embedded/reported label, negation and hedging. Prints JSON.
- `strict.py`: A strict score next to the loose one, for the three-slot lines and for the full predications.
- `ud_eval.py`: The step 3 gold standard: how accurate our own dependency parsers are, measured by us, on the human annotated Universal Dependencies test sets (never used to train these models' test scores).
- `wsj_check.py`: Constituency rules run on the treebank's own gold trees (function tags like -SBJ removed), so a wrong line there is a rule error, not a parser error. Dependency rules run on a UDPipe 1.4 (UD 2.5 EWT) parse of the same words.
- `wsj_diff.py`: Which Penn Treebank gold lines changed from exactly right to not (and the reverse) between two versions of the rules, for one method.
- `wsj_score.py`: Scores every method (each parser alone, the 2-of-3 vote, the tree-first designs) against the Penn Treebank's own human annotation, turned into gold lines by ptb_gold.py.

## DBpedia check on the sample

Links the claims of the sample sentences to DBpedia and scores the walk. Not yet run on the full corpus.

- `edu_dbpedia.py`: Finds the DBpedia concepts at the subject and object of every claim, and the walk between them, as asked for at the Oct 22 meeting.
- `edu_dbpedia_book.py`: The DBpedia step, every part: method with exact settings, all counts, worked examples, and a workbook with every candidate, every claim end and every walk for all 190 sentences.
- `edu_dbpedia_senses.py`: The share of claims with both ends in DBpedia again, counting only concepts whose page was judged the right sense in SENSE_CHECK.csv (columns word, page, reading_A, reading_B). Strict: both readings say right.
- `edu_dbpedia_sheet.py`: dsheet.py EDU_DBPEDIA.json SPOTLIGHT_RAW.json SENSE_CHECK.csv WALK_BASELINE.json OUT.xlsx The DBpedia step in two tabs: one row per claim (both ends, pages, how found, sense readings, walk), and every Spotlight candidate.
- `edu_dbpedia_xlsx.py`: The DBpedia check (edu_dbpedia.py) as a workbook to read and mark: a start page, every claim with the concepts at its two ends and why an end has none, every concept once (word and page) to mark right or wrong, the reasons ...
- `edu_walk_baseline.py`: Is a short walk between a claim's two concepts evidence for the claim? For every claim whose two ends have a concept judged the right sense (lenient: either reading says right), the walk score of the real pair is set beside the ...
- `run_dbpedia.sh`: Which claims have DBpedia concepts at their ends, why not, and the walk between them (asked for at the Oct 22 meeting).

## Figures, books and workbooks

These make the things people look at: tree figures, the check book, the Excel workbooks, the notebook.

- `build_disc_nb.py`: Writes the discourse-first notebook (the Oct 22 design, step by step, with its tests); with --run, also executes every cell in one Python process and stores the outputs (text, tables, figures) in the notebook, so it opens with ...
- `design2.py`: Scores the one-backbone design on the same saved parses as the current design.
- `design2_full.py`: The proposal, built end to end, on the same saved parses as design 1.
- `discourse_window.py`: The discourse parse of each answer-key sentence again, this time with the sentence before and the sentence after it (same bill, same day), so one sentence and a three-sentence window can be compared in both languages.
- `edu_check_book.py`: A check book for reading the output by hand: one sentence per page with its tree-inside-a-tree figure (edu_draw, simple=True), the discourse relations written as "unit 0 and unit 1 to unit 2", every claim the pipeline read from ...
- `edu_draw.py`: The "tree inside a tree" figure (Oct 22): the discourse tree drawn the way Mann and Thompson draw RST analyses, with each unit's constituency tree in place of the unit's number at the bottom.
- `edu_examples_docx.py`: examples_docx.py TRACE.json PARSES.json READINGS.csv FIG_PNG_DIR OUT.docx The examples as a Word file (Times New Roman 12, single spaced) that converts cleanly to Google Docs: same content as simple_book.py, figures as ...
- `edu_examples_simple.py`: simple_book.py TRACE.json PARSES.json READINGS.csv OUT.html A short examples document: for each sentence, its units, how they relate, and the claims, with the two readings.
- `edu_figure_files.py`: The "tree inside a tree" figure for each chosen sentence as its own file, for GitHub and for slides: the discourse relations drawn the Mann and Thompson way on top, and each unit's own constituency tree underneath ...
- `edu_figures.py`: The "tree inside a tree" figures: for each sentence, the discourse tree drawn over its units (Mann and Thompson style: a bar over the units each relation joins, the main part marked), the constituency tree of every unit drawn out ...
- `edu_steps_book.py`: Builds the step-by-step examples book: every step for each example sentence, from the raw sentence to the readers' verdicts.
- `edu_xlsx.py`: Discourse first (the Oct 22 design) as one Excel workbook, in the same layout as parser_examples.xlsx: a start page, a page to go through together, flow pages that carry one sentence through every step, then one page per step ...
- `examples_flow.py`: Flow sheets for examples_xlsx.py: one sentence read top to bottom through every step, in plain words, with the real output of each step.
- `examples_xlsx.py`: Every example sentence through every step, as one Excel workbook: one sheet per step, one row per word, line or triple, so the examples can be read, sorted and filtered.
- `examples_xlsx_docs.py`: Text for the documentation sheets of examples_xlsx.py: how each step works, where every file comes from, what each label means, and the questions a reviewer is likely to ask.

## Run scripts for the sample

Each runs a whole set of the steps above on the sample sentences.

- `run_all.sh`: Every number on the walkthrough page, recomputed from the parses saved on Oct 19. No parser runs, nothing outside outputs/scores_v6b/ changes. Plain python3, no packages. A few minutes.
- `run_edu.sh`: Discourse first (the Oct 22 design), end to end on this Mac: the discourse parse, every discourse unit parsed on its own by the constituency parser, 20 new sentences per legislature, the lines, the scores, the figures and the ...
- `run_parity.sh`: English-French parity check (Oct 20). Reads only; writes ~/Desktop/next_steps/oct20/.

## About this folder

- `README.md`: What this folder was made for and how its numbers were checked (written Oct 19 to 20).
