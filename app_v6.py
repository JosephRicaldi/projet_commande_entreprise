import html
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, time as heure

import pandas as pd
import streamlit as st

from traitement_v6 import (
    charger_execution, compter_marques, date_depuis_id_execution,
    DOSSIER_DONNEES, DOSSIER_PROJET, PREFIXE_EXECUTION, ANCIEN_PREFIXE,
)
from main_V6 import PROMPTS   # les prompts envoyés à chaque recherche

DOSSIER_BASE = DOSSIER_DONNEES
SCRIPT_MAIN = os.path.join(DOSSIER_PROJET, "main_V6.py")
CHEMIN_LOG = os.path.join(DOSSIER_BASE, "execution_actuelle.log")
os.makedirs(DOSSIER_BASE, exist_ok=True)

st.set_page_config(page_title="Observatoire de visibilité IA", page_icon="🔎", layout="wide")

# --------------------------------------------------------------------------- #
# Styles
# --------------------------------------------------------------------------- #
st.markdown("""
<style>
    .stApp { background-color: #FAFAFA;
             font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    .chatgpt-price { color: #10a37f; font-size: 1.25rem; font-weight: 700; margin: 4px 0; }
    table { width: 100%; border-collapse: collapse; margin: 15px 0; background-color: #FFFFFF;
            border-radius: 8px; overflow: hidden; border: 1px solid #E5E5E5; }
    th, td { padding: 12px 16px; text-align: left; border-bottom: 1px solid #F0F0F0; }
    th { background-color: #F9F9F9; font-weight: 600; }
    a { color: #2563EB !important; text-decoration: none; font-weight: 500; }
    a:hover { text-decoration: underline; }
    .prompt-box { background:#F3F4F6; border-left:4px solid #10a37f; padding:10px 14px;
                  border-radius:6px; margin-bottom:10px; font-size:0.95rem; }
</style>
""", unsafe_allow_html=True)

RE_PRIX = re.compile(r"^(#{1,6})\s*(\d[\d\s.,]*\s*(?:€|EUR|\$))\s*$", re.M)


# --------------------------------------------------------------------------- #
# Utilitaires
# --------------------------------------------------------------------------- #
def lister_executions():
    """Toutes les exécutions, de la plus récente à la plus ancienne."""
    executions = []
    if not os.path.isdir(DOSSIER_BASE):
        return executions
    for nom in os.listdir(DOSSIER_BASE):
        chemin = os.path.join(DOSSIER_BASE, nom, "traite.json")
        if nom.startswith((PREFIXE_EXECUTION, ANCIEN_PREFIXE)) and os.path.exists(chemin):
            date = date_depuis_id_execution(nom) or datetime.fromtimestamp(os.path.getmtime(chemin))
            executions.append({"id_execution": nom, "date": date, "chemin": chemin,
                               "date_modif": os.path.getmtime(chemin)})
    executions.sort(key=lambda r: r["date"], reverse=True)
    return executions


@st.cache_data(show_spinner=False)
def charger(chemin: str, date_modif: float):
    return charger_execution(chemin)


def fmt_date(dt: datetime) -> str:
    return dt.strftime("%d/%m/%Y à %H:%M:%S")


def surligner_prix(md: str) -> str:
    return RE_PRIX.sub(r'<div class="chatgpt-price">\2</div>', md)


def df_tableau(tableau: dict) -> pd.DataFrame:
    vus, colonnes = {}, []
    for c in tableau["en_tetes"]:                  # noms de colonnes uniques
        vus[c] = vus.get(c, 0) + 1
        colonnes.append(c if vus[c] == 1 else f"{c} ({vus[c]})")
    return pd.DataFrame(tableau["lignes"], columns=colonnes)


