# -*- coding: utf-8 -*-
"""Classeur Excel d'echange entre les deux modules (cahier des charges §5).

Le module 1 ecrit le fichier d'echange JSON (sorties/affectation_validee_<scenario>.json). Ce module
en fait un classeur .xlsx lisible par n'importe qui :
  Lisez-moi · Affectation · Entrepôts · Coûts · Distances · Scénario
La colonne « entrepot » de la feuille Affectation est modifiable (liste deroulante). Les charges,
taux d'utilisation et couts se recalculent dans Excel par formules. Le classeur, modifie ou non,
peut etre recharge dans le module 2 : il est relu, controle (capacites), et s'il differe du
scenario d'origine, il devient un scenario derive (seuls les entrepots touches seront recalcules,
grace au cache par signature du module 2)."""
from __future__ import annotations

import io
import json
from datetime import datetime

from . import tournees as tr

F_LISEZ, F_AFF, F_ENT, F_COUT, F_DIST, F_SCN = "Lisez-moi", "Affectation", "Entrepôts", "Coûts", "Distances", "Scénario"
COLS_AFF = ["id_pdv", "ville", "latitude", "longitude", "demande", "entrepot", "distance_km", "cout_affectation"]
COLS_ENT = ["id", "nom", "latitude", "longitude", "capacite", "charge", "taux_utilisation", "nb_magasins", "cout_fixe"]
CLES_SCN = ["scenario", "instance", "modele", "methode", "date", "parent", "unite_cout", "unite_demande", "kpal",
            "cout_affectation", "cout_fixe", "cout_total"]
NOIR, JAUNE, BLANC, ROUGE_PALE = "121417", "F6C000", "FFFFFF", "F8D7D4"


class ClasseurInvalide(tr.ScenarioInvalide):
    pass


def nom_fichier(scenario: str) -> str:
    return f"sijar_{scenario}.xlsx".replace("~", "-")


# ----------------------------------------------------------------------------- valeurs calculées
def _couts(sc):
    """Coût d'affectation, coût fixe et total d'un scénario, à partir de ses c_ij."""
    ch = tr.charges(sc)
    ca = sum(float(s.get("cout_affectation", 0.0)) for s in sc["magasins"])
    cf = (sum(float(e.get("cout_fixe", 0.0)) for e in sc["entrepots"] if ch[e["id"]] > 0)
          if sc.get("modele") == "sscflp" else 0.0)
    return round(ca, 2), round(cf, 2), round(ca + cf, 2)


def feuilles(sc: dict) -> dict:
    """Contenu du classeur en valeurs (pour l'aperçu dans l'outil) : {feuille: [lignes]}."""
    ch = tr.charges(sc)
    nb = {e["id"]: 0 for e in sc["entrepots"]}
    for s in sc["magasins"]:
        nb[s["entrepot"]] += 1
    ids_e = [e["id"] for e in sc["entrepots"]]
    ca, cf, ct = _couts(sc)
    lisez = [
        ["Classeur d'échange Sijar"],
        ["Scénario", sc["scenario"]],
        ["Ce classeur contient l'affectation retenue au module 1 (distribution)."],
        ["Feuille Affectation", "un magasin par ligne ; la colonne « entrepot » (en jaune) est modifiable"],
        ["Feuille Entrepôts", "capacité, charge et taux d'utilisation, recalculés automatiquement"],
        ["Feuilles Coûts et Distances", f"coût c_ij ({sc.get('unite_cout', 'TND / semaine')}) et distance (km) de chaque magasin vers chaque entrepôt"],
        ["Feuille Scénario", "identifiant, origine et coût total ; ne pas modifier l'identifiant"],
        ["Pour modifier", "changer « entrepot », vérifier qu'aucun taux ne dépasse 100 %, enregistrer, puis importer le classeur dans le module 2"],
        ["Recalcul", "le module 2 ne recalcule que les tournées des entrepôts dont les magasins ont changé"],
    ]
    aff = [COLS_AFF] + [[s["id"], s.get("ville", ""), float(s["lat"]), float(s["lon"]), float(s["demande"]), s["entrepot"],
                         s.get("distance_km"), s.get("cout_affectation")] for s in sc["magasins"]]
    ent = [COLS_ENT] + [[e["id"], e.get("nom", e["id"]), float(e["lat"]), float(e["lon"]), float(e["capacite"]),
                         ch[e["id"]], round(ch[e["id"]] / float(e["capacite"]), 4) if float(e["capacite"]) else None,
                         nb[e["id"]], float(e.get("cout_fixe", 0.0))] for e in sc["entrepots"]]
    cout = [["id_pdv"] + ids_e] + [[s["id"]] + [s.get("couts", {}).get(j) for j in ids_e] for s in sc["magasins"]]
    dist = [["id_pdv"] + ids_e] + [[s["id"]] + [s.get("distances_km", {}).get(j) for j in ids_e] for s in sc["magasins"]]
    vals = dict(sc, cout_affectation=ca, cout_fixe=cf, cout_total=ct)
    scn = [["cle", "valeur"]] + [[k, vals.get(k)] for k in CLES_SCN]
    return {F_LISEZ: lisez, F_AFF: aff, F_ENT: ent, F_COUT: cout, F_DIST: dist, F_SCN: scn}


