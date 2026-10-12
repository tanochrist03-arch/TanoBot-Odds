# 🎯 TanoBot Odds

**Bot Telegram d'analyse de value bets et de statistiques sportives.**

Il collecte les cotes de basket, estime une probabilité, calcule l'espérance
mathématique de chaque pari, et n'alerte que lorsque le marché se trompe — ou
semble se tromper.

```
EV = (probabilité estimée × cote) − 1
```

Un value bet n'existe que si `EV > 0` **après** prise en compte de la marge du
bookmaker.

---

## 1. Présentation — quel problème ce bot résout-il ?

Un parieur qui mise au hasard perd la marge du bookmaker, mécaniquement. Cette
marge n'est pas visible : elle est fondue dans les cotes. Sur un match à deux
issues, des cotes de 1,90 / 1,90 impliquent `1/1,90 + 1/1,90 = 1,053` — soit
**5,3 % prélevés** avant même que le match commence.

Trouver un « bon pari » ne suffit donc pas. Il faut trouver un pari dont la
probabilité réelle est **supérieure** à celle qu'annonce la cote. C'est ce que
calcule ce bot.

**Ce qu'il apporte concrètement :**

- il compare sa propre estimation à celle du marché, et affiche **les deux** ;
- il refuse de déclarer une valeur quand il n'a pas assez de données, au lieu
  d'inventer un écart ;
- il conserve l'historique, ce qui permet de mesurer **a posteriori** si le
  modèle vaut mieux que le marché — la seule question qui compte.

---

## 2. Fonctionnement

Le bot s'appuie sur un moteur d'analyse **déjà éprouvé** : celui de
[TanoTech Basket Analytics](../TanoTech-Basket-Analytics). Il ne réimplémente
aucun calcul.

**Pourquoi cette séparation ?** Parce que recopier une formule crée deux codes
qui divergent en silence. Le moteur a été corrigé sur des défauts mesurés :

| Défaut constaté | Correction |
|---|---|
| **36 value bets annoncés à +495 % d'EV** sur 67 matchs | Sans profil d'équipe, le modèle s'aligne sur le marché et se tait |
| **+15,6 % d'EV imaginaire** | Probabilité et EV calculées sur la **même** base de cotes (la marge du bookmaker n'est plus comptée comme un avantage) |
| Paris à +46 % sur 6 matchs | Nombre minimum de matchs exigé pour parier |

Recopier ce moteur aurait fait revenir ces trois défauts. Le bot l'importe donc
tel quel, et un test vérifie que les fonctions utilisées proviennent bien de
`engine.math_models` et `services.analysis` — pas d'une copie locale.

### Chaîne de traitement

```
   Source de cotes
        │
        ▼
   ingestion ──────────► profils d'équipes (marqués / encaissés, domicile/extérieur)
        │                              │
        ▼                              ▼
   probabilités du modèle ◄──── mélange avec le marché (30 %)
        │
        ▼
   comparaison au marché ──► écart en points
        │
        ▼
   expected_value() ──► EV positive ? ──► seuils de confiance
        │
        ▼
   mise recommandée (Kelly fractionnaire, plafond 2 % du capital)
        │
        ├──► message Telegram
        └──► Supabase / SQLite (historique)
```

---

## 3. Architecture

```
TanoBot-Odds/
├── bot/
│   ├── config.py           configuration, secrets, diagnostic
│   ├── engine_bridge.py    pont vers le moteur vérifié (aucun calcul réécrit)
│   ├── contexte.py         état partagé + verrou d'analyse
│   ├── rendu.py            mise en forme des messages (un seul endroit)
│   ├── keyboards.py        boutons interactifs
│   ├── handlers.py         commandes Telegram + filtre d'autorisation
│   ├── alerts.py           scan planifié et notifications
│   └── main.py             point d'entrée
├── storage/
│   ├── base.py             interface + traduction des noms de champs
│   ├── sqlite_store.py     stockage local
│   └── supabase_store.py   stockage distant
├── sql/001_schema.sql      schéma Supabase (tables, index, RLS)
├── tests/                  72 tests
└── verifier_integration.py contrôle de bout en bout
```

**Le stockage est interchangeable.** Le bot démarre avec SQLite s'il n'y a pas
de clés Supabase, et bascule automatiquement dès qu'elles sont fournies. Le
mode utilisé est **affiché au démarrage** : on ne doit jamais se demander où les
données ont été écrites.

---

## 4. Technologies

| Rôle | Choix | Pourquoi |
|---|---|---|
Bot | **aiogram 3** | Asynchrone nativement : le scan (long) et l'écoute Telegram (permanente) ne se bloquent pas mutuellement. `python-telegram-bot` conviendrait, mais aiogram s'intègre plus directement à un planificateur asynchrone. |
Planification | **APScheduler** | Planificateur asynchrone, partage la boucle d'événements du bot. |
Base distante | **Supabase** (PostgreSQL) | Exigé par le cahier des charges ; historique consultable en ligne. |
Base locale | **SQLite** (stdlib) | Permet de lancer et tester le bot sans configuration. |
Moteur | **Python standard** | Aucune dépendance de calcul : le moteur n'utilise que la bibliothèque standard. |
Secrets | **python-dotenv** | Séparation stricte entre le code et les identifiants. |

