"""Diseños visuales del tablero.

Cada tema define los colores base (los mismos que acepta [theme] de Streamlit), los colores de los gráficos
y un CSS que da el estilo propio: encabezado, tarjetas de indicadores, barra lateral y pestañas.
Se elige con `apariencia.tema` en config.yaml / Secrets, o con la variable MONITOR_TEMA.
"""

TEMAS = {
    "cobre": {
        "nombre": "Cobre",
        "oscuro": False,
        "fondo": "#FAF6F0", "fondo2": "#F1E8DC", "texto": "#2B1D14", "texto2": "#6B5646",
        "acento": "#B4632A", "acento_suave": "#F3DFCC",
        "lateral": "#2B1D14", "lateral_texto": "#F6EBDD",
        "serie": "#B4632A", "serie2": "#2F6F8F", "malo": "#C0392B", "bueno": "#2F6F8F", "neutro": "#EDE4D8",
        "fuente": "'Source Sans 3', sans-serif", "fuente_titulos": "'Fraunces', serif",
        "google_fonts": "Fraunces:wght@600;700&family=Source+Sans+3:wght@400;600",
        "encabezado": "linear-gradient(120deg, #2B1D14 0%, #6B3A1E 55%, #B4632A 100%)",
        "radio": "14px",
    },
    "noche": {
        "nombre": "Noche industrial",
        "oscuro": True,
        "fondo": "#0F1419", "fondo2": "#1A2129", "texto": "#E8E2D9", "texto2": "#9AA4AE",
        "acento": "#E8833A", "acento_suave": "#3A2616",
        "lateral": "#0A0E12", "lateral_texto": "#E8E2D9",
        "serie": "#E8833A", "serie2": "#3FB5A3", "malo": "#F05D5E", "bueno": "#3FB5A3", "neutro": "#2A323B",
        "fuente": "'Inter', sans-serif", "fuente_titulos": "'Inter', sans-serif",
        "google_fonts": "Inter:wght@400;600;800",
        "encabezado": "linear-gradient(120deg, #0A0E12 0%, #1A2129 60%, #3A2616 100%)",
        "radio": "12px",
    },
    "corporativo": {
        "nombre": "Corporativo",
        "oscuro": False,
        "fondo": "#F4F6FA", "fondo2": "#E6EBF3", "texto": "#0B2545", "texto2": "#51627A",
        "acento": "#1F6FEB", "acento_suave": "#DCE8FD",
        "lateral": "#0B2545", "lateral_texto": "#EAF0FA",
        "serie": "#1F6FEB", "serie2": "#E07A1F", "malo": "#D64545", "bueno": "#1F6FEB", "neutro": "#E9EDF3",
        "fuente": "'IBM Plex Sans', sans-serif", "fuente_titulos": "'IBM Plex Sans', sans-serif",
        "google_fonts": "IBM+Plex+Sans:wght@400;600;700",
        "encabezado": "linear-gradient(120deg, #0B2545 0%, #13315C 50%, #1F6FEB 100%)",
        "radio": "8px",
    },
    "minimal": {
        "nombre": "Minimalista",
        "oscuro": False,
        "fondo": "#FFFFFF", "fondo2": "#F5F5F4", "texto": "#111111", "texto2": "#6B6B6B",
        "acento": "#111111", "acento_suave": "#F0F0EE",
        "lateral": "#FAFAF9", "lateral_texto": "#111111",
        "serie": "#111111", "serie2": "#16A34A", "malo": "#DC2626", "bueno": "#16A34A", "neutro": "#EFEFED",
        "fuente": "'Manrope', sans-serif", "fuente_titulos": "'Manrope', sans-serif",
        "google_fonts": "Manrope:wght@400;600;800",
        "encabezado": "#FFFFFF",
        "radio": "4px",
    },
}
PREDETERMINADO = "cobre"


def obtener(nombre):
    return TEMAS.get((nombre or "").lower(), TEMAS[PREDETERMINADO])


def config_streamlit(t):
    """Opciones [theme] equivalentes (para .streamlit/config.toml o la línea de comandos)."""
    return {"base": "dark" if t["oscuro"] else "light", "primaryColor": t["acento"], "backgroundColor": t["fondo"],
            "secondaryBackgroundColor": t["fondo2"], "textColor": t["texto"]}


