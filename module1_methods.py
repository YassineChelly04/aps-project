# -*- coding: utf-8 -*-
"""
Projet APS - Module 1 : affectation des points de vente aux entrepots.

Implementation de 2 methodes exactes de la litterature recente
--------------------------------------------------------------
  1. gadegaard2018_cut_and_solve       Gadegaard, Klose & Nielsen (2018), EURO J. Comput. Optim. 6(1)
  2. ryu_park2021_branch_and_price     Ryu & Park (2021), arXiv:2103.13010  (SSCFLP robuste)

Notations (identiques au document « 6 articles, 1 exemple ») :
  i = entrepot (m), j = magasin (n), c[i, j] = cout d'affectation, d[j] = demande,
  s[i] = capacite, f[i] = cout fixe d'ouverture.

  SSCFLP : min sum c_ij x_ij + sum f_i y_i
           sum_i x_ij = 1,  sum_j d_j x_ij <= s_i y_i,  x_ij <= y_i,  x, y binaires
  GAP    : memes contraintes, tous les entrepots ouverts, sans couts fixes.

L'objet Solution renvoye contient toujours les deux valeurs (cout SSCFLP et cout
d'affectation).

Dependances : numpy, scipy (HiGHS pour les LP du branch-and-price), pulp (solveur CBC).
Les demandes et capacites doivent etre entieres (programmation dynamique des sacs a dos).
"""
from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass, field

import numpy as np
import pulp
from scipy import sparse
from scipy.optimize import linprog

TOL = 1e-6


# =============================================================================
# Donnees
# =============================================================================
@dataclass
class Instance:
    c: np.ndarray  # (m, n) cout d'affectation du magasin j a l'entrepot i
    d: np.ndarray  # (n,)   demandes
    s: np.ndarray  # (m,)   capacites
    f: np.ndarray  # (m,)   couts fixes (mettre 0 pour un GAP pur)
    name: str = "instance"
    customers_xy: np.ndarray | None = None   # (n, 2) lat, lon (optionnel, pour la carte)
    facilities_xy: np.ndarray | None = None  # (m, 2)

    def __post_init__(self):
        self.c = np.asarray(self.c, dtype=float)
        self.d = np.asarray(self.d, dtype=float)
        self.s = np.asarray(self.s, dtype=float)
        self.f = np.asarray(self.f, dtype=float)
        m, n = self.c.shape
        if self.d.shape != (n,) or self.s.shape != (m,) or self.f.shape != (m,):
            raise ValueError("Dimensions incoherentes entre c, d, s et f.")

    @property
    def m(self) -> int:
        return self.c.shape[0]

    @property
    def n(self) -> int:
        return self.c.shape[1]

    @property
    def total_demand(self) -> float:
        return float(self.d.sum())

    def int_data(self):
        """Demandes et capacites entieres (necessaires aux sacs a dos par programmation dynamique)."""
        if not np.allclose(self.d, np.round(self.d)):
            raise ValueError("Les demandes doivent etre entieres.")
        return np.round(self.d).astype(np.int64), np.floor(self.s + 1e-9).astype(np.int64)

    def costs_are_integral(self) -> bool:
        return bool(np.allclose(self.c, np.round(self.c)) and np.allclose(self.f, np.round(self.f)))


def example_instance() -> Instance:
    """Exemple commun du document : 2 entrepots (A, B), 3 magasins.
    SSCFLP : optimum 19 (A seul). GAP (A et B ouverts) : optimum 6 avec 1->A, 2->A, 3->B."""
    return Instance(c=[[2, 3, 4], [3, 2, 1]], d=[4, 3, 5], s=[12, 7], f=[10, 6], name="exemple_2x3")


def generate_instance(m: int, n: int, seed: int = 0, capacity_ratio: float = 1.3,
                      demand_range=(10, 100), unit_cost: float = 0.01,
                      fixed_cost_factor=(0.3, 0.6), name: str | None = None) -> Instance:
    """Instance aleatoire dans l'emprise de la Tunisie (cahier des charges, source B).
    c_ij = distance (km) x cout unitaire x demande ; capacite totale = capacity_ratio x demande totale."""
    rng = np.random.default_rng(seed)
    cust = np.column_stack([rng.uniform(30.5, 37.2, n), rng.uniform(8.0, 11.2, n)])
    fac = np.column_stack([rng.uniform(30.5, 37.2, m), rng.uniform(8.0, 11.2, m)])
    d = rng.integers(demand_range[0], demand_range[1] + 1, n).astype(float)
    w = rng.uniform(0.7, 1.3, m)
    s = np.floor(w / w.sum() * capacity_ratio * d.sum())
    s = np.maximum(s, d.max())
    lat1, lon1 = np.radians(fac[:, 0])[:, None], np.radians(fac[:, 1])[:, None]
    lat2, lon2 = np.radians(cust[:, 0])[None, :], np.radians(cust[:, 1])[None, :]
    h = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    dist = 2 * 6371.0 * np.arcsin(np.sqrt(h))
    c = np.round(dist * unit_cost * d[None, :], 2)
    f = np.round(rng.uniform(*fixed_cost_factor, m) * c.mean() * n / m, 2)
    return Instance(c, d, s, f, name=name or f"rand_{m}x{n}_s{seed}", customers_xy=cust, facilities_xy=fac)


# =============================================================================
# Solution et evaluation
# =============================================================================
@dataclass
class Solution:
    method: str
    objective: str               # "SSCFLP" ou "GAP" : la fonction que la methode optimise
    assign: np.ndarray           # assign[j] = entrepot du magasin j
    cost: float                  # cout SSCFLP = affectation + couts fixes des entrepots utilises
    assign_cost: float           # cout d'affectation seul (objectif du GAP)
    open_facilities: list
    feasible: bool
    lower_bound: float | None
    proven_optimal: bool
    time: float
    info: dict = field(default_factory=dict)

    @property
    def value(self) -> float:
        return self.cost if self.objective == "SSCFLP" else self.assign_cost

    @property
    def gap(self) -> float | None:
        if self.lower_bound is None or not self.feasible:
            return None
        return max(0.0, (self.value - self.lower_bound) / max(abs(self.value), 1e-9))

    def __str__(self):
        lb = "-" if self.lower_bound is None else f"{self.lower_bound:.2f}"
        gap = "-" if self.gap is None else f"{100 * self.gap:.2f}%"
        return (f"{self.method:<34} [{self.objective}] valeur={self.value:.2f} "
                f"(SSCFLP={self.cost:.2f}, affect.={self.assign_cost:.2f}) LB={lb} gap={gap} "
                f"opt={'oui' if self.proven_optimal else 'non'} realisable={self.feasible} "
                f"ouverts={self.open_facilities} t={self.time:.2f}s")


