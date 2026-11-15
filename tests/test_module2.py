# -*- coding: utf-8 -*-
"""Tests du module 2 (TSP bi-objectif) et du lien entre les modules (cahier des charges §4 et §5)."""
import itertools
import json
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

import module2_tournees as m2
from backend import donnees, tournees as tr
from backend.app import app

ID_M = "TN-M-g1-r135"


def petite_instance(k=8, graine=0):
    rng = np.random.default_rng(graine)
    lat, lon = 36.8 + rng.normal(0, 0.15, k), 10.2 + rng.normal(0, 0.15, k)
    return m2.matrices([f"P{i}" for i in range(k)], lat, lon)


# ----------------------------------------------------------------------------- matrices
def test_matrices_symetriques_et_conflictuelles():
    D, T = petite_instance(10)
    assert np.allclose(D, D.T) and np.allclose(T, T.T)
    assert np.all(np.diag(D) == 0) and np.all(D[~np.eye(10, dtype=bool)] > 0)
    # le temps n'est pas proportionnel a la distance (sinon les deux objectifs coincideraient)
    ratio = T[np.triu_indices(10, 1)] / D[np.triu_indices(10, 1)]
    assert ratio.std() > 0.05


def test_congestion_independante_du_sous_ensemble():
    """Un meme troncon a le meme temps quel que soit le scenario : indispensable au cache par entrepot."""
    ids, lat, lon = ["E", "A", "B", "C"], [36.8, 36.9, 36.7, 36.6], [10.2, 10.1, 10.3, 10.4]
    _, T1 = m2.matrices(ids, lat, lon)
    _, T2 = m2.matrices(["E", "A", "C"], [36.8, 36.9, 36.6], [10.2, 10.1, 10.4])
    assert T1[0, 1] == pytest.approx(T2[0, 1]) and T1[1, 3] == pytest.approx(T2[1, 2])


# ----------------------------------------------------------------------------- outils de Pareto
def test_non_domines_et_hypervolume():
    pts = [(1, 5), (2, 3), (3, 4), (4, 1), (2, 3)]
    assert sorted(m2.non_domines(pts)) == [0, 1, 3]
    assert m2.hypervolume([(1, 1)], (2, 2)) == pytest.approx(1)
    assert m2.hypervolume([(0, 1), (1, 0)], (2, 2)) == pytest.approx(3)


def test_indicateurs_fronts():
    ind = m2.indicateurs_fronts({"a": [(0, 1), (1, 0)], "b": [(0, 1)]})
    assert ind["a"]["hv_ratio"] == pytest.approx(1) and ind["a"]["igd"] == pytest.approx(0)
    assert ind["b"]["hv_ratio"] < 1 and ind["b"]["contribution"] == pytest.approx(0.5)


def test_compromis():
    pts = [(0, 10), (5, 5), (10, 0)]
    assert m2.compromis(pts, 1.0) == 0 and m2.compromis(pts, 0.0) == 2 and m2.compromis(pts, 0.5) == 1


# ----------------------------------------------------------------------------- méthodes
def front_exact_force_brute(D, T):
    n = D.shape[0] - 1
    pts = []
    for p in itertools.permutations(range(1, n + 1)):
        pts.append(m2.evaluer([0] + list(p), D, T))
    return sorted({(round(pts[i][0], 6), round(pts[i][1], 6)) for i in m2.non_domines(pts)})


def test_epsilon_contrainte_exacte_milp():
    """n = 8 magasins : la methode passe par le MIP (pas l'enumeration) et doit retrouver le front
    exact obtenu par force brute."""
    D, T = petite_instance(9, graine=3)
    r = m2.epsilon_contrainte(D, T, time_limit=120)
    assert r["stats"]["methode"] == "epsilon-contrainte" and r["stats"]["complet"]
    obtenu = sorted((round(s["f1"], 6), round(s["f2"], 6)) for s in r["solutions"])
    attendu = front_exact_force_brute(D, T)
    assert len(obtenu) == len(attendu)
    assert np.allclose(obtenu, attendu, atol=1e-4)


@pytest.mark.parametrize("cle", ["ws", "nsga", "pls", "eps"])
def test_methodes_tournees_valides(cle):
    D, T = petite_instance(12, graine=1)
    r = m2.METHODES_TSP[cle](D, T, time_limit=20, seed=0, generations=150)
    assert r["solutions"]
    for s in r["solutions"]:
        assert s["tour"][0] == 0 and sorted(s["tour"]) == list(range(12))
        assert s["f1"] == pytest.approx(m2.longueur(s["tour"], D))
        assert s["f2"] == pytest.approx(m2.longueur(s["tour"], T))
    pts = [(s["f1"], s["f2"]) for s in r["solutions"]]
    assert len(m2.non_domines(pts)) == len(pts)  # le front rendu est mutuellement non domine


