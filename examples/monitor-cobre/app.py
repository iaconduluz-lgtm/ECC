"""Tablero del monitor de cobre.  Ejecutar:  streamlit run app.py"""
import hmac
import os
from contextlib import nullcontext
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st

from monitor import __main__ as motor
from monitor import analisis, configuracion, costos, demo, ia, inventario
from monitor.noticias import ICONO

BASE = os.path.dirname(os.path.abspath(__file__))
AZUL, ROJO, GRIS, TINTA2 = "#2a78d6", "#e34948", "#f0efec", "#52514e"
NIVEL = {"URGENTE": st.error, "PELIGRO": st.error, "RIESGO ALTO": st.warning, "RIESGO MEDIO": st.info,
         "ATENCION": st.warning, "OPORTUNIDAD": st.success}
ORDEN_NIVELES = ["Peligro", "Alto", "Medio", "Bajo"]
TONO = {"urgente": st.error, "comprar": st.success, "esperar": st.warning, "normal": st.info}

st.set_page_config(page_title="Monitor de cobre", page_icon="🟠", layout="wide")


def secreto(clave, defecto=None):
    """Lee .streamlit/secrets.toml (local) o los Secrets de Streamlit Cloud; tolera que no existan."""
    try:
        return st.secrets[clave] if clave in st.secrets else defecto
    except Exception:
        return defecto


def revisar_secrets():
    """Si existen Secrets pero tienen un error de formato, Streamlit no lee ninguno (ni la clave de acceso).
    En ese caso se bloquea la app en vez de mostrarla sin protección."""
    try:
        list(st.secrets.keys())
    except Exception as e:
        texto = str(e)
        if "No secrets found" in texto:
            return  # no hay Secrets: uso local
        detalle = texto.split(": ", 1)[-1] if "Error parsing secrets" in texto else type(e).__name__
        st.title("Monitor de cobre")
        st.error("**Los Secrets tienen un error de formato**, así que la app no puede leerlos (tampoco la clave de "
                 f"acceso) y queda bloqueada por seguridad.\n\nDetalle: `{detalle}`\n\n"
                 "Revisa en *Settings → Secrets*: que ninguna sección (lo que va entre `[ ]`) esté repetida, que los "
                 "textos vayan entre comillas y que las listas usen corchetes, p. ej. `ventas = [5.8, 9, 9.2]`.")
        st.stop()


revisar_secrets()


def pedir_clave():
    """Si hay `clave_acceso` en los secrets, pide la clave antes de mostrar nada."""
    esperada = secreto("clave_acceso")
    if not esperada or st.session_state.get("autorizado"):
        return
    st.title("Monitor de cobre")
    intento = st.text_input("Clave de acceso", type="password")
    if intento and hmac.compare_digest(intento.encode(), str(esperada).encode()):
        st.session_state["autorizado"] = True
        st.rerun()
    if intento:
        st.error("Clave incorrecta.")
    st.stop()


pedir_clave()
if secreto("ANTHROPIC_API_KEY"):
    os.environ.setdefault("ANTHROPIC_API_KEY", str(secreto("ANTHROPIC_API_KEY")))


@st.cache_data(ttl=900, show_spinner="Consultando TRM, cobre y noticias…")
def descargar(cfg_noticias, modo_demo, marca):  # `marca` cambia al pulsar Actualizar e invalida la caché
    with demo.activar() if modo_demo else nullcontext():
        datos = motor.descargar({"noticias": cfg_noticias})
    datos["descargado"] = datetime.now().timestamp()
    return datos


def fmt(x, dec=0, pre="", suf=""):
    return "s/d" if x is None else f"{pre}{x:,.{dec}f}{suf}"


def millones(x):
    if x is None:
        return "s/d"
    signo = "+" if x > 0.05e6 else ("-" if x < -0.05e6 else "")
    return f"{signo}${abs(x) / 1e6:,.1f} M"


def pesos_m(x):
    return "s/d" if x is None else f"${x / 1e6:,.1f} M"


def a_df(serie):
    df = pd.DataFrame(serie, columns=["Fecha", "Valor"])
    df["Fecha"] = pd.to_datetime(df["Fecha"])
    return df.sort_values("Fecha")


def linea(df, titulo, unidad, color=AZUL):
    dias = (df["Fecha"].max() - df["Fecha"].min()).days if len(df) else 0
    fmt_x = "%d %b" if dias <= 120 else "%b %Y"
    hover = alt.selection_point(fields=["Fecha"], nearest=True, on="mouseover", empty=False)
    base = alt.Chart(df).encode(
        x=alt.X("Fecha:T", title=None, axis=alt.Axis(format=fmt_x, grid=False, labelOverlap=True)),
        y=alt.Y("Valor:Q", title=unidad, scale=alt.Scale(zero=False), axis=alt.Axis(gridOpacity=0.3)),
    )
    puntos = base.mark_point(size=80, filled=True, color=color, opacity=0).add_params(hover).encode(
        opacity=alt.condition(hover, alt.value(1), alt.value(0)),
        tooltip=[alt.Tooltip("Fecha:T", format="%d %b %Y" if "Mes" not in df else "%b %Y"),
                 alt.Tooltip("Valor:Q", format=",.2f", title=unidad)],
    )
    regla = base.mark_rule(color=TINTA2, strokeDash=[3, 3]).encode(
        opacity=alt.condition(hover, alt.value(0.6), alt.value(0))).transform_filter(hover)
    return (base.mark_line(color=color, strokeWidth=2) + regla + puntos).properties(title=titulo, height=280)


