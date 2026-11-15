# -*- coding: utf-8 -*-
"""File de calcul partagee par les deux modules : un seul calcul a la fois sur le serveur,
pour que les temps de reponse mesures ne soient pas faussés par un calcul voisin."""
import threading
from concurrent.futures import ThreadPoolExecutor

EXECUTEUR = ThreadPoolExecutor(max_workers=1)
VERROU = threading.Lock()
