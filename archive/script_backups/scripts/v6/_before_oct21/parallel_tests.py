"""parallel_tests.py   The same sentence in English and French, one construction at a time, with the lines the
pipeline should produce. Every construction has both languages, so a pass rate in one can be set beside the other.

Expected lines use the answer key's format: (subject, verb, object, kind, note). kind is asserted (stated), embedded
or reported; the note says "negated" and/or "hedged" when the line is. HEDGE_CHECK = False on a test means the
hedge policy for that construction is not settled, so hedging is not scored there.

Drafted with AI assistance from the project's labeling policy; to be checked by Caprice (English) and Joanie (French)
before any number from it is reported."""

T = []


def t(tid, group, construction, en, en_lines, fr, fr_lines, hedge_check=True):
    T.append(dict(id=tid, group=group, construction=construction, hedge_check=hedge_check,
                  en=dict(text=en, lines=en_lines), fr=dict(text=fr, lines=fr_lines)))


# ---------------------------------------------------------------- A. structure
t("A1", "structure", "one clause",
  "The committee approved the bill.", [("The committee", "approved", "the bill", "asserted", "")],
  "Le comité a approuvé le projet de loi.", [("Le comité", "a approuvé", "le projet de loi", "asserted", "")])
t("A2", "structure", "passive with by / par",
  "The bill was approved by the committee.", [("The bill", "was approved", "by the committee", "asserted", "")],
  "Le projet de loi a été approuvé par le comité.", [("Le projet de loi", "a été approuvé", "par le comité", "asserted", "")])
t("A3", "structure", "two subjects joined by and / et",
  "Dick and Jane go to the moon.", [("Dick and Jane", "go", "to the moon", "asserted", "")],
  "Dick et Jane vont sur la Lune.", [("Dick et Jane", "vont", "sur la Lune", "asserted", "")])
t("A4", "structure", "two clauses with a comma only",
  "Dick and Jane go to the moon, Spock goes to Mars.",
  [("Dick and Jane", "go", "to the moon", "asserted", ""), ("Spock", "goes", "to Mars", "asserted", "")],
  "Dick et Jane vont sur la Lune, Spock va sur Mars.",
  [("Dick et Jane", "vont", "sur la Lune", "asserted", ""), ("Spock", "va", "sur Mars", "asserted", "")])
t("A5", "structure", "two verbs share one subject",
  "Dick and Jane go to the moon and go to Mars.",
  [("Dick and Jane", "go", "to the moon", "asserted", ""), ("Dick and Jane (inh)", "go", "to Mars", "asserted", "")],
  "Dick et Jane vont sur la Lune et vont sur Mars.",
  [("Dick et Jane", "vont", "sur la Lune", "asserted", ""), ("Dick et Jane (inh)", "vont", "sur Mars", "asserted", "")])
t("A6", "structure", "shared subject, two objects",
  "The House passed the bill and sent the report to the Senate.",
  [("The House", "passed", "the bill", "asserted", ""), ("The House (inh)", "sent", "the report", "asserted", "")],
  "La Chambre a adopté le projet de loi et a envoyé le rapport au Sénat.",
  [("La Chambre", "a adopté", "le projet de loi", "asserted", ""), ("La Chambre (inh)", "a envoyé", "le rapport", "asserted", "")])
t("A7", "structure", "contrast with but / mais",
  "The House passed the bill, but the Senate rejected the amendment.",
  [("The House", "passed", "the bill", "asserted", ""), ("the Senate", "rejected", "the amendment", "asserted", "")],
  "La Chambre a adopté le projet de loi, mais le Sénat a rejeté l'amendement.",
  [("La Chambre", "a adopté", "le projet de loi", "asserted", ""), ("le Sénat", "a rejeté", "l'amendement", "asserted", "")])
t("A8", "structure", "David's sentence (D6)",
  "Last year the House passed legislation identical to H.R. 5, but the Senate refused to act.",
  [("the House", "passed", "legislation identical to H.R. 5", "asserted", ""), ("the Senate", "refused to act", "", "asserted", "")],
  "L'an dernier, la Chambre a adopté un projet de loi identique au projet de loi 5, mais le Sénat a refusé d'agir.",
  [("la Chambre", "a adopté", "un projet de loi identique au projet de loi 5", "asserted", ""),
   ("le Sénat", "a refusé d'agir", "", "asserted", "")])
t("A9", "structure", "form of address before the subject",
  "Mr. Speaker, the minister broke his promise.", [("the minister", "broke", "his promise", "asserted", "")],
  "M. le Président, le ministre a rompu sa promesse.", [("le ministre", "a rompu", "sa promesse", "asserted", "")])