def evaluate(inst: Instance, assign: np.ndarray):
    assign = np.asarray(assign, dtype=int)
    n = inst.n
    if assign.shape != (n,) or (assign < 0).any():
        return math.inf, math.inf, [], False, np.zeros(inst.m)
    load = np.bincount(assign, weights=inst.d, minlength=inst.m)
    used = np.bincount(assign, minlength=inst.m) > 0
    a_cost = float(inst.c[assign, np.arange(n)].sum())
    cost = a_cost + float(inst.f[used].sum())
    feasible = bool((load <= inst.s + TOL).all())
    return cost, a_cost, [int(i) for i in np.flatnonzero(used)], feasible, load


def make_solution(inst, assign, method, objective, t0, lower_bound=None, proven=False, info=None):
    cost, a_cost, used, feas, load = evaluate(inst, assign)
    info = dict(info or {})
    info["loads"] = load.tolist()
    return Solution(method, objective, np.asarray(assign, dtype=int), cost, a_cost, used, feas,
                    lower_bound, proven, time.time() - t0, info)


# =============================================================================
# Outils communs
# =============================================================================
def knapsack_max(profit, weight, cap):
    """Sac a dos 0-1 par programmation dynamique : max sum p_k z_k  s.c. sum w_k z_k <= cap.
    Seuls les objets de profit > 0 sont consideres. Complexite O(nb_objets x cap).
    Renvoie (valeur, indices choisis)."""
    profit = np.asarray(profit, dtype=float)
    weight = np.asarray(weight, dtype=np.int64)
    cap = int(math.floor(cap + 1e-9))
    if cap < 0:
        return -math.inf, np.array([], dtype=int)
    items = np.flatnonzero((profit > 1e-12) & (weight <= cap))
    if items.size == 0:
        return 0.0, np.array([], dtype=int)
    if weight[items].sum() <= cap:  # tout rentre
        return float(profit[items].sum()), items
    dp = np.zeros(cap + 1)
    keep = np.zeros((items.size, cap + 1), dtype=bool)
    for t, k in enumerate(items):
        w = int(weight[k])
        cand = dp[: cap + 1 - w] + profit[k]
        better = cand > dp[w:] + 1e-12
        keep[t, w:] = better
        dp[w:] = np.where(better, cand, dp[w:])
    chosen, r = [], cap
    for t in range(items.size - 1, -1, -1):
        if keep[t, r]:
            chosen.append(items[t])
            r -= int(weight[items[t]])
    return float(dp[cap]), np.array(sorted(chosen), dtype=int)


def regret_greedy(C, d, s, open_mask=None, allowed=None):
    """Glouton par regret (cahier des charges) : on affecte d'abord le magasin dont l'ecart
    entre les deux meilleurs entrepots realisables est le plus grand. Renvoie None si echec."""
    m, n = C.shape
    avail = np.ones(m, bool) if open_mask is None else np.asarray(open_mask, bool)
    resid = np.where(avail, s, -1.0).astype(float)
    assign = np.full(n, -1, dtype=int)
    todo = np.ones(n, bool)
    for _ in range(n):
        J = np.flatnonzero(todo)
        feas = (resid[:, None] >= d[None, J] - TOL) & avail[:, None]
        if allowed is not None:
            feas &= allowed[:, J]
        if not feas.any(axis=0).all():
            return None
        cost = np.where(feas, C[:, J], np.inf)
        srt = np.sort(cost, axis=0)
        best = srt[0]
        second = srt[1] if m > 1 else np.full(J.size, np.inf)
        regret = np.where(np.isfinite(second), second - best, 1e18)
        k = np.lexsort((d[J], regret))[-1]
        j, i = J[k], int(np.argmin(cost[:, k]))
        assign[j] = i
        resid[i] -= d[j]
        todo[j] = False
    return assign


def local_search(C, d, s, assign, f=None, allowed=None, max_rounds=100):
    """Descente « deplacer » (un magasin change d'entrepot) + « echanger » (deux magasins
    permutent). Si f est donne, l'ouverture/fermeture induite est comptee (SSCFLP)."""
    m, n = C.shape
    a = np.asarray(assign, dtype=int).copy()
    load = np.bincount(a, weights=d, minlength=m).astype(float)
    cnt = np.bincount(a, minlength=m)
    fz = np.zeros(m) if f is None else np.asarray(f, float)
    ar = np.arange(n)
    for _ in range(max_rounds):
        improved = False
        for j in range(n):  # deplacer
            i0 = a[j]
            feas = load + d[j] <= s + TOL
            feas[i0] = False
            if allowed is not None:
                feas &= allowed[:, j]
            if not feas.any():
                continue
            delta = C[:, j] - C[i0, j] + np.where(cnt == 0, fz, 0.0) - (fz[i0] if cnt[i0] == 1 else 0.0)
            delta = np.where(feas, delta, np.inf)
            i = int(np.argmin(delta))
            if delta[i] < -1e-9:
                a[j] = i
                load[i0] -= d[j]; load[i] += d[j]
                cnt[i0] -= 1; cnt[i] += 1
                improved = True
        for j1 in range(n):  # echanger
            a1 = a[j1]
            a2 = a
            mask = (a2 != a1) & (ar > j1)
            if not mask.any():
                continue
            feas = mask & (load[a1] - d[j1] + d <= s[a1] + TOL) & (load[a2] - d + d[j1] <= s[a2] + TOL)
            if allowed is not None:
                feas &= allowed[a2, j1] & allowed[a1, ar]
            if not feas.any():
                continue
            delta = C[a2, j1] + C[a1, ar] - C[a1, j1] - C[a2, ar]
            delta = np.where(feas, delta, np.inf)
            j2 = int(np.argmin(delta))
            if delta[j2] < -1e-9:
                i2 = a[j2]
                load[a1] += d[j2] - d[j1]
                load[i2] += d[j1] - d[j2]
                a[j1], a[j2] = i2, a1
                improved = True
        if not improved:
            break
    return a


