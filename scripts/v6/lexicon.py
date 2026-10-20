"""lexicon.py   Every word list the rules use, written once, as English-French pairs.

Each row is one meaning: (English words, French words). A meaning is never listed for one language only; if a row
has no counterpart it is a bug, and check_parity() reports it. The rule files (preds.py, const_fr.py, combine_lib.py)
take their sets from here, so both languages are read with the same vocabulary.

Policy written into the rows (one decision for both languages):
  * negation: the clause's verb is denied (not / ne ... pas, never / jamais, nobody / personne, nothing / rien ...)
  * hedge: the speaker is less than certain (could, might, may, would; the French conditional of pouvoir, avoir,
    etre). Obligation is not a hedge in either language: should, must, ought / devoir in any form.
  * cause clauses are stated (because / parce que, since / puisque, for / car, as / comme);
    condition, time, concession and "whether" clauses are not stated.
"""

# ---------------------------------------------------------------- negation
NEG_ADV = [            # words that deny the verb they hang on (French ones need ne, except where noted)
    (["not", "n't", "n’t"], ["pas"]),
    (["never"], ["jamais"]),
    (["no longer", "anymore"], ["plus"]),
    (["hardly", "scarcely"], ["guère"]),
    (["in no way", "nowise"], ["nullement"]),
    (["neither", "nor"], ["ni"]),
]
NEG_PRON = [           # negative pronouns and determiners as subject or object
    (["nothing"], ["rien"]),
    (["nobody", "no one", "no-one"], ["personne"]),
    (["none"], ["aucun", "aucune", "nul", "nulle"]),
]
NEG_DET = [(["no"], ["aucun", "aucune", "nul", "nulle"])]

# ---------------------------------------------------------------- hedges
HEDGE_AUX = [
    (["could"], ["pourrait", "pourraient", "pourrais", "pourrions", "pourriez"]),
    (["might", "may"], ["puisse", "puissent", "pourrait", "pourraient"]),
    (["would", "'d", "’d"], ["serait", "seraient", "serais", "serions", "seriez", "aurait", "auraient", "aurais",
                             "aurions", "auriez"]),
]
HEDGE_ADV = [
    (["perhaps", "maybe"], ["peut-être"]),
    (["possibly"], ["possiblement"]),
    (["probably"], ["probablement", "sans doute"]),
    (["likely"], ["vraisemblablement"]),
    (["apparently"], ["apparemment"]),
    (["presumably"], ["présumément", "vraisemblablement"]),
]
HEDGE_COND_LEMMAS = [(["could", "might", "would"], ["pouvoir", "avoir", "être"])]   # French: Mood=Cnd on these
NOT_HEDGE = [(["should", "must", "ought", "shall", "can"], ["devoir", "falloir", "pouvoir (présent)"])]   # documented only

# ---------------------------------------------------------------- speech and attribution
SPEECH = [             # lemma, then the surface forms the tree rules and the discourse trigger look for
    (["say", "says", "said", "saying"], ["dire", "dit", "dis", "disent", "disait", "dira", "disons", "dites", "disant"]),
    (["tell", "tells", "told", "telling"], ["raconter", "raconte", "racontent", "raconté"]),
    (["state", "states", "stated", "stating"], ["déclarer", "déclare", "déclarent", "déclaré", "déclarait"]),
    (["declare", "declares", "declared"], ["déclarer", "déclare", "déclaré"]),
    (["claim", "claims", "claimed"], ["prétendre", "prétend", "prétendent", "prétendu"]),
    (["affirm", "affirms", "affirmed"], ["affirmer", "affirme", "affirment", "affirmé"]),
    (["argue", "argues", "argued"], ["soutenir", "soutient", "soutiennent", "soutenu"]),
    (["maintain", "maintains", "maintained"], ["maintenir", "maintient", "maintiennent", "maintenu"]),
    (["ask", "asks", "asked"], ["demander", "demande", "demandent", "demandé"]),
    (["add", "adds", "added"], ["ajouter", "ajoute", "ajoutent", "ajouté"]),
    (["write", "writes", "wrote", "written"], ["écrire", "écrit", "écrivent"]),
    (["suggest", "suggests", "suggested"], ["suggérer", "suggère", "suggèrent", "suggéré"]),
    (["insist", "insists", "insisted"], ["insister", "insiste", "insistent", "insisté"]),
    (["announce", "announces", "announced"], ["annoncer", "annonce", "annoncent", "annoncé"]),
    (["note", "notes", "noted"], ["noter", "note", "notent", "noté", "signaler", "signale", "signalé"]),
    (["indicate", "indicates", "indicated"], ["indiquer", "indique", "indiquent", "indiqué"]),
    (["stress", "stresses", "stressed", "emphasize", "emphasizes", "emphasized"],
     ["souligner", "souligne", "soulignent", "souligné"]),
    (["explain", "explains", "explained"], ["expliquer", "explique", "expliquent", "expliqué"]),
    (["report", "reports", "reported"], ["rapporter", "rapporte", "rapportent", "rapporté"]),
]
SOURCE_EXTRA = [       # words that make an attribution someone else's in the discourse step (besides SPEECH)
    (["recommend", "recommends", "recommended"], ["recommander", "recommande", "recommandent", "recommandé"]),
    (["find", "finds", "found"], ["constater", "constate", "constatent", "constaté", "trouve"]),
    (["show", "shows", "showed", "shown"], ["montrer", "montre", "montrent", "montré"]),
    (["according"], ["selon", "d'après"]),
]
SELF = [(["i"], ["je", "j'", "j’"]), (["we"], ["nous", "on"]), (["you"], ["vous", "tu"])]

