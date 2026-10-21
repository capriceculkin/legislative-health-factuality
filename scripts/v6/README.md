# scripts/v6: English-French parity and full predications (Oct 19 to 20, 2026)

This folder makes the predication rules treat English and French the same way, and measures whether they do.
It does not change the full-corpus run: `data/dbpedia_pipeline/*/statements_v5.jsonl` were made with the v5 rules
in `scripts/v4/`. Every full-run number stays a v5 number until the corpus is parsed again with these rules.

The code was written with AI assistance. The answer keys and the parallel test sentences were first drafted with AI
assistance and are being checked by hand (English: Caprice; French: Joanie).

## Run everything yourself

    cd ~/MiscellaneousProjects/legislative-health-factuality && bash scripts/v6/run_all.sh

Plain `python3`, no packages, a few minutes. It recomputes every number below and on the walkthrough page
(`outputs/predication_walkthrough.html`) from the saved parses, writes them to `outputs/scores_v6b/`, and prints the
headline numbers next to the values the page states. No parser runs; parsing again is `run_parity.sh` on the Mac.

## What changed from v5

1. **One paired word list** (`lexicon.py`). Every word list the rules use (negation, hedges, speech verbs,
   linking words, attribution sources, pronouns, the words ignored when matching) is written once, as
   English-French pairs. `python3 lexicon.py` fails if any meaning is missing a side.
2. **v6 (Oct 19): 16 mismatches fixed.** Examples: `devrait` was a hedge in French while `should` was not one in
   English; the French conditional of ordinary verbs (`réduirait`) was never a hedge while `would lower` was; the
   French constituency rules had no "said that" rule, so French tree lines could never be reported; the matching
   stop list was missing 34 function words, mostly French (`avec`, `notre`, `son`, `était`), which made French
   matching looser than English.
