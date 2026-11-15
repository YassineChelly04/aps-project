# Protocole expérimental (T5) — fixé avant les exécutions

Ce protocole a été écrit **avant** de lancer la campagne. Les scripts `exp_module1.py`,
`exp_module2.py` et `exp_reglage.py` l'appliquent tel quel ; les résultats bruts (CSV) et
les synthèses (Markdown, figures) sont écrits dans `experimentation/resultats/`.

## Questions posées

| | Question |
|---|---|
| Q1 | Module 1 : quelle qualité (écart à l'optimum) et quel temps de réponse pour chacune des 6 méthodes, selon la taille et le modèle (GAP / SSCFLP) ? |
| Q2 | Module 1 : les méthodes stochastiques sont-elles stables d'une graine à l'autre ? |
| Q3 | Module 2 : quelle part du front de Pareto exact chaque méthode retrouve-t-elle, et en combien de temps ? |
| Q4 | Réglage : quels paramètres pour les recuits (⑤ ⑥) et pour NSGA-II ? |

## Instances (au moins trois tailles, deux sources)

| Source | Module 1 | Module 2 |
|---|---|---|
| B. Générées (Tunisie, graine 1, ρ = 1,35) | TN-S (3 × 20), TN-M (5 × 50), TN-L (10 × 200), en GAP et en SSCFLP | les tournées issues de l'affectation SSCFLP optimale de TN-M (5 tournées) et de TN-L (9 tournées, 11 à 31 magasins) |
| A. Benchmarks | OR-Library cap71, cap74 (16 × 50), cap101, cap104 (25 × 50), cap131, cap134 (50 × 50) en SSCFLP | TSPLIB kroAB (kroA100 pour la distance, kroB100 pour le temps), 15, 25 et 40 premiers nœuds ; le nœud 1 joue l'entrepôt |

Références : optimum HiGHS (`reference` des instances Tunisie ; `references_sscflp.json`, égal aux
optima publiés d'OR-Library) pour le module 1 ; front exact de l'ε-contrainte quand elle termine
(« complet »), sinon union non dominée de toutes les exécutions, pour le module 2.

## Exécutions

* Méthodes déterministes (①, ②, ④ ; somme pondérée, ε-contrainte) : **1 exécution**.
* Méthodes stochastiques (③, ⑤, ⑥ ; NSGA-II, 2PPLS) : **10 exécutions, graines 0 à 9**.
* Limites de temps, module 1 : 30 s (S), 60 s (M, OR-Library 16 et 25 entrepôts), 120 s (L, OR-Library 50 entrepôts).
  Module 2 : 60 s par méthode et par tournée ; 600 s pour l'ε-contrainte (référence).
* Paramètres : valeurs par défaut du code (celles retenues par `exp_reglage.py`, Q4).
* Machine : celle de l'équipe (processeur, nombre de cœurs et versions notés dans les résultats).
  Les exécutions tournent en parallèle sur des processus séparés (un cœur par exécution, solveurs
  mono-thread) ; les temps sont des temps réels mesurés par `time.perf_counter`.

## Indicateurs

* Module 1 : coût, écart à l'optimum `(coût − optimum) / optimum`, temps de réponse, optimalité
  prouvée ; pour les méthodes stochastiques : moyenne, écart-type, minimum et maximum sur 10 graines.
* Module 2 : nombre de points du front ; **hypervolume relatif** (HV de la méthode / HV de la
  référence, objectifs normalisés sur l'idéal et le nadir de la référence, point de référence
  (1,1 ; 1,1)) ; **IGD** (distance moyenne de la référence au front de la méthode, objectifs
  normalisés) ; part des points de la référence retrouvés ; temps de calcul.

## Réglage (Q4)

* Recuits ⑤ et ⑥ sur TN-M (GAP et SSCFLP), 5 graines : p0 ∈ {0,5 ; 0,2 ; 0,05} × budget ∈ {500, 2000, 5000} × m × n itérations.
* NSGA-II sur la tournée E01 de TN-L (31 magasins) et kroAB-25, 5 graines : taille de population ∈ {50, 100, 200} × probabilité de mutation ∈ {0,1 ; 0,3 ; 0,6}, 1000 générations.
* Critère : écart moyen (recuits), hypervolume relatif moyen (NSGA-II) ; à égalité, le temps.