# ---------------------------------------------------------------- clause linking words
CAUSE = [(["because"], ["parce"]), (["since"], ["puisque", "puisqu'", "puisqu’"]), (["for"], ["car"])]
NOT_STATED_AS = [(["as"], ["comme"])]       # opening a clause (as the bill moves / comme le gouvernement a refusé): not stated in both languages, as in v5 English. A policy choice to confirm.
NOT_STATED = [         # condition, time, concession, whether
    (["if"], ["si", "s'", "s’"]),
    (["unless"], ["moins"]),                           # à moins que
    (["when", "whenever"], ["quand", "lorsque", "lorsqu'", "lorsqu’"]),
    (["after"], ["après"]),
    (["before"], ["avant"]),
    (["while"], ["pendant", "tandis"]),
    (["whereas"], ["alors", "tandis"]),
    (["until"], ["jusqu'", "jusqu’"]),
    (["once"], ["dès", "une fois"]),
    (["whether"], ["si"]),
    (["though", "although"], ["bien", "quoique", "quoiqu'", "quoiqu’"]),
]
TIME_FIRST = [         # first word of a time / background unit in the discourse step
    (["when", "whenever"], ["quand", "lorsque", "lorsqu'", "lorsqu’"]), (["if"], ["si", "s'", "s’"]), (["after"], ["après"]),
    (["before"], ["avant"]), (["while"], ["pendant"]), (["since"], ["depuis"]), (["until"], ["jusqu'", "jusqu’"]),
    (["unless"], ["moins"]), (["once"], ["dès"]), (["as"], ["comme"]),
]
PURPOSE = [(["to"], ["pour", "de", "d'", "d’"]), (["in"], ["afin"]), (["so"], ["pour"])]   # to / pour, in order to / afin de, so that / pour que
MEANS = [(["by"], ["en", "par"])]
EXAMPLE = [(["including"], ["notamment"]), (["such as", "as"], ["comme"])]   # "as" only after "such"
CONTROL = [            # verbs whose object is the subject of the infinitive after it (urge my colleagues to reject)
    (["urg"], ["exhort", "incit"]), (["requir"], ["exig", "oblig"]), (["ask"], ["demand"]), (["allow", "permit", "enabl"], ["permet", "permis", "permett"]),
    (["authoriz", "entitl"], ["autoris"]), (["encourag"], ["encourag"]), (["forc", "compel"], ["forc", "contraign", "contraint"]),
    (["tell", "told", "order", "direct", "instruct"], ["ordonn"]), (["persuad"], ["persuad", "convainc"]), (["invit", "call"], ["invit", "appel"]),
    (["oblig"], ["oblig"]), (["advis"], ["conseill"]), (["remind"], ["rappel"]), (["help"], ["aid"]), (["caus"], ["pouss"]),
    (["mandat"], ["mandat"]), (["empower"], ["habilit"]), (["want", "expect"], ["(no French form: vouloir que takes a subjunctive clause, not object + infinitive)"]),
]
RAISING = [            # modal and raising verbs: never object control (je pourrais vous citer keeps je as the subject)
    (["can"], ["pouvoir"]), (["must"], ["devoir", "falloir"]), (["will", "shall"], ["aller"]), (["seem", "appear"], ["sembler", "paraître"]),
    (["want"], ["vouloir"]), (["need"], ["falloir"]), (["have"], ["avoir"]), (["try"], ["essayer", "tenter"]), (["be"], ["être"]),
    (["know"], ["savoir"]), (["come"], ["venir"]), (["go"], ["aller"]),
]
REL = [
    (["who"], ["qui"]), (["which", "that"], ["que", "qu'", "qu’", "lequel", "laquelle", "lesquels", "lesquelles"]),
    (["whom"], ["que", "qu'", "qu’"]), (["whose"], ["dont"]), (["where"], ["où"]),
]
CONNECTIVES = [        # (English phrase, relation), (French phrase, relation): used for the clause links only
    ([("but", "contrast")], [("mais", "contrast")]),
    ([("however", "contrast")], [("cependant", "contrast"), ("toutefois", "contrast"), ("pourtant", "contrast")]),
    ([("although", "concession"), ("though", "concession")], [("bien que", "concession"), ("quoique", "concession")]),
    ([("whereas", "contrast")], [("tandis que", "contrast")]),
    ([("while", "contrast or time")], [("alors que", "contrast or time")]),
    ([("because", "cause")], [("parce que", "cause"), ("parce qu'", "cause")]),
    ([("since", "cause or time")], [("puisque", "cause or time")]),
    ([("for", "cause")], [("car", "cause")]),
    ([("so", "result"), ("therefore", "result")], [("donc", "result")]),
    ([("thus", "result")], [("ainsi", "result")]),
    ([("if", "condition")], [("si", "condition")]),
    ([("unless", "condition")], [("à moins que", "condition"), ("à moins qu'", "condition")]),
    ([("when", "time")], [("quand", "time"), ("lorsque", "time"), ("lorsqu'", "time")]),
    ([("after", "time")], [("après que", "time"), ("après avoir", "time")]),
    ([("before", "time")], [("avant que", "time"), ("avant de", "time")]),
    ([("then", "sequence")], [("puis", "sequence")]),
    ([("as well as", "addition")], [("ainsi que", "addition")]),
    ([("and", "addition")], [("et", "addition")]),
    ([("or", "alternative")], [("ou", "alternative")]),
    ([("by", "means")], [("en", "means")]),
    ([("such as", "example"), ("including", "example")], [("notamment", "example"), ("comme", "example")]),
    ([("for example", "example")], [("par exemple", "example")]),
    ([("in order to", "purpose")], [("afin de", "purpose"), ("pour", "purpose")]),
]

