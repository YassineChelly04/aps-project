# -*- coding: utf-8 -*-
"""Classeur Excel d'échange (§5) : sortie du module 1 en .xlsx, relecture par le module 2,
modification manuelle dans Excel -> scénario dérivé, contrôle des capacités."""
import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from backend import classeur as cl, donnees, tournees as tr
from backend.app import app

ID_S = "TN-S-g1-r135"


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def scenario_s(client):
    client.post("/api/instance", json={"exemple": "S"})
    di = donnees.charger_fichier(donnees.chemin_exemple("S"))
    aff = di.reference("gap")["affectation"]
    r = client.post("/api/valider", json={"instance": ID_S, "modele": "gap", "methode": "cs", "affectation": aff})
    assert r.status_code == 200
    return r.json()["scenario"]


def _xlsx(client, scenario):
    r = client.get(f"/api/m2/scenario/{scenario}/xlsx")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    return r.content


def _deposer(client, contenu, nom="classeur.xlsx"):
    return client.post("/api/m2/scenario", files={"fichier": (nom, contenu, "application/octet-stream")})


def test_classeur_contient_les_feuilles_et_formules(client, scenario_s):
    wb = load_workbook(io.BytesIO(_xlsx(client, scenario_s)))
    assert wb.sheetnames == [cl.F_LISEZ, cl.F_AFF, cl.F_ENT, cl.F_COUT, cl.F_DIST, cl.F_SCN]
    aff = wb[cl.F_AFF]
    assert [c.value for c in aff[1]] == cl.COLS_AFF
    assert aff.max_row == 21  # 20 magasins + en-tête
    assert str(aff["H2"].value).startswith("=INDEX(")          # coût recalculé dans Excel
    assert str(wb[cl.F_ENT]["F2"].value).startswith("=SUMIF(")  # charge recalculée dans Excel
    assert aff.data_validations.dataValidation                  # liste déroulante des entrepôts


def test_feuilles_apercu(client, scenario_s):
    r = client.get(f"/api/m2/scenario/{scenario_s}/feuilles").json()
    f = r["feuilles"]
    assert len(f[cl.F_AFF]) == 21 and f[cl.F_AFF][0] == cl.COLS_AFF
    sc = tr.lire_scenario(scenario_s)
    total = dict((l[0], l[1]) for l in f[cl.F_SCN][1:])["cout_total"]
    assert total == pytest.approx(sc["cout_total"], abs=0.05)


def test_classeur_non_modifie_garde_le_scenario(client, scenario_s):
    r = _deposer(client, _xlsx(client, scenario_s))
    assert r.status_code == 200
    j = r.json()
    assert j["scenario"] == scenario_s and j["import_"]["deplaces"] == []


def test_classeur_modifie_donne_un_scenario_derive(client, scenario_s):
    sc = tr.lire_scenario(scenario_s)
    ch = tr.charges(sc)
    cap = {e["id"]: float(e["capacite"]) for e in sc["entrepots"]}
    # un magasin qui tient dans un autre entrepôt
    mag, vers = next((s, e) for s in sorted(sc["magasins"], key=lambda s: s["demande"]) for e in cap
                     if e != s["entrepot"] and ch[e] + s["demande"] <= cap[e])
    wb = load_workbook(io.BytesIO(_xlsx(client, scenario_s)))
    ws = wb[cl.F_AFF]
    ligne = next(r for r in range(2, ws.max_row + 1) if ws.cell(r, 1).value == mag["id"])
    ws.cell(ligne, 6).value = vers
    buf = io.BytesIO()
    wb.save(buf)
    r = _deposer(client, buf.getvalue())
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["scenario"].startswith(scenario_s + "~x") and j["parent"] == scenario_s
    assert j["import_"]["deplaces"] == [{"magasin": mag["id"], "de": mag["entrepot"], "vers": vers}]
    assert set(j["import_"]["entrepots_touches"]) == {mag["entrepot"], vers}
    nv = tr.lire_scenario(j["scenario"])
    attendu = sc["cout_total"] - mag["couts"][mag["entrepot"]] + mag["couts"][vers]
    assert nv["cout_total"] == pytest.approx(attendu, abs=0.05)
    # signatures : seuls les deux entrepôts touchés changent (le cache du module 2 garde les autres)
    sig = lambda s: {p["entrepot"]["id"]: p["signature"] for p in tr.sous_problemes(s)}
    a, b = sig(sc), sig(nv)
    assert {k for k in a if a[k] != b.get(k)} == {mag["entrepot"], vers}


def test_classeur_capacite_depassee_refuse(client, scenario_s):
    sc = tr.lire_scenario(scenario_s)
    cible = sc["entrepots"][0]["id"]
    wb = load_workbook(io.BytesIO(_xlsx(client, scenario_s)))
    ws = wb[cl.F_AFF]
    for r in range(2, ws.max_row + 1):
        ws.cell(r, 6).value = cible
    buf = io.BytesIO()
    wb.save(buf)
    r = _deposer(client, buf.getvalue())
    assert r.status_code == 422 and "Capacité dépassée" in r.json()["detail"]


def test_classeur_entrepot_inconnu_refuse(client, scenario_s):
    wb = load_workbook(io.BytesIO(_xlsx(client, scenario_s)))
    wb[cl.F_AFF].cell(2, 6).value = "E99"
    buf = io.BytesIO()
    wb.save(buf)
    r = _deposer(client, buf.getvalue())
    assert r.status_code == 422 and "E99" in r.json()["detail"]


def test_fichier_quelconque_refuse(client):
    assert _deposer(client, b"PK\x03\x04pas un classeur").status_code == 422