# ----------------------------------------------------------------------------- écriture .xlsx
def export_classeur(sc: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    fl = feuilles(sc)
    n, m = len(sc["magasins"]), len(sc["entrepots"])
    entete = Font(bold=True, color=BLANC)
    fond_noir = PatternFill("solid", fgColor=NOIR)
    fond_jaune = PatternFill("solid", fgColor=JAUNE)
    wb = Workbook()

    def feuille(nom, lignes, premiere=False):
        ws = wb.active if premiere else wb.create_sheet(nom)
        ws.title = nom
        for l in lignes:
            ws.append(l)
        return ws

    def styler_entete(ws, ncol):
        for c in ws[1][:ncol]:
            c.font, c.fill = entete, fond_noir
        ws.freeze_panes = "B2"

    def largeurs(ws, mini=10, maxi=48):
        for col in ws.columns:
            lg = max(len(str(c.value)) if c.value is not None and not str(c.value).startswith("=") else 8 for c in col)
            ws.column_dimensions[col[0].column_letter].width = max(mini, min(maxi, lg + 2))

    ws0 = feuille(F_LISEZ, fl[F_LISEZ], premiere=True)
    ws0["A1"].font = Font(bold=True, size=16)
    for r in range(4, ws0.max_row + 1):
        ws0.cell(r, 1).font = Font(bold=True)
        ws0.cell(r, 2).alignment = Alignment(wrap_text=True, vertical="top")
    ws0.column_dimensions["A"].width, ws0.column_dimensions["B"].width = 28, 90

    # Coûts et Distances d'abord (référencées par les formules)
    ws_aff = feuille(F_AFF, fl[F_AFF])
    ws_ent = feuille(F_ENT, fl[F_ENT])
    ws_c = feuille(F_COUT, fl[F_COUT])
    ws_d = feuille(F_DIST, fl[F_DIST])
    ws_s = feuille(F_SCN, fl[F_SCN])
    for ws, k in ((ws_aff, len(COLS_AFF)), (ws_ent, len(COLS_ENT)), (ws_c, m + 1), (ws_d, m + 1), (ws_s, 2)):
        styler_entete(ws, k)
    ws_aff["F1"].fill, ws_aff["F1"].font = fond_jaune, Font(bold=True, color=NOIR)

    derniere_col = get_column_letter(m + 1)
    plage_c = f"'{F_COUT}'!$B$2:${derniere_col}${n + 1}"
    plage_d = f"'{F_DIST}'!$B$2:${derniere_col}${n + 1}"
    for r in range(2, n + 2):
        ws_aff.cell(r, 6).fill = fond_jaune
        lig = f"MATCH($A{r},'{F_COUT}'!$A$2:$A${n + 1},0)"
        col = f"MATCH($F{r},'{F_COUT}'!$B$1:${derniere_col}$1,0)"
        ws_aff.cell(r, 7, f"=INDEX({plage_d},MATCH($A{r},'{F_DIST}'!$A$2:$A${n + 1},0),MATCH($F{r},'{F_DIST}'!$B$1:${derniere_col}$1,0))")
        ws_aff.cell(r, 8, f"=INDEX({plage_c},{lig},{col})")
        ws_aff.cell(r, 7).number_format = "0.0"
        ws_aff.cell(r, 8).number_format = "#,##0.00"
    dv = DataValidation(type="list", formula1='"' + ",".join(e["id"] for e in sc["entrepots"]) + '"', allow_blank=False,
                        showErrorMessage=True, errorTitle="Entrepôt inconnu",
                        error="Choisissez un identifiant d'entrepôt de la feuille Entrepôts.")
    ws_aff.add_data_validation(dv)
    dv.add(f"F2:F{n + 1}")

    for r in range(2, m + 2):
        ws_ent.cell(r, 6, f"=SUMIF('{F_AFF}'!$F$2:$F${n + 1},$A{r},'{F_AFF}'!$E$2:$E${n + 1})")
        ws_ent.cell(r, 7, f"=IF($E{r}>0,$F{r}/$E{r},0)")
        ws_ent.cell(r, 7).number_format = "0.0%"
        ws_ent.cell(r, 8, f"=COUNTIF('{F_AFF}'!$F$2:$F${n + 1},$A{r})")
    ws_ent.conditional_formatting.add(f"G2:G{m + 1}", CellIsRule(operator="greaterThan", formula=["1"],
                                                                 fill=PatternFill("solid", fgColor=ROUGE_PALE),
                                                                 font=Font(bold=True, color="B3261E")))
    # Scénario : coûts recalculés par formules
    lignes_scn = {ws_s.cell(r, 1).value: r for r in range(2, ws_s.max_row + 1)}
    ws_s.cell(lignes_scn["cout_affectation"], 2, f"=SUM('{F_AFF}'!$H$2:$H${n + 1})")
    if sc.get("modele") == "sscflp":
        ws_s.cell(lignes_scn["cout_fixe"], 2, f"=SUMPRODUCT(('{F_ENT}'!$F$2:$F${m + 1}>0)*'{F_ENT}'!$I$2:$I${m + 1})")
    ws_s.cell(lignes_scn["cout_total"], 2, f"=B{lignes_scn['cout_affectation']}+B{lignes_scn['cout_fixe']}")
    for k in ("cout_affectation", "cout_fixe", "cout_total"):
        ws_s.cell(lignes_scn[k], 2).number_format = "#,##0.00"
    for ws in (ws_aff, ws_ent, ws_c, ws_d, ws_s):
        largeurs(ws)
    ws_s.column_dimensions["B"].width = 44
    wb.active = 1
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ----------------------------------------------------------------------------- lecture .xlsx
def _lignes(ws):
    lignes = [list(r) for r in ws.iter_rows(values_only=True)]
    return [l for l in lignes if any(v not in (None, "") for v in l)]


def _table(ws, requis):
    lignes = _lignes(ws)
    if not lignes:
        raise ClasseurInvalide(f"La feuille {ws.title} est vide.")
    tete = [str(v).strip() if v is not None else "" for v in lignes[0]]
    manque = [c for c in requis if c not in tete]
    if manque:
        raise ClasseurInvalide(f"Feuille {ws.title} : colonnes manquantes ({', '.join(manque)}).")
    return [{tete[k]: v for k, v in enumerate(l) if k < len(tete) and tete[k]} for l in lignes[1:]]


def _matrice(ws):
    lignes = _lignes(ws)
    ids = [str(v) for v in lignes[0][1:] if v not in (None, "")]
    return {str(l[0]): {ids[k]: (float(v) if v not in (None, "") else None) for k, v in enumerate(l[1:len(ids) + 1])}
            for l in lignes[1:] if l[0] not in (None, "")}


def lire_classeur(contenu: bytes) -> dict:
    """Classeur .xlsx -> scénario au format du fichier d'échange (non encore enregistré)."""
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(contenu), data_only=False)
    except Exception:
        raise ClasseurInvalide("Ce fichier n'est pas un classeur Excel lisible (.xlsx).") from None
    for f in (F_AFF, F_ENT, F_COUT, F_SCN):
        if f not in wb.sheetnames:
            raise ClasseurInvalide(f"Feuille « {f} » absente : ce classeur ne vient pas du module 1.")
    meta = {str(l[0]).strip(): l[1] for l in _lignes(wb[F_SCN])[1:] if l and l[0]}
    if not meta.get("scenario"):
        raise ClasseurInvalide("Identifiant de scénario absent de la feuille Scénario.")
    couts = _matrice(wb[F_COUT])
    dists = _matrice(wb[F_DIST]) if F_DIST in wb.sheetnames else {}
    try:
        ents = [{"id": str(e["id"]).strip(), "nom": str(e.get("nom") or e["id"]), "lat": float(e["latitude"]),
                 "lon": float(e["longitude"]), "capacite": float(e["capacite"]), "cout_fixe": float(e.get("cout_fixe") or 0.0)}
                for e in _table(wb[F_ENT], ["id", "latitude", "longitude", "capacite"]) if e.get("id")]
    except (TypeError, ValueError):
        raise ClasseurInvalide("Feuille Entrepôts : coordonnées ou capacité non numériques.") from None
    ids_e = {e["id"] for e in ents}
    mags = []
    for k, s in enumerate(_table(wb[F_AFF], ["id_pdv", "latitude", "longitude", "demande", "entrepot"]), start=2):
        if not s.get("id_pdv"):
            continue
        sid, ent = str(s["id_pdv"]).strip(), str(s.get("entrepot") or "").strip()
        if ent not in ids_e:
            raise ClasseurInvalide(f"Affectation, ligne {k} ({sid}) : entrepôt « {ent} » inconnu.")
        try:
            lat, lon, dem = float(s["latitude"]), float(s["longitude"]), float(s["demande"])
        except (TypeError, ValueError):
            raise ClasseurInvalide(f"Affectation, ligne {k} ({sid}) : valeur non numérique.") from None
        c, d = couts.get(sid, {}), dists.get(sid, {})
        mag = {"id": sid, "ville": str(s.get("ville") or ""), "lat": lat, "lon": lon, "demande": dem, "entrepot": ent}
        if c.get(ent) is not None:
            mag["cout_affectation"] = c[ent]
            mag["couts"] = {j: v for j, v in c.items() if v is not None}
        if d.get(ent) is not None:
            mag["distance_km"] = d[ent]
            mag["distances_km"] = {j: v for j, v in d.items() if v is not None}
        mags.append(mag)
    if len({s["id"] for s in mags}) != len(mags):
        raise ClasseurInvalide("Feuille Affectation : un identifiant de magasin apparaît deux fois.")
    sc = {"scenario": str(meta["scenario"]).strip(), "instance": str(meta.get("instance") or ""),
          "modele": str(meta.get("modele") or "gap"), "methode": str(meta.get("methode") or ""),
          "date": str(meta.get("date") or ""), "parent": meta.get("parent") or None, "ajustements": [],
          "unite_cout": str(meta.get("unite_cout") or "TND / semaine"),
          "unite_demande": str(meta.get("unite_demande") or "palettes / semaine"),
          "kpal": float(meta.get("kpal") or 0.12324), "entrepots": ents, "magasins": mags}
    tr.valider_scenario(sc)
    ch = tr.charges(sc)
    trop = [f"{e['id']} ({ch[e['id']]:.0f} > {e['capacite']:.0f})" for e in ents if ch[e["id"]] > e["capacite"] + 1e-9]
    if trop:
        raise ClasseurInvalide("Capacité dépassée : " + ", ".join(trop) + ". Corrigez la colonne entrepot puis réimportez.")
    for e in ents:
        e["ouvert"] = ch[e["id"]] > 0 or sc["modele"] == "gap"
    sc["cout_affectation"], sc["cout_fixe"], sc["cout_total"] = _couts(sc)
    return sc