def greedy_sscflp(inst: Instance, candidates=None, ratio=1.05, capacities=None):
    """Solution initiale SSCFLP : on ouvre les entrepots par cout unitaire croissant jusqu'a
    couvrir ratio x demande, glouton par regret, descente, puis on essaie de fermer chaque
    entrepot (phase « drop »)."""
    m = inst.m
    s = inst.s if capacities is None else np.asarray(capacities, float)
    cand = np.ones(m, bool) if candidates is None else np.asarray(candidates, bool)
    D = inst.total_demand
    u = inst.f / np.maximum(s, 1) + inst.c.sum(axis=1) / D
    order = [i for i in np.argsort(u) if cand[i]]
    open_mask = np.zeros(m, bool)
    a = None
    for i in order:
        open_mask[i] = True
        if s[open_mask].sum() >= ratio * D:
            a = regret_greedy(inst.c, inst.d, s, open_mask)
            if a is not None:
                break
    if a is None:
        a = regret_greedy(inst.c, inst.d, s, cand)
        if a is None:
            return None
    a = local_search(inst.c, inst.d, s, a, inst.f)
    best = _cost_with(inst, a, s)
    improved = True
    while improved:
        improved = False
        for i in np.unique(a):
            mask = np.zeros(m, bool)
            mask[np.unique(a)] = True
            mask[i] = False
            if not mask.any():
                continue
            a2 = regret_greedy(inst.c, inst.d, s, mask)
            if a2 is None:
                continue
            a2 = local_search(inst.c, inst.d, s, a2, inst.f)
            c2 = _cost_with(inst, a2, s)
            if c2 < best - 1e-9:
                a, best, improved = a2, c2, True
                break
    return a


def _cost_with(inst, a, s):
    load = np.bincount(a, weights=inst.d, minlength=inst.m)
    if (load > s + TOL).any():
        return math.inf
    used = np.bincount(a, minlength=inst.m) > 0
    return float(inst.c[a, np.arange(inst.n)].sum() + inst.f[used].sum())


# ----------------------------------------------------------------------------- MIP (PuLP / CBC)
def solve_mip(prob, time_limit, warm=False, msg=False):
    """Resout avec CBC. Renvoie (solution_disponible, optimalite_prouvee, infaisable)."""
    tl = max(1, int(math.ceil(time_limit)))
    # Sous Windows, le demarrage a chaud de CBC via PuLP exige keepFiles=True : on le desactive
    # (sans effet sur les resultats : chaque methode garde de toute facon sa meilleure solution).
    warm = warm and os.name != "nt"
    prob.solve(pulp.PULP_CBC_CMD(msg=msg, timeLimit=tl, warmStart=warm))
    has = prob.sol_status in (pulp.LpSolutionOptimal, pulp.LpSolutionIntegerFeasible)
    proven = prob.status == pulp.LpStatusOptimal and prob.sol_status == pulp.LpSolutionOptimal
    infeasible = prob.status == pulp.LpStatusInfeasible
    return has, proven, infeasible


def build_sscflp(inst: Instance, *, relax=False, relax_x=False, cuts=(), y_fixed0=(), y_fixed1=(),
                 allowed=None, name="SSCFLP"):
    """Modele SSCFLP (forme forte, avec x_ij <= y_i et la contrainte de demande totale).
    cuts : liste de (coefs, rhs) avec coefs = {('x', i, j): a, ('y', i): b}, sens <=."""
    m, n = inst.m, inst.n
    xcat = pulp.LpContinuous if (relax or relax_x) else pulp.LpBinary
    ycat = pulp.LpContinuous if relax else pulp.LpBinary
    prob = pulp.LpProblem(name, pulp.LpMinimize)
    y = {i: pulp.LpVariable(f"y_{i}", 0, 1, ycat) for i in range(m)}
    alw = np.ones((m, n), bool) if allowed is None else allowed
    x = {(i, j): pulp.LpVariable(f"x_{i}_{j}", 0, 1, xcat) for i in range(m) for j in range(n) if alw[i, j]}
    prob += (pulp.lpSum(inst.c[i, j] * v for (i, j), v in x.items())
             + pulp.lpSum(inst.f[i] * y[i] for i in range(m)))
    for j in range(n):
        prob += pulp.lpSum(x[i, j] for i in range(m) if (i, j) in x) == 1, f"assign_{j}"
    for i in range(m):
        prob += pulp.lpSum(inst.d[j] * x[i, j] for j in range(n) if (i, j) in x) <= inst.s[i] * y[i], f"cap_{i}"
    for (i, j), v in x.items():
        prob += v <= y[i], f"vub_{i}_{j}"
    prob += pulp.lpSum(inst.s[i] * y[i] for i in range(m)) >= inst.total_demand, "total_demand"
    for i in y_fixed0:
        y[i].upBound = 0
    for i in y_fixed1:
        y[i].lowBound = 1
    for k, (coefs, rhs) in enumerate(cuts):
        expr = []
        for key, a in coefs.items():
            if key[0] == "y":
                expr.append(a * y[key[1]])
            elif (key[1], key[2]) in x:
                expr.append(a * x[key[1], key[2]])
        prob += pulp.lpSum(expr) <= rhs, f"cut_{k}"
    return prob, x, y


def _warm_start(x, y, assign):
    """Donne la solution courante comme point de depart, si elle respecte les bornes du modele."""
    used = set(int(i) for i in assign)
    if any((i, int(assign[j])) not in x for j, i in enumerate(assign)):
        return False
    if any((v.upBound is not None and (i in used) > v.upBound) or (v.lowBound or 0) > (i in used)
           for i, v in y.items()):
        return False
    for (i, j), v in x.items():
        v.setInitialValue(1 if assign[j] == i else 0)
    for i, v in y.items():
        v.setInitialValue(1 if i in used else 0)
    return True


