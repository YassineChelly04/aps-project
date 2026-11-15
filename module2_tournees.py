# -*- coding: utf-8 -*-
"""
Projet APS - Module 2 : tournee de chaque entrepot, TSP bi-objectif (distance, temps).

Pour un entrepot (noeud 0) et les n magasins qui lui sont affectes (noeuds 1..n), un vehicule
part de l'entrepot, visite chaque magasin une fois et revient. Deux objectifs a minimiser :
    f1 = distance totale (km)          f2 = temps total de conduite (min)
Ils ne coincident pas car la vitesse depend du type de route et de la congestion.
On cherche le FRONT DE PARETO (cahier des charges §4).

Quatre methodes de natures differentes (§4.3) :
  ws    somme_ponderee          heuristique : plus proche voisin + 2-opt + Or-opt sur
                                lambda f1 + (1 - lambda) f2 (normalises), lambda de 0 a 1
  nsga  nsga2                   evolutionnaire a base de Pareto : NSGA-II (Deb et al. 2002),
                                permutation, croisement OX, mutation inversion / echange
  pls   pareto_local_search     metaheuristique : 2PPLS (Lust & Teghem 2010), phase 1 dichotomique
                                (solutions supportees), phase 2 recherche locale de Pareto en 2-opt
  eps   epsilon_contrainte      exacte : epsilon-contrainte lexicographique, chaque sous-probleme
                                resolu par HiGHS (TSP symetrique, coupes de sous-tours DFJ ajoutees
                                a la volee) ; enumeration complete si n <= 7

Une tournee est une permutation de 0..n commencant par 0 (l'entrepot) ; le retour est implicite.
Toutes les methodes renvoient une liste de solutions non dominees {"tour", "f1", "f2"}.
"""
from __future__ import annotations

import itertools
import math
import random
import time
import zlib

import numpy as np
from scipy import sparse
from scipy.optimize import Bounds, LinearConstraint, milp

FACTEUR_ROUTE = 1.25          # distance routiere ~ 1,25 x vol d'oiseau (meme facteur qu'au module 1)
VITESSES = ((8.0, 35.0), (40.0, 60.0), (math.inf, 85.0))  # (troncon jusqu'a x km, vitesse km/h)
CONGESTION = (1.0, 1.5)       # facteur multiplicatif aleatoire par troncon (cahier des charges, source B)
ZONES_DENSES = ((36.81, 10.18, 15.0), (34.74, 10.76, 8.0), (35.83, 10.63, 8.0))  # Grand Tunis, Sfax, Sousse
SURCOUT_ZONE_DENSE = 1.3      # troncon dont le milieu est en zone dense
SERVICE_MIN = 15.0            # temps de service constant par arret (min) : s'ajoute au temps total


# =============================================================================
# Donnees : matrices distance / temps
# =============================================================================
def haversine(lat1, lon1, lat2, lon2):
    la1, lo1, la2, lo2 = map(np.radians, (lat1, lon1, lat2, lon2))
    h = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(np.clip(h, 0, 1)))


def _alea_paire(graine, a, b):
    """Nombre dans [0, 1) propre a la paire {a, b} (symetrique, independant du sous-ensemble) :
    un meme troncon a toujours la meme congestion, quel que soit le scenario."""
    a, b = sorted((str(a), str(b)))
    return zlib.crc32(f"{graine}|{a}|{b}".encode()) / 2 ** 32


def matrices(ids, lat, lon, graine=2026):
    """Matrices symetriques D (km) et T (min de conduite) pour les points donnes.
    D = 1,25 x haversine ;  T = D / v(type de route) x congestion(troncon) x zone dense.
    Le type de route se deduit de la longueur du troncon (urbain < 8 km : 35 km/h,
    regional < 40 km : 60 km/h, national : 85 km/h)."""
    lat = np.asarray(lat, float)
    lon = np.asarray(lon, float)
    k = lat.size
    D = FACTEUR_ROUTE * haversine(lat[:, None], lon[:, None], lat[None, :], lon[None, :])
    V = np.full_like(D, VITESSES[-1][1])
    for borne, v in reversed(VITESSES):
        V[D < borne] = v
    cong = np.ones_like(D)
    for i in range(k):
        for j in range(i + 1, k):
            u = _alea_paire(graine, ids[i], ids[j])
            c = CONGESTION[0] + (CONGESTION[1] - CONGESTION[0]) * u
            mla, mlo = (lat[i] + lat[j]) / 2, (lon[i] + lon[j]) / 2
            for zla, zlo, rayon in ZONES_DENSES:
                if haversine(mla, mlo, zla, zlo) <= rayon:
                    c *= SURCOUT_ZONE_DENSE
                    break
            cong[i, j] = cong[j, i] = c
    T = D / V * 60.0 * cong
    np.fill_diagonal(D, 0.0)
    np.fill_diagonal(T, 0.0)
    return D, T