def secciones_secrets():
    """Qué secciones de Secrets ve la app (solo nombres, nunca valores)."""
    aj = secreto("ajustes") or {}
    return [("clave_acceso", secreto("clave_acceso") is not None),
            ("ANTHROPIC_API_KEY", secreto("ANTHROPIC_API_KEY") is not None),
            ("[ajustes.empresa]", "empresa" in aj), ("[ajustes.proveedores]", "proveedores" in aj),
            ("[ajustes.plan_inventario]", "plan_inventario" in aj or secreto("plan_inventario") is not None)]


def texto_secciones():
    secc = secciones_secrets()
    if not any(ok for _, ok in secc):
        return ("**La app no ve ningún Secret.** Revisa en *Manage app → ⋮ → Settings → Secrets* que el texto esté "
                "pegado y que hayas pulsado **Save**; luego *Reboot app*.")
    return ("**Secciones detectadas en tus Secrets** (solo los nombres, nunca los valores): "
            + " · ".join(f"{'✅' if ok else '⬜'} `{n}`" for n, ok in secc))


# ======================= Configuración y plan de inventario =======================
cfg = configuracion.fusionar(configuracion.cargar(BASE), secreto("ajustes"))
if secreto("plan_inventario") and not cfg.get("plan_inventario"):  # también se acepta sin el prefijo "ajustes."
    cfg["plan_inventario"] = configuracion.fusionar({}, secreto("plan_inventario"))
EN_LA_NUBE = secreto("ajustes") is not None or secreto("clave_acceso") is not None

# El plan se edita en la pestaña Inventario; sus cambios se aplican aquí, antes de calcular nada.
PLAN_ORIGINAL = configuracion.fusionar({}, cfg.get("plan_inventario") or {})
TIENE_PLAN = bool(PLAN_ORIGINAL)
plan = dict(PLAN_ORIGINAL) if TIENE_PLAN else {"anio": datetime.now().year, "inventario_inicial": 0}


def plan_a_df(p):
    reales = list(p.get("cierres_reales") or [])
    df = pd.DataFrame({c: [f[c] for f in inventario.proyectar(p)] for c in inventario.CAMPOS}, index=inventario.MESES)
    df["cierre_real"] = [float(reales[i]) if i < len(reales) else None for i in range(12)]
    return df


TABLA_PLAN = plan_a_df(plan)
edicion = st.session_state.get("editor_plan", {}).get("edited_rows", {})
inicial_editado = st.session_state.get("inv_inicial")
if edicion or (inicial_editado is not None and inicial_editado != float(plan.get("inventario_inicial") or 0)):
    df_plan = TABLA_PLAN.copy()
    for fila, cambios in edicion.items():
        for k, v in cambios.items():
            df_plan.iloc[int(fila), df_plan.columns.get_loc(k)] = v
    plan.update({c: [float(x) if pd.notna(x) else 0.0 for x in df_plan[c]] for c in inventario.CAMPOS})
    reales = []
    for v in df_plan["cierre_real"]:
        if v is None or pd.isna(v):
            break
        reales.append(float(v))
    plan["cierres_reales"] = reales
    if inicial_editado is not None:
        plan["inventario_inicial"] = inicial_editado
    TIENE_PLAN = True
cfg["plan_inventario"] = plan if TIENE_PLAN else None
SITUACION = inventario.situacion_actual(plan) if TIENE_PLAN else None

# ======================= Barra lateral =======================
with st.sidebar:
    st.header("Controles")
    modo_demo = st.toggle("Modo demostración (datos ficticios)", value=os.environ.get("MONITOR_DEMO") == "1",
                          help="Úsalo para probar el tablero sin internet. Los números NO son reales.")
    if st.button("🔄 Actualizar ahora", width="stretch"):
        st.session_state["marca"] = datetime.now().isoformat()

    st.subheader("Tu empresa")
    emp = cfg["empresa"]
    if SITUACION:
        emp["inventario_toneladas"], emp["consumo_mensual_toneladas"] = SITUACION["inventario"], SITUACION["consumo_mensual"]
    emp["inventario_toneladas"] = st.number_input("Inventario actual (t)", 0.0, value=max(0.0, float(emp["inventario_toneladas"])), step=1.0)
    emp["consumo_mensual_toneladas"] = st.number_input("Consumo mensual (t)", 0.0, value=max(0.0, float(emp["consumo_mensual_toneladas"])), step=1.0)
    if SITUACION:
        st.caption(f"Tomados de tu plan: inventario al iniciar {SITUACION['mes'].lower()} y consumo promedio de "
                   "este mes y los 2 siguientes. Puedes cambiarlos para simular.")
    claves = list(cfg["proveedores"])
    emp["proveedor_actual"] = st.selectbox("Proveedor actual", claves, index=claves.index(emp["proveedor_actual"]),
                                           format_func=lambda k: cfg["proveedores"][k]["nombre"])

    st.subheader("Precio LME oficial (opcional)")
    manual = st.number_input("USD/t (0 = usar mercado)", 0.0, value=float(cfg["cobre"].get("precio_manual_usd_t") or 0), step=10.0)
    cfg["cobre"]["precio_manual_usd_t"] = manual or None

    st.subheader("TRM del día (opcional)")
    trm_manual = st.number_input("COP por USD (0 = automática)", 0.0, value=float(cfg.get("trm_manual") or 0), step=1.0,
                                 help="Úsalo si la TRM automática no carga. La TRM del día está en la página de la "
                                      "Superintendencia Financiera o en tu banco.")
    cfg["trm_manual"] = trm_manual or None

