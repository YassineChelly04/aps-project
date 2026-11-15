# -*- coding: utf-8 -*-
"""Module 2 cote serveur : lecture du fichier d'echange, sous-problemes par entrepot, cache,
indicateurs des fronts, plan final, export et retour vers le module 1 (cahier des charges §4.4 et §5).

Regle d'integration (§5) : le module 2 lit UNIQUEMENT le fichier d'echange
sorties/affectation_validee_<scenario>.json ecrit par le module 1. Chaque entrepot ouvert forme un
sous-probleme (entrepot + ses magasins). Sa SIGNATURE (entrepot, magasins, coordonnees, parametres
des matrices) sert de cle de cache : apres une modification de l'affectation, seuls les entrepots
dont l'ensemble de magasins a change sont recalcules."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from .donnees import DOSSIER_INSTANCES, RACINE

import sys
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))
import module2_tournees as m2  # noqa: E402

DOSSIER_SORTIES = RACINE / "sorties"
DOSSIER_CACHE = DOSSIER_SORTIES / "cache_tournees"
DOSSIER_PLANS = DOSSIER_SORTIES / "plans"
DOSSIER_CORRIGEES = DOSSIER_SORTIES / "instances_corrigees"
PREFIXE = "affectation_validee_"
VERSION_MATRICES = "v1"           # a changer si le modele des matrices change (invalide le cache)
VERSION_METHODES = "r2"           # a changer si les parametres par defaut des methodes changent
GRAINE_CONGESTION = 2026
CAPACITE_VEHICULE = 33            # palettes par semi-remorque (retour vers le module 1)

METHODES_M2 = {
    "ws": {"num": "1", "nom": "Somme pondérée", "famille": "Heuristique",
           "principe": "Plus proche voisin + 2-opt + Or-opt sur λ·distance + (1−λ)·temps, λ de 0 à 1 (21 valeurs)",
           "ref": "Lin & Kernighan (1973) ; Or (1976)", "stochastique": False, "couleur": "#D9822B", "forme": "carre"},
    "nsga": {"num": "2", "nom": "NSGA-II", "famille": "Évolutionnaire à base de Pareto",
             "principe": "Permutation, population 100, croisement OX, mutation inversion / échange (p = 0,6), tri par non-dominance",
             "ref": "Deb et al. (2002)", "stochastique": True, "couleur": "#1E8A6E", "forme": "triangle"},
    "pls": {"num": "3", "nom": "2PPLS", "famille": "Recherche locale de Pareto",
            "principe": "Phase 1 dichotomique (points supportés), phase 2 recherche locale de Pareto en 2-opt",
            "ref": "Lust & Teghem (2010)", "stochastique": True, "couleur": "#B8336A", "forme": "losange"},
    "eps": {"num": "4", "nom": "ε-contrainte exacte", "famille": "Exacte (solveur HiGHS)",
            "principe": "min distance s.c. temps ≤ ε, lexicographique ; coupes de sous-tours ; front complet si le temps le permet",
            "ref": "Haimes et al. (1971) ; Dantzig, Fulkerson & Johnson (1954)", "stochastique": False,
            "couleur": "#2443C4", "forme": "rond"},
}
PHASES_M2 = "Matrices distance / temps"


class ScenarioInvalide(ValueError):
    pass


# ----------------------------------------------------------------------------- fichiers d'échange
def chemin_scenario(scenario: str) -> Path:
    if not scenario or any(c in scenario for c in "/\\:") or scenario.startswith("."):
        raise ScenarioInvalide("Identifiant de scénario invalide.")
    return DOSSIER_SORTIES / f"{PREFIXE}{scenario}.json"


def valider_scenario(sc: dict) -> dict:
    """Controle minimal du format du fichier d'echange (§5 : identifiant, coordonnees, demande,
    entrepot affecte pour chaque magasin ; coordonnees et capacite des entrepots ; scenario)."""
    try:
        assert isinstance(sc, dict) and sc.get("scenario")
        ids_e = {e["id"] for e in sc["entrepots"]}
        for e in sc["entrepots"]:
            float(e["lat"]); float(e["lon"]); float(e["capacite"])
        for s in sc["magasins"]:
            float(s["lat"]); float(s["lon"]); float(s["demande"])
            assert s["entrepot"] in ids_e
        assert sc["magasins"]
    except (AssertionError, KeyError, TypeError, ValueError):
        raise ScenarioInvalide("Ce fichier n'a pas le format du fichier d'échange du module 1.") from None
    return sc


def lire_scenario(scenario: str) -> dict:
    p = chemin_scenario(scenario)
    if not p.exists():
        raise FileNotFoundError(f"Scénario introuvable : {scenario}")
    return valider_scenario(json.loads(p.read_text(encoding="utf-8")))


def ecrire_scenario(sc: dict) -> Path:
    DOSSIER_SORTIES.mkdir(exist_ok=True)
    p = chemin_scenario(sc["scenario"])
    p.write_text(json.dumps(sc, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def charges(sc: dict) -> dict:
    ch = {e["id"]: 0.0 for e in sc["entrepots"]}
    for s in sc["magasins"]:
        ch[s["entrepot"]] += float(s["demande"])
    return ch


def resume_scenario(sc: dict) -> dict:
    ch = charges(sc)
    sp = sous_problemes(sc)
    return {
        "scenario": sc["scenario"], "instance": sc.get("instance", ""), "modele": sc.get("modele", ""),
        "methode": sc.get("methode", ""), "cout_total": sc.get("cout_total"), "date": sc.get("date", ""),
        "parent": sc.get("parent"), "ajustements": sc.get("ajustements", []),
        "n_magasins": len(sc["magasins"]), "n_entrepots": len(sc["entrepots"]),
        "n_tournees": len(sp),
        "entrepots": [{"id": e["id"], "nom": e.get("nom", e["id"]), "lat": e["lat"], "lon": e["lon"],
                       "capacite": float(e["capacite"]), "charge": ch[e["id"]], "ouvert": ch[e["id"]] > 0}
                      for e in sc["entrepots"]],
        "magasins": [{"id": s["id"], "ville": s.get("ville", ""), "lat": s["lat"], "lon": s["lon"],
                      "demande": float(s["demande"]), "entrepot": s["entrepot"]} for s in sc["magasins"]],
        "tournees": [{"entrepot": p["entrepot"]["id"], "n": len(p["magasins"]), "signature": p["signature"]} for p in sp],
    }


def lister_scenarios() -> list:
    out = []
    for p in sorted(DOSSIER_SORTIES.glob(f"{PREFIXE}*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            sc = valider_scenario(json.loads(p.read_text(encoding="utf-8")))
        except (ScenarioInvalide, json.JSONDecodeError, UnicodeDecodeError):
            continue
        ch = charges(sc)
        out.append({"scenario": sc["scenario"], "instance": sc.get("instance", ""), "modele": sc.get("modele", ""),
                    "methode": sc.get("methode", ""), "cout_total": sc.get("cout_total"),
                    "n_magasins": len(sc["magasins"]), "n_ouverts": sum(1 for v in ch.values() if v > 0),
                    "ajustements": len(sc.get("ajustements", [])), "parent": sc.get("parent"),
                    "date": sc.get("date") or datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")})
    return out


# ----------------------------------------------------------------------------- sous-problèmes
def sous_problemes(sc: dict) -> list:
    """Un sous-probleme par entrepot ayant au moins un magasin, avec sa signature (cle de cache)."""
    out = []
    for e in sc["entrepots"]:
        mags = sorted((s for s in sc["magasins"] if s["entrepot"] == e["id"]), key=lambda s: s["id"])
        if not mags:
            continue
        cle = json.dumps([VERSION_MATRICES, GRAINE_CONGESTION, e["id"], round(float(e["lat"]), 6), round(float(e["lon"]), 6),
                          [[s["id"], round(float(s["lat"]), 6), round(float(s["lon"]), 6)] for s in mags]])
        out.append({"entrepot": e, "magasins": mags, "signature": hashlib.sha1(cle.encode()).hexdigest()[:16]})
    return out


def matrices_sp(sp: dict):
    e, mags = sp["entrepot"], sp["magasins"]
    ids = [e["id"]] + [s["id"] for s in mags]
    lat = [float(e["lat"])] + [float(s["lat"]) for s in mags]
    lon = [float(e["lon"])] + [float(s["lon"]) for s in mags]
    return m2.matrices(ids, lat, lon, GRAINE_CONGESTION)


def _cle_cache(signature, methode, limite, graine):
    g = graine if METHODES_M2[methode]["stochastique"] else "-"
    return f"{signature}-{methode}{VERSION_METHODES}-{float(limite):g}-{g}"


_CACHE: dict = {}


def cache_lire(cle):
    if cle in _CACHE:
        return _CACHE[cle]
    p = DOSSIER_CACHE / f"{cle}.json"
    if p.exists():
        try:
            _CACHE[cle] = json.loads(p.read_text(encoding="utf-8"))
            return _CACHE[cle]
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
    return None


def cache_ecrire(cle, valeur):
    _CACHE[cle] = valeur
    DOSSIER_CACHE.mkdir(parents=True, exist_ok=True)
    (DOSSIER_CACHE / f"{cle}.json").write_text(json.dumps(valeur), encoding="utf-8")


def vider_cache_memoire():
    _CACHE.clear()


def resoudre_sp(sp, methode, limite, graine, arret=None, rapport=None, D=None, T=None):
    """Applique une methode a un sous-probleme. Les tournees sont rendues en identifiants de magasins."""
    if D is None:
        D, T = matrices_sp(sp)
    fn = m2.METHODES_TSP[methode]
    t0 = time.perf_counter()
    r = fn(D, T, time_limit=limite, seed=graine, arret=arret, rapport=rapport)
    temps = time.perf_counter() - t0
    ids = [sp["entrepot"]["id"]] + [s["id"] for s in sp["magasins"]]
    sols = [{"sequence": [ids[k] for k in s["tour"][1:]], "distance_km": float(s["f1"]), "temps_min": float(s["f2"])}
            for s in r["solutions"]]
    stats = {k: (float(v) if isinstance(v, (np.floating,)) else v) for k, v in r["stats"].items()
             if not isinstance(v, (list, np.ndarray))}
    return {"solutions": sols, "stats": stats, "temps_s": temps,
            "arrete": bool(arret is not None and arret.is_set())}


def indicateurs_sp(resultats: dict) -> dict:
    """Indicateurs de qualite des fronts d'un entrepot (HV relatif, IGD, contribution au front de reference)."""
    fronts = {k: [(s["distance_km"], s["temps_min"]) for s in r["solutions"]] for k, r in resultats.items()}
    ind = m2.indicateurs_fronts(fronts)
    ref = {}
    tous = [(k, i, s) for k, r in resultats.items() for i, s in enumerate(r["solutions"])]
    if tous:
        nd = m2.non_domines([(s["distance_km"], s["temps_min"]) for _, _, s in tous])
        ref = [{"methode": tous[i][0], "index": tous[i][1], "distance_km": tous[i][2]["distance_km"],
                "temps_min": tous[i][2]["temps_min"]} for i in nd]
    exact = resultats.get("eps", {}).get("stats", {}).get("complet", False)
    return {"methodes": {k: {kk: float(vv) for kk, vv in v.items()} for k, v in ind.items()},
            "front_reference": ref, "reference_exacte": bool(exact)}


