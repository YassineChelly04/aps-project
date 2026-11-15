# -*- coding: utf-8 -*-
"""Q1 et Q2 du protocole : les 6 methodes du module 1 sur 3 tailles Tunisie (GAP et SSCFLP) et
6 instances OR-Library (SSCFLP). Usage : python experimentation/exp_module1.py"""
from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from commun import GRAINES, NB_PROCESSUS, RESULTATS, ecrire_csv, fr, sauver_machine, table_md

METHODES = {"cs": "① Cut-and-solve", "bp": "② Branch-and-price", "h1": "③ Matheuristique LNS",
            "h2": "④ Kernel Search", "m1": "⑤ Recuit · pénalité", "m2": "⑥ Recuit · réparation"}
STOCHASTIQUES = ("h1", "m1", "m2")
TN = {"S": 30, "M": 60, "L": 120}
CAP = {"cap71": 60, "cap74": 60, "cap101": 60, "cap104": 60, "cap131": 120, "cap134": 120}


def charger(nom, modele):
    """(instance module1_methods, optimum de reference)."""
    if nom.startswith("TN-"):
        from backend import donnees
        from backend.methodes import _instance_m1
        di = donnees.charger_fichier(donnees.chemin_exemple(nom[3]))
        return _instance_m1(di, modele), di.reference(modele)["cout"]
    from lecteurs import lire_cap, references_sscflp
    return lire_cap(nom), references_sscflp()[nom]["cout"]


def tache(args):
    nom, modele, meth, graine, limite = args
    import module1_heuristiques as mh
    import module1_methods as m1
    inst, ref = charger(nom, modele)
    t0 = time.perf_counter()
    try:
        if meth == "cs":
            sol = m1.gadegaard2018_cut_and_solve(inst, time_limit=limite)
        elif meth == "bp":
            sol = m1.ryu_park2021_branch_and_price(inst, time_limit=limite)
        else:
            kw = {"seed": graine} if meth in STOCHASTIQUES else {}
            sol = mh.METHODES_HEURISTIQUES[meth](inst, time_limit=limite, **kw)
        val, feas = sol.value, sol.feasible
        prouve = bool(sol.proven_optimal or (sol.gap is not None and sol.gap < 1e-9))
        erreur = ""
    except Exception as e:  # une methode qui echoue est notee, la campagne continue
        val, feas, prouve, erreur = float("nan"), False, False, str(e)[:120]
    t = time.perf_counter() - t0
    return {"instance": nom, "modele": modele, "m": inst.m, "n": inst.n, "methode": meth, "graine": graine,
            "limite_s": limite, "cout": val, "reference": ref, "ecart": (val - ref) / ref if feas else float("nan"),
            "realisable": feas, "optimal_prouve": prouve, "temps_s": t, "erreur": erreur}


def main():
    sauver_machine()
    combos = [(f"TN-{t}", mo, lim) for t, lim in TN.items() for mo in ("gap", "sscflp")]
    combos += [(c, "sscflp", lim) for c, lim in CAP.items()]
    taches = []
    for nom, mo, lim in combos:  # exactes d'abord (les plus longues)
        taches += [(nom, mo, k, 0, lim) for k in ("cs", "bp")]
    for nom, mo, lim in combos:
        taches += [(nom, mo, k, g, lim) for k in ("h1", "h2", "m1", "m2") for g in (GRAINES if k in STOCHASTIQUES else [0])]
    t0 = time.time()
    with ProcessPoolExecutor(NB_PROCESSUS) as ex:
        lignes = list(ex.map(tache, taches))
    print(f"{len(lignes)} executions en {time.time() - t0:.0f} s", flush=True)
    ecrire_csv(RESULTATS / "module1_runs.csv", lignes)
    rediger(lignes, combos)


