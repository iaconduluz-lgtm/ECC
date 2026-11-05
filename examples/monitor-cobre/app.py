"""Tablero del monitor de cobre.  Ejecutar:  streamlit run app.py"""
import hmac
import os
from contextlib import nullcontext
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

from monitor import __main__ as motor
from monitor import configuracion, demo

BASE = os.path.dirname(os.path.abspath(__file__))
AZUL = "#2a78d6"
NIVEL = {"URGENTE": st.error, "RIESGO SUMINISTRO": st.error, "ATENCION": st.warning, "OPORTUNIDAD": st.success}

st.set_page_config(page_title="Monitor de cobre", page_icon="🟠", layout="wide")


def secreto(clave, defecto=None):
    """Lee .streamlit/secrets.toml (local) o los Secrets de Streamlit Cloud; tolera que no existan."""
    try:
        return st.secrets[clave] if clave in st.secrets else defecto
    except Exception:
        return defecto


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


@st.cache_data(ttl=900, show_spinner="Consultando TRM, cobre y noticias…")
def consultar(cfg, modo_demo, marca):  # `marca` cambia al pulsar Actualizar e invalida la caché
    with demo.activar() if modo_demo else nullcontext():
        ctx, todas, _, errores, _ = motor.ejecutar(cfg, BASE, enviar=False, guardar=False)
    return ctx, todas, errores


def fmt(x, dec=0, pre="", suf=""):
    return "s/d" if x is None else f"{pre}{x:,.{dec}f}{suf}"


def linea(serie, titulo, unidad):
    df = pd.DataFrame(serie, columns=["Fecha", "Valor"])
    df["Fecha"] = pd.to_datetime(df["Fecha"])
    hover = alt.selection_point(fields=["Fecha"], nearest=True, on="mouseover", empty=False)
    base = alt.Chart(df).encode(
        x=alt.X("Fecha:T", title=None, axis=alt.Axis(format="%d %b", grid=False)),
        y=alt.Y("Valor:Q", title=unidad, scale=alt.Scale(zero=False), axis=alt.Axis(gridOpacity=0.3)),
    )
    capa_linea = base.mark_line(color=AZUL, strokeWidth=2)
    puntos = base.mark_point(size=80, filled=True, color=AZUL, opacity=0).add_params(hover).encode(
        opacity=alt.condition(hover, alt.value(1), alt.value(0)),
        tooltip=[alt.Tooltip("Fecha:T", format="%d %b %Y"), alt.Tooltip("Valor:Q", format=",.2f", title=unidad)],
    )
    regla = base.mark_rule(color="#52514e", strokeDash=[3, 3]).encode(
        opacity=alt.condition(hover, alt.value(0.6), alt.value(0))).transform_filter(hover)
    return (capa_linea + regla + puntos).properties(title=titulo, height=260)


# ---------------- Barra lateral: controles ----------------
cfg = configuracion.fusionar(configuracion.cargar(BASE), secreto("ajustes"))
EN_LA_NUBE = secreto("ajustes") is not None or secreto("clave_acceso") is not None
with st.sidebar:
    st.header("Controles")
    modo_demo = st.toggle("Modo demostración (datos ficticios)", value=os.environ.get("MONITOR_DEMO") == "1",
                          help="Úsalo para probar el tablero sin internet. Los números NO son reales.")
    if st.button("🔄 Actualizar ahora", width="stretch"):
        st.session_state["marca"] = datetime.now().isoformat()

    st.subheader("Tu empresa")
    emp = cfg["empresa"]
    emp["inventario_toneladas"] = st.number_input("Inventario actual (t)", 0.0, value=float(emp["inventario_toneladas"]), step=5.0)
    emp["consumo_mensual_toneladas"] = st.number_input("Consumo mensual (t)", 0.0, value=float(emp["consumo_mensual_toneladas"]), step=5.0)
    claves = list(cfg["proveedores"])
    emp["proveedor_actual"] = st.selectbox("Proveedor actual", claves, index=claves.index(emp["proveedor_actual"]),
                                           format_func=lambda k: cfg["proveedores"][k]["nombre"])

    st.subheader("Precio LME oficial (opcional)")
    manual = st.number_input("USD/t (0 = usar COMEX)", 0.0, value=float(cfg["cobre"].get("precio_manual_usd_t") or 0), step=10.0)
    cfg["cobre"]["precio_manual_usd_t"] = manual or None

st.title("Monitor de cobre")
with st.expander("✏️ Ajustar costos por proveedor (USD por tonelada)"):
    tabla_prov = pd.DataFrame(cfg["proveedores"]).T[["nombre", "prima_usd_t", "flete_usd_t", "seguro_usd_t", "arancel_pct", "dias_transito"]]
    editada = st.data_editor(tabla_prov, width="stretch", disabled=["nombre"],
                             column_config={"nombre": "Proveedor", "prima_usd_t": "Prima", "flete_usd_t": "Flete",
                                            "seguro_usd_t": "Seguro", "arancel_pct": "Arancel %", "dias_transito": "Días tránsito"})
    for clave, fila in editada.iterrows():
        cfg["proveedores"][clave].update({k: float(fila[k]) for k in editada.columns if k != "nombre"})
    if EN_LA_NUBE:
        st.caption("Versión en internet: los cambios sirven para simular. Para dejarlos fijos, cámbialos en "
                   "*Settings → Secrets* de Streamlit Cloud (sección `[ajustes]`).")
    else:
        st.caption("Cambia los valores y presiona Guardar para que las alertas automáticas también los usen.")
    if not EN_LA_NUBE and st.button("💾 Guardar mis valores"):
        configuracion.guardar_ajustes(BASE, {"empresa": emp, "cobre": cfg["cobre"], "proveedores": cfg["proveedores"]})
        st.success("Guardado en data/ajustes.yaml.")