# Las ediciones de la pestaña Ajustes se aplican antes de calcular (Streamlit corre de arriba a abajo).
COLS_PROV = ["nombre", "prima_usd_t", "flete_usd_t", "seguro_usd_t", "arancel_pct", "dias_transito"]
tabla_prov = pd.DataFrame(cfg["proveedores"]).T[COLS_PROV]
for fila, cambios in st.session_state.get("editor_prov", {}).get("edited_rows", {}).items():
    cfg["proveedores"][tabla_prov.index[int(fila)]].update({k: float(v) for k, v in cambios.items() if k != "nombre"})

datos = descargar(cfg["noticias"], modo_demo, st.session_state.get("marca"))
# Si faltó la TRM o el cobre, no esperar 15 minutos: reintentar a los 2 minutos.
if (not datos["serie_trm"] or not datos["cobre"]) and datetime.now().timestamp() - datos["descargado"] > 120:
    st.session_state["marca"] = datetime.now().isoformat()
    st.rerun()
ctx, todas, errores = motor.calcular(datos, cfg)
prov_actual = cfg["proveedores"][emp["proveedor_actual"]]

# ======================= Encabezado =======================
st.title("Monitor de cobre")
st.caption(f"Última consulta: {ctx['fecha_hora']} · Cobre: {ctx.get('fuente_cobre', 's/d')} · "
           f"TRM: {ctx.get('fuente_trm') or 's/d'}")
if not ctx.get("trm") or not ctx.get("cobre_usd_t"):
    st.warning("Falta " + " y ".join(x for x, ok in (("la TRM", ctx.get("trm")), ("el precio del cobre", ctx.get("cobre_usd_t")))
                                     if not ok) + ". El tablero vuelve a intentar solo en unos 2 minutos, o pulsa "
               "**Actualizar ahora**. Mientras tanto puedes escribir el valor en la barra lateral. "
               "El detalle está al final de la página.")
if modo_demo:
    st.warning("**Modo demostración:** los datos son ficticios, solo para ver cómo funciona el tablero.")

rec = ctx["recomendacion"]
TONO[rec["tono"]](f"### Recomendación: {rec['accion']}\n" + "\n".join(f"- {r}" for r in rec["razones"])
                  + ("\n- **Considera cotizar con un proveedor alternativo** (Chile/México) por riesgo en Perú."
                     if rec["diversificar"] else ""))
st.caption("Recomendación automática por reglas (precio vs. promedios, TRM, noticias e inventario). "
           "Es un apoyo para decidir, no asesoría financiera.")

t_res, t_inv, t_graf, t_esc, t_not, t_falta, t_aj = st.tabs(
    ["📊 Resumen", "📦 Inventario", "📈 Gráficos", "🧮 Escenarios", "📰 Noticias e IA", "✅ Qué falta", "✏️ Ajustes"])

