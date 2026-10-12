"""
TanoBot Odds — tests de la configuration et de la protection des secrets.

Un bot Telegram est une surface publique : ces tests vérifient que rien de
sensible ne peut être affiché par erreur.
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

from bot import config as config_bot


class TestLectureDeLaConfiguration(unittest.TestCase):
    def test_valeurs_par_defaut(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            configuration = config_bot.charger()
        self.assertEqual(configuration.seuil_ev, 0.05)
        self.assertEqual(configuration.seuil_confiance, 45)
        self.assertEqual(configuration.heure_scan, "07:00")
        self.assertFalse(configuration.alertes_actives)
        self.assertFalse(configuration.supabase_configure)
        self.assertFalse(configuration.jeton_configure)

    def test_lecture_des_identifiants_autorises(self):
        with mock.patch.dict(os.environ, {"BOT_ADMIN_IDS": "123, 456 ,789"}, clear=True):
            configuration = config_bot.charger()
        self.assertEqual(configuration.administrateurs, [123, 456, 789])

    def test_identifiants_invalides_ignores(self):
        """Une saisie approximative ne doit pas empêcher le démarrage."""
        with mock.patch.dict(os.environ,
                             {"BOT_ADMIN_IDS": "123,abc,, 456;789, "}, clear=True):
            configuration = config_bot.charger()
        self.assertEqual(configuration.administrateurs, [123, 456, 789])

    def test_valeurs_numeriques_illisibles(self):
        """Une valeur mal saisie retombe sur le défaut plutôt que de planter."""
        with mock.patch.dict(os.environ,
                             {"SEUIL_CONFIANCE": "quarante", "MAX_PARIS_ALERTE": ""},
                             clear=True):
            configuration = config_bot.charger()
        self.assertEqual(configuration.seuil_confiance, 45)
        self.assertEqual(configuration.max_paris_alerte, 5)

    def test_supabase_configure_seulement_si_les_deux_valeurs(self):
        with mock.patch.dict(os.environ, {"SUPABASE_URL": "https://x.supabase.co"},
                             clear=True):
            self.assertFalse(config_bot.charger().supabase_configure)
        with mock.patch.dict(os.environ,
                             {"SUPABASE_URL": "https://x.supabase.co",
                              "SUPABASE_SERVICE_KEY": "cle"}, clear=True):
            self.assertTrue(config_bot.charger().supabase_configure)

    def test_variantes_de_booleen(self):
        for valeur in ("1", "true", "vrai", "oui", "yes", "on", "TRUE"):
            with mock.patch.dict(os.environ, {"ALERTES_ACTIVES": valeur}, clear=True):
                self.assertTrue(config_bot.charger().alertes_actives, valeur)
        for valeur in ("0", "false", "non", ""):
            with mock.patch.dict(os.environ, {"ALERTES_ACTIVES": valeur}, clear=True):
                self.assertFalse(config_bot.charger().alertes_actives, valeur)

    def test_chemin_moteur_personnalise(self):
        with mock.patch.dict(os.environ, {"TANOTECH_PATH": r"C:\ailleurs\moteur"},
                             clear=True):
            configuration = config_bot.charger()
        self.assertEqual(str(configuration.chemin_moteur), r"C:\ailleurs\moteur")


class TestProtectionDesSecrets(unittest.TestCase):
    """Le résumé affichable ne doit jamais contenir de valeur secrète."""

    def test_le_jeton_n_apparait_jamais_en_clair(self):
        jeton = "7654321:AAH-secret-tres-long-a-ne-jamais-montrer"
        with mock.patch.dict(os.environ, {"BOT_TOKEN": jeton}, clear=True):
            configuration = config_bot.charger()
        resume = configuration.resume_securise()
        texte = str(resume)
        self.assertNotIn(jeton, texte)
        self.assertNotIn("AAH-secret", texte)
        # On veut seulement savoir qu'il est présent, et sa forme.
        self.assertIn("7654…", resume["jeton"])
        self.assertIn("caractères", resume["jeton"])

    def test_la_cle_supabase_n_apparait_jamais(self):
        # Valeur manifestement fictive : rien qui ressemble au format d'une
        # vraie clé, pour qu'aucun scan automatique ne la signale à tort.
        cle = "valeur-de-test-jamais-utilisee-nulle-part"
        with mock.patch.dict(os.environ,
                             {"SUPABASE_URL": "https://projet.supabase.co",
                              "SUPABASE_SERVICE_KEY": cle}, clear=True):
            configuration = config_bot.charger()
        texte = str(configuration.resume_securise())
        self.assertNotIn(cle, texte)
        self.assertNotIn("jamais-utilisee", texte)

    def test_l_url_supabase_est_publique_et_peut_apparaitre(self):
        """L'URL n'est pas un secret : elle sert au diagnostic."""
        with mock.patch.dict(os.environ,
                             {"SUPABASE_URL": "https://projet.supabase.co",
                              "SUPABASE_SERVICE_KEY": "x"}, clear=True):
            configuration = config_bot.charger()
        self.assertIn("projet.supabase.co", str(configuration.resume_securise()))


class TestDiagnostic(unittest.TestCase):
    def test_problemes_signale_le_jeton_manquant(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            problemes = config_bot.charger().problemes()
        textes = " ".join(problemes)
        self.assertIn("BOT_TOKEN", textes)
        # Le message doit dire QUOI FAIRE, pas seulement ce qui manque.
        self.assertIn("BotFather", textes)

    def test_problemes_signale_le_manque_de_verrouillage(self):
        with mock.patch.dict(os.environ, {"BOT_TOKEN": "123:abc"}, clear=True):
            problemes = config_bot.charger().problemes()
        textes = " ".join(problemes)
        self.assertIn("BOT_ADMIN_IDS", textes)
        self.assertIn("refuserait", textes)

    def test_aucun_probleme_quand_tout_est_là(self):
        environnement = {"BOT_TOKEN": "123:abc", "BOT_ADMIN_IDS": "42"}
        with mock.patch.dict(os.environ, environnement, clear=True):
            configuration = config_bot.charger()
        # Le moteur par défaut existe sur cette machine : seul son absence
        # produirait un problème ici.
        if configuration.chemin_moteur.exists():
            self.assertEqual(configuration.problemes(), [])


if __name__ == "__main__":
    unittest.main()
