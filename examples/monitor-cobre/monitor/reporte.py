"""Reporte en Markdown con el estado actual."""


def _num(x, dec=0):
    return "s/d" if x is None else f"{x:,.{dec}f}"


def generar(ctx, alertas, errores):
    l = [f"# Monitor de cobre — {ctx['fecha_hora']}", ""]
    l += ["## Mercado", "",
          "| Indicador | Valor | Var. semanal |", "|---|---|---|",
          f"| TRM (COP/USD) | {_num(ctx.get('trm'), 2)} | {_num(ctx.get('trm_var_semanal'), 2)} % |",
          f"| Cobre (USD/t) — {ctx.get('fuente_cobre', '')} | {_num(ctx.get('cobre_usd_t'), 0)} | {_num(ctx.get('cobre_var_semanal'), 2)} % |",
          ""]
    if ctx.get("ranking"):
        l += ["## Costo puesto en planta por proveedor", "",
              "| # | Proveedor | USD/t | COP/t | Días tránsito |", "|---|---|---|---|---|"]
        for i, r in enumerate(ctx["ranking"], 1):
            l.append(f"| {i} | {r['nombre']} | {_num(r['usd_t'])} | {_num(r['cop_t'])} | {r['dias_transito']} |")
        l.append("")
    if ctx.get("cobertura_dias") is not None:
        l += [f"**Cobertura de inventario:** {ctx['cobertura_dias']} días", ""]
    l += ["## Alertas", ""]
    l += [f"- **{a['nivel']}**: {a['texto'].splitlines()[0]}" for a in alertas] or ["- Sin alertas."]
    l.append("")
    if ctx.get("noticias"):
        l += ["## Noticias relevantes (mayor riesgo primero)", "", "| Riesgo | Título | Fuente |", "|---|---|---|"]
        for n in ctx["noticias"][:15]:
            titulo = n["titulo"].replace("|", "/")
            l.append(f"| {n['riesgo']}/10 | [{titulo}]({n['url']}) | {n['fuente'] or n['origen']} |")
        l.append("")
    if errores:
        l += ["## Fuentes con error", ""] + [f"- {e}" for e in errores] + [""]
    l += ["> Precio COMEX es aproximación a LME. Primas y fletes salen de `config.yaml`: ajústalos a tus cotizaciones.", ""]
    return "\n".join(l)
