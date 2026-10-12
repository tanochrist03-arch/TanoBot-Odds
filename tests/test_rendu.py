"""
TanoBot Odds — tests du rendu des messages.

Ces tests protègent trois choses qu'un bot peut casser sans qu'on s'en
aperçoive : le format français des nombres, l'échappement HTML (un caractère non
échappé fait échouer l'envoi Telegram), et le discours honnête quand il n'y a
rien à annoncer.
"""
from __future__ import annotations

import unittest

from bot import rendu


class TestFormatFrancais(unittest.TestCase):
    def test_milliers_avec_espace(self):
        self.assertEqual(rendu._nombre(1200), "1 200")
        self.assertEqual(rendu._nombre(1000000), "1 000 000")
        self.assertEqual(rendu._nombre(42), "42")

    def test_virgule_decimale(self):
        self.assertEqual(rendu._nombre(1.85, 2), "1,85")
        self.assertEqual(rendu._nombre(1234.5, 1), "1 234,5")

    def test_valeurs_inattendues(self):
        """Une valeur absente s'affiche « — », elle ne fait pas planter le bot."""
        for valeur in (None, "", "abc", [], {}):
            self.assertEqual(rendu._nombre(valeur), "—")

    def test_signe(self):
        self.assertEqual(rendu._signe(0.125 * 100, 1, " %"), "+12,5 %")
        self.assertEqual(rendu._signe(-0.03 * 100, 1, " %"), "−3,0 %")

    def test_pourcentage(self):
        self.assertEqual(rendu._pourcentage(0.62), "62,0 %")
        self.assertEqual(rendu._pourcentage(None), "—")


class TestEchappementHtml(unittest.TestCase):
    def test_caracteres_dangereux(self):
        self.assertEqual(rendu._echapper("<b>texte</b>"), "&lt;b&gt;texte&lt;/b&gt;")
        self.assertEqual(rendu._echapper("A & B"), "A &amp; B")

    def test_valeur_absente(self):
        self.assertEqual(rendu._echapper(None), "")

    def test_un_nom_d_equipe_ne_casse_pas_le_html(self):
        """Un nom comportant « & » ou « < » ne doit pas invalider le message."""
        rapport = {
            "ok": True,
            "compteurs": {},
            "value_bets": [{
                "match": "Young Boys & Co - FC <Test>", "equipe": "A & B",
                "cote": 1.9, "probabilite": 0.55, "ev": 0.07, "confiance": 60,
            }],
            "avertissements": [],
        }
        texte = rendu.value_bets(rapport, None, None)
        self.assertNotIn("<Test>", texte)
        self.assertIn("&lt;Test&gt;", texte)
        self.assertIn("&amp;", texte)


class TestDiscoursHonnete(unittest.TestCase):
    """Le bot ne doit ni promettre de gains, ni faire passer une absence
    d'opportunité pour une panne."""

    def test_zero_value_bet_est_explique_comme_normal(self):
        texte = rendu.value_bets({"ok": True, "value_bets": []}, None, None)
        self.assertIn("Aucune opportunité", texte)
        self.assertIn("pas une erreur", texte.lower())
        # Les trois raisons légitimes doivent être listées.
        self.assertIn("efficient", texte.lower())
        self.assertIn("données manquent", texte.lower())
        self.assertIn("seuils", texte.lower())

    def test_aucune_promesse_de_gain(self):
        rapport = {"ok": True, "compteurs": {}, "value_bets": [
            {"match": "A - B", "equipe": "A", "cote": 2.0, "probabilite": 0.6,
             "probabilite_marche": 0.5, "ecart": 0.1, "ev": 0.2, "confiance": 75,
             "mise": 1000}]}
        texte = rendu.value_bets(rapport, None, None).lower()
        for promesse in ("gain assuré", "gagné à coup sûr", "garanti", "certain",
                         "sans risque", "profit assuré"):
            self.assertNotIn(promesse, texte)
        self.assertIn("signal à vérifier", texte)

    def test_la_mise_unitaire_est_rappelée(self):
        rapport = {"ok": True, "compteurs": {}, "value_bets": [
            {"match": "A - B", "equipe": "A", "cote": 2.0, "probabilite": 0.6,
             "ev": 0.2, "confiance": 75}]}
        self.assertIn("1 à 2 %", rendu.value_bets(rapport, None, None))

    def test_echec_de_source_est_distingue_d_une_absence(self):
        texte = rendu.scan({"ok": False, "erreur": "Aucune réponse en 20 secondes."},
                           None)
        self.assertIn("Analyse impossible", texte)
        self.assertIn("Aucune réponse", texte)
        self.assertIn("n'est pas la même chose", texte)

    def test_scan_sans_opportunite_explique_le_silence(self):
        rapport = {"ok": True, "compteurs": {"matchs": 104, "matchs_cotes": 73},
                   "value_bets": [], "avertissements": []}
        texte = rendu.scan(rapport, None)
        self.assertIn("Aucune opportunité", texte)
        self.assertIn("résultat normal", texte)

    def test_les_limites_sont_affichees_avec_le_resultat(self):
        rapport = {"ok": True, "compteurs": {"matchs": 104}, "value_bets": [],
                   "avertissements": ["13 des 75 matchs n'ont pas de profil."]}
        texte = rendu.scan(rapport, None)
        self.assertIn("Limites", texte)
        self.assertIn("13 des 75", texte)