def df_liens(prompts, avec_prompt=False) -> pd.DataFrame:
    lignes = []
    for p in prompts:
        for e in p["extraction"]["liens"]:
            ligne = {"Texte": e["texte"] or "—", "Domaine": e["domaine"], "URL": e["url_propre"]}
            if avec_prompt:
                ligne = {"Prompt": p["id"], **ligne}
            lignes.append(ligne)
    return pd.DataFrame(lignes)


def lire_log() -> str:
    try:
        with open(CHEMIN_LOG, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def lancer_recherche():
    """Lance main_V6.py dans un processus séparé : Chromium s'ouvre et une nouvelle exécution est enregistrée."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    log = open(CHEMIN_LOG, "w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-u", SCRIPT_MAIN, "--sans-interface"],
                            cwd=DOSSIER_PROJET, stdout=log, stderr=subprocess.STDOUT, env=env)
    st.session_state["proc"] = proc
    st.session_state["proc_debut"] = time.time()
    st.session_state["ids_avant"] = {r["id_execution"] for r in lister_executions()}


CFG_URL = {"URL": st.column_config.LinkColumn("URL")}

# --------------------------------------------------------------------------- #
# Barre latérale (1/2) : nouvelle recherche
# --------------------------------------------------------------------------- #
st.title("🔎 Observatoire de visibilité IA")
st.sidebar.title("⚙️ Configuration")

proc_actuel = st.session_state.get("proc")
en_cours = proc_actuel is not None and proc_actuel.poll() is None

if st.sidebar.button("▶ Générer une nouvelle recherche", type="primary", disabled=en_cours,
                     help="Ouvre Chromium, envoie les prompts à ChatGPT et enregistre le résultat "
                          "avec la date et l'heure."):
    lancer_recherche()

with st.sidebar.expander("Prompts envoyés à chaque recherche"):
    for i, p in enumerate(PROMPTS, start=1):
        st.caption(f"**{i}.** {p}")

# --------------------------------------------------------------------------- #
# Suivi de la recherche en cours (bloque la page jusqu'à la fin)
# --------------------------------------------------------------------------- #
proc = st.session_state.get("proc")
if proc is not None:
    debut = st.session_state.get("proc_debut", time.time())
    with st.status("Recherche en cours… Chromium s'ouvre et envoie les prompts à ChatGPT. "
                   "Ne fermez pas cette page.", expanded=True) as etat:
        zone = st.empty()
        while proc.poll() is None:
            faits = lire_log().count("Pre-traitement sauvegardé")
            zone.markdown(f"⏱️ {int(time.time() - debut)} s · prompts terminés : "
                          f"**{faits}/{len(PROMPTS)}**")
            time.sleep(2)
        if proc.returncode == 0:
            etat.update(label="Recherche terminée ✅", state="complete", expanded=False)
        else:
            etat.update(label="La recherche a échoué ❌", state="error", expanded=True)

    st.session_state.pop("proc", None)
    st.cache_data.clear()
    ids_avant = st.session_state.pop("ids_avant", set())
    nouveaux = [r["id_execution"] for r in lister_executions() if r["id_execution"] not in ids_avant]
    if proc.returncode == 0 and nouveaux:
        st.session_state["sel_execution"] = nouveaux[0]   # la nouvelle exécution est sélectionnée automatiquement
        st.rerun()
    else:
        st.error("Aucune nouvelle exécution n'a été enregistrée. Dernières lignes du journal :")
        st.code("\n".join(lire_log().strip().splitlines()[-15:]) or "(journal vide)")

# --------------------------------------------------------------------------- #
# Barre latérale (2/2) : sélection de l'exécution
# --------------------------------------------------------------------------- #
executions_toutes = lister_executions()
if not executions_toutes:
    st.warning(f"Aucune exécution dans « {DOSSIER_BASE} ». Cliquez sur « Générer une nouvelle recherche ».")
    st.stop()

ids = [r["id_execution"] for r in executions_toutes]
par_id = {r["id_execution"]: r for r in executions_toutes}
if st.session_state.get("sel_execution") not in ids:
    st.session_state["sel_execution"] = ids[0]

# BOUTON 1 (principal) : une exécution précise, par date et heure
sel_id = st.sidebar.selectbox(
    "🕘 Exécution (date et heure)", ids, key="sel_execution",
    format_func=lambda i: ("🆕 " if i == ids[0] else "") + fmt_date(par_id[i]["date"]))
exec_sel = par_id[sel_id]

# BOUTON 2 (secondaire) : plage de dates et d'heures, pour l'onglet Historique
f_min, f_max = min(r["date"] for r in executions_toutes).date(), max(r["date"] for r in executions_toutes).date()
with st.sidebar.expander("📅 Plage de dates et d'heures (onglet Historique)"):
    plage = st.date_input("Dates", (f_min, f_max), min_value=f_min, max_value=f_max)
    t1 = st.time_input("De", heure(0, 0), step=60)
    t2 = st.time_input("À", heure(23, 59), step=60)
plage = tuple(plage) if isinstance(plage, (tuple, list)) else (plage,)
d1, d2 = (plage[0], plage[-1])
debut_plage = datetime.combine(d1, t1)
fin_plage = datetime.combine(d2, t2).replace(second=59)
executions_plage = [r for r in executions_toutes if debut_plage <= r["date"] <= fin_plage]

marques_txt = st.sidebar.text_input(
    "🏷️ Marques à compter (séparées par des virgules)", "", placeholder="ex. HP, Acer",
    help="Facultatif. Compte combien de fois chaque nom apparaît dans les réponses de ChatGPT. "
         "Vous choisissez les marques : l'application ne les devine pas.")
marques = [m.strip() for m in marques_txt.split(",") if m.strip()]

if st.sidebar.button("🔄 Recharger"):
    st.cache_data.clear()

# --------------------------------------------------------------------------- #
# En-tête de l'exécution sélectionnée
# --------------------------------------------------------------------------- #
doc = charger(exec_sel["chemin"], exec_sel["date_modif"])
meta, prompts = doc["execution"], doc["prompts"]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Date", exec_sel["date"].strftime("%d/%m/%Y"))
c2.metric("Heure", exec_sel["date"].strftime("%H:%M:%S"))
c3.metric("Plateforme", meta.get("plateforme", "—"))
c4.metric("Prompts", meta.get("n_prompts", len(prompts)))
c5.metric("Liens", sum(p["extraction"]["statistiques"]["n_liens"] for p in prompts))
if meta.get("ancien_format"):
    st.info("Exécution à l'ancien format : analysée au chargement "
            "(le texte des prompts n'était pas enregistré).")

tab_reponses, tab_analyse, tab_historique = st.tabs(["💬 Réponses", "📊 Analyse de cette exécution", "🕘 Historique"])

# --------------------------------------------------------------------------- #
# Onglet 1 · Réponses
# --------------------------------------------------------------------------- #
with tab_reponses:
    for p in prompts:
        ex, stat = p["extraction"], p["extraction"]["statistiques"]
        titre = p["prompt"][:90] + ("…" if len(p["prompt"]) > 90 else "")
        with st.expander(f"📌 Prompt {p['id']} — {titre}", expanded=(p["id"] == 1)):
            if p["prompt"]:
                st.markdown(f'<div class="prompt-box"><b>Prompt :</b> {html.escape(p["prompt"])}</div>',
                            unsafe_allow_html=True)
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Mots", stat["mots"])
            m2.metric("Liens", stat["n_liens"])
            m3.metric("Domaines", len(ex["domaines"]))
            m4.metric("Tableaux", stat["n_tableaux"])
            m5.metric("Images", stat["n_images"])

            sous_rep, sous_tab, sous_liens, sous_json = st.tabs(["Réponse", "Tableaux", "Liens", "Données (JSON)"])

            with sous_rep:
                st.markdown(surligner_prix(p["reponse"]["markdown"]), unsafe_allow_html=True)
                if ex["images"]:
                    st.caption("Images capturées")
                    cols = st.columns(min(len(ex["images"]), 4))
                    for i, img in enumerate(ex["images"]):
                        try:
                            cols[i % len(cols)].image(img["src"], caption=img["alt"], width=140)
                        except Exception:
                            cols[i % len(cols)].caption(f"(image non affichable : {img['alt']})")

            with sous_tab:
                if ex["tableaux"]:
                    for i, t in enumerate(ex["tableaux"], start=1):
                        st.caption(f"Tableau {i} · {len(t['lignes'])} lignes × {len(t['en_tetes'])} colonnes")
                        st.dataframe(df_tableau(t), hide_index=True)
                else:
                    st.info("Cette réponse ne contient aucun tableau.")

            with sous_liens:
                df = df_liens([p])
                if len(df):
                    st.dataframe(df, hide_index=True, column_config=CFG_URL)
                else:
                    st.info("Cette réponse ne contient aucun lien.")

            with sous_json:
                st.json(p, expanded=False)

# --------------------------------------------------------------------------- #
# Onglet 2 · Analyse de l'exécution sélectionnée
# --------------------------------------------------------------------------- #
with tab_analyse:
    st.subheader("Résumé par prompt")
    st.dataframe(pd.DataFrame([{
        "Prompt": p["id"],
        "Texte du prompt": p["prompt"] or "—",
        "Mots": p["extraction"]["statistiques"]["mots"],
        "Liens": p["extraction"]["statistiques"]["n_liens"],
        "Tableaux": p["extraction"]["statistiques"]["n_tableaux"],
        "Images": p["extraction"]["statistiques"]["n_images"],
    } for p in prompts]), hide_index=True)

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Sources (domaines cités)")
        cumul = {}
        for p in prompts:
            for d, n in p["extraction"]["domaines"].items():
                cumul[d] = cumul.get(d, 0) + n
        if cumul:
            st.bar_chart(pd.Series(cumul).sort_values(ascending=False))
        else:
            st.info("Aucun lien dans cette exécution.")
    with col_b:
        st.subheader("Marques citées par prompt")
        if not marques:
            st.info("Saisissez des marques dans la barre latérale (ex. HP, Acer) pour les compter.")
        else:
            df_m = pd.DataFrame({f"Prompt {p['id']}": {m: compter_marques(p["reponse"]["texte_simple"], marques).get(m, 0)
                                                      for m in marques} for p in prompts}).T
            if df_m.values.sum():
                st.bar_chart(df_m)
            else:
                st.info("Aucune de ces marques n'apparaît dans cette exécution.")

    st.subheader("Tous les liens de l'exécution")
    df_e = df_liens(prompts, avec_prompt=True)
    if len(df_e):
        st.dataframe(df_e, hide_index=True, column_config=CFG_URL)
        st.download_button("⬇️ Télécharger les liens (CSV)", df_e.to_csv(index=False).encode("utf-8"),
                           file_name=f"{exec_sel['id_execution']}_liens.csv", mime="text/csv",
                           help="Fichier tableur (s'ouvre dans Excel) avec la liste des liens de cette exécution.")
    st.download_button("⬇️ Télécharger l'exécution (JSON)",
                       json.dumps(doc, ensure_ascii=False, indent=2).encode("utf-8"),
                       file_name=f"{exec_sel['id_execution']}.json", mime="application/json",
                       help="Copie du fichier traite.json de cette exécution (il est déjà enregistré dans le dossier du projet).")

# --------------------------------------------------------------------------- #
# Onglet 3 · Historique (plage de dates et d'heures)
# --------------------------------------------------------------------------- #
with tab_historique:
    st.caption(f"Plage affichée : {fmt_date(debut_plage)} → {fmt_date(fin_plage)} "
               "(modifiable dans la barre latérale)")
    if not executions_plage:
        st.info("Aucune exécution dans cette plage.")
    else:
        charges = [(r, charger(r["chemin"], r["date_modif"])) for r in executions_plage]

        st.subheader(f"Exécutions ({len(charges)})")
        st.dataframe(pd.DataFrame([{
            "Date": r["date"].strftime("%d/%m/%Y"),
            "Heure": r["date"].strftime("%H:%M:%S"),
            "Exécution": r["id_execution"],
            "Plateforme": d["execution"].get("plateforme", "—"),
            "Prompts": len(d["prompts"]),
            "Mots": sum(p["extraction"]["statistiques"]["mots"] for p in d["prompts"]),
            "Liens": sum(p["extraction"]["statistiques"]["n_liens"] for p in d["prompts"]),
            "Tableaux": sum(p["extraction"]["statistiques"]["n_tableaux"] for p in d["prompts"]),
            "Images": sum(p["extraction"]["statistiques"]["n_images"] for p in d["prompts"]),
        } for r, d in charges]), hide_index=True)

        col_c, col_d = st.columns(2)
        with col_c:
            st.subheader("Domaines les plus cités")
            cumul = {}
            for _, d in charges:
                for p in d["prompts"]:
                    for dom_, n in p["extraction"]["domaines"].items():
                        cumul[dom_] = cumul.get(dom_, 0) + n
            if cumul:
                st.bar_chart(pd.Series(cumul).sort_values(ascending=False))
            else:
                st.info("Aucun lien dans cette plage.")
        with col_d:
            st.subheader("Mentions de marques dans le temps")
            if not marques:
                st.info("Saisissez des marques dans la barre latérale (ex. HP, Acer).")
            else:
                evolution = pd.DataFrame(
                    [{m: sum(compter_marques(p["reponse"]["texte_simple"], marques).get(m, 0)
                             for p in d["prompts"]) for m in marques} for _, d in charges],
                    index=[fmt_date(r["date"]) for r, _ in charges])
                if evolution.values.sum() == 0:
                    st.info("Aucune de ces marques n'apparaît dans cette plage.")
                else:
                    st.dataframe(evolution)
                    if len(evolution) > 1:
                        st.line_chart(evolution.iloc[::-1])
                    else:
                        st.caption("Le graphique apparaîtra à partir de 2 exécutions.")

        st.subheader("Comparer un même prompt entre exécutions")
        textes = sorted({p["prompt"] for _, d in charges for p in d["prompts"] if p["prompt"]})
        if textes:
            choisi = st.selectbox("Prompt", textes, format_func=lambda t: t[:110])
            lignes = []
            for r, d in charges:
                for p in d["prompts"]:
                    if p["prompt"] == choisi:
                        ex = p["extraction"]
                        lignes.append({
                            "Date et heure": fmt_date(r["date"]),
                            "Mots": ex["statistiques"]["mots"],
                            "Liens": ex["statistiques"]["n_liens"],
                            "Domaines": ", ".join(ex["domaines"]) or "—",
                            "Marques": ", ".join(f"{m} ({n})" for m, n in
                                                 compter_marques(p["reponse"]["texte_simple"], marques).items()) or "—",
                        })
            st.dataframe(pd.DataFrame(lignes), hide_index=True)
            st.caption("Si la même question donne des sources différentes à chaque exécution, "
                       "c'est la variabilité (non-déterminisme) de la plateforme.")
        else:
            st.info("Les anciennes exécutions n'enregistraient pas le texte du prompt ; "
                    "cette comparaison sera disponible avec les nouvelles.")

        frames = []
        for r, d in charges:
            df = df_liens(d["prompts"], avec_prompt=True)
            if len(df):
                frames.append(df.assign(**{"Exécution": r["id_execution"], "Date et heure": fmt_date(r["date"])}))
        if frames:
            st.download_button("⬇️ Télécharger l'historique des liens (CSV)",
                               pd.concat(frames, ignore_index=True).to_csv(index=False).encode("utf-8"),
                               file_name="historique_liens.csv", mime="text/csv")