t("A10", "structure", "apposition",
  "Jean Martin, the health minister, tabled the bill.",
  [("Jean Martin", "tabled", "the bill", "asserted", ""), ("Jean Martin", "is (apposition)", "the health minister", "asserted", "")],
  "Jean Martin, le ministre de la Santé, a déposé le projet de loi.",
  [("Jean Martin", "a déposé", "le projet de loi", "asserted", ""), ("Jean Martin", "is (apposition)", "le ministre de la Santé", "asserted", "")])
t("A11", "structure", "question (skipped by design)",
  "Will the minister resign?", [],
  "Le ministre va-t-il démissionner?", [])

# ---------------------------------------------------------------- B. negation
t("B1", "negation", "not / ne ... pas",
  "The Senate did not pass the bill.", [("The Senate", "did not pass", "the bill", "asserted", "negated")],
  "Le Sénat n'a pas adopté le projet de loi.", [("Le Sénat", "n'a pas adopté", "le projet de loi", "asserted", "negated")])
t("B2", "negation", "never / ne ... jamais",
  "The government never consulted the nurses.", [("The government", "never consulted", "the nurses", "asserted", "negated")],
  "Le gouvernement n'a jamais consulté les infirmières.", [("Le gouvernement", "n'a jamais consulté", "les infirmières", "asserted", "negated")])
t("B3", "negation", "nobody / personne as subject",
  "Nobody supports this amendment.", [("Nobody", "supports", "this amendment", "asserted", "negated")],
  "Personne n'appuie cet amendement.", [("Personne", "n'appuie", "cet amendement", "asserted", "negated")])
t("B4", "negation", "nothing / rien as object",
  "The minister did nothing for the hospitals.", [("The minister", "did", "nothing", "asserted", "negated")],
  "Le ministre n'a rien fait pour les hôpitaux.", [("Le ministre", "n'a rien fait", "pour les hôpitaux", "asserted", "negated")])
t("B5", "negation", "no longer / ne ... plus",
  "Patients no longer receive this service.", [("Patients", "no longer receive", "this service", "asserted", "negated")],
  "Les patients ne reçoivent plus ce service.", [("Les patients", "ne reçoivent plus", "ce service", "asserted", "negated")])
t("B6", "negation", "no / aucun on the subject",
  "No member opposed the motion.", [("No member", "opposed", "the motion", "asserted", "negated")],
  "Aucun député ne s'est opposé à la motion.", [("Aucun député", "ne s'est opposé", "à la motion", "asserted", "negated")])
t("B7", "negation", "only / ne ... que is not negation",
  "The program only helps seniors.", [("The program", "helps", "seniors", "asserted", "")],
  "Le programme n'aide que les aînés.", [("Le programme", "aide", "les aînés", "asserted", "")])

# ---------------------------------------------------------------- C. hedges
t("C1", "hedge", "would / conditional",
  "The bill would lower drug costs.", [("The bill", "would lower", "drug costs", "asserted", "hedged")],
  "Le projet de loi réduirait le coût des médicaments.", [("Le projet de loi", "réduirait", "le coût des médicaments", "asserted", "hedged")])
t("C2", "hedge", "could / pourrait",
  "The plan could save money.", [("The plan", "could save", "money", "asserted", "hedged")],
  "Le plan pourrait économiser de l'argent.", [("Le plan", "pourrait économiser", "de l'argent", "asserted", "hedged")])
t("C3", "hedge", "probably / probablement",
  "The minister probably made a mistake.", [("The minister", "made", "a mistake", "asserted", "hedged")],
  "Le ministre a probablement fait une erreur.", [("Le ministre", "a fait", "une erreur", "asserted", "hedged")])
t("C4", "hedge", "should / devrait is obligation, not a hedge",
  "The government should fund the clinics.", [("The government", "should fund", "the clinics", "asserted", "")],
  "Le gouvernement devrait financer les cliniques.", [("Le gouvernement", "devrait financer", "les cliniques", "asserted", "")])
t("C5", "hedge", "must / doit is obligation, not a hedge",
  "The province must fund the clinics.", [("The province", "must fund", "the clinics", "asserted", "")],
  "La province doit financer les cliniques.", [("La province", "doit financer", "les cliniques", "asserted", "")])
t("C6", "hedge", "seems / semble (hedge policy open)",
  "The program seems to work.", [("The program", "seems to work", "", "asserted", "")],
  "Le programme semble fonctionner.", [("Le programme", "semble fonctionner", "", "asserted", "")], hedge_check=False)

