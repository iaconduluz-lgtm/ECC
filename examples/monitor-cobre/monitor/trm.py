"""TRM oficial de Colombia desde datos.gov.co (dataset 32sa-8pi3, Superfinanciera)."""
from datetime import datetime

from . import red

URL = "https://www.datos.gov.co/resource/32sa-8pi3.json"


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


def obtener(dias=15):
    params = {"$order": "vigenciadesde DESC", "$limit": dias}
    serie = parse(red.get(URL, params=params).json())
    if not serie:
        raise RuntimeError("datos.gov.co no devolvió valores de TRM")
    return serie
