"""
traitement_v6.py
----------------
Fonctions partagées par main_V6.py (collecte) et app_v6.py (visualisation) :

  - DOSSIER_DONNEES      : dossier où sont enregistrées les exécutions (à modifier ici si besoin)
  - normaliser_markdown  : corrige les tableaux que ChatGPT copie avec des lignes vides entre les lignes
  - analyser_reponse     : extrait liens, tableaux, images, domaines, marques et statistiques
  - construire_*         : assemble le JSON (schéma v3)
  - charger_execution    : lit un traite.json (schéma v3, schéma v2 en espagnol ou ancien format fr/es/en)

Tout reste dans la langue d'origine (le français). Il n'y a pas de traduction pour le moment.
"""
import json
import os
import re
from collections import Counter
from datetime import datetime
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

VERSION_SCHEMA = 3

# Dossier du projet et dossier des données (chemin absolu : fonctionne même si le script est lancé d'ailleurs)
DOSSIER_PROJET = os.path.dirname(os.path.abspath(__file__))
DOSSIER_DONNEES = os.path.join(DOSSIER_PROJET, "telechargements_v6")

# Préfixe des dossiers d'exécution (« run_ » = ancien préfixe, toujours reconnu)
PREFIXE_EXECUTION = "execution_"
ANCIEN_PREFIXE = "run_"

# --------------------------------------------------------------------------- #
# Expressions régulières
# --------------------------------------------------------------------------- #
RE_IMG = re.compile(r"<img\s[^>]*>", re.I)
RE_IMG_SRC = re.compile(r'src="([^"]*)"', re.I)
RE_IMG_ALT = re.compile(r'alt="([^"]*)"', re.I)
RE_LIEN_MD = re.compile(r"\[([^\]]+)\]\(\s*<?([^)>\s]+)>?[^)]*\)")
RE_URL_NUE = re.compile(r"https?://[^\s<>)\]]+")


# --------------------------------------------------------------------------- #
# Utilitaires de texte
# --------------------------------------------------------------------------- #
def normaliser_markdown(texte: str) -> str:
    """Supprime les lignes vides entre les lignes d'un tableau et réduit les sauts de ligne répétés."""
    lignes = texte.replace("\r\n", "\n").split("\n")
    sortie = []
    for i, ligne in enumerate(lignes):
        if not ligne.strip():
            precedente = next((x for x in reversed(sortie) if x.strip()), None)
            suivante = next((x for x in lignes[i + 1:] if x.strip()), None)
            if (precedente and suivante
                    and precedente.strip().startswith("|") and suivante.strip().startswith("|")):
                continue
        sortie.append(ligne)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(sortie)).strip()


def retirer_images(md: str) -> str:
    return RE_IMG.sub("", md)


def vers_texte_simple(md: str) -> str:
    t = retirer_images(md)
    t = RE_LIEN_MD.sub(r"\1", t)
    t = re.sub(r"^\s*#{1,6}\s*", "", t, flags=re.M)
    t = re.sub(r"^\s*[-*]\s+", "", t, flags=re.M)
    t = re.sub(r"[*`]{1,3}", "", t)
    t = t.replace("|", " ")
    t = re.sub(r"^\s*[-: ]+$", "", t, flags=re.M)
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n{2,}", "\n", t).strip()


# --------------------------------------------------------------------------- #
# Liens
# --------------------------------------------------------------------------- #
def nettoyer_url(url: str) -> str:
    """Supprime les paramètres utm_* (ex. ?utm_source=chatgpt.com)."""
    p = urlparse(url)
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
         if not k.lower().startswith("utm_")]
    return urlunparse(p._replace(query=urlencode(q)))


def domaine_de(url: str) -> str:
    d = urlparse(url).netloc.lower()
    return d[4:] if d.startswith("www.") else d


def extraire_liens(md: str) -> list:
    liens = []
    sans_img = retirer_images(md)
    for texte, url in RE_LIEN_MD.findall(sans_img):
        if url.startswith("http"):
            liens.append({"texte": texte.strip(), "url": url,
                          "url_propre": nettoyer_url(url), "domaine": domaine_de(url)})
    reste = RE_LIEN_MD.sub(" ", sans_img)  # évite de compter deux fois les URL des liens markdown
    for url in RE_URL_NUE.findall(reste):
        url = url.rstrip(".,;")
        liens.append({"texte": "", "url": url,
                      "url_propre": nettoyer_url(url), "domaine": domaine_de(url)})
    return liens


# --------------------------------------------------------------------------- #
# Tableaux
# --------------------------------------------------------------------------- #
def _cellules(ligne: str) -> list:
    l = ligne.strip()
    if l.startswith("|"):
        l = l[1:]
    if l.endswith("|"):
        l = l[:-1]
    return [c.strip() for c in l.split("|")]


def est_separateur(ligne: str) -> bool:
    l = ligne.replace(" ", "")
    return bool(l) and "---" in l and set(l) <= set("|:-")


def extraire_tableaux(md: str) -> list:
    lignes = normaliser_markdown(md).split("\n")
    tableaux, i = [], 0
    while i < len(lignes):
        if (lignes[i].strip().startswith("|") and i + 1 < len(lignes)
                and est_separateur(lignes[i + 1])):
            en_tetes = _cellules(lignes[i])
            i += 2
            donnees = []
            while i < len(lignes) and lignes[i].strip().startswith("|"):
                ligne = _cellules(lignes[i])
                ligne += [""] * (len(en_tetes) - len(ligne))
                donnees.append(ligne[:len(en_tetes)])
                i += 1
            tableaux.append({"en_tetes": en_tetes, "lignes": donnees})
        else:
            i += 1
    return tableaux