# =============================================================================
# Evaluation et outils de Pareto
# =============================================================================
def longueur(tour, M):
    t = np.asarray(tour)
    return float(M[t, np.roll(t, -1)].sum())


def evaluer(tour, D, T):
    return longueur(tour, D), longueur(tour, T)


def domine(a, b):
    return a[0] <= b[0] and a[1] <= b[1] and (a[0] < b[0] or a[1] < b[1])


def non_domines(points, tol=1e-9):
    """Indices des points non domines (doublons d'objectifs retires), tries par f1 croissant."""
    P = np.asarray(points, float)
    if P.size == 0:
        return []
    ordre = np.lexsort((P[:, 1], P[:, 0]))
    garde, meilleur_f2 = [], math.inf
    for i in ordre:
        if P[i, 1] < meilleur_f2 - tol:
            garde.append(int(i))
            meilleur_f2 = P[i, 1]
    return garde


def filtrer(solutions):
    """Garde les solutions non dominees d'une liste de dicts {"tour", "f1", "f2"}."""
    if not solutions:
        return []
    idx = non_domines([(s["f1"], s["f2"]) for s in solutions])
    return [solutions[i] for i in idx]


def _sol(tour, D, T):
    t = [int(x) for x in tour]
    k = t.index(0)
    t = t[k:] + t[:k]  # commence a l'entrepot
    f1, f2 = evaluer(t, D, T)
    return {"tour": t, "f1": f1, "f2": f2}


def hypervolume(points, ref):
    """Hypervolume 2D (minimisation) domine par les points et borne par le point de reference."""
    P = sorted((p for p in points if p[0] < ref[0] and p[1] < ref[1]), key=lambda p: p[0])
    hv, f2_prec = 0.0, ref[1]
    for f1, f2 in P:
        if f2 < f2_prec:
            hv += (ref[0] - f1) * (f2_prec - f2)
            f2_prec = f2
    return hv


def igd(points, reference):
    """Inverted Generational Distance : distance moyenne d'un point du front de reference au point
    le plus proche du front evalue (dans l'espace normalise fourni par l'appelant)."""
    if not points or not reference:
        return math.inf
    A = np.asarray(points, float)
    R = np.asarray(reference, float)
    return float(np.sqrt(((R[:, None, :] - A[None, :, :]) ** 2).sum(axis=2)).min(axis=1).mean())


def indicateurs_fronts(fronts):
    """fronts : {nom: [(f1, f2), ...]}. Normalise sur l'ideal / nadir du front de reference (union
    non dominee de tous les fronts) et renvoie {nom: {hv, hv_ratio, igd, nb, contribution}}.
    Point de reference de l'hypervolume : (1,1, 1,1) dans l'espace normalise."""
    tous = [p for pts in fronts.values() for p in pts]
    if not tous:
        return {}
    ref_idx = non_domines(tous)
    R = np.asarray([tous[i] for i in ref_idx], float)
    ideal, nadir = R.min(axis=0), R.max(axis=0)
    ech = np.where(nadir - ideal > 1e-12, nadir - ideal, 1.0)
    norm = lambda pts: [tuple((np.asarray(p) - ideal) / ech) for p in pts]
    Rn = norm(R)
    hv_ref = hypervolume(Rn, (1.1, 1.1))
    out = {}
    for nom, pts in fronts.items():
        pn = norm(pts)
        hv = hypervolume(pn, (1.1, 1.1))
        contrib = sum(1 for r in R if any(abs(r[0] - p[0]) < 1e-6 and abs(r[1] - p[1]) < 1e-6 for p in pts))
        out[nom] = {"nb": len(pts), "hv": hv, "hv_ratio": hv / hv_ref if hv_ref > 0 else 1.0,
                    "igd": igd(pn, Rn), "contribution": contrib / len(R)}
    return out


