# Module 1 — qualité et temps de réponse (Q1, Q2)

Généré par `exp_module1.py`. Écart à l'optimum de référence (HiGHS ; optima publiés pour OR-Library). Méthodes stochastiques ③ ⑤ ⑥ : 10 graines, « moyenne (min – max) ». ✓ = optimalité prouvée par la méthode.

## Écart à l'optimum

| Instance | Modèle | m × n | Limite | ① Cut-and-solve | ② Branch-and-price | ③ Matheuristique LNS | ④ Kernel Search | ⑤ Recuit · pénalité | ⑥ Recuit · réparation |
|---|---|---|---|---|---|---|---|---|---|
| TN-S | GAP | 3 × 20 | 30 s | 0,00 % ✓ | 0,00 % ✓ | 0,00 % (0,00 – 0,00) | 0,00 % | 0,00 % (0,00 – 0,00) | 0,00 % (0,00 – 0,00) |
| TN-S | SSCFLP | 3 × 20 | 30 s | 0,00 % ✓ | 0,00 % ✓ | 0,00 % (0,00 – 0,00) | 0,00 % | 0,00 % (0,00 – 0,00) | 0,00 % (0,00 – 0,00) |
| TN-M | GAP | 5 × 50 | 60 s | 0,00 % ✓ | 0,07 % | 0,10 % (0,00 – 0,14) | 0,00 % | 0,10 % (0,00 – 0,30) | 0,41 % (0,29 – 0,64) |
| TN-M | SSCFLP | 5 × 50 | 60 s | 0,00 % ✓ | 3,29 % | 0,31 % (0,00 – 2,86) | 0,00 % | 0,49 % (0,16 – 1,63) | 0,82 % (0,17 – 1,92) |
| TN-L | GAP | 10 × 200 | 120 s | 0,00 % ✓ | 0,00 % ✓ | 0,01 % (0,00 – 0,07) | 0,00 % | 0,16 % (0,05 – 0,37) | 0,29 % (0,14 – 0,43) |
| TN-L | SSCFLP | 10 × 200 | 120 s | 0,00 % ✓ | 1,85 % | 0,00 % (0,00 – 0,01) | 0,00 % | 0,12 % (0,03 – 0,45) | 0,32 % (0,12 – 0,74) |
| cap71 | SSCFLP | 16 × 50 | 60 s | 0,00 % ✓ | 0,00 % ✓ | 0,00 % (0,00 – 0,00) | 0,00 % ✓ | 0,00 % (0,00 – 0,00) | 0,00 % (0,00 – 0,00) |
| cap74 | SSCFLP | 16 × 50 | 60 s | 0,00 % ✓ | 0,00 % ✓ | 0,00 % (0,00 – 0,00) | 0,00 % ✓ | 0,00 % (0,00 – 0,00) | 0,00 % (0,00 – 0,00) |
| cap101 | SSCFLP | 25 × 50 | 60 s | 0,00 % ✓ | 0,00 % ✓ | 0,00 % (0,00 – 0,00) | 0,00 % ✓ | 0,00 % (0,00 – 0,00) | 0,00 % (0,00 – 0,00) |
| cap104 | SSCFLP | 25 × 50 | 60 s | 0,00 % ✓ | 0,00 % ✓ | 0,00 % (0,00 – 0,00) | 0,00 % ✓ | 0,00 % (0,00 – 0,00) | 0,00 % (0,00 – 0,00) |
| cap131 | SSCFLP | 50 × 50 | 120 s | 0,00 % ✓ | 0,00 % ✓ | 0,00 % (0,00 – 0,00) | 0,00 % ✓ | 0,02 % (0,00 – 0,09) | 0,00 % (0,00 – 0,00) |
| cap134 | SSCFLP | 50 × 50 | 120 s | 0,00 % ✓ | 0,00 % ✓ | 0,00 % (0,00 – 0,00) | 0,00 % ✓ | 0,01 % (0,00 – 0,06) | 0,00 % (0,00 – 0,00) |

## Temps de réponse moyen