ctx, todas, errores = consultar(cfg, modo_demo, st.session_state.get("marca"))

# ---------------- Encabezado ----------------

st.caption(f"Última consulta: {ctx['fecha_hora']} · Cobre: {ctx.get('fuente_cobre', 's/d')}")
if modo_demo:
    st.warning("**Modo demostración:** los datos son ficticios, solo para ver cómo funciona el tablero.")

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
          f"mínimo {cfg['empresa']['cobertura_minima_dias']} días", delta_color="off", delta_arrow="off")

# ---------------- Alertas ----------------
st.subheader("¿Qué hacer hoy?")
if not todas:
    st.info("Sin alertas. Mercado y suministro dentro de lo normal.")
for a in todas:
    NIVEL.get(a["nivel"], st.info)(f"**{a['nivel']}** — {a['texto']}")

# ---------------- Gráficos de mercado ----------------
g1, g2 = st.columns(2)
with g1:
    if ctx.get("serie_cobre"):
        st.altair_chart(linea(ctx["serie_cobre"], "Cobre — último mes", "USD/t"), width="stretch")
    else:
        st.info("Sin histórico de cobre (se está usando el precio manual o ninguna fuente respondió).")
with g2:
    if ctx.get("serie_trm"):
        st.altair_chart(linea(ctx["serie_trm"], "TRM — último mes", "COP/USD"), width="stretch")

# ---------------- Proveedores ----------------
st.subheader("Costo puesto en planta por proveedor")
if ranking:
    df = pd.DataFrame(ranking)
    actual = cfg["empresa"]["proveedor_actual"]
    df["Estado"] = [" · ".join(e for e, ok in (("Más barato", i == 0), ("Actual", c == actual)) if ok)
                    for i, c in enumerate(df["clave"])]
    df["extra"] = df["cop_t"] - df["cop_t"].iloc[0]
    df["Proveedor"] = df["nombre"].str.split(" \\(").str[0]
    df["USD/t"] = df["usd_t"].map(lambda x: f"${x:,.0f}")
    df["COP/t"] = df["cop_t"].map(lambda x: f"${x:,.0f}")
    df["sobrecosto"] = df["extra"].map(lambda x: f"+${x:,.0f}" if x else "—")
    base_b = alt.Chart(df).encode(
        x=alt.X("extra:Q", title="Sobrecosto vs. el más barato (COP por tonelada)", axis=alt.Axis(format="~s", gridOpacity=0.3)),
        y=alt.Y("Proveedor:N", title=None, sort=None),
        tooltip=["Proveedor", "COP/t", "USD/t", alt.Tooltip("sobrecosto:N", title="Sobrecosto"), alt.Tooltip("dias_transito:Q", title="Días tránsito")],
    )
    barras = base_b.mark_bar(color=AZUL, cornerRadiusEnd=4, height=22) + base_b.mark_text(
        align="left", dx=6, color="#52514e").encode(text="sobrecosto:N")
    p1, p2 = st.columns(2)
    p1.altair_chart(barras.properties(height=45 * len(df) + 40), width="stretch")
    p2.dataframe(df[["Proveedor", "COP/t", "USD/t", "dias_transito", "Estado"]], hide_index=True, width="stretch",
                 column_config={"dias_transito": "Días"})
else:
    falta = "el precio del cobre" if not ctx.get("cobre_usd_t") else "la TRM"
    st.warning(f"No se puede calcular porque falta {falta}. Mientras tanto, escribe el precio LME en "
               "**Precio LME oficial** (barra lateral) y el cálculo aparece al instante. "
               "Abajo, en *fuentes no respondieron*, está el detalle de cada fuente.")

# ---------------- Noticias ----------------
st.subheader("Noticias que pueden afectar el suministro")
if ctx.get("noticias"):
    dfn = pd.DataFrame(ctx["noticias"])
    orden = st.radio("Ordenar", ["Mayor riesgo primero", "Más recientes primero"], horizontal=True,
                     label_visibility="collapsed")
    if orden == "Más recientes primero":
        dfn = dfn.sort_values("fecha", ascending=False, na_position="last")
    st.caption(f"{len(dfn)} noticias de los últimos {round(cfg['noticias'].get('max_horas', 72) / 24)} días. "
               "Riesgo 1/10 = habla de cobre o minería sin señales de problema.")
    dfn["Fecha"] = dfn["fecha"].map(lambda d: d.strftime("%d %b %H:%M") if d is not None else "")
    st.dataframe(dfn[["riesgo", "titulo", "fuente", "Fecha", "url"]], hide_index=True, width="stretch",
                 column_config={"riesgo": st.column_config.ProgressColumn("Riesgo", min_value=0, max_value=10, format="%d/10"),
                                "titulo": st.column_config.TextColumn("Título", width="large"),
                                "fuente": "Fuente", "url": st.column_config.LinkColumn("Abrir", display_text="ver")})
else:
    st.info("No hay noticias relevantes en las últimas horas.")

# ---------------- Histórico guardado ----------------
ruta_hist = os.path.join(BASE, "data", "historico.csv")
if os.path.exists(ruta_hist):
    with st.expander("Histórico de consultas automáticas"):
        st.dataframe(pd.read_csv(ruta_hist).iloc[::-1], hide_index=True, width="stretch")

if errores:
    with st.expander(f"⚠️ {len(errores)} fuente(s) no respondieron", expanded=not ctx.get("cobre_usd_t")):
        for e in errores:
            st.write("-", e)