# ----------------------------------------------------------------------------- calcul complet (job)
def calculer(sc, methodes, limite, graine, arret=None, progression=None):
    """Calcule (ou reprend du cache) les fronts de chaque entrepot pour chaque methode."""
    sps = sous_problemes(sc)
    total = max(1, len(sps) * len(methodes))
    fait = 0
    sortie = []
    for sp in sps:
        eid = sp["entrepot"]["id"]
        res, recalc, reutil = {}, [], []
        D = T = None
        for k in methodes:
            if arret is not None and arret.is_set():
                break
            cle = _cle_cache(sp["signature"], k, limite, graine)
            r = cache_lire(cle)
            if r is not None:
                reutil.append(k)
            else:
                if D is None:
                    D, T = matrices_sp(sp)
                if progression:
                    progression(f"{eid} · {METHODES_M2[k]['nom']}", fait / total)
                base = fait

                def rapport(fr, base=base):
                    if progression:
                        progression(f"{eid} · {METHODES_M2[k]['nom']}", (base + fr) / total)
                r = resoudre_sp(sp, k, limite, graine, arret, rapport, D, T)
                if not r["arrete"]:
                    cache_ecrire(cle, r)
                recalc.append(k)
            res[k] = r
            fait += 1
        demande = sum(float(s["demande"]) for s in sp["magasins"])
        sortie.append({"entrepot": eid, "nom": sp["entrepot"].get("nom", eid), "lat": sp["entrepot"]["lat"],
                       "lon": sp["entrepot"]["lon"], "n": len(sp["magasins"]), "demande": demande,
                       "signature": sp["signature"], "resultats": res, "recalcules": recalc, "reutilises": reutil,
                       "indicateurs": indicateurs_sp(res) if res else {}})
        if arret is not None and arret.is_set():
            break
    n_recalc = sum(1 for x in sortie if x["recalcules"])
    return {"scenario": sc["scenario"], "methodes": list(methodes), "limite_temps": limite, "graine": graine,
            "entrepots": sortie, "n_recalcules": n_recalc, "n_reutilises": len(sortie) - n_recalc,
            "arrete": bool(arret is not None and arret.is_set())}


