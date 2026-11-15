# -*- coding: utf-8 -*-
"""Chiffres cles, lecture automatique (§6) et indicateurs du tableau de bord 1 (§7).
Reproduit les regles de renderVals() de la maquette."""
from __future__ import annotations

import numpy as np

from .donnees import DonneesInstance

ESP = " "  # separateur de milliers fr-FR (espace fine insecable, comme toLocaleString)
TONS = {"alerte": ("#FBEDE0", "#8A4A0A"), "info": ("#E8EDFB", "#1F3A9E"), "ok": ("#E3F1EA", "#1E6B45")}
FAMILLES = {"exacte": "Exactes", "heuristique": "Heuristiques", "metaheuristique": "Métaheuristiques"}


def nf(x: float, dec: int = 0) -> str:
    s = f"{float(x):,.{dec}f}"
    return s.replace(",", ESP).replace(".", ",")


def pct(x: float, dec: int = 1) -> str:
    return nf(100 * x, dec) + " %"


def niveau_tension(fill: float) -> str:
    return "tension forte" if fill >= 0.8 else ("tension modérée" if fill >= 0.7 else "marge confortable")


# ----------------------------------------------------------------------------- étape 1
def chiffres_cles(di: DonneesInstance) -> list:
    D, Q = float(di.d.sum()), float(di.s.sum())
    fill = D / Q
    rho = di.brut["meta"].get("rho") or Q / D
    nb_gouv = len({s["gouvernorat"] for s in di.magasins})
    return [
        {"label": "Magasins", "value": nf(di.n), "sub": f"{nb_gouv} gouvernorats", "alerte": False},
        {"label": "Entrepôts candidats", "value": nf(di.m), "sub": "zones réelles", "alerte": False},
        {"label": "Demande", "value": nf(D), "sub": "palettes / semaine", "alerte": False},
        {"label": "Capacité", "value": nf(Q), "sub": f"{nf(rho, 2)} × la demande", "alerte": False},
        {"label": "Remplissage", "value": pct(fill, 0), "sub": niveau_tension(fill), "alerte": fill >= 0.8},
    ]


def _constat(ton, tag, titre, texte):
    return {"ton": ton, "bg": TONS[ton][0], "fg": TONS[ton][1], "tag": tag, "titre": titre, "texte": texte}


def constat_proximite(di: DonneesInstance) -> dict:
    proche = di.dist.argmin(axis=1)
    charge = np.bincount(proche, weights=di.d, minlength=di.m)
    taux = charge / di.s
    j = int(taux.argmax())
    lib = f"{di.entrepots[j]['id']} {di.nom_court(j)}"
    if taux[j] > 1:
        return _constat("alerte", "Proximité", "Servir chaque magasin par l’entrepôt le plus proche est impossible",
                        f"{lib} serait chargé à {pct(taux[j], 0)} de sa capacité : certains magasins devront aller plus loin.")
    return _constat("ok", "Proximité", "Servir chaque magasin par l’entrepôt le plus proche est faisable",
                    f"L’entrepôt le plus sollicité, {lib}, atteindrait {pct(taux[j], 0)} de sa capacité.")


def constat_capacite(di: DonneesInstance) -> dict:
    D, Q = float(di.d.sum()), float(di.s.sum())
    fill = D / Q
    texte = ("Capacités tendues : la gestion des capacités sera décisive pour les heuristiques." if fill >= 0.8
             else f"Il reste {nf(Q - D)} palettes de marge par semaine, inégalement réparties.")
    return _constat("alerte" if fill >= 0.7 else "ok", "Capacité", f"Remplissage du réseau : {pct(fill, 0)}", texte)


def demande_par_gouvernorat(di: DonneesInstance) -> list:
    tot: dict = {}
    for s in di.magasins:  # ordre d'apparition conserve en cas d'egalite (tri stable)
        tot[s["gouvernorat"]] = tot.get(s["gouvernorat"], 0.0) + float(s["demande"])
    return sorted(tot.items(), key=lambda kv: -kv[1])