@pytest.mark.parametrize("cle", ["ws", "nsga", "pls"])
def test_heuristiques_ne_depassent_pas_le_front_exact(cle):
    D, T = petite_instance(8, graine=5)
    exact = [(s["f1"], s["f2"]) for s in m2.epsilon_contrainte(D, T)["solutions"]]
    r = m2.METHODES_TSP[cle](D, T, time_limit=20, seed=0, generations=150)
    for s in r["solutions"]:  # aucun point heuristique ne domine un point exact
        assert not any(m2.domine((s["f1"] - 1e-6, s["f2"] - 1e-6), e) and m2.domine((s["f1"], s["f2"]), e) for e in exact)


@pytest.mark.parametrize("cle", ["nsga", "pls"])
def test_reproductibilite(cle):
    D, T = petite_instance(14, graine=2)
    a = m2.METHODES_TSP[cle](D, T, time_limit=60, seed=7, generations=100)
    b = m2.METHODES_TSP[cle](D, T, time_limit=60, seed=7, generations=100)
    assert [s["tour"] for s in a["solutions"]] == [s["tour"] for s in b["solutions"]]


def test_kroab_benchmark():
    xyA = m2.lire_tsplib(donnees.RACINE / "donnees_benchmarks" / "tsplib" / "kroA100.tsp")
    assert xyA.shape == (100, 2)
    D, T = m2.instance_kroab(donnees.RACINE / "donnees_benchmarks" / "tsplib" / "kroA100.tsp",
                             donnees.RACINE / "donnees_benchmarks" / "tsplib" / "kroB100.tsp", 10)
    assert D.shape == (10, 10) and np.allclose(D, D.T) and not np.allclose(D, T)


# ----------------------------------------------------------------------------- intégration (§5)
@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def scenario_m(client):
    """Valide au module 1 l'affectation de reference SSCFLP de TN-M : fichier d'echange."""
    client.post("/api/instance", json={"exemple": "M"})
    di = donnees.charger_fichier(donnees.chemin_exemple("M"))
    aff = di.reference("sscflp")["affectation"]
    r = client.post("/api/valider", json={"instance": ID_M, "modele": "sscflp", "methode": "h2", "affectation": aff})
    assert r.status_code == 200
    return r.json()["scenario"]


def _attendre(client, job, limite=300):
    t0 = time.time()
    while time.time() - t0 < limite:
        r = client.get(f"/api/m2/calcul/{job}").json()
        if r["etat"] not in ("en_attente", "en_cours"):
            return r
        time.sleep(0.2)
    raise TimeoutError(job)


def test_fichier_echange_lu_par_le_module_2(client, scenario_m):
    sc = tr.lire_scenario(scenario_m)
    assert {"id", "lat", "lon", "demande", "entrepot"} <= set(sc["magasins"][0])
    assert {"id", "lat", "lon", "capacite"} <= set(sc["entrepots"][0])
    r = client.get(f"/api/m2/scenario/{scenario_m}").json()
    ouverts = {e["id"] for e in r["entrepots"] if e["ouvert"]}
    assert {t["entrepot"] for t in r["tournees"]} == ouverts
    assert sum(t["n"] for t in r["tournees"]) == r["n_magasins"]
    assert scenario_m in [s["scenario"] for s in client.get("/api/m2/scenarios").json()["scenarios"]]


def test_scenario_invalide(client):
    r = client.post("/api/m2/scenario", files={"fichier": ("x.json", b'{"scenario": "X"}', "application/json")})
    assert r.status_code == 422
    assert client.get("/api/m2/scenario/..%5Cetc").status_code in (404, 422)