# ----------------------------------------------------------------------------- révision de l'affectation
def ajuster(sc: dict, magasin: str, vers: str) -> dict:
    """Deplace un magasin vers un autre entrepot et ecrit un NOUVEAU scenario derive (le fichier
    d'origine n'est pas modifie). Refuse un depassement de capacite. Le cout du module 1 est
    recalcule a partir des couts c_ij et des couts fixes portes par le fichier d'echange."""
    ent = {e["id"]: e for e in sc["entrepots"]}
    if vers not in ent:
        raise ScenarioInvalide(f"Entrepôt inconnu : {vers}")
    mag = next((s for s in sc["magasins"] if s["id"] == magasin), None)
    if mag is None:
        raise ScenarioInvalide(f"Magasin inconnu : {magasin}")
    de = mag["entrepot"]
    if de == vers:
        raise ScenarioInvalide("Le magasin est déjà servi par cet entrepôt.")
    ch = charges(sc)
    if ch[vers] + float(mag["demande"]) > float(ent[vers]["capacite"]) + 1e-9:
        raise ScenarioInvalide(f"Capacité de {vers} dépassée : {ch[vers] + float(mag['demande']):.0f} > {float(ent[vers]['capacite']):.0f} palettes.")
    nv = json.loads(json.dumps(sc))
    for s in nv["magasins"]:
        if s["id"] == magasin:
            s["entrepot"] = vers
            if "couts" in s and vers in s["couts"]:
                s["cout_affectation"] = s["couts"][vers]
            if "distances_km" in s and vers in s["distances_km"]:
                s["distance_km"] = s["distances_km"][vers]
    base = sc["scenario"].split("~")[0]
    k = 1
    while chemin_scenario(f"{base}~r{k}").exists():
        k += 1
    nv["scenario"] = f"{base}~r{k}"
    nv["parent"] = sc["scenario"]
    nv["ajustements"] = list(sc.get("ajustements", [])) + [{"magasin": magasin, "de": de, "vers": vers, "module": 2}]
    nv["date"] = datetime.now().isoformat(timespec="seconds")
    ch2 = charges(nv)
    for e in nv["entrepots"]:
        e["ouvert"] = ch2[e["id"]] > 0 or (nv.get("modele") == "gap")
    if all("cout_affectation" in s for s in nv["magasins"]):
        ca = sum(float(s["cout_affectation"]) for s in nv["magasins"])
        cf = sum(float(e.get("cout_fixe", 0.0)) for e in nv["entrepots"] if ch2[e["id"]] > 0) if nv.get("modele") == "sscflp" else 0.0
        nv["cout_affectation"], nv["cout_fixe"], nv["cout_total"] = round(ca, 2), round(cf, 2), round(ca + cf, 2)
    ecrire_scenario(nv)
    return nv


