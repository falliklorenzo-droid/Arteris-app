# Arteris — Guía de deploy, dominio y mantenimiento

Esta guía explica, paso a paso, cómo poner en producción la nueva versión de Arteris:
migrar la base de datos, subir el código, publicarlo en Railway (always-on),
conectar el dominio **arterismed.com** y activar los recordatorios por email.

Los pasos marcados con 🧑 **los tenés que hacer vos** desde tus cuentas (no puedo
acceder a tu registrador de dominio, GitHub, Railway ni Supabase por seguridad).

---

## Resumen de lo que cambió en esta versión

**Seguridad (Fase 0)**
- Se cerró el acceso por link `?codigo=` sin contraseña. Ahora, si la cuenta ya está
  activada, el paciente debe ingresar con email y contraseña.
- Se eliminaron las credenciales de admin por defecto. El admin ahora se configura
  por variable de entorno; si no está configurado, el acceso admin queda deshabilitado.
- Las contraseñas pasan a guardarse con **bcrypt**. Las cuentas viejas (SHA-256) se
  migran solas y de forma transparente la próxima vez que cada usuario inicia sesión.
- Se completó la recuperación de contraseña para pacientes y médicos.

**Infraestructura (Fase 1)**
- La app lee su configuración desde variables de entorno (para Railway) o desde
  `.streamlit/secrets.toml` (para correr local).
- Archivos de deploy listos: `Procfile`, `.streamlit/config.toml`, `.gitignore`,
  `.python-version`.

**Núcleo clínico (Fase 2)**
- Resultado con las **4 categorías** del consenso (controlada / no controlada /
  urgente / valores bajos) y promedios desglosados (mañana, tarde, diario, general).
- Sección "Pasos a seguir" con la especificación del tensiómetro validado y las
  medidas de brazalete.
- Registro de **eventos adversos** (los reporta el paciente) y **alertas**
  automáticas (tomas elevadas y resultado final).
- **Exportación a PDF** del informe HBPM (datos del paciente, 7 días, tendencia
  gráfica, tratamiento, eventos y alertas).

**Identidad (Fase 3)**
- Título "Monitoreo Domiciliario de Presión Arterial", detalle en rojo en la paleta,
  guías internacionales correctas en el pie de página y una página real de política
  de privacidad y términos.

**Recordatorios (Fase 4)**
- Script `enviar_recordatorios.py` + workflow de GitHub Actions que envía los
  recordatorios a las 10 y a las 18 hs.

---

## Paso 1 — Migrar la base de datos 🧑