def test_calcul_plan_export_et_cache(client, scenario_m):
    tr.vider_cache_memoire()
    for p in tr.DOSSIER_CACHE.glob("*.json") if tr.DOSSIER_CACHE.exists() else []:
        p.unlink()
    job = client.post("/api/m2/calcul", json={"scenario": scenario_m, "methodes": ["ws", "pls"], "limite_temps": 10}).json()["job_id"]
    r = _attendre(client, job)
    assert r["etat"] == "termine", r
    res = r["resultat"]
    assert res["n_recalcules"] == len(res["entrepots"]) and res["n_reutilises"] == 0
    for e in res["entrepots"]:
        assert set(e["resultats"]) == {"ws", "pls"} and e["indicateurs"]["front_reference"]

    # plan final : compromis equilibre de chaque entrepot
    choix = {}
    for e in res["entrepots"]:
        ref = e["indicateurs"]["front_reference"]
        k = m2.compromis([(p["distance_km"], p["temps_min"]) for p in ref], 0.5)
        sol = e["resultats"][ref[k]["methode"]]["solutions"][ref[k]["index"]]
        choix[e["entrepot"]] = {"methode": ref[k]["methode"], "sequence": sol["sequence"]}
    p = client.post("/api/m2/plan", json={"scenario": scenario_m, "choix": choix})
    assert p.status_code == 200
    plan = p.json()
    assert plan["totaux"]["arrets"] == sum(e["n"] for e in res["entrepots"])
    assert plan["cout_m1"] == pytest.approx(donnees.charger_fichier(donnees.chemin_exemple("M")).reference("sscflp")["cout"], abs=1)
    for l in plan["tournees"]:
        assert l["temps_total_min"] == pytest.approx(l["conduite_min"] + m2.SERVICE_MIN * l["arrets"])
    assert scenario_m in [x["scenario"] for x in client.get("/api/m2/plans").json()["plans"]]
    csv = client.get(f"/api/m2/plan/{scenario_m}/export?format=csv")
    assert csv.status_code == 200 and csv.content.decode("utf-8-sig").startswith("scenario;entrepot;rang")
    xl = client.get(f"/api/m2/plan/{scenario_m}/export?format=xlsx")
    assert xl.status_code == 200 and xl.content[:2] == b"PK"

    # tournée falsifiée : refusée
    faux = dict(choix)
    e0 = next(iter(faux))
    faux[e0] = {"methode": "ws", "sequence": faux[e0]["sequence"][:-1]}
    assert client.post("/api/m2/plan", json={"scenario": scenario_m, "choix": faux, "enregistrer": False}).status_code == 422

    # §5 « modification manuelle » : on déplace un magasin -> seuls les 2 entrepôts concernés sont recalculés
    sc = tr.lire_scenario(scenario_m)
    ch = tr.charges(sc)
    cap = {e["id"]: float(e["capacite"]) for e in sc["entrepots"]}
    mvt = next((s, e) for s in sorted(sc["magasins"], key=lambda s: s["demande"]) for e in cap
               if e != s["entrepot"] and ch[e] > 0 and ch[e] + s["demande"] <= cap[e])
    nv = client.post("/api/m2/ajuster", json={"scenario": scenario_m, "magasin": mvt[0]["id"], "vers": mvt[1]})
    assert nv.status_code == 200
    nv = nv.json()
    assert nv["parent"] == scenario_m and nv["ajustements"][-1]["vers"] == mvt[1]
    sc2 = tr.lire_scenario(nv["scenario"])
    attendu = sum(s["couts"][s["entrepot"]] for s in sc2["magasins"]) + sum(
        e["cout_fixe"] for e in sc2["entrepots"] if tr.charges(sc2)[e["id"]] > 0)
    assert sc2["cout_total"] == pytest.approx(attendu, abs=0.05)
    job2 = client.post("/api/m2/calcul", json={"scenario": nv["scenario"], "methodes": ["ws", "pls"], "limite_temps": 10}).json()["job_id"]
    r2 = _attendre(client, job2)["resultat"]
    recalc = {e["entrepot"] for e in r2["entrepots"] if e["recalcules"]}
    assert recalc == {mvt[0]["entrepot"], mvt[1]}
    assert r2["n_reutilises"] == len(r2["entrepots"]) - 2

    # capacité dépassée : refus
    gros = max(sc["magasins"], key=lambda s: s["demande"])
    plein = max((e for e in cap if e != gros["entrepot"]), key=lambda e: ch[e] / cap[e])
    if ch[plein] + gros["demande"] > cap[plein]:
        assert client.post("/api/m2/ajuster", json={"scenario": scenario_m, "magasin": gros["id"], "vers": plein}).status_code == 422

    # retour vers le module 1 (bonus) : instance corrigée chargeable par le module 1
    rt = client.post("/api/m2/retour", json={"scenario": scenario_m})
    assert rt.status_code == 200
    ident = rt.json()["instance"]
    r = client.post("/api/instance", json={"id": ident})
    assert r.status_code == 200 and r.json()["id"] == ident