# --------------------------------------------------------------------------- #
# Images et marques
# --------------------------------------------------------------------------- #
def extraire_images(brut: str) -> list:
    images = []
    for balise in RE_IMG.findall(brut):
        src = RE_IMG_SRC.search(balise)
        alt = RE_IMG_ALT.search(balise)
        if src:
            images.append({"src": src.group(1), "alt": alt.group(1) if alt else "image"})
    return images


def compter_marques(texte: str, marques) -> dict:
    res = {}
    for m in marques or []:
        m = m.strip()
        if not m:
            continue
        n = len(re.findall(r"(?<!\w)" + re.escape(m) + r"(?!\w)", texte, flags=re.I))
        if n:
            res[m] = n
    return res


# --------------------------------------------------------------------------- #
# Analyse complète d'une réponse
# --------------------------------------------------------------------------- #
def analyser_reponse(brut: str, marques=None) -> dict:
    markdown = normaliser_markdown(retirer_images(brut))
    simple = vers_texte_simple(markdown)
    liens = extraire_liens(brut)
    tableaux = extraire_tableaux(markdown)
    images = extraire_images(brut)
    domaines = dict(Counter(e["domaine"] for e in liens))
    return {
        "markdown": markdown,
        "texte_simple": simple,
        "extraction": {
            "liens": liens,
            "tableaux": tableaux,
            "images": images,
            "domaines": domaines,
            "marques_citees": compter_marques(simple, marques),
            "statistiques": {
                "mots": len(simple.split()),
                "caracteres": len(simple),
                "n_liens": len(liens),
                "n_tableaux": len(tableaux),
                "n_images": len(images),
            },
        },
    }


# --------------------------------------------------------------------------- #
# Construction du JSON (schéma v3)
# --------------------------------------------------------------------------- #
def date_depuis_id_execution(id_execution: str):
    for fmt in (PREFIXE_EXECUTION + "%Y%m%d_%H%M%S", ANCIEN_PREFIXE + "%Y%m%d_%H%M%S"):
        try:
            return datetime.strptime(id_execution, fmt)
        except ValueError:
            continue
    return None


def construire_prompt(idx, prompt, brut, analyse) -> dict:
    return {
        "id": idx,
        "prompt": prompt,
        "reponse": {
            "langue_originale": "fr",
            "markdown": analyse["markdown"],
            "texte_simple": analyse["texte_simple"],
            "brut": brut,
        },
        "extraction": analyse["extraction"],
    }


def construire_document(id_execution, date_debut_iso, date_fin_iso, plateforme, url,
                        langue_interface, marques, prompts, ancien_format=False) -> dict:
    return {
        "version_schema": VERSION_SCHEMA,
        "execution": {
            "id_execution": id_execution,
            "date_debut_iso": date_debut_iso,
            "date_fin_iso": date_fin_iso,
            "plateforme": plateforme,
            "url": url,
            "langue_interface": langue_interface,
            "marques_cibles": list(marques or []),
            "n_prompts": len(prompts),
            "ancien_format": ancien_format,
        },
        "prompts": prompts,
    }


# --------------------------------------------------------------------------- #
# Lecture d'un traite.json (avec compatibilité avec les anciens formats)
# --------------------------------------------------------------------------- #
# Correspondance des clés du schéma v2 (espagnol) vers le schéma v3 (français)
_CLES_V2_VERS_V3 = {
    "schema_version": "version_schema", "run": "execution", "run_id": "id_execution",
    "fecha_inicio_iso": "date_debut_iso", "fecha_fin_iso": "date_fin_iso",
    "plataforma": "plateforme", "idioma_interfaz": "langue_interface",
    "marcas_objetivo": "marques_cibles", "legacy": "ancien_format",
    "respuesta": "reponse", "idioma_original": "langue_originale",
    "texto_plano": "texte_simple", "raw": "brut", "extraccion": "extraction",
    "enlaces": "liens", "tablas": "tableaux", "imagenes": "images",
    "dominios": "domaines", "marcas_citadas": "marques_citees",
    "estadisticas": "statistiques", "palabras": "mots",
    "n_enlaces": "n_liens", "n_tablas": "n_tableaux", "n_imagenes": "n_images",
    "texto": "texte", "url_limpia": "url_propre", "dominio": "domaine",
    "encabezados": "en_tetes", "filas": "lignes",
}


def _migrer_v2(obj):
    if isinstance(obj, dict):
        return {_CLES_V2_VERS_V3.get(k, k): _migrer_v2(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_migrer_v2(x) for x in obj]
    return obj


def charger_execution(chemin: str) -> dict:
    """Lit un traite.json. Convertit le schéma v2 (espagnol) et l'ancien format ({'prompt 1': {'fr', ...}})."""
    with open(chemin, "r", encoding="utf-8") as f:
        donnees = json.load(f)

    if isinstance(donnees, dict) and donnees.get("version_schema"):
        return donnees
    if isinstance(donnees, dict) and donnees.get("schema_version"):
        donnees = _migrer_v2(donnees)
        donnees["version_schema"] = VERSION_SCHEMA
        return donnees

    id_execution = os.path.basename(os.path.dirname(chemin))
    date = date_depuis_id_execution(id_execution)
    iso = date.isoformat(timespec="seconds") if date else ""
    prompts = []
    for i, (cle, val) in enumerate(donnees.items(), start=1):
        fr = val.get("fr", "")
        prompts.append(construire_prompt(i, cle, fr, analyser_reponse(fr, [])))
    return construire_document(id_execution, iso, iso, "ChatGPT", "https://chatgpt.com",
                               "fr-FR", [], prompts, ancien_format=True)
