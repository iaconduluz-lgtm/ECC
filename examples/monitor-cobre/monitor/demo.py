"""Datos de demostración para ver el tablero sin conexión. No son datos reales."""
import math
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest import mock

NOTICIAS_DEMO = [
    "Comunidades bloquean corredor minero sur y Las Bambas suspende envíos de cobre",
    "Sindicato de Cerro Verde anuncia huelga indefinida desde el lunes",
    "Paro portuario en el Callao retrasa embarques de minerales",
    "Perú evalúa nuevo impuesto a las exportaciones mineras",
    "Precio del cobre sube por menores inventarios en bolsas",
    "Antamina reporta producción récord de cobre en el trimestre",
]


def _trm(dias=1825):
    hoy = datetime.now(timezone.utc).date()
    return [{"valor": f"{4000 + 250 * math.sin(i / 90) + 60 * math.sin(i / 7) - i * 0.2:.2f}", "unidad": "COP",
             "vigenciadesde": (hoy - timedelta(days=i)).isoformat() + "T00:00:00.000"} for i in range(dias)]


def _cobre(dias=1260):
    base = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    tiempos = [int((base - timedelta(days=dias - 1 - i)).timestamp()) for i in range(dias)]
    cierres = [3.8 + 1.0 * (i / dias) + 0.35 * math.sin(i / 60) + 0.06 * math.sin(i / 3) for i in range(dias)]
    return {"chart": {"result": [{"meta": {"regularMarketPrice": cierres[-1]}, "timestamp": tiempos,
                                  "indicators": {"quote": [{"close": cierres}]}}]}}


def _rss():
    ahora = datetime.now(timezone.utc)
    items = "".join(
        f"<item><title>{t}</title><link>https://ejemplo.demo/{i}</link>"
        f"<pubDate>{format_datetime(ahora - timedelta(hours=2 * i))}</pubDate><source>Demo</source></item>"
        for i, t in enumerate(NOTICIAS_DEMO))
    return f"<rss><channel>{items}</channel></rss>"


def falso_get(url, params=None, headers=None):
    r = mock.Mock()
    if "datos.gov.co" in url:
        r.json.return_value = _trm()
    elif "yahoo" in url:
        r.json.return_value = _cobre()
    elif "news.google" in url:
        r.text = _rss()
    else:
        r.json.return_value = {"articles": []}
    return r


def activar():
    """Context manager que reemplaza las llamadas de red por datos de demostración."""
    return mock.patch("monitor.red.get", side_effect=falso_get)
