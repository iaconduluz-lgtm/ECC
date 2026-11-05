"""Análisis sin IA: escenarios de cobre/TRM, contexto histórico, clasificación de noticias y recomendación.

Las reglas son heurísticas transparentes: cada recomendación lista sus razones. No es asesoría financiera.
"""
from datetime import timedelta
from statistics import mean

from . import costos
from .noticias import normalizar

PASOS = [-10, -5, 0, 5, 10]  # variaciones en % para los escenarios


def escenarios(precio_usd_t, trm, prov, consumo_mensual_t, pasos=PASOS):
    """Matriz cobre% x TRM%: costo COP/t y cuánto cambia tu gasto mensual frente a hoy."""
    base = costos.costo_proveedor(precio_usd_t, trm, prov)["cop_t"]
    filas = []
    for cu in pasos:
        for tr in pasos:
            c = costos.costo_proveedor(precio_usd_t * (1 + cu / 100), trm * (1 + tr / 100), prov)["cop_t"]
            filas.append({"cobre_pct": cu, "trm_pct": tr, "costo_cop_t": c, "delta_cop_t": c - base,
                          "impacto_mensual_cop": (c - base) * (consumo_mensual_t or 0)})
    return filas


def sensibilidad(precio_usd_t, trm, prov, consumo_mensual_t):
    """Cuánto cambia el gasto mensual por cada 1 % de subida del cobre y de la TRM."""
    base = costos.costo_proveedor(precio_usd_t, trm, prov)["cop_t"]
    cu = costos.costo_proveedor(precio_usd_t * 1.01, trm, prov)["cop_t"] - base
    tr = costos.costo_proveedor(precio_usd_t, trm * 1.01, prov)["cop_t"] - base
    return {"cobre_1pct_cop_t": cu, "trm_1pct_cop_t": tr,
            "cobre_1pct_mes": cu * (consumo_mensual_t or 0), "trm_1pct_mes": tr * (consumo_mensual_t or 0)}


def contexto(serie, dias=(30, 90, 365)):
    """Precio actual frente a sus promedios y su posición en el rango del último año (0 = mínimo, 100 = máximo)."""
    if not serie:
        return {}
    actual, hoy = serie[0][1], serie[0][0]
    out = {"actual": actual}
    for d in dias:
        tramo = [v for f, v in serie if f >= hoy - timedelta(days=d)]
        if len(tramo) >= 5:
            out[f"prom_{d}"] = round(mean(tramo), 2)
            out[f"vs_prom_{d}_pct"] = round((actual - mean(tramo)) / mean(tramo) * 100, 2)
    anio = [v for f, v in serie if f >= hoy - timedelta(days=365)]
    if len(anio) >= 20 and max(anio) > min(anio):
        out["percentil_1a"] = round((actual - min(anio)) / (max(anio) - min(anio)) * 100)
        out["min_1a"], out["max_1a"] = min(anio), max(anio)
    return out


CATEGORIAS = [
    # Logística primero: un paro en un puerto o en la vía a tu planta es logística, no minería.
    ("Logística / puertos", ("callao", "matarani", "buenaventura", "via al pacifico", "via buenaventura", "via cali",
                             "puerto", "portuari", "port ", "camioner", "transportador", "contenedor", "flete",
                             "freight", "naviera", "shipping", "carga"),
     "Puede retrasar el embarque, la llegada a Buenaventura o el transporte a tu planta en Cali, y subir el flete."),
    ("Suministro Perú", ("huelga", "paro", "bloqueo", "bloquean", "strike", "blockade", "fuerza mayor", "force majeure",
                         "suspende", "las bambas", "antamina", "cerro verde", "quellaveco", "corredor minero", "toma de"),
     "Puede retrasar o encarecer tus envíos desde Perú y presionar el precio al alza."),
    ("Política / aranceles", ("arancel", "tariff", "impuesto", "regalias", "export ban", "sancion", "gobierno", "congreso",
                              "dian", "aduana", "importacion", "reforma tributaria", "sobretasa"),
     "Puede cambiar tus costos de importación o generar volatilidad en el precio."),
    ("Dólar / economía", ("dolar", "trm", "tasa de cambio", "peso colombiano", "banco de la republica", "devaluacion",
                          "tasas de interes", "inflacion"),
     "Mueve la TRM: si el dólar sube, tu cobre cuesta más en pesos."),
    ("Oferta mundial", ("chile", "codelco", "escondida", "grasberg", "kamoa", "cobre panama", "supply", "oferta",
                        "deficit", "shortage", "escasez", "inventarios", "stocks"),
     "Menos oferta mundial suele subir el precio; más oferta, bajarlo."),
    ("Demanda / mercado", ("china", "demanda", "demand", "futuros", "futures", "precio", "price", "lme", "comex", "fed"),
     "Mueve el precio internacional del cobre."),
]


def clasificar(noticia):
    if noticia.get("afecta_proveedor"):
        return "Tu proveedor directo", "Afecta directamente a quien te vende: revisa tus pedidos y embarques."
    t = normalizar(noticia["titulo"])
    for nombre, claves, impacto in CATEGORIAS:
        if any(c in t for c in claves):
            return nombre, impacto
    return "Otros", "Impacto indirecto o por confirmar."


