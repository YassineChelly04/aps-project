# -*- coding: utf-8 -*-
"""
Projet APS - Module 1 : heuristiques et metaheuristiques pour l'affectation magasins -> entrepots.

Complete module1_methods.py (methodes exactes ① et ②) avec les methodes ③ a ⑥ :

  ③ matheuristique_grands_voisinages   construction par regret + descente + LNS a reparation exacte
  ④ kernel_search                       relaxation LP -> noyau + paquets de variables, MIP restreints
  ⑤ recuit_simule_penalite              recuit simule, capacites gerees par PENALITE adaptative
  ⑥ recuit_multi_voisinages             recuit simule a 4 voisinages, capacites gerees par REPARATION

Memes notations que module1_methods.py : i = entrepot (m), j = magasin (n), c[i, j], d[j], s[i], f[i].
Le GAP est le meme probleme avec f = 0 (tous les entrepots disponibles, aucun cout fixe).

Reproductibilite : les methodes stochastiques (③, ⑤, ⑥) prennent une graine ; leur critere d'arret
principal est un BUDGET D'ITERATIONS (independant de la vitesse de la machine), la limite de temps
n'est qu'un garde-fou. Meme graine + meme instance => meme resultat (sauf si la limite de temps coupe).

Interface commune : chaque methode accepte
    rapport(phase:int, fraction:float, meilleur_cout:float|None)   (facultatif)
    arret : objet avec is_set() (threading.Event)                  (facultatif)
et renvoie un module1_methods.Solution.
"""
from __future__ import annotations

import math
import random
import time

import numpy as np
from scipy import sparse
from scipy.optimize import Bounds, LinearConstraint, linprog, milp

import module1_methods as m1

TOL = 1e-6


# =============================================================================
# Outils communs
# =============================================================================
class _Suivi:
    """Horloge, arret et remontee de progression communs a toutes les methodes."""

    def __init__(self, time_limit, rapport=None, arret=None):
        self.t0 = time.perf_counter()
        self.limite = float(time_limit)
        self.rapport = rapport
        self.arret = arret
        self.coupe_par_le_temps = False

    def ecoule(self):
        return time.perf_counter() - self.t0

    def reste(self):
        return self.limite - self.ecoule()

    def doit_arreter(self):
        if self.arret is not None and self.arret.is_set():
            return True
        if self.ecoule() >= self.limite:
            self.coupe_par_le_temps = True
            return True
        return False

    def signale(self, phase, fraction, cout=None):
        if self.rapport is not None:
            self.rapport(phase, max(0.0, min(1.0, fraction)), cout)


def _solution(inst, a, nom, objectif, suivi, borne=None, info=None):
    cost, a_cost, used, feas, load = m1.evaluate(inst, a)
    info = dict(info or {})
    info["loads"] = load.tolist()
    info["coupe_par_le_temps"] = suivi.coupe_par_le_temps
    return m1.Solution(nom, objectif, np.asarray(a, dtype=int), cost, a_cost, used, feas,
                       borne, False, suivi.ecoule(), info)


def _objectif(inst):
    return "SSCFLP" if float(np.sum(inst.f)) > 0 else "GAP"


