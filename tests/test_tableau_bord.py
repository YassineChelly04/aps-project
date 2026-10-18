# -*- coding: utf-8 -*-
"""Tests du tableau de bord 1 (SPEC §10.6) sur TN-S-g1-r135 : une regle de lecture automatique
et un indicateur par test, recalcules independamment a partir du fichier brut."""
import json
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend import donnees, indicateurs as ind
from backend.app import DOSSIER_SORTIES, app

ID_S = "TN-S-g1-r135"


@pytest.fixture(scope="module")
def di():
    chemin = donnees.DOSSIER_INSTANCES / "S" / ID_S / "instance.json"
    if not chemin.exists():
        pytest.skip("Instance absente : lancer python donnees_tunisie/generer_instances.py")
    return donnees.charger_fichier(chemin)


@pytest.fixture(scope="module")
def brut(di):
    return di.brut


# ----------------------------------------------------------------------------- lecture automatique (§6)
def test_proximite(di, brut):
    dist = di.dist
    charge = {}
    for i, s in enumerate(brut["magasins"]):
        j = int(np.argmin(dist[i]))
        charge[j] = charge.get(j, 0) + s["demande"]
    taux = {j: charge.get(j, 0) / e["capacite"] for j, e in enumerate(brut["entrepots"])}
    j_max = max(taux, key=lambda j: (taux[j], -j))
    c = ind.constat_proximite(di)
    attendu = "impossible" if taux[j_max] > 1 else "faisable"
    assert c["tag"] == "Proximité" and attendu in c["titre"]
    assert brut["entrepots"][j_max]["id"] in c["texte"]
    assert ind.pct(taux[j_max], 0) in c["texte"]
    assert c["ton"] == ("alerte" if taux[j_max] > 1 else "ok")


def test_capacite(di, brut):
    D = sum(s["demande"] for s in brut["magasins"])
    Q = sum(e["capacite"] for e in brut["entrepots"])
    c = ind.constat_capacite(di)
    assert c["titre"] == f"Remplissage du réseau : {ind.pct(D / Q, 0)}"
    assert c["ton"] == ("alerte" if D / Q >= 0.7 else "ok")
    if D / Q < 0.8:
        assert ind.nf(Q - D) in c["texte"]
    kpi = {k["label"]: k for k in ind.chiffres_cles(di)}
    assert kpi["Remplissage"]["sub"] == ("tension forte" if D / Q >= 0.8 else "tension modérée" if D / Q >= 0.7 else "marge confortable")


@pytest.mark.parametrize("fill,niveau", [(0.85, "tension forte"), (0.8, "tension forte"), (0.75, "tension modérée"),
                                         (0.7, "tension modérée"), (0.69, "marge confortable")])
def test_seuils_tension(fill, niveau):
    assert ind.niveau_tension(fill) == niveau


def test_concentration(di, brut):
    D = sum(s["demande"] for s in brut["magasins"])
    par_g = {}
    for s in brut["magasins"]:
        par_g[s["gouvernorat"]] = par_g.get(s["gouvernorat"], 0) + s["demande"]
    tri = sorted(par_g.values(), reverse=True)
    premier = max(par_g, key=par_g.get)
    c = ind.constat_concentration(di)
    assert c["titre"] == f"{premier} pèse {ind.pct(tri[0] / D, 0)} de la demande"
    assert ind.pct(sum(tri[:3]) / D, 0) in c["texte"]
    assert c["ton"] == ("alerte" if tri[0] / D > 0.3 else "info")


def test_gros_clients(di, brut):
    D = sum(s["demande"] for s in brut["magasins"])
    hyp = [s for s in brut["magasins"] if s["format"] == "hypermarché"]
    c = ind.constat_gros_clients(di)
    if hyp:
        big = max(brut["magasins"], key=lambda s: s["demande"])
        assert c["tag"] == "Gros clients"
        assert c["titre"].startswith(f"{len(hyp)} hypermarché")
        assert ind.pct(sum(s["demande"] for s in hyp) / D, 0) in c["titre"]
        assert big["id"] in c["texte"] and ind.nf(big["demande"]) in c["texte"]
    else:
        assert c["tag"] == "Isolement"


def test_isolement_sans_hypermarche(di):
    brut = json.loads(json.dumps(di.brut))
    for s in brut["magasins"]:
        s["format"] = "proximité"
    d2 = donnees.charger(brut)
    d2.dist = di.dist
    c = ind.constat_gros_clients(d2)
    i = int(di.dist.min(axis=1).argmax())
    assert c["tag"] == "Isolement" and brut["magasins"][i]["ville"] in c["titre"]


