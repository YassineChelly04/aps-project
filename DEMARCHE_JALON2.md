# Projet APS — Démarche jusqu'au jalon 2 (outil intégré)

> Ce document explique **ce qui a été fait, dans quel ordre, et pourquoi**. Il sert de support
> pour présenter le travail à l'enseignant : chaque choix est justifié, chaque difficulté
> rencontrée est racontée avec la façon dont elle a été résolue, et les limites sont dites
> franchement. Les chiffres cités viennent des scripts du dépôt et sont reproductibles.

## Sommaire

1. [Où en est-on par rapport au cahier des charges ?](#1-où-en-est-on-par-rapport-au-cahier-des-charges-)
2. [Point de départ et plan de travail](#2-point-de-départ-et-plan-de-travail)
3. [Architecture de l'outil](#3-architecture-de-loutil)
4. [Données](#4-données)
5. [Module 1 : les six méthodes d'affectation](#5-module-1--les-six-méthodes-daffectation)
6. [Module 2 : TSP bi-objectif par entrepôt](#6-module-2--tsp-bi-objectif-par-entrepôt)
7. [Le lien entre les deux modules](#7-le-lien-entre-les-deux-modules)
8. [Les tableaux de bord](#8-les-tableaux-de-bord)
9. [Expérimentation](#9-expérimentation)
10. [Tests et vérifications](#10-tests-et-vérifications)
11. [Limites, honnêtement](#11-limites-honnêtement)
12. [Questions probables de l'enseignant et réponses](#12-questions-probables-de-lenseignant-et-réponses)
13. [Déroulé de la démonstration](#13-déroulé-de-la-démonstration)

---

## 1. Où en est-on par rapport au cahier des charges ?

| Exigence (section du cahier) | Réalisation | Où |
|---|---|---|
| §3.3 Module 1, modèle mathématique résolu par solveur, optimum ou écart à la borne | ① cut-and-solve et ② branch-and-price, limite de temps réglable, « optimum prouvé » ou « écart à la borne » | `module1_methods.py` |
| §3.3 Heuristique constructive + amélioration locale | ③ glouton par **regret** + **déplacer / échanger**, prolongé par une recherche à grands voisinages (LNS) ; ④ Kernel Search | `module1_heuristiques.py` |
| §3.3 Métaheuristique avec gestion des capacités (pénalité **ou** réparation) et réglage | ⑤ recuit simulé à **pénalité** ; ⑥ recuit multi-voisinages à **réparation** ; réglage documenté | `module1_heuristiques.py`, `experimentation/exp_reglage.py` |
| §3.4 Tableau de bord 1 : 6 indicateurs, carte, charge / capacité, choix, ajustement manuel | fait (jalon 1), complété : limite de temps, graine, garanties | `frontend/index.html`, `app.js` |
| §4.3 Module 2 : trois méthodes de natures différentes | somme pondérée (heuristique), NSGA-II (évolutionnaire à base de Pareto), 2PPLS (recherche locale de Pareto) **+** ε-contrainte exacte | `module2_tournees.py` |
| §4.4 Tableau de bord 2 : front superposé, clic → tournée sur carte, synthèse, export CSV / Excel | fait | `frontend/module2.html`, `module2.js` |
| §5 Fichier d'échange, le module 2 ne lit que lui | fait (JSON) | `backend/app.py` (`/api/valider`), `backend/tournees.py` |
| §5 Modification manuelle : seuls les entrepôts concernés sont recalculés | cache par **signature d'entrepôt** ; testé : 2 tournées recalculées, les 2 autres reprises du cache (TN-M) | `backend/tournees.py`, `tests/test_module2.py` |
| §5 Indicateurs consolidés et comparaison de scénarios | plan final M1 + M2, tableau des scénarios enregistrés | étape 4 du tableau de bord 2 |
| §5 / §10 Retour (bonus) | coût des tournées comparé au coût supposé dans c_ij ; création d'une instance corrigée relançable au module 1 | `/api/m2/retour` |
| §6 Au moins deux sources, trois tailles, origine / licence / traitements | B : Tunisie générée (S, M, L) ; A : OR-Library et TSPLIB | `donnees_tunisie/`, `donnees_benchmarks/README.md` |
| §7 T4 : Git, graines fixées, README | fait | `README.md` |
| §7 T5 : protocole défini à l'avance, 3 tailles, 10 exécutions des méthodes stochastiques | fait | `experimentation/` |

Restent pour le jalon final : la revue de littérature (T1) et la rédaction du rapport (T6). Ce
document et les fichiers de résultats en fournissent la matière pour les parties T2, T3 et T5.

---

## 2. Point de départ et plan de travail

**État au début de cette étape.** Le dépôt contenait le jalon 1 *partiel* : les deux méthodes
exactes ① et ②, un générateur d'instances « Tunisie » (S, M, L) avec des références HiGHS, et le
tableau de bord 1, où les quatre tuiles ③ à ⑥ affichaient « jalon ultérieur ». Il n'y avait ni
module 2, ni lien entre les modules, ni benchmark, ni expérimentation.

**Ordre de travail retenu, et pourquoi cet ordre :**

1. **Finir le module 1** (méthodes ③ à ⑥). Le module 2 consomme la sortie du module 1 ; il
   fallait que celle-ci soit complète avant de construire la suite.
2. **Cœur du module 2 en Python pur** (matrices, méthodes, indicateurs), testé hors interface.
   On sépare le calcul de l'affichage pour pouvoir tester et expérimenter sans navigateur.
3. **Intégration côté serveur** (fichier d'échange enrichi, cache par entrepôt, plan, export,
   retour), avec des tests de bout en bout via l'API.
4. **Tableau de bord 2**, vérifié dans un vrai navigateur (Edge sans interface, piloté par script).
5. **Données de référence** (OR-Library, TSPLIB) puis **protocole écrit avant** la campagne
   d'expérimentation.

À chaque étape, on a mesuré avant de conclure. Plusieurs défauts n'ont été découverts **que**
parce qu'on comparait systématiquement à l'optimum (voir §5.6 et §6.6).

---

## 3. Architecture de l'outil

```
                     donnees_tunisie/ (source B)        donnees_benchmarks/ (source A)
                              │                                   │ (expérimentation)
                              ▼                                   ▼
  ┌──────────── Module 1 · Distribution ────────────┐   module1_methods.py  ① ②
  │ index.html / app.js  ──HTTP──►  backend/app.py   │──►module1_heuristiques.py ③ ④ ⑤ ⑥
  │ (tableau de bord 1)            (FastAPI)         │
  └──────────────────────────────────┬───────────────┘
                     le décideur valide une affectation
                                     ▼
                sorties/affectation_validee_<scénario>.json   ◄── SEULE entrée du module 2
                                     ▼
  ┌──────────── Module 2 · Tournées ────────────────┐
  │ module2.html / module2.js ──HTTP──► api_module2 │──► backend/tournees.py ──► module2_tournees.py
  │ (tableau de bord 2)                (FastAPI)    │     (cache par entrepôt)    (4 méthodes)
  └──────────────────────────────────┬──────────────┘
                     le décideur choisit un compromis par tournée
                                     ▼
                sorties/plans/plan_<scénario>.json  →  export CSV / Excel
                                     │
                                     └─ retour (bonus) : instance aux coûts corrigés → module 1
```

**Pourquoi FastAPI + une page HTML plutôt que Streamlit ou Dash ?** Ce choix date du jalon 1
(maquette imposant une mise en page centrée et soignée, que Streamlit rend mal). On l'a gardé pour
le module 2, avec un avantage décisif : un **serveur unique** sert les deux modules. Ils partagent
donc la même file de calcul (`backend/travaux.py`, un calcul à la fois, ce qui évite de fausser les
temps mesurés) et le même dossier d'échange.

**Pourquoi séparer « méthodes » (fichiers racine) et « backend » ?** Les fichiers
`module1_*.py` et `module2_tournees.py` ne dépendent ni de FastAPI ni de l'interface. On peut
donc les appeler depuis les tests et les scripts d'expérimentation, qui mesurent ainsi exactement
le même code que celui de la démonstration.

---

## 4. Données

### 4.1 Source B — instances « Tunisie » générées (S, M, L)

Générées par `donnees_tunisie/generer_instances.py` (graine publiée, donc reproductibles) :
35 villes réelles pondérées par leur population, 10 zones logistiques réelles comme entrepôts
candidats. Trois tailles du cahier : S = 3 × 20, M = 5 × 50, L = 10 × 200. Les demandes dépendent
du format du magasin (proximité 4–12, supermarché 15–40, hypermarché 60–120 palettes / semaine).
La capacité totale vaut 1,35 fois la demande (dans l'intervalle 1,2–1,5 du cahier).

**Forme de c_ij (le cahier demande de la justifier) :**
`c_ij = d_i × (2 · KPAL · dist_ij + manutention_j)`, où :

* `KPAL = 0,12324 TND` = coût de transport d'une palette sur 1 km ;
* le facteur 2 compte l'aller-retour ;
* `dist_ij` = 1,25 × distance à vol d'oiseau, soit un ordre de grandeur du détour routier ;
* la manutention est propre à chaque entrepôt.

Ce coût est proportionnel à la demande et à la distance, donc un gros magasin éloigné coûte cher
à servir. C'est exactement la forme « distance × coût unitaire × demande » suggérée par le cahier.

### 4.2 Source A — benchmarks

Détails, licences et traitements : `donnees_benchmarks/README.md`. En résumé :

* **OR-Library, instances `cap`** (module 1). Le piège découvert : `cap41` à `cap64` sont
  **infaisables en source unique**, car un client demande 12 912 alors que les capacités valent
  au plus 7 500. Dans `cap71` à `cap134`, les capacités égalent la demande totale. L'optimum publié
  (pour le problème multi-source) est alors automatiquement mono-source, donc c'est aussi
  l'optimum SSCFLP. On l'a **vérifié avec HiGHS** : les 6 valeurs coïncident. Ces instances testent
  la décision d'ouverture (16, 25 et 50 entrepôts). Nos instances Tunisie testent, elles, les
  capacités tendues.
* **TSPLIB kroA100 / kroB100** (module 2) : l'instance bi-objectif « kroAB » de la littérature,
  avec mêmes villes, distance de kroA pour f1 et distance de kroB pour f2. On garde les 15, 25 et
  40 premiers nœuds.

### 4.3 Matrices distance / temps du module 2

Le cahier impose deux matrices qui **ne coïncident pas**. Si le temps était proportionnel à la
distance, les deux objectifs donneraient la même tournée et le front se réduirait à un point.
Notre modèle (`module2_tournees.matrices`) :

* `d_ij` = 1,25 × haversine, cohérent avec le module 1 ;
* `t_ij = d_ij / v(type de route) × congestion_ij × zone_dense`, avec :
  * vitesse selon la longueur du tronçon : < 8 km urbain, 35 km/h ; < 40 km régional, 60 km/h ;
    au-delà national, 85 km/h ;
  * congestion tirée dans [1 ; 1,5], comme le suggère le cahier (source B) ;
  * ×1,3 si le milieu du tronçon est dans le Grand Tunis, à Sfax ou à Sousse.
* un temps de service constant de 15 min par arrêt, ajouté au total. Il ne change pas
  l'optimisation, comme le précise le cahier.

**Détail important.** La congestion d'un tronçon est tirée par un hachage déterministe de la
paire de magasins (CRC32 de « graine | id1 | id2 »), et non par un générateur aléatoire séquentiel.
Ainsi, un même tronçon a **toujours** le même temps, quel que soit le scénario ou l'ensemble de
magasins de la tournée. Sans cela, le cache par entrepôt du §7 serait faux : deux scénarios qui
contiennent la même tournée produiraient des temps différents.

---

## 5. Module 1 : les six méthodes d'affectation

### 5.1 Modèle

Celui du cahier (§3.2). En **SSCFLP**, `min Σ c_ij x_ij + Σ f_j y_j` sous les contraintes :

* un seul entrepôt par magasin ;
* capacité `Σ_i d_i x_ij ≤ Q_j y_j` ;
* `x_ij ≤ y_j` ;
* variables binaires.

Le **GAP** est le même modèle avec tous les entrepôts ouverts et `f = 0`. Toutes les méthodes
reçoivent la même structure `Instance(c, d, s, f)`. Le GAP est passé avec `f = 0`, ce qui évite
deux codes différents.

### 5.2 Les deux méthodes exactes (jalon 1, rappel)

* **① Cut-and-solve** (Gadegaard, Klose & Nielsen 2018) en trois phases :
  1. plans coupants (couvertures relevées sur les contraintes de capacité) ;
  2. branchement local sur y puis sur x ;
  3. alternance entre un problème « dense » relâché (borne inférieure) et des problèmes « épars »
     exacts (solutions), jusqu'à ce que les bornes se rejoignent.
* **② Branch-and-price** (Ryu & Park 2021) : décomposition de Dantzig-Wolfe. Une colonne est un
  groupe de magasins servis par un entrepôt ; le pricing est un sac à dos résolu par
  programmation dynamique ; on branche sur y, puis sur les affectations.

Les deux renvoient l'optimum **prouvé**, ou la meilleure solution trouvée avec l'écart à la borne
si la limite de temps est atteinte (exigence du cahier).

### 5.3 ③ Matheuristique à grands voisinages (l'heuristique du cahier, prolongée)

**Principe.** Le cahier demande « glouton par regret, puis échanges (déplacement d'un point,
permutation de deux points) ». C'est exactement la phase 1. On la prolonge par une recherche à
grands voisinages (LNS) dont la réparation est **exacte**. On détruit une partie de la solution,
puis on réaffecte les magasins libérés de façon optimale par un petit MIP (HiGHS). Les autres
magasins restent fixés et leur charge réduit la capacité restante des entrepôts.

```
a ← glouton_par_regret()           # magasin au plus grand écart entre ses deux meilleurs entrepôts d'abord
a ← descente(a, {déplacer, échanger})
répéter jusqu'à 40 itérations sans gain (ou limite de temps) :
    op ← tirage pondéré parmi {voisins, entrepôts, regret, échange d'entrepôt}
    L  ← magasins libérés par op (q magasins)
    a' ← MIP_HiGHS(L, capacités résiduelles)   # optimal sur le sous-problème
    a' ← descente(a')
    si coût(a') < coût(a) : a ← a' ; poids[op] += 1 ; q ← q_min
    sinon : poids[op] *= 0,95 ; tous les 8 échecs, q *= 1,3
```

**Opérateurs de destruction et pourquoi :**

* *voisins* : un magasin et ses q−1 plus proches. La proximité se mesure sur le profil de coût
  `c_·j / d_j`, qui dépend de la distance : c'est un proxy géographique sans coordonnées, donc
  utilisable aussi sur OR-Library.
* *entrepôts* : **tous** les magasins d'un entrepôt, plus une partie d'un second. Libérer tous les
  magasins d'un entrepôt est la seule façon de pouvoir le fermer.
* *regret* : les magasins les plus chers par rapport à leur meilleur entrepôt.
* *échange d'entrepôt* (SSCFLP) : les magasins d'un entrepôt ouvert, plus ceux pour qui un
  entrepôt **fermé** est le moins cher. Le MIP peut alors fermer l'un et ouvrir l'autre en un seul
  mouvement.

**Paramètres :** q = 10 % des magasins (au moins 6), au plus 35 % ; 3 s maximum par sous-MIP ;
arrêt après 40 itérations sans gain. **Complexité :** chaque itération résout un MIP de
q × m variables, donc les MIP restent petits même sur 200 magasins. **Stochastique** (graine).

### 5.4 ④ Kernel Search

**Principe** (Angelelli, Mansini & Speranza 2010 ; version SSCFLP de Guastaroba & Speranza 2014).
La relaxation linéaire dit quelles variables x_ij ont des chances d'être à 1. On résout une suite
de MIP **restreints** à ces variables prometteuses (le *noyau*), puis au noyau augmenté de
*paquets* de variables triées par coût réduit.

```
(z_LP, x̄, coûts réduits) ← relaxation LP (forme forte, x_ij ≤ y_j)
noyau ← {x_ij : x̄_ij > 0} ∪ {affectations de la solution gloutonne}   # garantit un 1er MIP réalisable
a ← MIP(noyau)
paquets ← autres variables triées par coût réduit croissant, découpées en 8 paquets
pour chaque paquet P :
    a' ← MIP(noyau ∪ P, coût ≤ meilleur, au moins une variable de P à 1)
    si a' existe : a ← a' ; noyau ← noyau ∪ (variables de P utilisées)
a ← descente(a)
```

**Atout :** la valeur LP est une **borne inférieure**. Quand le coût trouvé l'atteint, l'optimum
est prouvé, et l'interface l'affiche (cas de toutes les instances GAP). **Déterministe.**

### 5.5 ⑤ et ⑥ : deux recuits simulés, pour comparer pénalité et réparation

Le cahier laisse le choix « pénalité ou réparation » pour gérer les capacités. Plutôt que de
choisir arbitrairement, on a fait **les deux**, avec le même moteur de recuit (`_recuit`), pour
pouvoir comparer.

**Moteur commun** (Kirkpatrick et al. 1983) :

* T0 telle qu'une dégradation moyenne soit acceptée avec la probabilité p0 (calibrée sur 400
  mouvements aléatoires) ;
* refroidissement géométrique `T ← 0,95 T` par palier jusqu'à `T_final = 10⁻⁴ T0` ;
* budget fixe de k × m × n itérations (borné à [10⁵ ; 3·10⁶]). p0 et k ont été réglés par
  expérience (§9.1) : p0 = 0,5 et k = 5 000 pour ⑤ ; p0 = 0,05 et k = 2 000 pour ⑥ ;
* descente finale (polissage) ;
* état incrémental : le coût et les charges sont mis à jour en O(1) par déplacement.

**Pourquoi un budget d'itérations et pas une durée ?** Pour la **reproductibilité**. Avec un arrêt
au temps, deux machines (ou deux exécutions sur une machine chargée) donneraient des résultats
différents pour la même graine. Avec un budget d'itérations, *même graine = même résultat*, ce
qui est vérifié par un test. La limite de temps reste un simple garde-fou.

* **⑤ pénalité** : objectif = `coût + w · Σ dépassements`, avec un poids w adaptatif (×1,10 si la
  solution courante est irréalisable, /1,05 sinon, tous les 100 mouvements). La recherche peut
  traverser l'irréalisable, et on ne garde que la meilleure solution **réalisable**.
* **⑥ réparation** (multi-voisinages, principe de Ceschia & Schaerf) : on ne propose **que** des
  mouvements qui restent réalisables. Quatre voisinages sont tirés au hasard :
  * déplacer et échanger (capacité vérifiée) ;
  * *vider* un entrepôt : ses magasins vont, par demande décroissante, à l'entrepôt réalisable le
    moins cher, ce qui ferme un entrepôt en un seul mouvement ;
  * *remplir* un entrepôt : il attire les magasins pour qui il est moins cher, ce qui l'ouvre en un
    seul mouvement.

### 5.6 Ce que le réglage nous a appris (deux défauts trouvés et corrigés)

**Défaut 1 : le recuit à pénalité restait bloqué en SSCFLP.** Au premier essai sur TN-M, ⑤
rendait **toujours** la solution initiale, à 4,86 % de l'optimum, quels que soient p0 et le
budget. L'analyse a montré un piège de structure : le glouton ouvre {E1, E2, E3, E5} alors que
l'optimum ouvre {E2, E3, E4, E5}. Pour passer de l'un à l'autre, il faut vider E1 magasin par
magasin. Chaque déplacement est dégradant jusqu'au dernier, qui seul économise le coût fixe ; à
basse température, un recuit ne franchit pas une telle barrière. **Correction :** un mouvement
« basculer un entrepôt » (2 % des tirages, SSCFLP seulement), qui ferme ou ouvre un entrepôt
d'un coup, ses magasins allant à l'entrepôt ouvert le moins cher. La capacité est ignorée, et
la pénalité s'en charge. Résultat : ⑤ passe de 4,86 % à environ 1 % sur TN-M SSCFLP, puis à 0,49 %
en moyenne sur 10 graines après réglage (§9). C'est aussi ce qui justifie que ⑥ ait des
voisinages *vider / remplir*.

**Défaut 2 : la matheuristique ③ ratait le même changement d'ouverture.** Elle restait à 2,9 % de
l'optimum sur TN-M SSCFLP pour les 3 graines testées. Cause : l'opérateur « entrepôts » tirait au
hasard une *partie* des magasins de l'entrepôt à libérer, donc l'entrepôt ne pouvait jamais
fermer. **Correction :** libérer **tous** ses magasins, et ajouter l'opérateur « échange
d'entrepôt ». Résultat : l'optimum est atteint sur M et L, en GAP et en SSCFLP, pour les 3 graines
testées. Sur les 10 graines de la campagne (§9), le piège subsiste pour **une** graine sur TN-M
SSCFLP (2,86 %) ; nous le signalons plutôt que de le cacher.

Ces deux épisodes illustrent un point de méthode : **on compare toujours à l'optimum prouvé**.
Sans la référence HiGHS, ces défauts seraient passés inaperçus, puisque les solutions étaient
réalisables et « raisonnables ».

### 5.7 Intégration dans l'outil

Chaque méthode respecte la même interface : `rapport(phase, fraction, meilleur_coût)` pour la
barre de progression et la trace, et `arret` (un `threading.Event`) pour le bouton « Arrêter »,
qui rend la meilleure solution trouvée. Le registre `backend/methodes.py` indique la famille et le
caractère stochastique. L'interface affiche donc le bon libellé :

* « Optimum prouvé » ;
* « écart à la borne LP x % » (④) ;
* « sans garantie d'optimalité » (③, ⑤, ⑥).

Le titre-conclusion ne parle plus d'« optimum » que si l'une des méthodes l'a **prouvé**. Avant,
une heuristique seule était annoncée « trouve l'optimum », ce qui était faux.

> **À signaler à l'enseignant :** la maquette du jalon 1 citait pour ③ à ⑥ des références (Kong
> 2021, Bakker et al. 2025, McKendall & Dhungel 2024, Ceschia & Schaerf 2024) dont nous n'avions
> pas les articles dans le dépôt. Les implémentations suivent les principes *génériques* décrits
> ci-dessus. Le registre cite désormais les références fondatrices réellement suivies. Si la revue
> de littérature (T1) retient ces articles, il faudra vérifier que nos implémentations leur
> correspondent, ou les présenter comme « inspirées de ».

---

## 6. Module 2 : TSP bi-objectif par entrepôt

### 6.1 Modèle

Pour chaque entrepôt (nœud 0) et ses n magasins : une tournée qui part de l'entrepôt, visite
chaque magasin une fois et revient. On minimise `f1 = Σ d_ij x_ij` (km) et `f2 = Σ t_ij x_ij`
(minutes de conduite). Le résultat attendu est un **front de Pareto** : l'ensemble des tournées
qu'on ne peut pas raccourcir sans les rallonger en temps, et inversement.

### 6.2 Méthode 1 — Somme pondérée (heuristique)

```
t1 ← 2opt+Oropt(PPV(D)) ; t2 ← 2opt+Oropt(PPV(T))      # tournées « extrêmes »
r1, r2 ← étendues de f1 et f2 entre t1 et t2            # normalisation
pour λ = 0 ; 0,05 ; … ; 1 :
    W ← λ D/r1 + (1−λ) T/r2
    t ← meilleure de { 2opt+Oropt(PPV(W)) , 2opt+Oropt(tournée du λ précédent) }
renvoyer les tournées non dominées
```

C'est la méthode suggérée par le cahier : plus proche voisin, 2-opt, Or-opt (déplacer un segment de
1 à 3 magasins, éventuellement retourné), λ de 0 à 1. **Normalisation :** sans elle, l'objectif
de plus grande amplitude écraserait l'autre. **Limite connue :** une somme pondérée ne trouve que
des points *supportés*, c'est-à-dire situés sur l'enveloppe convexe du front. Les points des
parties non convexes lui échappent quel que soit λ. C'est la raison d'être des deux méthodes
suivantes.

### 6.3 Méthode 2 — NSGA-II (évolutionnaire à base de Pareto)

Deb et al. (2002), comme le suggère le cahier :

* codage par permutation des magasins, l'entrepôt étant fixé en tête ;
* tournoi binaire (rang, puis distance d'encombrement) ;
* croisement **OX** (p = 0,9) ;
* mutation par **inversion** ou **échange** (p = 0,6) ;
* sélection élitiste (μ + λ) par tri de non-dominance ;
* population 100, 1 000 générations (taille et p réglées par expérience, §9.1) ;
* archive externe de toutes les solutions non dominées rencontrées ;
* deux individus initiaux « plus proche voisin », le reste aléatoire.

Le tri non dominé et l'évaluation de la population sont vectorisés avec numpy.

### 6.4 Méthode 3 — 2PPLS (recherche locale de Pareto)

Lust & Teghem (2010), cité par le cahier.

* **Phase 1** : points supportés par la méthode **dichotomique**. Entre deux points voisins du
  front, on minimise la somme pondérée orthogonale au segment qui les relie ; si on trouve un
  point sous le segment, on l'insère et on recommence de chaque côté.
* **Phase 2** : recherche locale de Pareto. Tant qu'il reste une solution non explorée dans
  l'archive, on évalue **tout** son voisinage 2-opt (Δf1 et Δf2 de chaque mouvement, vectorisés)
  et on ajoute chaque voisin non dominé.

On ajoute aussi 5 sommes pondérées fixes au départ de la phase 1. Sans elles, la dichotomie
s'arrêtait dès le début quand l'une des deux tournées « extrêmes » (obtenue par 2-opt, donc pas
exacte) était dominée par l'autre : c'était le cas de E02 de TN-L, où 2PPLS ne rendait qu'un point.

### 6.5 Méthode 4 — ε-contrainte exacte (référence)

```
ε ← +∞
répéter :
    f1* ← min f1  s.c. f2 ≤ ε                       # MIP HiGHS
    x   ← min f2  s.c. f1 ≤ f1*, f2 ≤ ε             # 2e étape lexicographique → point non dominé
    ajouter x au front ; ε ← f2(x) − 0,01 min
jusqu'à infaisabilité  (→ front COMPLET)  ou limite de temps (→ front partiel)
```

Chaque sous-problème est un TSP résolu exactement. On utilise la formulation symétrique en
variables d'arêtes : degré 2 en chaque nœud, et **coupes de sous-tours DFJ** ajoutées à la volée
quand la solution entière contient un sous-tour. Les coupes sont conservées d'un sous-problème à
l'autre, puisqu'elles sont valides pour tous. C'est l'équivalent du modèle MTZ du cahier (§4.2),
en plus fort : la relaxation de DFJ est plus serrée que celle de MTZ. Pour n ≤ 7, on énumère
toutes les tournées.

**Pourquoi l'étape lexicographique ?** Minimiser f1 seul sous `f2 ≤ ε` peut rendre un point
*faiblement* dominé, de même f1 mais de f2 plus grand. La seconde minimisation garantit que chaque
point est Pareto-optimal. **Constat :** le front exact est obtenu en quelques secondes jusqu'à
31 magasins sur les tournées tunisiennes (12 points pour E01 de TN-L en 2,9 s). Il nous sert
de **référence** pour juger les trois autres méthodes, et l'interface signale « front complet »
ou « front partiel ».

### 6.6 Indicateurs de qualité d'un front et choix du compromis

* **Hypervolume relatif.** C'est l'aire dominée par le front, divisée par celle du front de
  référence (100 % = aussi bon). Les objectifs sont normalisés sur l'idéal et le nadir de la
  référence, et le point de référence vaut (1,1 ; 1,1).
* **IGD.** C'est la distance moyenne de chaque point de la référence au point le plus proche du
  front évalué (0 = identique).
* **Part du front de référence retrouvée.**

**Choix du compromis : un défaut trouvé par un test.** Pour proposer un compromis par défaut et
régler toutes les tournées avec un seul curseur, on avait d'abord pris le point qui minimise une
somme pondérée normalisée. Le test unitaire sur le front {(0,10), (5,5), (10,0)} a échoué : sur
un front linéaire, les trois points sont *à égalité*, et le « compromis équilibré » renvoyait
une extrémité. On utilise donc la **distance de Tchebycheff pondérée au point idéal**,
`max(w·f1n, (1−w)·f2n)`. Elle désigne le point du milieu, et peut aussi choisir des points des
parties non convexes du front, ce qu'une somme pondérée ne fait jamais. La même règle est codée
côté serveur et côté navigateur.

---

## 7. Le lien entre les deux modules

C'est la partie « intégration », évaluée séparément selon le cahier (§5).

### 7.1 Le fichier d'échange

À la validation, le module 1 écrit `sorties/affectation_validee_<scénario>.json`. Il contient :

* **ce qu'exige le cahier** : pour chaque magasin, l'identifiant, les coordonnées, la demande et
  l'entrepôt affecté ; les entrepôts avec leurs coordonnées et leur capacité ; un identifiant de
  scénario ;
* **ce que nous avons ajouté, et pourquoi** : le modèle, la méthode et la date ; les ajustements
  manuels ; le coût du module 1 ; et, pour chaque magasin, ses coûts c_ij et ses distances vers
  **chaque** entrepôt. Ainsi, le module 2 peut réviser l'affectation (et recalculer le coût du
  module 1) et faire le retour **sans relire l'instance d'origine**. La règle « le module 2 ne lit
  que ce fichier » est donc respectée même pour ces fonctions avancées.

L'identifiant de scénario contient l'instance, le modèle, la méthode et l'horodatage à la seconde
(`SC-TN-L-g1-r135-SSC-h2-1109-073027`). Avant, il n'était qu'à la minute : deux validations dans
la même minute s'écrasaient.

### 7.2 « Seuls les entrepôts concernés sont recalculés »

Chaque tournée (un entrepôt et ses magasins) reçoit une **signature**, un hachage SHA-1 de
l'entrepôt, des identifiants et coordonnées des magasins, et des paramètres des matrices. Le
résultat d'une méthode est mis en cache sous la clé (signature, méthode, limite de temps, graine),
en mémoire et sur disque (`sorties/cache_tournees/`). Si le décideur déplace un magasin de E2 vers
E4, seules les signatures de E2 et E4 changent : les autres tournées sont reprises du cache.
L'interface l'affiche (par exemple « 2 entrepôts calculés, 7 repris du cache » sur TN-L) et un test le vérifie.

La révision est possible des deux côtés :

* au **module 1** (ajustement manuel avant validation, puis nouveau scénario) ;
* directement au **module 2** (« Réviser l'affectation »). Cette révision crée un **scénario
  dérivé** `…~r1`, sans modifier le fichier d'origine, refuse tout dépassement de capacité et
  recalcule le coût du module 1 à partir des c_ij du fichier.

### 7.3 Indicateurs consolidés et comparaison de scénarios

Le plan final réunit dans une même vue le coût d'affectation du module 1 et, pour le module 2, la
distance, le temps de conduite, le temps de service et le nombre d'arrêts, par entrepôt et pour le
réseau. Il est **recalculé côté serveur** à partir des séquences choisies : on ne fait pas
confiance aux chiffres envoyés par le navigateur, et une tournée qui ne visite pas exactement ses
magasins est refusée. Les plans enregistrés (`sorties/plans/`) alimentent le tableau de
comparaison des scénarios, avec la meilleure valeur de chaque colonne en gras.

### 7.4 Retour vers le module 1 (bonus)

Le module 1 suppose un transport direct : la part transport de c_ij vaut `2 · KPAL · d_i · dist_ij`.
On la compare à un **ordre de grandeur** du coût des tournées :

* ⌈demande de l'entrepôt / 33⌉ rotations par semaine, 33 palettes étant la capacité d'un
  semi-remorque ;
* chaque rotation a la longueur de la tournée choisie ;
* le kilomètre coûte 33 × KPAL TND, soit le coût d'une palette multiplié par 33, c'est-à-dire un
  camion plein.

Le rapport obtenu par entrepôt, borné à [0,5 ; 3], multiplie la part transport de c_ij dans une
**nouvelle instance** (`…-retour1`). Un bouton la rouvre dans le module 1, et le décideur peut
relancer les méthodes avec ces coûts corrigés. **Limite assumée :** c'est une estimation
grossière. En réalité, chaque rotation ne visite pas tous les magasins ; c'est le problème de
tournées de véhicules (VRP), extension facultative du cahier que nous n'avons pas traitée.

---

## 8. Les tableaux de bord

**Tableau de bord 1** (jalon 1, complété), en 4 étapes : Données → Calcul → Comparaison →
Décision. Ajouts de cette étape :

* les tuiles ③ à ⑥ sont actives ;
* la limite de temps et la graine sont réglables ;
* la garantie de chaque solution est affichée (prouvé / borne / sans garantie) ;
* un lien mène vers le module 2 après validation ;
* le module 1 s'ouvre directement sur une instance corrigée (`?instance=…`).

**Tableau de bord 2** (nouveau), en 4 étapes :

1. **Scénario** : liste des fichiers d'échange (ou dépôt d'un fichier) ; chiffres clés ; nombre
   de magasins par tournée.
2. **Calcul** : choix des méthodes à superposer, limite par tournée, graine ; progression avec
   bouton « Arrêter » ; grille entrepôt × méthode montrant ✓ calculé / ↺ repris du cache, et
   « front complet / partiel » pour la méthode exacte.
3. **Front de Pareto** :
   * un onglet par entrepôt ;
   * graphique distance / temps, chaque méthode avec sa forme et sa couleur, front de référence
     en pointillé ;
   * **clic sur un point**, qui affiche la tournée sur la carte (arrêts numérotés) et la
     séquence ;
   * tableau des indicateurs de qualité ;
   * curseur de préférence « plus rapide ↔ plus courte » appliqué à toutes les tournées.
4. **Plan final** : indicateurs consolidés, synthèse par entrepôt et totaux réseau, carte de
   toutes les tournées, enregistrement, export Excel (3 feuilles) et CSV (une ligne par arrêt),
   comparaison des scénarios, révision de l'affectation, retour vers le module 1.

Même charte que le module 1 : tout centré, couleur réservée aux données et aux éléments
cliquables, chiffres en police à chasse fixe. Le parcours complet (module 1 → validation →
module 2 → plan → export → retour) a été vérifié dans Edge sans interface, avec captures d'écran,
en largeur bureau et en largeur téléphone (390 px). C'est cette vérification qui a révélé que la
carte du réseau restait vide : Leaflet gardait une référence vers un conteneur remplacé lors d'un
nouvel affichage. Le défaut est corrigé.

---

## 9. Expérimentation

Protocole écrit **avant** les exécutions : `experimentation/PROTOCOLE.md`. Résultats bruts (CSV),
synthèses et figures : `experimentation/resultats/`. Machine : Intel 16 cœurs logiques, Windows,
Python 3.11. Les exécutions tournent à 8 en parallèle, une par processus. Les temps sont donc un
peu plus longs que pour un calcul seul dans l'outil.

### 9.1 Réglage des paramètres (Q4) — `resultats/reglage.md`

**Recuits** sur TN-M, 5 graines, grille p0 × budget. Écart moyen à l'optimum (GAP ; SSCFLP) :

| | p0 = 0,5 | p0 = 0,2 | p0 = 0,05 |
|---|---|---|---|
| ⑤ budget 2 000·m·n | 0,41 % ; 0,72 % | 0,46 % ; 0,71 % | 0,76 % ; 0,83 % |
| ⑤ budget 5 000·m·n | **0,06 % ; 0,39 %** | 0,55 % ; 0,48 % | 0,71 % ; 0,42 % |
| ⑥ budget 2 000·m·n | 1,71 % ; 0,99 % | 0,92 % ; 0,85 % | **0,45 % ; 0,73 %** |
| ⑥ budget 5 000·m·n | 1,00 % ; 0,70 % | 1,68 % ; 0,62 % | 0,56 % ; 0,83 % |

**Décision** (critère du protocole : meilleur écart moyen sur les deux modèles) : ⑤ avec p0 = 0,5
et 5 000·m·n ; ⑥ avec p0 = 0,05 et 2 000·m·n.

**Lecture.** Le budget compte davantage que p0. Avec 5 graines, les différences de moins
d'environ 0,5 point restent dans le bruit : c'est pourquoi la campagne utilise 10 graines.

**NSGA-II**, 1 000 générations, 5 graines. Hypervolume relatif (kroAB25 ; tournée E01 de TN-L) :

| | p_mut 0,1 | 0,3 | 0,6 |
|---|---|---|---|
| population 50 | 93,6 % ; 85,8 % | 96,5 % ; 84,8 % | 97,1 % ; 84,6 % |
| population 100 | 96,5 % ; 80,8 % | 98,1 % ; 80,8 % | **98,7 % ; 83,4 %** |
| population 200 | 98,7 % ; 80,7 % | 99,1 % ; 81,0 % | 99,5 % ; 81,0 % |

**Décision :** population 100 et p_mut = 0,6, la meilleure moyenne. La population 200 gagne sur
kroAB mais coûte 2,5 fois plus de temps. Une forte mutation aide, car l'inversion est un
mouvement 2-opt aléatoire. Les paramètres retenus sont les valeurs par défaut du code. La campagne
a été **relancée** après ce réglage, pour respecter le protocole.

### 9.2 Module 1 (Q1, Q2) — `resultats/module1.md`

12 combinaisons instance × modèle : Tunisie S, M, L en GAP et en SSCFLP, et OR-Library 16 × 50,
25 × 50, 50 × 50 avec deux coûts fixes. Soit 396 exécutions. Synthèse :

| Méthode | Écart moyen (Tunisie / OR-Lib) | Écart max | Optimum atteint | Optimum prouvé | Temps moyen (Tunisie / OR-Lib) |
|---|---|---|---|---|---|
| ① Cut-and-solve | 0 % / 0 % | 0 % | 12 / 12 | 12 / 12 | 13 s / 6 s |
| ② Branch-and-price | 0,87 % / 0 % | 3,29 % | 9 / 12 | 9 / 12 | 50 s / 13 s |
| ③ Matheuristique LNS | 0,07 % / 0 % | 2,86 % | 107 / 120 | — | 4,9 s / 2,1 s |
| ④ Kernel Search | 0 % / 0 % | 0 % | 12 / 12 | 6 / 12 | 0,6 s / 0,3 s |
| ⑤ Recuit · pénalité | 0,15 % / 0,004 % | 1,63 % | 78 / 120 | — | 9 s / 19 s |
| ⑥ Recuit · réparation | 0,31 % / 0 % | 1,92 % | 80 / 120 | — | 15 s / 36 s |

**Ce qu'on en retient :**

* **① cut-and-solve prouve l'optimum partout**, en 1 à 33 s. C'est la méthode de certification.
* **② branch-and-price** prouve l'optimum sur OR-Library et sur les petites instances. Il atteint
  la limite de temps sur les instances tunisiennes à capacités tendues (remplissage de 74 à
  82 %) : 3,29 % d'écart sur TN-M SSCFLP en 60 s. Interprétation : quand les capacités lient,
  les colonnes (groupes de magasins) se combinent de façon très fractionnaire, l'arbre de
  branchement s'allonge, et la stabilisation ne suffit pas. Sur OR-Library (capacités non
  liantes), le pricing devient trivial et la borne est serrée.
* **④ Kernel Search est la meilleure méthode approchée** : optimum sur les 12 combinaisons, en
  moins de 2 s. Il le **prouve** sur OR-Library, où sa borne LP est serrée, mais pas sur la
  Tunisie : la borne LP y reste en dessous de l'optimum, donc l'interface affiche « écart à la
  borne LP ».
* **③** atteint l'optimum dans 107 exécutions sur 120. La seule mauvaise exécution (2,86 %) est
  le piège de structure d'ouverture du §5.6, évité par 9 graines sur 10.
* **⑤ pénalité contre ⑥ réparation** (Q2, stabilité) : sur les capacités tendues, la pénalité est
  meilleure (0,15 % contre 0,31 % en moyenne) et plus rapide. Quand on interdit l'irréalisable,
  l'espace de recherche se fragmente, et ⑥ doit passer par ses grands mouvements *vider /
  remplir*, plus coûteux (O(n·m)). Quand les capacités ne lient pas (OR-Library), les deux sont à
  l'optimum. Les écarts-types restent sous 0,5 point, sauf TN-M SSCFLP (structure d'ouverture).
* **Pour le décideur :** ④ pour un usage courant (instantané et optimal sur nos instances), ①
  pour certifier, et un recuit quand aucun solveur MIP n'est disponible.

Figures : `module1_ecarts_boxplot.png` (dispersion sur 10 graines), `module1_temps.png`
(temps, échelle logarithmique).

### 9.3 Module 2 (Q3) — `resultats/module2.md`

16 instances, soit 352 exécutions :

* kroAB 15, 25 et 40 nœuds (TSPLIB) ;
* 13 tournées réelles, issues des affectations optimales de TN-M et TN-L (6 à 31 magasins).

Synthèse :

| Instances | Méthode | HV relatif | IGD | Points de la référence retrouvés | Temps |
|---|---|---|---|---|---|
| kroAB | Somme pondérée | 97,4 % | 0,039 | 13 % | 0,6 s |
| kroAB | NSGA-II | 97,5 % | 0,017 | 39 % | 19,6 s |
| kroAB | **2PPLS** | **99,9 %** | **0,002** | 78 % | 1,9 s |
| kroAB | ε-contrainte | 90,8 % | 0,059 | 82 % | 281 s |
| Tunisie | Somme pondérée | 83,5 % | 0,234 | 35 % | 0,3 s |
| Tunisie | NSGA-II | 90,1 % | 0,110 | 74 % | 18,4 s |
| Tunisie | 2PPLS | 93,0 % | 0,085 | 76 % | 0,1 s |
| Tunisie | **ε-contrainte** | **100 %** | **0** | **100 %** | 3,5 s |

**Ce qu'on en retient :**

* **L'ε-contrainte est exacte et complète sur 15 instances sur 16.** Toutes les tournées réelles
  sont résolues en 0 à 15 s, et kroAB25 (220 points de Pareto) en 225 s. Seul kroAB40 est
  partiel après 600 s : 72 % de l'hypervolume. Avec deux objectifs indépendants, le front a des
  centaines de points et il faut deux MIP par point. C'est la limite « petites instances » prévue
  par le cahier.
* **2PPLS est la meilleure méthode approchée** : 99,9 % de l'hypervolume sur kroAB en moins de
  2 s, et c'est elle qui fournit l'essentiel de la référence sur kroAB40.
* **NSGA-II** est bon jusqu'à environ 20 magasins (99 à 100 %), mais se dégrade au-delà de 25
  (E01 : 82 % ; E03 : 72 %) malgré 1 000 générations. Sans recherche locale, le croisement OX
  détruit les bonnes sous-séquences ; c'est connu dans la littérature.
* **La somme pondérée** est très rapide mais trouve peu de points (ceux de l'enveloppe convexe),
  ce qu'on attendait (§6.2).
* **Un phénomène instructif** (figure `fronts_TN-L-E01.png`) : sur E01, E02 et E03, les trois
  méthodes approchées restent toutes dans la **même** région du front. Les tournées les plus
  rapides ont une structure que les mouvements 2-opt / Or-opt n'atteignent pas depuis leurs
  points de départ ; seule la méthode exacte les trouve. C'est ce qui justifie de garder la
  référence exacte dans l'outil : le compromis par défaut est choisi sur le front de référence,
  toutes méthodes confondues.
* **Prudence sur l'hypervolume** : sur un front très étroit (E02, 3 points), la normalisation
  amplifie de petites différences (NSGA-II : 22 % ± 30 %). L'IGD et la part de points retrouvés
  complètent la lecture.

Figures : `fronts_kroAB15/25/40.png`, `fronts_TN-L-E01.png`, `fronts_TN-L-E06.png`,
`module2_hv_boxplot.png`.

### 9.4 Réponses courtes aux questions du protocole

* **Q1.** ① et ④ (④ en pratique) sont optimaux et rapides jusqu'à 10 × 200 ; ② ne tient pas la
  limite de temps sur les capacités tendues ; ⑤ et ⑥ restent à 0,15 % et 0,31 % en moyenne sur les instances tunisiennes (au pire 1,9 %).
* **Q2.** Les méthodes stochastiques sont stables (écart-type < 0,5 point), sauf un piège de
  structure d'ouverture sur TN-M SSCFLP.
* **Q3.** Le front exact est accessible jusqu'à environ 30 magasins par tournée. Au-delà,
  2PPLS ; NSGA-II pur est à éviter au-delà de 25 magasins.
* **Q4.** Les réglages retenus sont ci-dessus ; le budget d'itérations compte plus que la
  température initiale.

---

## 10. Tests et vérifications

`python -m pytest` lance 73 tests en environ une minute. Grâce à `tests/conftest.py`, ils écrivent
dans un dossier temporaire, jamais dans `sorties/`.

| Fichier | Ce qui est vérifié |
|---|---|
| `test_tableau_bord.py` (35) | une règle de lecture automatique par test ; chaque indicateur recalculé indépendamment ; titres-conclusions (dont « optimum » seulement si prouvé) ; **les 6 méthodes × GAP / SSCFLP retrouvent l'optimum de référence par l'API** ; arrêt d'un calcul ; validation refusée si une capacité est dépassée ; contenu du fichier d'échange |
| `test_module1_heuristiques.py` (19) | exemple du document (19 en SSCFLP, 6 en GAP) ; capacités respectées ; jamais mieux que l'optimum, à moins de 2 % de lui ; **même graine = même résultat** ; borne LP valide ; pénalité utile à 97 % de remplissage ; arrêt immédiat |
| `test_module2.py` (19) | matrices symétriques et objectifs réellement conflictuels ; congestion indépendante du sous-ensemble ; hypervolume, IGD, compromis ; **ε-contrainte = front exact par force brute** (8 magasins) ; tournées valides et fronts mutuellement non dominés pour les 4 méthodes ; aucune heuristique ne « bat » l'exact ; reproductibilité ; lecture de TSPLIB ; **intégration complète** : fichier d'échange → calcul → plan → export CSV / Excel → révision → **seuls les 2 entrepôts concernés recalculés** → refus d'un dépassement de capacité → retour → instance corrigée chargée au module 1 |

---

## 11. Limites, honnêtement

* **Jeu de données Tunisie de substitution.** Le jeu officiel (`rapport_donnees.pdf`) n'était pas
  dans le dépôt ; notre générateur produit le même format. Les coordonnées sont réalistes (villes
  réelles), mais les demandes et les coûts sont simulés.
* **Pas de source C** (données réelles Kaggle / OpenStreetMap / OSRM). Nous utilisons A + B, ce
  qui satisfait le minimum de deux sources. Les temps de trajet sont modélisés, pas issus d'OSRM.
* **NSGA-II pur** converge mal sur les tournées de plus de 25 magasins (72 à 82 % de
  l'hypervolume, §9.3). C'est connu pour les algorithmes génétiques sans recherche locale sur le TSP. Un hybride « mémétique »
  (2-opt sur les enfants) l'améliorerait, mais ne serait plus le NSGA-II du cahier.
* **ε-contrainte** : exact, mais le nombre de points du front peut exploser quand les objectifs
  sont indépendants. Sur kroAB-40, le front n'est que partiel après 600 s.
* **② branch-and-price** ne tient pas la limite de temps sur les capacités tendues (§9.2) ;
  ① et ④ le surpassent sur nos instances.
* **Le retour** (§7.4) est un ordre de grandeur, pas un VRP.
* **Références ③ à ⑥ de la maquette** à vérifier pendant la revue de littérature (§5.7).
* Un seul véhicule par entrepôt, sans capacité (TSP, comme le demande le cahier) : la tournée
  d'un entrepôt de 500 palettes est une tournée « type » répétée, pas un plan de chargement.

---

## 12. Questions probables de l'enseignant et réponses

**« Pourquoi six méthodes au module 1, alors que le cahier en demande trois ? »**
Le cahier demande *au moins* une méthode exacte, une heuristique et une métaheuristique. En faire
deux de chaque famille permet de comparer à l'intérieur d'une famille : deux exactes
(cut-and-solve, à base de plans coupants et de problèmes denses / épars, contre
branch-and-price par décomposition de Dantzig-Wolfe), et surtout deux recuits qui ne diffèrent
que par la gestion des capacités (pénalité contre réparation), ce que le cahier évoque.

**« Comment savez-vous que vos heuristiques sont bonnes ? »**
Parce qu'on connaît l'optimum : références HiGHS pour les instances Tunisie, optima publiés et
revérifiés pour OR-Library. Les écarts du §9 sont donc des écarts **à l'optimum**, pas à la
meilleure méthode.

**« Votre front de Pareto est-il le vrai ? »**
Pour les tournées réelles (jusqu'à 31 magasins), oui : l'ε-contrainte exacte termine (« front
complet ») et un test vérifie qu'elle donne le même front qu'une énumération exhaustive. Les trois
autres méthodes sont jugées par rapport à lui.

**« Pourquoi la somme pondérée trouve-t-elle si peu de points ? »**
Elle ne peut trouver que les points supportés, sur l'enveloppe convexe. C'est une limite
théorique, pas un défaut d'implémentation. 2PPLS commence d'ailleurs par ces points (phase 1),
puis complète les parties non convexes (phase 2).

**« Que se passe-t-il si je modifie l'affectation ? »**
Démonstration : déplacer un magasin dans le tableau de bord 2. Un scénario dérivé est créé et
seules deux tournées sont recalculées ; la grille l'affiche avec ✓ et ↺.

**« Les temps sont-ils comparables entre méthodes ? »**
Un seul calcul à la fois sur le serveur ; temps réels (`perf_counter`). Pendant la campagne, des
exécutions tournent en parallèle sur des cœurs distincts (méthode notée dans
`resultats/machine.json`). Les métaheuristiques s'arrêtent sur un budget d'itérations, donc leur
qualité ne dépend pas de la vitesse de la machine.

**« Pourquoi le recuit ⑤ a-t-il un mouvement “basculer” ? N'est-ce pas tricher ? »**
Non : c'est un voisinage de plus. Sans lui, nous avons **mesuré** que le recuit ne quittait jamais
la structure d'ouverture initiale (§5.6). Le mouvement reste géré par pénalité, ce qui garde la
différence avec ⑥.

---

## 13. Déroulé de la démonstration

1. `uvicorn backend.app:app --port 8000`, puis ouvrir http://localhost:8000.
2. **Module 1**, jeu « Moyen 5 × 50 », SSCFLP :
   * lancer ① puis ③ ④ ⑤ ⑥ (environ 30 s au total) ;
   * montrer le titre-conclusion, le tableau des 6 indicateurs (garanties), la carte et les
     charges.
3. Décision : choisir ④ ; ajuster un magasin (montrer le blocage si une capacité est dépassée) ;
   **Valider et transmettre** ; ouvrir le module 2.
4. **Module 2** :
   * calculer les 4 méthodes (limite 10 s) ;
   * dans l'onglet d'un entrepôt, montrer le front et la référence exacte, cliquer un point
     (tournée sur la carte), puis bouger le curseur de préférence.
5. **Plan final** : indicateurs consolidés ; enregistrer ; exporter en Excel.
6. **Intégration** :
   * réviser l'affectation (déplacer un magasin) : seules 2 tournées sont recalculées ;
   * enregistrer, puis comparer les deux scénarios.
7. **Bonus** : retour vers le module 1, avec l'instance corrigée ouverte au module 1.
8. Finir sur les résultats d'expérimentation (`experimentation/resultats/`).
