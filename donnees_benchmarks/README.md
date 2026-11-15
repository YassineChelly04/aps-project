# Jeux de données « benchmarks » (source A du cahier des charges)

Le cahier des charges (§6) demande au moins deux sources parmi A (benchmarks), B (données
générées) et C (données réelles), en documentant pour chacune l'origine, la licence et les
traitements. Ce dossier contient la source **A** ; la source **B** est `donnees_tunisie/`.

## OR-Library — localisation avec capacités (module 1)

| | |
|---|---|
| Origine | J. E. Beasley, *OR-Library*, https://people.brunel.ac.uk/~mastjjb/jeb/orlib/capinfo.html (Beasley 1990, J. Oper. Res. Soc. 41(11):1069-1072) ; instances de Beasley (1988), EJOR 33:314-325 |
| Licence | diffusion libre pour la recherche et l'enseignement (« test data sets for a variety of OR problems ») ; citer Beasley (1990) |
| Fichiers | `orlib/cap71.txt`, `cap74`, `cap101`, `cap104`, `cap131`, `cap134`, `capopt.txt` (optima publiés), téléchargés sans modification |
| Lecture | `lecteurs.py` → `module1_methods.Instance` (c[i, j] = coût d'affecter toute la demande du client j à l'entrepôt i) |

**Traitement et justification du choix des fichiers.** Ce sont des instances du CFLP (un client
peut être servi par plusieurs entrepôts). Notre module 1 impose la **source unique** (SSCFLP) :

* `cap41` à `cap64` sont **infaisables** en source unique : un client demande 12 912 unités alors
  que les capacités valent 5 000 à 7 500 ; nous ne les utilisons donc pas.
* `cap71` à `cap134` ont des capacités égales à la demande totale (58 268) : la contrainte de
  capacité ne lie jamais, et l'optimum CFLP affecte chaque client à l'entrepôt ouvert le moins
  cher. Il est donc mono-source, et l'**optimum publié est aussi l'optimum SSCFLP**. Nous l'avons
  vérifié avec HiGHS (`references_sscflp.json` : les 6 valeurs coïncident à 10⁻³ près).
* Ces instances testent la **décision d'ouverture** sur 16, 25 et 50 entrepôts, avec deux niveaux
  de coût fixe (7 500 pour cap71/101/131 ; 25 000 pour cap74/104/134 : moins d'entrepôts ouverts
  à l'optimum, 4 au lieu de 11 à 15). Les capacités tendues sont testées par nos instances Tunisie (remplissage 74 % à 82 %).
* Il n'y a pas de coordonnées : ces instances servent à l'expérimentation, pas à la carte du tableau de bord.

## TSPLIB — kroA100 / kroB100 (module 2)

| | |
|---|---|
| Origine | G. Reinelt, *TSPLIB*, Université de Heidelberg (Reinelt 1991, ORSA J. Comput. 3(4):376-384) ; copie `https://github.com/mastqe/tsplib` |
| Licence | bibliothèque publique de problèmes de test, libre pour la recherche ; citer Reinelt (1991) |
| Fichiers | `tsplib/kroA100.tsp`, `tsplib/kroB100.tsp`, sans modification |
| Lecture | `module2_tournees.instance_kroab` |

**Traitement.** Instance bi-objectif classique « kroAB » de la littérature (Lust & Teghem 2010) :
mêmes 100 villes, f1 = distance EUC_2D de TSPLIB (arrondi `nint`) sur les coordonnées de kroA100,
f2 = idem sur kroB100. Les deux objectifs sont indépendants, donc très conflictuels (front large).
Pour les trois tailles du protocole, nous gardons les 15, 25 et 40 premiers nœuds ; le nœud 1
joue le rôle de l'entrepôt.

## Pourquoi pas une instance « hybride » ?

Le cahier propose des instances hybrides (coordonnées TSPLIB pour les points de vente, entrepôts
générés). Nous avons préféré garder chaque benchmark **intact**, pour pouvoir comparer nos valeurs
aux références publiées (optima d'OR-Library, front exact de kroAB). Le lien entre les deux modules
est testé sur la source B (Tunisie), qui a des coordonnées géographiques réelles.
