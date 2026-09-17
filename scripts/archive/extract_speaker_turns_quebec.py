"""
extract_speaker_turns_quebec.py

Extracts speaker-attributed speech turns from Quebec National Assembly transcripts.
Speaker labels follow the pattern: "M. Legault:" or "Mme Anglade:" or "Le Président:"

Usage: python3 scripts/extract_speaker_turns_quebec.py
"""
import os, json, re
from collections import defaultdict
import unicodedata
import glob

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRANSCRIPT_DIR = os.path.join(REPO_ROOT, "data/canada/quebec_assembly")
MEMBERS_PATH = os.path.join(REPO_ROOT, "data/canada/quebec_members_recent.json")
OUTPUT_PATH = os.path.join(REPO_ROOT, "data/canada/quebec_speaker_turns.json")

# Quebec Assembly speaker patterns
SPEAKER_RE = re.compile(
    r'^((?:M\.|Mme|Le\s+Président|La\s+Présidente|Le\s+Vice-Président|'
    r'La\s+Vice-Présidente|M\.\s+le\s+ministre|Mme\s+la\s+ministre|'
    r'M\.\s+le\s+premier\s+ministre|Le\s+Président)\s*[\w\s\-\'àâäéèêëîïôùûüçœæ]*?):\s*',
    re.MULTILINE | re.IGNORECASE
)

EXCLUDE_SPEAKERS = {
    "le président", "la présidente", "le vice-président", "la vice-présidente",
    "le président suppléant", "la présidente suppléante"
}


def strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s)
                   if unicodedata.category(c) != 'Mn')

def normalize_name(raw):
    name = re.sub(r'\s+', ' ', raw)  # collapse all whitespace including newlines
    # post-1994 format: "Christine St-Pierre Mme St-Pierre" — take only the last name part
    # detect pattern: full name followed by title + short name
    double = re.match(r'^(.+?)\s+(M\.|Mme)\s+(\S+)\s*$', name, re.IGNORECASE)
    if double:
        name = double.group(3)  # take just the last name part after the repeated title
    name = re.sub(r'^(M\.|Mme)\s+', '', name, flags=re.IGNORECASE)
    name = re.sub(r'^(le\s+ministre|la\s+ministre|le\s+premier\s+ministre)\s*', '', name, flags=re.IGNORECASE)
    return name.strip().lower()


def extract_turns(text):
    turns = []
    matches = list(SPEAKER_RE.finditer(text))

    for i, m in enumerate(matches):
        speaker_raw = m.group(1).strip()
        speaker_norm = normalize_name(speaker_raw)

        if speaker_norm.lower() in EXCLUDE_SPEAKERS:
            continue
        if not speaker_norm or len(speaker_norm) < 2:
            continue

        start = m.end()
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        speech = text[start:end].strip()

        if len(speech) > 20:
            is_minister = bool(re.search(r'ministre|premier\s+ministre', speaker_raw, re.IGNORECASE))
            turns.append({
                "speaker_raw": speaker_raw,
                "speaker_normalized": speaker_norm,
                "text": speech[:500],
                "char_count": len(speech),
                "is_minister": is_minister,
            })

    return turns