def compromis(points, poids=0.5):
    """Indice du point qui minimise la distance de Tchebycheff ponderee au point ideal :
        max(poids x f1n, (1 - poids) x f2n) + 1e-6 (f1n + f2n)     (objectifs normalises sur le front).
    poids = 1 : la plus courte ; 0 : la plus rapide ; 0,5 : compromis equilibre. Contrairement a une
    somme ponderee, Tchebycheff peut designer un point d'une partie non convexe du front."""
    P = np.asarray(points, float)
    if len(P) == 1:
        return 0
    lo, hi = P.min(axis=0), P.max(axis=0)
    N = (P - lo) / np.where(hi - lo > 1e-12, hi - lo, 1.0)
    w = np.array([poids, 1 - poids])
    crit = (w * N).max(axis=1) + 1e-6 * N.sum(axis=1) + 1e-9 * (1 - poids) * N[:, 1] + 1e-9 * poids * N[:, 0]
    return int(np.argmin(crit))


# =============================================================================
# Recherches locales mono-objectif (sur une matrice W)
# =============================================================================
def plus_proche_voisin(W, depart=0):
    k = W.shape[0]
    tour, libre = [depart], np.ones(k, bool)
    libre[depart] = False
    while libre.any():
        c = np.where(libre, W[tour[-1]], np.inf)
        j = int(np.argmin(c))
        tour.append(j)
        libre[j] = False
    return tour


def deux_opt(tour, W):
    """2-opt en meilleure amelioration, vectorise : delta(i, j) pour tous les i < j a la fois."""
    t = np.array(tour)
    N = t.size
    if N < 4:
        return list(t)
    I, J = np.triu_indices(N, k=2)
    garde = ~((I == 0) & (J == N - 1))
    I, J = I[garde], J[garde]
    while True:
        a, b = t[I], t[(I + 1) % N]
        c, d = t[J], t[(J + 1) % N]
        delta = W[a, c] + W[b, d] - W[a, b] - W[c, d]
        k = int(np.argmin(delta))
        if delta[k] >= -1e-10:
            return list(t)
        i, j = I[k], J[k]
        t[i + 1:j + 1] = t[i + 1:j + 1][::-1]


def or_opt(tour, W):
    """Or-opt : deplacer un segment de 1 a 3 noeuds (eventuellement retourne) ailleurs dans la tournee."""
    t = list(tour)
    N = len(t)
    if N < 5:
        return t
    ameliore = True
    while ameliore:
        ameliore = False
        for L in (1, 2, 3):
            for i in range(1, N - L + 1):        # le segment t[i:i+L] (l'entrepot t[0] ne bouge pas)
                seg = t[i:i + L]
                p, q = t[i - 1], t[(i + L) % N]
                gain_retrait = W[p, seg[0]] + W[seg[-1], q] - W[p, q]
                reste = t[:i] + t[i + L:]
                meilleur, pos, inv = 1e-10, -1, False
                for k in range(len(reste)):
                    u, v = reste[k], reste[(k + 1) % len(reste)]
                    c1 = W[u, seg[0]] + W[seg[-1], v] - W[u, v]
                    c2 = W[u, seg[-1]] + W[seg[0], v] - W[u, v]
                    if gain_retrait - c1 > meilleur:
                        meilleur, pos, inv = gain_retrait - c1, k, False
                    if L > 1 and gain_retrait - c2 > meilleur:
                        meilleur, pos, inv = gain_retrait - c2, k, True
                if pos >= 0:
                    s = seg[::-1] if inv else seg
                    t = reste[:pos + 1] + s + reste[pos + 1:]
                    k0 = t.index(0)
                    t = t[k0:] + t[:k0]
                    ameliore = True
                    break
            if ameliore:
                break
    return t


def recherche_locale(tour, W):
    """2-opt puis Or-opt, repetes jusqu'a ce qu'aucun des deux n'ameliore."""
    t, v = list(tour), longueur(tour, W)
    while True:
        t = or_opt(deux_opt(t, W), W)
        v2 = longueur(t, W)
        if v2 >= v - 1e-10:
            return t
        v = v2


class _Suivi:
    def __init__(self, time_limit, arret=None, rapport=None):
        self.t0 = time.perf_counter()
        self.limite = float(time_limit)
        self.arret = arret
        self.rapport = rapport

    def ecoule(self):
        return time.perf_counter() - self.t0

    def fini(self):
        return (self.arret is not None and self.arret.is_set()) or self.ecoule() >= self.limite

    def signale(self, fraction):
        if self.rapport:
            self.rapport(max(0.0, min(1.0, fraction)))


def _trivial(D, T):
    """n <= 2 magasins : une seule tournee possible."""
    return [_sol(list(range(D.shape[0])), D, T)]


