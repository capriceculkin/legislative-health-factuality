# Transcript Division Samples — Legislative Health Factuality Pipeline
## Validation of Bill-Specific Text Extraction

This document shows how raw legislative transcripts are divided into
bill-specific segments at each stage of the pipeline, with n counts.

---
## Stage 1: Raw Transcript (Full Sitting Day)

### Quebec — 1995-12-04 (Journal des débats)
**N = 45,178 words, 1,305 lines**

```
Recherche avancée dans la section Travaux parlementaires

Mots clés

Type de documents

Type de travaux

Période

De

À

La date de début doit précéder la date de fin.

Session

Journal des débats de l'Assemblée nationale

Version finale

Retour à la liste des séances de l'Assemblée de cette session


 35
e
 législature, 1
re
 session
 

 (29 novembre 1994 au 13 mars 1996)
 


 Le lundi 4 décembre
```

### Ontario — 2009-04-02 (Ontario Hansard, full sitting day)
**N = ~350 rows (all business: Question Period, Orders of the Day, Petitions, etc.)**

```
ORAL QUESTIONS | DRUG BENEFIT PROGRAM | Hon. Deb Matthews
    My question is to the Minister of Health...

ORAL QUESTIONS | HOME CARE | Mr. John Yakabuski
    Will the minister admit that home care in Ontario...

ORDERS OF THE DAY | PERSONAL HEALTH INFORMATION PROTECTION ACT | Mr. Khalil Ramal
    Bill 104, An Act to amend the Personal Health Information...

PETITIONS | HOSPITAL FUNDING | Mr. Ted Arnott
    'We, the undersigned, petition the Legislative Assembly...'
```

### US — 2020-03-14 (Congressional Record)
**N = 24,387 words** (already bill-specific via GovInfo granule)

```
--- CREC-2020-03-13-pt1-PgH1675-9 ---
Congressional Record, Volume 166 Issue 49 (Friday, March 13, 2020)

[Congressional Record Volume 166, Number 49 (Friday, March 13, 2020)]
[House]
[Pages H1675-H1691]
From the Congressional Record Online through the Government Publishing Office [
www.gpo.gov
]

 FAMILIES FIRST CORONAVIRUS RESPONSE ACT

 Mrs. LOWEY. Mr. Speaker, I move to suspend the rules and p
```

---
## Stage 2: Bill-Specific Extraction

### Quebec — Section Marker Detection

**Markers used:**
- `Étude du projet de loi n° X`
- `Adoption du principe du projet de loi n° X`
- `Reprise du débat sur l'adoption du principe du projet de loi n° X`
- `Prise en considération du rapport sur le projet de loi n° X`
- `Adoption du projet de loi n° X`

**Bill 34 | 1988-11-17 | N = 345 words**

```
l'étude détaillée du projet de loi 34, Loi modifiant la
		Loi sur les services de santé et les services sociaux et d'autres
		dispositions législatives. De 19 heures à 22 heures, de
		même que le mardi 22 novembre, de 10 heures à 12 h 30, à la
		salle du Conseil législatif, la commission de l'éducation
		poursuivra l'étude détaillée des projets de loi suivants
		et ce, dans l'ordre ci-après indiqu
```

**Bill 47 | 2009-06-05 | N = 248 words**

```
Que la Commission des affaires sociales entreprendra l'étude détaillée du projet de loi n° 47, Loi modifiant la Loi approuvant l'Entente concernant la construction et l'exploitation d'un centre hospitalier sur le territoire de Kahnawake, aujourd'hui, de 15 heures à 18 heures, à la salle Louis-Hippolyte-La Fontaine.
	Cette même commission entreprendra ensuite l'étude détaillée du projet de loi n° 4
```

**Bill 33 | 1988-12-22 | N = 73 words**

```
le ministre de la Justice propose maintenant l'adoption du projet de loi 33,
		Loi modifiant le Code de procédure civile concernant le recouvrement de
		pensions alimentaires. Y a-t-il des interventions?
Des voix:
Non.
Le Vice-Président:
II n'y a pas d'interventions. Est-ce
		que cette motion d'adoption du projet de loi 33 est adoptée?
Des voix:
Adopté.
Le Vice-Président:
Adopté. M. le leader adjo
```

**Quebec total: 8,236 bill-date segments | 24,677,725 words**
*(vs full sitting-day corpus: ~24M words before extraction)*

### Ontario — OLA API Orders of the Day Filter

**Method:** Azure Search API query per date:
```
filter: (date ge {date}T00:00:00Z and date le {date}T23:59:59Z)
        and (typeOfBusiness eq "ORDERS OF THE DAY"
             or typeOfBusiness eq "Orders of the Day")
```
**Bill assignment:** matched by bill number mentioned in paragraph text,
or by topic keyword overlap with bill title.

**2013-Bill177 | 2014-03-25 | N = 33 paragraphs this date, 90 total**