def _x_values(inst, x):
    X = np.zeros((inst.m, inst.n))
    for (i, j), v in x.items():
        X[i, j] = v.varValue or 0.0
    return X


def _assign_from_x(inst, x):
    return np.argmax(_x_values(inst, x), axis=0).astype(int)


def _log(verbose, *args):
    if verbose:
        print(*args, flush=True)


# =============================================================================
# 1. Gadegaard, Klose & Nielsen (2018) - cut-and-solve ameliore (EXACTE, SSCFLP)
# =============================================================================
def separate_lifted_cover(w, cap, v):
    """Separation d'une inegalite de couverture relevee (lifted cover) pour le sac a dos
    sum w_k z_k <= cap au point v in [0,1]^K.
      1) couverture C minimisant sum_{C}(1 - v_k) (resolu exactement par DP) ;
      2) C rendue minimale (on retire les objets de plus petit v) ;
      3) relevement sequentiel exact des autres objets (DP), par v decroissant.
    Renvoie (alpha, r) pour l'inegalite sum alpha_k z_k <= r, ou None."""
    w = np.asarray(w, dtype=np.int64)
    v = np.clip(np.asarray(v, dtype=float), 0.0, 1.0)
    W = int(w.sum())
    if W <= cap:
        return None
    _, keep_out = knapsack_max(1.0 - v + 1e-9, w, W - cap - 1)  # objets HORS couverture
    inC = np.ones(w.size, bool)
    inC[keep_out] = False
    if w[inC].sum() <= cap:
        return None
    if (1.0 - v[inC]).sum() >= 1.0 + 0.5:  # couverture tres loin d'etre violee : on abandonne
        return None
    for k in sorted(np.flatnonzero(inC), key=lambda k: v[k]):  # minimalite
        if w[inC].sum() - w[k] > cap:
            inC[k] = False
    alpha = np.zeros(w.size)
    alpha[inC] = 1.0
    r = int(inC.sum()) - 1
    members = list(np.flatnonzero(inC))
    for k in sorted(np.flatnonzero(~inC & (v > 1e-9)), key=lambda k: -v[k]):
        rest = cap - int(w[k])
        if rest < 0:
            ak = r
        else:
            best, _ = knapsack_max(alpha[members], w[members], rest)
            ak = r - best
        if ak > 1e-9:
            alpha[k] = ak
            members.append(k)
    if alpha @ v > r + 1e-6:
        return alpha, r
    return None