def rediger(lignes, combos):
    md = ["# Module 1 — qualité et temps de réponse (Q1, Q2)", "",
          "Généré par `exp_module1.py`. Écart à l'optimum de référence (HiGHS ; optima publiés pour OR-Library). "
          "Méthodes stochastiques ③ ⑤ ⑥ : 10 graines, « moyenne (min – max) ». ✓ = optimalité prouvée par la méthode.", ""]
    ent = ["Instance", "Modèle", "m × n", "Limite"] + [METHODES[k] for k in METHODES]
    tab_e, tab_t = [], []
    for nom, mo, lim in combos:
        x = [l for l in lignes if l["instance"] == nom and l["modele"] == mo]
        le, lt = [nom, mo.upper(), f"{x[0]['m']} × {x[0]['n']}", f"{lim} s"], [nom, mo.upper(), f"{x[0]['m']} × {x[0]['n']}", f"{lim} s"]
        for k in METHODES:
            v = [l for l in x if l["methode"] == k]
            ec = [100 * l["ecart"] for l in v if l["realisable"]]
            if not ec:
                le.append("échec" if v and v[0]["erreur"] else "—")
            elif len(v) == 1:
                le.append(f"{fr(ec[0], 2)} %" + (" ✓" if v[0]["optimal_prouve"] else ""))
            else:
                le.append(f"{fr(np.mean(ec), 2)} % ({fr(min(ec), 2)} – {fr(max(ec), 2)})")
            lt.append(f"{fr(np.mean([l['temps_s'] for l in v]), 2)} s")
        tab_e.append(le)
        tab_t.append(lt)
    md += ["## Écart à l'optimum", "", table_md(ent, tab_e), "", "## Temps de réponse moyen", "", table_md(ent, tab_t), ""]
    syn = []
    for k in METHODES:
        for groupe, f in (("Tunisie", "TN-"), ("OR-Library", "cap")):
            v = [l for l in lignes if l["methode"] == k and l["instance"].startswith(f)]
            ok = [l for l in v if l["realisable"]]
            syn.append([METHODES[k], groupe, fr(100 * np.mean([l["ecart"] for l in ok]), 3) + " %" if ok else "—",
                        fr(100 * np.max([l["ecart"] for l in ok]), 2) + " %" if ok else "—",
                        f"{sum(1 for l in ok if abs(l['ecart']) < 1e-6)}/{len(v)}",
                        f"{sum(1 for l in v if l['optimal_prouve'])}/{len(v)}", fr(np.mean([l["temps_s"] for l in v]), 2) + " s"])
    md += ["## Synthèse par méthode", "", table_md(["Méthode", "Instances", "Écart moyen", "Écart max", "Optimum atteint",
                                                     "Optimum prouvé", "Temps moyen"], syn), ""]
    stab = []
    for k in STOCHASTIQUES:
        for nom, mo, _ in combos:
            v = [100 * l["ecart"] for l in lignes if l["methode"] == k and l["instance"] == nom and l["modele"] == mo and l["realisable"]]
            if v:
                stab.append([METHODES[k], f"{nom} {mo.upper()}", fr(np.mean(v), 3), fr(np.std(v), 3), fr(min(v), 3), fr(max(v), 3)])
    md += ["## Stabilité des méthodes stochastiques (10 graines, écarts en %)", "",
           table_md(["Méthode", "Instance", "Moyenne", "Écart-type", "Min", "Max"], stab), "",
           "Figures : `module1_ecarts_boxplot.png`, `module1_temps.png`.", ""]
    (RESULTATS / "module1.md").write_text("\n".join(md), encoding="utf-8")
    figures(lignes, combos)
    print("ecrit", RESULTATS / "module1.md")


def figures(lignes, combos):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 4.2))
    etiquettes, donnees_box = [], []
    for nom, mo, _ in combos:
        for k in STOCHASTIQUES:
            v = [100 * l["ecart"] for l in lignes if l["methode"] == k and l["instance"] == nom and l["modele"] == mo and l["realisable"]]
            donnees_box.append(v or [np.nan])
            etiquettes.append(f"{nom[-6:] if nom.startswith('cap') else nom} {mo[:3]} {k}")
    ax.boxplot(donnees_box)
    ax.set_xticks(range(1, len(etiquettes) + 1), etiquettes, rotation=90, fontsize=7)
    ax.set_ylabel("Écart à l'optimum (%)")
    ax.set_title("Méthodes stochastiques (③ h1, ⑤ m1, ⑥ m2) · 10 graines")
    ax.grid(alpha=0.25, axis="y")
    fig.tight_layout()
    fig.savefig(RESULTATS / "module1_ecarts_boxplot.png", dpi=130)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(10, 4.2))
    x = np.arange(len(combos))
    lg = 0.13
    couleurs = ["#2443C4", "#6D4CC2", "#D9822B", "#8A6D1E", "#1E8A6E", "#B8336A"]
    for i, k in enumerate(METHODES):
        t = [np.mean([l["temps_s"] for l in lignes if l["methode"] == k and l["instance"] == nom and l["modele"] == mo]) for nom, mo, _ in combos]
        ax.bar(x + (i - 2.5) * lg, t, lg, label=METHODES[k], color=couleurs[i])
    ax.set_yscale("log")
    ax.set_xticks(x, [f"{n} {m[:3]}" for n, m, _ in combos], rotation=45, fontsize=8)
    ax.set_ylabel("Temps de réponse (s, échelle log)")
    ax.legend(fontsize=7, ncol=3, frameon=False)
    ax.grid(alpha=0.25, axis="y")
    fig.tight_layout()
    fig.savefig(RESULTATS / "module1_temps.png", dpi=130)
    plt.close(fig)


def depuis_csv():
    """Regenere la synthese et les figures a partir de resultats/module1_runs.csv (sans recalcul)."""
    from commun import lire_csv
    lignes = lire_csv(RESULTATS / "module1_runs.csv")
    for l in lignes:
        for k in ("m", "n", "graine", "limite_s"):
            l[k] = int(float(l[k]))
        for k in ("cout", "reference", "ecart", "temps_s"):
            l[k] = float(l[k])
        for k in ("realisable", "optimal_prouve"):
            l[k] = l[k] == "True"
    combos = [(f"TN-{t}", mo, lim) for t, lim in TN.items() for mo in ("gap", "sscflp")]
    combos += [(c, "sscflp", lim) for c, lim in CAP.items()]
    rediger(lignes, combos)


if __name__ == "__main__":
    import sys
    depuis_csv() if "--rediger" in sys.argv else main()
