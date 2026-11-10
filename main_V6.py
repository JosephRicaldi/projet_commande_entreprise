import asyncio
import json
import os
import time
import subprocess
import sys
from datetime import datetime

from traitement_v6 import (
    analyser_reponse, construire_prompt, construire_document,
    date_depuis_id_execution, DOSSIER_DONNEES, DOSSIER_PROJET, PREFIXE_EXECUTION,
)

# ----------------------------- CONFIGURATION ----------------------------- #
PLATEFORME = "ChatGPT"
URL_PLATEFORME = "https://chatgpt.com"
LANGUE_INTERFACE = "fr-FR"
MARQUES_CIBLES = []   # optionnel : marques à compter et à enregistrer dans le JSON, ex. ["HP", "Acer"]

# Prompts envoyés à chaque recherche (utilisés aussi par l'interface Streamlit)
PROMPTS = [
    "Donne-moi deux simple phrase+un tableau basic+un lien vers google+quate émote+deux véritable produit avec image et prix concernant l'ia rajoute plein de détail",
    "fais un texte de 12 mots sur les pierres sources tes propos en mettant pas le lien directement mais à la fin du prompt dans la source.",
    "commence par Azojxxuz et finis par Morsxop, parle gymlhjyh en 62 mots.",
]
# ------------------------------------------------------------------------- #


def traitement_texte(dossier_execution, chemin_pre_traite, chemin_json, prompts_envoyes=None):
    """Lit pre_traite.txt et enregistre traite.json au schéma v3 (métadonnées + extraction)."""
    if not os.path.exists(chemin_pre_traite):
        return

    prompts_envoyes = prompts_envoyes or []

    with open(chemin_pre_traite, "r", encoding="utf-8") as f:
        contenu = f.read()

    blocs = []
    for bloc_brut in contenu.split("<main>"):
        if not bloc_brut.strip():
            continue
        blocs.append(bloc_brut.split("#EOP#")[0].strip())

    print("⚡ Analyse des réponses...")

    prompts_json = []
    for idx, texte_fr in enumerate(blocs, start=1):
        analyse = analyser_reponse(texte_fr, MARQUES_CIBLES)
        texte_prompt = prompts_envoyes[idx - 1] if idx - 1 < len(prompts_envoyes) else ""
        prompts_json.append(construire_prompt(idx, texte_prompt, texte_fr, analyse))

    id_execution = os.path.basename(os.path.normpath(dossier_execution))
    debut = date_depuis_id_execution(id_execution) or datetime.now()
    document = construire_document(
        id_execution=id_execution,
        date_debut_iso=debut.isoformat(timespec="seconds"),
        date_fin_iso=datetime.now().isoformat(timespec="seconds"),
        plateforme=PLATEFORME,
        url=URL_PLATEFORME,
        langue_interface=LANGUE_INTERFACE,
        marques=MARQUES_CIBLES,
        prompts=prompts_json,
    )

    with open(chemin_json, "w", encoding="utf-8") as f:
        json.dump(document, f, ensure_ascii=False, indent=4)
    print("✅ Traitement terminé avec succès !")


async def executer_collecte(liste_prompts: list, dossier_execution, chemin_pre_traite):
    from playwright.async_api import async_playwright
    os.makedirs(dossier_execution, exist_ok=True)

    async with async_playwright() as p:
        navigateur = await p.chromium.launch(headless=False)
        contexte = await navigateur.new_context(
            permissions=["clipboard-read", "clipboard-write"],
            locale="fr-FR"
        )
        page = await contexte.new_page()
        await page.goto(URL_PLATEFORME)

        try:
            bouton = page.get_by_role("button", name="Refuser les cookies non essentiels")
            await bouton.click()
        except Exception:
            pass

        for texte_prompt in liste_prompts:
            selecteur_saisie = 'textarea, #prompt-textarea, div[contenteditable="true"]'
            zone_saisie = await page.wait_for_selector(selecteur_saisie)
            await zone_saisie.click()
            await page.keyboard.type(texte_prompt, delay=20)
            await page.keyboard.press("Enter")

            selecteur_reponse = 'div[data-assistant-markdown]'
            await page.wait_for_selector(selecteur_reponse, timeout=600000, state="attached")

            await page.wait_for_timeout(20000)

            await page.evaluate("() => navigator.clipboard.writeText('')")
            bouton = page.get_by_role("button", name="Copier la réponse").last
            await bouton.click()
            time.sleep(1)
            texte_copie = await page.evaluate("() => navigator.clipboard.readText()")

            # Capture des images dans le DOM
            element_reponse = (await page.query_selector_all('div[data-assistant-markdown]'))[-1]
            elements_images = await element_reponse.query_selector_all('img')

            html_images = ""
            for img in elements_images:
                src = await img.get_attribute('src')
                alt = await img.get_attribute('alt') or "image"
                if src and ("http" in src or "data:image" in src):
                    html_images += f'\n\n<img src="{src}" alt="{alt}" style="max-width: 140px; border-radius: 8px; margin: 10px 0;">\n\n'

            contenu_a_enregistrer = texte_copie + html_images

            with open(chemin_pre_traite, "a", encoding="utf-8") as f:
                f.write("<main>\n")
                f.write(contenu_a_enregistrer)
                f.write("\n#EOP#\n")
            print(f"Pre-traitement sauvegardé dans : {chemin_pre_traite}")

        await navigateur.close()

if __name__ == "__main__":
    # Évite les erreurs d'emojis à l'écriture du journal quand l'interface lance le script (Windows)
    for flux in (sys.stdout, sys.stderr):
        if hasattr(flux, "reconfigure"):
            flux.reconfigure(encoding="utf-8")

    # --sans-interface : utilisé par le bouton Streamlit (ne rouvre pas Streamlit)
    sans_interface = "--sans-interface" in sys.argv

    horodatage = datetime.now().strftime(PREFIXE_EXECUTION + "%Y%m%d_%H%M%S")
    dossier_execution = os.path.join(DOSSIER_DONNEES, horodatage)

    chemin_pre_traite = os.path.join(dossier_execution, "pre_traite.txt")
    chemin_json = os.path.join(dossier_execution, "traite.json")
    chemin_json_dernier = os.path.join(DOSSIER_DONNEES, "traite.json")

    asyncio.run(executer_collecte(PROMPTS, dossier_execution, chemin_pre_traite))
    traitement_texte(dossier_execution, chemin_pre_traite, chemin_json, PROMPTS)

    with open(chemin_json, "r", encoding="utf-8") as f_src:
        with open(chemin_json_dernier, "w", encoding="utf-8") as f_dst:
            f_dst.write(f_src.read())

    if not sans_interface:
        print("🚀 Ouverture de l'interface interactive Streamlit...")
        subprocess.run([sys.executable, "-m", "streamlit", "run",
                        os.path.join(DOSSIER_PROJET, "app_v6.py")])