def gadegaard2018_cut_and_solve(inst: Instance, time_limit=120, max_cut_rounds=30, pair_cuts=True,
                                k_y=None, k_x=None, heuristic_time_frac=0.3, node_time=None,
                                verbose=False) -> Solution:
    """Algorithme en trois phases (Gadegaard, Klose & Nielsen, 2018). Les details (coupes sur
    paires d'entrepots, Omega = {i : y_i^DP = 0}) suivent le preprint compagnon de Gadegaard
    (2016, Optimization Online 5415, Algorithme 6 et section 4.3) qui resume la methode de 2018 :
    Phase 1 - plans coupants : relaxation LP renforcee par
        (a) les bornes x_ij <= y_i, (b) des inegalites de couverture relevees separees sur
        chaque contrainte de capacite sum_j d_j x_ij <= s_i y_i (point x_i / y_i, coupe
        alpha.x_i <= r y_i), (c) si rien n'est trouve, des coupes sur la « capacite effective »
        d'une paire d'entrepots : sum_j d_j (x_i1j + x_i2j) + s_i1 (1-y_i1) + s_i2 (1-y_i2)
        <= s_i1 + s_i2 (les coupes de Fenchel de l'article ne sont pas reprises).
    Phase 2 - branchement local a deux niveaux : d'abord sur les y (Hamming(y, y_bar) <= k_y),
        puis sur les x (nombre de magasins reaffectes <= k_x), chaque fois suivi d'une
        descente « deplacer / echanger ».
    Phase 3 - cut-and-solve : probleme dense DP = CFLP (x continus, y binaires) + coupes
        percantes ; Omega = {i : y_i^DP = 0} ; probleme epars SP = SSCFLP avec y_i = 0 pour
        i in Omega (gamma = 0), resolu exactement ; coupe percante sum_{Omega} y_i >= 1.
        Arret quand Z_DP >= meilleure solution : optimum prouve."""
    t0 = time.time()
    deadline = t0 + time_limit
    m, n = inst.m, inst.n
    d_int, s_int = inst.int_data()
    integral = inst.costs_are_integral()
    rnd_lb = (lambda z: math.ceil(z - 1e-6) if math.isfinite(z) else z) if integral else (lambda z: z)
    info = {}

    # ---------------- Phase 1 : plans coupants
    cuts, prev, lb, lp0 = [], -math.inf, -math.inf, None
    X = Y = None
    for rnd in range(max_cut_rounds):
        prob, x, y = build_sscflp(inst, relax=True, cuts=cuts, name="LP")
        solve_mip(prob, max(1, deadline - time.time()))
        z = pulp.value(prob.objective)
        X = _x_values(inst, x)
        Y = np.array([y[i].varValue or 0.0 for i in range(m)])
        if lp0 is None:
            lp0 = z
        lb = max(lb, z)
        _log(verbose, f"[Gadegaard] tour {rnd}: LP = {z:.4f}, coupes = {len(cuts)}")
        if np.all(np.minimum(X, 1 - X) < TOL) and np.all(np.minimum(Y, 1 - Y) < TOL):
            break  # solution LP entiere
        if rnd > 0 and z - prev < 1e-4 * max(1.0, abs(z)):
            break
        prev = z
        new = []
        for i in range(m):
            if Y[i] < 1e-6:
                continue
            res = separate_lifted_cover(d_int, s_int[i], X[i] / Y[i])
            if res is None:
                continue
            alpha, r = res
            if alpha @ X[i] - r * Y[i] > 1e-6:
                coefs = {("x", i, j): float(alpha[j]) for j in range(n) if alpha[j] > 0}
                coefs[("y", i)] = -float(r)
                new.append((coefs, 0.0))
        if not new and pair_cuts:
            for i1 in range(m):
                for i2 in range(i1 + 1, m):
                    if Y[i1] < 1e-6 and Y[i2] < 1e-6:
                        continue
                    w = np.concatenate([d_int, [s_int[i1], s_int[i2]]])
                    v = np.concatenate([np.minimum(X[i1] + X[i2], 1.0), [1 - Y[i1], 1 - Y[i2]]])
                    res = separate_lifted_cover(w, int(s_int[i1] + s_int[i2]), v)
                    if res is None:
                        continue
                    alpha, r = res
                    p1, p2 = alpha[n], alpha[n + 1]
                    coefs = {}
                    for j in range(n):
                        if alpha[j] > 0:
                            coefs[("x", i1, j)] = float(alpha[j])
                            coefs[("x", i2, j)] = float(alpha[j])
                    coefs[("y", i1)] = -float(p1)
                    coefs[("y", i2)] = -float(p2)
                    rhs = float(r - p1 - p2)
                    lhs = sum(a * (X[k[1], k[2]] if k[0] == "x" else Y[k[1]]) for k, a in coefs.items())
                    if lhs > rhs + 1e-6:
                        new.append((coefs, rhs))
        if not new:
            break
        cuts += new
    info.update(lp_bound=lp0, lp_bound_with_cuts=lb, n_cuts=len(cuts))

    # ---------------- Phase 2 : branchement local a deux niveaux
    inc = greedy_sscflp(inst)
    if inc is None:
        inc = regret_greedy(inst.c, inst.d, inst.s)
    ub = _cost_with(inst, inc, inst.s) if inc is not None else math.inf
    info["ub_greedy"] = ub
    h_deadline = time.time() + heuristic_time_frac * max(0.0, deadline - time.time())
    nt = node_time or max(2.0, time_limit / 20)
    ky = k_y or max(1, math.ceil(0.2 * m))
    kx = k_x or max(2, math.ceil(0.1 * n))
    if inc is not None:
        for level, k0, kmax in (("y", ky, m), ("x", kx, n)):
            k = k0
            while time.time() < h_deadline:
                prob, x, y = build_sscflp(inst, cuts=cuts, name=f"LB_{level}")
                if level == "y":
                    used = set(int(i) for i in inc)
                    prob += (pulp.lpSum(1 - y[i] for i in range(m) if i in used)
                             + pulp.lpSum(y[i] for i in range(m) if i not in used)) <= k, "local_branching"
                else:
                    prob += pulp.lpSum(1 - x[int(inc[j]), j] for j in range(n)) <= k, "local_branching"
                _warm_start(x, y, inc)
                has, proven, _ = solve_mip(prob, min(nt, max(1, h_deadline - time.time())), warm=True)
                improved = False
                if has:
                    a = local_search(inst.c, inst.d, inst.s, _assign_from_x(inst, x), inst.f)
                    ca = _cost_with(inst, a, inst.s)
                    if ca < ub - 1e-6:
                        inc, ub, improved, k = a, ca, True, k0
                        _log(verbose, f"[Gadegaard] branchement local ({level}, k={k}) : UB = {ub:.4f}")
                if improved:
                    continue
                if proven and k < kmax:
                    k = min(kmax, k + k0)  # voisinage epuise : on l'elargit
                    continue
                break
    info["ub_local_branching"] = ub

    # ---------------- Phase 3 : cut-and-solve
    piercing, exact, levels = [], True, 0
    lb_final = rnd_lb(lb)
    while True:
        if lb_final >= ub - 1e-6:
            break
        rem = deadline - time.time()
        if rem <= 0:
            exact = False
            break
        prob, x, y = build_sscflp(inst, relax_x=True, cuts=cuts + piercing, name="DP")
        has, proven, infeas = solve_mip(prob, rem)
        if infeas:  # tout l'espace a ete couvert par les SP
            lb_final = ub
            break
        if has and proven:
            zdp = pulp.value(prob.objective)
            ydp = np.array([y[i].varValue or 0.0 for i in range(m)])
        else:  # DP non resolu : borne LP du probleme dense, Omega tire de la meilleure solution
            exact = False
            lp, xl, yl = build_sscflp(inst, relax=True, cuts=cuts + piercing, name="DP_LP")
            solve_mip(lp, max(1, deadline - time.time()))
            zdp = pulp.value(lp.objective)
            ydp = (np.array([y[i].varValue or 0.0 for i in range(m)]) if has
                   else np.array([yl[i].varValue or 0.0 for i in range(m)]))
        zdp_r = rnd_lb(zdp)
        lb_final = max(lb_final, min(zdp_r, ub)) if exact else lb_final
        _log(verbose, f"[Gadegaard] niveau {levels}: Z_DP = {zdp:.4f}, UB = {ub:.4f}")
        if zdp_r >= ub - 1e-6:
            lb_final = ub
            break
        omega = [i for i in range(m) if ydp[i] < 0.5]
        levels += 1
        sp, xs, ys = build_sscflp(inst, cuts=cuts + piercing, y_fixed0=omega, name="SP")
        warm = inc is not None and _warm_start(xs, ys, inc)
        has, proven, infeas = solve_mip(sp, max(1, deadline - time.time()), warm=warm)
        if has:
            a = _assign_from_x(inst, xs)
            ca = _cost_with(inst, a, inst.s)
            if ca < ub - 1e-6:
                inc, ub = a, ca
                _log(verbose, f"[Gadegaard] SP niveau {levels}: nouvelle solution {ub:.4f}")
        if not (proven or infeas):
            exact = False
        if not omega:  # SP = tout l'espace restant
            if proven or infeas:
                lb_final = ub
            break
        piercing.append(({("y", i): -1.0 for i in omega}, -1.0))  # sum_{Omega} y_i >= 1
    info.update(cut_and_solve_levels=levels, exact=exact)
    if inc is None:
        return Solution("Gadegaard 2018 (cut-and-solve)", "SSCFLP", np.full(n, -1), math.inf, math.inf,
                        [], False, lb_final, False, time.time() - t0, info)
    proven = exact and lb_final >= ub - 1e-6
    return make_solution(inst, inc, "Gadegaard 2018 (cut-and-solve)", "SSCFLP", t0,
                         lower_bound=min(lb_final, ub) if exact else rnd_lb(lb), proven=proven, info=info)