def build_name_lookup(members):
    import csv
    ppb_path = os.path.join(REPO_ROOT, "data/canada/PPB.csv")
    lookup = {}
    flat = {}

    if os.path.exists(ppb_path):
        with open(ppb_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("province", "").lower() != "quebec":
                    continue
                name = row.get("first_last", "").strip().lower()
                parts = name.split("_")
                # PPB stores as firstname_lastname or firstname_middlename_lastname
                # last name is the final part, but hyphenated surnames are stored as separate parts
                # e.g. rita_dionne_marsolais -> last = dionne-marsolais
                if len(parts) >= 3:
                    last = "-".join(parts[1:])  # everything after first name
                    last_single = parts[-1]      # just final part as fallback
                elif len(parts) == 2:
                    last = parts[-1]
                    last_single = parts[-1]
                else:
                    last = name
                    last_single = name
                last_stripped = strip_accents(last)
                
                party = row.get("party", "")
                year = row.get("year", "")
                if last and party:
                    lookup[(last, year)] = party
                    lookup[(last_stripped, year)] = party
                    flat[last] = party
                    flat[last_stripped] = party
                    last_nohyphen = last_stripped.replace("-", "")
                    lookup[(last_nohyphen, year)] = party
                    flat[last_nohyphen] = party
                    if '-' in last_stripped:
                        last_final = last_stripped.split('-')[-1]
                        lookup[(last_final, year)] = party
                        flat[last_final] = party

    OCR_FIXES = {
        # garbled name → correct PPB last name (must exist in flat)
        "bouierice": "bourgeois",
        "uncoln": "lincoln",
        "béiisle": "belisle",
        "bélisie": "belisle",
        "gobei": "gobeil",
        "joiivet": "jolivet",
        "harei": "harel",
        "boisciair": "boisclair",
        "rémilard": "remillard",
        "rémiilard": "remillard",
        "blackbum": "blackburn",
        "vailières": "vallieres",
        "ubman": "libman",
        "lefevbre": "lefebvre",
        "fiiion": "filion",
        "va liera nd": "vallerand",
        "robiilard": "robillard",
        "charbomeau": "charbonneau",
        "charbornneau": "charbonneau",
        "pouiin": "poulin",
        "beauine": "beaudin",
        "rocheieau": "rocheleau",   # Gilles Rocheleau, Liberal
        "macdonakj": "macdonald",   # Pierre MacDonald, Liberal 
        "la porte": "laporte",
        "rémiliard": "remillard",
        "oufour": "dufour",
        "howen": "holden",  
        "loiseile": "loiselle",
        "hoiden": "holden",
        "bordeieau": "bordeleau", # Additional OCR fixes - all confirmed MNAs
        "rémiiiard": "remillard",
        "hard": "harel",
        "jolrvet": "jolivet",
        "jollvet": "jolivet", 
        "jollivet": "jolivet",
        "jotivet": "jolivet",
        "jotlvet": "jolivet",
        "j olivet": "jolivet",
        "jcjivet": "jolivet",
        "joli vet": "jolivet",
        "vaiiières": "vallieres",
        "valiières": "vallieres",
        "homen": "holden",
        "hokjen": "holden",
        "hotden": "holden",
        "macmilian": "macmillan",
        "macoonald": "macdonald",
        "macdonaw": "macdonald",
        "macdonaid": "macdonald",
        "gobefl": "gobeil",
        "gobel": "gobeil",
        "gobeii": "gobeil",
        "lederc": "leclerc",
        "vailerand": "vallerand",
        "lefebbre": "lefebvre",
        "leîebvre": "lefebvre",
        "chabonneau": "charbonneau",
        "charbonnea": "charbonneau",
        "charbomeau": "charbonneau",
        "charbonoeau": "charbonneau",
        "charbormeau": "charbonneau",
        "roeheleau": "rocheleau",
        "rocnefort": "rocheleau",
        "rocherfort": "rocheleau",
        "ver mette": "vermette",
        "latuiippe": "latulippe",
        "séguln": "seguin",
        "rlvard": "rivard",
        "rivant": "rivard",
        "fition": "filion",
        "fllion": "filion",
        "grattoin": "gratton",
        "ooyon": "doyon",
        "oesbiens": "desbiens",
        "leveaque": "levesque",
        "levesgue": "levesque",
        "bourrassa": "bourassa",
        "bourasa": "bourassa",
        "boursssa": "bourassa",
        "trench": "french",
        "camion": "cannon",
        "bout beau": "bourbeau",
        "marcl": "marcil",
        "mardi": "marcil",
        "marcii": "marcil",
        "béiisie": "belisle",
        "m.bélisle": "belisle",
        "m.middlemiss": "middlemiss",
        "mkjdlemiss": "middlemiss",
        "m.trudel": "trudel",
        "eikas": "elkas",
        "carrier-perreauh": "carrier-perreault",
        "carrier-perreauk": "carrier-perreault",
        "trépanler": "trepanier",
        "nicole loiselie mme loiselie": "loiselle",
        "liza frulia mme frulia": "frulla",
        "oupuis": "dupuis",
        "luce dupuis mme oupuis": "dupuis",
        "france dionne mme oionne": "dionne",
        "hotden": "holden",
        "qendron": "gendron",
        "hamei": "hamel",
        "sûtos": "sirros",
        "trudd": "trudel",
        "chary": "cherry",
        "bourbon": "bourbeau",
        "gagnon-trernblay": "gagnon-tremblay",
            "théorôt": "theoret",
        "boulerlce": "bourgeois",
        "momeau": "moreau",
        "m.middlemiss": "middlemiss",
        "panneau": "cannon",
        "fllion": "filion",
        "khelta": "khelfa",
        "gagnon-trernblay": "gagnon-tremblay",
        "warner": None,
        "diamant": None,
        # confirmed civil servants/procedural — exclude entirely
        "mockle": None,
        "abgral": None,
        "d'astous": None,
        "querido": None,
        "quérido": None,
        "bougie": None,
        "st-roch": None,
        "saint-roch": None,
        "le président le président": None,
        "le président- une voix": None,
        "le vice-présidente": None,
        "la présidente- la vice-présidente": None,
        "boisvert": None,    # civil servant, student aid program
        "prémont": None,     # parliamentary librarian/official
        "disait tantôt": None,   # regex false positive on "M. le ministre disait tantôt"
        "le président du conseil du trésor dit": None,   # regex false positive
        "noël de tiliy": None,
        "gabrièle": None,
        "warner": None,
        "khelta": None,
        "mettais": None,
        "la présidente-la vice-présidente": None,
        "le président du conseil du trésor nous dit": None,
        "dit": None,
        "johnson disait": None,
        "yvon lemire adjoint parlementaire au ministre de la main-d'oeuvre et de la sécurité du revenu et ministre du travail 11 mars 1986 membres de l'assemblée nationale du québec président": None,
        "le président du conseil du trésor disait": None,
        "lesage écrit toujours": None,
        "la présidente - cela me permet de terminer - cela me fait penser immédiatement au dire d'un homme politique pas tout à fait inconnu du chef de l'opposition qui disait": None,
        "pourrait me dire": None,
        "le président du conseil du trésor a dit": None,
        "le député de lévis disait tout à l'heure": None,
        "le président du conseil du trésor très honnêtement avait dit": None,
        "le président de l'association des hôpitaux du québec nous dit": None,
        "le président du conseil du trésor disait ceci le 2 juin": None,
        "le président du conseil du trésor a eu également l'occasion de dire ceci": None,
        "le président du conseil du trésor dit ceci": None,
        "le président du conseil du trésor a eu l'occasion d'ajouter ceci": None,
        "le président de l'association des hôpitaux du québec disait récemment": None,
        "gagnon-trernblay": "gagnon-tremblay",
        "baron": "bacon",
        "carrier-perreauh": "carrier-perreault",
        "carrier-perreauk": "carrier-perreault",
        "dubuc continue en expliquant": None,
        "michel girard disait ceci": None,
        "smereka concluait en disant": None,
        "le président a posé une question": None,
        "a parlé aussi des programmes d'aide à l'accession à la propriété": None,
        "perreault vient de le dire": None,
        "le député de lévis présente la motion suivante": None,
        "le président du conseil du trésor va nous dire": None,
        "le député de jacques-cartier a présenté la motion suivante": None,
        "la députée de hochelaga-maisonneuve situait le débat au niveau des garderies": None,
        "a tellement bien expliqué": None,
        "charland pose une question": None,
        "carrier-perreauh": "perreault",
        "carrier-perreauk": "perreault",

        "trépanler": "trepanier",
            "gagnon-trernblay": "gagnon-tremblay",  # fix this one
        "rivard disait aussi": None,
        "dubuc concluait ainsi": None,
        "dubuc poursuivait dans son éditorial": None,
        "dubuc termine son développement sur cette notion de ticket modérateur en disant": None,
        "dubuc ajoutait": None,
        "la députée de dorion semblait dire": None,
        "le député de gouin pour sa part nous disait": None,
        "nous disait tout à l'heure": None,
        "des affaires culturelles des voix": None,
        "mulroney rassure le canada anglais": None,
        "le président de l'assemblée nationale ajoutait même": None,
        "le président de l'upa continue": None,
        "scott a dit à un autre moment": None,
        "létourneau continue": None,
        "le vice-président le vice-président": None,
        "réjean doyon adjoint parlementaire au ministre des relations internationales octobre 1987 président": None,
        "comeau continue": None,
        "rémy poulin le vice-président": None,
        "herbert marx le vice-président": None,
        "lesage écrit": None,
        "oumais": None,
        "francoeur titre": None,
        "la députée va dire": None,
        "lesage continue dans le journal le devoir": None,
        "bourassa avait comme argument à cette époque": None,
        "la présidente- une voix": None,
        "michel roy continuait": None,
        "bernard saint-laurent": None,
        "jdy": None,
        "me demande": None,
        "admet qu'il y a eu une baisse": None,
        "disait": None,
        "a dit à plusieurs reprises": None,
        "dufour je la répète": None,
        "la députée de marie-victorin présente la motion suivante": None,
        "le président du conseil du trésor nous disait": None,
        "lesage continuait": None,
        "le député de louis-hébert nous disait": None,
        "whissel": "whissell",
        "loiselie": "loiselle",
        "frulia": "frulla",
        # Commission witnesses, journalists quoted, diplomatic visitors, procedural captures
        "brault": None,
        "noël de tilly": None,
        "marsolais": None,
        "renaud": None,
        "furlong": None,
        "brant pour lui dire": None,
        "michel david ajoutait": None,
        "bourgault continue en disant": None,
        "cloutier continue": None,
        "bissonnette disait également": None,
        "giusti conclut en disant": None,
        "bureau disait ceci": None,
        "ryan continue": None,
        "la présidente de l'ordre poursuit": None,
        "duchesne poursuit": None,
        "breton continue": None,
        "gagnon poursuit": None,
        "reid continue en disant": None,
        "samson terminait sa chronique avec cette phrase": None,
        "gagné termine en effet son article en écrivant": None,
        "bérubé conclut en disant": None,
        "perreault poursuit en nous disant": None,
        "caillé continue": None,
        "daigneault-bourdeau rappelait hier": None,
        "brisebois disait récemment à la ministre": None,
        "samson du soleil disait ceci": None,
        "gadbois continue de croire": None,
        "jean-robert sansfaçon": None,
        "castonguay de lui poser la question": None,
        "dutrisac continue en disant": None,
        "robitaille continue en disant": None,
        "lapalme disait aussi": None,
        "bacon nous a aussi offert plusieurs livres magnifiques aux titres évocateurs": None,
        "rhéaume a littéralement consacré sa vie au québec et à l'idée qu'il s'en faisait": None,
        "dion reconnaîtra les paroles de cette chanson qui lui est si chère": None,
        "desfossés incarne ce qu'il y a de plus beau dans l'engagement bénévole": None,
        "kirkland-casgrain fut une pionnière": None,
        "sima samar pour ses nominations": None,
        "nicole duplé à titre de membre": None,
        "john zacharias à titre de commissaire": None,
        "simon nabukwesi le président": None,
        "orestis athanasios kafopoulos le président": None,
        "hélène le gal le président": None,
        "barbeau n'a pas faites": None,
        "alejandra zaga mendez 19 263 mme zaga mendez": None,
        "lisée liste": None,
        "des finances nous avait dit aussi en commentant ce rapport mensuel": None,
        "le président jean-pierre saintonge indiquait le 14 mai 1992": None,
        "le président a fait mention des mandats qui ont été donnés à différents niveaux": None,
        "la députée de jean-talon se pose la question": None,
        "jacques fournier disait ceci": None,
        "champagne disait en commission parlementaire": None,
        "le président du conseil du trésor pourra nous dire": None,
        "le président de la commission d'accès à l'information nous dit ceci": None,
        "le président du conseil du trésor puis le ministre des finances ont expliqué au ministre de la sécurité publique ou à ses conseillers": None,
        "plamondon est venue ici jeudi dernier pour dire au ministre": None,
        "nicolas marceau ajournement annexes sommaire des opérations budgétaires -- année financière 2011-2012 sommaire des opérations budgétaires -- prévisions 2012-2013 revenus budgétaires du fonds général -- prévisions 2012-2013 dépenses budgétaires du fonds général -- prévisions 2012-2013 opérations non budgétaires -- prévisions 2012-2013 opérations de financement -- prévisions 2012-2013 annexes du discours dur le budget plan budgétaire 2012-2013 section a": None,
        "henri-françois gautrin mise aux voix renvoi à la commission des finances publiques mise aux voix ajournement annexes sommaire des opérations budgétaires -- année financière 2012-2013 sommaire des opérations budgétaires -- prévisions 2013-2014 revenus budgétaires du fonds général -- prévisions 2013-2014 dépenses budgétaires du fonds général -- prévisions 2013-2014 opérations non budgétaires -- prévisions 2013-2014 opérations de financement -- prévisions 2013-2014 annexes du discours sur le budget plan budgétaire 2013-2014 section a": None,
        "stéphane bergeron dépôt de documents rapport d'appréciation de la performance du système de santé et de services sociaux intitulé les médicaments d'ordonnance": None,
        "francois blais souligner le 100e anniversaire des chevaliers de colomb du conseil de st-eustache no": None,
        "harold lebel féliciter les lauréats des prix de l'île mme caroline simard souligner le succès de la guignolée organisée par les chevaliers de colomb du conseil de beloeil no": None,
        "jean boucher rendre hommage aux chevaliers de colomb du conseil de stemadeleine no": None,
        "stéphanie vallée mise aux voix dépôt de documents documentintitulé paradis fiscaux": None,
        "jennifer maccarone dépôt de documents réponse à une pétition réponses à des questions inscrites au feuilleton prévisions budgétaires et rapport financier préliminaire du directeur général des élections et de la commission de la représentation électorale rapport du directeur général des élections intitulé financement politique": None,
        "jean boulet mise aux voix dépôt de documents dépôt de rapports de commissions audition d'hydro-québec sur le chapitre 5 du rapport de décembre 2022 du vérificateur général intitulé hydro-québec": None,
        "andrés fontecilla mme elisabeth prass mise aux voix renvoià la commission de la santé et des services sociaux mise aux voix débats sur les rapports de commissions prise en considération du rapport de la commission qui a procédé à l'audition d'hydro-québec sur le chapitre 5 du rapport de décembre 2022 du vérificateur général intitulé hydro-québec": None,
        "louis lemieux appuyer le rapport d'amnistie internationaleintitulé l'apartheid israélien envers le peuple palestinien": None,
        "marilyne picard saluer la campagne fonds vers l'avenir": None,
        "geneviève hébert souligner le succès du film documentaire je vous salue salope": None,
        "geneviève guilbault souligner le lancement du livre de la vallée aux sommets": None,
        "pierre-étienne laporte mise aux voix procéder à une consultation générale sur le document intitulé l'immigration au québec de 1998 à 2000": None,
        "le député de lafontaine présente la motion suivante": None,
        "le président du conseil du trésor a dit hier": None,
        "alexandre cloutier le président": None,
        "carole poirier le président": None,
        "lise thériault le président": None,
        "jean-françois roberge le président": None,
        "paul st-pierre plamondon la présidente": None,
        "sonia lebel la présidente": None,
        "guillaume cliche-rivard la présidente": None,
        "jean boucher souligner le 100e anniversaire": None,
        "stéphane billette féliciter aidants scolaires": None,
        "marc picard souligner le 100e anniversaire": None,
        "luc blanchette mise aux voix": None,
        "luc blanchette souligner le succès": None,
        "raymond bernier décision de la présidence": None,
        "diane lamarre mise aux voix": None,
        "pierre arcand souligner le 25e anniversaire": None,
        "jean boulet mise aux voix dépôt de documents": None,
        "jean boucher féliciter les artisans": None,
        "jean boucher souligner le succès": None,
        "yves séguin motions sans préavis": None,
        "francois legault ajournement annexes": None,
        "nicolas marceau ajournement annexes": None,
        "andré boulerice mme michelle courchesne mise aux voix": None,
        "solange charest mise aux voix dépôt de documents": None,
        "jacques brassard mise aux voix dépôt de documents": None,
        "henri-francois gautrin mise aux voix": None,
        "pierre paradis le président note de l'éditeur": None,
        "dubuc dit ceci": None,
        "vient nous dire": None,
        "nous répond": None,
        "solange charest mise aux voix dépôt de documents livre vert intitulé la sécurité routière au québec": None,
        "cope man": None,
        "gadbois continue de croire que la fusion des huit villes n'est pas la meilleure solution pour renforcer l'avenir de larive-sud": None,
        "jacques brassard mise aux voix dépôt de documents avant-projet de loi instituant l'union civile des personnes de même sexe et modifiant le code civil et d'autres dispositions législatives et document intitulé pour un traitement égalitaire": None,
        "sima samar pour ses nominations au sein du gouvernementintérimaire afghan et pour sa contribution à la cause des femmes le président": None,
        "jacques chagnon la présidente": None,
        "andré boulerice mme michelle courchesne mise aux voix féliciter les lauréats du concours québécois en entrepreneurshipmise aux voix procéder à une consultation générale sur le document intitulé une réforme de l'accès à l'information": None,
        "agnès maltais le président": None,
        "yves séguin motions sans préavis procéder à des consultations particulières sur le document intitulé la sécurité privée": None,
        "françois legault ajournement annexes sommaire des opérations financières consolidées - année financière 2003-2004 sommaire des opérations financières consolidées - prévisions 2004-2005 revenus budgétaires du fonds consolidé du revenu - prévisions 2004-2005 dépenses du fonds consolidé du revenu - prévisions2004-2005 opérations budgétaires des organismes consolidés - prévisions 2004-2005 opérations non budgétaires - prévisions 2004-2005 opérations de financement - prévisions 2004-2005 annexesdu discours sur le budget renseignements additionnels sur les mesures du budget section 1": None,
        "jacques parizeau le président": None,
        "louise harel le président": None,
        "andré boisclair le président": None,
        "fatima houda-pepin la vice-présidente": None,
        "pauline marois le président": None,
        "nicole duplé à titre de membre de la commission des droits de la personne et des droits de la jeunesse le président": None,
        "gadbois continue de croire que la fusion des huit villes n'est pas la meilleure solution pour renforcer l'avenir de larive-sud": None,
        "sima samar pour ses nominations au sein du gouvernementintérimaire afghan et pour sa contribution à la cause des femmes le président": None,
        "sima samar pour ses nominations au sein du gouvernement intérimaire afghan et pour sa contribution à la cause des femmes le président": None,
        "andré boulerice mme michelle courchesne mise aux voix féliciter les lauréats du concours québécois en entrepreneurshipmise aux voix procéder à une consultation générale sur le document intitulé une réforme de l'accès à l'information": None,
        "andré boulerice mme michelle courchesne mise aux voix féliciter les lauréats du concours québécois en entrepreneurship mise aux voix procéder à une consultation générale sur le document intitulé une réforme de l'accès à l'information": None,
        "françois legault ajournement annexes sommaire des opérations financières consolidées - année financière 2003-2004 sommaire des opérations financières consolidées - prévisions 2004-2005 revenus budgétaires du fonds consolidé du revenu - prévisions 2004-2005 dépenses du fonds consolidé du revenu - prévisions2004-2005 opérations budgétaires des organismes consolidés - prévisions 2004-2005 opérations non budgétaires - prévisions 2004-2005 opérations de financement - prévisions 2004-2005 annexesdu discours sur le budget renseignements additionnels sur les mesures du budget section 1": None,
        "françois legault ajournement annexes sommaire des opérations financières consolidées - année financière 2003-2004 sommaire des opérations financières consolidées - prévisions 2004-2005revenus budgétaires du fonds consolidé du revenu - prévisions 2004-2005 dépenses du fonds consolidé du revenu - prévisions 2004-2005 opérations budgétaires des organismes consolidés - prévisions 2004-2005 opérations non budgétaires - prévisions 2004-2005 opérations de financement - prévisions 2004-2005 annexes dudiscours sur le budget renseignements additionnels sur les mesures du budget section 1": None,
        "sébastien proulx le président": None,
        "monique jérôme-forget le président": None,
        "denise beaudoin le président": None,
        "couillard a rappelé que pour régler pour de bon les problèmes des urgences il fallait s'attaquer aux problèmes existant en amont": None,
        "john zacharias à titre de commissaire à la commission de la représentation électorale du québec le président": None,
        "jean boucher rendre hommage aux chevaliers de colomb duconseil de ste-madeleine no": None,
        "jean boucher rendre hommage aux chevaliers de colomb du conseil de ste-madeleine no": None,
        "marc picard souligner le 100e anniversaire des chevaliers de colomb du conseil de lachine no": None,
        "françois paradis le président": None,
        "simon jolin-barrette le président": None,
        "de l'éducation vous disait tantôt": None,
        "luc blanchette mise aux voix dépôt de documents plan d'action gouvernemental 2015-2018 intitulé la radicalisation au québec": None,
        "kirkland-casgrain fut une pionnière de la lutte pour l'égalité entre les femmes et les hommes": None,
        "raymond bernier décision de la présidence sur la recevabilité de la question de violation de droit ou de privilège soulevée aux affaires courantes sur le dépôt du document intitulé rapport d'audit": None,
        "luc blanchette souligner le succès de la conférence internet et la radicalisation des jeunes": None,
        "sylvie d'amours le président": None,
        "le président du conseil du trésor nous a dit à de multiples reprises": None,
        "diane lamarre mise aux voix dépôt de documents réponses à des pétitions rapport du directeur général des élections intitulé financement politique": None,
        "jean-françois roberge mme dominique vien série télévisée canada": None,
        "jean boucher féliciter les artisans du recueil 1792": None,
        "pierre arcand souligner le 25e anniversaire du baladeur rené de longueuil mme diane lamarre dépôt de documents rapport sur l'application de la loi sur l'administration publique réponseà une question inscrite au feuilleton rapport du commissaire au lobbyisme intitulé la révision de la loi sur la transparence et l'éthique en matière de lobbyisme": None,
        "stéphanie vallée mise aux voix dépôt de documents documentintitulé paradis fiscaux": None,
        "le président de la fae affirme": None,
        "quévillon a déclaré en recevant son prix": None,
        "louis lemieux appuyer le rapport d'amnistie internationaleintitulé l'apartheid israélien envers le peuple palestinien": None,
        "andrés fontecilla mme elisabeth prass mise aux voix renvoià la commission de la santé et des services sociaux mise aux voix débats sur les rapports de commissions prise en considération du rapport de la commission qui a procédé à l'audition d'hydro-québec sur le chapitre 5 du rapport de décembre 2022 du vérificateur général intitulé hydro-québec": None,
        "gadbois continue de croire que la fusion des huit villes n'est pas la meilleure solution pour renforcer l'avenir de larive-sud": None,
        "françois legault ajournement annexes sommaire des opérations financières consolidées - année financière 2003-2004 sommaire des opérations financières consolidées - prévisions 2004-2005 revenus budgétaires du fonds consolidé du revenu - prévisions 2004-2005 dépenses du fonds consolidé du revenu - prévisions2004-2005 opérations budgétaires des organismes consolidés - prévisions 2004-2005 opérations non budgétaires - prévisions 2004-2005 opérations de financement - prévisions 2004-2005 annexesdu discours sur le budget renseignements additionnels sur les mesures du budget section 1": None,
        "pierre arcand souligner le 25e anniversaire du baladeurrené de longueuil mme diane lamarre dépôt de documents rapportsur l'application de la loi sur l'administration publique réponse à une question inscrite au feuilleton rapport du commissaire au lobbyisme intitulé la révision de la loi sur la transparence et l'éthique en matière de lobbyisme": None,
        "stéphanie vallée mise aux voix dépôt de documents document intitulé paradis fiscaux": None,
        "louis lemieux appuyer le rapport d'amnistie internationale intitulé l'apartheid israélien envers le peuple palestinien": None,
        "andrés fontecilla mme elisabeth prass mise aux voix renvoi à la commission de la santé et des services sociaux mise aux voix débats sur les rapports de commissions prise en considération du rapport de la commission qui a procédé à l'audition d'hydro-québec sur le chapitre 5 du rapport de décembre 2022 du vérificateur général intitulé hydro-québec": None,
    }

    for garbled, correct in OCR_FIXES.items():
        if correct is None:
            flat[garbled] = "EXCLUDE"
            flat[strip_accents(garbled)] = "EXCLUDE"
        elif correct in flat:
            flat[garbled] = flat[correct]
            flat[strip_accents(garbled)] = flat[correct]

    MANUAL_PARTY = {
        # Verified from 33rd legislature cabinet list
        "lincoln": "Liberal",
        "gobeil": "Liberal",
        "remillard": "Liberal",
        "blackburn": "Liberal",
        "trepanier": "Liberal",
        # Verified from 34th legislature cabinet list
        "frulla": "Liberal",
        "lefebvre": "Liberal",
        # Confirmed opposition MNAs from transcript content
        "biais": "Parti québécois",
        "marais": "Parti québécois",
        "wilson": "Parti québécois",
        # Civil servants — exclude
        "morneau": "EXCLUDE",
        "l'heureux": "EXCLUDE",
        
        #other confirmed
        "outil": "dutil",
        "st-roch": "Liberal",
        "saint-roch": "Liberal",
        "baron": "Liberal",
        "gagnon-trernblay": "Liberal",
        "gagnon-tremblay": "Liberal",

        # All verified from assnat.qc.ca and/or Wikipedia
        "beauchemin": "Parti libéral du Québec",          # Frédéric Beauchemin, Liberal, assnat PDF ✓
        "duranceau": "Coalition avenir Québec",            # France-Élaine Duranceau, CAQ, assnat PDF ✓
        "d'amour": "Parti libéral du Québec",              # Jean D'Amour, Liberal, assnat biography ✓
        "cadet": "Parti libéral du Québec",                # Madwa-Nika Cadet, Liberal, assnat PDF ✓
        "setlakwe": "Parti libéral du Québec",             # Michelle Setlakwe, Liberal, assnat PDF ✓
        "prass": "Parti libéral du Québec",                # Elisabeth Prass, Liberal, assnat PDF ✓
        "bouazzi": "Québec solidaire",                     # Haroun Bouazzi, QS, assnat PDF ✓
        "garceau": "Parti libéral du Québec",              # Brigitte B. Garceau, Liberal, assnat PDF ✓
        "alejandra zaga mendez mme zaga mendez": "Québec solidaire",  # double-capture, QS ✓
        "d'amours": "Coalition avenir Québec",             # Sylvie D'Amours, CAQ, assnat PDF ✓
        "déry": "Coalition avenir Québec",                 # Pascale Déry, CAQ, assnat PDF ✓
        "mcgraw": "Parti libéral du Québec",               # Désirée McGraw, Liberal, assnat PDF ✓
        "surprenant": "Coalition avenir Québec",           # Claude Surprenant, CAQ 2014-2017, Wikipedia ✓
        "rita de santis mme de santis": "Parti libéral du Québec",   # double-capture, Liberal ✓
        "rita lc de santis mme de santis": "Parti libéral du Québec", # same person ✓
        "l'écuyer": "Parti libéral du Québec",             # Charlotte L'Écuyer, Liberal, Wikipedia ✓
        "gentilcore": "Parti québécois",                   # Catherine Gentilcore, PQ, assnat + Le Devoir ✓
        "le bouyonnec": "Coalition avenir Québec",         # Stéphane Le Bouyonnec, CAQ 2012-2014, assnat ✓
        "zaga mendez": "Québec solidaire",                 # Alejandra Zaga Mendez, QS, assnat PDF ✓
        "poulet": "Coalition avenir Québec",               # Isabelle Poulet, CAQ 2022-2025, then Independent ✓
        # All verified from assnat.qc.ca PDF and Wikipedia
        "boissonneault": "Parti québécois",
        "mallette": "Coalition avenir Québec",
        "de santis": "Parti libéral du Québec",
        "st-louis": "Coalition avenir Québec",
        "dorismond": "Coalition avenir Québec",
        "schmaltz": "Coalition avenir Québec",
        "bogemans": "Coalition avenir Québec",
        "haytayan": "Coalition avenir Québec",
        "sainte-croix": "Coalition avenir Québec",
        "montigny": "Coalition avenir Québec",
        "laflamme": "Parti québécois",
        "abou-khalil": "Coalition avenir Québec",
        "le hir": "Parti québécois",
        "roy verville": "Action démocratique du Québec",
        "monique roy verville mme roy verville": "Action démocratique du Québec",
        "oionne": "Parti québécois",  # OCR of Dionne, already in PPB as dionne
        "la présidente la présidente": "EXCLUDE",
        "picher disait également ceci": "EXCLUDE",
        "bourgault a même ajouté": "EXCLUDE",
        
    }

    for name, party in MANUAL_PARTY.items():
        flat[name] = party
        flat[strip_accents(name)] = party

    return lookup, flat


def main():
    # load member data
    name_to_party = {}
    if os.path.exists(MEMBERS_PATH):
        with open(MEMBERS_PATH, encoding="utf-8") as f:
            members = json.load(f)
        name_to_party, flat_lookup = build_name_lookup(members)
        print(f"Loaded {len(members)} Quebec members")
    else:
        print("Quebec members file not found - party matching will be limited")
        name_to_party, flat_lookup = {}, {}

    if not os.path.exists(TRANSCRIPT_DIR):
        print(f"Transcript directory not found: {TRANSCRIPT_DIR}")
        return

        
    transcript_files = sorted(
        glob.glob(os.path.join(TRANSCRIPT_DIR, "*.txt")) +
        glob.glob(os.path.join(TRANSCRIPT_DIR, "transcripts", "*.txt"))
    )
    transcript_files = [os.path.basename(f) for f in transcript_files]
    print(f"{len(transcript_files)} Quebec transcript files")

    results = {}
    total_turns = 0

    for fname in transcript_files:
        date = fname.replace(".txt", "")
        # check both directories
        fpath = os.path.join(TRANSCRIPT_DIR, fname)
        if not os.path.exists(fpath):
            fpath = os.path.join(TRANSCRIPT_DIR, "transcripts", fname)

        with open(fpath, encoding="utf-8", errors="replace") as f:
            text = f.read()

        turns = extract_turns(text)

        kept_turns = []
        for turn in turns:
            norm = turn["speaker_normalized"]
            last = norm.split()[-1] if norm else ""
            last_stripped = strip_accents(last)
            norm_stripped = strip_accents(norm)
            year = date[:4]
            # exclude obvious procedural captures — no real MNA name is this long
            if len(norm) > 60:
                continue
            last_final = last_stripped.split('-')[-1] if '-' in last_stripped else last_stripped
            last_nohyphen = last_stripped.replace("-", "")
            party = (flat_lookup.get(norm) or
                         flat_lookup.get(norm_stripped) or
                         name_to_party.get((last_stripped, year)) or
                         name_to_party.get((last_nohyphen, year)) or
                         name_to_party.get((last_final, year)) or
                         name_to_party.get((last, year)) or
                         flat_lookup.get(last_stripped) or
                         flat_lookup.get(last_nohyphen) or
                         flat_lookup.get(last_final) or
                         flat_lookup.get(last, ""))
            if party == "EXCLUDE":
                continue
            turn["party"] = party
            kept_turns.append(turn)

        results[date] = {
            "date": date,
            "turn_count": len(kept_turns),
            "speakers": list(set(t["speaker_normalized"] for t in kept_turns)),
            "turns": kept_turns,
        }
        total_turns += len(kept_turns)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"Processed {len(results)} transcript files")
    print(f"Total speaker turns: {total_turns}")
    print(f"Saved to {OUTPUT_PATH}")

    dates_with_turns = [d for d, v in results.items() if v["turn_count"] > 0]
    if dates_with_turns:
        sample = dates_with_turns[len(dates_with_turns)//2]
        print(f"\nSample from {sample}:")
        for t in results[sample]["turns"][:3]:
            print(f"  {t['speaker_raw']} [{t.get('party','?')}]: {t['text'][:80]}...")


if __name__ == "__main__":
    main()