def test_format_invalide():
    with pytest.raises(donnees.FormatInvalide, match="Ce fichier n'a pas le format instance.json attendu."):
        donnees.charger({"meta": {}, "magasins": []})


# ----------------------------------------------------------------------------- indicateurs (§7)
@pytest.fixture(scope="module")
def ref_ssc(di):
    r = di.reference("sscflp")
    return r, di.indices(r["affectation"])


def test_cout_total_sscflp(di, brut, ref_ssc):
    r, a = ref_ssc
    C = np.array(brut["cout_affectation"])
    ouverts = sorted(set(a))
    attendu = sum(C[i, a[i]] for i in range(len(a))) + sum(brut["entrepots"][j]["cout_fixe_semaine"] for j in ouverts)
    e = ind.evaluer(di, a, "sscflp")
    assert e["cout_total"] == pytest.approx(attendu, abs=0.01)
    assert e["cout_total"] == pytest.approx(r["cout"], abs=1)


def test_cout_total_gap(di, brut):
    r = di.reference("gap")
    a = di.indices(r["affectation"])
    C = np.array(brut["cout_affectation"])
    e = ind.evaluer(di, a, "gap")
    assert e["cout_total"] == pytest.approx(C[np.arange(len(a)), a].sum(), abs=0.01)
    assert e["cout_fixe"] == 0
    assert e["cout_total"] == pytest.approx(r["cout"], abs=1)


def test_entrepots_ouverts(di, ref_ssc):
    _, a = ref_ssc
    assert ind.evaluer(di, a, "gap")["entrepots_ouverts"] == di.m
    assert ind.evaluer(di, a, "sscflp")["entrepots_ouverts"] == len(set(a.tolist()))


def test_taux_utilisation(di, brut, ref_ssc):
    _, a = ref_ssc
    D = sum(s["demande"] for s in brut["magasins"])
    cap_ouverte = sum(brut["entrepots"][j]["capacite"] for j in set(a.tolist()))
    assert ind.evaluer(di, a, "sscflp")["taux_utilisation"] == pytest.approx(D / cap_ouverte)
    assert ind.evaluer(di, a, "gap")["taux_utilisation"] == pytest.approx(D / sum(e["capacite"] for e in brut["entrepots"]))


def test_distance_moyenne(di, ref_ssc):
    _, a = ref_ssc
    with np.load(donnees.DOSSIER_INSTANCES / "S" / ID_S / "matrices.npz") as z:
        dist = z["distance_km"]
    assert ind.evaluer(di, a, "sscflp")["distance_moyenne"] == pytest.approx(dist[np.arange(len(a)), a].mean())


def test_ecart_meilleure():
    assert ind.ecart(110.0, 100.0) == pytest.approx(0.10)
    assert ind.ecart(100.0, 100.0) == 0


def test_realisabilite(di, ref_ssc):
    _, a = ref_ssc
    assert ind.evaluer(di, a, "sscflp")["realisable"]
    tout_sur_un = np.zeros(di.n, dtype=int)
    assert not ind.evaluer(di, tout_sur_un, "sscflp")["realisable"]


def test_titres_conclusion(di, ref_ssc):
    from backend.methodes import METHODES
    _, a = ref_ssc
    e = ind.evaluer(di, a, "sscflp")
    un = ind.comparer(di, {"cs": {"temps_s": 1.0, "indicateurs": e}}, METHODES)
    assert un["titre"].startswith("① Cut-and-solve trouve l’optimum")
    assert f"sur {di.m}" in un["titre"]
    deux = ind.comparer(di, {"cs": {"temps_s": 1.0, "indicateurs": e}, "bp": {"temps_s": 3.0, "indicateurs": e}}, METHODES)
    assert deux["titre"].startswith("Même coût optimal") and "① Cut-and-solve répond 3,0 fois plus vite" in deux["titre"]
    pire = dict(e, cout_total=e["cout_total"] + 100)
    diff = ind.comparer(di, {"cs": {"temps_s": 1.0, "indicateurs": pire}, "bp": {"temps_s": 3.0, "indicateurs": e}}, METHODES)
    assert diff["titre"].startswith("② Branch-and-price donne le coût le plus bas")
    lignes = {l["cle"]: l for l in deux["lignes"]}
    assert len(lignes) == 6 and lignes["h1"]["cout"] == "jalon ultérieur"
    assert lignes["cs"]["temps_gras"] and not lignes["bp"]["temps_gras"]


# ----------------------------------------------------------------------------- API de bout en bout (§10)
@pytest.fixture(scope="module")
def client(di):
    return TestClient(app)