def mip_restreint(C, d, s, f, permis, time_limit, cutoff=None, au_moins_un=None, rel_gap=1e-6):
    """SSCFLP restreint resolu par HiGHS (scipy.optimize.milp), en memoire (pas de fichier).
    C (m, n), d (n,), s (m,) capacites (eventuellement residuelles), f (m,) couts fixes,
    permis (m, n) booleen : seules ces variables x_ij existent.
    cutoff : impose cout <= cutoff ; au_moins_un : masque (m, n) dont au moins une variable vaut 1.
    Renvoie (affectation ou None, valeur, optimal_prouve)."""
    m, n = C.shape
    I, J = np.nonzero(permis)
    K = I.size
    if K == 0 or not np.all(np.bincount(J, minlength=n) > 0):
        return None, math.inf, False
    nv = K + m
    cout = np.concatenate([C[I, J], f])
    k = np.arange(K)
    blocs, bas, haut = [], [], []
    # chaque magasin servi une fois
    blocs.append(sparse.csr_matrix((np.ones(K), (J, k)), shape=(n, nv)))
    bas.append(np.ones(n)); haut.append(np.ones(n))
    # capacite : sum_j d_j x_ij - s_i y_i <= 0
    A = sparse.csr_matrix((np.concatenate([d[J], -s]), (np.concatenate([I, np.arange(m)]),
                                                         np.concatenate([k, K + np.arange(m)]))), shape=(m, nv))
    blocs.append(A); bas.append(np.full(m, -np.inf)); haut.append(np.zeros(m))
    # x_ij <= y_i (forme forte)
    blocs.append(sparse.csr_matrix((np.concatenate([np.ones(K), -np.ones(K)]),
                                    (np.concatenate([k, k]), np.concatenate([k, K + I]))), shape=(K, nv)))
    bas.append(np.full(K, -np.inf)); haut.append(np.zeros(K))
    if cutoff is not None and math.isfinite(cutoff):
        blocs.append(sparse.csr_matrix(cout[None, :])); bas.append([-np.inf]); haut.append([cutoff])
    if au_moins_un is not None:
        sel = au_moins_un[I, J]
        if not sel.any():
            return None, math.inf, False
        blocs.append(sparse.csr_matrix((np.ones(int(sel.sum())), (np.zeros(int(sel.sum()), int), k[sel])), shape=(1, nv)))
        bas.append([1.0]); haut.append([np.inf])
    cons = LinearConstraint(sparse.vstack(blocs).tocsr(), np.concatenate(bas), np.concatenate(haut))
    res = milp(cout, constraints=cons, integrality=np.ones(nv), bounds=Bounds(0, 1),
               options={"time_limit": max(0.05, float(time_limit)), "mip_rel_gap": rel_gap, "disp": False})
    if res.x is None:
        return None, math.inf, False
    x = res.x[:K] > 0.5
    a = np.full(n, -1, dtype=int)
    a[J[x]] = I[x]
    if (a < 0).any():
        return None, math.inf, False
    return a, float(res.fun), res.status == 0


def relaxation_lineaire(inst):
    """Relaxation LP de la forme forte (x_ij <= y_i). Renvoie (valeur, X (m, n), Y (m,), couts reduits de X)."""
    m, n = inst.m, inst.n
    C, d, s, f = inst.c, inst.d, inst.s, inst.f
    K = m * n
    nv = K + m
    I, J = np.divmod(np.arange(K), n)  # variable k = (i, j) en ordre ligne
    k = np.arange(K)
    A_eq = sparse.csr_matrix((np.ones(K), (J, k)), shape=(n, nv))
    cap = sparse.csr_matrix((np.concatenate([d[J], -s]), (np.concatenate([I, np.arange(m)]),
                                                           np.concatenate([k, K + np.arange(m)]))), shape=(m, nv))
    vub = sparse.csr_matrix((np.concatenate([np.ones(K), -np.ones(K)]),
                             (np.concatenate([k, k]), np.concatenate([k, K + I]))), shape=(K, nv))
    tot = sparse.csr_matrix((-s, (np.zeros(m, int), K + np.arange(m))), shape=(1, nv))  # sum s_i y_i >= D
    A_ub = sparse.vstack([cap, vub, tot]).tocsr()
    b_ub = np.concatenate([np.zeros(m + K), [-d.sum()]])
    res = linprog(np.concatenate([C.ravel(), f]), A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=np.ones(n),
                  bounds=(0, 1), method="highs")
    if res.status != 0:
        return -math.inf, None, None, None
    X = res.x[:K].reshape(m, n)
    rc = res.lower.marginals[:K].reshape(m, n)
    return float(res.fun), X, res.x[K:], rc


def solution_initiale(inst, temps_max=10.0):
    """Construction (cahier des charges §3.3) : glouton par regret, puis descente deplacer/echanger.
    SSCFLP : greedy_sscflp (ouvre par cout unitaire, regret, descente, phase de fermeture).
    Si le glouton echoue (capacites tres tendues), un MIP restreint court donne une solution."""
    if float(np.sum(inst.f)) > 0:
        a = m1.greedy_sscflp(inst)
    else:
        a = m1.regret_greedy(inst.c, inst.d, inst.s)
        if a is not None:
            a = m1.local_search(inst.c, inst.d, inst.s, a)
    if a is None:
        a, _, _ = mip_restreint(inst.c, inst.d, inst.s, inst.f, np.ones((inst.m, inst.n), bool), temps_max, rel_gap=0.05)
    return a


def _cout(inst, a):
    return m1._cost_with(inst, np.asarray(a, dtype=int), inst.s)


