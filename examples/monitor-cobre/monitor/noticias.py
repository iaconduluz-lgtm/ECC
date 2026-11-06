"""Noticias de riesgo de suministro: Google News RSS + GDELT, con puntaje por palabras clave."""
import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
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
    "sobretasa": 2, "contrabando": 1,
    # mundo (titulares en inglés): interrupciones, precios disparados, logística global
    "halt": 3, "halts": 3, "suspends": 4, "closure": 3, "flood": 3, "flooding": 3, "explosion": 4, "collapse": 3,
    "export restrictions": 4, "restricciones a la exportacion": 4, "sanctions": 2, "war": 2, "guerra": 2, "attack": 2,
    "record high": 3, "maximo historico": 3, "record historico": 3, "soars": 3, "surges": 3, "se dispara": 4,
    "sequia": 2, "drought": 2, "freight rates": 2, "fletes": 2, "tarifas de flete": 2, "quiebra": 5, "bankruptcy": 5, "insolvencia": 5, "falta de": 2,
    # señales que bajan el riesgo (buenas noticias para el suministro)
    "produccion record": -2, "record production": -2, "reanuda": -3, "resume": -3, "acuerdo": -2, "levantan": -2, "levanta el": -2, "agreement": -2,
}
ACTIVOS = {
    "las bambas": 3, "antamina": 3, "cerro verde": 3, "quellaveco": 3, "toquepala": 2,
    "cuajone": 2, "antapaccay": 2, "constancia": 2, "tia maria": 2, "corredor minero": 3,
    "callao": 2, "matarani": 2, "southern copper": 2, "codelco": 2, "escondida": 2,
    "grasberg": 2, "kamoa": 2, "cobre panama": 2, "glencore": 1, "freeport": 1,
    # Colombia: puerto de llegada, vía a la planta y entidades que cambian tus costos
    "buenaventura": 3, "via al pacifico": 3, "via buenaventura": 3, "via cali": 2,
    "dian": 2, "banco de la republica": 2, "spbun": 2, "sociedad portuaria": 2,
    # mundo: grandes productores y rutas marítimas
    "kamoto": 2, "tenke": 2, "zambia": 1, "congo": 1, "drc": 1, "chuquicamata": 2, "el teniente": 2,
    "collahuasi": 2, "los pelambres": 2, "oyu tolgoi": 2, "canal de panama": 3, "panama canal": 3,
    "mar rojo": 2, "red sea": 2, "suez": 2,
}
# Lugares que solo cuentan si la noticia habla de un problema (evita "festival en Cali").
CONTEXTO = ("cali", "valle del cauca", "colombia")
TEMA = ("cobre", "copper", "miner", "minas?",
        # Colombia: dólar, comercio exterior y la ruta Buenaventura - Cali
        "dolar", "trm", "tasa de cambio", "peso colombiano", "importacion", "importador", "dian", "aduana",
        "puerto", "portuari", "camioner", "transportador", "carga",
        # mundo: logística marítima y dólar global
        "shipping", "naviera", "freight", "flete", "smelter", "fundicion", "refineria", "refinery")


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in texto if not unicodedata.combining(c)).lower()


def _hay(termino, texto):
    """Coincidencia al inicio de palabra (evita que 'paro' coincida con 'comparo')."""
    return re.search(r"\b" + termino, texto) is not None


NIVELES = [(8, "Peligro"), (6, "Alto"), (4, "Medio"), (1, "Bajo")]
ICONO = {"Peligro": "🔴", "Alto": "🟠", "Medio": "🟡", "Bajo": "🟢"}
POSITIVAS = ("produccion record", "record production", "reabren", "reabre", "reapertura", "habilitan el paso",
             "habilitan la via", "restablecen", "se normaliza", "reopen", "reopens", "lifted", "rates to fall", "rates fall", "rates drop", "rates decline",
             "rates ease", "fletes bajan", "bajan los fletes", "caen los fletes", "reanuda", "resume", "acuerdo", "levantan", "levanta el", "agreement", "normaliza", "restablece")
POSIBLE = ("amenaza", "amenazan", "anuncia", "anuncian", "podria", "posible", "evalua", "evaluan", "convocan",
           "plantea", "propone", "threaten", "could", "may ", "plans to", "warns")
HECHO = ("inicia", "inician", "en curso", "continua", "persiste", "cumple", "ongoing", "continues",
         "enters", "segundo dia", "tercer dia", "paraliza", "detiene", "suspende")


PERU = ("peru", "lima", "callao", "matarani", "las bambas", "antamina", "cerro verde", "quellaveco", "toquepala",
        "cuajone", "antapaccay", "constancia", "tia maria", "corredor minero", "southern copper", "cusco", "apurimac",
        "arequipa", "moquegua", "ilo")