def resumen_noticias(noticias):
    """Agrupa por categoría: cantidad, riesgo máximo e impacto típico."""
    grupos = {}
    for n in noticias:
        cat, impacto = clasificar(n)
        g = grupos.setdefault(cat, {"categoria": cat, "cantidad": 0, "riesgo_max": 0, "impacto": impacto, "ejemplo": ""})
        g["cantidad"] += 1
        if n["riesgo"] > g["riesgo_max"]:
            g["riesgo_max"], g["ejemplo"] = n["riesgo"], n["titulo"]
    return sorted(grupos.values(), key=lambda g: (-g["riesgo_max"], -g["cantidad"]))


def recomendacion(ctx, cfg):
    """Devuelve {'accion', 'tono', 'razones', 'diversificar'} combinando precio, TRM, noticias e inventario."""
    puntos, razones = 0, []
    cu = ctx.get("contexto_cobre") or {}
    tr = ctx.get("contexto_trm") or {}

    if cu.get("vs_prom_90_pct") is not None:
        v = cu["vs_prom_90_pct"]
        if v <= -3:
            puntos += 1
            razones.append(f"El cobre está {abs(v):.1f} % por debajo de su promedio de 3 meses: precio atractivo.")
        elif v >= 5:
            puntos -= 1
            razones.append(f"El cobre está {v:.1f} % por encima de su promedio de 3 meses: precio caro.")
    if cu.get("percentil_1a") is not None:
        p = cu["percentil_1a"]
        if p <= 30:
            puntos += 1
            razones.append(f"El cobre está en la parte baja de su rango del último año ({p}/100).")
        elif p >= 80:
            puntos -= 1
            razones.append(f"El cobre está cerca del máximo del último año ({p}/100).")
    var_cu = ctx.get("cobre_var_semanal")
    if var_cu is not None and var_cu <= cfg["alertas"]["cobre_baja_semanal_pct"]:
        puntos += 1
        razones.append(f"El cobre cayó {abs(var_cu):.1f} % en la semana.")

    if tr.get("vs_prom_90_pct") is not None:
        v = tr["vs_prom_90_pct"]
        if v <= -2:
            puntos += 1
            razones.append(f"El dólar (TRM) está {abs(v):.1f} % por debajo de su promedio de 3 meses: buen momento para pagar en USD.")
        elif v >= 3:
            puntos -= 1
            razones.append(f"El dólar (TRM) está {v:.1f} % por encima de su promedio de 3 meses: pagar en USD sale más caro.")

    noticias = ctx.get("noticias", [])
    peligro_prov = [n for n in noticias if n.get("afecta_proveedor") and n["riesgo"] >= 8]
    riesgo_peru = [n for n in noticias if (n["riesgo"] >= cfg["alertas"]["noticia_riesgo_minimo"]
                   and clasificar(n)[0] in ("Suministro Perú", "Logística / puertos", "Tu proveedor directo"))
                   or (n.get("afecta_proveedor") and n["riesgo"] >= 4)]
    if peligro_prov:
        return {"accion": "Asegurar el suministro: activar un proveedor alternativo", "tono": "urgente",
                "diversificar": True,
                "razones": [f"PELIGRO en tu proveedor directo: {peligro_prov[0]['titulo']}",
                            "Confirma hoy con tu proveedor el estado de tus pedidos y embarques.",
                            "Cotiza con un proveedor alternativo y revisa cuántos días de inventario te quedan."] + razones}
    if riesgo_peru:
        puntos += 1
        razones.append(f"{len(riesgo_peru)} noticia(s) de riesgo alto para tu suministro (Perú, puertos o la vía a "
                       "tu planta): asegurar material antes de que suba o se retrase.")

    cob, minimo = ctx.get("cobertura_dias"), cfg["empresa"]["cobertura_minima_dias"]
    if cob is not None and cob < minimo:
        return {"accion": "Comprar ya lo necesario", "tono": "urgente", "diversificar": bool(riesgo_peru),
                "razones": [f"El inventario solo alcanza para {cob:.0f} días (mínimo {minimo})."] + razones}
    if cob is not None and cob > minimo * 3:
        puntos -= 1
        razones.append(f"Tienes inventario para {cob:.0f} días: no hay prisa por comprar.")

    if puntos >= 2:
        accion, tono = "Comprar más / adelantar compras", "comprar"
    elif puntos <= -2:
        accion, tono = "Comprar solo lo necesario y esperar", "esperar"
    else:
        accion, tono = "Comprar lo normal", "normal"
    if not razones:
        razones.append("Precio, dólar y noticias dentro de lo normal.")
    return {"accion": accion, "tono": tono, "razones": razones, "diversificar": bool(riesgo_peru)}


def promedio_mensual(serie):
    """[(fecha, valor)] -> [('2026-10', promedio)] de más antiguo a más reciente."""
    meses = {}
    for f, v in serie:
        meses.setdefault(f.strftime("%Y-%m"), []).append(v)
    return [(m, round(mean(vs), 2)) for m, vs in sorted(meses.items())]
