# -*- coding: utf-8 -*-
"""API du tableau de bord 2 (Module 2 · Tournées). Toutes les routes commencent par /api/m2."""
from __future__ import annotations

import json
import time
import uuid
import threading

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from . import classeur as cl
from . import tournees as tr
from .travaux import EXECUTEUR, VERROU

routeur = APIRouter(prefix="/api/m2")
JOBS_M2: dict = {}


def _scenario(scenario: str) -> dict:
    try:
        return tr.lire_scenario(scenario)
    except tr.ScenarioInvalide as e:
        raise HTTPException(422, str(e)) from None
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from None


@routeur.get("/methodes")
def methodes():
    return {"methodes": tr.METHODES_M2, "service_min": tr.m2.SERVICE_MIN}


@routeur.get("/scenarios")
def scenarios():
    return {"scenarios": tr.lister_scenarios()}


@routeur.get("/scenario/{scenario}")
def scenario(scenario: str):
    return tr.resume_scenario(_scenario(scenario))


@routeur.post("/scenario")
async def deposer_scenario(request: Request):
    """Dépôt d'un fichier d'échange (multipart, champ « fichier ») : classeur .xlsx du module 1
    (modifié ou non) ou fichier JSON. Il est validé puis rangé dans sorties/. Un classeur modifié
    devient un scénario dérivé ; la réponse liste les magasins déplacés et les entrepôts touchés."""
    form = await request.form()
    f = form.get("fichier")
    if f is None:
        raise HTTPException(422, "Aucun fichier reçu.")
    contenu = await f.read()
    try:
        if contenu[:2] == b"PK":  # .xlsx = archive zip
            sc, diff = cl.importer(contenu)
        else:
            sc, diff = cl.importer_json(contenu)
    except tr.ScenarioInvalide as e:
        raise HTTPException(422, str(e)) from None
    return dict(tr.resume_scenario(sc), import_=diff)


@routeur.get("/scenario/{scenario}/feuilles")
def scenario_feuilles(scenario: str):
    """Contenu du classeur d'échange, en valeurs, pour l'aperçu dans l'outil."""
    return {"scenario": scenario, "fichier": cl.nom_fichier(scenario), "feuilles": cl.feuilles(_scenario(scenario))}


