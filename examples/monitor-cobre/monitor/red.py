"""Cliente HTTP compartido con timeout, User-Agent y reintentos ante errores temporales."""
import time

import requests

TIMEOUT = 20
HEADERS = {"User-Agent": "monitor-cobre/1.0 (+uso interno)"}
TEMPORALES = {429, 500, 502, 503, 504}


def get(url, params=None, headers=None, intentos=3, espera=1.5):
    """GET que reintenta (1,5 s, 3 s) si el servidor responde un error temporal o se corta la conexión."""
    for i in range(intentos):
        try:
            resp = requests.get(url, params=params, headers=headers or HEADERS, timeout=TIMEOUT)
            if resp.status_code in TEMPORALES and i < intentos - 1:
                time.sleep(espera * (i + 1))
                continue
            resp.raise_for_status()
            return resp
        except (requests.ConnectionError, requests.Timeout):
            if i == intentos - 1:
                raise
            time.sleep(espera * (i + 1))
