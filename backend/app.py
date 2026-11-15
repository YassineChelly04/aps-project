# -*- coding: utf-8 -*-
"""API du tableau de bord 1 (Module 1 · Distribution).  Lancement :  uvicorn backend.app:app"""
from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import donnees, tournees
from .api_module2 import routeur as routeur_m2
from .donnees import RACINE, FormatInvalide
from .indicateurs import comparer, ecart, evaluer, resume
from .methodes import METHODES, PHASES, ArretSansSolution, MethodeIndisponible, resoudre, tuer_solveurs
from .travaux import EXECUTEUR as _executeur, VERROU as _verrou

DOSSIER_SORTIES = RACINE / "sorties"
FRONTEND = RACINE / "frontend"

app = FastAPI(title="Sijar · Planification de la distribution et des tournées")
app.include_router(routeur_m2)
INSTANCES: dict = {}           # id -> DonneesInstance
JOBS: dict = {}                # job_id -> etat
# Un seul calcul a la fois (file partagee avec le module 2, backend/travaux.py).


def _instance(ident: str):
    di = INSTANCES.get(ident)
    if di is None:
        raise HTTPException(404, f"Instance inconnue : {ident}. Rechargez le fichier.")
    return di


def _modele(m: str) -> str:
    if m not in ("gap", "sscflp"):
        raise HTTPException(422, "modele doit valoir 'gap' ou 'sscflp'")
    return m


# ----------------------------------------------------------------------------- données
@app.get("/api/exemples")
def exemples():
    return {"exemples": donnees.liste_exemples(), "methodes": METHODES, "phases": PHASES}


@app.post("/api/instance")
async def instance(request: Request):
    """Corps multipart (champ « fichier ») ou JSON {"exemple": "S"|"M"|"L"} ou {"id": "<id d'instance>"}
    (instance du jeu ou instance corrigée par le retour du module 2)."""
    try:
        if request.headers.get("content-type", "").startswith("multipart/"):
            form = await request.form()
            fichier = form.get("fichier")
            if fichier is None:
                raise FormatInvalide()
            try:
                brut = json.loads(await fichier.read())
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise FormatInvalide() from None
            ident = brut.get("meta", {}).get("id") if isinstance(brut, dict) else None
            di = donnees.charger(brut, donnees.trouver_npz(ident) if ident else None)
        else:
            corps = await request.json()
            if corps.get("id"):
                chemin = tournees.trouver_instance(str(corps["id"]))
                if chemin is None:
                    raise HTTPException(404, f"Instance introuvable : {corps['id']}")
                di = donnees.charger_fichier(chemin)
                INSTANCES[di.id] = di
                return resume(di)
            chemin = donnees.chemin_exemple(str(corps.get("exemple", "")))
            if chemin is None:
                raise HTTPException(404, "Jeu d'exemple introuvable.")
            di = donnees.charger_fichier(chemin)
    except FormatInvalide as e:
        raise HTTPException(422, str(e)) from None
    INSTANCES[di.id] = di
    return resume(di)


# ----------------------------------------------------------------------------- calcul
class DemandeCalcul(BaseModel):
    instance: str
    modele: str
    limite_temps: float = 120
    graine: int = 0


def _executer(job_id: str):
    job = JOBS[job_id]
    di = INSTANCES[job["instance"]]

    def progression(phase, fraction):
        if not job["arret"].is_set():
            job.update(phase=phase, fraction=fraction)

    with _verrou:
        if job["arret"].is_set():  # arrete pendant l'attente : rien a calculer
            job.update(etat="arrete", erreur="Arrêté avant le début du calcul.")
            return
        job.update(etat="en_cours", debut=time.perf_counter())
    try:
        res = resoudre(job["cle"], di, job["modele"], job["limite_temps"], job["graine"], progression, job["arret"])
        job.update(etat="termine", resultat=res)
    except ArretSansSolution as e:
        job.update(etat="arrete", erreur=str(e))
    except Exception as e:  # erreur remontee au frontend, le serveur continue
        job.update(etat="erreur", erreur=str(e))


@app.post("/api/calcul/{cle}")
def lancer(cle: str, demande: DemandeCalcul):
    if cle not in METHODES:
        raise HTTPException(404, f"Méthode inconnue : {cle}")
    if not METHODES[cle]["pret"]:
        raise HTTPException(409, str(MethodeIndisponible(f"{METHODES[cle]['num']} {METHODES[cle]['nom']} : jalon ultérieur.")))
    _instance(demande.instance)
    job_id = uuid.uuid4().hex[:12]
    with _verrou:
        JOBS[job_id] = {"cle": cle, "instance": demande.instance, "modele": _modele(demande.modele),
                        "limite_temps": demande.limite_temps, "graine": demande.graine,
                        "etat": "en_attente", "phase": "En attente du calcul précédent…", "fraction": 0.0, "debut": None,
                        "arret": threading.Event()}
    _executeur.submit(_executer, job_id)
    return {"job_id": job_id}


@app.post("/api/calcul/{job_id}/arreter")
def arreter(job_id: str):
    """Interrompt un calcul : la méthode rend sa meilleure solution trouvée jusque-là."""
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "Calcul inconnu.")
    with _verrou:
        if job["etat"] not in ("en_attente", "en_cours"):
            return {"etat": job["etat"]}
        job["arret"].set()
        if job["etat"] == "en_attente":
            job.update(etat="arrete", erreur="Arrêté avant le début du calcul.")
            return {"etat": "arrete"}
        job["phase"] = "Arrêt en cours…"
    tuer_solveurs()
    return {"etat": "en_cours"}