# =============================================================================
# ③ Matheuristique a grands voisinages (construction + descente + LNS a reparation exacte)
# =============================================================================
def matheuristique_grands_voisinages(inst, time_limit=60, seed=0, max_sans_amelioration=40, taille_min=6,
                                     taille_frac=0.10, taille_max_frac=0.35, temps_sous_probleme=3.0,
                                     rapport=None, arret=None):
    """Heuristique du cahier des charges (glouton par regret puis echanges), prolongee par une
    recherche a grands voisinages (LNS) dont la reparation est EXACTE (« matheuristique ») :
      repeter : detruire q magasins (4 operateurs tires au hasard, poids adaptatifs),
                reaffecter ces q magasins de facon optimale par un MIP restreint
                (les autres magasins restent fixes : capacites residuelles), descente,
                accepter si le cout baisse ; q augmente quand on stagne.
    Operateurs de destruction :
      - « voisins » : un magasin tire au hasard et les q-1 magasins de profil de cout le plus proche
                      (le profil c_ij / d_j sert de proxy geographique : il depend de la distance) ;
      - « entrepots » : tous les magasins de deux entrepots ouverts (permet d'en fermer un) ;
      - « regret » : les magasins les plus chers par rapport a leur meilleur entrepot ;
      - « echange d'entrepot » (SSCFLP) : tous les magasins d'un entrepot ouvert + les magasins pour
                      qui un entrepot FERME est le moins cher par palette : le MIP peut alors fermer
                      l'un et ouvrir l'autre dans le meme mouvement (indispensable sur TN-M).
    Arret : max_sans_amelioration iterations sans gain, ou limite de temps."""
    suivi = _Suivi(time_limit, rapport, arret)
    rng = np.random.default_rng(seed)
    m, n = inst.m, inst.n
    C, d, s, f = inst.c, inst.d, inst.s, inst.f
    nom, obj = "Matheuristique a grands voisinages", _objectif(inst)

    suivi.signale(0, 0.0)
    a = solution_initiale(inst)
    if a is None:
        raise RuntimeError("Aucune solution initiale realisable.")
    trace = [(suivi.ecoule(), _cout(inst, a))]
    suivi.signale(1, 0.0, trace[-1][1])
    a = m1.local_search(C, d, s, a, f)
    best = _cout(inst, a)
    trace.append((suivi.ecoule(), best))
    suivi.signale(2, 0.0, best)

    profil = C / d[None, :]
    proches = np.argsort(((profil.T[:, None, :] - profil.T[None, :, :]) ** 2).sum(axis=2), axis=1)
    poids = np.ones(4)
    if float(np.sum(f)) == 0 or m < 2:
        poids[3] = 0.0  # GAP : tous les entrepots sont deja disponibles
    q = min(n, max(taille_min, int(round(taille_frac * n))))
    q_max = min(n, max(taille_min + 4, int(round(taille_max_frac * n))))
    sans, it, stats = 0, 0, {"iterations": 0, "ameliorations": 0, "operateurs": [0, 0, 0, 0]}
    while sans < max_sans_amelioration and not suivi.doit_arreter():
        it += 1
        op = int(rng.choice(4, p=poids / poids.sum()))
        if op == 3 and np.unique(a).size == m:
            op = 1  # aucun entrepot ferme : on se rabat sur l'operateur « entrepots »
        if op == 0:
            j0 = int(rng.integers(n))
            libres = proches[j0, :q]
        elif op == 1:
            ouverts = np.unique(a)
            i1 = int(rng.choice(ouverts))
            # le second entrepot : celui qui est le 2e choix le plus frequent des magasins de i1
            cl = np.flatnonzero(a == i1)
            rang = np.argsort(C[:, cl], axis=0)
            second = rang[1] if m > 1 else rang[0]
            i2 = int(np.bincount(second, minlength=m).argmax()) if cl.size else int(rng.integers(m))
            # TOUS les magasins de i1 sont liberes (sinon i1 ne peut jamais fermer), puis ceux de i2
            # dans la limite de q_max magasins au total.
            de_i2 = np.flatnonzero((a == i2) & (a != i1))
            place = max(0, q_max - cl.size)
            if de_i2.size > place:
                de_i2 = rng.choice(de_i2, place, replace=False)
            libres = np.concatenate([cl, de_i2])
        elif op == 2:
            surcout = C[a, np.arange(n)] - C.min(axis=0)
            pr = surcout + 1e-9
            libres = rng.choice(n, min(q, n), replace=False, p=pr / pr.sum())
        else:
            ouverts = np.unique(a)
            fermes = np.setdiff1d(np.arange(m), ouverts)
            i1 = int(rng.choice(ouverts))
            i3 = int(rng.choice(fermes))
            cl = np.flatnonzero(a == i1)
            attires = [j for j in np.argsort(profil[i3]) if a[j] != i1][: max(q, q_max - cl.size)]
            libres = np.concatenate([cl, np.array(attires, dtype=int)])
        libres = np.unique(libres)
        fixe = np.ones(n, bool)
        fixe[libres] = False
        charge_fixe = np.bincount(a[fixe], weights=d[fixe], minlength=m)
        ouvert_fixe = np.bincount(a[fixe], minlength=m) > 0
        s_res = s - charge_fixe
        f_sub = np.where(ouvert_fixe, 0.0, f)
        permis = d[libres][None, :] <= s_res[:, None] + TOL
        sub, _, _ = mip_restreint(C[:, libres], d[libres], s_res, f_sub, permis,
                                  min(temps_sous_probleme, max(0.1, suivi.reste())))
        ameliore = False
        if sub is not None:
            a2 = a.copy()
            a2[libres] = sub
            a2 = m1.local_search(C, d, s, a2, f)
            c2 = _cout(inst, a2)
            if c2 < best - 1e-6:
                a, best, ameliore = a2, c2, True
        stats["operateurs"][op] += 1
        if ameliore:
            poids[op] += 1.0
            stats["ameliorations"] += 1
            sans = 0
            q = min(n, max(taille_min, int(round(taille_frac * n))))
            trace.append((suivi.ecoule(), best))
        else:
            sans += 1
            if poids[op] > 0:
                poids[op] = max(0.2, poids[op] * 0.95)
            if sans % 8 == 0:
                q = min(q_max, int(math.ceil(q * 1.3)))
        suivi.signale(2, sans / max_sans_amelioration, best)
    stats["iterations"] = it
    suivi.signale(3, 1.0, best)
    return _solution(inst, a, nom, obj, suivi, info=dict(stats, trace=trace, graine=seed))