def _extremes(D, T):
    """Tournees optimisees sur la distance seule et sur le temps seul (bornes de normalisation)."""
    t1 = recherche_locale(plus_proche_voisin(D), D)
    t2 = recherche_locale(plus_proche_voisin(T), T)
    return t1, t2


def _echelles(D, T, t1, t2):
    s1, s2 = _sol(t1, D, T), _sol(t2, D, T)
    r1 = max(s2["f1"] - s1["f1"], 1e-6 * max(s1["f1"], 1.0))
    r2 = max(s1["f2"] - s2["f2"], 1e-6 * max(s2["f2"], 1.0))
    # si les deux extremes coincident, on normalise par la valeur elle-meme
    if s2["f1"] - s1["f1"] < 1e-9 and s1["f2"] - s2["f2"] < 1e-9:
        r1, r2 = max(s1["f1"], 1e-9), max(s2["f2"], 1e-9)
    return r1, r2


# =============================================================================
# Methode 1 : somme ponderee (heuristique)
# =============================================================================
def somme_ponderee(D, T, nb_lambda=21, time_limit=60, arret=None, rapport=None, **_):
    """Pour lambda = 0, 1/(K-1), ..., 1 : minimiser f = lambda f1/r1 + (1 - lambda) f2/r2
    (r1, r2 = etendues entre les tournees optimisees sur un seul objectif) par
    plus proche voisin + 2-opt + Or-opt, en partant aussi de la meilleure tournee du lambda
    precedent. Deterministe. Ne trouve que des points « supportes » (sur l'enveloppe convexe)."""
    suivi = _Suivi(time_limit, arret, rapport)
    if D.shape[0] <= 3:
        return {"solutions": _trivial(D, T), "stats": {"lambdas": 0}}
    t1, t2 = _extremes(D, T)
    r1, r2 = _echelles(D, T, t1, t2)
    sols = [_sol(t1, D, T), _sol(t2, D, T)]
    prec = t2
    lambdas = np.linspace(0.0, 1.0, nb_lambda)
    for k, lam in enumerate(lambdas):
        if suivi.fini():
            break
        W = lam * D / r1 + (1 - lam) * T / r2
        cands = [recherche_locale(plus_proche_voisin(W), W), recherche_locale(prec, W)]
        best = min(cands, key=lambda t: longueur(t, W))
        sols.append(_sol(best, D, T))
        prec = best
        suivi.signale((k + 1) / len(lambdas))
    return {"solutions": filtrer(sols), "stats": {"lambdas": int(k + 1), "echelles": [r1, r2]}}


# =============================================================================
# Methode 2 : NSGA-II
# =============================================================================
def _tri_non_domine(F):
    """Fast non-dominated sort (Deb et al. 2002). Renvoie le rang (0 = premier front) de chaque individu."""
    n = len(F)
    le = (F[:, None, :] <= F[None, :, :]).all(axis=2)
    lt = (F[:, None, :] < F[None, :, :]).any(axis=2)
    dom = le & lt                       # dom[p, q] : p domine q
    nb_dominants = dom.sum(axis=0)
    rang = np.full(n, -1)
    courant = np.flatnonzero(nb_dominants == 0)
    r = 0
    while courant.size:
        rang[courant] = r
        nb_dominants = nb_dominants - dom[courant].sum(axis=0)
        nb_dominants[rang >= 0] = -1
        courant = np.flatnonzero(nb_dominants == 0)
        r += 1
    return rang


def _distance_encombrement(F):
    n = len(F)
    cd = np.zeros(n)
    if n <= 2:
        return np.full(n, np.inf)
    for k in range(F.shape[1]):
        o = np.argsort(F[:, k])
        cd[o[0]] = cd[o[-1]] = np.inf
        e = F[o[-1], k] - F[o[0], k]
        if e > 0:
            cd[o[1:-1]] += (F[o[2:], k] - F[o[:-2], k]) / e
    return cd


def _ox(p1, p2, rng):
    """Croisement d'ordre OX (Davis 1985) sur des permutations."""
    n = len(p1)
    a, b = sorted(rng.choice(n + 1, 2, replace=False))
    enfant = -np.ones(n, dtype=int)
    enfant[a:b] = p1[a:b]
    pris = set(p1[a:b].tolist())
    reste = [g for g in np.roll(p2, -b) if g not in pris]
    pos = [(b + k) % n for k in range(n - (b - a))]
    enfant[pos] = reste
    return enfant


