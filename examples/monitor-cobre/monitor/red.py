"""Cliente HTTP compartido con timeout y User-Agent."""
import requests

TIMEOUT = 20
HEADERS = {"User-Agent": "monitor-cobre/1.0 (+uso interno)"}


def get(url, params=None, headers=None):
    resp = requests.get(url, params=params, headers=headers or HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp
