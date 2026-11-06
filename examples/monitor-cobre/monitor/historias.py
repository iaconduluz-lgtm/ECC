"""Seguimiento de historias y opiniones del usuario sobre las noticias.

Una HISTORIA agrupa las noticias del mismo hecho a lo largo de los días (p. ej. un bloqueo que dura una semana).
Su estado se calcula con fechas, no con el número de veces que se abre la app, así que es estable:
  Nueva (vista por primera vez hace < 24 h) · Sigue · Empeora (subió de nivel en las últimas 24 h)
  · Resuelta (salió una buena noticia del mismo hecho) · Sin novedades (nada nuevo en 48 h).

OPINIONES: "me sirve" destaca la historia; "no me sirve" la oculta (también las noticias futuras del mismo hecho).
Los medios con varias opiniones negativas se marcan como poco útiles y bajan en el orden.

Todo se guarda en un archivo JSON pequeño (data/historias.json).
"""
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

from . import noticias as nt

DIAS_GUARDADOS = 30
DIAS_PARA_UNIR = 14
UMBRAL_HISTORIA = 0.5  # entre días distintos la redacción cambia más que entre medios del mismo día (0,6)


def vacio():
    return {"historias": {}, "opiniones": {}, "medios": {}}


def cargar(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
        return {**vacio(), **datos}
    except (OSError, ValueError):
        return vacio()


def guardar(ruta, estado):
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=0, default=str)


def _ts(fecha):
    return fecha.isoformat() if isinstance(fecha, datetime) else fecha


def _dt(texto):
    return datetime.fromisoformat(texto) if isinstance(texto, str) else texto


def _nuevo_id(titulo):
    return hashlib.sha1(nt.normalizar(titulo).encode()).hexdigest()[:12]


def actualizar(estado, lista, ahora=None):
    """Asigna cada noticia a una historia (o crea una) y anota en la noticia el estado de su historia.

    Devuelve (visibles, ocultas): las noticias que el usuario marcó "no me sirve" quedan en `ocultas`.
    """
    ahora = ahora or datetime.now(timezone.utc)
    hist = estado["historias"]
    limite_union = ahora - timedelta(days=DIAS_PARA_UNIR)
    # Primero los problemas, después las buenas noticias (que pueden resolver una historia ya creada).
    orden = sorted(lista, key=lambda n: n.get("certeza") == "Buena noticia")
    for n in orden:
        pal = nt.palabras(n["titulo"])
        buena = n.get("certeza") == "Buena noticia"
        fecha = n.get("fecha") or ahora
        candidatas = [(sid, h) for sid, h in hist.items() if _dt(h["ultima_vez"]) >= limite_union]
        if buena:
            # Una buena noticia resuelve un problema del mismo hecho (umbral más bajo: los verbos cambian).
            match = next(((sid, h) for sid, h in candidatas if not h.get("buena")
                          and nt.misma_noticia(pal, set(h["palabras"]), UMBRAL_HISTORIA)), None)
            if match:
                sid, h = match
                h["resuelta"] = _ts(fecha)
                h["resuelta_por"] = n["titulo"]
                n["historia"], n["estado_historia"] = sid, "Resuelve una historia"
                n["dias_historia"] = (fecha.date() - _dt(h["primera_vez"]).date()).days + 1
                continue
        match = next(((sid, h) for sid, h in candidatas if bool(h.get("buena")) == buena
                      and nt.misma_noticia(pal, set(h["palabras"]), UMBRAL_HISTORIA)), None)
        if match:
            sid, h = match
            h["palabras"] = sorted(set(h["palabras"]) | pal)
            h["primera_vez"] = _ts(min(_dt(h["primera_vez"]), fecha))
            h["ultima_vez"] = _ts(max(_dt(h["ultima_vez"]), fecha))
            if n["riesgo"] > h["riesgo_max"]:
                h["riesgo_max"], h["empeoro"] = n["riesgo"], _ts(ahora)
            h["titulo_reciente"] = n["titulo"]
        else:
            sid = _nuevo_id(n["titulo"])
            while sid in hist:
                sid = _nuevo_id(sid)
            h = hist[sid] = {"titulo": n["titulo"], "titulo_reciente": n["titulo"], "palabras": sorted(pal),
                             "primera_vez": _ts(fecha), "ultima_vez": _ts(fecha), "riesgo_max": n["riesgo"],
                             "creada": _ts(ahora), "buena": buena}
        n["historia"] = sid
    for n in lista:
        sid = n.get("historia")
        if sid and n.get("estado_historia") != "Resuelve una historia":
            h = hist[sid]
            n["estado_historia"] = estado_de(h, ahora)
            n["dias_historia"] = (ahora.date() - _dt(h["primera_vez"]).date()).days + 1
            if n["estado_historia"] == "Resuelta":
                n["riesgo"], n["nivel"] = min(n["riesgo"], 2), nt.nivel(min(n["riesgo"], 2))
                n["certeza"] = "Resuelta: " + h.get("resuelta_por", "")[:80]
        n["opinion"] = estado["opiniones"].get(sid or "", "")
        n["medio_poco_util"] = any(_medio_poco_util(estado, m) for m in n.get("lista_fuentes") or [n.get("fuente", "")])
    # Limpieza: historias viejas fuera.
    for sid in [s for s, h in hist.items() if _dt(h["ultima_vez"]) < ahora - timedelta(days=DIAS_GUARDADOS)]:
        hist.pop(sid)
        estado["opiniones"].pop(sid, None)
    visibles = [n for n in lista if n.get("opinion") != "no_sirve"]
    ocultas = [n for n in lista if n.get("opinion") == "no_sirve"]
    visibles.sort(key=lambda n: (n.get("opinion") == "sirve", n["afecta_proveedor"] and n["riesgo"] >= 4,
                                 n["riesgo"], not n.get("medio_poco_util"), n.get("fuentes", 1)), reverse=True)
    return visibles, ocultas


def estado_de(h, ahora):
    if h.get("resuelta"):
        return "Resuelta"
    if _dt(h["creada"]) >= ahora - timedelta(hours=24) and _dt(h["primera_vez"]) >= ahora - timedelta(hours=48):
        return "Nueva"
    if h.get("empeoro") and _dt(h["empeoro"]) >= ahora - timedelta(hours=24):
        return "Empeora"
    if _dt(h["ultima_vez"]) < ahora - timedelta(hours=48):
        return "Sin novedades"
    return "Sigue"


def opinar(estado, noticia, opinion):
    """opinion: "sirve", "no_sirve" o "" (quitar). También cuenta la opinión para cada medio de la noticia."""
    sid = noticia.get("historia")
    if not sid:
        return
    anterior = estado["opiniones"].get(sid, "")
    if opinion:
        estado["opiniones"][sid] = opinion
    else:
        estado["opiniones"].pop(sid, None)
    for medio in noticia.get("lista_fuentes") or [noticia.get("fuente", "")]:
        if not medio:
            continue
        m = estado["medios"].setdefault(medio, {"sirve": 0, "no_sirve": 0})
        if anterior:
            m[anterior] = max(0, m[anterior] - 1)
        if opinion:
            m[opinion] += 1


def _medio_poco_util(estado, medio):
    m = estado["medios"].get(medio)
    return bool(m) and m["no_sirve"] >= 3 and m["no_sirve"] > m["sirve"]


def medios_poco_utiles(estado):
    return sorted(m for m in estado["medios"] if _medio_poco_util(estado, m))
