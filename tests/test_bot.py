"""
TanoBot Odds — tests du pont vers le moteur et des protections du bot.

Le pont est la pièce critique : s'il charge le mauvais module, le bot affiche
des chiffres que plus personne ne peut expliquer. Ces tests vérifient que le
calcul vient bien du moteur vérifié, et non d'une copie.
"""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from bot import engine_bridge as pont

CHEMIN_MOTEUR = Path(r"C:\Users\HD\Desktop\TanoTech-Basket-Analytics")


@unittest.skipUnless(CHEMIN_MOTEUR.exists(), "moteur absent de cette machine")
class TestChargementDuMoteur(unittest.TestCase):
    def test_le_moteur_se_charge(self):
        etat = pont.initialiser(CHEMIN_MOTEUR)
        self.assertTrue(etat["ok"], etat["erreur"])
        self.assertEqual(etat["manquants"], [])

    def test_les_quatre_modules_sont_presents(self):
        etat = pont.initialiser(CHEMIN_MOTEUR)
        for etiquette in ("math_models", "analysis", "telegram_formatter",
                          "config_moteur"):
            self.assertIn(etiquette, etat["modules"], etiquette)

    def test_chemin_inexistant_est_explique(self):
        """Un mauvais chemin doit produire un message utile, pas une trace."""
        from bot import engine_bridge
        etat = engine_bridge._charger(Path(r"C:\un\dossier\qui\nexiste\pas"))
        self.assertFalse(etat["ok"])
        self.assertIn("introuvable", etat["erreur"])
        self.assertIn("TANOTECH_PATH", etat["erreur"])


@unittest.skipUnless(CHEMIN_MOTEUR.exists(), "moteur absent de cette machine")
class TestCalculsDelegues(unittest.TestCase):
    """Le bot ne réécrit aucune formule : il appelle celle du moteur."""

    def setUp(self) -> None:
        pont.initialiser(CHEMIN_MOTEUR)

    def test_ev_est_delegue_au_moteur(self):
        self.assertEqual(pont.expected_value.__module__, "engine.math_models")
        self.assertEqual(pont.analyser.__module__, "services.analysis")
        self.assertEqual(pont.formater_paris.__module__,
                         "services.telegram_formatter")

    def test_formule_ev_correcte(self):
        """EV = (probabilité × cote) − 1."""
        self.assertAlmostEqual(pont.ev_pourcentage(0.60, 1.80), 8.0, places=4)
        self.assertAlmostEqual(pont.ev_pourcentage(0.50, 2.00), 0.0, places=4)
        self.assertAlmostEqual(pont.ev_pourcentage(0.40, 2.00), -20.0, places=4)

    def test_ev_positive_seulement_au_dessus_de_la_cote_d_equilibre(self):
        """Le seuil exact : la cote qui annule l'espérance vaut 1/probabilité."""
        probabilite = 0.55
        cote_equilibre = 1 / probabilite
        self.assertAlmostEqual(pont.ev_pourcentage(probabilite, cote_equilibre),
                               0.0, places=6)
        self.assertGreater(pont.ev_pourcentage(probabilite, cote_equilibre * 1.1), 0)
        self.assertLess(pont.ev_pourcentage(probabilite, cote_equilibre * 0.9), 0)

    def test_marge_du_marche(self):
        """La marge des cotes affichées : c'est elle qui explique pourquoi la
        plupart des paris ont une espérance négative."""
        marge = pont.marge_marche({"domicile": 1.90, "exterieur": 1.90})
        self.assertIsNotNone(marge)
        self.assertGreater(marge, 0)           # 1/1.9 + 1/1.9 = 1.053 → 5,3 %

    def test_marge_indisponible_si_cotes_invalides(self):
        self.assertIsNone(pont.marge_marche({"domicile": 0, "exterieur": 0}))


class TestProtectionDesIdentifiants(unittest.IsolatedAsyncioTestCase):
    """Le bot ne doit servir que son propriétaire."""

    async def test_identifiant_autorise_accepte(self):
        from bot import handlers
        from bot.contexte import Contexte, installer

        class Faux:
            administrateurs = [42, 99]

        installer(Contexte(configuration=Faux()))

        class Evenement:
            class from_user:
                id = 42

        filtre = handlers.EstAutorise()
        self.assertTrue(await filtre(Evenement()))

    async def test_identifiant_inconnu_refuse(self):
        from bot import handlers
        from bot.contexte import Contexte, installer

        class Faux:
            administrateurs = [42, 99]

        installer(Contexte(configuration=Faux()))

        class Evenement:
            class from_user:
                id = 12345

        filtre = handlers.EstAutorise()
        self.assertFalse(await filtre(Evenement()))

    async def test_evenement_sans_utilisateur_refuse(self):
        from bot import handlers
        from bot.contexte import Contexte, installer

        class Faux:
            administrateurs = [42]

        installer(Contexte(configuration=Faux()))

        class Evenement:
            from_user = None

        filtre = handlers.EstAutorise()
        self.assertFalse(await filtre(Evenement()))

    async def test_aucun_administrateur_donc_personne(self):
        """Sans liste, le bot refuse tout le monde : c'est le comportement sûr."""
        from bot import handlers
        from bot.contexte import Contexte, installer

        class Faux:
            administrateurs = []

        installer(Contexte(configuration=Faux()))

        class Evenement:
            class from_user:
                id = 42

        filtre = handlers.EstAutorise()
        self.assertFalse(await filtre(Evenement()))


class TestAssemblageDuBot(unittest.TestCase):
    """Le routeur et le planificateur doivent se construire sans erreur."""

    def test_le_routeur_est_construit(self):
        from bot.handlers import routeur
        self.assertIsNotNone(routeur)
        self.assertGreater(len(routeur.message.handlers), 3)

    def test_les_commandes_attendues_existent(self):
        from bot import handlers
        self.assertTrue(hasattr(handlers, "commande_start"))
        self.assertTrue(hasattr(handlers, "commande_scan"))
        self.assertTrue(hasattr(handlers, "commande_matchs"))
        self.assertTrue(hasattr(handlers, "commande_valuebets"))
        self.assertTrue(hasattr(handlers, "commande_stats"))
        self.assertTrue(hasattr(handlers, "commande_sante"))

    def test_planificateur_desactive_par_defaut(self):
        from bot.alerts import construire_planificateur

        class Faux:
            alertes_actives = False
            administrateurs = [42]
            heure_scan = "07:00"
            fuseau = "Africa/Abidjan"

        self.assertIsNone(construire_planificateur(None, Faux()))

    def test_planificateur_construit_quand_active(self):
        from bot.alerts import construire_planificateur

        class Faux:
            alertes_actives = True
            administrateurs = [42]
            heure_scan = "06:30"
            fuseau = "Africa/Abidjan"

        planificateur = construire_planificateur(None, Faux())
        self.assertIsNotNone(planificateur)
        tache = planificateur.get_job("scan_quotidien")
        self.assertIsNotNone(tache)

    def test_heure_illisible_retombe_sur_le_defaut(self):
        from bot.alerts import construire_planificateur

        class Faux:
            alertes_actives = True
            administrateurs = [42]
            heure_scan = "pas-une-heure"
            fuseau = "Africa/Abidjan"

        planificateur = construire_planificateur(None, Faux())
        self.assertIsNotNone(planificateur)
        self.assertIsNotNone(planificateur.get_job("scan_quotidien"))


if __name__ == "__main__":
    unittest.main()