def importer(contenu: bytes) -> tuple[dict, dict]:
    """Lit un classeur et l'enregistre. Renvoie (scénario retenu, différences).
    Classeur identique au scénario d'origine : on garde l'original. Classeur modifié : nouveau
    scénario dérivé « <base>~x<k> », avec la liste des magasins déplacés."""
    sc = lire_classeur(contenu)
    try:
        orig = tr.lire_scenario(sc["scenario"])
    except FileNotFoundError:
        orig = None
    if orig is None:
        tr.chemin_scenario(sc["scenario"])
        tr.ecrire_scenario(sc)
        return sc, {"nouveau": True, "deplaces": [], "entrepots_touches": [], "origine": None}
    avant = {s["id"]: s["entrepot"] for s in orig["magasins"]}
    if set(avant) != {s["id"] for s in sc["magasins"]}:
        raise ClasseurInvalide("La liste des magasins ne correspond pas au scénario d'origine.")
    deplaces = [{"magasin": s["id"], "de": avant[s["id"]], "vers": s["entrepot"]}
                for s in sc["magasins"] if avant[s["id"]] != s["entrepot"]]
    if not deplaces:
        return orig, {"nouveau": False, "deplaces": [], "entrepots_touches": [], "origine": orig["scenario"]}
    base = orig["scenario"].split("~")[0]
    k = 1
    while tr.chemin_scenario(f"{base}~x{k}").exists():
        k += 1
    sc["scenario"] = f"{base}~x{k}"
    sc["parent"] = orig["scenario"]
    sc["methode"] = orig.get("methode", sc["methode"])
    sc["ajustements"] = list(orig.get("ajustements", [])) + [dict(d, module="classeur") for d in deplaces]
    sc["date"] = datetime.now().isoformat(timespec="seconds")
    tr.ecrire_scenario(sc)
    touches = sorted({d["de"] for d in deplaces} | {d["vers"] for d in deplaces})
    return sc, {"nouveau": True, "deplaces": deplaces, "entrepots_touches": touches, "origine": orig["scenario"]}


def importer_json(contenu: bytes) -> tuple[dict, dict]:
    try:
        sc = tr.valider_scenario(json.loads(contenu))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ClasseurInvalide("Ce fichier n'a pas le format du fichier d'échange du module 1.") from None
    tr.chemin_scenario(sc["scenario"])
    tr.ecrire_scenario(sc)
    return sc, {"nouveau": True, "deplaces": [], "entrepots_touches": [], "origine": None}
