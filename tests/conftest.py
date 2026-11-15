# -*- coding: utf-8 -*-
"""Les tests ecrivent leurs fichiers d'echange, plans, cache et instances corrigees dans un
dossier temporaire : le dossier sorties/ du projet n'est jamais modifie par pytest."""
import shutil
import tempfile
from pathlib import Path

import backend.app as app_module
import backend.tournees as tournees

_TMP = Path(tempfile.mkdtemp(prefix="aps_sorties_"))
app_module.DOSSIER_SORTIES = _TMP
tournees.DOSSIER_SORTIES = _TMP
tournees.DOSSIER_CACHE = _TMP / "cache_tournees"
tournees.DOSSIER_PLANS = _TMP / "plans"
tournees.DOSSIER_CORRIGEES = _TMP / "instances_corrigees"
tournees.vider_cache_memoire()


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP, ignore_errors=True)
