# Publicar el tablero en internet (gratis)

Con esto tú y tu equipo abren el tablero desde el celular o cualquier computador, con un enlace
y una clave, sin instalar nada. Se usa **Streamlit Community Cloud** (gratis).

## Antes de empezar: seguridad

El repositorio `iaconduluz-lgtm/ECC` es **público**. Por eso:

- **Nunca** escribas tus primas, fletes o inventario reales en `config.yaml`: cualquiera los vería en GitHub.
  Los valores reales van en los *Secrets* de Streamlit (paso 4), que no se publican.
- La app **siempre** debe tener `clave_acceso`. Sin ella, cualquiera con el enlace ve el tablero.

## Pasos (unos 10 minutos)

1. Entra a <https://share.streamlit.io> y elige **Continue with GitHub** con tu cuenta `iaconduluz-lgtm`.
   Acepta los permisos que pide.
2. Pulsa **Create app** y luego **Deploy a public app from GitHub** (o *Yup, I have an app*).
3. Llena los campos:

   | Campo | Valor |
   |---|---|
   | Repository | `iaconduluz-lgtm/ECC` |
   | Branch | `claude/wizardly-dijkstra-lo3lru` |
   | Main file path | `examples/monitor-cobre/app.py` |
   | App URL | el nombre que quieras, p. ej. `monitor-cobre-tuempresa` |

4. Abre **Advanced settings**:
   - **Python version:** 3.12.
   - **Secrets:** copia el contenido de `.streamlit/secrets.toml.example`, pégalo y cambia:
     - `clave_acceso` por una clave larga (por ejemplo, cuatro palabras al azar);
     - las primas, fletes, inventario y consumo por tus valores reales.
5. Pulsa **Deploy**. La primera vez tarda 2 o 3 minutos en instalar.
6. Abre el enlace, escribe la clave y listo. Compártelo con tu equipo junto con la clave.

## Uso diario

- Los datos se actualizan cada 15 minutos o al pulsar **Actualizar ahora**.
- Para cambiar costos o inventario de forma permanente: en Streamlit Cloud, abre tu app,
  **⋮ → Settings → Secrets**, edita y guarda. La app se reinicia sola con los nuevos valores.
  Los cambios hechos en la pantalla del tablero sirven para simular, pero no se guardan.
- Si nadie abre la app en varios días, Streamlit la "duerme". Al entrar aparece un botón para
  despertarla; tarda menos de un minuto.

## Si algo falla

- **"Fuentes no respondieron" al final de la página:** copia el mensaje y revísalo.
  Si Yahoo Finance bloquea el precio del cobre, escribe el precio LME en la barra lateral
  o en los secrets (`[ajustes.cobre]` → `precio_manual_usd_t = 9850`).
- **La app no arranca:** en Streamlit Cloud, abre **Manage app** (abajo a la derecha) para ver el error.
- **Cambié de rama o la borré:** la app deja de funcionar. Si la rama se une a `main`,
  edita la app en Streamlit Cloud y cambia *Branch* a `main`.

## Alertas automáticas (Telegram/correo cada hora)

El tablero solo consulta cuando alguien lo abre. Para recibir alertas sin abrirlo, usa
GitHub Actions como se explica en el `README.md`, **en un repositorio privado**: en uno público,
los reportes de cada ejecución quedarían visibles para todos. Allí, guarda tus costos reales
en el secret `MONITOR_AJUSTES` (mismo formato que `config.yaml`, solo lo que cambia).