SOURCE_PREP = [(["according"], ["selon", "d'après", "d’après"])]          # according to X / selon X: the clause is X's claim
FRAMING = [            # the speaker's own framing: "I think X", "we know X" -> X is the speaker's claim (answer key, #35)
    (["think", "thinks", "thought"], ["penser", "pense", "pensons", "pensais"]),
    (["believe", "believes", "believed"], ["croire", "crois", "croyons", "croyais"]),
    (["know", "knows", "knew"], ["savoir", "sais", "savons", "savez", "sait"]),
    (["sure"], ["sûr", "sûre", "certain", "certaine"]),
]
FIRST_PERSON = [(["i"], ["je", "j'", "j’"]), (["we"], ["nous", "on"])]
COPULA_LIKE = [         # lemma and forms (spaCy French gives "reste" the lemma "reste")
    (["stay", "stays", "stayed", "remain", "remains", "remained"], ["rester", "reste", "restent", "restera", "demeurer", "demeure", "demeurent"]),
    (["become", "becomes", "became"], ["devenir", "devient", "deviennent", "devenu"]),
    (["seem", "seems", "seemed", "appear", "appears"], ["sembler", "semble", "semblent", "paraître", "paraît"]),
]
QUANT_ADV = [(["more"], ["plus", "davantage"]), (["less"], ["moins"]), (["much", "a lot"], ["beaucoup"])]
SUBORD_PHRASES = [     # subordinators written as several words; the last word is the one that marks the clause
    (["even if"], ["même si"]), (["as soon as"], ["dès que", "aussitôt que"]), (["so that"], ["pour que", "afin que"]),
    (["unless"], ["à moins que", "à moins qu'"]), (["until"], ["jusqu'à ce que", "jusqu'à ce qu'"]),
    (["although", "even though"], ["bien que", "bien qu'", "alors même que"]), (["while"], ["pendant que", "tandis que"]),
    (["whereas"], ["alors que", "alors qu'"]), (["before"], ["avant que", "avant qu'"]), (["after"], ["après que", "après qu'"]),
    (["because"], ["parce que", "parce qu'"]), (["given that"], ["étant donné que", "vu que"]),
]
SUBORD_PHRASE_CAUSE = {"because", "parce que", "parce qu'", "given that", "étant donné que", "vu que"}
SUBORD_PHRASE_PURPOSE = {"so that", "pour que", "afin que"}