```
Well, you know, we don’t have a monopoly on good ideas, nor do others on the other side.  Again, to the member from Welland, whom I respect a great deal, we do need to debate these things, but it’s fairly straightforward what we’re talking about. We’ve debated this before. What we’re talking about is an extension. It has to do with the 107 of us. The member from Renfrew–Nipissing is right: It’s ju
```

**2021-Bill235 | 2024-12-09 | N = 83 paragraphs this date, 104 total**

```
I’m really pleased to be able to continue conversing about this important thing. The member opposite simply doesn’t recognize the fact that most of what is in this bill today are amendments that New Democrats have put forward to the government years prior. They are things that we could have already had in place.  And now, when our families and our seniors are in crisis, we’re putting forward these
```

**2021-Bill116 | 2022-03-02 | N = 1 paragraphs this date, 1 total**
Speaker: Ms. Peggy Sattler

```
The first bill, Bill 2, was time-allocated.  Bill 5 was time-allocated, and that, as everyone will recall, is the Better Local Government Act. That was the bill that the Premier introduced in order to get some payback on Toronto city councillors that he had a grudge against, and it was a bill to cut the size of Toronto city council in half. Interestingly enough, that was a bill that also did not g
```

**Ontario total: 327 bills | 168,672 paragraphs**
*(vs full sitting-day corpus: ~1.6M sentences before extraction)*

### US — GovInfo Granule (Bill-Specific by Definition)

Each GovInfo granule corresponds to one bill's floor debate.
No extraction needed — the granule IS the bill-specific text.

**2008-01-23 | N = 7,697 words**

```
=== Daily Digest/Senate; Congressional Record Vol. 154, No. 10 ===
[Daily Digest]
[Pages D33-D34]
From the Congressional Record Online through the Government Publishing Office [
www.gpo.gov
]



                                        Wednesday, January 23, 2008

[[Page D33]]

                              Daily Digest

                                 Senate


Chamber Action
Routine Proceedings,
```

**1990-09-27 | N = 122,281 words**

```
--- GPO-CRECB-1990-pt18-1-2 ---
September 24, 1990

CONGRESSIONAL RECORD—HOUSE

25435

HOUSE OF REPRESENTATIVES—Monday, September 24, 1990

The House met at 12 noon.

The Chaplain, Rev. James David
Ford, D.D., offered the following
prayer:

We are overwhelmed, O God, when
we come into a vast cathedral, by Your
great majesty and glory and might and
we realize that Your plans are greater
than our pl
```

---
## Stage 3: Sentence Tokenization

| Jurisdiction | Input | Output sentences | Claim-bearing (DB1) |
|---|---|---|---|
| US | 145 granule files | 376,347 sentences | 58,979 (15.7%) |
| Ontario | OLA API paragraphs | TBD (pipeline running) | TBD |
| Quebec | Bill segments | 923,634 sentences | 329,790 (35.7%) |

---
## Stage 4: DBpedia Spotlight Entity Linking

Spotlight identifies named entities in each sentence and links them to DBpedia URIs.

**Example — English (Ontario/US):**
```
Input:  'The Ontario Medical Association has endorsed this legislation.'
Output: entities = ['Ontario_Medical_Association', 'Legislation']
        → concept pair: (Ontario_Medical_Association, Legislation)
```

**Example — French (Quebec):**
```
Input:  'Le gouvernement a modifié la Loi sur les services de santé.'
Output: entities = ['Gouvernement_du_Québec', 'Health_care_in_Canada']
        → concept pair: (Gouvernement_du_Québec, Health_care_in_Canada)
```

**Note:** Single-entity sentences (~60% of corpus) cannot form pairs
and are counted in the denominator as unverifiable claim-bearing sentences.

---
## Stage 5: SPARQL / DBpedia Verification

For each unique entity pair, a SPARQL query checks whether DBpedia
confirms a direct relationship between the two entities.

**Query template:**
```sparql
SELECT ?a ?b ?p WHERE {
  VALUES (?a ?b) { (<URI_A> <URI_B>) }
  { ?a ?p ?b } UNION { ?b ?p ?a }
}
```

**Example — Supported:**
```
Pair: (Canada, United_States)
Result: dbo:neighboringMunicipality, dbo:country → supported = True
```

**Example — Not supported:**
```
Pair: (Ontario_Medical_Association, Legislation)
Result: [] → supported = False
```

| Jurisdiction | Unique pairs | Supported | Support rate |
|---|---|---|---|
| US | ~200K | ~30K | ~15% |
| Ontario | TBD (pipeline running) | TBD | TBD |
| Quebec | 130,691 | 43,004 sentences | 13.1% |

---
## Stage 6: Factuality Score

Factuality score = supported claim-bearing sentences / total claim-bearing sentences

| Jurisdiction | Mean factuality | Passed | Failed |
|---|---|---|---|
| US | 0.2054 | 0.2094 (n=386) | 0.2015 (n=34) |
| Ontario | TBD | TBD | TBD |
| Quebec | 0.1387 | 0.1266 (n=767) | n/a |