1. Entrá a [supabase.com](https://supabase.com) → tu proyecto Arteris.
2. En el menú izquierdo: **SQL Editor** → **New query**.
3. Abrí el archivo `migracion_supabase.sql` (está en esta misma carpeta), copiá
   todo su contenido, pegalo y presioná **Run**.
4. Debería terminar sin errores. Crea las tablas `eventos_adversos` y `alertas`,
   y agrega la columna `reset_token` a la tabla `medicos`.

---

## Paso 2 — Subir el código a GitHub 🧑

Subí al repositorio todos los archivos nuevos y modificados de esta carpeta:
`app.py`, `requirements.txt`, `Procfile`, `.gitignore`, `.python-version`,
`enviar_recordatorios.py`, la carpeta `.streamlit/` y la carpeta `.github/`.

> Importante: el archivo `.streamlit/secrets.toml` **no debe subirse nunca**
> (ya está bloqueado por `.gitignore`). Solo se sube `secrets.toml.example`.

---

## Paso 3 — Publicar en Railway 🧑

1. Creá una cuenta en [railway.app](https://railway.app) (podés entrar con GitHub).
2. **New Project** → **Deploy from GitHub repo** → elegí el repositorio de Arteris.
3. Railway detecta Python automáticamente e instala las dependencias de
   `requirements.txt`. El `Procfile` le indica cómo arrancar la app.
4. Esperá a que el primer deploy termine (unos minutos).

> Railway mantiene la app **siempre encendida** — no se duerme por inactividad,
> que era el problema que tenías con Streamlit Community Cloud.

---

## Paso 4 — Cargar las variables de entorno en Railway 🧑

En Railway: tu proyecto → el servicio → pestaña **Variables** → agregá estas
(una por una, con el nombre exacto en mayúsculas):

| Variable | Valor |
|---|---|
| `SUPABASE_URL` | La URL de tu proyecto Supabase |
| `SUPABASE_KEY` | La API key de Supabase |
| `RESEND_API_KEY` | Tu API key de Resend |
| `ADMIN_EMAIL` | El email con el que entrás como administrador |
| `ADMIN_PASSWORD` | Una contraseña fuerte para el admin (elegila vos) |
| `APP_BASE_URL` | `https://arterismed.com` |

Después de guardarlas, Railway vuelve a desplegar la app sola.

> Estos son los mismos datos que hoy tenés en los *secrets* de Streamlit.
> El admin ya **no** es `admin@arteris.com` / `admin123`: ahora es lo que pongas
> en `ADMIN_EMAIL` y `ADMIN_PASSWORD`.

---

## Paso 5 — Conectar el dominio arterismed.com 🧑

1. En Railway: el servicio → **Settings** → **Networking** → **Custom Domain**.
2. Escribí `arterismed.com` (y, si querés, también `www.arterismed.com`).
3. Railway te va a mostrar un valor de tipo **CNAME** (algo como
   `xxxx.up.railway.app`).
4. Entrá al panel de tu registrador de dominio (donde compraste arterismed.com)
   y creá el registro DNS que Railway te indique:
   - Para `www.arterismed.com`: un registro **CNAME** apuntando al valor de Railway.
   - Para el dominio raíz `arterismed.com`: si tu registrador permite registros
     **ALIAS** o **CNAME flattening**, usalos apuntando al valor de Railway. Si no
     lo permite, configurá el dominio raíz para que **redirija** a `www.arterismed.com`.
5. Los cambios de DNS pueden tardar desde minutos hasta unas horas. Railward
   muestra el dominio como "verificado" cuando está listo.

---

## Paso 6 — Activar los recordatorios por email 🧑

Los recordatorios corren con GitHub Actions (gratis), no en Railway.

1. En GitHub: el repositorio de Arteris → **Settings** → **Secrets and variables**
   → **Actions** → **New repository secret**.
2. Cargá estos 4 secrets (mismos valores que en Railway):
   `SUPABASE_URL`, `SUPABASE_KEY`, `RESEND_API_KEY`, `APP_BASE_URL`.
3. Listo: el workflow `.github/workflows/recordatorios.yml` se ejecuta solo a las
   10 y a las 18 hs (Argentina). Para probarlo ahora, andá a la pestaña **Actions**
   → "Recordatorios HBPM" → **Run workflow**.

---

## Paso 7 — Verificar el dominio del email en Resend 🧑

Para que los emails salgan desde `noreply@arterismed.com`, el dominio
`arterismed.com` tiene que estar verificado en Resend.

1. En [resend.com](https://resend.com) → **Domains** → **Add Domain** → `arterismed.com`.
2. Resend te da unos registros DNS (SPF y DKIM). Cargalos en tu registrador de
   dominio, igual que en el Paso 5.
3. Cuando Resend marque el dominio como verificado, los emails saldrán sin problemas.

---

## Correr la app localmente (opcional)

Si querés probar la app en tu computadora antes de publicar:

1. Copiá `.streamlit/secrets.toml.example` como `.streamlit/secrets.toml` y completá
   los valores.
2. Instalá las dependencias: `pip install -r requirements.txt`.
3. Ejecutá: `streamlit run app.py`.

---

## Lo que queda pendiente (Fase 5 — a planificar aparte)

Estas mejoras no entran en este lote y conviene planificarlas como una etapa
siguiente:

- **Multitenant real:** modelar la "institución" como inquilino con varios médicos,
  y la suscripción mensual por paciente activo (facturación).
- **Múltiples rondas de monitoreo** por paciente (el estudio del Hospital Favaloro
  usa 4 rondas de 7 días: basal, semana 8, 16 y 24). Hoy la app maneja una sola ronda.
- **Row Level Security** en Supabase, para que el aislamiento de datos no dependa
  solo del filtrado de la app.
- **Documentación técnica** formal del sistema (requisito contractual).
- **Backups y monitoreo** gestionados.

---

*Nota: el código de esta versión se escribió sin un entorno para ejecutarlo y
probarlo (el sandbox no estuvo disponible). Antes de publicarlo conviene correrlo
localmente una vez, o que tu equipo de desarrollo lo revise, para confirmar que
todo funciona en tu instalación concreta de Supabase.*
