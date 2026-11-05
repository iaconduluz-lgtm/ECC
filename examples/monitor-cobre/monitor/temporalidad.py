"""Temporalidad de una serie diaria [(fecha, valor)]: variación por plazo, estacionalidad y comparación año a año."""
from datetime import timedelta
from statistics import mean

HORIZONTES = [("1 semana", 7), ("1 mes", 30), ("3 meses", 91), ("6 meses", 182), ("1 año", 365), ("5 años", 1826)]
MESES_CORTOS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def _ordenada(serie):
    return sorted(serie, key=lambda x: x[0])


def valor_en(serie, fecha):
    """Último valor disponible en o antes de `fecha` (None si la serie empieza después)."""
    previo = None
    for f, v in _ordenada(serie):
        if f > fecha:
            break
        previo = v
    return previo


def variaciones(serie, horizontes=HORIZONTES):
    """{plazo: % de cambio entre el valor de hace N días y el último}. None si no hay datos tan antiguos."""
    if not serie:
        return {}
    s = _ordenada(serie)
    hoy, actual = s[-1]
    out = {}
    for nombre, dias in horizontes:
        antes = valor_en(s, hoy - timedelta(days=dias)) if s[0][0] <= hoy - timedelta(days=dias) else None
        out[nombre] = round((actual - antes) / antes * 100, 2) if antes else None
    return out


def promedios_mensuales(serie):
    """{(año, mes): promedio}"""
    grupos = {}
    for f, v in serie:
        grupos.setdefault((f.year, f.month), []).append(v)
    return {k: mean(vs) for k, vs in grupos.items()}


def por_anio(serie):
    """Filas {anio, mes, nombre_mes, promedio} para comparar años mes a mes."""
    return [{"anio": a, "mes": m, "nombre_mes": MESES_CORTOS[m - 1], "promedio": round(v, 2)}
            for (a, m), v in sorted(promedios_mensuales(serie).items())]


def estacionalidad(serie, meses_minimos=6):
    """Para cada mes del calendario: cuánto suele estar por encima (+) o por debajo (−) del promedio de su año, en %.

    Solo usa años con al menos `meses_minimos` meses de datos, para que un año a medias no sesgue el resultado.
    """
    mensual = promedios_mensuales(serie)
    anios = {}
    for (a, m), v in mensual.items():
        anios.setdefault(a, {})[m] = v
    desvios = {m: [] for m in range(1, 13)}
    for meses in anios.values():
        if len(meses) < meses_minimos:
            continue
        prom = mean(meses.values())
        for m, v in meses.items():
            desvios[m].append((v - prom) / prom * 100)
    return [{"mes": m, "nombre_mes": MESES_CORTOS[m - 1],
             "desvio_pct": round(mean(d), 2) if d else None, "anios": len(d)} for m, d in desvios.items()]


def mejores_meses(estac, n=3, barato=True):
    """Los `n` meses que suelen estar más baratos (o más caros)."""
    validos = [e for e in estac if e["desvio_pct"] is not None]
    return sorted(validos, key=lambda e: e["desvio_pct"], reverse=not barato)[:n]
