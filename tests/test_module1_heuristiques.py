# -*- coding: utf-8 -*-
"""Tests des methodes ③ a ⑥ du module 1 (heuristiques et metaheuristiques)."""
import numpy as np
import pytest

import module1_heuristiques as mh
import module1_methods as m1
from backend import donnees
from backend.methodes import _instance_m1

CLES = list(mh.METHODES_HEURISTIQUES)
STOCHASTIQUES = ["h1", "m1", "m2"]


def lancer(cle, inst, **kw):
    if cle in STOCHASTIQUES:
        kw.setdefault("seed", 0)
    return mh.METHODES_HEURISTIQUES[cle](inst, time_limit=30, **kw)


@pytest.mark.parametrize("cle", CLES)
def test_exemple_du_document(cle):
    """Exemple commun (2 entrepots, 3 magasins) : SSCFLP = 19, GAP = 6."""
    ex = m1.example_instance()
    assert lancer(cle, ex).cost == pytest.approx(19)
    gap = m1.Instance(c=ex.c, d=ex.d, s=ex.s, f=np.zeros(2))
    assert lancer(cle, gap).assign_cost == pytest.approx(6)


@pytest.fixture(scope="module")
def inst_s():
    di = donnees.charger_fichier(donnees.chemin_exemple("S"))
    return di


@pytest.mark.parametrize("modele", ["gap", "sscflp"])
@pytest.mark.parametrize("cle", CLES)
def test_realisable_et_proche_de_la_reference(inst_s, cle, modele):
    inst = _instance_m1(inst_s, modele)
    sol = lancer(cle, inst)
    assert sol.feasible
    charge = np.bincount(sol.assign, weights=inst.d, minlength=inst.m)
    assert (charge <= inst.s + 1e-9).all()
    ref = inst_s.reference(modele)["cout"]
    assert sol.value >= ref - 1  # jamais mieux que l'optimum prouve
    assert sol.value <= ref * 1.02


@pytest.mark.parametrize("cle", STOCHASTIQUES)
def test_meme_graine_meme_resultat(inst_s, cle):
    inst = _instance_m1(inst_s, "sscflp")
    a, b = lancer(cle, inst, seed=3), lancer(cle, inst, seed=3)
    assert (a.assign == b.assign).all() and a.cost == b.cost


def test_kernel_search_borne_valide(inst_s):
    inst = _instance_m1(inst_s, "sscflp")
    sol = mh.kernel_search(inst, time_limit=30)
    assert sol.lower_bound <= sol.cost + 1e-6
    assert sol.lower_bound <= inst_s.reference("sscflp")["cout"] + 1e-6


def test_recuit_penalite_traverse_l_irrealisable():
    """Capacites tres tendues (remplissage 97 %) : la penalite permet quand meme de rendre une
    solution realisable."""
    inst = m1.generate_instance(4, 30, seed=5, capacity_ratio=1.03)
    sol = mh.recuit_simule_penalite(inst, time_limit=30, seed=0, iterations=200_000)
    assert sol.feasible


def test_arret_rend_une_solution(inst_s):
    import threading
    ev = threading.Event()
    ev.set()
    sol = mh.recuit_multi_voisinages(_instance_m1(inst_s, "sscflp"), time_limit=30, seed=0, arret=ev)
    assert sol.feasible  # arret immediat : on rend la solution initiale (realisable)


def test_mip_restreint_respecte_les_variables_permises():
    ex = m1.example_instance()
    permis = np.array([[True, True, False], [False, True, True]])
    a, v, opt = mh.mip_restreint(ex.c, ex.d, ex.s, ex.f, permis, 10)
    assert opt and a[0] == 0 and a[2] == 1