# =============================================================================
# ④ Kernel Search (noyau + paquets)
# =============================================================================
def kernel_search(inst, time_limit=60, nb_paquets=8, taille_paquet=None, temps_noyau_frac=0.3,
                  rapport=None, arret=None):
    """Kernel Search (Angelelli, Mansini & Speranza 2010 ; version SSCFLP de Guastaroba & Speranza 2014).
      1) relaxation LP de la forme forte : les x_ij > 0 forment le NOYAU (variables prometteuses) ;
         on y ajoute le « motif » de la solution gloutonne (regret + descente) pour que le premier
         MIP restreint soit toujours realisable ;
      2) les autres x_ij sont triees par cout reduit croissant et decoupees en PAQUETS ;
      3) MIP restreint au noyau, puis pour chaque paquet : MIP restreint a noyau + paquet avec
         cout <= meilleure solution et au moins une variable du paquet a 1 ; les variables du paquet
         utilisees entrent dans le noyau ;
      4) polissage par descente deplacer / echanger.
    Deterministe. La valeur LP fournit une borne inferieure (=> ecart a la borne affichable)."""
    suivi = _Suivi(time_limit, rapport, arret)
    m, n = inst.m, inst.n
    C, d, s, f = inst.c, inst.d, inst.s, inst.f
    nom, obj = "Kernel Search", _objectif(inst)

    suivi.signale(0, 0.0)
    zlp, X, Y, rc = relaxation_lineaire(inst)
    if X is None:
        raise RuntimeError("Relaxation lineaire infaisable : capacite totale insuffisante.")
    a0 = solution_initiale(inst)
    noyau = X > 1e-6
    if a0 is not None:
        noyau[a0, np.arange(n)] = True
    best, a = (_cout(inst, a0), a0) if a0 is not None else (math.inf, None)
    trace = [(suivi.ecoule(), best)] if a is not None else []
    suivi.signale(1, 0.0, best if a is not None else None)

    a1, v1, _ = mip_restreint(C, d, s, f, noyau, max(0.2, temps_noyau_frac * suivi.reste()), cutoff=best)
    if a1 is not None and _cout(inst, a1) < best - 1e-6:
        a, best = a1, _cout(inst, a1)
        trace.append((suivi.ecoule(), best))
    # paquets : variables hors noyau triees par cout reduit
    hors = np.flatnonzero(~noyau.ravel())
    ordre = hors[np.lexsort((C.ravel()[hors], rc.ravel()[hors]))]
    tp = taille_paquet or max(2 * m, int(math.ceil(noyau.sum() / 2)))
    paquets = [ordre[k:k + tp] for k in range(0, ordre.size, tp)][:nb_paquets]
    stats = {"lp": zlp, "taille_noyau_initial": int(noyau.sum()), "paquets": len(paquets), "paquets_utiles": 0}
    for b, pq in enumerate(paquets):
        if suivi.doit_arreter():
            break
        suivi.signale(2, b / max(1, len(paquets)), best)
        masque_pq = np.zeros(m * n, bool)
        masque_pq[pq] = True
        masque_pq = masque_pq.reshape(m, n)
        tl = max(0.2, suivi.reste() / max(1, len(paquets) - b))
        ab, vb, _ = mip_restreint(C, d, s, f, noyau | masque_pq, tl, cutoff=best - 1e-6, au_moins_un=masque_pq)
        if ab is not None and _cout(inst, ab) < best - 1e-6:
            a, best = ab, _cout(inst, ab)
            utilises = masque_pq[ab, np.arange(n)]
            noyau[ab[utilises], np.flatnonzero(utilises)] = True
            stats["paquets_utiles"] += 1
            trace.append((suivi.ecoule(), best))
    if a is None:
        raise RuntimeError("Kernel Search : aucune solution realisable trouvee.")
    suivi.signale(3, 0.9, best)
    a = m1.local_search(C, d, s, a, f)
    best = _cout(inst, a)
    trace.append((suivi.ecoule(), best))
    stats["taille_noyau_final"] = int(noyau.sum())
    borne = zlp if not inst.costs_are_integral() else math.ceil(zlp - 1e-6)
    return _solution(inst, a, nom, obj, suivi, borne=borne, info=dict(stats, trace=trace))