Le bot n'ajoute que **quatre dépendances directes**. Chacune est une surface à
surveiller ; aucune n'est là par confort.

---

## 5. API externe

**Le bot n'appelle aucune API tierce : il lit des pages publiques** de
comparaison de cotes (`betexplorer.com`), avec les limitations décrites en §9.

⚠️ **Les sources citées dans un cahier des charges classique — OddsPortal et
Flashscore — ne sont pas exploitables.** Vérifié depuis ce réseau : les deux
renvoient `HTTP 200` avec **381 Ko et 735 Ko de page anti-robot** (captcha),
donc **aucune cote**. Un code 200 ne signifie pas « accessible » : un scraper
naïf y voit « 0 match » et on cherche le bug pendant des heures.

| Source | État mesuré |
|---|---|
`betexplorer.com/basketball/next/` | ✅ Contenu réel (581 blocs de données) |
`betexplorer.com/next/soccer/` | ✅ Contenu réel (1007 blocs) |
`oddsportal.com` | ❌ Page anti-robot (captcha) |
`flashscore.com` | ❌ Page anti-robot (captcha) |
`sofascore.com` | ❌ Cloudflare + refus explicite |
`api.the-odds-api.com` | ⚠️ `HTTP 401` — clé payante requise |
`site.web.api.espn.com` | ✅ Accessible (calendriers, mais **aucune cote basket**) |

---

## 6. Base de données

Trois tables, séparées parce que les informations n'ont ni la même durée de vie
ni la même utilité.

