"""
TanoBot Odds — rendu des messages Telegram.

Tout passe par ici : un seul endroit décide de la mise en forme, donc un seul
endroit à corriger si un chiffre s'affiche mal.

Règles de rédaction tenues partout :

- **Nombres au format français** (espace pour les milliers, virgule décimale).
- **Aucune promesse de gain.** Un écart d'EV élevé est un signal à vérifier,
  pas une certitude — et le message le dit.
- **Zéro value bet est une réponse normale**, pas une panne : quand le modèle
  n'a pas de données suffisantes, il s'aligne sur le marché et se tait. Le dire
  évite de croire à un bug.
- **Les limites sont affichées avec les résultats**, pas cachées.
"""
from __future__ import annotations

from typing import Any

from . import engine_bridge as pont

# Telegram accepte un sous-ensemble de HTML : on n'utilise que celui-là.
def _echapper(texte: Any) -> str:
    return (str(texte or "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _nombre(valeur: Any, decimales: int = 0) -> str:
    """Format français : espace pour les milliers, virgule décimale."""
    try:
        nombre = float(valeur)
    except (TypeError, ValueError):
        return "—"
    if decimales == 0:
        entier = int(round(nombre))
        return f"{entier:,}".replace(",", " ")
    texte = f"{nombre:,.{decimales}f}"
    return texte.replace(",", " ").replace(".", ",")


def _signe(valeur: Any, decimales: int = 0, suffixe: str = "") -> str:
    try:
        nombre = float(valeur)
    except (TypeError, ValueError):
        return "—"
    return f"{'+' if nombre >= 0 else '−'}{_nombre(abs(nombre), decimales)}{suffixe}"


def _pourcentage(valeur: Any, decimales: int = 1) -> str:
    try:
        return f"{_nombre(float(valeur) * 100, decimales)} %"
    except (TypeError, ValueError):
        return "—"


# --------------------------------------------------------------------------- #
# Messages fixes
# --------------------------------------------------------------------------- #
def demarrage(configuration) -> str:
    depot = "Supabase" if configuration.supabase_configure else "base locale (SQLite)"
    return (
        "<b>🎯 TanoBot Odds</b>\n"
        "<i>Détection de value bets et analyse statistique</i>\n\n"
        "Je collecte les cotes de basket, j'estime une probabilité, et je "
        "calcule l'espérance :\n\n"
        "<code>EV = (probabilité estimée × cote) − 1</code>\n\n"
        "Un value bet n'existe que si l'espérance est <b>positive</b> après "
        "marge du bookmaker.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>Commandes</b>\n"
        "/scan — lancer une analyse maintenant\n"
        "/matches — les matchs à venir et leurs cotes\n"
        "/valuebets — les opportunités détectées\n"
        "/stats — historique et bilan\n"
        "/sante — vérifier que tout fonctionne\n"
        "/aide — cette liste\n\n"
        f"<b>Stockage :</b> {depot}\n"
        f"<b>Seuil d'EV :</b> {_pourcentage(configuration.seuil_ev)} · "
        f"<b>Confiance minimale :</b> {configuration.seuil_confiance}/100\n\n"
        "⚠️ <i>Outil d'analyse, pas une promesse de gain. Les cotes "
        "contiennent la marge du bookmaker ; un écart détecté reste un signal "
        "à vérifier.</i>"
    )


def aide() -> str:
    return (
        "<b>Commandes disponibles</b>\n\n"
        "<b>/scan</b> — collecte les cotes et relance le moteur.\n"
        "<b>/matches</b> — les prochaines rencontres, avec cotes et "
        "probabilité du marché.\n"
        "<b>/valuebets</b> — uniquement les paris à espérance positive, "
        "avec leur mise recommandée.\n"
        "<b>/stats</b> — combien d'analyses, combien d'opportunités, "
        "quelle réussite réelle.\n"
        "<b>/sante</b> — état du moteur, du stockage et de la source.\n\n"
        "<i>Le bot est réservé à son propriétaire : les autres identifiants "
        "sont refusés.</i>"
    )


# --------------------------------------------------------------------------- #
# Analyse
# --------------------------------------------------------------------------- #
def scan(rapport: dict, configuration) -> str:
    """Résumé d'une analyse : ce qui a été lu, et ce qui en sort."""
    if not rapport.get("ok"):
        return (
            "<b>⚠️ Analyse impossible</b>\n\n"
            f"{_echapper(rapport.get('erreur') or 'raison inconnue')}\n\n"
            "<i>La source de cotes peut limiter temporairement les requêtes. "
            "Réessaie dans quelques minutes : une réponse vide n'est pas la "
            "même chose qu'une absence d'opportunité.</i>"
        )

    compteurs = rapport.get("compteurs") or {}
    lignes = ["<b>📊 Analyse terminée</b>", ""]

    paires = (
        ("Matchs lus", "matchs"),
        ("Matchs cotés", "matchs_cotes"),
        ("Résultats d'historique", "resultats"),
        ("Profils d'équipes", "equipes_profiles"),
        ("Compétitions reconnues", "ligues_reconnues"),
        ("Matchs évaluables", "matchs_evaluables"),
    )
    for libelle, cle in paires:
        if compteurs.get(cle) is not None:
            lignes.append(f"• {libelle} : <b>{_nombre(compteurs[cle])}</b>")

    value_bets = rapport.get("value_bets") or []
    lignes.append("")
    if value_bets:
        lignes.append(f"<b>🎯 {len(value_bets)} opportunité(s) détectée(s)</b>")
        lignes.append("Utilise /valuebets pour le détail.")
    else:
        lignes.append("<b>Aucune opportunité détectée.</b>")
        lignes.append(
            "<i>C'est un résultat normal : quand un match manque de données, "
            "le modèle s'aligne sur le marché et ne déclare aucune valeur "
            "plutôt que d'inventer un écart.</i>"
        )

    ecrits = rapport.get("_value_bets_ecrits")
    if ecrits is not None:
        lignes.append("")
        lignes.append(f"<i>{_nombre(ecrits)} nouveau(x) pari(s) enregistré(s).</i>")

    avertissements = rapport.get("avertissements") or []
    if avertissements:
        lignes.append("")
        lignes.append("<b>Limites de cette analyse</b>")
        for avertissement in avertissements[:3]:
            lignes.append(f"<i>· {_echapper(avertissement)}</i>")

    return "\n".join(lignes)


def matchs(rapport: dict, limite: int = 8) -> str:
    """Liste des matchs à venir, avec la probabilité implicite du marché."""
    if not rapport or not rapport.get("ok"):
        return ("<i>Aucune analyse récente. Lance /scan pour en produire une.</i>")

    pronostics = rapport.get("pronostics") or []
    if not pronostics:
        return ("<i>Aucun match coté n'a été trouvé lors de la dernière "
                "analyse.</i>")

    lignes = [f"<b>🏀 Matchs à venir</b> — {_nombre(len(pronostics))} au total", ""]
    affiches = 0
    for pronostic in pronostics[:limite]:
        try:
            donnees = pronostic.en_dictionnaire() if hasattr(pronostic, "en_dictionnaire") \
                else pronostic
            match = donnees["match"]
            marche = donnees["marche"]
            probabilites = donnees["probabilites"]
            lignes.append(
                f"<b>{_echapper(match['domicile'])} — {_echapper(match['exterieur'])}</b>"
            )
            ligue = (donnees.get("ligue") or {}).get("nom")
            if ligue:
                lignes.append(f"  <i>{_echapper(ligue)}</i>")
            debut = match.get("debut_utc") or match.get("debut")
            if debut:
                lignes.append(f"  🕐 {_echapper(str(debut)[:16].replace('T', ' '))} UTC")
            cotes = []
            if marche.get("cote_domicile"):
                cotes.append(f"1 : <b>{_nombre(marche['cote_domicile'], 2)}</b>")
            if marche.get("cote_exterieur"):
                cotes.append(f"2 : <b>{_nombre(marche['cote_exterieur'], 2)}</b>")
            if cotes:
                lignes.append("  Cotes " + " · ".join(cotes))
            if probabilites.get("marche_domicile") is not None:
                lignes.append(
                    f"  Marché : {_pourcentage(probabilites['marche_domicile'])} "
                    f"domicile · {_pourcentage(probabilites['marche_exterieur'])} "
                    f"extérieur"
                )
            lignes.append("")
            affiches += 1
        except Exception:
            continue

    if affiches == 0:
        return "<i>Les matchs de la dernière analyse n'ont pas pu être affichés.</i>"

    if len(pronostics) > limite:
        lignes.append(f"<i>… et {_nombre(len(pronostics) - limite)} autre(s).</i>")
    lignes.append("<i>Horaires en UTC. Les cotes comportent la marge du "
                  "bookmaker.</i>")
    return "\n".join(lignes)


def value_bets(rapport: dict, recents: list[dict] | None = None,
               configuration=None, limite: int = 5) -> str:
    """Les opportunités détectées, ou un constat honnête s'il n'y en a pas."""
    paris = list(rapport.get("value_bets") or []) if rapport else []
    if not paris and recents:
        # Repli sur l'historique : le bot redémarre souvent, et voir les
        # dernières détections vaut mieux qu'un message vide.
        paris = [{
            "match": ligne.get("match_libelle"),
            "equipe": ligne.get("equipe"),
            "cote": ligne.get("cote"),
            "probabilite": ligne.get("probabilite_modele"),
            "probabilite_marche": ligne.get("probabilite_marche"),
            "ecart": ligne.get("ecart_points"),
            "ev": ligne.get("ev"),
            "confiance": ligne.get("confiance"),
            "ligue": ligne.get("competition"),
            "mise": ligne.get("mise_recommandee"),
            "_historique": True,
        } for ligne in recents]

    if not paris:
        return (
            "<b>🎯 Aucune opportunité pour le moment</b>\n\n"
            "Ce n'est pas une erreur. Trois raisons possibles :\n\n"
            "• <b>Le marché est efficient</b> — les cotes reflètent "
            "correctement les probabilités, il n'y a rien à prendre.\n"
            "• <b>Les données manquent</b> — sans suffisamment de matchs "
            "d'historique, le modèle refuse de déclarer un écart.\n"
            "• <b>Les seuils sont stricts</b> — et c'est voulu : un moteur "
            "permissif annonce des dizaines de fausses trouvailles.\n\n"
            "<i>Lance /scan pour rafraîchir l'analyse.</i>"
        )

    lignes = [f"<b>🎯 {len(paris)} opportunité(s)</b>", ""]
    for position, pari in enumerate(paris[:limite], start=1):
        lignes.append(f"<b>{position}. {_echapper(pari.get('match'))}</b>")
        if pari.get("ligue"):
            lignes.append(f"  <i>{_echapper(pari['ligue'])}</i>")
        lignes.append(f"  Pari : <b>{_echapper(pari.get('equipe'))}</b> "
                      f"à <b>{_nombre(pari.get('cote'), 2)}</b>")
        if pari.get("probabilite") is not None:
            lignes.append(
                f"  Modèle : {_pourcentage(pari['probabilite'])} · "
                f"Marché : {_pourcentage(pari.get('probabilite_marche'))}"
            )
        if pari.get("ecart") is not None:
            ecart = float(pari["ecart"])
            lignes.append(f"  Écart : <b>{_signe(ecart * 100, 1, ' pts')}</b>")
        if pari.get("ev") is not None:
            lignes.append(f"  Espérance : <b>{_signe(pari['ev'] * 100, 1, ' %')}</b>")
        if pari.get("confiance") is not None:
            lignes.append(f"  Confiance : {_nombre(pari['confiance'])}/100")
        if pari.get("mise"):
            lignes.append(f"  Mise conseillée : {_nombre(pari['mise'], 0)} FCFA")
        lignes.append("")

    if len(paris) > limite:
        lignes.append(f"<i>… et {_nombre(len(paris) - limite)} autre(s).</i>")
    lignes.append(
        "<i>Un écart élevé est un signal à vérifier, pas une certitude. "
        "Mise unitaire : 1 à 2 % du capital.</i>"
    )
    return "\n".join(lignes)


def stats(depot, configuration) -> str:
    """Bilan : combien d'analyses, combien d'opportunités, quel résultat réel."""
    try:
        chiffres = depot.statistiques()
    except Exception as exc:
        return (f"<b>Statistiques indisponibles</b>\n\n"
                f"<i>{_echapper(type(exc).__name__)}: {_echapper(exc)}</i>")

    lignes = ["<b>📈 Bilan</b>", ""]
    lignes.append(f"• Analyses lancées : <b>{_nombre(chiffres.get('nb_scans'))}</b>")
    lignes.append(f"• Opportunités détectées : "
                  f"<b>{_nombre(chiffres.get('total_value_bets'))}</b>")

    par_statut = chiffres.get("par_statut") or {}
    if par_statut:
        lignes.append("")
        lignes.append("<b>Par état</b>")
        libelles = {
            "detecte": "détectés (pas encore joués)",
            "joue": "joués (en attente du résultat)",
            "gagne": "gagnés",
            "perdu": "perdus",
            "annule": "annulés",
            "ignore": "ignorés",
        }
        for statut, nombre in sorted(par_statut.items()):
            lignes.append(f"• {libelles.get(statut, statut)} : {_nombre(nombre)}")

        joues = par_statut.get("gagne", 0) + par_statut.get("perdu", 0)
        if joues:
            reussite = par_statut.get("gagne", 0) / joues
            lignes.append("")
            lignes.append(f"<b>Réussite réelle : {_pourcentage(reussite)}</b> "
                          f"sur {_nombre(joues)} pari(s) réglé(s)")

    if chiffres.get("ev_moyenne") is not None:
        lignes.append("")
        lignes.append(f"• Espérance moyenne annoncée : "
                      f"<b>{_signe(chiffres['ev_moyenne'] * 100, 1, ' %')}</b>")
    if chiffres.get("confiance_moyenne") is not None:
        lignes.append(f"• Confiance moyenne : "
                      f"<b>{_nombre(chiffres['confiance_moyenne'], 0)}/100</b>")

    dernier = chiffres.get("dernier_scan")
    if dernier:
        lignes.append("")
        lignes.append(f"<i>Dernière analyse : {_echapper(str(dernier.get('horodatage'))[:19])}"
                      f" — {_nombre(dernier.get('nb_pronostics'))} pronostic(s), "
                      f"{_nombre(dernier.get('nb_value_bets'))} opportunité(s).</i>")

    lignes.append("")
    lignes.append(f"<i>Stockage : {_echapper(chiffres.get('depot'))}. "
                  "Les paris ne sont réglés qu'à la main (statut), car le bot "
                  "ne connaît pas le résultat des rencontres.</i>")
    return "\n".join(lignes)


def sante(configuration, depot, etat_moteur: dict) -> str:
    """Diagnostic : ce qui fonctionne et ce qui manque, sans révéler de secret."""
    lignes = ["<b>🩺 État du système</b>", ""]

    moteur = "✅" if etat_moteur.get("ok") else "❌"
    lignes.append(f"{moteur} <b>Moteur d'analyse</b>")
    lignes.append(f"  <i>{_echapper(etat_moteur.get('chemin'))}</i>")
    if not etat_moteur.get("ok"):
        lignes.append(f"  <i>{_echapper(etat_moteur.get('erreur'))}</i>")
    else:
        lignes.append(f"  <i>modules : {', '.join(etat_moteur.get('modules', {}))}</i>")

    lignes.append("")
    lignes.append(f"✅ <b>Stockage</b> : {_echapper(depot.decrire())}")
    if not configuration.supabase_configure:
        lignes.append("  <i>Supabase non configuré — les données sont locales. "
                      "Ajoute SUPABASE_URL et la clé dans .env pour les "
                      "conserver en ligne.</i>")

    lignes.append("")
    lignes.append(f"{'✅' if configuration.jeton_configure else '❌'} <b>Jeton Telegram</b>")
    lignes.append(f"{'✅' if configuration.administrateurs else '❌'} "
                  f"<b>Verrouillage</b> — {len(configuration.administrateurs)} "
                  f"identifiant(s) autorisé(s)")

    lignes.append("")
    lignes.append(f"<b>Alertes automatiques :</b> "
                  f"{'activées à ' + configuration.heure_scan if configuration.alertes_actives else 'désactivées'}")

    problemes = configuration.problemes()
    if problemes:
        lignes.append("")
        lignes.append("<b>À corriger</b>")
        for probleme in problemes:
            lignes.append(f"<i>· {_echapper(probleme)}</i>")

    return "\n".join(lignes)


def apercu(texte: str) -> str:
    """Version texte brut d'un message HTML, pour les journaux."""
    try:
        return pont.apercu_texte_html(texte) if hasattr(pont, "apercu_texte_html") else texte
    except Exception:
        return texte