# ----------------------------------------------------------------------------- plan final
def construire_plan(sc: dict, choix: dict) -> dict:
    """choix : {id_entrepot: {"methode": cle, "sequence": [id_magasin, ...]}}.
    Les indicateurs sont RECALCULES ici a partir des matrices (on ne fait pas confiance au client)."""
    lignes, arrets = [], []
    kpal = float(sc.get("kpal", 0.12324))
    cout_km = CAPACITE_VEHICULE * kpal
    for sp in sous_problemes(sc):
        eid = sp["entrepot"]["id"]
        ch = choix.get(eid)
        if ch is None:
            raise ScenarioInvalide(f"Aucune tournée choisie pour {eid}.")
        attendu = {s["id"] for s in sp["magasins"]}
        seq = list(ch["sequence"])
        if set(seq) != attendu or len(seq) != len(attendu):
            raise ScenarioInvalide(f"La tournée de {eid} ne visite pas exactement ses magasins.")
        D, T = matrices_sp(sp)
        pos = {s["id"]: k + 1 for k, s in enumerate(sp["magasins"])}
        tour = [0] + [pos[x] for x in seq]
        f1, f2 = m2.evaluer(tour, D, T)
        par_id = {s["id"]: s for s in sp["magasins"]}
        demande = sum(float(s["demande"]) for s in sp["magasins"])
        service = m2.SERVICE_MIN * len(seq)
        # Retour (bonus §5) : cout de transport suppose par le module 1 (c_ij = d_i (2 KPAL dist + manut))
        # contre un ordre de grandeur du cout des tournees : ceil(D / Q) rotations par semaine,
        # chacune de la longueur de la tournee, a 33 x KPAL TND/km (semi-remorque plein).
        transp_m1 = None
        if all("distance_km" in par_id[x] for x in seq):
            transp_m1 = sum(2 * kpal * float(par_id[x]["demande"]) * float(par_id[x]["distance_km"]) for x in seq)
        rotations = math.ceil(demande / CAPACITE_VEHICULE)
        cout_tournees = rotations * f1 * cout_km
        lignes.append({"entrepot": eid, "nom": sp["entrepot"].get("nom", eid), "methode": ch.get("methode", ""),
                       "arrets": len(seq), "demande": demande, "distance_km": f1, "conduite_min": f2,
                       "service_min": service, "temps_total_min": f2 + service, "sequence": seq,
                       "transport_m1": transp_m1, "rotations": rotations, "cout_tournees": cout_tournees,
                       "ratio_retour": (cout_tournees / transp_m1) if transp_m1 else None})
        prec = sp["entrepot"]
        cumul_d = cumul_t = 0.0
        pts = [sp["entrepot"]] + [par_id[x] for x in seq] + [sp["entrepot"]]
        for r in range(1, len(pts)):
            a_, b_ = tour[r - 1], tour[r] if r < len(tour) else 0
            cumul_d += float(D[a_, b_]); cumul_t += float(T[a_, b_])
            arrets.append({"scenario": sc["scenario"], "entrepot": eid, "rang": r, "arret": pts[r]["id"],
                           "lat": pts[r]["lat"], "lon": pts[r]["lon"],
                           "demande": float(pts[r].get("demande", 0)) if r < len(pts) - 1 else 0.0,
                           "distance_cumulee_km": round(cumul_d, 3), "conduite_cumulee_min": round(cumul_t, 2)})
            prec = pts[r]
    tot = {k: sum(l[k] for l in lignes) for k in ("arrets", "demande", "distance_km", "conduite_min", "service_min",
                                                  "temps_total_min", "cout_tournees")}
    tm1 = [l["transport_m1"] for l in lignes if l["transport_m1"] is not None]
    tot["transport_m1"] = sum(tm1) if len(tm1) == len(lignes) else None
    plan = {"scenario": sc["scenario"], "instance": sc.get("instance", ""), "modele": sc.get("modele", ""),
            "methode_m1": sc.get("methode", ""), "cout_m1": sc.get("cout_total"),
            "ajustements": len(sc.get("ajustements", [])), "n_tournees": len(lignes),
            "date": datetime.now().isoformat(timespec="seconds"), "parametres": {
                "facteur_route": m2.FACTEUR_ROUTE,
                "vitesses": [{"troncon_jusqu_a_km": (b if math.isfinite(b) else None), "kmh": v} for b, v in m2.VITESSES],
                "congestion": list(m2.CONGESTION), "service_min": m2.SERVICE_MIN,
                "capacite_vehicule": CAPACITE_VEHICULE, "cout_km": cout_km},
            "tournees": lignes, "totaux": tot, "arrets": arrets}
    return plan