def _muter(p, rng):
    p = p.copy()
    i, j = sorted(rng.choice(len(p), 2, replace=False))
    if rng.random() < 0.5:
        p[i:j + 1] = p[i:j + 1][::-1]   # inversion (2-opt aleatoire)
    else:
        p[i], p[j] = p[j], p[i]         # echange
    return p


def _evaluer_pop(P, D, T):
    tours = np.hstack([np.zeros((len(P), 1), int), P])
    nxt = np.roll(tours, -1, axis=1)
    return np.column_stack([D[tours, nxt].sum(axis=1), T[tours, nxt].sum(axis=1)])


def nsga2(D, T, taille_pop=100, generations=1000, p_croisement=0.9, p_mutation=0.6, seed=0, time_limit=60,
          arret=None, rapport=None, **_):
    """NSGA-II (Deb et al. 2002) : codage par permutation des magasins (l'entrepot est fixe en tete),
    tournoi binaire (rang puis distance d'encombrement), croisement OX, mutation par inversion ou
    echange, selection elitiste (mu + lambda) par tri de non-dominance et encombrement.
    Initialisation : aleatoire, plus deux individus « plus proche voisin » (distance, temps).
    Une archive externe garde toutes les solutions non dominees rencontrees.
    Population 100 et p_mutation 0,6 retenues par experimentation/exp_reglage.py."""
    suivi = _Suivi(time_limit, arret, rapport)
    n = D.shape[0] - 1
    if n <= 2:
        return {"solutions": _trivial(D, T), "stats": {"generations": 0}}
    rng = np.random.default_rng(seed)
    pop = [rng.permutation(np.arange(1, n + 1)) for _ in range(taille_pop - 2)]
    pop += [np.array(plus_proche_voisin(D)[1:]), np.array(plus_proche_voisin(T)[1:])]
    P = np.array(pop)
    F = _evaluer_pop(P, D, T)
    archive = {}

    def archiver(P, F):
        for k in non_domines(F):
            archive[(round(F[k, 0], 9), round(F[k, 1], 9))] = P[k]
        cles = list(archive)
        for i in set(range(len(cles))) - set(non_domines(cles)):
            del archive[cles[i]]

    archiver(P, F)
    rang = _tri_non_domine(F)
    cd = _distance_encombrement(F)
    g = 0
    for g in range(generations):
        if suivi.fini():
            break

        def tournoi():
            a, b = rng.integers(len(P), size=2)
            if rang[a] != rang[b]:
                return a if rang[a] < rang[b] else b
            return a if cd[a] >= cd[b] else b

        enfants = []
        while len(enfants) < taille_pop:
            p1, p2 = P[tournoi()], P[tournoi()]
            if rng.random() < p_croisement:
                e1, e2 = _ox(p1, p2, rng), _ox(p2, p1, rng)
            else:
                e1, e2 = p1.copy(), p2.copy()
            for e in (e1, e2):
                enfants.append(_muter(e, rng) if rng.random() < p_mutation else e)
        Q = np.array(enfants[:taille_pop])
        FQ = _evaluer_pop(Q, D, T)
        archiver(Q, FQ)
        R, FR = np.vstack([P, Q]), np.vstack([F, FQ])
        rR = _tri_non_domine(FR)
        choisis = []
        for r in range(rR.max() + 1):
            front = np.flatnonzero(rR == r)
            if len(choisis) + front.size <= taille_pop:
                choisis.extend(front.tolist())
            else:
                c = _distance_encombrement(FR[front])
                choisis.extend(front[np.argsort(-c)][: taille_pop - len(choisis)].tolist())
                break
        P, F = R[choisis], FR[choisis]
        rang = _tri_non_domine(F)
        cd = _distance_encombrement(F)
        suivi.signale((g + 1) / generations)
    sols = [_sol([0] + list(p), D, T) for p in archive.values()]
    return {"solutions": filtrer(sols), "stats": {"generations": g + 1, "taille_pop": taille_pop, "graine": seed}}


# =============================================================================
# Methode 3 : 2PPLS (Lust & Teghem 2010)
# =============================================================================
def _ajouter(archive, cand):
    """Ajoute cand a l'archive (liste de dicts) si non domine ; retire ce qu'il domine. Renvoie True si ajoute."""
    c = (cand["f1"], cand["f2"])
    for s in archive:
        p = (s["f1"], s["f2"])
        if (p[0] <= c[0] + 1e-9 and p[1] <= c[1] + 1e-9):
            return False
    archive[:] = [s for s in archive if not domine(c, (s["f1"], s["f2"]))]
    archive.append(cand)
    return True