# ======================= Inventario =======================
with t_inv:
    minimo = emp["cobertura_minima_dias"]
    if not TIENE_PLAN:
        st.info("Todavía no hay plan de inventario. Llena la tabla de abajo (toneladas por mes) y copia el texto "
                "que aparece al final en *Settings → Secrets* para que quede guardado.")
        st.markdown(texto_secciones())
    else:
        filas = ctx.get("plan") or []
        sit = ctx.get("situacion_plan")
        pend = ctx.get("compras_pendientes") or []
        i1, i2, i3, i4 = st.columns(4)
        if sit:
            i1.metric(f"Inventario al iniciar {sit['mes'].lower()}", f"{sit['inventario']:g} t")
            i2.metric("Consumo promedio próximo", f"{sit['consumo_mensual']:g} t/mes")
        i3.metric("Cierre de diciembre (proyectado)", f"{filas[-1]['final']:g} t",
                  f"{filas[-1]['dias_inventario']} días" if filas[-1]["dias_inventario"] is not None else None,
                  delta_color="off", delta_arrow="off")
        if pend:
            i4.metric(f"Próxima compra ({pend[0]['mes'].lower()})", f"{pend[0]['toneladas']:g} t",
                      pesos_m(pend[0]["costo_estimado_cop"]) if pend[0].get("costo_estimado_cop") else None,
                      delta_color="off", delta_arrow="off")
        criticos = ctx.get("meses_criticos") or []
        negativos = [f for f in filas if f["final"] < 0]
        if negativos:
            st.error("**Te quedarías sin material:** el plan proyecta inventario negativo en "
                     + ", ".join(f"**{f['mes']}** ({f['final']:g} t)" for f in negativos)
                     + ". Revisa las compras o las ventas de esos meses.")
        if criticos:
            st.warning("Meses con inventario por debajo del mínimo de "
                       f"{minimo} días: " + ", ".join(f"**{f['mes']}** ({f['dias_inventario']} días)" for f in criticos))
        else:
            st.success(f"De aquí a diciembre ningún mes baja del mínimo de {minimo} días de inventario.")

        dfp = pd.DataFrame(filas)
        base_i = alt.Chart(dfp).encode(
            x=alt.X("mes:N", sort=inventario.MESES, title=None, axis=alt.Axis(labelAngle=0, labelExpr="slice(datum.label, 0, 3)")),
            tooltip=[alt.Tooltip("mes:N", title="Mes"), alt.Tooltip("tipo:N", title="Dato"),
                     alt.Tooltip("final:Q", title="Inventario final (t)", format=",.1f"),
                     alt.Tooltip("dias_inventario:Q", title="Días de inventario"),
                     alt.Tooltip("compras_importacion:Q", title="Importación (t)"), alt.Tooltip("ventas:Q", title="Ventas (t)")])
        barras_i = base_i.mark_bar(cornerRadiusEnd=4, size=26).encode(
            y=alt.Y("dias_inventario:Q", title="Días de inventario al cierre del mes", axis=alt.Axis(gridOpacity=0.3)),
            color=alt.Color("tipo:N", scale=alt.Scale(domain=["Real", "Proyectado"], range=[AZUL, "#eb6834"]),
                            legend=alt.Legend(title=None, orient="top")))
        regla_i = alt.Chart(pd.DataFrame({"y": [minimo]})).mark_rule(color=TINTA2, strokeDash=[4, 4]).encode(y="y:Q")
        st.altair_chart((barras_i + regla_i).properties(height=300), width="stretch")
        st.caption(f"Línea punteada: mínimo de {minimo} días de inventario.")

        tabla = dfp.rename(columns={"mes": "Mes", "tipo": "Dato", "inicial": "Inicial", "compras_importacion": "Importación",
                                    "compra_nacional": "Nacional", "producto_terminado": "PT", "ventas": "Ventas",
                                    "ajuste": "Ajuste", "final": "Final", "meses_inventario": "Meses inv.",
                                    "dias_inventario": "Días inv.", "diferencia": "Dif. vs cálculo"})
        st.dataframe(tabla[["Mes", "Dato", "Inicial", "Importación", "Nacional", "PT", "Ventas", "Ajuste", "Final",
                            "Meses inv.", "Días inv.", "Dif. vs cálculo"]], hide_index=True, width="stretch")
        st.caption("Final = inicial + importación + nacional + PT − ventas + ajuste. En los meses *Real* se usa tu cierre "
                   "real; *Dif. vs cálculo* muestra cuánto difiere de la fórmula (útil para encontrar errores en la hoja).")

        if pend:
            st.subheader("Compras pendientes y su riesgo de precio")
            dpend = pd.DataFrame(pend)
            for c, fn in (("costo_estimado_cop", pesos_m), ("si_cobre_sube_5pct", millones), ("si_trm_sube_5pct", millones)):
                if c in dpend:
                    dpend[c] = dpend[c].map(fn)
            st.dataframe(dpend.rename(columns={"mes": "Mes", "toneladas": "Toneladas", "costo_estimado_cop": "Costo estimado",
                                               "si_cobre_sube_5pct": "Si el cobre sube 5 %", "si_trm_sube_5pct": "Si la TRM sube 5 %"}),
                         hide_index=True, width="stretch")
            st.caption(f"Costo con el precio de hoy y el proveedor {prov_actual['nombre']} (primas y fletes de *Ajustes*).")

    with st.expander("✏️ Editar el plan de inventario", expanded=not TIENE_PLAN):
        st.number_input("Inventario inicial de enero (t)", 0.0, value=float(PLAN_ORIGINAL.get("inventario_inicial") or 0),
                        step=0.1, key="inv_inicial")
        st.data_editor(TABLA_PLAN, key="editor_plan", width="stretch", column_config={
            "compras_importacion": st.column_config.NumberColumn("Compras importación (t)", format="%.2f"),
            "compra_nacional": st.column_config.NumberColumn("Compra nacional (t)", format="%.2f"),
            "producto_terminado": st.column_config.NumberColumn("PT (t)", format="%.3f"),
            "ventas": st.column_config.NumberColumn("Ventas (t)", format="%.2f"),
            "ajuste": st.column_config.NumberColumn("Ajuste (t)", format="%.2f"),
            "cierre_real": st.column_config.NumberColumn("Cierre real (t)", format="%.2f",
                                                         help="Solo meses ya cerrados, en orden desde enero. Vacío = proyectar.")})
        st.caption("Los cambios se ven al instante en todo el tablero. Para guardarlos de forma permanente, copia este "
                   "texto en *Settings → Secrets* de Streamlit (reemplaza la sección `[ajustes.plan_inventario]` si ya existe):")
        st.code(inventario.a_toml(plan), language="toml")