def css(t):
    claro_enc = t["encabezado"] == "#FFFFFF"
    texto_enc = t["texto"] if claro_enc else "#FFFFFF"
    borde_enc = f"border-bottom: 2px solid {t['texto']};" if claro_enc else ""
    return f"""
<link href="https://fonts.googleapis.com/css2?family={t['google_fonts']}&display=swap" rel="stylesheet">
<style>
  .stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea, .stApp button, .stApp td, .stApp th,
  .stApp [data-testid="stMarkdownContainer"], .stApp [data-testid="stMetricValue"] {{ font-family: {t['fuente']}; }}
  .stApp {{ background: {t['fondo']}; color: {t['texto']}; }}
  h1, h2, h3 {{ font-family: {t['fuente_titulos']} !important; color: {t['texto']} !important; letter-spacing: -0.01em; }}
  [data-testid="stHeader"] {{ background: transparent; }}

  /* Encabezado */
  .mc-encabezado {{ background: {t['encabezado']}; color: {texto_enc}; border-radius: {t['radio']};
                   padding: 26px 30px 22px; margin: 0 0 18px; {borde_enc} }}
  .mc-encabezado h1 {{ color: {texto_enc} !important; margin: 0; font-size: 2.3rem; line-height: 1.1; }}
  .mc-encabezado .mc-sub {{ opacity: .82; margin-top: 6px; font-size: .95rem; }}
  .mc-chip {{ display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: .78rem; margin: 10px 6px 0 0;
             background: {'rgba(255,255,255,.14)' if not claro_enc else t['fondo2']}; color: {texto_enc}; }}

  /* Barra lateral */
  [data-testid="stSidebar"] {{ background: {t['lateral']}; }}
  [data-testid="stSidebar"] p, [data-testid="stSidebar"] label, [data-testid="stSidebar"] h1,
  [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3, [data-testid="stSidebar"] small {{ color: {t['lateral_texto']} !important; }}
  {'' if t['oscuro'] else '[data-testid="stSidebar"] input, [data-testid="stSidebar"] [data-baseweb="select"] * { color: #111 !important; }'}

  /* Tarjetas de indicadores */
  [data-testid="stMetric"] {{ background: {t['fondo2'] if t['oscuro'] else '#FFFFFF'}; border-radius: {t['radio']};
                             padding: 16px 18px; border: 1px solid {t['neutro']};
                             box-shadow: 0 1px 2px rgba(0,0,0,{'.35' if t['oscuro'] else '.05'});
                             border-top: 3px solid {t['acento']}; }}
  [data-testid="stMetricLabel"] {{ color: {t['texto2']} !important; font-weight: 600; }}
  [data-testid="stMetricValue"] {{ font-family: {t['fuente_titulos']}; font-weight: 700; color: {t['texto']}; }}

  /* Pestañas */
  .stTabs [data-baseweb="tab-list"] {{ gap: 4px; border-bottom: 1px solid {t['neutro']}; }}
  .stTabs [data-baseweb="tab"] {{ border-radius: {t['radio']} {t['radio']} 0 0; padding: 8px 14px; }}
  .stTabs [aria-selected="true"] {{ background: {t['acento_suave']}; }}
  .stTabs [data-baseweb="tab-highlight"] {{ background-color: {t['acento']}; }}

  /* Botones, etiquetas y tablas */
  .stButton button, .stDownloadButton button {{ border-radius: {t['radio']}; border: 1px solid {t['acento']};
                                               color: {t['acento']}; background: transparent; font-weight: 600; }}
  .stButton button:hover {{ background: {t['acento']}; color: #fff; }}
  [data-baseweb="tag"] {{ background-color: {t['acento']} !important; }}
  [data-testid="stDataFrame"], [data-testid="stExpander"], [data-testid="stAlert"] {{ border-radius: {t['radio']}; }}
</style>
"""


def bloque_css(t):
    """CSS listo para st.markdown: sin líneas en blanco ni comentarios (si no, Markdown lo muestra como texto)."""
    import re
    texto = re.sub(r"/\*.*?\*/", "", css(t), flags=re.S)
    return "\n".join(linea for linea in texto.splitlines() if linea.strip())


def encabezado_html(t, titulo, subtitulo, chips):
    chips_html = "".join(f'<span class="mc-chip">{c}</span>' for c in chips)
    return (f'<div class="mc-encabezado"><h1>{titulo}</h1><div class="mc-sub">{subtitulo}</div>'
            f"{chips_html}</div>")
