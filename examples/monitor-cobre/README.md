# Monitor de cobre

Sistema de alertas para una empresa que importa cobre (principalmente de Perú) y lo transforma en cable.
Cada hora revisa:

| Qué | Fuente | Frecuencia real |
|---|---|---|
| TRM oficial | datos.gov.co (Superfinanciera, dataset `32sa-8pi3`) | 1 vez al día |
| Precio del cobre | COMEX `HG=F` (Yahoo Finance), aproximación a LME | ~15 min de retraso |
| Riesgo de suministro | Google News RSS + GDELT (huelgas, bloqueos, puertos, aranceles) | continua |

Con eso calcula el **costo puesto en planta en COP/t por proveedor**, lo compara y envía alertas
por Telegram y/o correo.

## Abrir el programa (tablero)

El tablero muestra en una sola pantalla la TRM, el cobre, el costo por proveedor, qué hacer hoy y las noticias de riesgo.

- **Windows:** doble clic en `iniciar.bat`.
- **Mac:** doble clic en `iniciar.command` (la primera vez: clic derecho, *Abrir*).
- **Linux o terminal:** `pip install -r requirements.txt` y luego `streamlit run app.py`.

La primera vez instala lo necesario (solo hace falta tener [Python](https://www.python.org/downloads/) instalado).
Después se abre en el navegador, en `http://localhost:8501`.

En el tablero puedes:

- cambiar inventario, consumo y proveedor actual en la barra lateral;
- escribir el precio LME oficial si tu broker te lo da;
- ajustar primas, fletes y aranceles en *Ajustar costos por proveedor* y guardarlos
  (quedan en `data/ajustes.yaml` y también los usan las alertas automáticas);
- activar el **modo demostración** para ver cómo funciona sin internet (datos ficticios).

## Cálculo de costo

```
costo COP/t = (cobre USD/t + prima + flete + seguro) × (1 + arancel %) × TRM
```

Las primas, fletes, seguros y aranceles se configuran por proveedor en `config.yaml`.
**Los valores que vienen son estimados (marcados `AJUSTAR`): reemplázalos con tus cotizaciones reales.**

## Alertas

| Nivel | Cuándo |
|---|---|
| OPORTUNIDAD | El cobre baja más de 3 % en la semana, o otro proveedor sale al menos 2 % más barato |
| ATENCION | El cobre sube más de 5 % en la semana, o la TRM se mueve más de 2 % |
| URGENTE | El inventario alcanza para menos de 30 días |
| RIESGO SUMINISTRO | Noticia con puntaje de riesgo ≥ 6/10 (p. ej. bloqueo en Las Bambas, huelga en Cerro Verde, paro en el Callao) |

Todos los umbrales se cambian en `config.yaml`. Cada alerta se envía una sola vez
(registro en `data/alertas_enviadas.json`).

El puntaje de noticias suma pesos por evento (huelga, bloqueo, fuerza mayor…) y por activo
(Las Bambas, Antamina, Cerro Verde, Callao…). Solo cuenta noticias que hablan de cobre o minería.
Las listas están en `monitor/noticias.py`.

## Uso por terminal (sin tablero)

```bash
pip install -r requirements.txt
```

```bash
python -m monitor --sin-envio
```

El reporte queda en `reportes/ultimo.md` y el histórico de precios en `data/historico.csv`.

Pruebas:

```bash
python -m unittest discover -s tests -t .
```

## Puesta en marcha automática (gratis, con GitHub Actions)

1. Crea un repositorio nuevo (privado) y copia el contenido de esta carpeta en su raíz.
   El workflow `.github/workflows/monitor.yml` corre cada hora, de lunes a viernes, de 7 a. m. a 6 p. m. hora Colombia.
2. Crea un bot de Telegram con @BotFather y obtén tu `chat_id`.
3. En el repositorio, ve a *Settings → Secrets and variables → Actions* y agrega:
   - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
   - opcional, para correo: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `ALERTA_EMAIL_DESTINO`
4. Ejecuta el workflow una vez a mano (*Actions → Monitor de cobre → Run workflow*).

Cada ejecución guarda el reporte en el resumen del job y hace commit del histórico.

## Precio LME oficial

COMEX y LME se mueven casi igual, pero no son idénticos. Para negociar contratos usa el precio
oficial de la LME (es un servicio pago; muchas veces tu proveedor, broker o banco te lo dan).
Ponlo en `cobre.precio_manual_usd_t` dentro de `config.yaml` y el sistema lo usa en lugar de COMEX.
No se hace scraping del sitio de la LME, porque sus términos lo prohíben.

## Próximas fases

- **Fase 2:** clasificación de noticias con IA (relevancia, gravedad y resumen diario en español).
- **Fase 3:** publicar el tablero en internet (Streamlit Community Cloud) para verlo desde el celular.
