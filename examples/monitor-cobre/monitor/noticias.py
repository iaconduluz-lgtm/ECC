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
    "impuesto a las exportaciones": 3, "export tax": 3,
    "retrasa": 2, "retraso": 2, "delay": 2, "incendio": 4, "fire": 3, "explosion": 4, "paraliza": 3,
    "detiene": 3, "cierra la via": 3, "cierran la via": 3, "cierra el puerto": 4, "indefinid": 1,
    "bloquea": 4, "paro camionero": 1, "paro nacional": 3, "cierre de la via": 3, "cierre total": 3,
    "derrumbe": 3, "inundacion": 3, "congestion": 2, "represados": 3, "contenedores varados": 3,
    "se dispara": 4, "devaluacion": 4, "dolar sube": 3, "sube el dolar": 3, "reforma tributaria": 2,
    "sobretasa": 2, "contrabando": 1, "quiebra": 5, "bankruptcy": 5, "insolvencia": 5, "falta de": 2,
    # señales que bajan el riesgo (buenas noticias para el suministro)
    "record": -2, "reanuda": -3, "resume": -3, "acuerdo": -2, "levantan": -2, "levanta el": -2, "agreement": -2,
}
ACTIVOS = {
    "las bambas": 3, "antamina": 3, "cerro verde": 3, "quellaveco": 3, "toquepala": 2,
    "cuajone": 2, "antapaccay": 2, "constancia": 2, "tia maria": 2, "corredor minero": 3,
    "callao": 2, "matarani": 2, "southern copper": 2, "codelco": 2, "escondida": 2,
    "grasberg": 2, "kamoa": 2, "cobre panama": 2, "glencore": 1, "freeport": 1,
    # Colombia: puerto de llegada, vía a la planta y entidades que cambian tus costos
    "buenaventura": 3, "via al pacifico": 3, "via buenaventura": 3, "via cali": 2,
    "dian": 2, "banco de la republica": 2, "spbun": 2, "sociedad portuaria": 2,
}
# Lugares que solo cuentan si la noticia habla de un problema (evita "festival en Cali").
CONTEXTO = ("cali", "valle del cauca", "colombia")
TEMA = ("cobre", "copper", "miner", "minas?",
        # Colombia: dólar, comercio exterior y la ruta Buenaventura - Cali
        "dolar", "trm", "tasa de cambio", "peso colombiano", "importacion", "importador", "dian", "aduana",
        "puerto", "portuari", "camioner", "transportador", "carga")


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in texto if not unicodedata.combining(c)).lower()


def _hay(termino, texto):
    """Coincidencia al inicio de palabra (evita que 'paro' coincida con 'comparo')."""
    return re.search(r"\b" + termino, texto) is not None


NIVELES = [(8, "Peligro"), (6, "Alto"), (4, "Medio"), (1, "Bajo")]
ICONO = {"Peligro": "🔴", "Alto": "🟠", "Medio": "🟡", "Bajo": "🟢"}
POSITIVAS = ("record", "reanuda", "resume", "acuerdo", "levantan", "levanta el", "agreement", "normaliza", "restablece")
POSIBLE = ("amenaza", "amenazan", "anuncia", "anuncian", "podria", "posible", "evalua", "evaluan", "convocan",
           "plantea", "propone", "threaten", "could", "may ", "plans to", "warns")
HECHO = ("inicia", "inician", "en curso", "continua", "persiste", "cumple", "ongoing", "continues",
         "enters", "segundo dia", "tercer dia", "paraliza", "detiene", "suspende")


def nivel(riesgo):
    """1-3 Bajo, 4-5 Medio, 6-7 Alto, 8-10 Peligro (0 = no relevante)."""
    return next((n for minimo, n in NIVELES if riesgo >= minimo), "")