TIME_ADV = [           # adverbs of time: ARGM-TMP in a frame
    (["now"], ["maintenant"]), (["today"], ["aujourd'hui", "aujourd’hui"]), (["yesterday"], ["hier"]), (["tomorrow"], ["demain"]),
    (["already"], ["déjà"]), (["soon"], ["bientôt"]), (["still"], ["encore", "toujours"]), (["always"], ["toujours"]),
    (["then"], ["alors", "ensuite"]), (["recently"], ["récemment"]), (["finally"], ["finalement", "enfin"]), (["ago"], ["il y a"]),
    (["again"], ["encore", "de nouveau"]), (["often"], ["souvent"]), (["once"], ["autrefois"]), (["later"], ["plus tard"]),
]
TIME_NOUN = [          # an oblique or noun phrase headed by one of these is ARGM-TMP
    (["year", "years"], ["an", "ans", "année", "années"]), (["day", "days"], ["jour", "jours", "journée"]),
    (["week", "weeks"], ["semaine", "semaines"]), (["month", "months"], ["mois"]), (["time", "times"], ["fois", "temps"]),
    (["morning"], ["matin"]), (["afternoon"], ["après-midi"]), (["evening", "night"], ["soir", "soirée", "nuit"]),
    (["century"], ["siècle"]), (["decade"], ["décennie"]), (["session"], ["session", "séance"]),
    (["january", "february", "march", "april", "june", "july", "august", "september", "october", "november", "december"],
     ["janvier", "février", "mars", "avril", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]),
]

# ---------------------------------------------------------------- forms of address and pronouns
ADDRESS = [(["speaker"], ["président", "présidente"]), (["president"], ["président", "présidente"]),
           (["chair", "chairman", "chairwoman", "chairperson"], ["président", "présidente"]), (["colleagues"], ["collègues"])]
TITLES = [(["mr", "mr."], ["m.", "monsieur"]), (["mrs", "mrs.", "ms", "ms.", "madam"], ["mme", "madame"]), (["dr", "dr."], ["dr", "dr."])]
PRONOUNS = [(["it"], ["il", "elle", "ça", "cela", "ce", "c'"]), (["they"], ["ils", "elles"]), (["he"], ["il"]), (["she"], ["elle"]),
            (["we"], ["nous", "on"]), (["i"], ["je", "j'"]), (["you"], ["vous", "tu"]), (["this", "that"], ["ceci", "cela", "ça"]),
            (["one"], ["on"])]
LOC_ADV = [(["here"], ["ici"]), (["there"], ["là", "là-bas", "y"]), (["abroad", "overseas"], ["ailleurs", "à l'étranger"]),
           (["away", "far"], ["loin"]), (["outside"], ["dehors"]), (["home"], ["chez nous"]), (["elsewhere"], ["ailleurs"]),
           (["underground"], ["sous terre"])]

# ---------------------------------------------------------------- scoring: words that never count as shared content
STOP = [
    (["the", "a", "an"], ["le", "la", "les", "l'", "un", "une", "des"]),
    (["of", "from"], ["de", "du", "d'"]), (["to", "at"], ["à", "au", "aux"]), (["in", "into"], ["dans", "en"]),
    (["on"], ["sur"]), (["for"], ["pour"]), (["by"], ["par"]), (["with"], ["avec"]), (["toward", "towards"], ["vers"]),
    (["as"], ["comme"]), (["and"], ["et"]), (["or"], ["ou"]), (["that"], ["que", "qu'"]),
    (["this", "these", "those"], ["ce", "cet", "cette", "ces", "ceux"]),
    (["his", "her", "its"], ["son", "sa", "ses"]), (["their"], ["leur", "leurs"]), (["our"], ["notre", "nos"]),
    (["my"], ["mon", "ma", "mes"]), (["your"], ["votre", "vos"]),
    (["be", "is", "are", "was", "were", "been"], ["être", "est", "sont", "était", "étaient", "été", "sera", "seront"]),
    (["have", "has", "had"], ["avoir", "a", "ont", "avait", "avaient", "aura", "auront", "eu"]),
    (["will", "would"], ["serait", "aurait"]),        # not va / vont: in French they are often the main verb (ils s'en vont) (["not"], ["ne", "pas", "n'"]),
    (["(inh)", "inh"], ["(inh)", "inh"]),
]


# ---------------------------------------------------------------- sets the rule files use
def en(rows):
    return {w for e, _ in rows for w in e}


def fr(rows):
    return {w for _, f in rows for w in f}


def both(rows):
    return en(rows) | fr(rows)


def check_parity():
    """Every row must have at least one word on each side. Returns the rows that do not."""
    bad = []
    for name, rows in list(globals().items()):
        if name.isupper() and isinstance(rows, list) and rows and isinstance(rows[0], tuple):
            for k, (e, f) in enumerate(rows):
                if not e or not f:
                    bad.append((name, k, e, f))
    return bad


if __name__ == "__main__":
    import sys
    bad = check_parity()
    for name, rows in sorted(globals().items()):
        if name.isupper() and isinstance(rows, list) and rows and isinstance(rows[0], tuple):
            print(f"{name:12s} {len(rows):3d} meanings   en {len(en(rows)):3d} words   fr {len(fr(rows)):3d} words")
    print("rows missing a side:", bad or "none")
    sys.exit(1 if bad else 0)