def constat_concentration(di: DonneesInstance) -> dict:
    D = float(di.d.sum())
    gl = demande_par_gouvernorat(di)
    part1 = gl[0][1] / D
    part3 = sum(v for _, v in gl[:3]) / D
    return _constat("alerte" if part1 > 0.3 else "info", "Concentration",
                    f"{gl[0][0]} pèse {pct(part1, 0)} de la demande",
                    f"Les trois premiers gouvernorats en représentent {pct(part3, 0)}.")


def constat_gros_clients(di: DonneesInstance) -> dict:
    D = float(di.d.sum())
    hyp = [s for s in di.magasins if s.get("format") == "hypermarché"]
    if hyp:
        big = di.magasins[int(di.d.argmax())]
        part = sum(float(s["demande"]) for s in hyp) / D
        k = len(hyp)
        return _constat("info", "Gros clients", f"{k} hypermarché{'s' if k > 1 else ''} = {pct(part, 0)} de la demande",
                        f"Le plus gros ({big['id']}, {big['ville']}) commande {nf(big['demande'])} palettes par semaine.")
    dmin = di.dist.min(axis=1)
    i = int(dmin.argmax())
    return _constat("info", "Isolement", f"Magasin le plus isolé : {di.magasins[i]['ville']}",
                    f"À {nf(dmin[i])} km de l’entrepôt le plus proche.")


def lecture_automatique(di: DonneesInstance) -> list:
    return [constat_proximite(di), constat_capacite(di), constat_concentration(di), constat_gros_clients(di)]


def resume(di: DonneesInstance) -> dict:
    """Tout ce que l'etape 1 affiche, plus les donnees brutes utiles a la carte."""
    return {
        "id": di.id, "region": di.brut["meta"].get("region", ""), "n": di.n, "m": di.m,
        "chiffres_cles": chiffres_cles(di), "constats": lecture_automatique(di),
        "entrepots": [{"id": e["id"], "nom": di.nom_court(j), "lat": e["lat"], "lon": e["lon"],
                       "capacite": float(di.s[j]), "cout_fixe": float(di.f[j])} for j, e in enumerate(di.entrepots)],
        "magasins": [{"id": s["id"], "ville": s.get("ville", ""), "gouvernorat": s.get("gouvernorat", ""),
                      "format": s.get("format", ""), "lat": s["lat"], "lon": s["lon"], "demande": float(di.d[i])}
                     for i, s in enumerate(di.magasins)],
    }


# ----------------------------------------------------------------------------- §7 indicateurs
def evaluer(di: DonneesInstance, a: np.ndarray, modele: str) -> dict:
    """Indicateurs d'une affectation a (indices d'entrepot par magasin)."""
    a = np.asarray(a, dtype=int)
    ssc = modele == "sscflp"
    n = di.n
    charge = np.bincount(a, weights=di.d, minlength=di.m)
    ouverts = charge > 0 if ssc else np.ones(di.m, bool)
    cout_aff = float(di.C[np.arange(n), a].sum())
    cout_fixe = float(di.f[ouverts].sum()) if ssc else 0.0
    cap_ouverte = float(di.s[ouverts].sum())
    return {
        "cout_total": round(cout_aff + cout_fixe, 2),
        "cout_affectation": round(cout_aff, 2), "cout_fixe": round(cout_fixe, 2),
        "entrepots_ouverts": int(ouverts.sum()), "m": di.m,
        "taux_utilisation": float(di.d.sum()) / cap_ouverte if cap_ouverte else float("inf"),
        "distance_moyenne": float(di.dist[np.arange(n), a].mean()),
        "charges": charge.tolist(), "ouverts": ouverts.tolist(),
        "realisable": bool((charge <= di.s + 1e-9).all()),
    }


def ecart(cout: float, meilleur: float) -> float:
    return (cout - meilleur) / meilleur if meilleur else 0.0


