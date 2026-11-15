# Module 2 — qualité des fronts de Pareto (Q3)

Généré par `exp_module2.py`. Limite : 60 s par méthode (600 s pour l'ε-contrainte). Méthodes stochastiques : 10 graines (moyenne ± écart-type). Référence : front exact de l'ε-contrainte quand il est complet, sinon union non dominée de toutes les exécutions.

## Hypervolume relatif et temps par instance

| Instance | n | Réf. (points) | Somme pondérée HV | NSGA-II HV | 2PPLS HV | ε-contrainte HV | Somme pondérée temps | NSGA-II temps | 2PPLS temps | ε-contrainte temps |
|---|---|---|---|---|---|---|---|---|---|---|
| kroAB15 | 14 | exact (40) | 98,1 % | 100,0 % ± 0,0 | 99,8 % ± 0,1 | 100,0 % | 0,1 s | 20,1 s | 0,1 s | 18,3 s |
| kroAB25 | 24 | exact (220) | 97,7 % | 98,6 % ± 0,7 | 99,9 % ± 0,0 | 100,0 % | 0,5 s | 19,3 s | 1,2 s | 225,1 s |
| kroAB40 | 39 | union (446) | 96,3 % | 94,0 % ± 1,0 | 99,9 % ± 0,0 | 72,4 % | 1,2 s | 19,5 s | 4,4 s | 600,0 s |
| TN-M-E02 | 6 | exact (2) | 100,0 % | 100,0 % ± 0,0 | 100,0 % ± 0,0 | 100,0 % | 0,0 s | 17,3 s | 0,0 s | 0,0 s |
| TN-M-E03 | 18 | exact (11) | 97,6 % | 99,4 % ± 0,8 | 100,0 % ± 0,0 | 100,0 % | 0,2 s | 18,4 s | 0,1 s | 2,5 s |
| TN-M-E04 | 13 | exact (19) | 89,2 % | 99,9 % ± 0,3 | 97,9 % ± 0,4 | 100,0 % | 0,1 s | 18,1 s | 0,0 s | 1,3 s |
| TN-M-E05 | 13 | exact (8) | 96,9 % | 100,0 % ± 0,0 | 100,0 % ± 0,0 | 100,0 % | 0,1 s | 18,0 s | 0,0 s | 0,6 s |
| TN-L-E01 | 31 | exact (12) | 13,8 % | 82,2 % ± 3,6 | 81,0 % ± 0,0 | 100,0 % | 0,6 s | 18,9 s | 0,1 s | 4,9 s |
| TN-L-E02 | 26 | exact (3) | 45,9 % | 22,5 % ± 29,9 | 45,9 % ± 0,0 | 100,0 % | 0,5 s | 18,5 s | 0,1 s | 1,4 s |
| TN-L-E03 | 28 | exact (9) | 84,0 % | 71,9 % ± 5,3 | 86,9 % ± 0,0 | 100,0 % | 0,5 s | 20,4 s | 0,2 s | 5,1 s |
| TN-L-E04 | 21 | exact (21) | 90,8 % | 97,1 % ± 2,2 | 98,2 % ± 0,0 | 100,0 % | 0,3 s | 19,5 s | 0,1 s | 4,3 s |
| TN-L-E05 | 19 | exact (8) | 97,8 % | 100,0 % ± 0,0 | 100,0 % ± 0,0 | 100,0 % | 0,3 s | 18,3 s | 0,1 s | 1,3 s |
| TN-L-E06 | 25 | exact (41) | 97,0 % | 99,2 % ± 0,5 | 99,7 % ± 0,1 | 100,0 % | 0,4 s | 19,1 s | 0,3 s | 15,1 s |
| TN-L-E08 | 23 | exact (22) | 93,7 % | 98,5 % ± 0,7 | 99,8 % ± 0,1 | 100,0 % | 0,3 s | 18,8 s | 0,2 s | 6,7 s |
| TN-L-E09 | 11 | exact (15) | 89,4 % | 100,0 % ± 0,0 | 100,0 % ± 0,0 | 100,0 % | 0,1 s | 18,0 s | 0,0 s | 1,1 s |
| TN-L-E10 | 16 | exact (6) | 89,4 % | 100,0 % ± 0,0 | 100,0 % ± 0,0 | 100,0 % | 0,1 s | 16,6 s | 0,1 s | 1,0 s |

## Synthèse par famille d'instances

| Instances | Méthode | HV relatif moyen | IGD moyen | Points de la réf. retrouvés | Points | Temps moyen |
|---|---|---|---|---|---|---|
| kroAB (TSPLIB) | Somme pondérée | 97,4 % | 0,039 | 13 % | 15,3 | 0,62 s |
| kroAB (TSPLIB) | NSGA-II | 97,5 % | 0,017 | 39 % | 104,7 | 19,61 s |
| kroAB (TSPLIB) | 2PPLS | 99,9 % | 0,002 | 78 % | 203,2 | 1,92 s |
| kroAB (TSPLIB) | ε-contrainte | 90,8 % | 0,059 | 82 % | 154,3 | 281,13 s |
| Tunisie | Somme pondérée | 83,5 % | 0,234 | 35 % | 4,2 | 0,27 s |
| Tunisie | NSGA-II | 90,1 % | 0,110 | 74 % | 12,0 | 18,44 s |
| Tunisie | 2PPLS | 93,0 % | 0,085 | 76 % | 11,2 | 0,11 s |
| Tunisie | ε-contrainte | 100,0 % | 0,000 | 100 % | 13,6 | 3,49 s |

Figures : `fronts_*.png` (fronts superposés, graine 0) et `module2_hv_boxplot.png`.
