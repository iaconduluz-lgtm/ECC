"""Precio del cobre con varias fuentes en cadena (si una falla se prueba la siguiente).

1. Precio manual (p. ej. el cierre LME que te da tu broker), si está configurado.
2. COMEX HG=F desde Yahoo Finance (USD/lb, ~15 min de retraso). Suele bloquear servidores en la nube.
3. COMEX HG.F desde Stooq (CSV diario).
4. LME cash settlement desde Westmetall (oficial LME, cierre del día hábil anterior).

Cada lector valida que el precio esté en un rango creíble antes de aceptarlo.
"""
import csv
import io
import re
from datetime import date, datetime, timezone

from . import red

LB_POR_TONELADA = 2204.62
MAX_DIAS = 1900  # ~5 años de días hábiles con margen
RANGO_USD_T = (3000, 30000)  # fuera de esto se considera un dato mal leído
YAHOO = ["https://query1.finance.yahoo.com/v8/finance/chart/HG=F",
         "https://query2.finance.yahoo.com/v8/finance/chart/HG=F"]
STOOQ = "https://stooq.com/q/d/l/"
WESTMETALL = "https://www.westmetall.com/en/markdaten.php"
NAVEGADOR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


def _valido(usd_t):
    return usd_t is not None and RANGO_USD_T[0] <= usd_t <= RANGO_USD_T[1]


def _lb_a_t(valor):
    """Convierte USD/lb (o centavos/lb) a USD/t."""
    if valor > 100:  # vino en centavos por libra
        valor /= 100
    return round(valor * LB_POR_TONELADA, 2)


def parse(payload):
    """Yahoo: devuelve (precio_actual_usd_t, [(fecha, cierre_usd_t)] de más reciente a más antigua)."""
    result = payload["chart"]["result"][0]
    tiempos = result.get("timestamp") or []
    cierres = result["indicators"]["quote"][0].get("close") or []
    serie = []
    for ts, c in zip(tiempos, cierres):
        if c is None:
            continue
        fecha = datetime.fromtimestamp(ts, tz=timezone.utc).date()
        serie.append((fecha, _lb_a_t(c)))
    serie.sort(key=lambda x: x[0], reverse=True)
    actual = result.get("meta", {}).get("regularMarketPrice")
    actual_t = _lb_a_t(actual) if actual else (serie[0][1] if serie else None)
    if not _valido(actual_t):
        raise ValueError(f"precio fuera de rango: {actual_t}")
    return actual_t, serie


def parse_stooq(texto):
    filas = list(csv.DictReader(io.StringIO(texto.strip())))
    if not filas or "Close" not in filas[0]:
        raise ValueError(f"respuesta inesperada: {texto[:80]!r}")
    serie = []
    for f in filas:
        try:
            serie.append((date.fromisoformat(f["Date"]), _lb_a_t(float(f["Close"]))))
        except (KeyError, ValueError):
            continue
    serie.sort(key=lambda x: x[0], reverse=True)
    serie = serie[:MAX_DIAS]
    if not serie or not _valido(serie[0][1]):
        raise ValueError("sin precios válidos")
    return serie[0][1], serie


def _numero(texto):
    """'10,123.50' o '10.123,50' -> 10123.5"""
    t = texto.strip()
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", t):
        t = t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(",", "")
    return float(t)


MESES = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}


def _fecha(texto):
    t = texto.strip().lower()
    m = re.match(r"(\d{1,2})\.?\s*([a-z]+)\.?\s*(\d{4})", t)
    if m and m.group(2)[:3] in {k[:3] for k in MESES}:
        mes = next(v for k, v in MESES.items() if k.startswith(m.group(2)[:3]))
        return date(int(m.group(3)), mes, int(m.group(1)))
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            pass
    return None


def parse_westmetall(html):
    """Lee filas <tr> cuya primera celda es una fecha y la segunda un precio en USD/t."""
    serie = []
    for fila in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S | re.I):
        celdas = [re.sub(r"<[^>]+>|&nbsp;", " ", c).strip()
                  for c in re.findall(r"<td[^>]*>(.*?)</td>", fila, flags=re.S | re.I)]
        if len(celdas) < 2:
            continue
        fecha = _fecha(celdas[0])
        try:
            valor = _numero(celdas[1])
        except ValueError:
            continue
        if fecha and _valido(valor):
            serie.append((fecha, round(valor, 2)))
    serie = sorted(set(serie), key=lambda x: x[0], reverse=True)[:MAX_DIAS]
    if not serie:
        raise ValueError("no se encontró la tabla de precios")
    return serie[0][1], serie


def _yahoo():
    ultimo = None
    for url in YAHOO:
        try:
            return parse(red.get(url, params={"interval": "1d", "range": "5y"}, headers=NAVEGADOR).json())
        except Exception as e:
            ultimo = e
    raise ultimo


def _stooq():
    return parse_stooq(red.get(STOOQ, params={"s": "hg.f", "i": "d"}, headers=NAVEGADOR).text)


def _westmetall():
    return parse_westmetall(red.get(WESTMETALL, params={"action": "table", "field": "LME_Cu_cash"},
                                    headers=NAVEGADOR).text)


FUENTES = [
    ("COMEX HG=F vía Yahoo (aprox. LME, ~15 min retraso)", _yahoo),
    ("COMEX vía Stooq (aprox. LME, cierre diario)", _stooq),
    ("LME oficial vía Westmetall (cierre día hábil anterior)", _westmetall),
]


def obtener(config, errores=None):
    """Devuelve (precio_usd_t, serie, nombre_fuente). Anota en `errores` las fuentes que fallaron."""
    manual = (config or {}).get("precio_manual_usd_t")
    if manual:
        return float(manual), [], "manual (LME/broker)"
    fallos = []
    for nombre, fn in FUENTES:
        try:
            precio, serie = fn()
            if fallos and errores is not None:
                errores.extend(f"Cobre ({n}): {e}" for n, e in fallos)
            return precio, serie, nombre
        except Exception as e:
            fallos.append((nombre.split(" (")[0], e))
    raise RuntimeError("ninguna fuente respondió — " + "; ".join(f"{n}: {e}" for n, e in fallos))