@app.get("/api/calcul/{job_id}")
def etat(job_id: str):
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "Calcul inconnu.")
    out = {"job_id": job_id, "cle": job["cle"], "etat": job["etat"], "modele": job["modele"]}
    if job["etat"] in ("en_attente", "en_cours"):
        out.update(phase=job["phase"], fraction=job["fraction"],
                   ecoule=time.perf_counter() - job["debut"] if job["debut"] else 0.0)
    elif job["etat"] == "termine":
        out["resultat"] = job["resultat"]
    else:
        out["erreur"] = job["erreur"]
    return out


class DemandeComparaison(BaseModel):
    job_ids: list[str]


@app.post("/api/comparer")
def comparaison(demande: DemandeComparaison):
    """Titre-conclusion et tableau des 6 indicateurs pour les calculs terminés (même instance, même modèle)."""
    jobs = [JOBS[j] for j in demande.job_ids if j in JOBS and JOBS[j]["etat"] == "termine"]
    if not jobs:
        raise HTTPException(422, "Aucun calcul terminé.")
    di = _instance(jobs[0]["instance"])
    return comparer(di, {j["cle"]: j["resultat"] for j in jobs}, METHODES)


# ----------------------------------------------------------------------------- décision
class DemandeEvaluation(BaseModel):
    instance: str
    modele: str
    affectation: dict[str, str]
    meilleur_cout: float | None = None


@app.post("/api/evaluer")
def evaluation(demande: DemandeEvaluation):
    di = _instance(demande.instance)
    try:
        a = di.indices(demande.affectation)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    ind = evaluer(di, a, _modele(demande.modele))
    if demande.meilleur_cout:
        ind["ecart_meilleure"] = ecart(ind["cout_total"], demande.meilleur_cout)
    return ind


class Ajustement(BaseModel):
    magasin: str
    de: str
    vers: str


class DemandeValidation(BaseModel):
    instance: str
    modele: str
    methode: str
    affectation: dict[str, str]
    ajustements: list[Ajustement] = []


@app.post("/api/valider")
def valider(demande: DemandeValidation):
    di = _instance(demande.instance)
    modele = _modele(demande.modele)
    try:
        a = di.indices(demande.affectation)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    ind = evaluer(di, a, modele)
    if not ind["realisable"]:
        raise HTTPException(422, "Une capacité d'entrepôt est dépassée : l'affectation ne peut pas être validée.")
    maintenant = datetime.now()
    scenario = f"SC-{di.id}-{'SSC' if modele == 'sscflp' else 'GAP'}-{demande.methode}-{maintenant:%m%d-%H%M%S}"
    W = di.entrepots
    # Fichier d'echange (§5) : champs exiges (identifiant, coordonnees, demande, entrepot affecte ;
    # entrepots avec coordonnees et capacite ; scenario) + couts c_ij et distances vers chaque
    # entrepot, pour que le module 2 puisse reviser l'affectation et faire le retour sans relire l'instance.
    sortie = {
        "scenario": scenario, "instance": di.id, "modele": modele, "methode": demande.methode,
        "date": maintenant.isoformat(timespec="seconds"), "parent": None,
        "ajustements": [x.model_dump() for x in demande.ajustements],
        "cout_total": ind["cout_total"], "cout_affectation": ind["cout_affectation"], "cout_fixe": ind["cout_fixe"],
        "unite_cout": di.brut["meta"].get("unite_cout", "TND / semaine"),
        "unite_demande": di.brut["meta"].get("unite_demande", "palettes / semaine"),
        "kpal": float(di.brut["meta"].get("kpal", donnees.KPAL)),
        "entrepots": [{"id": e["id"], "nom": di.nom_court(j), "lat": e["lat"], "lon": e["lon"], "capacite": e["capacite"],
                       "cout_fixe": float(di.f[j]), "ouvert": bool(ind["ouverts"][j])} for j, e in enumerate(W)],
        "magasins": [{"id": s["id"], "ville": s.get("ville", ""), "lat": s["lat"], "lon": s["lon"], "demande": s["demande"],
                      "entrepot": W[int(a[i])]["id"], "cout_affectation": round(float(di.C[i, a[i]]), 2),
                      "distance_km": round(float(di.dist[i, a[i]]), 3),
                      "couts": {e["id"]: round(float(di.C[i, j]), 2) for j, e in enumerate(W)},
                      "distances_km": {e["id"]: round(float(di.dist[i, j]), 3) for j, e in enumerate(W)}}
                     for i, s in enumerate(di.magasins)],
    }
    DOSSIER_SORTIES.mkdir(exist_ok=True)
    chemin = DOSSIER_SORTIES / f"affectation_validee_{scenario}.json"
    chemin.write_text(json.dumps(sortie, ensure_ascii=False, indent=1), encoding="utf-8")
    try:  # chemin relatif au projet pour l'affichage ; absolu si sorties/ est ailleurs (tests)
        fichier = str(chemin.relative_to(RACINE))
    except ValueError:
        fichier = str(chemin)
    return {"scenario": scenario, "fichier": fichier, "n_magasins": di.n,
            "n_ouverts": ind["entrepots_ouverts"], "cout_total": ind["cout_total"]}


# ----------------------------------------------------------------------------- frontend statique
@app.get("/")
def accueil():
    return FileResponse(FRONTEND / "index.html")


app.mount("/", StaticFiles(directory=FRONTEND), name="frontend")
