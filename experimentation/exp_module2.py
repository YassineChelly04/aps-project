# -*- coding: utf-8 -*-
"""Q3 du protocole : qualite des fronts de Pareto du module 2.
Usage : python experimentation/exp_module2.py"""
from __future__ import annotations

import json
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from commun import GRAINES, NB_PROCESSUS, RACINE, RESULTATS, ecrire_csv, fr, sauver_machine, table_md

LIMITE = 60
LIMITE_EPS = 600
KRO = (15, 25, 40)
METHODES = {"ws": "Somme pondérée", "nsga": "NSGA-II", "pls": "2PPLS", "eps": "ε-contrainte"}
STOCHASTIQUES = ("nsga", "pls")


def tournees_tunisie(taille):
    """Tournees (matrices D, T) de chaque entrepot dans l'affectation SSCFLP optimale de TN-<taille>."""
    import module2_tournees as m2
    from backend import donnees
    di = donnees.charger_fichier(donnees.chemin_exemple(taille))
    a = di.indices(di.reference("sscflp")["affectation"])
    out = {}
    for j, e in enumerate(di.entrepots):
        idx = np.flatnonzero(a == j)
        if idx.size < 2:
            continue
        ids = [e["id"]] + [di.magasins[i]["id"] for i in idx]
        lat = [e["lat"]] + [di.magasins[i]["lat"] for i in idx]
        lon = [e["lon"]] + [di.magasins[i]["lon"] for i in idx]
        out[f"TN-{taille}-{e['id']}"] = m2.matrices(ids, lat, lon)
    return out


def instances():
    import module2_tournees as m2
    t = RACINE / "donnees_benchmarks" / "tsplib"
    out = {f"kroAB{k}": m2.instance_kroab(t / "kroA100.tsp", t / "kroB100.tsp", k) for k in KRO}
    out.update(tournees_tunisie("M"))
    out.update(tournees_tunisie("L"))
    return out


def hv_relatif(points, ref):
    """Hypervolume du front rapporte a celui de la reference, normalise sur l'ideal / nadir de la
    reference, point de reference (1,1 ; 1,1)."""
    import module2_tournees as m2
    R = np.asarray(ref, float)
    lo, hi = R.min(axis=0), R.max(axis=0)
    e = np.where(hi - lo > 1e-12, hi - lo, 1.0)
    n = lambda P: [tuple((np.asarray(p) - lo) / e) for p in P]
    hr = m2.hypervolume(n(R), (1.1, 1.1))
    return m2.hypervolume(n(points), (1.1, 1.1)) / hr if hr > 0 else 1.0


def igd(points, ref):
    import module2_tournees as m2
    R = np.asarray(ref, float)
    lo, hi = R.min(axis=0), R.max(axis=0)
    e = np.where(hi - lo > 1e-12, hi - lo, 1.0)
    return m2.igd([tuple((np.asarray(p) - lo) / e) for p in points], [tuple((r - lo) / e) for r in R])


_CACHE = {}


def tache(args):
    nom, meth, graine = args
    import module2_tournees as m2
    if not _CACHE:
        _CACHE.update(instances())
    D, T = _CACHE[nom]
    t0 = time.perf_counter()
    r = m2.METHODES_TSP[meth](D, T, time_limit=LIMITE_EPS if meth == "eps" else LIMITE, seed=graine)
    return {"instance": nom, "n": D.shape[0] - 1, "methode": meth, "graine": graine, "temps_s": time.perf_counter() - t0,
            "complet": r["stats"].get("complet"), "front": [(s["f1"], s["f2"]) for s in r["solutions"]]}


