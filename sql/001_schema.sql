-- ============================================================================
--  TanoBot Odds — schéma de base (Supabase / PostgreSQL)
-- ============================================================================
--  À exécuter une fois dans l'éditeur SQL de Supabase.
--
--  POURQUOI CES TABLES ?
--  Le bot produit trois niveaux d'information, qui n'ont ni la même durée de
--  vie ni la même utilité :
--
--    1. `scan`       : une exécution de l'analyse. Sert à savoir quand le
--                      système a tourné, sur quelle source, et avec quels
--                      seuils. Sans cette table, un chiffre sorti de son
--                      contexte (un jour de seuils différents) devient
--                      incomparable.
--    2. `match`      : chaque rencontre évaluée, avec les probabilités du
--                      modèle ET celles du marché. C'est cette table qui
--                      permet de mesurer, plus tard, si le modèle vaut mieux
--                      que le marché — la seule question qui compte vraiment.
--    3. `value_bet`  : chaque opportunité détectée, avec son résultat une fois
--                      le match joué. C'est le suivi qui distingue un outil
--                      d'analyse d'un outil qui apprend.
--
--  La séparation `scan` → `match` → `value_bet` évite la redondance : les
--  seuils sont stockés une fois par scan, pas répétés sur chaque ligne.
-- ============================================================================

-- ---------------------------------------------------------------- extensions
create extension if not exists "pgcrypto";

-- ------------------------------------------------------------------- scans
create table if not exists public.scan (
    id                bigserial primary key,
    horodatage        timestamptz      not null default now(),
    source            text             not null,
    depuis_cache      boolean          not null default false,
    seuil_ev          numeric(6, 4)    not null default 0.05,
    seuil_confiance   integer          not null default 45,
    matchs_observes   integer          not null default 0,
    matchs_evalues    integer          not null default 0,
    nb_pronostics     integer          not null default 0,
    nb_value_bets     integer          not null default 0,
    avertissements    jsonb            not null default '[]'::jsonb,
    -- Un scan marqué en erreur reste enregistré : c'est une information utile
    -- (source indisponible), pas un déchet à effacer.
    erreur            text
);

comment on table public.scan is
    'Une exécution de l''analyse : contexte (seuils, source) et volumétrie.';

-- ------------------------------------------------------------------- matchs
create table if not exists public.match (
    id                      bigserial primary key,
    scan_id                 bigint references public.scan(id) on delete cascade,
    horodatage              timestamptz  not null default now(),
    debut_utc               timestamptz,
    competition             text         not null default '',
    domicile                text         not null,
    exterieur               text         not null,
    cote_domicile           numeric(8, 3),
    cote_exterieur          numeric(8, 3),
    cote_domicile_max       numeric(8, 3),
    cote_exterieur_max      numeric(8, 3),
    probabilite_modele_dom  numeric(6, 4),
    probabilite_modele_ext  numeric(6, 4),
    probabilite_marche_dom  numeric(6, 4),
    probabilite_marche_ext  numeric(6, 4),
    marge_marche            numeric(6, 4),
    ecart_points            numeric(6, 2),
    confiance               integer,
    -- Combien de matchs d'historique ont servi : sans ce chiffre, une
    -- probabilité n'est pas interprétable (8 matchs ≠ 40 matchs).
    matchs_historique_dom    integer default 0,
    matchs_historique_ext    integer default 0,
    justification           text,
    -- Résultat réel, renseigné plus tard : permet de mesurer la justesse.
    score_domicile          integer,
    score_exterieur         integer,
    termine                 boolean      not null default false
);

create index if not exists match_scan_idx        on public.match (scan_id);
create index if not exists match_horodatage_idx  on public.match (horodatage desc);
create index if not exists match_equipes_idx     on public.match (domicile, exterieur);

comment on table public.match is
    'Chaque rencontre évaluée : probabilités du modèle ET du marché, pour '
    'comparer les deux a posteriori.';

-- --------------------------------------------------------------- value bets
create table if not exists public.value_bet (
    id                     bigserial primary key,
    scan_id                bigint references public.scan(id) on delete set null,
    match_id               bigint references public.match(id) on delete set null,
    horodatage             timestamptz  not null default now(),
    competition            text         not null default '',
    match_libelle          text         not null,
    equipe                 text         not null default '',
    marche                 text         not null default 'vainqueur',
    cote                   numeric(8, 3) not null,
    probabilite_modele     numeric(6, 4) not null,
    probabilite_marche     numeric(6, 4),
    ecart_points           numeric(6, 2),
    ev                     numeric(7, 4) not null,
    confiance              integer,
    mise_recommandee       numeric(14, 2),
    mise_unites            numeric(8, 4),
    -- Cycle de vie : détecté → joué → réglé. Le statut est contraint pour
    -- qu'aucune valeur fantaisiste n'entre en base.
    statut                 text         not null default 'detecte'
                           check (statut in ('detecte', 'joue', 'gagne', 'perdu',
                                             'annule', 'ignore')),
    gain_reel              numeric(14, 2),
    note                   text,
    -- Empreinte d'unicité : un même pari détecté deux fois n'est enregistré
    -- qu'une seule fois (contrainte, pas convention).
    empreinte              text         unique,
    constraint ev_plausible check (ev < 10)
);

create index if not exists value_bet_horodatage_idx on public.value_bet (horodatage desc);
create index if not exists value_bet_statut_idx     on public.value_bet (statut);

comment on table public.value_bet is
    'Chaque opportunité détectée, avec son cycle de vie et son résultat réel.';

-- -------------------------------------------------- vue de suivi de performance
create or replace view public.bilan_value_bets as
select
    count(*)                                        as total,
    count(*) filter (where statut = 'joue')         as joues,
    count(*) filter (where statut = 'gagne')        as gagnes,
    count(*) filter (where statut = 'perdu')        as perdus,
    coalesce(avg(ev), 0)                            as ev_moyenne,
    coalesce(sum(gain_reel), 0)                     as gain_cumule
from public.value_bet;

comment on view public.bilan_value_bets is
    'Vue de synthèse : combien de paris, quel taux de réussite, quel gain réel.';

-- ============================================================================
--  SÉCURITÉ — RLS activé, aucun accès anonyme
-- ============================================================================
--  Le bot tourne côté serveur avec la clé service_role, qui contourne RLS par
--  conception. Activer RLS SANS créer de politique publique signifie donc :
--  le bot écrit et lit, personne d'autre ne peut rien voir.
--
--  C'est le point à expliquer : « j'ai activé RLS et je n'ai créé aucune
--  politique, parce qu'aucune donnée de cette base ne doit être lisible par
--  un visiteur. Une politique publique ici exposerait l'historique. »
-- ============================================================================

alter table public.scan       enable row level security;
alter table public.match      enable row level security;
alter table public.value_bet  enable row level security;

-- Aucune politique n'est créée volontairement. Ne pas en ajouter sans raison :
-- une politique `using (true)` annulerait la protection.