# ---------------------------------------------------------------- D. reported and the speaker's own framing
t("D1", "reported", "said that / a dit que",
  "The minister said that the bill lowers costs.",
  [("The minister", "said", "that the bill lowers costs", "asserted", ""), ("the bill", "lowers", "costs", "reported", "")],
  "Le ministre a dit que le projet de loi réduit les coûts.",
  [("Le ministre", "a dit", "que le projet de loi réduit les coûts", "asserted", ""), ("le projet de loi", "réduit", "les coûts", "reported", "")])
t("D2", "reported", "told X that / a dit à X que",
  "The doctors told the minister that the wait times are rising.",
  [("The doctors", "told", "the minister", "asserted", ""), ("the wait times", "are rising", "", "reported", "")],
  "Les médecins ont dit au ministre que les délais augmentent.",
  [("Les médecins", "ont dit", "au ministre", "asserted", ""), ("les délais", "augmentent", "", "reported", "")])
t("D3", "reported", "according to / selon",
  "According to the report, the program failed.", [("the program", "failed", "", "reported", "")],
  "Selon le rapport, le programme a échoué.", [("le programme", "a échoué", "", "reported", "")])
t("D4", "reported", "direct quotation",
  'The doctor said: "The wait times are too long."',
  [("The doctor", "said", "The wait times are too long", "asserted", ""), ("The wait times", "are", "too long", "reported", "")],
  "Le médecin a dit : « Les délais sont trop longs. »",
  [("Le médecin", "a dit", "Les délais sont trop longs", "asserted", ""), ("Les délais", "sont", "trop longs", "reported", "")])
t("D5", "reported", "the speaker's own framing (I think / je pense)",
  "I think the bill lowers costs.",
  [("I", "think", "the bill lowers costs", "asserted", ""), ("the bill", "lowers", "costs", "asserted", "")],
  "Je pense que le projet de loi réduit les coûts.",
  [("Je", "pense", "que le projet de loi réduit les coûts", "asserted", ""), ("le projet de loi", "réduit", "les coûts", "asserted", "")],
  hedge_check=False)

# ---------------------------------------------------------------- E. clauses that are not stated, and clauses that are
t("E1", "clauses", "condition: if / si",
  "If the bill passes, costs will fall.",
  [("the bill", "passes", "", "embedded", ""), ("costs", "will fall", "", "asserted", "")],
  "Si le projet de loi est adopté, les coûts vont baisser.",
  [("le projet de loi", "est adopté", "", "embedded", ""), ("les coûts", "vont baisser", "", "asserted", "")])
t("E2", "clauses", "time: when / quand",
  "When the minister arrived, the debate began.",
  [("the minister", "arrived", "", "embedded", ""), ("the debate", "began", "", "asserted", "")],
  "Quand le ministre est arrivé, le débat a commencé.",
  [("le ministre", "est arrivé", "", "embedded", ""), ("le débat", "a commencé", "", "asserted", "")])
t("E3", "clauses", "time: before / avant que",
  "The minister resigned before the report came out.",
  [("The minister", "resigned", "", "asserted", ""), ("the report", "came out", "", "embedded", "")],
  "Le ministre a démissionné avant que le rapport soit publié.",
  [("Le ministre", "a démissionné", "", "asserted", ""), ("le rapport", "soit publié", "", "embedded", "")])
t("E4", "clauses", "until / jusqu'à ce que",
  "The clinic stays open until the province pays.",
  [("The clinic", "stays", "open", "asserted", ""), ("the province", "pays", "", "embedded", "")],
  "La clinique reste ouverte jusqu'à ce que la province paie.",
  [("La clinique", "reste", "ouverte", "asserted", ""), ("la province", "paie", "", "embedded", "")])
t("E5", "clauses", "unless / à moins que",
  "Unless the Senate acts, the program ends.",
  [("the Senate", "acts", "", "embedded", ""), ("the program", "ends", "", "asserted", "")],
  "À moins que le Sénat agisse, le programme prend fin.",
  [("le Sénat", "agisse", "", "embedded", ""), ("le programme", "prend fin", "", "asserted", "")])   # light-verb phrase kept whole, as the key does (#58 se rendent compte)
t("E6", "clauses", "whether / si (indirect question)",
  "The committee will decide whether the bill proceeds.",
  [("The committee", "will decide", "whether the bill proceeds", "asserted", ""), ("the bill", "proceeds", "", "embedded", "")],
  "Le comité décidera si le projet de loi va de l'avant.",
  [("Le comité", "décidera", "si le projet de loi va de l'avant", "asserted", ""), ("le projet de loi", "va", "de l'avant", "embedded", "")])
