"""
TanoBot Odds — stockage local (SQLite).

Utilisé quand Supabase n'est pas configuré, et comme repli si le service est
momentanément injoignable. Le schéma reprend les mêmes colonnes que la base
distante : passer de l'un à l'autre ne change rien au code du bot.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .base import Depot, normaliser_pari

RACINE = Path(__file__).resolve().parent.parent
CHEMIN_DEFAUT = RACINE / "data" / "tanobot.db"

SCHEMA = """
create table if not exists scan (
    id                integer primary key autoincrement,
    horodatage        text    not null,
    source            text    not null default '',
    depuis_cache      integer not null default 0,
    seuil_ev          real    not null default 0.05,
    seuil_confiance   integer not null default 45,
    matchs_observes   integer not null default 0,
    matchs_evalues    integer not null default 0,
    nb_pronostics     integer not null default 0,
    nb_value_bets     integer not null default 0,
    avertissements    text    not null default '[]',
    erreur            text
);

create table if not exists value_bet (
    id                 integer primary key autoincrement,
    scan_id            integer references scan(id) on delete set null,
    horodatage         text    not null,
    competition        text    not null default '',
    match_libelle      text    not null,
    equipe             text    not null default '',
    marche             text    not null default 'vainqueur',
    cote               real    not null,
    probabilite_modele real    not null,
    probabilite_marche real,
    ecart_points       real,
    ev                 real    not null,
    confiance          integer,
    mise_recommandee   real,
    mise_unites        real,
    statut             text    not null default 'detecte',
    gain_reel          real,
    note               text,
    empreinte          text    unique
);

create index if not exists value_bet_horodatage_idx on value_bet (horodatage desc);
create index if not exists value_bet_statut_idx     on value_bet (statut);
"""


class SqliteDepot(Depot):
    """Stockage local : aucune configuration, aucun service externe."""

    nom = "SQLite local"

    def __init__(self, chemin: Path | str | None = None) -> None:
        self.chemin = Path(chemin) if chemin else CHEMIN_DEFAUT
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        self._cx = sqlite3.connect(str(self.chemin), check_same_thread=False)
        self._cx.row_factory = sqlite3.Row
        self._cx.executescript(SCHEMA)
        self._cx.commit()

    # ------------------------------------------------------------------ #
    def enregistrer_scan(self, rapport: dict[str, Any], *,
                         seuil_ev: float, seuil_confiance: int) -> int:
        compteurs = rapport.get("compteurs") or {}
        curseur = self._cx.execute(
            """insert into scan (horodatage, source, depuis_cache, seuil_ev,
                                 seuil_confiance, matchs_observes, matchs_evalues,
                                 nb_pronostics, nb_value_bets, avertissements, erreur)
               values (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                rapport.get("horodatage") or datetime.now(timezone.utc).isoformat(),
                str(rapport.get("source") or ""),
                1 if rapport.get("depuis_cache") else 0,
                float(seuil_ev), int(seuil_confiance),
                int(compteurs.get("matchs_a_venir") or compteurs.get("matchs_total") or 0),
                int(compteurs.get("matchs_evalues") or 0),
                len(rapport.get("pronostics") or []),
                len(rapport.get("value_bets") or []),
                json.dumps(rapport.get("avertissements") or [], ensure_ascii=False),
                rapport.get("erreur") or None,
            ),
        )
        self._cx.commit()
        return int(curseur.lastrowid)

    # ------------------------------------------------------------------ #
    def enregistrer_value_bets(self, paris: list[dict[str, Any]],
                               scan_id: int | None = None) -> int:
        ecrits = 0
        for pari in paris:
            normalise = normaliser_pari(pari)
            try:
                self._cx.execute(
                    """insert into value_bet (scan_id, horodatage, competition,
                           match_libelle, equipe, marche, cote, probabilite_modele,
                           probabilite_marche, ecart_points, ev, confiance,
                           mise_recommandee, statut, empreinte)
                       values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        scan_id,
                        datetime.now(timezone.utc).isoformat(),
                        normalise["competition"],
                        normalise["match_libelle"],
                        normalise["equipe"],
                        normalise["marche"],
                        normalise["cote"],
                        normalise["probabilite_modele"],
                        normalise["probabilite_marche"],
                        normalise["ecart_points"],
                        normalise["ev"],
                        normalise["confiance"],
                        normalise["mise_recommandee"],
                        "detecte",
                        normalise["empreinte"],
                    ),
                )
                ecrits += 1
            except sqlite3.IntegrityError:
                # Empreinte déjà présente : ce pari a déjà été enregistré par un
                # scan précédent. Ce n'est pas une erreur.
                continue
        self._cx.commit()
        return ecrits

    # ------------------------------------------------------------------ #
    def value_bets_recents(self, limite: int = 10) -> list[dict[str, Any]]:
        lignes = self._cx.execute(
            """select * from value_bet order by id desc limit ?""", (int(limite),)
        ).fetchall()
        return [dict(ligne) for ligne in lignes]

    # ------------------------------------------------------------------ #
    def statistiques(self) -> dict[str, Any]:
        total = self._cx.execute("select count(*) as n from value_bet").fetchone()["n"]
        par_statut = {
            ligne["statut"]: ligne["n"]
            for ligne in self._cx.execute(
                "select statut, count(*) as n from value_bet group by statut").fetchall()
        }
        ev_moyenne = self._cx.execute(
            "select avg(ev) as e from value_bet").fetchone()["e"]
        confiance = self._cx.execute(
            "select avg(confiance) as c from value_bet").fetchone()["c"]
        scans = self._cx.execute("select count(*) as n from scan").fetchone()["n"]
        dernier = self._cx.execute(
            "select horodatage, nb_value_bets, nb_pronostics from scan "
            "order by id desc limit 1").fetchone()
        return {
            "total_value_bets": int(total or 0),
            "par_statut": par_statut,
            "ev_moyenne": ev_moyenne,
            "confiance_moyenne": confiance,
            "nb_scans": int(scans or 0),
            "dernier_scan": dict(dernier) if dernier else None,
            "depot": self.nom,
        }

    # ------------------------------------------------------------------ #
    def fermer(self) -> None:
        try:
            self._cx.close()
        except Exception:
            pass