def comparer(di: DonneesInstance, resultats: dict, methodes: dict) -> dict:
    """resultats : {cle: {"temps_s", "indicateurs"}} des methodes terminees (meme modele).
    Renvoie le titre-conclusion, le sous-titre et les lignes du tableau (6 methodes)."""
    nom = lambda k: f"{methodes[k]['num']} {methodes[k]['nom']}"
    dk = [k for k in methodes if k in resultats]
    if not dk:
        return {"titre": "", "sous_titre": "", "lignes": []}
    cout = {k: resultats[k]["indicateurs"]["cout_total"] for k in dk}
    temps = {k: resultats[k]["temps_s"] for k in dk}
    best, best_t = min(cout.values()), min(temps.values())
    prouve = {k: bool(resultats[k].get("optimal_prouve", False)) for k in dk}
    if len(dk) >= 2:
        if all(abs(cout[k] - best) < 0.5 for k in dk):
            rapide = sorted(dk, key=lambda k: temps[k])
            ratio = temps[rapide[-1]] / max(temps[rapide[0]], 1e-9)
            qualif = "Même coût optimal" if any(prouve.values()) else "Même coût"
            titre = f"{qualif}, {nf(best)} TND/semaine : {nom(rapide[0])} répond {nf(ratio, 1)} fois plus vite"
        else:
            k_best = min(dk, key=lambda k: (cout[k], temps[k]))
            titre = f"{nom(k_best)} donne le coût le plus bas : {nf(best)} TND/semaine"
    else:
        k = dk[0]
        o = resultats[k]["indicateurs"]["entrepots_ouverts"]
        verbe = "trouve l’optimum" if prouve[k] else "propose"
        titre = f"{nom(k)} {verbe} : {nf(best)} TND/semaine avec {o} entrepôt{'s' if o > 1 else ''} sur {di.m}"
    ref = resultats[min(dk, key=lambda k: cout[k])]["indicateurs"]
    restants = [methodes[k]["num"] for k in methodes if k not in resultats and methodes[k]["pret"]]
    sous_titre = (f"Taux d’utilisation {pct(ref['taux_utilisation'], 0)}, distance moyenne magasin–entrepôt "
                  f"{nf(ref['distance_moyenne'], 1)} km."
                  + (f" Méthodes non lancées : {' '.join(restants)}." if restants else " Les six méthodes ont été lancées."))
    if any(prouve.values()):
        sous_titre += " L’écart est mesuré par rapport à un optimum prouvé."
    lignes = []
    for k, mt in methodes.items():
        r = resultats.get(k)
        ligne = {"cle": k, "methode": nom(k), "famille": FAMILLES[mt["famille"]], "termine": r is not None,
                 "garantie": ""}
        if r:
            ind = r["indicateurs"]
            ligne.update(cout=nf(ind["cout_total"]), cout_gras=abs(ind["cout_total"] - best) < 0.5,
                         temps=nf(temps[k], 2) + " s", temps_gras=temps[k] == best_t,
                         ecart=pct(ecart(ind["cout_total"], best), 2),
                         ouverts=f"{ind['entrepots_ouverts']} / {di.m}",
                         utilisation=pct(ind["taux_utilisation"], 0), distance=nf(ind["distance_moyenne"], 1) + " km",
                         garantie=("optimum prouvé" if r.get("optimal_prouve") else
                                   f"écart à la borne {pct(r['ecart_borne'], 2)}" if r.get("ecart_borne") is not None
                                   else "sans garantie")
                         + (f" · graine {r['graine']}" if r.get("graine") is not None else ""))
        else:
            ligne.update(cout="non lancé" if mt["pret"] else "jalon ultérieur", cout_gras=False, temps="—",
                         temps_gras=False, ecart="—", ouverts="—", utilisation="—", distance="—")
        lignes.append(ligne)
    return {"titre": titre, "sous_titre": sous_titre, "lignes": lignes, "meilleur_cout": best}