t("E7", "clauses", "purpose: to / pour",
  "The government cut taxes to help families.",
  [("The government", "cut", "taxes", "asserted", ""), ("The government (inh)", "help", "families", "embedded", "")],
  "Le gouvernement a réduit les impôts pour aider les familles.",
  [("Le gouvernement", "a réduit", "les impôts", "asserted", ""), ("Le gouvernement (inh)", "aider", "les familles", "embedded", "")])
t("E8", "clauses", "cause: because / parce que (stated)",
  "The program failed because the province cut its budget.",
  [("The program", "failed", "", "asserted", ""), ("the province", "cut", "its budget", "asserted", "")],
  "Le programme a échoué parce que la province a réduit son budget.",
  [("Le programme", "a échoué", "", "asserted", ""), ("la province", "a réduit", "son budget", "asserted", "")])
t("E9", "clauses", "cause: since / puisque (stated)",
  "The bill is urgent since the clinics are closing.",
  [("The bill", "is", "urgent", "asserted", ""), ("the clinics", "are closing", "", "asserted", "")],
  "Le projet de loi est urgent puisque les cliniques ferment.",
  [("Le projet de loi", "est", "urgent", "asserted", ""), ("les cliniques", "ferment", "", "asserted", "")])
t("E10", "clauses", "concession: although / bien que",
  "Although the bill passed, the clinics closed.",
  [("the bill", "passed", "", "embedded", ""), ("the clinics", "closed", "", "asserted", "")],
  "Bien que le projet de loi ait été adopté, les cliniques ont fermé.",
  [("le projet de loi", "ait été adopté", "", "embedded", ""), ("les cliniques", "ont fermé", "", "asserted", "")])
t("E11", "clauses", "as / comme opening a clause (policy: not stated)",
  "As the debate continued, members left the chamber.",
  [("the debate", "continued", "", "embedded", ""), ("members", "left", "the chamber", "asserted", "")],
  "Comme le débat se poursuivait, les députés ont quitté la salle.",
  [("le débat", "se poursuivait", "", "embedded", ""), ("les députés", "ont quitté", "la salle", "asserted", "")])
t("E12", "clauses", "means: by -ing / en -ant (stated)",
  "The province saved money by closing clinics.",
  [("The province", "saved", "money", "asserted", ""), ("The province (inh)", "closing", "clinics", "asserted", "")],
  "La province a économisé de l'argent en fermant des cliniques.",
  [("La province", "a économisé", "de l'argent", "asserted", ""), ("La province (inh)", "fermant", "des cliniques", "asserted", "")])

# ---------------------------------------------------------------- F. relative clauses and verb complements
t("F1", "relative", "subject relative: who / qui",
  "The nurses who work nights earn less.",
  [("The nurses", "earn", "less", "asserted", ""), ("The nurses", "work", "nights", "embedded", "")],
  "Les infirmières qui travaillent la nuit gagnent moins.",
  [("Les infirmières", "gagnent", "moins", "asserted", ""), ("Les infirmières", "travaillent", "la nuit", "embedded", "")])
t("F2", "relative", "object relative: that / que",
  "The bill that the House passed lowers costs.",
  [("The bill", "lowers", "costs", "asserted", ""), ("the House", "passed", "The bill", "embedded", "")],
  "Le projet de loi que la Chambre a adopté réduit les coûts.",
  [("Le projet de loi", "réduit", "les coûts", "asserted", ""), ("la Chambre", "a adopté", "Le projet de loi", "embedded", "")])
t("F3", "relative", "participle describing a noun",
  "Families living in rural areas pay more.",
  [("Families", "pay", "more", "asserted", ""), ("Families", "living", "in rural areas", "embedded", "")],
  "Les familles vivant en région paient plus.",
  [("Les familles", "paient", "plus", "asserted", ""), ("Les familles", "vivant", "en région", "embedded", "")])
t("F4", "relative", "object control: urge X to / exhorter X à",
  "The minister urged the doctors to accept the deal.",
  [("The minister", "urged", "the doctors", "asserted", ""), ("the doctors", "accept", "the deal", "embedded", "")],
  "Le ministre a exhorté les médecins à accepter l'entente.",
  [("Le ministre", "a exhorté", "les médecins", "asserted", ""), ("les médecins", "accepter", "l'entente", "embedded", "")])