| Table | Ce qu'elle contient | Pourquoi elle existe |
|---|---|---|
`scan` | une exécution : horodatage, source, **seuils appliqués**, volumétrie | Un chiffre sorti de son contexte (un jour avec d'autres seuils) devient incomparable. Les seuils sont stockés **une fois par scan**, pas répétés sur chaque ligne. |
`match` | chaque rencontre évaluée, avec les probabilités **du modèle ET du marché** | C'est cette table qui permet de mesurer plus tard si le modèle vaut mieux que le marché. |
`value_bet` | chaque opportunité détectée + son cycle de vie (`detecte` → `joue` → `gagne`/`perdu`) | Le suivi du résultat réel est ce qui distingue un outil d'analyse d'un outil qui apprend. |

**Une contrainte d'unicité protège contre le double comptage.** Chaque pari
porte une *empreinte* calculée sur le match, le marché et l'équipe — **pas** sur
la cote ni sur l'EV, qui varient d'un scan à l'autre. Un value bet redétecté le
lendemain est donc reconnu comme le même, et non compté deux fois.

### Sécurité de la base

```sql
alter table public.scan       enable row level security;
alter table public.match      enable row level security;
alter table public.value_bet  enable row level security;
-- Aucune politique n'est créée — volontairement.
```

**RLS est activé et aucune politique n'est définie.** Le bot tourne côté serveur
avec la clé `service_role`, qui contourne RLS par conception. Résultat : le bot
lit et écrit, **personne d'autre ne peut rien voir**.

C'est un point à expliquer : ajouter une politique `using (true)` « pour que ça
marche » annulerait la protection et exposerait l'historique complet.

---

## 7. Installation

### Prérequis

- Python 3.11 ou supérieur
- Le projet **TanoTech Basket Analytics** (le moteur), placé à côté de ce dossier
- Un bot Telegram (facultatif pour tester : le mode `--verifier` fonctionne sans)

### Étapes

```bash
# 1. environnement
uv venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt

# 2. configuration
cp .env.example .env
#   → remplis BOT_TOKEN et BOT_ADMIN_IDS (voir §8)

# 3. contrôle avant démarrage
.venv/Scripts/python.exe -m bot.main --verifier

# 4. Supabase (facultatif)
#   → exécute sql/001_schema.sql dans l'éditeur SQL de ton projet Supabase

# 5. lancement
.venv/Scripts/python.exe -m bot.main
```

> **Windows / venv** : si un import échoue avec `ModuleNotFoundError:
> pydantic_core`, c'est que la variable `PYTHONPATH` pointe vers le Python
> système et court-circuite l'isolation du venv. Utilise
> `set PYTHONPATH=` (cmd) ou `export PYTHONPATH=""` (bash) avant de lancer.

---

## 8. Utilisation

### Obtenir le jeton du bot

1. Sur Telegram, écris à **@BotFather** → `/newbot` → choisis un nom
2. Il renvoie un jeton de la forme `123456:ABC-DEF…` → mets-le dans `BOT_TOKEN`
3. Écris à **@userinfobot** : il te renvoie ton identifiant numérique → mets-le
   dans `BOT_ADMIN_IDS`

**Sans `BOT_ADMIN_IDS`, le bot refuse tout le monde — y compris toi.** C'est
volontaire : un bot d'analyse laissé ouvert exposerait l'historique et la base à
n'importe qui.

### Commandes

| Commande | Effet |
|---|---|
`/start` | présentation et menu |
`/scan` | collecte les cotes et relance le moteur |
`/matches` | les matchs à venir, cotes et probabilité du marché |
`/valuebets` | les paris à espérance positive, avec la mise recommandée |
`/stats` | historique : combien d'analyses, combien d'opportunités, quelle réussite réelle |
`/sante` | état du moteur, du stockage et de la configuration |
`/aide` | la liste des commandes |

### Alertes automatiques

Dans `.env` :

```bash
ALERTES_ACTIVES=1
HEURE_SCAN=07:00
FUSEAU=Africa/Abidjan
```

Le bot **n'envoie un message que s'il a quelque chose à dire**. Pas de « rien de
nouveau » quotidien : un bot qui parle pour ne rien dire finit en sourdine, et
l'alerte qui compte passe inaperçue. Seuls deux cas déclenchent une
notification :

1. une ou plusieurs opportunités franchissent tous les seuils ;
2. la source de cotes échoue **trois fois de suite** — là, c'est le système qui
   a besoin d'attention.

---

## 9. Limites — ce que ce bot ne sait pas faire

Énoncées franchement, parce qu'elles conditionnent l'usage.

**Sur les performances**

- **Il ne prédit pas les résultats.** Il compare deux estimations : la sienne et
  celle du marché. Les deux peuvent se tromper.
- **Aucun gain n'est promis.** Une EV positive est une espérance sur le long
  terme, pas un résultat sur un match. C'est précisément pour cela que la mise
  recommandée est plafonnée à 2 % du capital.
- **Aucun backtest complet n'a été réalisé.** Le suivi du taux de réussite réel
  nécessite que les résultats des matchs soient renseignés, ce que le bot ne
  fait pas seul.

**Sur les données**

- **Le moteur ne connaît ni les blessures, ni les compositions, ni la forme
  physique.** Il travaille sur les scores passés et les cotes du marché. Les
  sélections sont donc **pilotées par le marché**, pas par une analyse d'équipe.
- **13 matchs sur 75 n'ont pas de profil exploitable** lors d'un relevé type :
  les compétitions hors saison renvoient une page de résultats vide. Pour
  ceux-là, le modèle s'aligne sur le marché et ne déclare rien.
- **La source limite le débit.** Des requêtes trop rapprochées sont
  temporairement refusées : le bot affiche alors une erreur explicite plutôt
  qu'une liste vide.
- **Le marché du basket n'a que deux issues** (1 et 2), pas de match nul. Les
  barèmes conçus pour le football ne s'y transposent pas.

**Sur le périmètre**

- **Le bot ne place aucun pari.** Il n'accède à aucun compte de bookmaker, ne
  détecte aucun paiement et ne connaît aucune cote personnalisée.
- **Il ne règle pas les paris automatiquement.** Le passage `détecté` → `joué`
  → `gagné`/`perdu` est manuel, faute de source de résultats fiable et
  autorisée.
- **Il ne fonctionne que sur le basket**, seule discipline pour laquelle les
  cotes sont accessibles depuis ce réseau.

---

## 10. Tests

```bash
.venv/Scripts/python.exe -m unittest discover -s tests -t .
.venv/Scripts/python.exe verifier_integration.py        # chaîne complète, données réelles
```

**72 tests** couvrent :

| Domaine | Ce qui est vérifié |
|---|---|
Configuration | valeurs par défaut, saisies invalides, variantes booléennes |
**Secrets** | le jeton et la clé Supabase n'apparaissent **jamais** en clair |
Stockage | écriture, **unicité par empreinte** (pas de double comptage), statistiques |
Traduction des champs | le moteur et la base n'ont pas les mêmes noms : la traduction couvre les deux |
Rendu | format français, échappement HTML, absence de promesse de gain |
Moteur | EV déléguée (pas recopiée), formule vérifiée à la cote d'équilibre |
Autorisation | un identifiant inconnu est **refusé** ; sans liste, personne ne passe |
Planification | construction, désactivation, heure illisible |

---

## 11. Avertissement

Ce bot est un **outil d'analyse statistique**. Il ne garantit aucun gain, ne
place aucun pari et n'accède à aucun compte de bookmaker.

Les paris sportifs comportent un risque de perte. La marge du bookmaker rend
l'espérance négative pour la grande majorité des paris — c'est ce que ce bot
sert à visualiser, pas à contourner.

Ce projet est destiné à un **usage personnel d'analyse**. Vérifie la
réglementation applicable dans ton pays avant toute pratique de pari.
