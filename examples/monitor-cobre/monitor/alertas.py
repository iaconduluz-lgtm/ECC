"""Reglas de decisión y envío de alertas (Telegram y/o correo)."""
import os
import smtplib
from email.message import EmailMessage

import requests


def evaluar(ctx, cfg):
    """Devuelve una lista de alertas [{'id', 'nivel', 'texto'}] a partir del contexto calculado."""
    a = cfg["alertas"]
    out = []
    var_cu = ctx.get("cobre_var_semanal")
    if var_cu is not None and var_cu <= a["cobre_baja_semanal_pct"]:
        out.append({"id": f"cu-baja-{ctx['fecha']}", "nivel": "OPORTUNIDAD",
                    "texto": f"Cobre bajó {abs(var_cu)}% en la semana. Evaluar comprar más / adelantar pedido."})
    if var_cu is not None and var_cu >= a["cobre_sube_semanal_pct"]:
        out.append({"id": f"cu-sube-{ctx['fecha']}", "nivel": "ATENCION",
                    "texto": f"Cobre subió {var_cu}% en la semana. Considerar fijar precio o cubrir."})
    var_trm = ctx.get("trm_var_semanal")
    if var_trm is not None and abs(var_trm) >= a["trm_variacion_semanal_pct"]:
        sentido = "subió" if var_trm > 0 else "bajó"
        out.append({"id": f"trm-{ctx['fecha']}", "nivel": "ATENCION",
                    "texto": f"TRM {sentido} {abs(var_trm)}% en la semana (hoy {ctx['trm']:,.2f}). Revisar cobertura cambiaria."})

    ranking = ctx.get("ranking") or []
    actual = next((r for r in ranking if r["clave"] == cfg["empresa"]["proveedor_actual"]), None)
    if ranking and actual and ranking[0]["clave"] != actual["clave"]:
        ahorro = (actual["cop_t"] - ranking[0]["cop_t"]) / actual["cop_t"] * 100
        if ahorro >= a["ahorro_minimo_cambio_proveedor_pct"]:
            out.append({"id": f"prov-{ranking[0]['clave']}-{ctx['fecha']}", "nivel": "OPORTUNIDAD",
                        "texto": f"{ranking[0]['nombre']} sale {ahorro:.1f}% más barato que {actual['nombre']}."})

    cob = ctx.get("cobertura_dias")
    if cob is not None and cob < cfg["empresa"]["cobertura_minima_dias"]:
        out.append({"id": f"inv-{ctx['fecha']}", "nivel": "URGENTE",
                    "texto": f"Inventario alcanza para {cob} días (mínimo {cfg['empresa']['cobertura_minima_dias']}). Reponer."})

    for n in ctx.get("noticias", []):
        if n["riesgo"] >= a["noticia_riesgo_minimo"]:
            out.append({"id": f"news-{n['id']}", "nivel": "RIESGO SUMINISTRO",
                        "texto": f"[{n['riesgo']}/10] {n['titulo']}\n{n['url']}"})
    return out


def formatear(alertas):
    return "\n\n".join(f"⚠️ {x['nivel']}: {x['texto']}" for x in alertas)


def enviar_telegram(texto):
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return False
    resp = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                         json={"chat_id": chat, "text": texto[:4000], "disable_web_page_preview": True}, timeout=20)
    resp.raise_for_status()
    return True


def enviar_correo(asunto, texto):
    host, usuario, clave, destino = (os.environ.get(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "ALERTA_EMAIL_DESTINO"))
    if not (host and usuario and clave and destino):
        return False
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = asunto, usuario, destino
    msg.set_content(texto)
    with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=30) as s:
        s.starttls()
        s.login(usuario, clave)
        s.send_message(msg)
    return True