# =============================================================================
# 2. Ryu & Park (2021) - branch-and-price pour le SSCFLP robuste (EXACTE)
# =============================================================================
def ryu_park2021_branch_and_price(inst: Instance, gamma=0, deviations=None, time_limit=120,
                                  max_nodes=100000, cols_per_facility=5, root_rmp_heuristic=True,
                                  smoothing=0.5, lagr_warmstart_iters=200, rmp_heuristic_frac=0.15,
                                  verbose=False) -> Solution:
    """Branch-and-price de Ryu & Park (2021).
    Incertitude a cardinalite : d_j peut monter jusqu'a d_j + b_j, au plus Gamma_i demandes
    devient en meme temps parmi celles servies par l'entrepot i. Capacite robuste :
        sum_j d_j x_ij + max_{|R|<=Gamma_i} sum_{j in R} b_j x_ij <= s_i y_i.
    Probleme maitre (Dantzig-Wolfe) : une colonne (i, R) = groupe R de magasins robuste-realisable
    pour i, de cout f_i + sum_{j in R} c_ij ;  min sum cout z  s.c.  sum_{(i,R) : j in R} z >= 1 (lambda_j),
    sum_R z_R^i <= 1 (mu_i), z >= 0.  Une colonne factice couvre tout a un cout tres eleve.
    Pricing de l'entrepot i : max sum_j (lambda_j - c_ij) x_j sur l'ensemble robuste, resolu
    exactement par n - Gamma_i + 1 sacs a dos classiques (Lee et al.) : pour theta parmi les b
    tries, poids d_j + (b_j - theta)^+ et capacite s_i - Gamma_i theta.
    Cout reduit : f_i - mu_i - xi_i. Borne lagrangienne a chaque tour :
        sum_j lambda_j + sum_i min(0, f_i - xi_i)   (f_i - xi_i si y_i = 1 est impose).
    Branchement : y_i le plus proche de 0,5 ; puis, si les y sont entiers, dichotomie GUB sur un
    magasin j fractionnaire (x_ij = 0 pour i in S1 | x_ij = 0 pour i hors S1). Parcours en profondeur.
    gamma = 0 (ou deviations = None) donne le SSCFLP nominal."""
    t0 = time.time()
    deadline = t0 + time_limit
    m, n = inst.m, inst.n
    d_int, s_int = inst.int_data()
    b = np.zeros(n, dtype=np.int64) if deviations is None else np.round(np.asarray(deviations)).astype(np.int64)
    G = np.broadcast_to(np.asarray(gamma, dtype=int), (m,)).copy()
    integral = inst.costs_are_integral()
    rnd_lb = (lambda z: math.ceil(z - 1e-6) if math.isfinite(z) else z) if integral else (lambda z: z)
    BIG = 2 * (inst.c.sum() + inst.f.sum()) + inst.f.sum()
    b_desc = np.sort(b)[::-1]

    thetas = []
    for i in range(m):
        if G[i] <= 0 or b.max() == 0:
            thetas.append([int(b.max())])  # nominal : poids d_j
        elif G[i] >= n:
            thetas.append([0])
        else:
            thetas.append(sorted(set(int(t) for t in b_desc[G[i] - 1:]) | {0}, reverse=True))

    def robust_ok(i, mask):
        dev = np.sort(b[mask])[::-1][: max(G[i], 0)].sum()
        return d_int[mask].sum() + dev <= s_int[i]

    def price(i, profit):
        found = {}
        for th in thetas[i]:
            wgt = d_int + np.maximum(b - th, 0)
            val, R = knapsack_max(profit, wgt, s_int[i] - G[i] * th)
            if val == -math.inf:
                continue
            key = tuple(int(k) for k in R)
            if key not in found or val > found[key]:
                found[key] = val
        res = sorted(((v, k) for k, v in found.items()), reverse=True)
        return res if res else [(0.0, ())]

    # pool de colonnes
    cols_i, cols_mask, cols_cost, seen = [], [], [], set()

    def add_col(i, R):
        key = (i, tuple(sorted(int(j) for j in R)))
        if key in seen:
            return False
        mask = np.zeros(n, bool)
        mask[list(key[1])] = True
        if not robust_ok(i, mask):
            return False
        seen.add(key)
        cols_i.append(i)
        cols_mask.append(mask)
        cols_cost.append(float(inst.f[i] + inst.c[i, mask].sum()))
        return True

    for i in range(m):
        add_col(i, ())
        for j in range(n):
            add_col(i, (j,))

    # solution initiale (capacites reduites du pire ecart global => toujours robuste)
    ub, inc = math.inf, None
    s_safe = inst.s - np.array([b_desc[: max(G[i], 0)].sum() for i in range(m)])
    g0 = greedy_sscflp(inst, capacities=s_safe) if (s_safe >= inst.d.max()).any() else None
    def improve(a):
        """Descente deplacer/echanger qui reste robuste : un entrepot ne recoit un magasin que si
        sa charge reste <= s_i - (somme des Gamma_i plus grands ecarts), borne prudente."""
        a2 = local_search(inst.c, inst.d, s_safe, a, inst.f)
        ok = all(robust_ok(int(i), a2 == i) for i in np.unique(a2))
        return a2 if ok and _cost_with(inst, a2, inst.s) <= _cost_with(inst, a, inst.s) else a

    if g0 is not None:
        inc, ub = g0, _cost_with(inst, g0, inst.s)
        for i in np.unique(g0):
            add_col(int(i), np.flatnonzero(g0 == i))

    cache = {"K": -1}

    def col_arrays():
        if cache["K"] != len(cols_i):
            cache.update(K=len(cols_i), I=np.array(cols_i), M=np.array(cols_mask), cost=np.array(cols_cost))
        return cache["I"], cache["M"], cache["cost"]

    def solve_rmp(y0, y1, forbid):
        CI, CM, CC = col_arrays()
        ok = ~np.isin(CI, list(y0)) & ~(CM & forbid[CI]).any(axis=1)
        elig = np.flatnonzero(ok)
        K = elig.size + 1
        cost = np.concatenate([CC[elig], [BIG]])
        Mcov = sparse.csr_matrix(CM[elig].T.astype(float))
        A_cov = -sparse.hstack([Mcov, sparse.csr_matrix(np.ones((n, 1)))]).tocsr()
        ub_fac = [i for i in range(m) if i not in y0 and i not in y1]
        eq_fac = sorted(y1)

        def fac_rows(fl):
            pos = {i: a for a, i in enumerate(fl)}
            t = np.array([t for t, k in enumerate(elig) if CI[k] in pos], dtype=int)
            r = np.array([pos[CI[elig[k]]] for k in t], dtype=int)
            return sparse.csr_matrix((np.ones(t.size), (r, t)), shape=(len(fl), K))
        A_ub = sparse.vstack([A_cov, fac_rows(ub_fac)]).tocsr() if ub_fac else A_cov
        b_ub = np.concatenate([-np.ones(n), np.ones(len(ub_fac))])
        kw = {}
        if eq_fac:
            kw = dict(A_eq=fac_rows(eq_fac), b_eq=np.ones(len(eq_fac)))
        res = linprog(cost, A_ub=A_ub, b_ub=b_ub, bounds=(0, None), method="highs", **kw)
        if res.status != 0:
            return None
        lam = np.maximum(-res.ineqlin.marginals[:n], 0.0)
        mu = np.zeros(m)
        for a, i in enumerate(ub_fac):
            mu[i] = res.ineqlin.marginals[n + a]
        for a, i in enumerate(eq_fac):
            mu[i] = res.eqlin.marginals[a]
        return res.fun, res.x, elig, lam, mu

    def to_assign(z, elig):
        """Colonnes a 1 -> affectation (un magasin couvert deux fois va au moins cher)."""
        best = np.full(n, np.inf)
        a = np.full(n, -1, dtype=int)
        for t, k in enumerate(elig):
            if z[t] > 0.5:
                i = cols_i[k]
                better = cols_mask[k] & (inst.c[i] < best)
                a[better] = i
                best[better] = inst.c[i, better]
        return a

    stats = dict(nodes=0, columns_generated=0, root_lp=None, root_lagrangean=None)
    # Demarrage lagrangien (ajout pratique) : la borne du maitre est le dual lagrangien des
    # contraintes de couverture, dont le sous-probleme est EXACTEMENT le pricing. Quelques
    # iterations de sous-gradient remplissent le pool de bonnes colonnes et donnent un centre
    # de stabilisation, ce qui evite le demarrage tres degenere de la generation de colonnes.
    root_bound, root_stab = -math.inf, None
    lam = np.min(inst.c + (inst.f / inst.s)[:, None] * inst.d[None, :], axis=0)
    pi, stall = 2.0, 0
    for _ in range(lagr_warmstart_iters):
        if time.time() > t0 + 0.25 * time_limit:
            break
        L, cover = lam.sum(), np.zeros(n)
        for i in range(m):
            val, R = price(i, lam - inst.c[i])[0]
            add_col(i, R)
            if inst.f[i] - val < 0:
                L += inst.f[i] - val
                cover[list(R)] += 1
        if L > root_bound + 1e-9:
            root_bound, root_stab, stall = L, lam.copy(), 0
        else:
            stall += 1
            if stall >= 10:
                pi, stall = pi / 2, 0
        g = 1.0 - cover
        g = np.where((lam <= 0) & (g < 0), 0.0, g)
        if g @ g < 1e-12 or pi < 1e-3 or rnd_lb(root_bound) >= ub - 1e-6:
            break
        target = ub if ub < math.inf else abs(L) * 1.1 + 1
        lam = np.maximum(0.0, lam + pi * (target - L) / (g @ g) * g)
    stats["lagrangean_warmstart_bound"] = root_bound
    stack = [(frozenset(), frozenset(), np.zeros((m, n), bool), root_bound, 0)]
    timeout = False
    while stack:
        if time.time() > deadline or stats["nodes"] >= max_nodes:
            timeout = True
            break
        y0, y1, forbid, bound, depth = stack.pop()
        if rnd_lb(bound) >= ub - 1e-6:
            continue
        stats["nodes"] += 1
        best_lag, stab = bound, (root_stab if depth == 0 else None)
        pruned, lp = False, None
        while True:  # generation de colonnes
            if time.time() > deadline:
                timeout = True
                break
            lp = solve_rmp(y0, y1, forbid)
            if lp is None:
                pruned = True
                break
            zlp, z, elig, lam, mu = lp
            # Stabilisation de Wentges (ajout pratique, absent de l'article) : on price avec
            # lambda_sep = a * lambda_stab + (1 - a) * lambda_RMP ; si aucune colonne n'est trouvee
            # (« mispricing »), on recommence avec a = 0, ce qui garde l'algorithme exact.
            for a in ((smoothing, 0.0) if (stab is not None and smoothing > 0) else (0.0,)):
                lam_sep = lam if a == 0.0 else a * stab + (1 - a) * lam
                lag, added = lam_sep.sum(), 0
                for i in range(m):
                    if i in y0:
                        continue
                    profit = lam_sep - inst.c[i]
                    profit[forbid[i]] = -1.0
                    res = price(i, profit)
                    term = inst.f[i] - res[0][0]
                    lag += term if i in y1 else min(0.0, term)
                    for _, R in res[:cols_per_facility]:
                        R = list(R)
                        rc = inst.f[i] - mu[i] - (lam[R] - inst.c[i, R]).sum()  # cout reduit aux duaux du RMP
                        if rc < -1e-7 and add_col(i, R):
                            added += 1
                if stab is None or lag > best_lag:
                    stab = lam_sep.copy()
                best_lag = max(best_lag, lag)
                if added:
                    break
            stats["columns_generated"] += added
            if depth == 0:
                stats["root_lp"], stats["root_lagrangean"] = zlp, best_lag
                root_bound = max(root_bound, best_lag)
            if rnd_lb(best_lag) >= ub - 1e-6:
                pruned = True
                break
            if added == 0:
                break
        if timeout:
            stack.append((y0, y1, forbid, bound, depth))
            break
        if pruned:
            continue
        zlp, z, elig, lam, mu = lp
        node_bound = max(zlp, best_lag)
        if depth == 0:
            root_bound = max(root_bound, node_bound)
            stats["root_time"] = time.time() - t0
            _log(verbose, f"[Ryu-Park] racine : LP maitre = {zlp:.4f}, {len(cols_i)} colonnes, "
                          f"{stats['root_time']:.1f}s")
        if z[-1] > 1e-6:  # la colonne factice est utilisee : noeud infaisable
            continue
        if rnd_lb(node_bound) >= ub - 1e-6:
            continue
        zc = z[:-1]
        if np.all(np.minimum(zc, 1 - zc) < 1e-6):  # solution entiere
            a = improve(to_assign(zc, elig))
            ca = _cost_with(inst, a, inst.s)
            if ca < ub - 1e-6:
                inc, ub = a, ca
                _log(verbose, f"[Ryu-Park] noeud {stats['nodes']}: solution entiere {ub:.4f}")
            continue
        if depth == 0 and root_rmp_heuristic:  # ajout pratique : maitre restreint en nombres entiers
            prob = pulp.LpProblem("RMP_int", pulp.LpMinimize)
            zv = [pulp.LpVariable(f"z_{k}", cat=pulp.LpBinary) for k in range(len(cols_i))]
            prob += pulp.lpSum(cols_cost[k] * v for k, v in enumerate(zv))
            CI, CM, _ = col_arrays()
            for j in range(n):
                prob += pulp.lpSum(zv[k] for k in np.flatnonzero(CM[:, j])) >= 1
            for i in range(m):
                prob += pulp.lpSum(zv[k] for k in np.flatnonzero(CI == i)) <= 1
            has, _, _ = solve_mip(prob, min(max(1, rmp_heuristic_frac * time_limit), max(1, deadline - time.time())))
            if has:
                zz = np.array([v.varValue or 0 for v in zv])
                a = to_assign(zz, list(range(len(cols_i))))
                if (a >= 0).all():
                    a = improve(a)
                    ca = _cost_with(inst, a, inst.s)
                    if ca < ub - 1e-6:
                        inc, ub = a, ca
                        _log(verbose, f"[Ryu-Park] heuristique maitre entier : {ub:.4f}")
            if rnd_lb(node_bound) >= ub - 1e-6:
                continue
        # valeurs y et x induites
        yv, xv = np.zeros(m), np.zeros((m, n))
        for t, k in enumerate(elig):
            yv[cols_i[k]] += zc[t]
            xv[cols_i[k], cols_mask[k]] += zc[t]
        frac_y = [i for i in range(m) if 1e-6 < yv[i] < 1 - 1e-6]
        if frac_y:
            i = min(frac_y, key=lambda i: abs(yv[i] - 0.5))
            stack.append((y0 | {i}, y1, forbid, node_bound, depth + 1))  # y_i = 0
            stack.append((y0, y1 | {i}, forbid, node_bound, depth + 1))  # y_i = 1 (explore d'abord)
            continue
        frac_j = [j for j in range(n) if np.any((xv[:, j] > 1e-6) & (xv[:, j] < 1 - 1e-6))]
        j = max(frac_j, key=lambda j: 1 - xv[:, j].max())
        pos = sorted(np.flatnonzero(xv[:, j] > 1e-6), key=lambda i: -xv[i, j])
        S1, acc = [], 0.0
        for i in pos:
            if not S1 or acc + xv[i, j] <= 0.5 + 1e-9:
                S1.append(int(i)); acc += xv[i, j]
        if len(S1) == len(pos):
            S1.pop()
        f1, f2 = forbid.copy(), forbid.copy()
        f1[S1, j] = True
        f2[[i for i in range(m) if i not in S1], j] = True
        stack.append((y0, y1, f2, node_bound, depth + 1))
        stack.append((y0, y1, f1, node_bound, depth + 1))

    if timeout:
        lb = min([ub] + [rnd_lb(nd[3]) for nd in stack]) if stack else ub
        lb = max(min(lb, ub), rnd_lb(root_bound)) if root_bound > -math.inf else None
        proven = False
    else:
        lb, proven = ub, inc is not None
    info = dict(stats, gamma=G.tolist(), robust=bool(b.max() > 0 and G.max() > 0), n_columns=len(cols_i))
    name = "Ryu & Park 2021 (branch-and-price)"
    if inc is None:
        return Solution(name, "SSCFLP", np.full(n, -1), math.inf, math.inf, [], False, lb, False,
                        time.time() - t0, info)
    info["robust_feasible"] = all(robust_ok(int(i), inc == i) for i in np.unique(inc))
    return make_solution(inst, inc, name, "SSCFLP", t0, lower_bound=lb, proven=proven, info=info)


# =============================================================================
# Execution groupee
# =============================================================================
def run_all(inst: Instance, time_limit=60, seed=0, verbose=False):
    runs = [
        lambda: gadegaard2018_cut_and_solve(inst, time_limit=time_limit, verbose=verbose),
        lambda: ryu_park2021_branch_and_price(inst, time_limit=time_limit, verbose=verbose),
    ]
    return [r() for r in runs]


if __name__ == "__main__":
    ex = example_instance()
    print("=== Exemple du document (SSCFLP : 19, GAP : 6) ===")
    for sol in run_all(ex, time_limit=10):
        print(sol)
    rob = ryu_park2021_branch_and_price(ex, gamma=1, deviations=[1, 1, 1], time_limit=10)
    print("Robuste (Gamma = 1, b = 1, attendu 22) :", rob)

    inst = generate_instance(3, 20, seed=42)
    print(f"\n=== {inst.name} ===")
    for sol in run_all(inst, time_limit=20):
        print(sol)
