"""TRM de Colombia.

1. TRM oficial desde datos.gov.co (dataset 32sa-8pi3, Superfinanciera). Si la consulta larga falla,
   se piden periodos más cortos (5 años -> 1 año -> 30 días).
2. Respaldo: dólar de mercado USD/COP (Yahoo Finance, `COP=X`), aproximación a la TRM.
"""
from datetime import date, datetime, timedelta, timezone

from . import red

URL = "https://www.datos.gov.co/resource/32sa-8pi3.json"
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/COP=X"
NAVEGADOR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
RANGO = (1500, 10000)  # COP por USD creíbles
OFICIAL = "TRM oficial (datos.gov.co)"
MERCADO = "USD/COP de mercado vía Yahoo (aprox. TRM)"


def parse(rows):
    """Convierte filas de la API en [(fecha, valor)] ordenadas de más reciente a más antigua."""
    out = []
    for row in rows:
        try:
            fecha = datetime.fromisoformat(row["vigenciadesde"][:10]).date()
            out.append((fecha, float(row["valor"])))
        except (KeyError, ValueError, TypeError):
            continue
    out.sort(key=lambda x: x[0], reverse=True)
    return out


def parse_yahoo(payload):
    result = payload["chart"]["result"][0]
    serie = [(datetime.fromtimestamp(ts, tz=timezone.utc).date(), round(c, 2))
             for ts, c in zip(result.get("timestamp") or [], result["indicators"]["quote"][0].get("close") or [])
             if c is not None]
    serie = sorted(dict(serie).items(), reverse=True)  # un valor por día
    if not serie or not RANGO[0] <= serie[0][1] <= RANGO[1]:
        raise ValueError("sin valores válidos de USD/COP")
    return serie


def _oficial(anios):
    if anios:
        desde = (date.today() - timedelta(days=365 * anios)).isoformat()
        params = {"$where": f"vigenciadesde >= '{desde}T00:00:00'", "$order": "vigenciadesde DESC", "$limit": 5000}
    else:
        params = {"$order": "vigenciadesde DESC", "$limit": 30}
    serie = parse(red.get(URL, params=params).json())
    if not serie:
        raise ValueError("datos.gov.co no devolvió valores")
    return serie


def obtener(anios=5, errores=None):
    """Devuelve (serie, fuente). Anota en `errores` los intentos fallidos si al final hubo que usar un respaldo."""
    fallos = []
    for periodo in (anios, 1, None):
        try:
            serie = _oficial(periodo)
            if fallos and errores is not None:
                errores.append("TRM: histórico largo no disponible, se muestra un periodo más corto "
                               f"({'1 año' if periodo == 1 else '30 días'}). Detalle: {fallos[0]}")
            return serie, OFICIAL
        except Exception as e:
            fallos.append(e)
    try:
        serie = parse_yahoo(red.get(YAHOO, params={"interval": "1d", "range": f"{anios}y"}, headers=NAVEGADOR).json())
        if errores is not None:
            errores.append(f"TRM oficial no disponible (datos.gov.co: {fallos[-1]}). Se usa el dólar de mercado.")
        return serie, MERCADO
    except Exception as e:
        raise RuntimeError(f"ninguna fuente respondió — datos.gov.co: {fallos[-1]}; Yahoo USD/COP: {e}")
