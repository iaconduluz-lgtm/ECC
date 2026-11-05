"""Persistencia simple en archivos: histórico CSV y alertas ya enviadas (para no repetir)."""
import csv
import json
import os

CAMPOS = ["fecha_hora", "trm", "cobre_usd_t", "fuente_cobre", "proveedor_mas_barato", "costo_cop_t_mas_barato"]


def anexar_historico(ruta, fila):
    nuevo = not os.path.exists(ruta)
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    with open(ruta, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS)
        if nuevo:
            w.writeheader()
        w.writerow({k: fila.get(k) for k in CAMPOS})


def cargar_enviadas(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
            return datos if isinstance(datos, list) else []
    except (OSError, ValueError):
        return []


def guardar_enviadas(ruta, ids, maximo=2000):
    """Guarda los últimos `maximo` ids en orden de envío."""
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(list(ids)[-maximo:], f, indent=0)
