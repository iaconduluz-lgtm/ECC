"""Plan de inventario mensual (toneladas).

Inventario final = inicial + compras importación + compra nacional + producto terminado (PT) - ventas + ajuste.
El inicial de cada mes es el final del mes anterior. Meses de inventario = final / ventas del mes.
Para los meses ya cerrados se puede dar el inventario final real (`cierres_reales`, en orden desde enero):
se usa ese valor y la diferencia con el cálculo queda como "diferencia" del mes.

El plan es información privada: se guarda en los Secrets de Streamlit (`[ajustes.plan_inventario]`)
o en data/ajustes.yaml (excluido de git), nunca en config.yaml.
"""
from datetime import date

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre",
         "Noviembre", "Diciembre"]
CAMPOS = ["compras_importacion", "compra_nacional", "producto_terminado", "ventas", "ajuste"]


def _lista(plan, campo):
    valores = list(plan.get(campo) or [])
    valores = [float(v or 0) for v in valores][:12]
    return valores + [0.0] * (12 - len(valores))


def proyectar(plan):
    """Devuelve una fila por mes con inicial, entradas, ventas, final, meses y días de inventario."""
    datos = {c: _lista(plan, c) for c in CAMPOS}
    inicial = float(plan.get("inventario_inicial") or 0)
    reales = [float(v) for v in (plan.get("cierres_reales") or [])][:12]
    filas = []
    for i, mes in enumerate(MESES):
        entradas = datos["compras_importacion"][i] + datos["compra_nacional"][i] + datos["producto_terminado"][i]
        calculado = round(inicial + entradas - datos["ventas"][i] + datos["ajuste"][i], 2)
        real = i < len(reales)
        final = round(reales[i], 2) if real else calculado
        ventas = datos["ventas"][i]
        meses_inv = round(final / ventas, 2) if ventas else None
        filas.append({"mes": mes, "numero": i + 1, "inicial": round(inicial, 2),
                      **{c: datos[c][i] for c in CAMPOS}, "final": final, "tipo": "Real" if real else "Proyectado",
                      "diferencia": round(final - calculado, 2) if real else 0.0, "meses_inventario": meses_inv,
                      "dias_inventario": round(meses_inv * 30) if meses_inv is not None else None})
        inicial = final
    return filas


def mes_actual(plan, hoy=None):
    hoy = hoy or date.today()
    return hoy.month if int(plan.get("anio") or hoy.year) == hoy.year else None


def situacion_actual(plan, hoy=None):
    """Inventario al inicio del mes en curso y consumo de referencia (promedio de ventas de este mes y los 2 siguientes)."""
    m = mes_actual(plan, hoy)
    if not m:
        return None
    filas = proyectar(plan)
    fila = filas[m - 1]
    proximas = [f["ventas"] for f in filas[m - 1:m + 2] if f["ventas"]]
    consumo = round(sum(proximas) / len(proximas), 2) if proximas else fila["ventas"]
    return {"mes": fila["mes"], "inventario": fila["inicial"], "consumo_mensual": consumo, "fila": fila}


def meses_criticos(plan, minimo_dias, hoy=None):
    """Meses desde el actual en adelante cuyo inventario final cubre menos de `minimo_dias`."""
    m = mes_actual(plan, hoy) or 1
    return [f for f in proyectar(plan)[m - 1:] if f["dias_inventario"] is not None and f["dias_inventario"] < minimo_dias]


def compras_pendientes(plan, costo_cop_t, sens=None, hoy=None):
    """Compras de importación de este mes en adelante, con su costo estimado y su sensibilidad al cobre/TRM."""
    m = mes_actual(plan, hoy) or 1
    out = []
    for f in proyectar(plan)[m - 1:]:
        t = f["compras_importacion"]
        if not t:
            continue
        fila = {"mes": f["mes"], "toneladas": t, "costo_estimado_cop": round(t * costo_cop_t) if costo_cop_t else None}
        if sens:
            fila["si_cobre_sube_5pct"] = round(t * sens["cobre_1pct_cop_t"] * 5)
            fila["si_trm_sube_5pct"] = round(t * sens["trm_1pct_cop_t"] * 5)
        out.append(fila)
    return out


def _num(v):
    """Siempre con decimal (9 -> 9.0): el validador de Streamlit Cloud rechaza listas que mezclan enteros y decimales."""
    return repr(round(float(v), 4))


def a_toml(plan):
    """Texto listo para pegar en los Secrets de Streamlit."""
    lineas = ["[ajustes.plan_inventario]", f"anio = {int(plan.get('anio') or date.today().year)}",
              f"inventario_inicial = {_num(plan.get('inventario_inicial') or 0)}"]
    for c in CAMPOS:
        lineas.append(f"{c} = [{', '.join(_num(v) for v in _lista(plan, c))}]")
    reales = [float(v) for v in (plan.get("cierres_reales") or [])][:12]
    lineas.append(f"cierres_reales = [{', '.join(_num(v) for v in reales)}]")
    return "\n".join(lineas)
