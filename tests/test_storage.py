"""
TanoBot Odds — tests du stockage.

Vérifient l'unicité des paris (un value bet redétecté ne doit pas être compté
deux fois), la traduction des noms de champs du moteur, et les statistiques.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from storage import SqliteDepot, empreinte_pari, normaliser_pari


def pari(match: str = "Lakers - Celtics", equipe: str = "Lakers",
         cote: float = 1.85, ev: float = 0.08, confiance: int = 72) -> dict:
    """Un pari au format du moteur (mêmes noms de champs)."""
    return {
        "match": match, "equipe": equipe, "ligue": "NBA", "issue": "domicile",
        "cote": cote, "probabilite": 0.62, "probabilite_marche": 0.54,
        "ecart": 0.08, "ev": ev, "confiance": confiance, "mise": 2000.0,
        "devise": "FCFA", "debut_utc": "2026-10-13T01:00:00Z",
    }


def rapport(ok: bool = True, paris: list | None = None) -> dict:
    return {
        "ok": ok,
        "source": "betexplorer",
        "depuis_cache": False,
        "horodatage": "2026-10-12T15:00:00+00:00",
        "compteurs": {"matchs": 104, "matchs_cotes": 73, "matchs_evalues": 41},
        "pronostics": [{}] * 73,
        "value_bets": paris or [],
        "avertissements": [],
        "erreur": "",
    }


class BaseDepot(unittest.TestCase):
    def setUp(self) -> None:
        self.dossier = tempfile.TemporaryDirectory()
        self.depot = SqliteDepot(Path(self.dossier.name) / "test.db")

    def tearDown(self) -> None:
        self.depot.fermer()
        self.dossier.cleanup()


class TestTraductionDesChamps(unittest.TestCase):
    """Le moteur et la base n'utilisent pas les mêmes noms : la traduction
    centralisée doit couvrir les deux."""

    def test_les_noms_du_moteur_sont_traduits(self):
        normalise = normaliser_pari(pari())
        self.assertEqual(normalise["match_libelle"], "Lakers - Celtics")
        self.assertEqual(normalise["competition"], "NBA")         # ligue → competition
        self.assertEqual(normalise["marche"], "domicile")         # issue → marche
        self.assertEqual(normalise["ecart_points"], 0.08)         # ecart → ecart_points
        self.assertEqual(normalise["probabilite_modele"], 0.62)
        self.assertEqual(normalise["mise_recommandee"], 2000.0)

    def test_les_noms_de_la_base_sont_acceptes_aussi(self):
        """Accepter les deux formes évite une colonne vide silencieuse."""
        normalise = normaliser_pari({
            "match_libelle": "A - B", "competition": "Ligue", "marche": "exterieur",
            "cote": 2.1, "probabilite_modele": 0.5, "ecart_points": 0.03, "ev": 0.05,
        })
        self.assertEqual(normalise["match_libelle"], "A - B")
        self.assertEqual(normalise["competition"], "Ligue")
        self.assertEqual(normalise["ecart_points"], 0.03)

    def test_un_pari_incomplet_ne_plante_pas(self):
        normalise = normaliser_pari({})
        self.assertEqual(normalise["match_libelle"], "")
        self.assertEqual(normalise["cote"], 0.0)
        self.assertEqual(normalise["marche"], "vainqueur")


class TestEmpreinte(unittest.TestCase):
    """L'empreinte empêche le doublon sans dépendre de la cote."""

    def test_meme_pari_meme_empreinte(self):
        self.assertEqual(empreinte_pari(pari()), empreinte_pari(pari()))

    def test_la_cote_ne_change_pas_l_empreinte(self):
        """Un pari redétecté le lendemain à une autre cote reste le même pari."""
        self.assertEqual(empreinte_pari(pari(cote=1.85)),
                         empreinte_pari(pari(cote=1.95)))

    def test_l_ev_ne_change_pas_l_empreinte(self):
        self.assertEqual(empreinte_pari(pari(ev=0.08)),
                         empreinte_pari(pari(ev=0.25)))

    def test_equipe_differente_change_l_empreinte(self):
        self.assertNotEqual(empreinte_pari(pari(equipe="Lakers")),
                            empreinte_pari(pari(equipe="Celtics")))

    def test_match_different_change_l_empreinte(self):
        self.assertNotEqual(empreinte_pari(pari(match="A - B")),
                            empreinte_pari(pari(match="C - D")))

    def test_la_casse_et_les_espaces_ne_comptent_pas(self):
        self.assertEqual(empreinte_pari(pari(match="Lakers - Celtics")),
                         empreinte_pari(pari(match="  lakers - celtics  ")))


