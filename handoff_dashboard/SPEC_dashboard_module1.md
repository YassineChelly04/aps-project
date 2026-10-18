# Spécification — Tableau de bord 1 (Module 1 · Distribution), projet APS

À l'attention de Claude Code. Objectif : implémenter dans le dépôt le tableau de bord
décrit par la maquette `maquette_dashboard_module1.dc.html`, branché sur les deux
méthodes exactes déjà codées en Python. La maquette fait foi pour la mise en page,
le texte et le comportement ; ce document fixe l'architecture et les règles de calcul.

> La maquette est au format « Design Component » (balises `<x-dc>`, `{{trous}}`,
> `<sc-for>`, `<sc-if>`, classe `Component` en bas du fichier). Ce n'est PAS du
> HTML à copier tel quel : c'est la référence visuelle et logique. Toute la logique
> de calcul est dans `renderVals()` ; la reproduire côté Python.

---

## 1. Ce qui existe déjà (à inspecter avant de coder)

- Les deux méthodes exactes en Python (dans le dépôt) :
  ① Cut-and-solve — Gadegaard, Klose & Nielsen (2018) ;
  ② Branch-and-price — Ryu & Park (2021).
- Le jeu de données « Tunisie » : `donnees_tunisie/instances/<S|M|L|XL>/<id>/instance.json`
  (+ `matrices.npz`), décrit dans `donnees_tunisie/README.md` et `rapport_donnees.pdf`.

Commencer par lire le code des deux méthodes et noter leur signature réelle.
Ne PAS réécrire ces méthodes : les envelopper.

## 2. Architecture demandée

Le cahier des charges recommande Python (Streamlit ou Dash). La maquette exige un
rendu centré et soigné que Streamlit rend mal. Choix retenu :

```
backend/   FastAPI (Python) — charge les instances, lance les méthodes, calcule les indicateurs
frontend/  une page HTML + CSS + JavaScript (sans framework), qui reproduit la maquette
```

- `uvicorn backend.app:app` sert aussi `frontend/` en statique → une seule commande pour la démo.
- Aucune dépendance réseau à l'exécution sauf Google Fonts (IBM Plex Sans / Mono) ;
  prévoir une police de repli système.
- Si l'équipe impose Streamlit/Dash, garder exactement les mêmes étapes, textes,
  indicateurs et règles (sections 4 à 7) ; seule la couche d'affichage change.

## 3. Interface commune des méthodes (adaptateur)

Créer `backend/methodes.py` avec un registre :

```python
METHODES = {
  "cs": {"num": "①", "nom": "Cut-and-solve", "ref": "Gadegaard, Klose & Nielsen (2018)", "famille": "exacte", "pret": True},
  "bp": {"num": "②", "nom": "Branch-and-price", "ref": "Ryu & Park (2021)", "famille": "exacte", "pret": True},
  "h1": {"num": "③", "nom": "Matheuristique à grands voisinages", "ref": "Kong (2021)", "famille": "heuristique", "pret": False},
  "h2": {"num": "④", "nom": "Kernel Search + motifs", "ref": "Bakker et al. (2025)", "famille": "heuristique", "pret": False},
  "m1": {"num": "⑤", "nom": "Recuit simulé", "ref": "McKendall & Dhungel (2024)", "famille": "metaheuristique", "pret": False},
  "m2": {"num": "⑥", "nom": "Recuit multi-voisinages", "ref": "Ceschia & Schaerf (2024)", "famille": "metaheuristique", "pret": False},
}

def resoudre(cle, instance, modele, limite_temps, graine=0, progression=None) -> dict:
    """modele = "gap" (tous ouverts, sans coût fixe) ou "sscflp" (ouverture + affectation).
    progression(phase:str, fraction:float) est appelé par la méthode si elle le peut.
    Retourne :
      affectation: {id_magasin: id_entrepot}
      cout_total, borne_inf (ou None), optimal_prouve (bool), temps_s (mesuré, perf_counter)
      trace: [(temps_s, meilleur_cout), ...]   # pour l'intégrale primale du benchmark
    """
```

