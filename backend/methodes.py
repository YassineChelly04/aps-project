# -*- coding: utf-8 -*-
"""Interface commune des methodes (§3). Les methodes ① et ② de module1_methods.py sont
enveloppees, pas reecrites : leur journal (_log) est intercepte pour remonter la phase
courante et la trace (temps, meilleur cout) necessaire a l'integrale primale."""
from __future__ import annotations

import math
import os
import re
import signal
import subprocess
import sys
import threading
import time

import numpy as np

from .donnees import RACINE, DonneesInstance
from .indicateurs import evaluer

if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))
import module1_methods as m1  # noqa: E402
import module1_heuristiques as mh  # noqa: E402

METHODES = {
    "cs": {"num": "①", "nom": "Cut-and-solve", "ref": "Gadegaard, Klose & Nielsen (2018)", "famille": "exacte",
           "pret": True, "stochastique": False},
    "bp": {"num": "②", "nom": "Branch-and-price", "ref": "Ryu & Park (2021)", "famille": "exacte",
           "pret": True, "stochastique": False},
    "h1": {"num": "③", "nom": "Matheuristique à grands voisinages", "ref": "Regret + échanges, puis LNS à réparation MIP (Shaw 1998 ; Pisinger & Ropke 2010)",
           "famille": "heuristique", "pret": True, "stochastique": True},
    "h2": {"num": "④", "nom": "Kernel Search", "ref": "Angelelli, Mansini & Speranza (2010) ; Guastaroba & Speranza (2014)",
           "famille": "heuristique", "pret": True, "stochastique": False},
    "m1": {"num": "⑤", "nom": "Recuit simulé · pénalité", "ref": "Kirkpatrick et al. (1983) ; capacités pénalisées",
           "famille": "metaheuristique", "pret": True, "stochastique": True},
    "m2": {"num": "⑥", "nom": "Recuit multi-voisinages · réparation", "ref": "Principe de Ceschia & Schaerf ; capacités réparées",
           "famille": "metaheuristique", "pret": True, "stochastique": True},
}
PHASES = {
    "cs": ["Plans coupants", "Branchement local", "Problème épars / dense", "Fermeture de l’écart"],
    "bp": ["Décomposition de Dantzig-Wolfe", "Génération de colonnes", "Branchement", "Fermeture de l’écart"],
    "h1": ["Construction par regret", "Échanges (déplacer / permuter)", "Grands voisinages + MIP", "Polissage"],
    "h2": ["Relaxation linéaire", "MIP sur le noyau", "Paquets de variables", "Polissage"],
    "m1": ["Solution initiale", "Calibrage de la température", "Recuit (capacités pénalisées)", "Polissage"],
    "m2": ["Solution initiale", "Calibrage de la température", "Recuit (4 voisinages, réparation)", "Polissage"],
}
# (motif du journal, indice de phase, le message porte-t-il un nouveau meilleur cout ?)
_REGLES = {
    "cs": [(r"\[Gadegaard\] tour", 0, False), (r"\[Gadegaard\] branchement local.*UB = ([\d.]+)", 1, True),
           (r"\[Gadegaard\] niveau .*UB = ([\d.]+)", 2, True), (r"\[Gadegaard\] SP niveau.*solution ([\d.]+)", 3, True)],
    "bp": [(r"\[Ryu-Park\] racine", 1, False), (r"\[Ryu-Park\] heuristique maitre entier : ([\d.]+)", 2, True),
           (r"\[Ryu-Park\] noeud.*solution entiere ([\d.]+)", 2, True)],
}


class MethodeIndisponible(RuntimeError):
    pass


# ----------------------------------------------------------------------------- interception du journal
_local = threading.local()
_log_original = m1._log


def _log_intercepte(verbose, *args):
    ecoute = getattr(_local, "ecoute", None)
    if ecoute is None:
        return _log_original(verbose, *args)
    ecoute(" ".join(str(a) for a in args))


m1._log = _log_intercepte


# ----------------------------------------------------------------------------- arrêt à la demande
class _HorlogeArretable:
    """Remplace le module time vu par module1_methods : quand l'arret du calcul courant est
    demande, time.time() saute loin dans le futur, toutes les echeances des methodes sont
    depassees et elles rendent proprement leur meilleure solution."""

    def __getattr__(self, nom):
        return getattr(time, nom)

    def time(self):
        arret = getattr(_local, "arret", None)
        return time.time() + (1e9 if arret is not None and arret.is_set() else 0.0)


m1.time = _HorlogeArretable()
_solve_mip_original = m1.solve_mip


def _solve_mip_arretable(prob, time_limit, warm=False, msg=False):
    try:
        return _solve_mip_original(prob, time_limit, warm=warm, msg=msg)
    except Exception:
        arret = getattr(_local, "arret", None)
        if arret is not None and arret.is_set():  # CBC tue par l'arret : pas de nouvelle solution
            return False, False, False
        raise


m1.solve_mip = _solve_mip_arretable