@routeur.get("/scenario/{scenario}/xlsx")
def scenario_xlsx(scenario: str):
    """Classeur d'échange .xlsx du scénario (sortie du module 1, lisible et modifiable dans Excel)."""
    sc = _scenario(scenario)
    return Response(cl.export_classeur(sc),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{cl.nom_fichier(scenario)}"'})


# ----------------------------------------------------------------------------- calcul
class DemandeCalculM2(BaseModel):
    scenario: str
    methodes: list[str] = ["ws", "nsga", "pls", "eps"]
    limite_temps: float = 20
    graine: int = 0


def _executer(job_id):
    job = JOBS_M2[job_id]
    sc = job["sc"]

    def progression(phase, fraction):
        if not job["arret"].is_set():
            job.update(phase=phase, fraction=fraction)

    with VERROU:
        if job["arret"].is_set():
            job.update(etat="arrete", erreur="Arrêté avant le début du calcul.")
            return
        job.update(etat="en_cours", debut=time.perf_counter())
    try:
        res = tr.calculer(sc, job["methodes"], job["limite_temps"], job["graine"], job["arret"], progression)
        res["temps_s"] = time.perf_counter() - job["debut"]
        job.update(etat="termine", resultat=res)
    except Exception as e:  # remonte au frontend, le serveur continue
        job.update(etat="erreur", erreur=str(e))


@routeur.post("/calcul")
def lancer(d: DemandeCalculM2):
    sc = _scenario(d.scenario)
    inconnues = [k for k in d.methodes if k not in tr.METHODES_M2]
    if inconnues or not d.methodes:
        raise HTTPException(422, f"Méthodes inconnues : {inconnues}" if inconnues else "Choisissez au moins une méthode.")
    if not (0 < d.limite_temps <= 3600):
        raise HTTPException(422, "La limite de temps doit être comprise entre 0 et 3600 s.")
    ordre = [k for k in tr.METHODES_M2 if k in d.methodes]
    job_id = uuid.uuid4().hex[:12]
    JOBS_M2[job_id] = {"sc": sc, "methodes": ordre, "limite_temps": d.limite_temps, "graine": d.graine,
                       "etat": "en_attente", "phase": "En attente du calcul précédent…", "fraction": 0.0,
                       "debut": None, "arret": threading.Event()}
    EXECUTEUR.submit(_executer, job_id)
    return {"job_id": job_id}


@routeur.get("/calcul/{job_id}")
def etat(job_id: str):
    job = JOBS_M2.get(job_id)
    if job is None:
        raise HTTPException(404, "Calcul inconnu.")
    out = {"job_id": job_id, "etat": job["etat"], "scenario": job["sc"]["scenario"]}
    if job["etat"] in ("en_attente", "en_cours"):
        out.update(phase=job["phase"], fraction=job["fraction"],
                   ecoule=time.perf_counter() - job["debut"] if job["debut"] else 0.0)
    elif job["etat"] == "termine":
        out["resultat"] = job["resultat"]
    else:
        out["erreur"] = job.get("erreur", "")
    return out


@routeur.post("/calcul/{job_id}/arreter")
def arreter(job_id: str):
    job = JOBS_M2.get(job_id)
    if job is None:
        raise HTTPException(404, "Calcul inconnu.")
    with VERROU:
        if job["etat"] == "en_attente":
            job["arret"].set()
            job.update(etat="arrete", erreur="Arrêté avant le début du calcul.")
        elif job["etat"] == "en_cours":
            job["arret"].set()
            job["phase"] = "Arrêt en cours…"
    return {"etat": job["etat"]}


# ----------------------------------------------------------------------------- révision de l'affectation
class DemandeAjustement(BaseModel):
    scenario: str
    magasin: str
    vers: str


@routeur.post("/ajuster")
def ajuster(d: DemandeAjustement):
    sc = _scenario(d.scenario)
    try:
        nv = tr.ajuster(sc, d.magasin, d.vers)
    except tr.ScenarioInvalide as e:
        raise HTTPException(422, str(e)) from None
    return tr.resume_scenario(nv)


# ----------------------------------------------------------------------------- plan final
class Choix(BaseModel):
    methode: str = ""
    sequence: list[str]


class DemandePlan(BaseModel):
    scenario: str
    choix: dict[str, Choix]
    enregistrer: bool = True


@routeur.post("/plan")
def plan(d: DemandePlan):
    sc = _scenario(d.scenario)
    try:
        p = tr.construire_plan(sc, {k: v.model_dump() for k, v in d.choix.items()})
    except tr.ScenarioInvalide as e:
        raise HTTPException(422, str(e)) from None
    if d.enregistrer:
        tr.enregistrer_plan(p)
    return p


@routeur.get("/plans")
def plans():
    return {"plans": tr.lister_plans()}


@routeur.get("/plan/{scenario}")
def lire_plan(scenario: str):
    try:
        return tr.lire_plan(scenario)
    except tr.ScenarioInvalide as e:
        raise HTTPException(422, str(e)) from None
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from None


@routeur.get("/plan/{scenario}/export")
def exporter(scenario: str, format: str = "csv"):
    try:
        p = tr.lire_plan(scenario)
    except tr.ScenarioInvalide as e:
        raise HTTPException(422, str(e)) from None
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from None
    nom = f"plan_{scenario}".replace("~", "-")
    if format == "xlsx":
        return Response(tr.export_xlsx(p), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{nom}.xlsx"'})
    if format == "csv":
        return Response(tr.export_csv(p), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{nom}.csv"'})
    raise HTTPException(422, "format doit valoir csv ou xlsx")


class DemandeRetour(BaseModel):
    scenario: str


@routeur.post("/retour")
def retour(d: DemandeRetour):
    """Bonus §5 : crée une instance du module 1 aux coûts de transport corrigés par les tournées."""
    try:
        p = tr.lire_plan(d.scenario)
        ident, _ = tr.instance_corrigee(p)
    except tr.ScenarioInvalide as e:
        raise HTTPException(422, str(e)) from None
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from None
    facteurs = {l["entrepot"]: l["ratio_retour"] for l in p["tournees"]}
    return {"instance": ident, "facteurs": facteurs}