class TestEcritureEtUnicite(BaseDepot):
    def test_scan_enregistre(self):
        identifiant = self.depot.enregistrer_scan(
            rapport(), seuil_ev=0.05, seuil_confiance=45)
        self.assertGreater(identifiant, 0)
        chiffres = self.depot.statistiques()
        self.assertEqual(chiffres["nb_scans"], 1)

    def test_scan_en_erreur_reste_enregistre(self):
        """Un échec de source est une information, pas un déchet."""
        identifiant = self.depot.enregistrer_scan(
            rapport(ok=False), seuil_ev=0.05, seuil_confiance=45)
        self.assertGreater(identifiant, 0)
        self.assertEqual(self.depot.statistiques()["nb_scans"], 1)

    def test_ecriture_des_paris(self):
        identifiant = self.depot.enregistrer_scan(
            rapport(), seuil_ev=0.05, seuil_confiance=45)
        ecrits = self.depot.enregistrer_value_bets([pari()], identifiant)
        self.assertEqual(ecrits, 1)
        self.assertEqual(self.depot.statistiques()["total_value_bets"], 1)

    def test_reecriture_ne_cree_pas_de_doublon(self):
        """Le point clé : un scan qui repasse sur les mêmes paris ne les
        compte pas deux fois."""
        identifiant = self.depot.enregistrer_scan(
            rapport(), seuil_ev=0.05, seuil_confiance=45)
        self.assertEqual(self.depot.enregistrer_value_bets([pari()], identifiant), 1)
        self.assertEqual(self.depot.enregistrer_value_bets([pari()], identifiant), 0)
        self.assertEqual(self.depot.statistiques()["total_value_bets"], 1)

    def test_lot_partiel_ecrit_ce_qui_est_nouveau(self):
        identifiant = self.depot.enregistrer_scan(
            rapport(), seuil_ev=0.05, seuil_confiance=45)
        self.depot.enregistrer_value_bets([pari()], identifiant)
        nouveaux = [pari(), pari(match="A - B", equipe="A"),
                    pari(match="C - D", equipe="C")]
        self.assertEqual(self.depot.enregistrer_value_bets(nouveaux, identifiant), 2)

    def test_statut_par_defaut(self):
        identifiant = self.depot.enregistrer_scan(
            rapport(), seuil_ev=0.05, seuil_confiance=45)
        self.depot.enregistrer_value_bets([pari()], identifiant)
        recents = self.depot.value_bets_recents(1)
        self.assertEqual(recents[0]["statut"], "detecte")


class TestStatistiques(BaseDepot):
    def test_depot_vide(self):
        chiffres = self.depot.statistiques()
        self.assertEqual(chiffres["total_value_bets"], 0)
        self.assertEqual(chiffres["par_statut"], {})
        self.assertIsNone(chiffres["ev_moyenne"])
        self.assertIsNone(chiffres["dernier_scan"])

    def test_statistiques_apres_ecriture(self):
        identifiant = self.depot.enregistrer_scan(
            rapport(), seuil_ev=0.05, seuil_confiance=45)
        self.depot.enregistrer_value_bets(
            [pari(ev=0.10, confiance=80), pari(match="A - B", equipe="A",
                                               ev=0.06, confiance=60)],
            identifiant)
        chiffres = self.depot.statistiques()
        self.assertEqual(chiffres["total_value_bets"], 2)
        self.assertAlmostEqual(chiffres["ev_moyenne"], 0.08, places=4)
        self.assertAlmostEqual(chiffres["confiance_moyenne"], 70.0, places=1)
        self.assertIsNotNone(chiffres["dernier_scan"])

    def test_le_dernier_scan_indique_les_compteurs(self):
        self.depot.enregistrer_scan(rapport(paris=[pari()]),
                                    seuil_ev=0.05, seuil_confiance=45)
        dernier = self.depot.statistiques()["dernier_scan"]
        self.assertEqual(dernier["nb_pronostics"], 73)
        self.assertEqual(dernier["nb_value_bets"], 1)


class TestDescription(BaseDepot):
    def test_le_depot_sait_se_nommer(self):
        """Le mode de stockage doit être affichable sans ambiguïté."""
        self.assertIn("SQLite", self.depot.decrire())


if __name__ == "__main__":
    unittest.main()