def enregistrer_plan(plan: dict) -> Path:
    DOSSIER_PLANS.mkdir(parents=True, exist_ok=True)
    p = DOSSIER_PLANS / f"plan_{plan['scenario']}.json"
    p.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def lister_plans() -> list:
    out = []
    for p in sorted(DOSSIER_PLANS.glob("plan_*.json"), key=lambda p: p.stat().st_mtime):
        try:
            pl = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        t = pl["totaux"]
        out.append({"scenario": pl["scenario"], "instance": pl["instance"], "modele": pl["modele"],
                    "methode_m1": pl["methode_m1"], "cout_m1": pl["cout_m1"], "ajustements": pl["ajustements"],
                    "n_tournees": pl["n_tournees"], "arrets": t["arrets"], "distance_km": t["distance_km"],
                    "conduite_min": t["conduite_min"], "temps_total_min": t["temps_total_min"],
                    "cout_tournees": t.get("cout_tournees"), "transport_m1": t.get("transport_m1"),
                    "methodes_m2": sorted({l["methode"] for l in pl["tournees"]}), "date": pl["date"]})
    return out


def lire_plan(scenario: str) -> dict:
    chemin_scenario(scenario)  # valide l'identifiant
    p = DOSSIER_PLANS / f"plan_{scenario}.json"
    if not p.exists():
        raise FileNotFoundError(f"Aucun plan enregistré pour {scenario}.")
    return json.loads(p.read_text(encoding="utf-8"))