# ======================= Resumen =======================
with t_res:
    ranking = ctx.get("ranking") or []
    mejor = ranking[0] if ranking else None
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("TRM (COP por USD)", fmt(ctx.get("trm"), 2, "$"),
              None if ctx.get("trm_var_semanal") is None else f"{ctx['trm_var_semanal']:+.2f} % semana", delta_color="inverse")
    c2.metric("Cobre (USD por tonelada)", fmt(ctx.get("cobre_usd_t"), 0, "$"),
              None if ctx.get("cobre_var_semanal") is None else f"{ctx['cobre_var_semanal']:+.2f} % semana", delta_color="inverse")
    c3.metric("Más barato puesto en planta", mejor["nombre"].split(" (")[0] if mejor else "s/d",
              fmt(mejor["cop_t"], 0, "$", " COP/t") if mejor else None, delta_color="off", delta_arrow="off")
    c4.metric("Inventario alcanza para", fmt(ctx.get("cobertura_dias"), 0, suf=" días"),
              f"mínimo {emp['cobertura_minima_dias']} días", delta_color="off", delta_arrow="off")

    st.subheader("Alertas")
    if not todas:
        st.info("Sin alertas. Mercado y suministro dentro de lo normal.")
    for a in todas:
        NIVEL.get(a["nivel"], st.info)(f"**{a['nivel']}** — {a['texto']}")

    st.subheader("Costo puesto en planta por proveedor")
    if ranking:
        df = pd.DataFrame(ranking)
        df["Estado"] = [" · ".join(e for e, ok in (("Más barato", i == 0), ("Actual", c == emp["proveedor_actual"])) if ok)
                        for i, c in enumerate(df["clave"])]
        df["extra"] = df["cop_t"] - df["cop_t"].iloc[0]
        df["Proveedor"] = df["nombre"].str.split(" \\(").str[0]
        df["USD/t"] = df["usd_t"].map(lambda x: f"${x:,.0f}")
        df["COP/t"] = df["cop_t"].map(lambda x: f"${x:,.0f}")
        df["sobrecosto"] = df["extra"].map(lambda x: f"+${x:,.0f}" if x else "—")
        base_b = alt.Chart(df).encode(
            x=alt.X("extra:Q", title="Sobrecosto vs. el más barato (COP por tonelada)", axis=alt.Axis(format="~s", gridOpacity=0.3)),
            y=alt.Y("Proveedor:N", title=None, sort=None),
            tooltip=["Proveedor", "COP/t", "USD/t", alt.Tooltip("sobrecosto:N", title="Sobrecosto"),
                     alt.Tooltip("dias_transito:Q", title="Días tránsito")])
        barras = base_b.mark_bar(color=AZUL, cornerRadiusEnd=4, height=22) + base_b.mark_text(
            align="left", dx=6, color=TINTA2).encode(text="sobrecosto:N")
        p1, p2 = st.columns(2)
        p1.altair_chart(barras.properties(height=45 * len(df) + 40), width="stretch")
        p2.dataframe(df[["Proveedor", "COP/t", "USD/t", "dias_transito", "Estado"]], hide_index=True, width="stretch",
                     column_config={"dias_transito": "Días"})
    else:
        faltan = [(x, campo) for x, campo, ok in (("el precio del cobre", "Precio LME oficial", ctx.get("cobre_usd_t")),
                                                   ("la TRM", "TRM del día", ctx.get("trm"))) if not ok]
        st.warning("No se puede calcular porque falta " + " y ".join(x for x, _ in faltan) + ". Mientras tanto, "
                   "escríbelo en " + " y ".join(f"**{c}**" for _, c in faltan) + " (barra lateral) y el cálculo "
                   "aparece al instante.")

# ======================= Gráficos =======================
with t_graf:
    serie_cu, serie_trm = ctx.get("serie_cobre") or [], ctx.get("serie_trm") or []
    fechas = [f for f, _ in serie_cu + serie_trm]
    if not fechas:
        st.info("Todavía no hay histórico disponible.")
    else:
        g1, g2 = st.columns([3, 2])
        periodo = g1.radio("Periodo", ["3 meses", "6 meses", "1 año", "3 años", "5 años", "Elegir meses"],
                           index=2, horizontal=True)
        vista = g2.radio("Ver", ["Diario", "Promedio mensual"], horizontal=True)
        fin = max(fechas)
        if periodo == "Elegir meses":
            meses = pd.period_range(min(fechas), fin, freq="M").strftime("%Y-%m").tolist()
            desde_m, hasta_m = st.select_slider("Meses", options=meses, value=(meses[max(0, len(meses) - 12)], meses[-1]),
                                                format_func=lambda m: pd.Period(m).strftime("%b %Y"))
            desde = pd.Period(desde_m).start_time.date()
            fin = pd.Period(hasta_m).end_time.date()
        else:
            dias = {"3 meses": 92, "6 meses": 183, "1 año": 366, "3 años": 1096, "5 años": 1827}[periodo]
            desde = fin - timedelta(days=dias)

        def recorte(serie):
            df = a_df([(f, v) for f, v in serie if desde <= f <= fin])
            if vista == "Promedio mensual" and len(df):
                df = df.set_index("Fecha").resample("MS").mean().reset_index()
                df["Mes"] = df["Fecha"].dt.strftime("%Y-%m")
            return df

        df_cu, df_trm = recorte(serie_cu), recorte(serie_trm)
        c1, c2 = st.columns(2)
        with c1:
            if len(df_cu):
                st.altair_chart(linea(df_cu, "Cobre (COMEX/LME)", "USD/t"), width="stretch")
            else:
                st.info("Sin histórico de cobre: ninguna fuente respondió (ver detalle al final).")
        with c2:
            if len(df_trm):
                st.altair_chart(linea(df_trm, "TRM", "COP por USD"), width="stretch")

        # Costo estimado del proveedor actual en el tiempo (cobre x TRM del mismo día)
        if len(df_cu) and len(df_trm):
            unido = pd.merge_asof(df_cu.sort_values("Fecha"), df_trm.sort_values("Fecha"), on="Fecha", suffixes=("_cu", "_trm"))
            unido = unido.dropna()
            unido["Valor"] = [costos.costo_proveedor(cu, tr, prov_actual)["cop_t"]
                              for cu, tr in zip(unido["Valor_cu"], unido["Valor_trm"])]
            st.altair_chart(linea(unido[["Fecha", "Valor"] + (["Mes"] if "Mes" in unido else [])],
                                  f"Costo estimado puesto en planta — {prov_actual['nombre']} (con primas y fletes de hoy)",
                                  "COP por tonelada"), width="stretch")

            st.subheader("Promedio por mes")
            mensual = pd.DataFrame({
                "Mes": [m for m, _ in analisis.promedio_mensual([(f, v) for f, v in serie_cu if desde <= f <= fin])]})
            cu_m = dict(analisis.promedio_mensual([(f, v) for f, v in serie_cu if desde <= f <= fin]))
            tr_m = dict(analisis.promedio_mensual([(f, v) for f, v in serie_trm if desde <= f <= fin]))
            mensual["Cobre USD/t"] = mensual["Mes"].map(cu_m)
            mensual["TRM"] = mensual["Mes"].map(tr_m)
            mensual = mensual.dropna()
            mensual["Cobre USD/t"] = mensual["Cobre USD/t"].round(0)
            mensual["TRM"] = mensual["TRM"].round(2)
            mensual["Costo COP/t"] = [costos.costo_proveedor(c, t, prov_actual)["cop_t"]
                                      for c, t in zip(mensual["Cobre USD/t"], mensual["TRM"])]
            mensual["Var. costo vs. mes anterior"] = mensual["Costo COP/t"].pct_change().mul(100).round(1)
            mensual = mensual.iloc[::-1]
            st.dataframe(mensual, hide_index=True, width="stretch", column_config={
                "Cobre USD/t": st.column_config.NumberColumn(format="localized"),
                "TRM": st.column_config.NumberColumn(format="localized"),
                "Costo COP/t": st.column_config.NumberColumn(format="localized"),
                "Var. costo vs. mes anterior": st.column_config.NumberColumn(format="%+.1f %%")})
            st.download_button("⬇️ Descargar tabla (CSV)", mensual.to_csv(index=False).encode("utf-8"),
                               "promedio_mensual_cobre_trm.csv", "text/csv")