# =============================================================================
# Recuit simule : etat incremental partage par ⑤ et ⑥
# =============================================================================
class _Etat:
    """Affectation avec charges, effectifs et cout tenus a jour : O(1) par deplacement,
    O(taille du plan) pour un mouvement composite (plan = liste de (magasin, nouvel entrepot))."""

    def __init__(self, inst, a):
        self.C = inst.c.tolist()
        self.d = inst.d.tolist()
        self.s = inst.s.tolist()
        self.f = inst.f.tolist()
        self.m, self.n = inst.m, inst.n
        self.a = [int(x) for x in a]
        self.load = [0.0] * self.m
        self.cnt = [0] * self.m
        for j, i in enumerate(self.a):
            self.load[i] += self.d[j]
            self.cnt[i] += 1
        self.cout = sum(self.C[i][j] for j, i in enumerate(self.a)) + sum(self.f[i] for i in range(self.m) if self.cnt[i])
        self.exces = sum(max(0.0, self.load[i] - self.s[i]) for i in range(self.m))

    def deplacer(self, j, i):
        i0 = self.a[j]
        if i == i0:
            return
        dc, de = self.delta_deplacer(j, i)
        dj = self.d[j]
        self.cout += dc
        self.exces += de
        self.load[i] += dj; self.load[i0] -= dj
        self.cnt[i] += 1; self.cnt[i0] -= 1
        self.a[j] = i

    def delta_deplacer(self, j, i):
        i0 = self.a[j]
        dj = self.d[j]
        dc = self.C[i][j] - self.C[i0][j]
        if self.cnt[i] == 0:
            dc += self.f[i]
        if self.cnt[i0] == 1:
            dc -= self.f[i0]
        de = (max(0.0, self.load[i] + dj - self.s[i]) - max(0.0, self.load[i] - self.s[i])
              + max(0.0, self.load[i0] - dj - self.s[i0]) - max(0.0, self.load[i0] - self.s[i0]))
        return dc, de

    def delta_echanger(self, j1, j2):
        i1, i2 = self.a[j1], self.a[j2]
        d1, d2 = self.d[j1], self.d[j2]
        dc = self.C[i2][j1] + self.C[i1][j2] - self.C[i1][j1] - self.C[i2][j2]
        l1, l2 = self.load[i1] + d2 - d1, self.load[i2] + d1 - d2
        de = (max(0.0, l1 - self.s[i1]) - max(0.0, self.load[i1] - self.s[i1])
              + max(0.0, l2 - self.s[i2]) - max(0.0, self.load[i2] - self.s[i2]))
        return dc, de

    def delta_plan(self, plan):
        """(variation de cout, variation de depassement) si l'on applique le plan."""
        dl, dn, dc = {}, {}, 0.0
        for j, i in plan:
            i0 = self.a[j]
            dc += self.C[i][j] - self.C[i0][j]
            dl[i] = dl.get(i, 0.0) + self.d[j]
            dl[i0] = dl.get(i0, 0.0) - self.d[j]
            dn[i] = dn.get(i, 0) + 1
            dn[i0] = dn.get(i0, 0) - 1
        de = 0.0
        for k, x in dl.items():
            de += max(0.0, self.load[k] + x - self.s[k]) - max(0.0, self.load[k] - self.s[k])
            c0, c1 = self.cnt[k], self.cnt[k] + dn[k]
            if c0 == 0 and c1 > 0:
                dc += self.f[k]
            elif c0 > 0 and c1 == 0:
                dc -= self.f[k]
        return dc, de

    def appliquer(self, plan):
        # un echange (j1 -> i2, j2 -> i1) s'applique correctement deplacement par deplacement
        for j, i in plan:
            self.deplacer(j, i)

    # --- mouvements composites -------------------------------------------------------------
    def plan_fermer_penalite(self, i0):
        """Ferme i0 : chacun de ses magasins va a l'entrepot ouvert le moins cher, SANS regarder la
        capacite (le depassement eventuel est penalise)."""
        autres = [i for i in range(self.m) if i != i0 and self.cnt[i]]
        if not autres:
            return None
        return [(j, min(autres, key=lambda i: self.C[i][j])) for j in range(self.n) if self.a[j] == i0]

    def plan_fermer_reparation(self, i0):
        """Ferme i0 en restant realisable : ses magasins, par demande decroissante, vont a l'entrepot
        realisable le moins cher (cout fixe compris s'il faut l'ouvrir). None si impossible."""
        clients = sorted((j for j in range(self.n) if self.a[j] == i0), key=lambda j: -self.d[j])
        load, cnt, plan = list(self.load), list(self.cnt), []
        for j in clients:
            meilleur, ib = math.inf, -1
            for i in range(self.m):
                if i == i0 or load[i] + self.d[j] > self.s[i] + TOL:
                    continue
                c = self.C[i][j] + (self.f[i] if cnt[i] == 0 else 0.0)
                if c < meilleur:
                    meilleur, ib = c, i
            if ib < 0:
                return None
            load[ib] += self.d[j]
            cnt[ib] += 1
            plan.append((j, ib))
        return plan

    def plan_remplir(self, i):
        """L'entrepot i attire les magasins pour qui il est moins cher, par economie par palette
        decroissante, tant qu'il a de la place (ne cree jamais de depassement)."""
        gains = sorted(((self.C[self.a[j]][j] - self.C[i][j]) / self.d[j], j) for j in range(self.n)
                       if self.a[j] != i and self.C[i][j] < self.C[self.a[j]][j])
        place, plan = self.s[i] - self.load[i], []
        for _, j in reversed(gains):
            if self.d[j] <= place + TOL:
                place -= self.d[j]
                plan.append((j, i))
        return plan or None


