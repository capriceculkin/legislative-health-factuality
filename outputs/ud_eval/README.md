# Parser accuracy on UD test sets

`ud_eval_results.txt`: spaCy and Stanza on five Universal Dependencies test sets, given the gold words and sentence
breaks, scored by our scorer and by the official CoNLL 2018 scorer.

spaCy English scores about 55 to 57 UAS here. That is not its accuracy: spaCy's English model uses ClearNLP labels,
which draw some arrows the other way from UD (the preposition heads its noun, the verb "be" heads its clause, "and"
hangs on the first item). Rewriting the UD gold with just those three conventions changes the head of 28 to 30% of
the words, and spaCy's own published UAS on its own test set is 92.0. The French rows compare like with like.
Stanza's models are trained on the training files of these same treebanks, so its scores here are in-domain.
