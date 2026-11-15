# Sijar · Planification de la distribution et des tournées

**Sijar** (« les arbres » en tunisien, شجر) est l'outil d'aide à la décision du projet APS : chaque entrepôt est un
tronc, ses magasins sont des branches, les tournées les relient. Deux modules reliés (cahier des charges) :

* **Module 1 · Distribution** : affecter chaque magasin à un entrepôt (GAP, ou SSCFLP si l'ouverture
  des entrepôts est aussi à décider) ; 6 méthodes (2 exactes, 2 heuristiques, 2 métaheuristiques) ;
  tableau de bord 1, puis validation d'une affectation → fichier d'échange.
* **Module 2 · Tournées** : pour chaque entrepôt, TSP bi-objectif distance / temps ; 4 méthodes
  (somme pondérée, NSGA-II, 2PPLS, ε-contrainte exacte) ; tableau de bord 2 (front de Pareto, carte,
  plan final, export, comparaison de scénarios, retour vers le module 1).

La démarche complète, les choix et leur justification sont expliqués dans
[DEMARCHE_JALON2.md](DEMARCHE_JALON2.md).

## Lancer la démo

```
pip install -r requirements.txt
python donnees_tunisie/generer_instances.py     # une fois : instances S, M, L + références HiGHS
uvicorn backend.app:app --port 8000             # puis ouvrir http://localhost:8000
```

Une seule application à barre latérale, six stations (la puce jaune « Prochaine action » indique l'étape suivante) :

1. **Données** : jeu Tunisie S / M / L ou import d'un `instance.json`, modèle GAP ou SSCFLP, limite de temps, graine.
2. **Affectation** (tableau de bord 1) : lancer les 6 méthodes, tableau comparatif, carte, charge / capacité,
   convergence ; clic sur un magasin pour le confier à un autre entrepôt ; validation.
3. **Classeur** : la sortie du module 1 est un **classeur Excel** (`Lisez-moi`, `Affectation`, `Entrepôts`, `Coûts`,
   `Distances`, `Scénario`). La colonne `entrepot` est modifiable (liste déroulante) ; charges, taux et coûts se
   recalculent dans Excel. Le classeur, modifié ou non, se recharge dans l'outil : capacités contrôlées, magasins
   déplacés détectés, scénario dérivé `~x1`. Bouton « Charger dans le module 2 ».
4. **Tournées** (tableau de bord 2) : 4 méthodes, front de Pareto distance / temps par entrepôt, curseur de
   compromis, carte de la tournée, indicateurs (hypervolume, IGD). Cache par entrepôt : après une modification,
   seuls les entrepôts touchés sont recalculés.
5. **Plan final** : indicateurs consolidés module 1 + module 2, carte du réseau, export Excel / CSV.
6. **Scénarios** : comparaison des plans enregistrés, retour vers le module 1 avec coûts corrigés.

Cartes : tuiles OpenStreetMap (connexion internet requise pour le fond de carte). Thème clair / sombre.

## Tests

```
python -m pytest                                # 80 tests, ~1 min ; n'écrit rien dans sorties/
```

## Expérimentation (T5)

```
python experimentation/exp_reglage.py           # réglage des paramètres (Q4)
python experimentation/exp_module1.py           # module 1 (Q1, Q2)
python experimentation/exp_module2.py           # module 2 (Q3)
```

Protocole : [experimentation/PROTOCOLE.md](experimentation/PROTOCOLE.md). Résultats (CSV, synthèses
Markdown, figures) : `experimentation/resultats/`. Variable `APS_PROCESSUS` = nombre de processus (8 par défaut).

## Organisation

| Chemin | Rôle |
|---|---|
| `module1_methods.py` | méthodes exactes ① cut-and-solve (Gadegaard et al. 2018) et ② branch-and-price (Ryu & Park 2021) |
| `module1_heuristiques.py` | ③ matheuristique (regret + échanges + LNS à réparation MIP), ④ Kernel Search, ⑤ recuit simulé à pénalité, ⑥ recuit multi-voisinages à réparation |
| `module2_tournees.py` | matrices distance / temps, outils de Pareto (hypervolume, IGD), somme pondérée, NSGA-II, 2PPLS, ε-contrainte exacte |
| `backend/app.py` | API FastAPI du module 1 + service des pages ; écrit le fichier d'échange |
| `backend/api_module2.py`, `backend/tournees.py` | API et logique du module 2 : lecture du fichier d'échange, cache par entrepôt, plan, export, retour |
| `backend/classeur.py` | classeur Excel d'échange : écriture (formules, liste déroulante) et relecture d'un classeur modifié |
| `backend/methodes.py`, `indicateurs.py`, `donnees.py`, `travaux.py` | registre des méthodes du module 1, indicateurs, lecture des instances, file de calcul partagée |
| `frontend/` | application Sijar : `index.html`, `sijar.css` (charte), `js/core.js` (état, API, shader, cartes), `js/app.js` (navigation), `js/vues/` (une vue par station) |
| `donnees_tunisie/` | source B : instances générées (S 3 × 20, M 5 × 50, L 10 × 200) + références HiGHS |
| `donnees_benchmarks/` | source A : OR-Library (cap71 … cap134) et TSPLIB (kroA100, kroB100), voir son README |
| `experimentation/` | protocole, scripts, résultats |
| `sorties/` | fichiers d'échange `affectation_validee_<scénario>.json`, `plans/`, `cache_tournees/`, `instances_corrigees/` (non versionnés) |
| `tests/` | pytest : lecture automatique et indicateurs (module 1), heuristiques, module 2, intégration |

**Jeu de données Tunisie :** le jeu officiel `donnees_tunisie/` (avec `rapport_donnees.pdf`) n'était pas
dans le dépôt. `generer_instances.py` produit un jeu de substitution au même format (graine publiée).
Pour utiliser le jeu officiel, copiez ses dossiers dans `donnees_tunisie/instances/` à la place.