COLOMBIA = ("colombia", "buenaventura", "cali", "valle del cauca", "via al pacifico", "dian", "banco de la republica",
            "peso colombiano", "bogota", "cartagena", "barranquilla", "trm")


def region(titulo, del_proveedor=False):
    """Perú, Colombia o Mundo, según los lugares que menciona el titular."""
    t = normalizar(titulo)
    if del_proveedor or any(_hay(re.escape(k) + r"\b", t) for k in PERU):
        return "Perú"
    if any(_hay(re.escape(k) + r"\b", t) for k in COLOMBIA):
        return "Colombia"
    return "Mundo"


def nivel(riesgo):
    """1-3 Bajo, 4-5 Medio, 6-7 Alto, 8-10 Peligro (0 = no relevante)."""
    return next((n for minimo, n in NIVELES if riesgo >= minimo), "")


def evaluar(titulo, proveedor=(), resumen=""):
    """Clasifica un titular: riesgo 0-10, nivel, certeza, duración y si menciona a tu proveedor directo.

    El `resumen` (párrafo que trae la noticia) solo se usa para detectar buenas noticias ("levantan el bloqueo")
    y menciones a tu proveedor; los puntos de riesgo salen del título, para no sumar dos veces lo mismo.
    """
    t = normalizar(titulo)
    tr = normalizar(resumen)
    del_proveedor = any(_hay(re.escape(normalizar(k)), t) or _hay(re.escape(normalizar(k)), tr) for k in proveedor)
    activos = [k for k in ACTIVOS if _hay(re.escape(k), t)]
    eventos = [k for k in EVENTOS if _hay(re.escape(k), t)]
    en_contexto = any(_hay(k, t) for k in CONTEXTO) and any(EVENTOS[k] >= 3 for k in eventos)
    if not del_proveedor and not activos and not en_contexto and not any(_hay(k, t) for k in TEMA):
        return {"riesgo": 0, "nivel": "", "terminos": [], "afecta_proveedor": False, "certeza": "", "duracion_dias": None,
                "region": ""}
    total = sum(EVENTOS[k] for k in eventos) + sum(ACTIVOS[k] for k in activos)
    hay_problema = any(EVENTOS[k] > 0 for k in eventos)
    if del_proveedor and hay_problema:
        total += 4  # tu proveedor directo (casi único) pesa más que cualquier otra mina
    positiva = any(_hay(re.escape(k), t) or _hay(re.escape(k), tr) for k in POSITIVAS)
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
    reg = region(titulo, del_proveedor)
    if reg == "Mundo":
        total = min(total, 7)  # el resto del mundo mueve el precio, pero no corta tu suministro directo: máximo Alto
    riesgo = max(1, min(total, 10))
    if positiva:
        certeza = "Buena noticia"
    elif riesgo < 4:
        certeza = ""  # sin problema relevante
    else:
        certeza = "Posible" if posible and not hecho else "Hecho"
    return {"riesgo": riesgo, "nivel": nivel(riesgo), "terminos": eventos + activos, "afecta_proveedor": del_proveedor,
            "region": reg,
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
        if fuente and titulo.endswith(" - " + fuente):  # Google News añade " - Medio" al final del título
            titulo = titulo[: -len(" - " + fuente)].strip()
        descripcion = item.findtext("description") or ""
        # Google agrupa la misma noticia de varios medios: cada uno aparece como <font>Medio</font>.
        otros = [re.sub(r"<[^>]+>", "", m).strip() for m in re.findall(r"<font[^>]*>(.*?)</font>", descripcion, re.S)]
        resumen = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", descripcion)).strip()
        if resumen.startswith(titulo):
            resumen = resumen[len(titulo):].strip()
        try:
            fecha = parsedate_to_datetime(item.findtext("pubDate"))
        except (TypeError, ValueError):
            fecha = None
        items.append({"titulo": titulo, "url": url, "fuente": fuente, "fecha": fecha, "origen": "Google News",
                      "resumen": resumen[:400], "otros_medios": [o for o in otros if o and o != fuente]})
    return items


def parse_gdelt(payload):
    items = []
    for a in (payload or {}).get("articles", []):
        try:
            fecha = datetime.strptime(a.get("seendate", ""), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            fecha = None
        # Ojo: seendate es cuando GDELT VIO la noticia, no cuando se publicó (un artículo viejo
        # actualizado puede aparecer como nuevo). Por eso filtrar() revisa también la fecha del enlace.
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


FECHA_EN_URL = [re.compile(r"/(20\d{2})[/-](\d{1,2})[/-](\d{1,2})(?:/|-|$)"),
                re.compile(r"[/_-](20\d{2})(\d{2})(\d{2})(?:[/_.-]|$)")]
VACIAS = {"para", "por", "con", "los", "las", "del", "que", "una", "sus", "tras", "the", "and", "for", "from", "with",
          "como", "mas", "ante", "sobre", "entre", "este", "esta", "cobre", "copper"}


# ---- Fecha publicada en la propia página de la noticia ----
_CACHE_FECHAS = {}  # url -> datetime | None (una consulta por enlace mientras la app esté encendida)
PATRONES_FECHA_PAGINA = [
    r'<meta[^>]+(?:property|name|itemprop)=["\'](?:article:published_time|og:published_time|datePublished|'
    r'pubdate|publishdate|publish-date|date|dc\.date|DC\.date\.issued|parsely-pub-date|sailthru\.date)["\'][^>]*'
    r'content=["\']([^"\']+)["\']',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name|itemprop)=["\'](?:article:published_time|datePublished)["\']',
    r'"datePublished"\s*:\s*"([^"]+)"',
    r'<time[^>]+datetime=["\']([^"\']+)["\']',
]


def _leer_fecha(texto):
    texto = texto.strip()
    for intento in (texto, texto.replace("Z", "+00:00"), texto[:19], texto[:10]):
        try:
            d = datetime.fromisoformat(intento)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def fecha_en_pagina(html):
    """Fecha de publicación que el medio declara en la página (metadatos para buscadores)."""
    for patron in PATRONES_FECHA_PAGINA:
        for m in re.finditer(patron, html or "", re.I):
            d = _leer_fecha(m.group(1))
            if d and d.year >= 2000:
                return d
    return None


def verificar_fechas(items, minimo_riesgo=4, maximo=40, proveedor=()):
    """Abre la página de las noticias relevantes con enlace directo y anota `fecha_pagina` si el medio la declara.

    Los enlaces de Google News vienen cifrados y no se pueden abrir así; esos quedan con la fecha del buscador.
    """
    candidatos = []
    for it in items:
        url = it.get("url") or ""
        if not url.startswith("http") or "news.google.com" in url or fecha_en_url(url):
            continue
        if evaluar(it["titulo"], proveedor, it.get("resumen", ""))["riesgo"] < minimo_riesgo:
            continue
        candidatos.append(it)
    pendientes = list({it["url"] for it in candidatos if it["url"] not in _CACHE_FECHAS})[:maximo]

    def leer(url):
        try:
            return url, fecha_en_pagina(red.get(url, headers={"User-Agent": "Mozilla/5.0 (monitor-cobre)"}, intentos=1).text[:300000])
        except Exception:
            return url, None

    with ThreadPoolExecutor(max_workers=8) as ex:
        for url, fecha in ex.map(leer, pendientes):
            _CACHE_FECHAS[url] = fecha
    for it in candidatos:
        it["fecha_pagina"] = _CACHE_FECHAS.get(it["url"])
    return items


def fecha_en_url(url):
    """Fecha de publicación escrita en el enlace (p. ej. /2026/09/15/ o -20260915-), si la hay."""
    for patron in FECHA_EN_URL:
        m = patron.search(url or "")
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def _palabras(titulo):
    return {w for w in re.findall(r"[a-z0-9]+", normalizar(titulo)) if len(w) >= 4 and w not in VACIAS}


def palabras(titulo):
    return _palabras(titulo)


def misma_noticia(a, b, umbral=0.6):
    return _misma_noticia(a, b, umbral)


def _misma_noticia(a, b, umbral=0.6):
    """Dos titulares cuentan la misma noticia si comparten la mayoría de sus palabras importantes."""
    if not a or not b:
        return False
    return len(a & b) / min(len(a), len(b)) >= umbral


def filtrar(items, max_horas, ahora=None, proveedor=()):
    """Descarta noticias viejas o sin fecha, agrupa la misma noticia de distintos medios, puntúa y ordena.

    - Fecha: la del enlace si existe (la de GDELT es de cuando la vio, no de cuando se publicó); si no, la del feed.
      Sin fecha confiable, la noticia se descarta.
    - Confirmación: con una sola fuente el riesgo queda como máximo en Alto ("Sin confirmar");
      Peligro exige al menos 2 medios distintos.
    """
    ahora = ahora or datetime.now(timezone.utc)
    limite = ahora - timedelta(hours=max_horas)
    grupos = []  # cada grupo = la misma noticia en varios medios
    vistos = set()
    for it in items:
        nid = _id(it["url"], it["titulo"])
        if nid in vistos:
            continue
        vistos.add(nid)
        f_url = fecha_en_url(it["url"])
        f_pag = it.get("fecha_pagina")
        confiable = f_url or f_pag  # fecha declarada por el medio (enlace o página): manda sobre la del buscador
        fecha = confiable or it["fecha"]
        if fecha is None or fecha < limite:
            continue
        if fecha > ahora + timedelta(hours=6):  # fechas en el futuro: dato malo
            continue
        e = evaluar(it["titulo"], proveedor, it.get("resumen", ""))
        if e["riesgo"] == 0:
            continue
        nueva = {**it, "id": nid, **e, "fecha": fecha, "fecha_desde_url": bool(f_url),
                 "fecha_verificada": "en el enlace" if f_url else ("en la página" if f_pag else "según el buscador")}
        pal = _palabras(it["titulo"])
        buena = e["certeza"] == "Buena noticia"  # "levantan el bloqueo" no confirma "bloquean"
        grupo = next((g for g in grupos if g["buena"] == buena and _misma_noticia(pal, g["palabras"])), None)
        if grupo:
            grupo["miembros"].append(nueva)
            grupo["palabras"] |= pal
        else:
            grupos.append({"palabras": pal, "miembros": [nueva], "buena": buena})

    out = []
    for g in grupos:
        m = g["miembros"]
        principal = max(m, key=lambda x: x["riesgo"])
        fuentes = sorted(({(x.get("fuente") or x.get("origen") or "").strip() for x in m}
                          | {o.strip() for x in m for o in x.get("otros_medios", [])}) - {""})
        n = max(1, len(fuentes))
        item = {**principal, "fuentes": n, "lista_fuentes": fuentes,
                "fecha": min(x["fecha"] for x in m)}  # la primera publicación conocida
        if n < 2 and item["riesgo"] >= 8:
            item["riesgo"] = 7
            item["nivel"] = nivel(7)
        if n < 2 and item["riesgo"] >= 4 and item.get("certeza") not in ("Buena noticia", ""):
            item["certeza"] = f"{item['certeza']} · sin confirmar"
        elif n >= 2 and item.get("certeza"):
            item["certeza"] = f"{item['certeza']} · {n} fuentes"
        out.append(item)
    out.sort(key=lambda x: (x["afecta_proveedor"] and x["riesgo"] >= 4, x["riesgo"], x["fuentes"]), reverse=True)
    return out


def obtener(config, errores, estado=None):
    """Ejecuta todas las búsquedas en paralelo (una caída no detiene el resto).

    `estado`, si se pasa una lista, recibe una fila por búsqueda: origen, consulta, noticias encontradas y error.
    """
    dias = max(1, round(config.get("max_horas", 72) / 24))
    tareas = ([("Google News · Perú", q, lambda q=q: _buscar_google(q, "es", dias)) for q in config.get("google_news", [])]
              + [("Google News · Colombia", q, lambda q=q: _buscar_google(q, "co", dias)) for q in config.get("google_news_colombia", [])]
              + [("Google News · Mundo (es)", q, lambda q=q: _buscar_google(q, "es", dias)) for q in config.get("google_news_mundo", [])]
              + [("Google News · Mundo (en)", q, lambda q=q: _buscar_google(q, "en", dias)) for q in config.get("google_news_en", [])]
              + [("RSS directo", f.get("nombre") or f.get("url"), lambda f=f: _rss_directo(f)) for f in config.get("rss_directos", [])])

    def una(tarea):
        origen, consulta, fn = tarea
        try:
            return origen, consulta, fn(), None
        except Exception as e:
            return origen, consulta, [], str(e)[:160]

    items = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for origen, consulta, encontrados, error in ex.map(una, tareas):  # map conserva el orden
            items += encontrados
            if error:
                errores.append(f"{origen} '{consulta}': {error}")
            if estado is not None:
                estado.append({"origen": origen, "consulta": consulta, "noticias": len(encontrados), "error": error or ""})
    for q in config.get("gdelt", []):
        try:
            encontrados, error = _buscar_gdelt(q), ""
        except ValueError:
            encontrados, error = [], "respuesta no válida (suele ser límite de consultas; se reintenta en la próxima)"
        except Exception as e:
            encontrados, error = [], str(e)[:160]
        items += encontrados
        if error:
            errores.append(f"GDELT: {error}")
        if estado is not None:
            estado.append({"origen": "GDELT", "consulta": q, "noticias": len(encontrados), "error": error})
    if config.get("verificar_fechas", True):
        verificar_fechas(items, proveedor=config.get("proveedor_claves", []))
    return filtrar(items, config.get("max_horas", 72), proveedor=config.get("proveedor_claves", []))


def _rss_directo(fuente):
    """Feed RSS de un medio u organismo (config `rss_directos`: lista de {nombre, url})."""
    items = parse_rss(red.get(fuente["url"]).text)
    for it in items:
        it["origen"] = "RSS directo"
        it["fuente"] = it["fuente"] or fuente.get("nombre", "")
    return items
