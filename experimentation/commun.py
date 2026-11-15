# -*- coding: utf-8 -*-
"""Outils communs aux scripts d'experimentation."""
from __future__ import annotations

import csv
import json
import os
import platform
import sys
from datetime import datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
RESULTATS = Path(__file__).resolve().parent / "resultats"
for p in (RACINE, RACINE / "donnees_benchmarks"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

NB_PROCESSUS = int(os.environ.get("APS_PROCESSUS", "8"))
GRAINES = list(range(10))


def machine() -> dict:
    import numpy, scipy, pulp
    return {"date": datetime.now().isoformat(timespec="seconds"), "os": platform.platform(),
            "processeur": platform.processor(), "coeurs_logiques": os.cpu_count(), "processus_paralleles": NB_PROCESSUS,
            "python": platform.python_version(), "numpy": numpy.__version__, "scipy": scipy.__version__,
            "pulp": pulp.__version__}


def ecrire_csv(chemin: Path, lignes: list[dict]):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    cles = list(dict.fromkeys(k for l in lignes for k in l))
    with open(chemin, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cles, delimiter=";")
        w.writeheader()
        w.writerows(lignes)


def lire_csv(chemin: Path) -> list[dict]:
    with open(chemin, encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter=";"))


def table_md(entete: list[str], lignes: list[list]) -> str:
    out = ["| " + " | ".join(entete) + " |", "|" + "|".join("---" for _ in entete) + "|"]
    out += ["| " + " | ".join(str(x) for x in l) + " |" for l in lignes]
    return "\n".join(out)


def fr(x, d=2):
    """Nombre au format francais (virgule decimale)."""
    if x is None or x == "":
        return "—"
    x = float(x)
    if abs(x) < 0.5 * 10 ** (-d):
        x = 0.0  # evite « -0,00 » (optimum publie arrondi au millieme pres)
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")


def sauver_machine():
    RESULTATS.mkdir(parents=True, exist_ok=True)
    (RESULTATS / "machine.json").write_text(json.dumps(machine(), indent=1), encoding="utf-8")
