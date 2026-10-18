# APS · Module 1 – Tableau de bord 1 (Distribution)

## Lancer la démo

```
pip install -r requirements.txt
python donnees_tunisie/generer_instances.py     # une fois (instances S, M, L + références HiGHS)
uvicorn backend.app:app --port 8000             # puis ouvrir http://localhost:8000
```

## Tests

```
python -m pytest tests
```

## Organisation

| Dossier | Rôle |
|---|---|
| `module1_methods.py` | méthodes ① cut-and-solve (Gadegaard et al. 2018) et ② branch-and-price (Ryu & Park 2021) |
| `backend/` | FastAPI : `donnees.py` (lecture d'`instance.json`), `indicateurs.py` (lecture automatique §6, indicateurs §7), `methodes.py` (registre + adaptateur `resoudre`), `app.py` (API §4) |
| `frontend/` | page HTML/CSS/JS sans framework, reproduit `handoff_dashboard/maquette_dashboard_module1.dc.html` |
| `donnees_tunisie/` | instances `instances/<S|M|L>/<id>/instance.json` + `matrices.npz` |
| `sorties/` | fichiers d'échange `affectation_validee_<scénario>.json` vers le module 2 |

**Jeu de données :** le jeu officiel `donnees_tunisie/` (avec `rapport_donnees.pdf`) n'était pas
dans le dépôt. `generer_instances.py` produit un jeu de substitution au même format. Pour utiliser
le jeu officiel, copiez ses dossiers dans `donnees_tunisie/instances/` à la place.