def _budget(inst, iterations, par_paire=2000):
    """Budget d'iterations : par_paire x m x n, borne a [100 000 ; 3 000 000]."""
    return int(iterations) if iterations else int(min(3_000_000, max(100_000, par_paire * inst.m * inst.n)))


def _calibrer_temperature(echantillon, p0):
    """T0 telle qu'une degradation moyenne soit acceptee avec la probabilite p0 (Kirkpatrick et al. 1983)."""
    pos = [x for x in echantillon if x > 1e-9]
    if not pos:
        return 1.0
    return -float(np.mean(pos)) / math.log(p0)


def _recuit(E, tirer, cout_de, suivi, N, alpha, p0, t_final_frac, rnd, realisable):
    """Boucle de recuit commune a ⑤ et ⑥.
    tirer() -> (nom_voisinage, plan ou None, (dc, de)) ; cout_de(dc, de) -> variation de l'objectif.
    Renvoie (meilleure affectation realisable, son cout, trace, statistiques)."""
    ech = []
    for _ in range(400):
        _, plan, dl = tirer()
        if plan:
            ech.append(cout_de(*dl))
    T0 = _calibrer_temperature(ech, p0)
    nb_paliers = max(1, int(math.ceil(math.log(t_final_frac) / math.log(alpha))))
    L = max(1, N // nb_paliers)
    T = T0
    best_a, best = (list(E.a), E.cout) if realisable() else (None, math.inf)
    trace = [(suivi.ecoule(), best)] if best_a else []
    usage = {}
    for it in range(N):
        if it % 500 == 0:
            if suivi.doit_arreter():
                break
            if it % 5000 == 0:
                suivi.signale(2, it / N, best if best_a else None)
        if it and it % L == 0:
            T *= alpha
        k, plan, dl = tirer()
        if plan is None:
            continue
        u = usage.setdefault(k, [0, 0])
        u[0] += 1
        delta = cout_de(*dl)
        if delta <= 0 or rnd.random() < math.exp(-delta / T):
            u[1] += 1
            E.appliquer(plan)
            if E.cout < best - 1e-9 and realisable():
                best, best_a = E.cout, list(E.a)
                trace.append((suivi.ecoule(), best))
    stats = dict(T0=T0, alpha=alpha, p0=p0, t_final=T0 * t_final_frac, iterations=N, paliers=nb_paliers,
                 voisinages={k: {"proposes": u[0], "acceptes": u[1]} for k, u in usage.items()})
    return best_a, best, trace, stats


def _polir(inst, suivi, best_a, best, trace):
    suivi.signale(3, 0.95, best)
    a = m1.local_search(inst.c, inst.d, inst.s, np.array(best_a), inst.f)
    if _cout(inst, a) < best - 1e-9:
        trace.append((suivi.ecoule(), _cout(inst, a)))
    return a


# =============================================================================
# ⑤ Recuit simule avec penalite de capacite
# =============================================================================
def recuit_simule_penalite(inst, time_limit=60, seed=0, iterations=None, alpha=0.95, p0=0.5, t_final_frac=1e-4,
                           p_echange=0.3, p_bascule=0.02, maj_penalite=100, budget_par_paire=5000,
                           rapport=None, arret=None):
    """Recuit simule (Kirkpatrick et al. 1983) ; les capacites sont gerees par PENALITE :
        objectif = cout + w * (somme des depassements de capacite),
    w adaptatif : x1,10 si la solution courante est irrealisable, /1,05 sinon (tous les maj_penalite
    mouvements). La recherche traverse des solutions irrealisables ; seule la meilleure solution
    REALISABLE est retenue.
    Voisinages : deplacer un magasin ; echanger deux magasins (p_echange) ; en SSCFLP seulement,
    basculer un entrepot (p_bascule) : fermer un entrepot ouvert (ses magasins vont a l'entrepot ouvert
    le moins cher, sans regarder la capacite) ou ouvrir un entrepot ferme (il attire les magasins pour
    qui il est moins cher). Sans ce mouvement, fermer un entrepot exige une longue suite de
    deplacements tous degradants : le recuit reste piege dans la structure d'ouverture initiale
    (constate au reglage sur TN-M).
    Refroidissement geometrique T <- alpha T par palier ; T0 calibree pour accepter une degradation
    moyenne avec la probabilite p0 ; T_final = t_final_frac T0 ; budget = budget_par_paire x m x n.
    Valeurs par defaut (p0 = 0,5 ; 5000 m n) retenues par experimentation/exp_reglage.py."""
    suivi = _Suivi(time_limit, rapport, arret)
    rnd = random.Random(seed)
    nom, obj = "Recuit simule (penalite)", _objectif(inst)
    if obj == "GAP":
        p_bascule = 0.0
    suivi.signale(0, 0.0)
    a0 = solution_initiale(inst)
    if a0 is None:
        a0 = np.array([rnd.randrange(inst.m) for _ in range(inst.n)])
    E = _Etat(inst, a0)
    m, n = E.m, E.n
    w0 = 2.0 * float(np.mean(inst.c / inst.d[None, :]))
    etat = {"w": w0, "k": 0}
    suivi.signale(1, 0.0)

    def tirer():
        etat["k"] += 1
        if etat["k"] % maj_penalite == 0:
            etat["w"] = min(100 * w0, etat["w"] * 1.10) if E.exces > TOL else max(w0 / 10, etat["w"] / 1.05)
        u = rnd.random()
        if u < p_bascule:
            i = rnd.randrange(m)
            plan = E.plan_fermer_penalite(i) if E.cnt[i] else E.plan_remplir(i)
            return "basculer", plan, (E.delta_plan(plan) if plan else None)
        if u < p_bascule + p_echange:
            j1 = rnd.randrange(n)
            j2 = rnd.randrange(n)
            i1, i2 = E.a[j1], E.a[j2]
            if i1 == i2:
                return "echanger", None, None
            return "echanger", [(j1, i2), (j2, i1)], E.delta_echanger(j1, j2)
        j = rnd.randrange(n)
        i = rnd.randrange(m)
        if i == E.a[j]:
            return "deplacer", None, None
        return "deplacer", [(j, i)], E.delta_deplacer(j, i)

    best_a, best, trace, stats = _recuit(E, tirer, lambda dc, de: dc + etat["w"] * de, suivi,
                                         _budget(inst, iterations, budget_par_paire), alpha, p0, t_final_frac, rnd,
                                         lambda: E.exces <= TOL)
    if best_a is None:
        raise RuntimeError("Recuit simule : aucune solution realisable rencontree.")
    a = _polir(inst, suivi, best_a, best, trace)
    stats.update(penalite_initiale=w0, penalite_finale=etat["w"], graine=seed, trace=trace)
    return _solution(inst, a, nom, obj, suivi, info=stats)


# =============================================================================
# ⑥ Recuit multi-voisinages avec reparation (solutions toujours realisables)
# =============================================================================
def recuit_multi_voisinages(inst, time_limit=60, seed=0, iterations=None, alpha=0.95, p0=0.05, t_final_frac=1e-4,
                            probas=None, budget_par_paire=2000, rapport=None, arret=None):
    """Recuit simule a plusieurs voisinages tires au hasard a chaque iteration (principe de Ceschia &
    Schaerf) ; les capacites sont gerees par REPARATION : seuls des mouvements qui gardent la solution
    realisable sont proposes (contraste volontaire avec ⑤ qui penalise).
    Voisinages (probabilites par defaut SSCFLP 0,55 / 0,30 / 0,075 / 0,075 ; GAP 0,60 / 0,35 / 0,025 / 0,025) :
      - deplacer : un magasin vers un entrepot qui a la place (3 essais) ;
      - echanger : deux magasins de deux entrepots, si les capacites restent respectees ;
      - vider    : un entrepot ouvert est vide, ses magasins vont (par demande decroissante) a l'entrepot
                   realisable le moins cher -> FERME un entrepot en un seul mouvement ;
      - remplir  : un entrepot attire les magasins pour lesquels il est moins cher (economie par palette
                   decroissante) tant qu'il a de la place -> OUVRE un entrepot en un seul mouvement.
    Valeurs par defaut (p0 = 0,05 ; 2000 m n) retenues par experimentation/exp_reglage.py."""
    suivi = _Suivi(time_limit, rapport, arret)
    rnd = random.Random(seed)
    nom, obj = "Recuit multi-voisinages", _objectif(inst)
    if probas is None:
        probas = (0.55, 0.30, 0.075, 0.075) if obj == "SSCFLP" else (0.60, 0.35, 0.025, 0.025)
    cum = np.cumsum(probas) / np.sum(probas)
    suivi.signale(0, 0.0)
    a0 = solution_initiale(inst)
    if a0 is None:
        raise RuntimeError("Recuit multi-voisinages : aucune solution initiale realisable.")
    E = _Etat(inst, a0)
    m, n, d, s = E.m, E.n, E.d, E.s
    suivi.signale(1, 0.0)

    def tirer():
        u = rnd.random()
        if u < cum[0]:
            j = rnd.randrange(n)
            for _ in range(3):
                i = rnd.randrange(m)
                if i != E.a[j] and E.load[i] + d[j] <= s[i] + TOL:
                    return "deplacer", [(j, i)], E.delta_deplacer(j, i)
            return "deplacer", None, None
        if u < cum[1]:
            j1 = rnd.randrange(n)
            j2 = rnd.randrange(n)
            i1, i2 = E.a[j1], E.a[j2]
            if i1 == i2 or E.load[i1] - d[j1] + d[j2] > s[i1] + TOL or E.load[i2] - d[j2] + d[j1] > s[i2] + TOL:
                return "echanger", None, None
            return "echanger", [(j1, i2), (j2, i1)], E.delta_echanger(j1, j2)
        if u < cum[2]:
            ouverts = [i for i in range(m) if E.cnt[i]]
            if len(ouverts) < 2:
                return "vider", None, None
            plan = E.plan_fermer_reparation(rnd.choice(ouverts))
            return "vider", plan, (E.delta_plan(plan) if plan else None)
        plan = E.plan_remplir(rnd.randrange(m))
        return "remplir", plan, (E.delta_plan(plan) if plan else None)

    best_a, best, trace, stats = _recuit(E, tirer, lambda dc, de: dc, suivi, _budget(inst, iterations, budget_par_paire),
                                         alpha, p0, t_final_frac, rnd, lambda: True)
    a = _polir(inst, suivi, best_a, best, trace)
    stats.update(graine=seed, trace=trace, probas=list(probas))
    return _solution(inst, a, nom, obj, suivi, info=stats)


METHODES_HEURISTIQUES = {
    "h1": matheuristique_grands_voisinages,
    "h2": kernel_search,
    "m1": recuit_simule_penalite,
    "m2": recuit_multi_voisinages,
}


if __name__ == "__main__":
    ex = m1.example_instance()
    for nom, fn in METHODES_HEURISTIQUES.items():
        kw = {} if nom == "h2" else {"seed": 0}
        print(nom, fn(ex, time_limit=10, **kw))