def export_csv(plan: dict) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["scenario", "entrepot", "rang", "arret", "lat", "lon", "demande_palettes",
                "distance_cumulee_km", "conduite_cumulee_min"])
    for a in plan["arrets"]:
        w.writerow([a["scenario"], a["entrepot"], a["rang"], a["arret"], a["lat"], a["lon"], a["demande"],
                    a["distance_cumulee_km"], a["conduite_cumulee_min"]])
    return ("﻿" + buf.getvalue()).encode("utf-8")  # BOM : Excel ouvre l'UTF-8 correctement


def export_xlsx(plan: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "Synthèse"
    ws.append(["Scénario", plan["scenario"]]); ws.append(["Instance", plan["instance"]])
    ws.append(["Modèle (module 1)", plan["modele"]]); ws.append(["Méthode (module 1)", plan["methode_m1"]])
    ws.append(["Coût d'affectation (TND / semaine)", plan["cout_m1"]]); ws.append([])
    entete = ["Entrepôt", "Nom", "Méthode M2", "Arrêts", "Demande (pal.)", "Distance (km)", "Conduite (min)",
              "Service (min)", "Temps total (min)"]
    ws.append(entete)
    for c in ws[ws.max_row]:
        c.font = Font(bold=True)
    for l in plan["tournees"]:
        ws.append([l["entrepot"], l["nom"], l["methode"], l["arrets"], l["demande"], round(l["distance_km"], 2),
                   round(l["conduite_min"], 1), l["service_min"], round(l["temps_total_min"], 1)])
    t = plan["totaux"]
    ws.append(["Réseau", "", "", t["arrets"], t["demande"], round(t["distance_km"], 2), round(t["conduite_min"], 1),
               t["service_min"], round(t["temps_total_min"], 1)])
    for c in ws[ws.max_row]:
        c.font = Font(bold=True)
    ws2 = wb.create_sheet("Tournées")
    ws2.append(["Entrepôt", "Rang", "Arrêt", "Latitude", "Longitude", "Demande (pal.)", "Distance cumulée (km)",
                "Conduite cumulée (min)"])
    for c in ws2[1]:
        c.font = Font(bold=True)
    for a in plan["arrets"]:
        ws2.append([a["entrepot"], a["rang"], a["arret"], a["lat"], a["lon"], a["demande"],
                    a["distance_cumulee_km"], a["conduite_cumulee_min"]])
    ws3 = wb.create_sheet("Paramètres")
    for k, v in plan["parametres"].items():
        ws3.append([k, json.dumps(v) if isinstance(v, (list, dict)) else v])
    for feuille in (ws, ws2, ws3):
        for col in feuille.columns:
            feuille.column_dimensions[col[0].column_letter].width = max(12, min(40, max(len(str(c.value or "")) for c in col) + 2))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ----------------------------------------------------------------------------- retour vers le module 1 (bonus)
def trouver_instance(ident: str) -> Path | None:
    for p in list(DOSSIER_INSTANCES.glob(f"*/{ident}/instance.json")) + list(DOSSIER_CORRIGEES.glob(f"{ident}/instance.json")):
        return p
    return None


def instance_corrigee(plan: dict) -> tuple[str, Path]:
    """Cree une instance du module 1 dont la part transport de c_ij est multipliee, pour chaque
    entrepot, par le ratio (cout des tournees / cout de transport suppose). Les entrepots sans
    tournee gardent un facteur 1. Renvoie (id, chemin)."""
    src = trouver_instance(plan["instance"])
    if src is None:
        raise FileNotFoundError(f"Instance d'origine introuvable : {plan['instance']}")
    brut = json.loads(src.read_text(encoding="utf-8"))
    with np.load(src.parent / "matrices.npz") as z:
        dist = np.asarray(z["distance_km"], float)
    d = np.array([float(s["demande"]) for s in brut["magasins"]])
    manut = np.array([float(e.get("cout_manutention_palette", 0.0)) for e in brut["entrepots"]])
    kpal = float(brut["meta"].get("kpal", 0.12324))
    facteurs = {l["entrepot"]: float(np.clip(l["ratio_retour"], 0.5, 3.0)) for l in plan["tournees"] if l["ratio_retour"]}
    k = np.array([facteurs.get(e["id"], 1.0) for e in brut["entrepots"]])
    C = np.round(d[:, None] * (2 * kpal * dist * k[None, :] + manut[None, :]), 2)
    base = plan["instance"].split("-retour")[0]
    n = 1
    while (DOSSIER_CORRIGEES / f"{base}-retour{n}").exists():
        n += 1
    ident = f"{base}-retour{n}"
    brut["meta"] = dict(brut["meta"], id=ident, source=f"coûts corrigés par le retour du module 2 (scénario {plan['scenario']})",
                        facteurs_transport=facteurs)
    brut["cout_affectation"] = C.tolist()
    brut.pop("reference", None)
    dossier = DOSSIER_CORRIGEES / ident
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "instance.json").write_text(json.dumps(brut, ensure_ascii=False, indent=1), encoding="utf-8")
    np.savez_compressed(dossier / "matrices.npz", distance_km=dist, cout_affectation=C)
    return ident, dossier / "instance.json"
