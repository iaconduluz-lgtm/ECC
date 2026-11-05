"""Análisis de noticias con Claude (opcional). Requiere ANTHROPIC_API_KEY.

Envía titulares + números del mercado y recibe un JSON validado con impacto y recomendación en español.
Costo aproximado: unos pocos centavos de dólar por análisis (solo se ejecuta al pulsar el botón).
"""
import json
import os
from typing import List, Literal

from pydantic import BaseModel

MODELO = "claude-opus-5-5"


class NoticiaClave(BaseModel):
    titulo: str
    nivel: Literal["Bajo", "Medio", "Alto", "Peligro"]
    por_que_importa: str
    efecto_precio: Literal["sube", "baja", "neutral", "incierto"]
    afecta_suministro_peru: bool


class Analisis(BaseModel):
    resumen: str
    presion_precio_cobre: Literal["alcista", "bajista", "neutral", "mixta"]
    riesgo_suministro_peru: Literal["bajo", "medio", "alto"]  # toda la cadena: Perú, puertos y vía a la planta
    noticias_clave: List[NoticiaClave]
    si_sube_cobre: str
    si_sube_trm: str
    recomendacion: str
    acciones: List[str]
    proveedores_alternativos: str


ESQUEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": list(Analisis.model_fields),
    "properties": {
        "resumen": {"type": "string", "description": "3-4 frases sobre la situación de hoy"},
        "presion_precio_cobre": {"type": "string", "enum": ["alcista", "bajista", "neutral", "mixta"]},
        "riesgo_suministro_peru": {"type": "string", "enum": ["bajo", "medio", "alto"]},
        "noticias_clave": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["titulo", "nivel", "por_que_importa", "efecto_precio", "afecta_suministro_peru"],
            "properties": {
                "titulo": {"type": "string"},
                "nivel": {"type": "string", "enum": ["Bajo", "Medio", "Alto", "Peligro"],
                          "description": "Bajo: sin problema de suministro. Medio: posible problema aún no confirmado. "
                                         "Alto: problema activo que puede afectar envíos. Peligro: interrupción grave, "
                                         "prolongada o que afecta al proveedor directo."},
                "por_que_importa": {"type": "string"},
                "efecto_precio": {"type": "string", "enum": ["sube", "baja", "neutral", "incierto"]},
                "afecta_suministro_peru": {"type": "boolean"},
            }}},
        "si_sube_cobre": {"type": "string", "description": "Impacto concreto para la empresa si el cobre sigue subiendo"},
        "si_sube_trm": {"type": "string", "description": "Impacto concreto para la empresa si la TRM sigue subiendo"},
        "recomendacion": {"type": "string", "description": "Recomendación principal de compra, en 1-2 frases"},
        "acciones": {"type": "array", "items": {"type": "string"}, "description": "3-5 acciones concretas para esta semana"},
        "proveedores_alternativos": {"type": "string", "description": "Cuándo conviene activar Chile/México u otros"},
    },
}

SISTEMA = (
    "Eres analista de compras de materias primas de una empresa colombiana que compra cobre en Perú, casi todo a un "
    "único proveedor (indicado en los datos como proveedor_directo), y lo transforma en cables. Cualquier problema de "
    "ese proveedor (huelga, incendio, paro, problemas financieros, logística en Lima/Callao) es el riesgo más importante. "
    "El material llega por el puerto indicado en puerto_llegada y va por carretera a la planta en ciudad_planta, así "
    "que también importan paros, bloqueos y cierres en ese puerto y en esa vía, el dólar en Colombia, la DIAN y los aranceles. Paga en dólares, así que le afectan el precio del cobre "
    "(LME/COMEX) y la TRM. Analiza las noticias y los datos que te dan. Sé concreto y práctico, en español sencillo, "
    "y usa las cifras de impacto que te entregan en lugar de inventar otras. Si una noticia no es relevante, ignórala. "
    "Si los datos no alcanzan para una conclusión, dilo. Tus recomendaciones son de apoyo: la decisión final es del equipo."
)


