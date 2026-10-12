"""Controle final avant publication : aucun secret ne doit partir.

Analyse les fichiers reellement indexes par git, et cherche des motifs de
secrets par NOM de variable (et non par valeur), pour ne jamais afficher une
eventuelle valeur trouvee.
"""
from __future__ import annotations

import pathlib
import re
import subprocess

RACINE = pathlib.Path(r"C:\Users\HD\Desktop\TanoBot-Odds")

# Motifs de VALEURS qui ne doivent jamais apparaitre dans un depot.
MOTIFS_VALEUR = {
    "jeton Telegram (chiffres:chaine)": re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b"),
    "cle prefixed sk-": re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    "cle Supabase service": re.compile(r"\bsb_secret_[A-Za-z0-9_-]{10,}\b"),
    "cle Google API": re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    "cle AWS": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
}

# Fichiers dont l'extension est binaire : on ne les lit pas en texte.
IGNORES = (".png", ".jpg", ".ico", ".pdf", ".db", ".sqlite3")

resultat = subprocess.run(["git", "-C", str(RACINE), "add", "-A"],
                          capture_output=True, text=True)
resultat = subprocess.run(["git", "-C", str(RACINE), "diff", "--cached",
                           "--name-only"], capture_output=True, text=True)
fichiers = [ligne.strip() for ligne in resultat.stdout.splitlines() if ligne.strip()]

print("=" * 74)
print("  CONTROLE AVANT PUBLICATION")
print("=" * 74)
print(f"\n  fichiers a publier : {len(fichiers)}")

# 1. Aucun fichier d'environnement ou de cle dans l'index
sensibles = [f for f in fichiers
             if pathlib.PurePosixPath(f).name == ".env"
             or f.endswith((".key", ".pem", ".p12", ".pfx"))]
print(f"  fichiers sensibles indexes : {len(sensibles)}  (0 attendu)")
for fichier in sensibles:
    print(f"    !! {fichier}")

# 2. Aucune valeur de secret dans le contenu indexe
print("\n  recherche de valeurs secretes :")
total = 0
for nom_fichier in fichiers:
    chemin = RACINE / nom_fichier
    if not chemin.exists() or chemin.suffix.lower() in IGNORES:
        continue
    try:
        contenu = chemin.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    for etiquette, motif in MOTIFS_VALEUR.items():
        for correspondance in motif.finditer(contenu):
            total += 1
            # On affiche la POSITION, jamais la valeur elle-meme.
            ligne = contenu[:correspondance.start()].count("\n") + 1
            print(f"    !! {etiquette} dans {nom_fichier} ligne {ligne}"
                  f"  (valeur masquee, {len(correspondance.group(0))} caracteres)")
if total == 0:
    print("    OK — aucun motif de valeur secrete detecte")

# 3. Les variables sensibles existent-elles uniquement a vide ?
print("\n  variables sensibles dans .env.example :")
exemple = RACINE / ".env.example"
if exemple.exists():
    for ligne in exemple.read_text(encoding="utf-8", errors="ignore").splitlines():
        ligne = ligne.strip()
        if ligne.startswith(("BOT_TOKEN=", "BOT_ADMIN_IDS=", "SUPABASE_URL=",
                             "SUPABASE_SERVICE_KEY=")):
            nom, _, valeur = ligne.partition("=")
            etat = "vide (correct)" if not valeur.strip() else "REMPLI"
            print(f"    {nom:<24} {etat}")

# 4. Le fichier .env est-il bien ignore ?
resultat = subprocess.run(["git", "-C", str(RACINE), "check-ignore", "-v", ".env"],
                          capture_output=True, text=True)
print(f"\n  .env ignore par git : "
      f"{'OUI — ' + resultat.stdout.strip() if resultat.returncode == 0 else 'NON'}")

print("\n" + "=" * 74)
print("  VERDICT :", "AUCUN SECRET NE PEUT PARTIR" if not sensibles and not total
      else "CORRIGER AVANT DE PUBLIER")
print("=" * 74)