def pareto_local_search(D, T, seed=0, time_limit=60, profondeur_max=6, nb_amorces=5, arret=None, rapport=None, **_):
    """Two-Phase Pareto Local Search (Lust & Teghem 2010).
    Phase 1 (solutions supportees, methode dichotomique d'Aneja & Nair) : on part des deux tournees
      optimisees sur un objectif et de nb_amorces ponderations fixes ; pour deux points voisins (a, b), on minimise la somme ponderee
      dont la direction est orthogonale au segment [a, b] ; si le point trouve est sous le segment,
      on l'insere et on recommence de part et d'autre.
    Phase 2 (recherche locale de Pareto) : tant qu'il reste des solutions non explorees dans
      l'archive, on en prend une, on evalue TOUT son voisinage 2-opt (vectorise : delta f1 et delta f2
      de chaque mouvement) et on ajoute a l'archive chaque voisin non domine. Les points non
      supportes (entre les points supportes) apparaissent ainsi. Ordre d'exploration aleatoire (graine)."""
    suivi = _Suivi(time_limit, arret, rapport)
    N = D.shape[0]
    if N <= 3:
        return {"solutions": _trivial(D, T), "stats": {}}
    rng = random.Random(seed)
    t1, t2 = _extremes(D, T)
    r1, r2 = _echelles(D, T, t1, t2)
    a, b = _sol(t1, D, T), _sol(t2, D, T)
    archive = []
    _ajouter(archive, a)
    _ajouter(archive, b)

    def dicho(a, b, prof):
        if prof > profondeur_max or suivi.fini():
            return
        l1, l2 = (a["f2"] - b["f2"]) / r2, (b["f1"] - a["f1"]) / r1   # normale au segment [a, b]
        if l1 <= 0 or l2 <= 0:
            return
        W = l1 * D / r1 + l2 * T / r2
        t = min((recherche_locale(a["tour"], W), recherche_locale(b["tour"], W)), key=lambda x: longueur(x, W))
        c = _sol(t, D, T)
        if l1 * c["f1"] / r1 + l2 * c["f2"] / r2 < l1 * a["f1"] / r1 + l2 * a["f2"] / r2 - 1e-9:
            _ajouter(archive, c)
            dicho(a, c, prof + 1)
            dicho(c, b, prof + 1)

    # amorce : quelques ponderations fixes, pour que la dichotomie demarre meme quand une tournee
    # « extreme » (2-opt n'est pas exact) est dominee par une autre
    for lam in np.linspace(0.0, 1.0, nb_amorces):
        W = lam * D / r1 + (1 - lam) * T / r2
        _ajouter(archive, _sol(recherche_locale(plus_proche_voisin(W), W), D, T))
    supportees = sorted(archive, key=lambda s: s["f1"])
    for u, v in zip(supportees[:-1], supportees[1:]):
        dicho(u, v, 0)
    nb_supportees = len(archive)
    suivi.signale(0.2)

    I, J = np.triu_indices(N, k=2)
    garde = ~((I == 0) & (J == N - 1))
    I, J = I[garde], J[garde]
    explorees, nb_explorations = set(), 0
    while not suivi.fini():
        a_explorer = [s for s in archive if tuple(s["tour"]) not in explorees]
        if not a_explorer:
            break
        s = rng.choice(a_explorer)
        explorees.add(tuple(s["tour"]))
        nb_explorations += 1
        t = np.array(s["tour"])
        pa, pb, pc, pd = t[I], t[(I + 1) % N], t[J], t[(J + 1) % N]
        d1 = D[pa, pc] + D[pb, pd] - D[pa, pb] - D[pc, pd]
        d2 = T[pa, pc] + T[pb, pd] - T[pa, pb] - T[pc, pd]
        F = np.column_stack([s["f1"] + d1, s["f2"] + d2])
        A = np.array([(x["f1"], x["f2"]) for x in archive])
        # voisins non (faiblement) domines par l'archive
        domine_par_A = ((A[None, :, 0] <= F[:, None, 0] + 1e-9) & (A[None, :, 1] <= F[:, None, 1] + 1e-9)).any(axis=1)
        cand = np.flatnonzero(~domine_par_A)
        if cand.size:
            for k in [cand[i] for i in non_domines(F[cand])]:
                nt = t.copy()
                nt[I[k] + 1:J[k] + 1] = nt[I[k] + 1:J[k] + 1][::-1]
                _ajouter(archive, _sol(nt, D, T))
        suivi.signale(0.2 + 0.8 * len(explorees) / max(1, len(explorees) + len(a_explorer) - 1))
    archive.sort(key=lambda s: s["f1"])
    return {"solutions": filtrer(archive),
            "stats": {"supportees_phase1": nb_supportees, "explorations": nb_explorations, "graine": seed,
                      "complete": not any(tuple(s["tour"]) not in explorees for s in archive)}}