def _attendre(client, job_id, limite=120):
    t0 = time.time()
    while time.time() - t0 < limite:
        r = client.get(f"/api/calcul/{job_id}").json()
        if r["etat"] in ("termine", "erreur", "arrete"):
            return r
        time.sleep(0.3)
    raise TimeoutError(job_id)


def test_api_depot_fichier(client, di):
    contenu = (donnees.DOSSIER_INSTANCES / "S" / ID_S / "instance.json").read_bytes()
    r = client.post("/api/instance", files={"fichier": ("instance.json", contenu, "application/json")})
    assert r.status_code == 200
    corps = r.json()
    assert corps["id"] == ID_S and len(corps["chiffres_cles"]) == 5 and len(corps["constats"]) == 4
    r = client.post("/api/instance", files={"fichier": ("x.json", b'{"meta": {}}', "application/json")})
    assert r.status_code == 422 and r.json()["detail"] == "Ce fichier n'a pas le format instance.json attendu."


@pytest.mark.parametrize("modele", ["gap", "sscflp"])
@pytest.mark.parametrize("cle", ["cs", "bp"])
def test_api_calcul_reference(client, di, cle, modele):
    client.post("/api/instance", json={"exemple": "S"})
    job = client.post(f"/api/calcul/{cle}", json={"instance": ID_S, "modele": modele, "limite_temps": 60}).json()["job_id"]
    r = _attendre(client, job)
    assert r["etat"] == "termine", r
    res = r["resultat"]
    assert res["cout_total"] == pytest.approx(di.reference(modele)["cout"], abs=1)
    assert res["temps_s"] > 0 and res["trace"]


def test_api_arret(client):
    """Arrêter un calcul long rend vite la meilleure solution ; un calcul en attente est annulé."""
    client.post("/api/instance", json={"exemple": "M"})
    long = client.post("/api/calcul/bp", json={"instance": "TN-M-g1-r135", "modele": "sscflp", "limite_temps": 120}).json()["job_id"]
    file = client.post("/api/calcul/cs", json={"instance": "TN-M-g1-r135", "modele": "sscflp", "limite_temps": 120}).json()["job_id"]
    assert client.post(f"/api/calcul/{file}/arreter").json()["etat"] == "arrete"
    t0 = time.time()
    while (e := client.get(f"/api/calcul/{long}").json()["etat"]) == "en_attente" and time.time() - t0 < 30:
        time.sleep(0.1)
    assert e == "en_cours", e
    time.sleep(4)
    client.post(f"/api/calcul/{long}/arreter")
    r = _attendre(client, long, limite=30)
    assert time.time() - t0 < 30, "l'arrêt doit intervenir bien avant la limite de 120 s"
    assert r["etat"] in ("termine", "arrete")
    if r["etat"] == "termine":
        assert r["resultat"]["arrete"] and r["resultat"]["indicateurs"]["realisable"]
    assert _attendre(client, file)["etat"] == "arrete"


def test_api_methode_jalon(client):
    r = client.post("/api/calcul/h1", json={"instance": ID_S, "modele": "gap"})
    assert r.status_code == 409


def test_api_validation(client, di, ref_ssc):
    client.post("/api/instance", json={"exemple": "S"})
    r, a = ref_ssc
    aff = dict(r["affectation"])
    # Ajustement qui dépasse une capacité : tout sur le premier entrepôt -> validation refusée
    tout = {k: di.entrepots[0]["id"] for k in aff}
    assert not client.post("/api/evaluer", json={"instance": ID_S, "modele": "sscflp", "affectation": tout}).json()["realisable"]
    refus = client.post("/api/valider", json={"instance": ID_S, "modele": "sscflp", "methode": "cs", "affectation": tout})
    assert refus.status_code == 422
    ok = client.post("/api/valider", json={"instance": ID_S, "modele": "sscflp", "methode": "cs", "affectation": aff})
    assert ok.status_code == 200
    scen = ok.json()["scenario"]
    assert scen.startswith(f"SC-{ID_S}-SSC-")
    fichier = DOSSIER_SORTIES / f"affectation_validee_{scen}.json"
    sortie = json.loads(fichier.read_text(encoding="utf-8"))
    assert set(sortie) == {"scenario", "instance", "modele", "methode", "ajustements", "cout_total", "entrepots", "magasins"}
    assert sortie["cout_total"] == pytest.approx(r["cout"], abs=1)
    assert len(sortie["magasins"]) == di.n and {"id", "lat", "lon", "demande", "entrepot"} <= set(sortie["magasins"][0])
    assert {"id", "lat", "lon", "capacite", "ouvert"} <= set(sortie["entrepots"][0])