class TestDemarrage(unittest.TestCase):
    def test_le_formule_ev_est_presente(self):
        class Faux:
            seuil_ev = 0.05
            seuil_confiance = 45
            supabase_configure = False
        texte = rendu.demarrage(Faux())
        self.assertIn("EV = (probabilité estimée × cote) − 1", texte)

    def test_le_mode_de_stockage_est_annonce(self):
        class Faux:
            seuil_ev = 0.05
            seuil_confiance = 45

            def __init__(self, supabase):
                self.supabase_configure = supabase
        self.assertIn("Supabase", rendu.demarrage(Faux(True)))
        self.assertIn("SQLite", rendu.demarrage(Faux(False)))

    def test_l_avertissement_est_present(self):
        class Faux:
            seuil_ev = 0.05
            seuil_confiance = 45
            supabase_configure = False
        texte = rendu.demarrage(Faux()).lower()
        self.assertIn("promesse de gain", texte)


class TestStatistiques(unittest.TestCase):
    def test_bilan_vide(self):
        class Depot:
            def statistiques(self):
                return {"total_value_bets": 0, "par_statut": {}, "nb_scans": 1,
                        "ev_moyenne": None, "confiance_moyenne": None,
                        "dernier_scan": None, "depot": "SQLite local"}
        texte = rendu.stats(Depot(), None)
        self.assertIn("Bilan", texte)
        self.assertIn("0", texte)

    def test_taux_de_reussite_calcule_seulement_si_des_paris_regles(self):
        class Depot:
            def statistiques(self):
                return {"total_value_bets": 10, "nb_scans": 3,
                        "par_statut": {"gagne": 3, "perdu": 1, "detecte": 6},
                        "ev_moyenne": 0.07, "confiance_moyenne": 68.0,
                        "dernier_scan": None, "depot": "SQLite local"}
        texte = rendu.stats(Depot(), None)
        self.assertIn("75,0 %", texte)          # 3 gagnés sur 4 réglés
        self.assertIn("4 pari(s) réglé(s)", texte)

    def test_stockage_en_panne_est_signale(self):
        class Depot:
            def statistiques(self):
                raise RuntimeError("base verrouillée")
        texte = rendu.stats(Depot(), None)
        self.assertIn("indisponibles", texte)
        self.assertIn("base verrouillée", texte)


class TestSante(unittest.TestCase):
    def test_etat_complet(self):
        class Faux:
            supabase_configure = False
            jeton_configure = True
            administrateurs = [42]
            alertes_actives = False
            heure_scan = "07:00"

            def problemes(self):
                return []

        class Depot:
            def decrire(self):
                return "SQLite local"

        texte = rendu.sante(Faux(), Depot(),
                            {"ok": True, "chemin": "C:\\moteur",
                             "modules": {"math_models": True}})
        self.assertIn("État du système", texte)
        self.assertIn("SQLite local", texte)
        self.assertIn("1 identifiant", texte)

    def test_moteur_indisponible_est_visible(self):
        class Faux:
            supabase_configure = False
            jeton_configure = True
            administrateurs = [42]
            alertes_actives = False
            heure_scan = "07:00"

            def problemes(self):
                return []

        class Depot:
            def decrire(self):
                return "SQLite local"

        texte = rendu.sante(Faux(), Depot(),
                            {"ok": False, "chemin": "C:\\absent",
                             "erreur": "projet moteur introuvable", "modules": {}})
        self.assertIn("❌", texte)
        self.assertIn("introuvable", texte)

    def test_aucun_secret_dans_l_etat(self):
        class Faux:
            supabase_configure = True
            supabase_url = "https://projet.supabase.co"
            jeton_configure = True
            administrateurs = [42]
            alertes_actives = False
            heure_scan = "07:00"

            def problemes(self):
                return []

        class Depot:
            def decrire(self):
                return "Supabase"

        texte = rendu.sante(Faux(), Depot(),
                            {"ok": True, "chemin": "C:\\moteur", "modules": {}})
        self.assertNotIn("sb_secret", texte)
        self.assertNotIn("BOT_TOKEN", texte)


if __name__ == "__main__":
    unittest.main()
