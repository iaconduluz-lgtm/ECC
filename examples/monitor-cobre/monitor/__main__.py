"""Ejecuta un ciclo del monitor: python -m monitor [--config config.yaml] [--sin-envio]"""
import argparse
import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import alertas, analisis, cobre, configuracion, costos, estado, noticias, reporte, trm


def descargar(cfg):
    """Parte lenta (red): TRM, cobre (siempre el de mercado, para tener histórico) y noticias."""
    errores = []
    ahora = datetime.now(timezone.utc)
    datos = {"fecha": ahora.date().isoformat(),
             "fecha_hora": ahora.astimezone(ZoneInfo("America/Bogota")).strftime("%Y-%m-%d %H:%M (hora Colombia)"),
             "serie_trm": [], "cobre": None, "errores": errores}
    try:
        datos["serie_trm"] = trm.obtener()
    except Exception as e:
        errores.append(f"TRM: {e}")
    try:
        datos["cobre"] = cobre.obtener({}, errores)
    except Exception as e:
        errores.append(f"Cobre: {e}")
    datos["noticias"] = noticias.obtener(cfg.get("noticias", {}), errores)
    return datos


def calcular(datos, cfg):
    """Parte rápida (sin red): costos, contexto, escenarios y recomendación con la configuración actual."""
    ctx = {k: datos[k] for k in ("fecha", "fecha_hora", "noticias")}
    errores = list(datos["errores"])
    serie_trm = datos["serie_trm"]
    if serie_trm:
        ctx.update(trm=serie_trm[0][1], trm_var_semanal=costos.variacion_pct(serie_trm, 5),
                   serie_trm=serie_trm, contexto_trm=analisis.contexto(serie_trm))
    serie_cu = []
    if datos["cobre"]:
        precio, serie_cu, fuente = datos["cobre"]
        ctx.update(cobre_usd_t=precio, fuente_cobre=fuente, serie_cobre=serie_cu,
                   cobre_var_semanal=costos.variacion_pct(serie_cu, 5), contexto_cobre=analisis.contexto(serie_cu))
    manual = (cfg.get("cobre") or {}).get("precio_manual_usd_t")
    if manual:
        ctx.update(cobre_usd_t=float(manual), fuente_cobre="manual (LME/broker)")
        if serie_cu:
            ctx["contexto_cobre"] = analisis.contexto([(serie_cu[0][0], float(manual))] + serie_cu[1:])

    if ctx.get("trm") and ctx.get("cobre_usd_t"):
        ctx["ranking"] = costos.comparar(ctx["cobre_usd_t"], ctx["trm"], cfg["proveedores"])
    emp = cfg["empresa"]
    ctx["cobertura_dias"] = costos.cobertura_dias(emp.get("inventario_toneladas", 0), emp.get("consumo_mensual_toneladas"))
    if ctx.get("ranking"):
        prov = cfg["proveedores"][emp["proveedor_actual"]]
        ctx["sensibilidad"] = analisis.sensibilidad(ctx["cobre_usd_t"], ctx["trm"], prov, emp.get("consumo_mensual_toneladas"))
    ctx["recomendacion"] = analisis.recomendacion(ctx, cfg)
    return ctx, alertas.evaluar(ctx, cfg), errores


def ejecutar(cfg, base, enviar=True, guardar=True):
    ctx, todas, errores = calcular(descargar(cfg), cfg)
    ruta_enviadas = os.path.join(base, "data", "alertas_enviadas.json")
    enviadas = estado.cargar_enviadas(ruta_enviadas)
    nuevas = [a for a in todas if a["id"] not in set(enviadas)]

    texto = reporte.generar(ctx, todas, errores)
    if not guardar:
        return ctx, todas, nuevas, errores, texto
    with open(os.path.join(base, "reportes", "ultimo.md"), "w", encoding="utf-8") as f:
        f.write(texto)
    resumen = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumen:
        with open(resumen, "a", encoding="utf-8") as f:
            f.write(texto)

    if ctx.get("ranking"):
        estado.anexar_historico(os.path.join(base, "data", "historico.csv"), {
            "fecha_hora": ctx["fecha_hora"], "trm": ctx["trm"], "cobre_usd_t": ctx["cobre_usd_t"],
            "fuente_cobre": ctx["fuente_cobre"], "proveedor_mas_barato": ctx["ranking"][0]["clave"],
            "costo_cop_t_mas_barato": ctx["ranking"][0]["cop_t"]})

    if enviar and nuevas:
        msg = alertas.formatear(nuevas)
        canales = []
        for nombre, fn in (("Telegram", lambda: alertas.enviar_telegram(msg)),
                           ("correo", lambda: alertas.enviar_correo("Alertas monitor de cobre", msg))):
            try:
                if fn():
                    canales.append(nombre)
            except Exception as e:
                errores.append(f"Envío {nombre}: {e}")
        if canales:
            estado.guardar_enviadas(ruta_enviadas, enviadas + [a["id"] for a in nuevas])
    return ctx, todas, nuevas, errores, texto


def main(argv=None):
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description="Monitor de cobre, TRM y riesgo de suministro")
    ap.add_argument("--config", default=os.path.join(base, "config.yaml"))
    ap.add_argument("--sin-envio", action="store_true", help="no enviar Telegram/correo")
    args = ap.parse_args(argv)
    cfg = configuracion.cargar(base, args.config)
    _, todas, nuevas, errores, texto = ejecutar(cfg, base, enviar=not args.sin_envio)
    print(texto)
    print(f"Alertas: {len(todas)} (nuevas: {len(nuevas)}). Errores de fuentes: {len(errores)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