# ======================= Escenarios =======================
with t_esc:
    sens = ctx.get("sensibilidad")
    if not sens:
        st.info("Se necesitan la TRM y el precio del cobre para calcular escenarios.")
    else:
        consumo = emp.get("consumo_mensual_toneladas") or 0
        st.markdown(f"Con tu consumo de **{consumo:,.0f} t/mes** y el proveedor **{prov_actual['nombre']}**:")
        s1, s2 = st.columns(2)
        s1.metric("Si el cobre sube 1 %", millones(sens["cobre_1pct_mes"]) + " al mes",
                  f"+${sens['cobre_1pct_cop_t']:,.0f} por tonelada", delta_color="inverse")
        s2.metric("Si la TRM sube 1 %", millones(sens["trm_1pct_mes"]) + " al mes",
                  f"+${sens['trm_1pct_cop_t']:,.0f} por tonelada", delta_color="inverse")

        st.subheader("Simulador")
        a, b = st.columns(2)
        sim_cu = a.slider("¿Cuánto cambia el cobre?", -20, 20, 5, format="%d %%")
        sim_tr = b.slider("¿Cuánto cambia la TRM?", -20, 20, 0, format="%d %%")
        hoy = costos.costo_proveedor(ctx["cobre_usd_t"], ctx["trm"], prov_actual)["cop_t"]
        nuevo = costos.costo_proveedor(ctx["cobre_usd_t"] * (1 + sim_cu / 100), ctx["trm"] * (1 + sim_tr / 100),
                                                prov_actual)["cop_t"]
        delta = nuevo - hoy
        inv = emp.get("inventario_toneladas") or 0
        r1, r2, r3 = st.columns(3)
        r1.metric("Nuevo costo por tonelada", fmt(nuevo, 0, "$", " COP"), f"{delta:+,.0f}", delta_color="inverse")
        r2.metric("Impacto en tu gasto mensual", millones(delta * consumo), delta_color="off")
        r3.metric("Cambio de valor de tu inventario", millones(delta * inv),
                  help="Si el costo sube, el cobre que ya tienes en bodega vale más (y al revés).", delta_color="off")
        if delta > 0:
            st.write(f"➡️ Comprar **antes** de esa subida te ahorraría unos **{millones(delta * consumo)}** por cada mes de consumo que adelantes.")
        elif delta < 0:
            st.write(f"➡️ Si esperas y se da esa baja, ahorrarías unos **{millones(-delta * consumo)}** por mes de consumo.")

        st.subheader("Mapa de escenarios: cambio en tu gasto mensual")
        esc = pd.DataFrame(analisis.escenarios(ctx["cobre_usd_t"], ctx["trm"], prov_actual, consumo))
        esc["Cobre"] = esc["cobre_pct"].map(lambda x: f"{x:+d} %")
        esc["TRM"] = esc["trm_pct"].map(lambda x: f"{x:+d} %")
        esc["texto"] = esc["impacto_mensual_cop"].map(millones)
        lim = max(1, esc["impacto_mensual_cop"].abs().max())
        orden = [f"{x:+d} %" for x in analisis.PASOS]
        base_h = alt.Chart(esc).encode(
            x=alt.X("Cobre:N", sort=orden, title="Cambio del precio del cobre", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("TRM:N", sort=list(reversed(orden)), title="Cambio de la TRM"),
            tooltip=["Cobre", "TRM", alt.Tooltip("texto:N", title="Gasto mensual"),
                     alt.Tooltip("costo_cop_t:Q", format=",.0f", title="Costo COP/t")])
        calor = base_h.mark_rect(stroke="white", strokeWidth=2, cornerRadius=4).encode(
            color=alt.Color("impacto_mensual_cop:Q", legend=alt.Legend(title="COP/mes", format="~s"),
                            scale=alt.Scale(domain=[-lim, 0, lim], range=[AZUL, GRIS, ROJO], interpolate="rgb")))
        etiquetas = base_h.mark_text(fontSize=12).encode(
            text="texto:N",
            color=alt.condition(f"abs(datum.impacto_mensual_cop) > {lim * 0.55}", alt.value("white"), alt.value("#0b0b0b")))
        st.altair_chart((calor + etiquetas).properties(height=320), width="stretch")
        st.caption("Rojo = gastas más al mes; azul = gastas menos. Supone primas, fletes y consumo constantes.")

# ======================= Noticias e IA =======================
with t_not:
    noticias = ctx.get("noticias") or []
    st.subheader("Nivel de riesgo de las noticias")
    cols = st.columns(4)
    for col, nv in zip(cols, ORDEN_NIVELES):
        col.metric(f"{ICONO[nv]} {nv}", sum(1 for n in noticias if n.get("nivel") == nv))
    with st.expander("¿Qué significa cada nivel?"):
        st.markdown(
            "| Nivel | Puntaje | Significa | Qué hacer |\n|---|---|---|---|\n"
            "| 🟢 Bajo | 1–3 | Noticia del sector sin problema de suministro (o buena noticia) | Solo informativo |\n"
            "| 🟡 Medio | 4–5 | Posible problema aún no confirmado: amenaza de huelga, propuesta de impuesto | Vigilar; preguntar al proveedor |\n"
            "| 🟠 Alto | 6–7 | Problema activo que puede afectar envíos: huelga, bloqueo, paro en puerto | Confirmar tu embarque; cotizar alternativo |\n"
            "| 🔴 Peligro | 8–10 | Interrupción grave o prolongada, o problema serio en tu proveedor | Activar proveedor alternativo; asegurar inventario |\n\n"
            "Suben el nivel: que mencione a **tu proveedor** (Elcope), que sea un **hecho** (\"inicia\", \"paraliza\") y "
            "que dure **varios días**. Lo bajan: que sea solo una **amenaza o propuesta** (máximo Medio) o una "
            "**buena noticia** (\"levantan el bloqueo\", \"reanuda\"). Las noticias de tu proveedor generan alerta desde Medio.\n\n"
            "**Región:** Perú y Colombia cubren tu cadena directa (Elcope → Callao → Buenaventura → Cali). "
            "Las noticias del **resto del mundo** llegan como máximo a **Alto**: mueven el precio, pero no cortan tu suministro.")

    st.subheader("Análisis automático de noticias")
    grupos = analisis.resumen_noticias(noticias)
    if grupos:
        st.dataframe(pd.DataFrame(grupos)[["categoria", "cantidad", "riesgo_max", "impacto", "ejemplo"]], hide_index=True,
                     width="stretch", column_config={
                         "categoria": "Tema", "cantidad": "Noticias",
                         "riesgo_max": st.column_config.ProgressColumn("Riesgo máx.", min_value=0, max_value=10, format="%d/10"),
                         "impacto": st.column_config.TextColumn("Qué puede significar para ti", width="large"),
                         "ejemplo": st.column_config.TextColumn("Noticia más relevante", width="large")})

    st.subheader("Análisis con inteligencia artificial")
    if not ia.disponible():
        st.info("Para activar el análisis con IA agrega tu clave `ANTHROPIC_API_KEY` en los Secrets "
                "(ver pestaña **Qué falta**). Cuesta unos pocos centavos de dólar por análisis.")
    elif not noticias:
        st.info("No hay noticias para analizar.")
    else:
        if st.button("🤖 Analizar noticias e impacto con IA"):
            with st.spinner("La IA está analizando las noticias y los números (puede tardar hasta un minuto)…"):
                try:
                    st.session_state["ia"] = (ctx["fecha_hora"], ia.analizar(ctx, cfg, sens, rec))
                except Exception as e:
                    st.error(f"No se pudo hacer el análisis: {e}")
        if "ia" in st.session_state:
            cuando, r = st.session_state["ia"]
            st.caption(f"Análisis generado con datos de {cuando}")
            m1, m2 = st.columns(2)
            m1.metric("Presión sobre el precio del cobre", r.presion_precio_cobre.capitalize())
            m2.metric("Riesgo de suministro desde Perú", r.riesgo_suministro_peru.capitalize())
            st.markdown(f"**Resumen:** {r.resumen}")
            st.success(f"**Recomendación:** {r.recomendacion}")
            st.markdown("**Acciones para esta semana:**\n" + "\n".join(f"1. {x}" for x in r.acciones))
            e1, e2 = st.columns(2)
            e1.markdown(f"**Si el cobre sigue subiendo:** {r.si_sube_cobre}")
            e2.markdown(f"**Si la TRM sigue subiendo:** {r.si_sube_trm}")
            st.markdown(f"**Proveedores alternativos:** {r.proveedores_alternativos}")
            if r.noticias_clave:
                st.dataframe(pd.DataFrame([n.model_dump() for n in r.noticias_clave]), hide_index=True, width="stretch",
                             column_config={"titulo": "Noticia", "nivel": "Nivel (IA)",
                                            "por_que_importa": st.column_config.TextColumn("Por qué importa", width="large"),
                                            "efecto_precio": "Precio", "afecta_suministro_peru": "¿Afecta Perú?"})
            st.caption("Análisis generado por IA: puede equivocarse. Verifica las noticias antes de decidir.")

    st.subheader("Todas las noticias")
    if noticias:
        dfn = pd.DataFrame(noticias)
        dfn["Tema"] = [analisis.clasificar(n)[0] for n in noticias]
        dfn["Nivel"] = dfn["nivel"].map(lambda nv: f"{ICONO.get(nv, '')} {nv}")
        dfn["Proveedor"] = dfn["afecta_proveedor"].map(lambda x: "⚠️ Sí" if x else "")
        dfn["Región"] = dfn["region"].map({"Perú": "🇵🇪 Perú", "Colombia": "🇨🇴 Colombia", "Mundo": "🌎 Mundo"})
        f1, f2, f3 = st.columns([2, 2, 2])
        ver_niveles = f1.multiselect("Mostrar niveles", ORDEN_NIVELES, default=ORDEN_NIVELES,
                                     format_func=lambda nv: f"{ICONO[nv]} {nv}")
        ver_regiones = f2.multiselect("Mostrar regiones", ["Perú", "Colombia", "Mundo"], default=["Perú", "Colombia", "Mundo"])
        with f3:
            orden_n = st.radio("Ordenar", ["Mayor riesgo primero", "Más recientes primero"], horizontal=True)
        dfn = dfn[dfn["nivel"].isin(ver_niveles) & dfn["region"].isin(ver_regiones)]
        if orden_n == "Más recientes primero":
            dfn = dfn.sort_values("fecha", ascending=False, na_position="last")
        dfn["Fecha"] = dfn["fecha"].map(lambda d: d.astimezone(ZoneInfo("America/Bogota")).strftime("%d %b %H:%M")
                                        if d is not None and not pd.isna(d) else "")
        st.caption(f"{len(dfn)} de {len(noticias)} noticias de los últimos {round(cfg['noticias'].get('max_horas', 72) / 24)} días. "
                   "Proveedor = la noticia menciona a tu proveedor directo.")
        st.dataframe(dfn[["Nivel", "riesgo", "Región", "Proveedor", "certeza", "Tema", "titulo", "fuente", "Fecha", "url"]],
                     hide_index=True, width="stretch",
                     column_config={"riesgo": st.column_config.ProgressColumn("Riesgo", min_value=0, max_value=10, format="%d/10"),
                                    "certeza": "Certeza", "titulo": st.column_config.TextColumn("Título", width="large"),
                                    "fuente": "Fuente", "url": st.column_config.LinkColumn("Abrir", display_text="ver")})
    else:
        st.info("No hay noticias relevantes en los últimos días.")

# ======================= Qué falta =======================
with t_falta:
    st.markdown("Lo que necesita el programa para que sus cálculos y recomendaciones sean precisos:")
    costos_reales = secreto("ajustes") is not None or os.path.exists(configuracion.ruta_ajustes(BASE)) \
        or bool(os.environ.get("MONITOR_AJUSTES"))
    pendientes = [
        (costos_reales, "Tus primas, fletes y seguros reales por proveedor",
         "Pídelos a tus proveedores o a tu agente de carga, en USD por tonelada, y ponlos en Secrets → `[ajustes.proveedores.*]`."),
        (TIENE_PLAN, "Plan de inventario mensual",
         "Llénalo en la pestaña **Inventario** y copia el texto que genera en Secrets."),
        (costos_reales, "Inventario y consumo mensual reales", "En Secrets → `[ajustes.empresa]` (o en la barra lateral para simular)."),
        (bool(ctx.get("cobre_usd_t")), "Precio del cobre llegando", "Si ninguna fuente responde, escribe el precio LME del día en la barra lateral."),
        (bool(manual), "Precio LME oficial de tu broker o proveedor (opcional, el más exacto)",
         "El precio de mercado gratuito es una aproximación. Si tu contrato usa LME, pide el cierre oficial diario."),
        (ia.disponible(), "Clave de IA para analizar noticias (opcional)",
         "Crea una clave en console.anthropic.com → API Keys y agrégala en Secrets como `ANTHROPIC_API_KEY = \"...\"`."),
        (bool(ctx.get("noticias")), "Noticias llegando", "Si no aparecen, revisa *fuentes no respondieron* al final de la página."),
    ]
    for ok, titulo, como in pendientes:
        st.markdown(f"{'✅' if ok else '⬜'} **{titulo}**" + ("" if ok else f"  \n&nbsp;&nbsp;&nbsp;&nbsp;{como}"))
    st.markdown(texto_secciones())
    st.markdown("**Para decisiones aún mejores (opcional):** fecha y tamaño de tus próximos pedidos, si tus contratos "
                "fijan precio (precio fijo o promedio LME del mes), plazo de pago en dólares, y si tienes coberturas "
                "cambiarias con tu banco.")

# ======================= Ajustes =======================
with t_aj:
    st.markdown("**Costos por proveedor (USD por tonelada)**")
    st.data_editor(tabla_prov, key="editor_prov", width="stretch", disabled=["nombre"],
                   column_config={"nombre": "Proveedor", "prima_usd_t": "Prima", "flete_usd_t": "Flete",
                                  "seguro_usd_t": "Seguro", "arancel_pct": "Arancel %", "dias_transito": "Días tránsito"})
    st.caption("Los cambios se aplican al instante en todas las pestañas.")
    if EN_LA_NUBE:
        st.caption("Versión en internet: los cambios sirven para simular. Para dejarlos fijos, cámbialos en "
                   "*Settings → Secrets* de Streamlit Cloud (sección `[ajustes]`).")
    elif st.button("💾 Guardar mis valores"):
        configuracion.guardar_ajustes(BASE, {"empresa": emp, "cobre": cfg["cobre"], "proveedores": cfg["proveedores"],
                                             **({"plan_inventario": plan} if TIENE_PLAN else {})})
        st.success("Guardado en data/ajustes.yaml. Las alertas automáticas usarán estos valores.")

# ======================= Pie =======================
ruta_hist = os.path.join(BASE, "data", "historico.csv")
if os.path.exists(ruta_hist):
    with st.expander("Histórico de consultas automáticas"):
        st.dataframe(pd.read_csv(ruta_hist).iloc[::-1], hide_index=True, width="stretch")
if errores:
    with st.expander(f"⚠️ {len(errores)} fuente(s) no respondieron", expanded=not ctx.get("cobre_usd_t")):
        for e in errores:
            st.write("-", e)
