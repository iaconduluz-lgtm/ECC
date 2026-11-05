"""Precio del cobre.

Fuente por defecto: futuro COMEX HG=F (USD por libra) desde el endpoint público de
Yahoo Finance, con ~15 min de retraso. Es una aproximación a la LME (se mueven casi igual).
Si se configura `precio_manual_usd_t` (p. ej. el cierre LME que te da tu broker), se usa ese.
"""
from datetime import datetime, timezone

from . import red

LB_POR_TONELADA = 2204.62
URL = "https://query1.finance.yahoo.com/v8/finance/chart/HG=F"


def parse(payload):
    """Devuelve (precio_actual_usd_t, [(fecha, cierre_usd_t)] de más reciente a más antigua)."""
    result = payload["chart"]["result"][0]
    tiempos = result.get("timestamp") or []
    cierres = result["indicators"]["quote"][0].get("close") or []
    serie = []
    for ts, c in zip(tiempos, cierres):
        if c is None:
            continue
        fecha = datetime.fromtimestamp(ts, tz=timezone.utc).date()
        serie.append((fecha, round(c * LB_POR_TONELADA, 2)))
    serie.sort(key=lambda x: x[0], reverse=True)
    actual = result.get("meta", {}).get("regularMarketPrice")
    actual_t = round(actual * LB_POR_TONELADA, 2) if actual else (serie[0][1] if serie else None)
    if actual_t is None:
        raise RuntimeError("Sin precio de cobre en la respuesta")
    return actual_t, serie


def obtener(config):
    manual = (config or {}).get("precio_manual_usd_t")
    if manual:
        return float(manual), [], "manual (LME/broker)"
    payload = red.get(URL, params={"interval": "1d", "range": "1mo"}).json()
    actual, serie = parse(payload)
    return actual, serie, "COMEX HG=F (aprox. LME, ~15 min retraso)"