| Instance | Modèle | m × n | Limite | ① Cut-and-solve | ② Branch-and-price | ③ Matheuristique LNS | ④ Kernel Search | ⑤ Recuit · pénalité | ⑥ Recuit · réparation |
|---|---|---|---|---|---|---|---|---|---|
| TN-S | GAP | 3 × 20 | 30 s | 1,19 s | 0,03 s | 0,54 s | 0,03 s | 1,25 s | 0,59 s |
| TN-S | SSCFLP | 3 × 20 | 30 s | 1,45 s | 2,72 s | 0,56 s | 0,06 s | 1,42 s | 0,66 s |
| TN-M | GAP | 5 × 50 | 60 s | 11,46 s | 60,01 s | 4,32 s | 0,70 s | 6,06 s | 3,28 s |
| TN-M | SSCFLP | 5 × 50 | 60 s | 13,83 s | 60,04 s | 7,33 s | 0,56 s | 7,25 s | 5,24 s |
| TN-L | GAP | 10 × 200 | 120 s | 16,52 s | 56,14 s | 6,67 s | 0,52 s | 16,48 s | 28,55 s |
| TN-L | SSCFLP | 10 × 200 | 120 s | 32,96 s | 120,33 s | 9,95 s | 1,78 s | 23,74 s | 54,16 s |
| cap71 | SSCFLP | 16 × 50 | 60 s | 3,60 s | 2,39 s | 1,88 s | 0,30 s | 18,83 s | 17,26 s |
| cap74 | SSCFLP | 16 × 50 | 60 s | 3,41 s | 18,04 s | 1,67 s | 0,20 s | 18,35 s | 23,64 s |
| cap101 | SSCFLP | 25 × 50 | 60 s | 5,49 s | 2,63 s | 2,43 s | 0,40 s | 19,08 s | 27,47 s |
| cap104 | SSCFLP | 25 × 50 | 60 s | 5,13 s | 26,35 s | 1,58 s | 0,21 s | 18,32 s | 42,18 s |
| cap131 | SSCFLP | 50 × 50 | 120 s | 10,42 s | 4,90 s | 3,12 s | 0,52 s | 19,56 s | 40,62 s |
| cap134 | SSCFLP | 50 × 50 | 120 s | 8,81 s | 20,69 s | 2,16 s | 0,31 s | 18,35 s | 65,80 s |

## Synthèse par méthode

| Méthode | Instances | Écart moyen | Écart max | Optimum atteint | Optimum prouvé | Temps moyen |
|---|---|---|---|---|---|---|
| ① Cut-and-solve | Tunisie | 0,000 % | 0,00 % | 6/6 | 6/6 | 12,90 s |
| ① Cut-and-solve | OR-Library | 0,000 % | 0,00 % | 6/6 | 6/6 | 6,14 s |
| ② Branch-and-price | Tunisie | 0,868 % | 3,29 % | 3/6 | 3/6 | 49,88 s |
| ② Branch-and-price | OR-Library | 0,000 % | 0,00 % | 6/6 | 6/6 | 12,50 s |
| ③ Matheuristique LNS | Tunisie | 0,069 % | 2,86 % | 47/60 | 0/60 | 4,90 s |
| ③ Matheuristique LNS | OR-Library | 0,000 % | 0,00 % | 60/60 | 0/60 | 2,14 s |
| ④ Kernel Search | Tunisie | 0,000 % | 0,00 % | 6/6 | 0/6 | 0,61 s |
| ④ Kernel Search | OR-Library | 0,000 % | 0,00 % | 6/6 | 6/6 | 0,32 s |
| ⑤ Recuit · pénalité | Tunisie | 0,145 % | 1,63 % | 21/60 | 0/60 | 9,37 s |
| ⑤ Recuit · pénalité | OR-Library | 0,004 % | 0,09 % | 57/60 | 0/60 | 18,75 s |
| ⑥ Recuit · réparation | Tunisie | 0,307 % | 1,92 % | 20/60 | 0/60 | 15,41 s |
| ⑥ Recuit · réparation | OR-Library | 0,000 % | 0,00 % | 60/60 | 0/60 | 36,16 s |

## Stabilité des méthodes stochastiques (10 graines, écarts en %)

| Méthode | Instance | Moyenne | Écart-type | Min | Max |
|---|---|---|---|---|---|
| ③ Matheuristique LNS | TN-S GAP | 0,000 | 0,000 | 0,000 | 0,000 |
| ③ Matheuristique LNS | TN-S SSCFLP | 0,000 | 0,000 | 0,000 | 0,000 |
| ③ Matheuristique LNS | TN-M GAP | 0,097 | 0,045 | 0,000 | 0,144 |
| ③ Matheuristique LNS | TN-M SSCFLP | 0,312 | 0,852 | 0,000 | 2,858 |
| ③ Matheuristique LNS | TN-L GAP | 0,007 | 0,021 | 0,000 | 0,069 |
| ③ Matheuristique LNS | TN-L SSCFLP | 0,001 | 0,002 | 0,000 | 0,007 |
| ③ Matheuristique LNS | cap71 SSCFLP | 0,000 | 0,000 | 0,000 | 0,000 |
| ③ Matheuristique LNS | cap74 SSCFLP | 0,000 | 0,000 | 0,000 | 0,000 |
| ③ Matheuristique LNS | cap101 SSCFLP | 0,000 | 0,000 | 0,000 | 0,000 |
| ③ Matheuristique LNS | cap104 SSCFLP | 0,000 | 0,000 | 0,000 | 0,000 |
| ③ Matheuristique LNS | cap131 SSCFLP | 0,000 | 0,000 | 0,000 | 0,000 |
| ③ Matheuristique LNS | cap134 SSCFLP | 0,000 | 0,000 | 0,000 | 0,000 |
| ⑤ Recuit · pénalité | TN-S GAP | 0,000 | 0,000 | 0,000 | 0,000 |
| ⑤ Recuit · pénalité | TN-S SSCFLP | 0,000 | 0,000 | 0,000 | 0,000 |
| ⑤ Recuit · pénalité | TN-M GAP | 0,105 | 0,102 | 0,000 | 0,303 |
| ⑤ Recuit · pénalité | TN-M SSCFLP | 0,490 | 0,422 | 0,164 | 1,628 |
| ⑤ Recuit · pénalité | TN-L GAP | 0,155 | 0,106 | 0,046 | 0,373 |
| ⑤ Recuit · pénalité | TN-L SSCFLP | 0,122 | 0,117 | 0,029 | 0,452 |
| ⑤ Recuit · pénalité | cap71 SSCFLP | 0,000 | 0,000 | 0,000 | 0,000 |
| ⑤ Recuit · pénalité | cap74 SSCFLP | 0,000 | 0,000 | 0,000 | 0,000 |
| ⑤ Recuit · pénalité | cap101 SSCFLP | 0,000 | 0,000 | 0,000 | 0,000 |
| ⑤ Recuit · pénalité | cap104 SSCFLP | 0,000 | 0,000 | 0,000 | 0,000 |
| ⑤ Recuit · pénalité | cap131 SSCFLP | 0,018 | 0,036 | 0,000 | 0,091 |
| ⑤ Recuit · pénalité | cap134 SSCFLP | 0,006 | 0,017 | 0,000 | 0,058 |
| ⑥ Recuit · réparation | TN-S GAP | 0,000 | 0,000 | 0,000 | 0,000 |
| ⑥ Recuit · réparation | TN-S SSCFLP | 0,000 | 0,000 | 0,000 | 0,000 |
| ⑥ Recuit · réparation | TN-M GAP | 0,410 | 0,114 | 0,290 | 0,639 |
| ⑥ Recuit · réparation | TN-M SSCFLP | 0,823 | 0,521 | 0,166 | 1,919 |
| ⑥ Recuit · réparation | TN-L GAP | 0,287 | 0,085 | 0,143 | 0,426 |
| ⑥ Recuit · réparation | TN-L SSCFLP | 0,320 | 0,187 | 0,125 | 0,740 |
| ⑥ Recuit · réparation | cap71 SSCFLP | 0,000 | 0,000 | 0,000 | 0,000 |
| ⑥ Recuit · réparation | cap74 SSCFLP | 0,000 | 0,000 | 0,000 | 0,000 |
| ⑥ Recuit · réparation | cap101 SSCFLP | 0,000 | 0,000 | 0,000 | 0,000 |
| ⑥ Recuit · réparation | cap104 SSCFLP | 0,000 | 0,000 | 0,000 | 0,000 |
| ⑥ Recuit · réparation | cap131 SSCFLP | 0,000 | 0,000 | 0,000 | 0,000 |
| ⑥ Recuit · réparation | cap134 SSCFLP | 0,000 | 0,000 | 0,000 | 0,000 |

Figures : `module1_ecarts_boxplot.png`, `module1_temps.png`.
