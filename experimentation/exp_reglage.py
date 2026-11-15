# -*- coding: utf-8 -*-
"""Q4 du protocole : reglage des parametres des recuits (⑤ ⑥) et de NSGA-II.
Usage : python experimentation/exp_reglage.py"""
from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from commun import NB_PROCESSUS, RACINE, RESULTATS, ecrire_csv, fr, sauver_machine, table_md

P0 = (0.5, 0.2, 0.05)
BUDGETS = (500, 2000, 5000)
POPS = (50, 100, 200)
PMS = (0.1, 0.3, 0.6)
GRAINES = range(5)


def _tn(taille, modele):
    from backend import donnees
    from backend.methodes import _instance_m1
    di = donnees.charger_fichier(donnees.chemin_exemple(taille))
    return _instance_m1(di, modele), di.reference(modele)["cout"]


def tache_recuit(args):
    meth, modele, p0, budget, graine = args
    import module1_heuristiques as mh
    inst, ref = _tn("M", modele)
    fn = mh.recuit_simule_penalite if meth == "m1" else mh.recuit_multi_voisinages
    t0 = time.perf_counter()
    sol = fn(inst, time_limit=600, seed=graine, p0=p0, iterations=budget * inst.m * inst.n)
    return {"methode": meth, "modele": modele, "p0": p0, "budget_par_paire": budget, "graine": graine,
            "ecart": (sol.value - ref) / ref, "temps_s": time.perf_counter() - t0}


def _tournee(nom):
    import module2_tournees as m2
    if nom == "kroAB25":
        t = RACINE / "donnees_benchmarks" / "tsplib"
        return m2.instance_kroab(t / "kroA100.tsp", t / "kroB100.tsp", 25)
    from exp_module2 import tournees_tunisie
    return tournees_tunisie("L")["TN-L-E01"]


def tache_nsga(args):
    nom, pop, pm, graine = args
    import module2_tournees as m2
    D, T = _tournee(nom)
    t0 = time.perf_counter()
    r = m2.nsga2(D, T, taille_pop=pop, p_mutation=pm, generations=1000, seed=graine, time_limit=600)
    return {"instance": nom, "pop": pop, "p_mutation": pm, "graine": graine, "temps_s": time.perf_counter() - t0,
            "front": [(s["f1"], s["f2"]) for s in r["solutions"]]}


def main():
    sauver_machine()
    t0 = time.time()
    taches_r = [(me, mo, p0, b, g) for me in ("m1", "m2") for mo in ("gap", "sscflp") for p0 in P0 for b in BUDGETS for g in GRAINES]
    taches_n = [(nom, pop, pm, g) for nom in ("kroAB25", "TN-L-E01") for pop in POPS for pm in PMS for g in GRAINES]
    with ProcessPoolExecutor(NB_PROCESSUS) as ex:
        rec = list(ex.map(tache_recuit, taches_r))
        print(f"recuits : {len(rec)} executions en {time.time() - t0:.0f} s", flush=True)
        nsg = list(ex.map(tache_nsga, taches_n))
    print(f"NSGA-II : {len(nsg)} executions, total {time.time() - t0:.0f} s", flush=True)
    ecrire_csv(RESULTATS / "reglage_recuits.csv", rec)

    # hypervolume relatif de chaque front NSGA-II, rapporte a l'union de toutes les executions
    import module2_tournees as m2
    from exp_module2 import hv_relatif
    lignes_n = []
    for nom in ("kroAB25", "TN-L-E01"):
        runs = [r for r in nsg if r["instance"] == nom]
        union = [p for r in runs for p in r["front"]]
        ref = [union[i] for i in m2.non_domines(union)]
        for r in runs:
            lignes_n.append({k: r[k] for k in ("instance", "pop", "p_mutation", "graine", "temps_s")} |
                            {"hv_relatif": hv_relatif(r["front"], ref), "points": len(r["front"])})
    ecrire_csv(RESULTATS / "reglage_nsga2.csv", lignes_n)

    md = ["# Réglage des paramètres (Q4)", "",
          "Généré par `exp_reglage.py`. Recuits : TN-M, 5 graines ; écart moyen à l'optimum HiGHS. "
          "NSGA-II : 1000 générations, 5 graines ; hypervolume relatif à l'union non dominée de toutes les exécutions.", ""]
    for meth, nom in (("m1", "⑤ Recuit simulé · pénalité"), ("m2", "⑥ Recuit multi-voisinages · réparation")):
        for modele in ("gap", "sscflp"):
            lignes = []
            for p0 in P0:
                lig = [fr(p0, 2)]
                for b in BUDGETS:
                    x = [r for r in rec if r["methode"] == meth and r["modele"] == modele and r["p0"] == p0 and r["budget_par_paire"] == b]
                    lig.append(f"{fr(100 * np.mean([r['ecart'] for r in x]), 3)} % ({fr(np.mean([r['temps_s'] for r in x]), 1)} s)")
                lignes.append(lig)
            md += [f"## {nom} — {modele.upper()}", "", table_md(["p0 \\ budget (× m n)"] + [str(b) for b in BUDGETS], lignes), ""]
    for nom in ("kroAB25", "TN-L-E01"):
        lignes = []
        for pop in POPS:
            lig = [str(pop)]
            for pm in PMS:
                x = [r for r in lignes_n if r["instance"] == nom and r["pop"] == pop and r["p_mutation"] == pm]
                lig.append(f"{fr(100 * np.mean([r['hv_relatif'] for r in x]), 1)} % ({fr(np.mean([r['temps_s'] for r in x]), 1)} s)")
            lignes.append(lig)
        md += [f"## NSGA-II — {nom}", "", table_md(["population \\ p_mutation"] + [fr(p, 1) for p in PMS], lignes), ""]
    (RESULTATS / "reglage.md").write_text("\n".join(md), encoding="utf-8")
    print("ecrit", RESULTATS / "reglage.md")


if __name__ == "__main__":
    main()