- `temps_s` est le temps RÉEL mesuré (la maquette simule les temps : à remplacer).
- Les méthodes ③–⑥ (`pret: False`) renvoient une erreur claire si appelées ;
  le frontend les affiche « Jalon ultérieur ».
- Phases affichées pendant le calcul (si la méthode ne remonte pas sa progression,
  afficher seulement un indicateur d'activité et le temps écoulé) :
  - ① : « Plans coupants », « Branchement local », « Problème épars / dense », « Fermeture de l'écart »
  - ② : « Décomposition de Dantzig-Wolfe », « Génération de colonnes », « Branchement », « Fermeture de l'écart »

## 4. API (FastAPI)

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/api/exemples` | liste des instances d'exemple (S, M, L) |
| POST | `/api/instance` | charge un `instance.json` (fichier déposé ou id d'exemple) → résumé + lecture automatique |
| POST | `/api/calcul/{cle}` | lance une méthode (`modele`, `limite_temps`) dans un thread → `job_id` |
| GET | `/api/calcul/{job_id}` | état : `en_cours` (phase, fraction, écoulé) ou `termine` (résultat + indicateurs) — interrogé toutes les 300 ms |
| POST | `/api/evaluer` | indicateurs d'une affectation quelconque (ajustement manuel) |
| POST | `/api/valider` | écrit le fichier d'échange vers le module 2, renvoie l'id de scénario |

Validation des entrées : rejeter un fichier qui n'a pas `meta`, `entrepots`,
`magasins`, `cout_affectation` avec le message « Ce fichier n'a pas le format
instance.json attendu. »

## 5. Parcours (4 étapes, tout est centré)

Bandeau fixe en haut : chemin « APS · Planification de la distribution › Module 1 ·
Affectation magasins → entrepôts › Module 2 · Tournées (jalon ultérieur) » et les
4 pastilles d'étapes (✓ faite / noire = en cours / grise = à venir).

1. **Données** — à l'arrivée, une seule action : grande zone « Glissez-déposez votre
   fichier ici » + bouton « Choisir un fichier » ; dessous, 3 jeux d'exemple
   (Petit 3 × 20, Moyen 5 × 50, Grand 10 × 200). Après chargement : pastille
   « id · région » + « Changer de fichier », 5 chiffres clés, 4 constats (§6).
2. **Calcul** — question « Peut-on fermer des entrepôts ? » : Non · GAP / Oui · SSCFLP
   (bloquée pendant un calcul ; la changer efface les résultats). Puis 6 tuiles en
   3 familles (Exactes, Heuristiques, Métaheuristiques). Tuile : prête → « Lancer » ;
   en cours → phase + barre + secondes ; terminée → coût, temps, « Optimum prouvé »
   (ou « écart à la borne x % » si arrêt sur limite de temps) ; ③–⑥ → « Jalon ultérieur ».
3. **Comparaison** (visible dès qu'une méthode a fini) — titre-conclusion généré (§7),
   tableau des 6 indicateurs, carte d'affectation, graphique charge / capacité.
4. **Décision** — choix de l'affectation (boutons radio), ajustement manuel
   (magasin → nouvel entrepôt, recalcul immédiat du coût, de l'écart et des capacités),
   bouton « Valider et transmettre au module 2 » (désactivé si une capacité est dépassée).

## 6. Lecture automatique (règles fixes, pas d'IA)

Calculées à partir de l'instance chargée (voir `renderVals()` de la maquette) :

- **Proximité** : affecter chaque magasin à l'entrepôt le plus proche ; si un
  entrepôt dépasse sa capacité → « Servir chaque magasin par l'entrepôt le plus proche
  est impossible » (+ entrepôt le plus chargé et son %), sinon « … est faisable ».
- **Capacité** : remplissage = demande / capacité ; ≥ 80 % tension forte,
  70–80 % modérée, sinon marge confortable.
- **Concentration** : part du 1er gouvernorat dans la demande (alerte si > 30 %)
  et part des 3 premiers.
- **Gros clients** : nombre d'hypermarchés et leur part ; le plus gros magasin.
  S'il n'y a pas d'hypermarché : magasin le plus isolé.

## 7. Indicateurs du tableau de bord 1 (cahier des charges §3.4)

Pour une affectation `a` :

- `coût total` = Σ c[i][a(i)] + (si SSCFLP) Σ f_j des entrepôts utilisés  — TND / semaine
- `temps de réponse` = temps mesuré de la méthode
- `écart / meilleure` = (coût − meilleur coût parmi les méthodes terminées) / meilleur
- `entrepôts ouverts` = GAP : m ; SSCFLP : nombre d'entrepôts avec charge > 0 (afficher « k / m »)
- `taux d'utilisation` = demande totale / capacité des entrepôts ouverts
- `distance moyenne` = moyenne des distances magasin → entrepôt affecté (km, `matrices.npz`)

En gras : meilleure valeur de chaque colonne. Titre-conclusion :
- 2 méthodes et même coût : « Même coût optimal, X TND/semaine : ① répond k fois plus vite »
- coûts différents : « <méthode> donne le coût le plus bas : X TND/semaine »
- une seule : « <méthode> trouve l'optimum : X TND/semaine avec k entrepôts sur m »

Carte : magasins colorés par entrepôt (taille ∝ √demande), lien magasin → entrepôt,
entrepôts en carrés étiquetés, entrepôt fermé grisé « fermé ». Dans le code final,
utiliser Leaflet (ou Folium côté Python) avec un fond de carte ; la maquette dessine
une projection simple faute de fond de carte.

Charge / capacité : une barre par entrepôt, trait noir = capacité, barre rouge si dépassement.

## 8. Fichier d'échange vers le module 2 (cahier des charges §5)

`sorties/affectation_validee_<id_scenario>.json` :

```json
{"scenario": "SC-TN-M-g1-r135-SSC-2140", "instance": "TN-M-g1-r135", "modele": "sscflp",
 "methode": "cs", "ajustements": [{"magasin": "PV0145", "de": "E01", "vers": "E03"}],
 "cout_total": 27716.98,
 "entrepots": [{"id": "E01", "lat": 36.76, "lon": 10.26, "capacite": 617, "ouvert": true}],
 "magasins":  [{"id": "PV0145", "lat": 36.805, "lon": 10.104, "demande": 54, "entrepot": "E01"}]}
```

Le module 2 lira uniquement ce fichier.

## 9. Charte visuelle (reprendre la maquette)

- Fond `#F4F5F7`, cartes blanches, bordure `#E1E4EA`, rayon 16 px ; encre `#10141C`,
  texte secondaire `#5A6170` ; action et état actif `#2443C4` ; succès `#1E6B45` ;
  alerte `#8A4A0A` sur `#FBEDE0` ; dépassement `#C0392B`.
- IBM Plex Sans (texte), IBM Plex Mono (chiffres, `tabular-nums`).
- **Tout est centré** (titres, cartes, tableaux, boutons) : exigence explicite de l'utilisateur.
- Couleur réservée aux données et aux éléments cliquables ; le reste neutre.
- Cibles cliquables ≥ 44 px ; vrais `<button>`, `<label>` + `<input>` ; responsive
  (grilles `auto-fit`, tableau dans un conteneur `overflow-x: auto`).

## 10. Critères d'acceptation

1. Déposer `instance.json` (S, M ou L) affiche les chiffres clés et les 4 constats.
2. Lancer ① puis ② (GAP puis SSCFLP) donne des coûts égaux aux valeurs `reference`
   de l'instance (à 1 TND près), avec des temps réellement mesurés.
3. Le tableau, la carte et les charges se mettent à jour à chaque méthode terminée.
4. Un ajustement manuel qui dépasse une capacité bloque la validation.
5. La validation écrit le fichier d'échange de la section 8.
6. Tests : un test par règle de lecture automatique et par indicateur (pytest),
   sur `TN-S-g1-r135`.