def main():
    import module2_tournees as m2
    sauver_machine()
    noms = list(instances())
    taches = [(nom, "eps", 0) for nom in noms]  # les plus longues d'abord
    taches += [(nom, k, g) for nom in noms for k in METHODES if k != "eps" for g in (GRAINES if k in STOCHASTIQUES else [0])]
    t0 = time.time()
    with ProcessPoolExecutor(NB_PROCESSUS) as ex:
        runs = list(ex.map(tache, taches))
    print(f"{len(runs)} executions en {time.time() - t0:.0f} s", flush=True)
    (RESULTATS / "module2_fronts.json").write_text(json.dumps(runs), encoding="utf-8")

    lignes, refs = [], {}
    for nom in noms:
        rs = [r for r in runs if r["instance"] == nom]
        eps = next(r for r in rs if r["methode"] == "eps")
        if eps["complet"]:
            ref, type_ref = eps["front"], "exact"
        else:
            union = [p for r in rs for p in r["front"]]
            ref, type_ref = [union[i] for i in m2.non_domines(union)], "union"
        refs[nom] = (ref, type_ref)
        for r in rs:
            trouves = sum(1 for q in ref if any(abs(q[0] - p[0]) < 1e-6 and abs(q[1] - p[1]) < 1e-6 for p in r["front"]))
            lignes.append({"instance": nom, "n": r["n"], "methode": r["methode"], "graine": r["graine"],
                           "reference": type_ref, "points_reference": len(ref), "points": len(r["front"]),
                           "hv_relatif": hv_relatif(r["front"], ref), "igd": igd(r["front"], ref),
                           "part_reference_trouvee": trouves / len(ref), "temps_s": r["temps_s"], "complet": r["complet"]})
    ecrire_csv(RESULTATS / "module2_runs.csv", lignes)
    rediger(lignes, noms, refs, runs)


def rediger(lignes, noms, refs, runs):
    md = ["# Module 2 — qualité des fronts de Pareto (Q3)", "",
          f"Généré par `exp_module2.py`. Limite : {LIMITE} s par méthode ({LIMITE_EPS} s pour l'ε-contrainte). "
          "Méthodes stochastiques : 10 graines (moyenne ± écart-type). Référence : front exact de l'ε-contrainte "
          "quand il est complet, sinon union non dominée de toutes les exécutions.", ""]
    ent = ["Instance", "n", "Réf. (points)"] + [f"{METHODES[k]} HV" for k in METHODES] + [f"{METHODES[k]} temps" for k in METHODES]
    tab = []
    for nom in noms:
        ref, tr = refs[nom]
        x = [l for l in lignes if l["instance"] == nom]
        lig = [nom, x[0]["n"], f"{tr} ({len(ref)})"]
        for k in METHODES:
            v = [l["hv_relatif"] for l in x if l["methode"] == k]
            lig.append(f"{fr(100 * np.mean(v), 1)} %" + (f" ± {fr(100 * np.std(v), 1)}" if len(v) > 1 else ""))
        for k in METHODES:
            v = [l["temps_s"] for l in x if l["methode"] == k]
            lig.append(f"{fr(np.mean(v), 1)} s")
        tab.append(lig)
    md += ["## Hypervolume relatif et temps par instance", "", table_md(ent, tab), ""]
    agg = []
    for groupe, filtre in (("kroAB (TSPLIB)", "kro"), ("Tunisie", "TN-")):
        for k in METHODES:
            x = [l for l in lignes if l["methode"] == k and l["instance"].startswith(filtre)]
            agg.append([groupe, METHODES[k], fr(100 * np.mean([l["hv_relatif"] for l in x]), 1) + " %",
                        fr(np.mean([l["igd"] for l in x]), 3), fr(100 * np.mean([l["part_reference_trouvee"] for l in x]), 0) + " %",
                        fr(np.mean([l["points"] for l in x]), 1), fr(np.mean([l["temps_s"] for l in x]), 2) + " s"])
    md += ["## Synthèse par famille d'instances", "",
           table_md(["Instances", "Méthode", "HV relatif moyen", "IGD moyen", "Points de la réf. retrouvés", "Points", "Temps moyen"], agg), ""]
    md += ["Figures : `fronts_*.png` (fronts superposés, graine 0) et `module2_hv_boxplot.png`.", ""]
    (RESULTATS / "module2.md").write_text("\n".join(md), encoding="utf-8")
    figures(lignes, noms, refs, runs)
    print("ecrit", RESULTATS / "module2.md")


