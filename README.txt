================================================================================
 OBSERVATOIRE DE VISIBILITÉ IA
================================================================================

Outil qui mesure ce que répond un assistant d'IA (actuellement ChatGPT) et
quelles sources il cite face à un ensemble fixe de prompts. Il automatise la
capture des réponses depuis l'interface web, en extrait la structure (liens,
domaines, tableaux, images, marques mentionnées) et la présente dans un
tableau de bord interactif avec historique et comparaison entre exécutions.

Technologies : Python 3.11+, Streamlit, Playwright (Chromium), pandas.


--------------------------------------------------------------------------------
 FONCTIONNEMENT
--------------------------------------------------------------------------------

   main_V6.py --> Playwright/Chromium --> ChatGPT
       |                                     |
       |       pre_traite.txt  <-------------+   (réponse brute + images)
       v
   traitement_v6.py --> analyser_reponse() --> traite.json (schéma v3)
                                                    |
   app_v6.py (Streamlit)  <-------------------------+   (visualisation et historique)

  1. main_V6.py ouvre le navigateur, envoie chaque prompt de la liste PROMPTS
     et enregistre la réponse dans pre_traite.txt.
  2. traitement_v6.py normalise le Markdown et extrait liens, tableaux,
     images, domaines et marques.
  3. traite.json est généré dans le dossier de l'exécution, avec une copie de
     la dernière exécution dans telechargements_v6/traite.json.
  4. app_v6.py lit toutes les exécutions et les affiche ; il peut aussi lancer
     une nouvelle collecte avec le bouton « Générer une nouvelle recherche ».


--------------------------------------------------------------------------------
 INSTALLATION (WINDOWS)
--------------------------------------------------------------------------------
 Prérequis : Python 3.11 ou supérieur (cocher « Add python.exe to PATH » lors
 de l'installation) et une connexion internet.

 Ouvrir PowerShell dans le dossier du projet, puis :

  1. Vérifier Python :

         python --version

  2. Créer l'environnement virtuel :

         python -m venv venv

  3. Activer l'environnement virtuel :

         .\venv\Scripts\Activate.ps1

     (dans CMD : venv\Scripts\activate.bat)
     Le prompt affiche (venv) au début de la ligne.

     Si PowerShell bloque le script, exécuter une seule fois :

         Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

  4. Installer les bibliothèques depuis requirements.txt :

         python -m pip install --upgrade pip
         pip install -r requirements.txt

     requirements.txt contient :

         streamlit==1.66.0
         pandas==3.0.6
         playwright==1.64.0

     (requirements-full.txt = copie complète de l'environnement de
     développement, avec torch, spacy, etc. Facultatif et très lourd.)

  5. Installer le navigateur Chromium de Playwright :

         playwright install chromium


--------------------------------------------------------------------------------
 UTILISATION
--------------------------------------------------------------------------------
 Avec l'environnement virtuel activé :

  Option 1 - Depuis le tableau de bord (recommandé) :

         streamlit run app_v6.py

     Ouvre http://localhost:8501. Cliquer sur « Générer une nouvelle
     recherche » dans la barre latérale : Chromium s'ouvre, envoie les prompts
     à ChatGPT, puis la nouvelle exécution est sélectionnée automatiquement.
     Ne pas fermer la page pendant la collecte.

  Option 2 - En ligne de commande :

         python main_V6.py                    (collecte, puis ouvre Streamlit)
         python main_V6.py --sans-interface   (collecte seulement)

 Les résultats sont enregistrés dans :

         telechargements_v6\execution_AAAAMMJJ_HHMMSS\
             pre_traite.txt    réponses brutes
             traite.json       données traitées (schéma v3)


--------------------------------------------------------------------------------
 CONFIGURATION
--------------------------------------------------------------------------------
 Dans main_V6.py (section CONFIGURATION) :

     PLATEFORME, URL_PLATEFORME   plateforme ciblée (ChatGPT)
     LANGUE_INTERFACE             "fr-FR" (l'interface de ChatGPT doit être en
                                  français : les boutons sont repérés par leur
                                  texte)
     MARQUES_CIBLES               marques à compter, ex. ["HP", "Acer"]
     PROMPTS                      prompts envoyés à chaque exécution


--------------------------------------------------------------------------------
 DÉPANNAGE RAPIDE
--------------------------------------------------------------------------------
  - « No module named ... »  -> l'environnement virtuel n'est pas activé, ou
                                 pip install -r requirements.txt n'a pas été fait.
  - Erreur de navigateur      -> exécuter playwright install chromium.
  - Blocage sur ChatGPT       -> connexion, CAPTCHA ou changement d'interface :
                                 le navigateur est visible, vérifier l'écran.
  - Journal de la collecte    -> telechargements_v6\execution_actuelle.log

 Limites : les sélecteurs dépendent de l'interface de ChatGPT et peuvent
 nécessiter des ajustements ; l'automatisation d'interfaces web peut être
 restreinte par les conditions d'utilisation de la plateforme.