3. **v6b (Oct 20): fixes found by running the parallel tests on real parses.**
   - The vote keeps the majority's label and hedge when all three parsers agree, not spaCy's.
   - The discourse step finds the attribution source by its words (said, dit, according to, selon), not by
     nuclearity: French attribution comes out of UniRST with the opposite nucleus to English.
   - "according to / selon" makes a clause reported; "I think / je pense" (first person, not negated, not a wh- or
     si clause) is the speaker's own framing, as the answer key treats "we know" (#35).
   - Several-word linking words (`à moins que`, `jusqu'à ce que`, `even if`), adverbial clauses parsed as
     complements (`parce que`), appositions after a full name, copula-like verbs (`reste ouverte`), quantity
     adverbs (`gagnent moins`), light-verb nouns kept in the verb (`prend fin`, `se rendre compte`).
   - "recommends / shows / finds that X" makes X reported in both languages (answer key #38), and a stray closing
     quotation mark at the start of a sentence no longer marks the whole sentence as a quote.

4. **Full predications (Oct 20), `full.py`.** Prompted by the two sentences walked through in the Oct 19 meeting. Each kept
   line now carries every argument of its verb (to whom, for what, when, how), negation inside an argument ("not to
   themselves but off to others"), a time phrase that opens the sentence carried to the clauses joined to it (marked
   inherited), an unstated object marked as unstated (with the object of a contrasting clause as an inferred
   candidate), and links between lines with the linking word and the discourse relation. "That is why X" becomes a
   link. Each line takes the wording two of the parsers agree on. The two-of-three vote itself is unchanged.
5. **Strict scoring (Oct 20), `strict.py` and `compare3.py`.** The loose test (verb shares a word or 4 letters,
   subject and object share one content word) counted "sending | their premiums" as right without "to others". The
   strict score asks for subject, verb and object equal to the key, and is reported next to the loose one, with 95%
   intervals, McNemar tests and sentence-level bootstrap intervals for every comparison.

## Results (all on the parses saved on Oct 19, `data/parity_oct19/parity_parses.json`)

Parallel test pairs, passed out of 45 per language (the fixes were found on these, so this is optimistic):

| Rules | English | French |
|---|---|---|
| v5 | 39 | 31 |
| v6 | 41 | 32 |
| v6b | 44 | 45 |

Answer keys (key lines found by the final output / key lines; never used to write rules: the held-out key):

| | 100-sentence EN | 100-sentence FR | held-out EN | held-out FR |
|---|---|---|---|---|
| v5 | 107/119 | 93/116 | 29/36 | 25/33 |
| v6b | 108/119 | 94/116 | 30/36 | 25/33 |

Right labels (stated / embedded / reported) went from 26 to 28 (English) and 23 to 25 (French) on the held-out key,
and from 102 to 106 (English) and 84 to 87 (French) on the 100-sentence key. From v5 to v6b no answer-key line was lost at any stage (`keydiff.py`), and one label got worse: #99 in the final
output, where two of the three parsers read the clause as a complement, so the majority label is embedded. The numbers were checked two ways: through
`combine_lib.evaluate` (`score.py`) and through the full-run path (`parity_score.py`); both give 108/119 and 94/116.

Design 1 (three parsers, two-of-three vote) against design 2 (one Stanza backbone), `design2.py`:

| 100-sentence key | found | share of output in the key |
|---|---|---|
| EN design 1 | 108/119 | 87% |
| EN design 2a (every Stanza line) | 102/119 | 81% |
| FR design 1 | 94/116 | 78% |
| FR design 2a | 95/116 | 71% |


Strict score, all three slots exact, full predications (`compare3.py`; the exact counts were also checked by a plain
string comparison of every key line with every output line):

| 100-sentence key | spaCy alone | Stanza alone | tree alone | vote |
|---|---|---|---|---|
| English (119 lines) | 54 | 63 | 53 | 60 |
| French (116 lines) | 26 | 42 | 32 | 34 |
| held-out English (36) | 18 | 17 | 17 | 21 |
| held-out French (33) | 9 | 11 | 8 | 9 |

In English the vote is at least as good as any one parser, but the only clear difference is against spaCy alone
(exact, p = 0.03). In French, Stanza alone gets more lines exactly right than the vote (11 against 3, p = 0.06,
bootstrap interval -12.7 to -1.6 points), while the vote keeps fewer lines that are not in the key (27 against 37).
Part of the low exact score is the key itself: it has one object slot, so it leaves out parts a full predication
carries. The key needs a slot for each part before the strict score can be final.

## Files

| File | What it is |
|---|---|
| `lexicon.py` | the paired English-French word lists |
| `preds.py`, `const_fr.py`, `combine_lib.py` | the v6b rules, the vote and the discourse re-read |
| `parallel_tests.py` | 45 constructions, each in English and French, with the expected lines |
| `parity_collect.py`, `run_parity.sh` | parses the test pairs, the held-out key and the 100-sentence sample with every parser and saves the raw parses (run on the Mac) |
| `parity_score.py` | scores any rule version on saved parses, the way the full run treats a sentence |
| `design2.py` | scores the one-backbone design on the same parses |
| `keydiff.py` | lists every answer-key line gained or lost between two rule versions |
| `score.py` | second scoring path, through `combine_lib.evaluate` |
| `full.py` | full predications: every argument, negation inside arguments, inherited time, unstated objects, links between lines |
| `strict.py` | loose against exact score, three-slot lines against full predications |
| `compare3.py` | each parser alone against the vote, with McNemar tests, bootstrap intervals and how often the parsers agree |
| `frames.py`, `eval_roles.py` | PropBank-style roles from the UD tree, scored against Universal Proposition Bank 1.0 |
| `run_all.sh` | recomputes every score and prints the headline numbers |
| `wsj_check.py`, `udpipe_parse.py`, `design2_full.py`, `discourse_window.py` | Penn Treebank check, UDPipe parses, design 2 end to end, discourse on a three-sentence window |
| `gold.py`, `gold2.py`, `gold_heldout.py`, `heldout.json` | the answer keys |
| `pc.json`, `discourse.json` | the saved parses and discourse parses of the 100-sentence sample (Oct 15) |

To score again: `python3 scripts/v6/parity_score.py scripts/v6 data/parity_oct19/parity_parses.json`

## Published work on combining parsers

- Henderson and Brill 1999, *Exploiting Diversity in Natural Language Processing: Combining Parsers*: keep a
  constituent when at least 2 of 3 parsers propose it.
- Zeman and Žabokrtský 2005, *Improving Parsing Accuracy by Combining Diverse Dependency Parsers*: vote on each
  word's head.
- Sagae and Lavie 2006, *Parser Combination by Reparsing*: merge the outputs into one weighted graph and reparse.
- Surdeanu and Manning 2010, *Ensemble Models for Dependency Parsing: Cheap and Good?*: simple voting does as well
  as complex models; the diversity of the parsers matters most.

All four vote on the same kind of structure. This pipeline votes on extracted lines across different formalisms.