# =============================================================================
# Methode 4 : epsilon-contrainte exacte
# =============================================================================
class _TSPExact:
    """TSP symetrique en variables d'aretes x_e : degre 2 en chaque noeud, coupes de sous-tours
    DFJ sum_{e in delta(S)} x_e >= 2 ajoutees quand la solution entiere contient un sous-tour.
    Les coupes sont valides pour tous les sous-problemes : elles sont conservees d'un appel a l'autre.
    C'est la formulation equivalente (et plus forte) du modele MTZ du cahier des charges."""

    def __init__(self, D, T):
        self.N = D.shape[0]
        self.U, self.V = np.triu_indices(self.N, k=1)
        self.E = self.U.size
        self.cD, self.cT = D[self.U, self.V], T[self.U, self.V]
        e = np.arange(self.E)
        self.A_deg = sparse.csr_matrix((np.ones(2 * self.E), (np.concatenate([self.U, self.V]), np.concatenate([e, e]))),
                                       shape=(self.N, self.E))
        self.coupes = []
        self.appels = 0

    def _composantes(self, x):
        parent = list(range(self.N))

        def trouve(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a
        for k in np.flatnonzero(x > 0.5):
            parent[trouve(self.U[k])] = trouve(self.V[k])
        comp = {}
        for v in range(self.N):
            comp.setdefault(trouve(v), []).append(v)
        return list(comp.values())

    def resoudre(self, objectif, bornes=(), deadline=math.inf):
        """min objectif.x  s.c. pour (vecteur, rhs) dans bornes : vecteur.x <= rhs.
        Renvoie (x, valeur, statut) avec statut 'optimal', 'infaisable' ou 'temps'."""
        while True:
            reste = deadline - time.perf_counter()
            if reste <= 0:
                return None, math.inf, "temps"
            lignes = [LinearConstraint(self.A_deg, 2, 2)]
            for vec, rhs in bornes:
                lignes.append(LinearConstraint(sparse.csr_matrix(vec[None, :]), -np.inf, rhs))
            if self.coupes:
                lignes.append(LinearConstraint(sparse.vstack(self.coupes).tocsr(), 2, np.inf))
            self.appels += 1
            res = milp(objectif, constraints=lignes, integrality=np.ones(self.E), bounds=Bounds(0, 1),
                       options={"time_limit": max(0.05, reste), "mip_rel_gap": 0.0, "disp": False})
            if res.status == 2:
                return None, math.inf, "infaisable"
            if res.x is None or res.status != 0:
                return None, math.inf, "temps"
            comps = self._composantes(res.x)
            if len(comps) == 1:
                return res.x, float(res.fun), "optimal"
            for S in comps:
                dans = np.zeros(self.N, bool)
                dans[S] = True
                coupe = (dans[self.U] != dans[self.V]).astype(float)
                self.coupes.append(sparse.csr_matrix(coupe[None, :]))

    def tour(self, x):
        voisins = {v: [] for v in range(self.N)}
        for k in np.flatnonzero(x > 0.5):
            voisins[self.U[k]].append(self.V[k])
            voisins[self.V[k]].append(self.U[k])
        t, prec = [0], None
        while len(t) < self.N:
            nxt = [w for w in voisins[t[-1]] if w != prec][0]
            prec = t[-1]
            t.append(int(nxt))
        return t


def _enumeration(D, T):
    """Front exact par enumeration de toutes les tournees (n <= 7 magasins : au plus 2 520 tournees)."""
    n = D.shape[0] - 1
    sols = []
    for p in itertools.permutations(range(1, n + 1)):
        if p[0] < p[-1]:  # chaque cycle n'est compte qu'une fois (symetrie)
            sols.append(_sol([0] + list(p), D, T))
    return filtrer(sols)


def epsilon_contrainte(D, T, time_limit=60, pas=0.01, arret=None, rapport=None, **_):
    """Methode epsilon-contrainte (Haimes et al. 1971) en version lexicographique, exacte :
      1) point de distance minimale : min f1, puis min f2 a f1 optimal ;
      2) eps = f2(point) - pas ; min f1 s.c. f2 <= eps, puis min f2 s.c. f1 <= f1*, f2 <= eps ;
      3) recommencer jusqu'a ce que le probleme devienne infaisable (point de temps minimal atteint).
    Chaque point obtenu est Pareto-optimal ; le front est COMPLET (a la resolution 'pas' minute pres)
    si l'on n'est pas coupe par la limite de temps. n <= 7 : enumeration complete."""
    suivi = _Suivi(time_limit, arret, rapport)
    n = D.shape[0] - 1
    if n <= 2:
        return {"solutions": _trivial(D, T), "stats": {"complet": True, "methode": "triviale"}}
    if n <= 7:
        return {"solutions": _enumeration(D, T), "stats": {"complet": True, "methode": "enumeration"}}
    deadline = suivi.t0 + suivi.limite
    P = _TSPExact(D, T)
    sols, complet, eps = [], False, math.inf
    t_min = None
    while True:
        if suivi.fini():
            break
        bornes = [] if eps == math.inf else [(P.cT, eps)]
        x, v1, st = P.resoudre(P.cD, bornes, deadline)
        if st == "infaisable":
            complet = True
            break
        if st != "optimal":
            break
        x2, _, st2 = P.resoudre(P.cT, bornes + [(P.cD, v1 + 1e-6 * max(1.0, v1))], deadline)
        if st2 != "optimal":
            x2 = x
        s = _sol(P.tour(x2), D, T)
        sols.append(s)
        if t_min is None:  # estimation de l'etendue en temps pour la progression
            t2 = recherche_locale(plus_proche_voisin(T), T)
            t_min = longueur(t2, T)
        eps = s["f2"] - pas
        if eps < 0:
            complet = True
            break
        f0 = sols[0]["f2"]
        suivi.signale(min(0.99, (f0 - s["f2"]) / max(1e-9, f0 - t_min)))
    return {"solutions": filtrer(sols), "stats": {"complet": complet, "methode": "epsilon-contrainte",
                                                   "appels_milp": P.appels, "coupes": len(P.coupes), "pas_min": pas}}


METHODES_TSP = {
    "ws": somme_ponderee,
    "nsga": nsga2,
    "pls": pareto_local_search,
    "eps": epsilon_contrainte,
}


# =============================================================================
# Benchmark TSPLIB bi-objectif (kroA / kroB)
# =============================================================================
def lire_tsplib(chemin):
    """Coordonnees d'un fichier TSPLIB EUC_2D."""
    coords, dans = [], False
    with open(chemin, encoding="utf-8") as fh:
        for ligne in fh:
            ligne = ligne.strip()
            if ligne.startswith("NODE_COORD_SECTION"):
                dans = True
                continue
            if ligne == "EOF":
                break
            if dans and ligne:
                _, x, y = ligne.split()[:3]
                coords.append((float(x), float(y)))
    return np.array(coords)


def matrice_euc2d(xy):
    """Distance EUC_2D de TSPLIB : arrondi a l'entier le plus proche (nint)."""
    d = np.sqrt(((xy[:, None, :] - xy[None, :, :]) ** 2).sum(axis=2))
    return np.floor(d + 0.5)


def instance_kroab(chemin_a, chemin_b, nb_noeuds):
    """Instance bi-objectif classique kroAB : memes villes, f1 sur les coordonnees kroA, f2 sur kroB
    (Lust & Teghem 2010). On garde les nb_noeuds premiers noeuds ; le noeud 1 joue l'entrepot."""
    A, B = lire_tsplib(chemin_a)[:nb_noeuds], lire_tsplib(chemin_b)[:nb_noeuds]
    return matrice_euc2d(A), matrice_euc2d(B)


if __name__ == "__main__":
    rng = np.random.default_rng(0)
    k = 12
    lat, lon = 36.8 + rng.normal(0, 0.15, k), 10.2 + rng.normal(0, 0.15, k)
    D, T = matrices([f"P{i}" for i in range(k)], lat, lon)
    for nom, fn in METHODES_TSP.items():
        t0 = time.perf_counter()
        r = fn(D, T, time_limit=30, seed=0)
        pts = [(round(s["f1"], 1), round(s["f2"], 1)) for s in r["solutions"]]
        print(f"{nom:5} {len(pts):3} points  {time.perf_counter() - t0:6.2f}s  {pts[:4]}...  {r['stats']}")
