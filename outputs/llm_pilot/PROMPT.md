# LLM claim extraction pilot, Nov 16, 2026

What was asked of the LLM, for each sentence on its own:

List every predication in the sentence, one line per verb, as `subject | verb | object`, with a fourth field for a
recipient when there is one ("offered Mrs. Yeargin a resignation"). Rules:

- One line for every verb, including infinitives ("to make"), participles ("involving", "exchanging") and verbs inside
  relative clauses.
- Subject: the full noun phrase as written, with appositives ("Pierre Vinken, 61 years old"). When the subject is not
  said, use the phrase it refers to ("the unit | makes" for "the unit ... that makes"), or `(unstated)` when it
  refers to no one in particular.
- Verb: the whole verb group with auxiliaries and modals ("will join", "has been mollified", "stopped using"). Keep
  "n't" where it is written.
- Object: the full complement as written (a noun phrase, a predicative complement such as "chairman of ...", or a
  whole clause after say/think). Leave out "that" before a clause, and leave out time and place adjuncts. Leave the
  object empty when the verb has none.

Who ran it: Claude (Anthropic, the model behind this chat session, Nov 16, 2026), writing the lines by hand in the chat
for 100 sentences drawn at random (seed 20261116) from the Penn Treebank sample, without looking at the treebank's
annotation for those sentences. Six gold lines from wsj_0001 to wsj_0003 (other sentences) had been seen earlier and
served as examples. This is a pilot: it was not run through the API with a fixed model version and settings, so it
can't be repeated exactly. The next step is the same instructions through an API (Claude or Gemma), run twice.
