# -*- coding: utf-8 -*-
"""Lecteurs des benchmarks (source A du cahier des charges) et solutions de reference.

OR-Library (Beasley 1990), localisation avec capacites « cap41 ... cap134 » :
    m n
    pour chaque entrepot i : capacite  cout_fixe
    pour chaque magasin j  : demande  puis m couts (cout d'affecter TOUTE la demande de j a i)
Ce sont des instances du CFLP (approvisionnement multiple). En source unique :
  - cap41 a cap64 sont INFAISABLES (un client demande 12 912 > capacite 5 000, 7 500...) ;
  - cap71 a cap134 ont des capacites egales a la demande totale : la contrainte de capacite ne lie
    jamais, l'optimum CFLP affecte chaque client a l'entrepot ouvert le moins cher, il est donc
    mono-source : les optima publies (capopt.txt) sont aussi les optima SSCFLP. On les verifie
    par HiGHS (references_sscflp.json). Ces instances testent la decision d'OUVERTURE (16, 25, 50
    entrepots), nos instances Tunisie testent les capacites tendues.

TSPLIB (Reinelt 1991) kroA100 / kroB100 : voir module2_tournees.instance_kroab."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ICI = Path(__file__).resolve().parent
RACINE = ICI.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

import module1_methods as m1  # noqa: E402

ORLIB = ICI / "orlib"
TSPLIB = ICI / "tsplib"
FICHIER_REFERENCES = ORLIB / "references_sscflp.json"


def lire_cap(nom: str) -> m1.Instance:
    """Instance OR-Library capXX -> module1_methods.Instance (c[i, j] entrepot x magasin)."""
    jetons = (ORLIB / f"{nom}.txt").read_text().split()
    pos = 0

    def lire():
        nonlocal pos
        pos += 1
        return jetons[pos - 1]

    m, n = int(lire()), int(lire())
    s, f = np.zeros(m), np.zeros(m)
    for i in range(m):
        s[i], f[i] = float(lire()), float(lire())
    d, c = np.zeros(n), np.zeros((m, n))
    for j in range(n):
        d[j] = float(lire())
        for i in range(m):
            c[i, j] = float(lire())
    return m1.Instance(c=c, d=d, s=s, f=f, name=nom)


INSTANCES_CAP = ("cap71", "cap74", "cap101", "cap104", "cap131", "cap134")


def optima_publies():
    out = {}
    for ligne in (ORLIB / "capopt.txt").read_text().splitlines()[1:]:
        x = ligne.split()
        if len(x) == 2:
            out[x[0]] = float(x[1])
    return out


def references_sscflp(noms=INSTANCES_CAP, time_limit=600):
    """Optimum SSCFLP de chaque instance par HiGHS (calcule une fois, puis lu dans le fichier)."""
    refs = json.loads(FICHIER_REFERENCES.read_text()) if FICHIER_REFERENCES.exists() else {}
    manquants = [x for x in noms if x not in refs]
    if manquants:
        sys.path.insert(0, str(RACINE / "donnees_tunisie"))
        from generer_instances import resoudre_reference
        for nom in manquants:
            inst = lire_cap(nom)
            cout, a, statut = resoudre_reference(inst.c.T, inst.d, inst.s, inst.f, True, time_limit)
            refs[nom] = {"cout": round(cout, 3), "statut": statut, "solveur": "HiGHS", "m": inst.m, "n": inst.n,
                         "ouverts": sorted({int(i) for i in a}), "optimum_publie": optima_publies().get(nom)}
            FICHIER_REFERENCES.write_text(json.dumps(refs, indent=1))
    return refs


if __name__ == "__main__":
    for nom, r in references_sscflp().items():
        inst = lire_cap(nom)
        print(nom, f"{inst.m} x {inst.n}", "remplissage", round(inst.d.sum() / inst.s.sum(), 3), r)