def figures(lignes, noms, refs, runs):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    style = {"ws": ("s", "#D9822B"), "nsga": ("^", "#1E8A6E"), "pls": ("D", "#B8336A"), "eps": ("o", "#2443C4")}
    for nom in [n for n in noms if n.startswith("kro")] + ["TN-L-E01", "TN-L-E06"]:
        if nom not in refs:
            continue
        fig, ax = plt.subplots(figsize=(6.4, 4.6))
        ref, tr = refs[nom]
        R = sorted(ref)
        ax.step([p[0] for p in R], [p[1] for p in R], where="post", color="#10141C", lw=0.8, ls="--", label=f"référence ({tr})")
        # tailles decroissantes : un point trouve par plusieurs methodes reste visible (marqueurs emboites)
        for k, taille in (("eps", 70), ("pls", 42), ("nsga", 22), ("ws", 9)):
            r = next((r for r in runs if r["instance"] == nom and r["methode"] == k and r["graine"] == 0), None)
            if r:
                ax.scatter([p[0] for p in r["front"]], [p[1] for p in r["front"]], marker=style[k][0], c=style[k][1],
                           s=taille, alpha=0.9, label=METHODES[k], edgecolors="white", linewidths=0.6, zorder=3)
        ax.set_xlabel("f1 : distance" + (" (kroA)" if nom.startswith("kro") else " (km)"))
        ax.set_ylabel("f2 : temps" + (" (kroB)" if nom.startswith("kro") else " de conduite (min)"))
        ax.set_title(f"Fronts de Pareto · {nom}")
        ax.legend(fontsize=8, frameon=False)
        ax.grid(alpha=0.25)
        fig.tight_layout()
        fig.savefig(RESULTATS / f"fronts_{nom}.png", dpi=130)
        plt.close(fig)
    fig, ax = plt.subplots(figsize=(7, 4))
    data = [[100 * l["hv_relatif"] for l in lignes if l["methode"] == k] for k in METHODES]
    ax.boxplot(data, tick_labels=[METHODES[k] for k in METHODES])
    ax.set_ylabel("Hypervolume relatif (%)")
    ax.set_title("Module 2 · toutes instances, toutes graines")
    ax.grid(alpha=0.25, axis="y")
    fig.tight_layout()
    fig.savefig(RESULTATS / "module2_hv_boxplot.png", dpi=130)
    plt.close(fig)


def depuis_fichiers():
    """Regenere synthese et figures depuis module2_fronts.json (sans recalcul)."""
    import json as _json
    import module2_tournees as m2
    runs = _json.loads((RESULTATS / "module2_fronts.json").read_text(encoding="utf-8"))
    for r in runs:
        r["front"] = [tuple(p) for p in r["front"]]
    noms = list(dict.fromkeys(r["instance"] for r in runs))
    lignes, refs = [], {}
    for nom in noms:
        rs = [r for r in runs if r["instance"] == nom]
        eps = next(r for r in rs if r["methode"] == "eps")
        if eps["complet"]:
            ref, type_ref = eps["front"], "exact"
        else:
            union = [p for r in rs for p in r["front"]]
            ref, type_ref = [union[i] for i in m2.non_domines(union)], "union"
        refs[nom] = (ref, type_ref)
        for r in rs:
            trouves = sum(1 for q in ref if any(abs(q[0] - p[0]) < 1e-6 and abs(q[1] - p[1]) < 1e-6 for p in r["front"]))
            lignes.append({"instance": nom, "n": r["n"], "methode": r["methode"], "graine": r["graine"],
                           "reference": type_ref, "points_reference": len(ref), "points": len(r["front"]),
                           "hv_relatif": hv_relatif(r["front"], ref), "igd": igd(r["front"], ref),
                           "part_reference_trouvee": trouves / len(ref), "temps_s": r["temps_s"], "complet": r["complet"]})
    ecrire_csv(RESULTATS / "module2_runs.csv", lignes)
    rediger(lignes, noms, refs, runs)


if __name__ == "__main__":
    import sys
    depuis_fichiers() if "--rediger" in sys.argv else main()
