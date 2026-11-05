"""Costo puesto en planta por proveedor, en COP y USD por tonelada."""


def costo_proveedor(precio_cobre_usd_t, trm, prov):
    usd = precio_cobre_usd_t + prov.get("prima_usd_t", 0) + prov.get("flete_usd_t", 0) + prov.get("seguro_usd_t", 0)
    usd_con_arancel = usd * (1 + prov.get("arancel_pct", 0) / 100)
    return {
        "usd_t": round(usd_con_arancel, 2),
        "cop_t": round(usd_con_arancel * trm, 0),
        "dias_transito": prov.get("dias_transito"),
    }


def comparar(precio_cobre_usd_t, trm, proveedores):
    """Lista de proveedores ordenada del más barato al más caro."""
    filas = []
    for clave, prov in proveedores.items():
        c = costo_proveedor(precio_cobre_usd_t, trm, prov)
        filas.append({"clave": clave, "nombre": prov.get("nombre", clave), **c})
    filas.sort(key=lambda f: f["cop_t"])
    return filas


def variacion_pct(serie, dias=5):
    """Variación % entre el valor más reciente y el de `dias` observaciones atrás."""
    if len(serie) <= dias:
        return None
    actual, antes = serie[0][1], serie[dias][1]
    if not antes:
        return None
    return round((actual - antes) / antes * 100, 2)


def cobertura_dias(inventario_t, consumo_mensual_t):
    if not consumo_mensual_t:
        return None
    return round(inventario_t / consumo_mensual_t * 30, 1)