def evaluar(titulo, proveedor=()):
    """Clasifica un titular: riesgo 0-10, nivel, certeza, duración y si menciona a tu proveedor directo."""
    t = normalizar(titulo)
    del_proveedor = any(_hay(re.escape(normalizar(k)), t) for k in proveedor)
    activos = [k for k in ACTIVOS if _hay(re.escape(k), t)]
    eventos = [k for k in EVENTOS if _hay(re.escape(k), t)]
    en_contexto = any(_hay(k, t) for k in CONTEXTO) and any(EVENTOS[k] >= 3 for k in eventos)
    if not del_proveedor and not activos and not en_contexto and not any(_hay(k, t) for k in TEMA):
        return {"riesgo": 0, "nivel": "", "terminos": [], "afecta_proveedor": False, "certeza": "", "duracion_dias": None}
    total = sum(EVENTOS[k] for k in eventos) + sum(ACTIVOS[k] for k in activos)
    hay_problema = any(EVENTOS[k] > 0 for k in eventos)
    if del_proveedor and hay_problema:
        total += 4  # tu proveedor directo (casi único) pesa más que cualquier otra mina
    positiva = any(_hay(re.escape(k), t) for k in POSITIVAS)
    posible = any(_hay(re.escape(k), t) for k in POSIBLE)
    hecho = any(_hay(re.escape(k), t) for k in HECHO)
    m = re.search(r"(\d+)\s*(dias|days|semanas|weeks)", t)
    dias = (int(m.group(1)) * (7 if m.group(2) in ("semanas", "weeks") else 1)) if m else None
    if positiva:
        total = min(total, 3)  # p. ej. "levantan el bloqueo tras 15 días": buena noticia
    else:
        if hecho and hay_problema:
            total += 1
        if dias and hay_problema:
            total += 2 if dias >= 7 else 1
        if posible and not hecho:
            total = min(total, 5)  # una amenaza o propuesta todavía no es un hecho: máximo Medio
    riesgo = max(1, min(total, 10))
    if positiva:
        certeza = "Buena noticia"
    elif riesgo < 4:
        certeza = ""  # sin problema relevante
    else:
        certeza = "Posible" if posible and not hecho else "Hecho"
    return {"riesgo": riesgo, "nivel": nivel(riesgo), "terminos": eventos + activos, "afecta_proveedor": del_proveedor,
            "certeza": certeza, "duracion_dias": dias}


def puntaje(titulo, proveedor=()):
    """Atajo: (riesgo 0-10, términos encontrados)."""
    e = evaluar(titulo, proveedor)
    return e["riesgo"], e["terminos"]


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
           "co": {"hl": "es-419", "gl": "CO", "ceid": "CO:es-419"},
           "en": {"hl": "en-US", "gl": "US", "ceid": "US:en"}}


def _buscar_google(q, idioma="es", dias=3):
    params = {"q": f"{q} when:{dias}d", **IDIOMAS[idioma]}
    return parse_rss(red.get(GOOGLE_RSS, params=params).text)


def _buscar_gdelt(q):
    params = {"query": q, "mode": "artlist", "format": "json", "maxrecords": 50, "timespan": "2d", "sort": "datedesc"}
    return parse_gdelt(red.get(GDELT, params=params).json())


def filtrar(items, max_horas, ahora=None, proveedor=()):
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
        e = evaluar(it["titulo"], proveedor)
        if e["riesgo"] == 0:
            continue
        out.append({**it, "id": nid, **e})
    out.sort(key=lambda x: (x["afecta_proveedor"] and x["riesgo"] >= 4, x["riesgo"]), reverse=True)
    return out


def obtener(config, errores):
    items = []
    dias = max(1, round(config.get("max_horas", 72) / 24))
    busquedas = ([(q, "es") for q in config.get("google_news", [])]
                 + [(q, "co") for q in config.get("google_news_colombia", [])]
                 + [(q, "en") for q in config.get("google_news_en", [])])
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
    return filtrar(items, config.get("max_horas", 72), proveedor=config.get("proveedor_claves", []))