def _pids_cbc_enfants():
    """PID des processus CBC lances par ce serveur (None si psutil est absent)."""
    try:
        import psutil
    except ImportError:
        return None
    pids = []
    for p in psutil.Process().children(recursive=True):
        try:
            if "cbc" in p.name().lower():
                pids.append(p.pid)
        except psutil.Error:
            pass
    return pids


def tuer_solveurs():
    """Termine les processus CBC en cours (un seul calcul tourne a la fois sur le serveur).
    Sous Windows : taskkill /F /T (arbre du processus) ; ailleurs : SIGKILL."""
    pids = _pids_cbc_enfants()
    if os.name == "nt":
        if pids is None:  # sans psutil : tous les CBC (seul ce serveur en lance)
            cmds = [["taskkill", "/F", "/T", "/IM", "cbc.exe"]]
        else:
            cmds = [["taskkill", "/F", "/T", "/PID", str(p)] for p in pids]
        for cmd in cmds:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        for p in pids or []:
            try:
                os.kill(p, signal.SIGKILL)
            except OSError:
                pass


class ArretSansSolution(RuntimeError):
    pass


def _instance_m1(di: DonneesInstance, modele: str) -> m1.Instance:
    # module1 : c[i, j] = cout de l'entrepot i pour le magasin j. GAP = SSCFLP sans cout fixe.
    f = di.f if modele == "sscflp" else np.zeros(di.m)
    return m1.Instance(c=di.C.T, d=di.d, s=di.s, f=f, name=di.id)


def resoudre(cle, instance: DonneesInstance, modele, limite_temps, graine=0, progression=None, arret=None) -> dict:
    """modele = "gap" (tous ouverts, sans cout fixe) ou "sscflp" (ouverture + affectation).
    progression(phase:str, fraction:float) est appele quand la methode change de phase.
    arret : threading.Event ; s'il est leve, la methode s'interrompt et rend sa meilleure solution."""
    if cle not in METHODES:
        raise KeyError(f"Méthode inconnue : {cle}")
    if not METHODES[cle]["pret"]:
        raise MethodeIndisponible(f"{METHODES[cle]['num']} {METHODES[cle]['nom']} : jalon ultérieur, pas encore implémentée.")
    if modele not in ("gap", "sscflp"):
        raise ValueError("modele doit valoir 'gap' ou 'sscflp'")
    phases = PHASES[cle]
    trace, etat = [], {"phase": 0}
    t0 = time.perf_counter()

    def signaler(k, fraction=None):
        etat["phase"] = max(etat["phase"], k)
        if progression:
            fr = (etat["phase"] + (0.5 if fraction is None else fraction)) / len(phases)
            progression(phases[etat["phase"]], min(fr, 1.0))

    inst = _instance_m1(instance, modele)
    signaler(0)
    if cle in ("cs", "bp"):
        regles = _REGLES[cle]

        def ecoute(msg):
            for motif, k, porte_cout in regles:
                mo = re.search(motif, msg)
                if mo:
                    if porte_cout:
                        trace.append((time.perf_counter() - t0, float(mo.group(1))))
                    signaler(k)
                    break

        _local.ecoute, _local.arret = ecoute, arret
        try:
            if cle == "cs":
                sol = m1.gadegaard2018_cut_and_solve(inst, time_limit=limite_temps, verbose=True)
            else:
                sol = m1.ryu_park2021_branch_and_price(inst, time_limit=limite_temps, verbose=True)
        finally:
            _local.ecoute = _local.arret = None
    else:
        def rapport(phase, fraction, cout):
            if cout is not None and math.isfinite(cout) and (not trace or cout < trace[-1][1] - 1e-9):
                trace.append((time.perf_counter() - t0, float(cout)))
            signaler(phase, fraction)

        fn = mh.METHODES_HEURISTIQUES[cle]
        kw = {"seed": int(graine)} if METHODES[cle]["stochastique"] else {}
        sol = fn(inst, time_limit=limite_temps, rapport=rapport, arret=arret, **kw)
    temps = time.perf_counter() - t0
    arrete = arret is not None and arret.is_set()
    if not sol.feasible or (sol.assign < 0).any():
        if arrete:
            raise ArretSansSolution("Arrêté avant de trouver une solution réalisable.")
        raise RuntimeError("Aucune solution réalisable trouvée dans la limite de temps.")
    signaler(len(phases) - 1)
    ind = evaluer(instance, sol.assign, modele)
    trace.append((temps, ind["cout_total"]))
    lb = sol.lower_bound
    return {
        "affectation": instance.ids(sol.assign),
        "cout_total": ind["cout_total"],
        "borne_inf": None if lb is None or not np.isfinite(lb) else float(lb),
        # une heuristique dont le cout atteint sa borne (LP du Kernel Search) a aussi prouve l'optimum
        "optimal_prouve": bool(sol.proven_optimal or (sol.gap is not None and sol.gap < 1e-9)),
        "graine": int(graine) if METHODES[cle]["stochastique"] else None,
        "arrete": arrete,
        "ecart_borne": None if sol.gap is None else float(sol.gap),
        "temps_s": temps,
        "trace": trace,
        "indicateurs": ind,
    }
