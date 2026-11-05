"""Noticias de riesgo de suministro: Google News RSS + GDELT, con puntaje por palabras clave."""
import hashlib
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from . import red

GOOGLE_RSS = "https://news.google.com/rss/search"
GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"

# Peso por término (texto sin tildes, en minúsculas).
EVENTOS = {
    "huelga": 4, "strike": 4, "paro": 3, "bloqueo": 4, "blockade": 4, "bloquean": 4,
    "fuerza mayor": 5, "force majeure": 5, "suspende operaciones": 5, "suspend": 3,
    "estado de emergencia": 4, "cierre": 2, "toma de": 3, "protesta": 2, "protest": 2,
    "conflicto": 2, "derrame": 2, "accidente": 2, "arancel": 2, "tariff": 2,
    "impuesto": 1, "regalias": 1, "sanciones": 2, "inventarios": 1, "deficit": 2,
    "escasez": 3, "shortage": 3, "disruption": 3, "interrupcion": 3, "outage": 3, "landslide": 3,
    "deslizamiento": 3, "huaico": 3, "export ban": 4, "prohibe": 2, "aranceles": 2, "tariffs": 2,
}
ACTIVOS = {
    "las bambas": 3, "antamina": 3, "cerro verde": 3, "quellaveco": 3, "toquepala": 2,
    "cuajone": 2, "antapaccay": 2, "constancia": 2, "tia maria": 2, "corredor minero": 3,
    "callao": 2, "matarani": 2, "southern copper": 2, "codelco": 2, "escondida": 2,
    "grasberg": 2, "kamoa": 2, "cobre panama": 2, "glencore": 1, "freeport": 1,
}
TEMA = ("cobre", "copper", "miner", "minas?")


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in texto if not unicodedata.combining(c)).lower()


def _hay(termino, texto):
    """Coincidencia al inicio de palabra (evita que 'paro' coincida con 'comparo')."""
    return re.search(r"\b" + termino, texto) is not None


def puntaje(titulo):
    """Puntaje de riesgo 0-10. Cero si no trata de cobre/minería; 1 si trata del tema sin señales de riesgo."""
    t = normalizar(titulo)
    activos = [k for k in ACTIVOS if _hay(re.escape(k), t)]
    if not activos and not any(_hay(k, t) for k in TEMA):
        return 0, []
    eventos = [k for k in EVENTOS if _hay(re.escape(k), t)]
    total = sum(EVENTOS[k] for k in eventos) + sum(ACTIVOS[k] for k in activos)
    return max(1, min(total, 10)), eventos + activos


def _id(url, titulo):
    return hashlib.sha1((url or normalizar(titulo)).encode()).hexdigest()[:16]


def parse_rss(xml_text):
    items = []
    root = ET.fromstring(xml_text)
    for item in root.iter("item"):
        titulo = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        fuente = (item.findtext("source") or "").strip()
        try:
            fecha = parsedate_to_datetime(item.findtext("pubDate"))
        except (TypeError, ValueError):
            fecha = None
        items.append({"titulo": titulo, "url": url, "fuente": fuente, "fecha": fecha, "origen": "Google News"})
    return items


def parse_gdelt(payload):
    items = []
    for a in (payload or {}).get("articles", []):
        try:
            fecha = datetime.strptime(a.get("seendate", ""), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            fecha = None
        items.append({"titulo": a.get("title", ""), "url": a.get("url", ""),
                      "fuente": a.get("domain", ""), "fecha": fecha, "origen": "GDELT"})
    return items


IDIOMAS = {"es": {"hl": "es-419", "gl": "PE", "ceid": "PE:es-419"},
           "en": {"hl": "en-US", "gl": "US", "ceid": "US:en"}}


def _buscar_google(q, idioma="es", dias=3):
    params = {"q": f"{q} when:{dias}d", **IDIOMAS[idioma]}
    return parse_rss(red.get(GOOGLE_RSS, params=params).text)


def _buscar_gdelt(q):
    params = {"query": q, "mode": "artlist", "format": "json", "maxrecords": 50, "timespan": "2d", "sort": "datedesc"}
    return parse_gdelt(red.get(GDELT, params=params).json())


def filtrar(items, max_horas, ahora=None):
    """Deduplica, descarta noticias viejas, calcula puntaje y ordena por riesgo."""
    ahora = ahora or datetime.now(timezone.utc)
    limite = ahora - timedelta(hours=max_horas)
    vistos, out = set(), []
    for it in items:
        nid = _id(it["url"], it["titulo"])
        clave_titulo = normalizar(it["titulo"])[:80]
        if nid in vistos or clave_titulo in vistos:
            continue
        vistos.update({nid, clave_titulo})
        if it["fecha"] and it["fecha"] < limite:
            continue
        p, terminos = puntaje(it["titulo"])
        if p == 0:
            continue
        out.append({**it, "id": nid, "riesgo": p, "terminos": terminos})
    out.sort(key=lambda x: x["riesgo"], reverse=True)
    return out


def obtener(config, errores):
    items = []
    dias = max(1, round(config.get("max_horas", 72) / 24))
    busquedas = [(q, "es") for q in config.get("google_news", [])] + [(q, "en") for q in config.get("google_news_en", [])]
    for q, idioma in busquedas:
        try:
            items += _buscar_google(q, idioma, dias)
        except Exception as e:  # una búsqueda caída no detiene el resto
            errores.append(f"Google News '{q}': {e}")
    for q in config.get("gdelt", []):
        try:
            items += _buscar_gdelt(q)
        except ValueError:
            errores.append("GDELT: respuesta no válida (suele ser límite de consultas; se reintenta en la próxima)")
        except Exception as e:
            errores.append(f"GDELT: {e}")
    return filtrar(items, config.get("max_horas", 72))