def disponible():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _datos(ctx, cfg, sens, recomendacion_reglas):
    prov = cfg["proveedores"][cfg["empresa"]["proveedor_actual"]]
    return {
        "fecha": ctx.get("fecha_hora"),
        "trm_hoy": ctx.get("trm"), "trm_var_semanal_pct": ctx.get("trm_var_semanal"),
        "trm_contexto": ctx.get("contexto_trm"),
        "cobre_usd_t_hoy": ctx.get("cobre_usd_t"), "cobre_fuente": ctx.get("fuente_cobre"),
        "cobre_var_semanal_pct": ctx.get("cobre_var_semanal"), "cobre_contexto": ctx.get("contexto_cobre"),
        "proveedor_actual": prov.get("nombre"),
        "proveedor_directo": (cfg.get("noticias") or {}).get("proveedor_claves", []),
        "puerto_llegada": cfg["empresa"].get("puerto_llegada"), "ciudad_planta": cfg["empresa"].get("ciudad_planta"),
        "costo_por_proveedor": [{k: r[k] for k in ("nombre", "usd_t", "cop_t", "dias_transito")}
                                for r in ctx.get("ranking") or []],
        "inventario_dias": ctx.get("cobertura_dias"),
        "plan_inventario_proximos_meses": [
            {k: f[k] for k in ("mes", "tipo", "compras_importacion", "ventas", "final", "dias_inventario")}
            for f in (ctx.get("plan") or [])[(ctx.get("situacion_plan") or {}).get("fila", {}).get("numero", 13) - 1:]],
        "compras_pendientes": ctx.get("compras_pendientes"),
        "consumo_mensual_t": cfg["empresa"].get("consumo_mensual_toneladas"),
        "impacto_gasto_mensual_cop": {
            "por_cada_1pct_que_sube_cobre": sens.get("cobre_1pct_mes") if sens else None,
            "por_cada_1pct_que_sube_trm": sens.get("trm_1pct_mes") if sens else None,
        },
        "recomendacion_por_reglas": recomendacion_reglas,
        "noticias": [{"titulo": n["titulo"], "fuente": n.get("fuente"), "riesgo_reglas": n["riesgo"],
                      "nivel_reglas": n.get("nivel"), "menciona_proveedor_directo": n.get("afecta_proveedor", False),
                      "fecha": n["fecha"].isoformat() if n.get("fecha") else None}
                     for n in (ctx.get("noticias") or [])[:25]],
    }


def analizar(ctx, cfg, sens, recomendacion_reglas, cliente=None):
    """Devuelve un Analisis. Lanza RuntimeError con un mensaje en español si algo falla."""
    import anthropic

    cliente = cliente or anthropic.Anthropic()
    datos = json.dumps(_datos(ctx, cfg, sens, recomendacion_reglas), ensure_ascii=False, default=str)
    try:
        resp = cliente.beta.messages.create(
            model=MODELO,
            max_tokens=16000,
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": ESQUEMA}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",  # si el modelo rechaza la solicitud, otro modelo la completa
            system=SISTEMA,
            messages=[{"role": "user", "content": f"Datos de hoy (JSON):\n{datos}\n\nHaz el análisis."}],
        )
    except anthropic.AuthenticationError:
        raise RuntimeError("La clave ANTHROPIC_API_KEY no es válida.")
    except anthropic.RateLimitError:
        raise RuntimeError("Demasiadas solicitudes a la IA. Intenta de nuevo en un minuto.")
    except anthropic.APIStatusError as e:
        raise RuntimeError(f"Error de la API de IA ({e.status_code}).")
    except anthropic.APIConnectionError:
        raise RuntimeError("No se pudo conectar con la API de IA.")
    if resp.stop_reason == "refusal":
        raise RuntimeError("La IA no pudo completar este análisis. Intenta más tarde.")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("La respuesta de la IA quedó incompleta. Intenta de nuevo.")
    texto = next((b.text for b in resp.content if b.type == "text"), "")
    return Analisis.model_validate_json(texto)
