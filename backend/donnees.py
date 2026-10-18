# -*- coding: utf-8 -*-
"""Chargement et validation des instances « Tunisie » (instance.json + matrices.npz)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_INSTANCES = RACINE / "donnees_tunisie" / "instances"
KPAL = 0.12324  # TND par palette et par km (aller-retour : 2 * KPAL), cf. maquette
CLES_REQUISES = ("meta", "entrepots", "magasins", "cout_affectation")
MESSAGE_FORMAT = "Ce fichier n'a pas le format instance.json attendu."
EXEMPLES = {"S": "Petit · 3 × 20", "M": "Moyen · 5 × 50", "L": "Grand · 10 × 200"}


class FormatInvalide(ValueError):
    def __init__(self):
        super().__init__(MESSAGE_FORMAT)


@dataclass
class DonneesInstance:
    brut: dict
    C: np.ndarray      # (n, m) cout d'affectation magasin i -> entrepot j, TND / semaine
    dist: np.ndarray   # (n, m) distance en km
    d: np.ndarray      # (n,) demande en palettes / semaine
    s: np.ndarray      # (m,) capacite
    f: np.ndarray      # (m,) cout fixe hebdomadaire

    @property
    def id(self) -> str:
        return self.brut["meta"]["id"]

    @property
    def magasins(self) -> list:
        return self.brut["magasins"]

    @property
    def entrepots(self) -> list:
        return self.brut["entrepots"]

    @property
    def n(self) -> int:
        return len(self.magasins)

    @property
    def m(self) -> int:
        return len(self.entrepots)

    def nom_court(self, j: int) -> str:
        return self.entrepots[j].get("nom", self.entrepots[j]["id"]).split(" (")[0].split(" – ")[0]

    def reference(self, modele: str) -> dict | None:
        prefixe = "GAP" if modele == "gap" else "SSCFLP"
        return next((r for r in self.brut.get("reference", []) if str(r.get("modele", "")).startswith(prefixe)), None)

    def indices(self, affectation: dict) -> np.ndarray:
        """{id_magasin: id_entrepot} -> tableau d'indices d'entrepot."""
        idx = {e["id"]: j for j, e in enumerate(self.entrepots)}
        try:
            return np.array([idx[affectation[s["id"]]] for s in self.magasins], dtype=int)
        except KeyError as e:
            raise ValueError(f"Affectation incomplete ou inconnue : {e.args[0]}") from None

    def ids(self, a: np.ndarray) -> dict:
        return {s["id"]: self.entrepots[int(a[i])]["id"] for i, s in enumerate(self.magasins)}


def charger(brut: dict, npz: Path | None = None) -> DonneesInstance:
    if not isinstance(brut, dict) or any(k not in brut for k in CLES_REQUISES):
        raise FormatInvalide()
    try:
        W, S = brut["entrepots"], brut["magasins"]
        C = np.asarray(brut["cout_affectation"], dtype=float)
        d = np.array([float(x["demande"]) for x in S])
        s = np.array([float(e["capacite"]) for e in W])
        f = np.array([float(e.get("cout_fixe_semaine", 0.0)) for e in W])
        if C.shape != (len(S), len(W)) or not brut["meta"].get("id"):
            raise FormatInvalide()
    except (KeyError, TypeError, ValueError):
        raise FormatInvalide() from None
    dist = None
    if npz is not None and npz.exists():
        with np.load(npz) as z:
            if "distance_km" in z and z["distance_km"].shape == C.shape:
                dist = np.asarray(z["distance_km"], dtype=float)
    if dist is None:  # meme reconstruction que la maquette : c = d (2 KPAL dist + manutention)
        manut = np.array([float(e.get("cout_manutention_palette", 0.0)) for e in W])
        kpal = float(brut["meta"].get("kpal", KPAL))
        dist = np.maximum(0.0, (C / d[:, None] - manut[None, :]) / (2 * kpal))
    return DonneesInstance(brut, C, dist, d, s, f)


def chemin_exemple(taille: str) -> Path | None:
    dossier = DOSSIER_INSTANCES / taille
    if not dossier.is_dir():
        return None
    cands = sorted(p for p in dossier.iterdir() if (p / "instance.json").exists())
    return cands[0] / "instance.json" if cands else None


def charger_fichier(chemin: Path) -> DonneesInstance:
    with open(chemin, encoding="utf-8") as fh:
        brut = json.load(fh)
    return charger(brut, chemin.parent / "matrices.npz")


def trouver_npz(id_instance: str) -> Path | None:
    """Un instance.json depose dont l'id correspond a une instance du jeu : on reprend ses distances."""
    for p in DOSSIER_INSTANCES.glob(f"*/{id_instance}/matrices.npz"):
        return p
    return None


def liste_exemples() -> list:
    out = []
    for t, libelle in EXEMPLES.items():
        p = chemin_exemple(t)
        if p:
            out.append({"taille": t, "libelle": libelle, "id": p.parent.name})
    return out
