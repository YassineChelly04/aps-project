# -*- coding: utf-8 -*-
"""
Generateur d'instances « Tunisie » de remplacement (format instance.json + matrices.npz).

ATTENTION : jeu de substitution. Le jeu officiel (donnees_tunisie/ fourni avec
rapport_donnees.pdf) n'etait pas dans le depot ; ce script produit des instances au MEME
format (celui que lit la maquette du tableau de bord) pour que le tableau de bord et les
tests tournent. Si le jeu officiel est copie dans donnees_tunisie/instances/, il remplace
simplement ces fichiers.

Modele de cout (identique a la maquette) :
    cout_affectation[i][j] = demande_i * (2 * KPAL * distance_ij + manutention_j)
    KPAL = cout de transport d'une palette sur 1 km (TND), aller-retour.
Les solutions de reference (GAP et SSCFLP) sont calculees par HiGHS (scipy.optimize.milp).

Usage : python donnees_tunisie/generer_instances.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from scipy import sparse
from scipy.optimize import Bounds, LinearConstraint, milp

KPAL = 0.12324
FACTEUR_ROUTE = 1.25
ICI = Path(__file__).resolve().parent

# ville, gouvernorat, lat, lon, poids (population relative)
VILLES = [
    ("Tunis", "Tunis", 36.806, 10.181, 10), ("La Marsa", "Tunis", 36.878, 10.325, 3),
    ("Ariana", "Ariana", 36.862, 10.195, 5), ("Raoued", "Ariana", 36.940, 10.183, 2),
    ("Ben Arous", "Ben Arous", 36.753, 10.218, 4), ("Hammam-Lif", "Ben Arous", 36.727, 10.341, 2),
    ("La Manouba", "La Manouba", 36.808, 10.097, 3), ("Nabeul", "Nabeul", 36.456, 10.737, 3),
    ("Hammamet", "Nabeul", 36.400, 10.616, 3), ("Kélibia", "Nabeul", 36.847, 11.093, 1),
    ("Bizerte", "Bizerte", 37.274, 9.874, 4), ("Menzel Bourguiba", "Bizerte", 37.154, 9.786, 2),
    ("Zaghouan", "Zaghouan", 36.402, 10.143, 1), ("Béja", "Béja", 36.725, 9.182, 2),
    ("Jendouba", "Jendouba", 36.501, 8.780, 2), ("Le Kef", "Le Kef", 36.174, 8.705, 1),
    ("Siliana", "Siliana", 36.085, 9.371, 1), ("Sousse", "Sousse", 35.825, 10.636, 5),
    ("Msaken", "Sousse", 35.729, 10.581, 2), ("Monastir", "Monastir", 35.777, 10.826, 3),
    ("Ksar Hellal", "Monastir", 35.643, 10.890, 1), ("Mahdia", "Mahdia", 35.505, 11.062, 2),
    ("El Jem", "Mahdia", 35.296, 10.707, 1), ("Kairouan", "Kairouan", 35.678, 10.096, 3),
    ("Kasserine", "Kasserine", 35.168, 8.836, 2), ("Sidi Bouzid", "Sidi Bouzid", 35.038, 9.484, 2),
    ("Sfax", "Sfax", 34.740, 10.760, 7), ("Gafsa", "Gafsa", 34.425, 8.784, 2),
    ("Tozeur", "Tozeur", 33.920, 8.134, 1), ("Kébili", "Kébili", 33.705, 8.969, 1),
    ("Gabès", "Gabès", 33.881, 10.098, 3), ("Médenine", "Médenine", 33.354, 10.505, 2),
    ("Houmt Souk", "Médenine", 33.875, 10.857, 2), ("Zarzis", "Médenine", 33.504, 11.112, 1),
    ("Tataouine", "Tataouine", 32.929, 10.452, 1),
]
# id, nom, lat, lon
ZONES = [
    ("Radès (Ben Arous)", 36.768, 10.275), ("Charguia (Tunis)", 36.840, 10.205),
    ("Grombalia (Nabeul)", 36.598, 10.500), ("Sousse Sidi Abdelhamid (Sousse)", 35.800, 10.640),
    ("Bizerte Menzel Abderrahmane (Bizerte)", 37.233, 9.860), ("Sfax Thyna (Sfax)", 34.680, 10.700),
    ("Gabès Ghannouch (Gabès)", 33.930, 10.060), ("Kairouan Raccada (Kairouan)", 35.620, 10.050),
    ("Béja Nord (Béja)", 36.750, 9.200), ("Gafsa Ksar (Gafsa)", 34.400, 8.800),
]
REGIONS = {
    "S": ("Grand Tunis et Cap Bon", {"Tunis", "Ariana", "Ben Arous", "La Manouba", "Nabeul", "Zaghouan"}),
    "M": ("Nord-Est et Sahel", {"Tunis", "Ariana", "Ben Arous", "La Manouba", "Nabeul", "Zaghouan",
                                "Bizerte", "Sousse", "Monastir", "Mahdia"}),
    "L": ("Tunisie entière", None),
}
TAILLES = {"S": (3, 20), "M": (5, 50), "L": (10, 200)}
FORMATS = [("proximité", 0.62, (4, 12)), ("supermarché", 0.30, (15, 40)), ("hypermarché", 0.08, (60, 120))]


def haversine(a_lat, a_lon, b_lat, b_lon):
    la1, lo1, la2, lo2 = map(np.radians, (a_lat, a_lon, b_lat, b_lon))
    h = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(h))


def resoudre_reference(C, d, s, f, sscflp, time_limit=300):
    """MIP exact (HiGHS). C : (n, m) magasin x entrepot. Renvoie (cout, affectation, statut)."""
    n, m = C.shape
    nx = n * m
    nv = nx + (m if sscflp else 0)
    cost = np.concatenate([C.ravel(), f if sscflp else []])
    rows, cols, vals = [], [], []
    lb, ub = [], []
    r = 0
    for i in range(n):  # chaque magasin servi une fois
        rows += [r] * m; cols += list(range(i * m, i * m + m)); vals += [1.0] * m
        lb.append(1); ub.append(1); r += 1
    for j in range(m):  # capacite
        rows += [r] * n; cols += [i * m + j for i in range(n)]; vals += list(d.astype(float))
        if sscflp:
            rows.append(r); cols.append(nx + j); vals.append(-float(s[j]))
            lb.append(-np.inf); ub.append(0)
        else:
            lb.append(-np.inf); ub.append(float(s[j]))
        r += 1
    if sscflp:  # x_ij <= y_j
        for i in range(n):
            for j in range(m):
                rows += [r, r]; cols += [i * m + j, nx + j]; vals += [1.0, -1.0]
                lb.append(-np.inf); ub.append(0); r += 1
    A = sparse.csr_matrix((vals, (rows, cols)), shape=(r, nv))
    res = milp(cost, constraints=LinearConstraint(A, lb, ub), integrality=np.ones(nv),
               bounds=Bounds(0, 1), options={"time_limit": time_limit, "mip_rel_gap": 0})
    if res.x is None:
        raise RuntimeError(f"HiGHS n'a pas trouve de solution : {res.message}")
    a = res.x[:nx].reshape(n, m).argmax(axis=1)
    statut = "optimal" if res.status == 0 else "limite de temps"
    return float(res.fun), a, statut


def generer(taille: str, graine: int = 1, rho: float = 1.35):
    m, n = TAILLES[taille]
    region, govs = REGIONS[taille]
    rng = np.random.default_rng(1000 * graine + "SML".index(taille))
    villes = [v for v in VILLES if govs is None or v[1] in govs]
    p = np.array([v[4] for v in villes], float); p /= p.sum()

    # Entrepots : les m premieres zones situees dans la region
    zones = [z for z in ZONES if govs is None or z[0].split("(")[-1].rstrip(")") in govs][:m]
    if len(zones) < m:
        zones += [z for z in ZONES if z not in zones][: m - len(zones)]

    magasins = []
    fmt_p = np.array([x[1] for x in FORMATS])
    for k in range(n):
        v = villes[rng.choice(len(villes), p=p)]
        fm = FORMATS[rng.choice(len(FORMATS), p=fmt_p)]
        magasins.append({
            "id": f"PV{k + 1:04d}", "ville": v[0], "gouvernorat": v[1], "format": fm[0],
            "lat": round(v[2] + rng.normal(0, 0.025), 4), "lon": round(v[3] + rng.normal(0, 0.025), 4),
            "demande": int(rng.integers(fm[2][0], fm[2][1] + 1)),
        })
    d = np.array([x["demande"] for x in magasins])
    D = int(d.sum())
    w = rng.uniform(0.75, 1.25, m)
    cap = np.maximum(np.floor(w / w.sum() * rho * D).astype(int), int(d.max()))
    entrepots = []
    for j, (nom, la, lo) in enumerate(zones):
        entrepots.append({
            "id": f"E{j + 1:02d}", "nom": nom, "lat": la, "lon": lo, "capacite": int(cap[j]),
            "cout_fixe_semaine": float(round(rng.uniform(2200, 4200), 2)),
            "cout_manutention_palette": float(round(rng.uniform(2.8, 4.6), 2)),
        })

    slat = np.array([x["lat"] for x in magasins])[:, None]; slon = np.array([x["lon"] for x in magasins])[:, None]
    wlat = np.array([e["lat"] for e in entrepots])[None, :]; wlon = np.array([e["lon"] for e in entrepots])[None, :]
    dist = np.round(FACTEUR_ROUTE * haversine(slat, slon, wlat, wlon), 2)
    manut = np.array([e["cout_manutention_palette"] for e in entrepots])[None, :]
    C = np.round(d[:, None] * (2 * KPAL * dist + manut), 2)
    f = np.array([e["cout_fixe_semaine"] for e in entrepots])

    ident = f"TN-{taille}-g{graine}-r{int(round(rho * 100))}"
    reference = []
    for modele, ssc in (("GAP (tous ouverts)", False), ("SSCFLP (ouverture + affectation)", True)):
        cout, a, statut = resoudre_reference(C, d, cap, f, ssc)
        reference.append({"modele": modele, "solveur": "HiGHS", "statut": statut, "cout": round(cout, 2),
                          "affectation": {magasins[i]["id"]: entrepots[a[i]]["id"] for i in range(n)}})
    inst = {
        "meta": {"id": ident, "region": region, "taille": taille, "graine": graine, "rho": rho,
                 "unite_demande": "palettes / semaine", "unite_cout": "TND / semaine", "kpal": KPAL,
                 "source": "jeu de substitution genere par generer_instances.py"},
        "entrepots": entrepots, "magasins": magasins, "cout_affectation": C.tolist(),
        "reference": reference,
    }
    dossier = ICI / "instances" / taille / ident
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "instance.json").write_text(json.dumps(inst, ensure_ascii=False, indent=1), encoding="utf-8")
    np.savez_compressed(dossier / "matrices.npz", distance_km=dist, cout_affectation=C)
    return ident, reference


if __name__ == "__main__":
    for t in "SML":
        ident, ref = generer(t)
        print(ident, " | ".join(f"{r['modele']} = {r['cout']} ({r['statut']})" for r in ref))
