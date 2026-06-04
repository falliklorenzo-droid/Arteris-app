"""
Envío de recordatorios por email a pacientes con un monitoreo HBPM en curso.

Este script NO corre dentro de la app de Streamlit: se ejecuta de forma
programada (ver .github/workflows/recordatorios.yml), dos veces por día.

Reglas (Fase 8):
  - Si el paciente no cargó ninguna toma todavía → SÍ recordatorio (que arranque).
  - Si cargó ≥1 toma → recordatorio solo si pasaron 7 días o menos desde la primera.
  - Si cargó 28 tomas → no recordatorio (terminó).
  - Si pasó el día 7 sin completar (o abandonó con muy baja adherencia) →
    mail FINAL (una sola vez) avisando que el protocolo finalizó.

Variables de entorno requeridas:
    SUPABASE_URL, SUPABASE_KEY, RESEND_API_KEY
    APP_BASE_URL  (opcional, por defecto https://arterismed.com)
"""
import os
from datetime import datetime, timezone, timedelta
import resend
from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
RESEND_API_KEY = os.environ["RESEND_API_KEY"]
APP_URL = os.environ.get("APP_BASE_URL", "https://arterismed.com")

ARG_TZ = timezone(timedelta(hours=-3))

sb = create_client(SUPABASE_URL, SUPABASE_KEY)
resend.api_key = RESEND_API_KEY


def hoy_arg():
    return datetime.now(ARG_TZ).date()


def now_arg_iso():
    return datetime.now(ARG_TZ).isoformat()


def obtener_mediciones(codigo):
    try:
        r = sb.table("mediciones").select("fecha")\
            .eq("codigo_paciente", codigo).execute()
        return r.data or []
    except Exception:
        return []


def fecha_inicio(mediciones):
    """Fecha local (Argentina) del primer toma del paciente. None si no hay."""
    if not mediciones:
        return None
    fechas = []
    for m in mediciones:
        val = m.get("fecha")
        if not val:
            continue
        try:
            # Aceptamos cualquier formato ISO con tz; convertimos a Argentina.
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            fechas.append(dt.astimezone(ARG_TZ).date())
        except Exception:
            continue
    return min(fechas) if fechas else None


def html_recordatorio(nombre):
    cargar_url = f"{APP_URL}/?vista=paciente"
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;background:#0a1628;color:#e8eef7;border-radius:12px;overflow:hidden;">
      <div style="background:#1d4ed8;padding:24px 32px;">
        <h1 style="font-size:24px;margin:0;color:white;font-weight:400;">Arteris</h1>
        <p style="font-size:12px;color:rgba(255,255,255,0.7);margin:4px 0 0;letter-spacing:1px;text-transform:uppercase;">Monitoreo Domiciliario de Presión Arterial</p>
      </div>
      <div style="padding:32px;">
        <p style="font-size:16px;">Hola {nombre},</p>
        <p style="color:#94a3b8;line-height:1.6;">Es momento de cargar tu presión arterial en Arteris.
        Recordá tomar la medición en reposo y registrar los dos valores y la frecuencia cardíaca.</p>
        <div style="text-align:center;margin:32px 0;">
          <a href="{cargar_url}" style="background:#1d4ed8;color:white;padding:14px 32px;text-decoration:none;border-radius:8px;font-size:15px;display:inline-block;">Cargar mi presión arterial →</a>
        </div>
        <p style="font-size:13px;color:#94a3b8;text-align:center;">Si ya iniciaste sesión en este navegador, te lleva directo a la pantalla de carga.</p>
        <p style="font-size:11px;color:#64748b;">Podés desactivar estos recordatorios desde Ajustes en la plataforma.</p>
      </div>
    </div>"""


def html_mail_final(nombre, motivo):
    """Mail único cuando el protocolo expiró sin completar."""
    cargar_url = f"{APP_URL}/?vista=paciente"
    if motivo == "abandonado":
        titulo = "Tu monitoreo HBPM se cerró por baja adherencia"
        cuerpo = (
            "Tu monitoreo HBPM se cerró porque la cantidad de tomas cargadas "
            "es muy baja para llegar al mínimo clínico requerido (12 tomas en 6 días)."
        )
    else:  # expirado
        titulo = "Tu monitoreo HBPM finalizó sin resultado"
        cuerpo = (
            "Pasaron los 7 días del protocolo HBPM y tu monitoreo no llegó al mínimo "
            "de tomas que requieren los estándares clínicos actuales "
            "(12 tomas en los últimos 6 días)."
        )
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;background:#0a1628;color:#e8eef7;border-radius:12px;overflow:hidden;">
      <div style="background:#1d4ed8;padding:24px 32px;">
        <h1 style="font-size:24px;margin:0;color:white;font-weight:400;">Arteris</h1>
        <p style="font-size:12px;color:rgba(255,255,255,0.7);margin:4px 0 0;letter-spacing:1px;text-transform:uppercase;">Monitoreo Domiciliario de Presión Arterial</p>
      </div>
      <div style="padding:32px;">
        <p style="font-size:16px;">Hola {nombre},</p>
        <p style="color:#94a3b8;line-height:1.6;">{cuerpo}</p>
        <p style="color:#94a3b8;line-height:1.6;">Por eso no pudimos calcular un resultado útil. Si querés volver a empezar el monitoreo:</p>
        <div style="text-align:center;margin:24px 0;">
          <a href="{cargar_url}" style="background:#1d4ed8;color:white;padding:14px 32px;text-decoration:none;border-radius:8px;font-size:15px;display:inline-block;">Reiniciar el monitoreo →</a>
        </div>
        <p style="color:#94a3b8;line-height:1.6;font-size:14px;">También te recomendamos consultar con tu médico tratante.</p>
        <p style="font-size:11px;color:#64748b;margin-top:20px;">No vas a recibir más recordatorios por mail hasta que reinicies el monitoreo.</p>
      </div>
    </div>"""


def main():
    try:
        pacientes = sb.table("pacientes").select("*")\
            .eq("recordatorios_email", True)\
            .eq("password_set", True).execute().data or []
    except Exception as e:
        print("Error al leer pacientes:", e)
        return

    hoy = hoy_arg()
    enviados_recordatorio = 0
    enviados_final = 0
    saltados = 0

    for p in pacientes:
        codigo = p.get("codigo")
        email = p.get("email")
        nombre = p.get("nombre", "")
        if not codigo or not email or not p.get("edad"):
            saltados += 1
            continue

        mediciones = obtener_mediciones(codigo)
        total = len(mediciones)

        # Caso 1: ya terminó el protocolo (28 tomas)
        if total >= 28:
            saltados += 1
            continue

        inicio = fecha_inicio(mediciones)
        # Caso 2: nunca empezó el protocolo → siempre mandar recordatorio para que arranque
        if inicio is None:
            try:
                resend.Emails.send({
                    "from": "Arteris <noreply@arterismed.com>",
                    "to": email,
                    "subject": "Recordatorio · Cargá tu presión arterial en Arteris",
                    "html": html_recordatorio(nombre),
                })
                enviados_recordatorio += 1
            except Exception as e:
                print(f"Error con {email}: {e}")
            continue

        # Calcular cuántos días pasaron desde la primera toma
        dias_desde_inicio = (hoy - inicio).days  # 0 = mismo día, 6 = día 7
        dia_actual = dias_desde_inicio + 1
        expirado = dias_desde_inicio >= 7
        # Mismo cálculo de abandono que la app: A) imposibilidad matemática + B) adherencia
        dias_restantes = max(0, 7 - dia_actual + 1)
        max_posible = total + 4 * dias_restantes
        abandono_matematico = max_posible < 12
        abandono_adherencia = (dia_actual >= 4) and (total < dia_actual)
        abandonado = (abandono_matematico or abandono_adherencia) and not expirado

        # Caso 3: protocolo expirado o abandonado → mail final UNA SOLA VEZ
        if expirado or abandonado:
            ya_enviado = bool(p.get("mail_expiracion_enviado_at"))
            if not ya_enviado:
                try:
                    motivo = "abandonado" if (abandonado and not expirado) else "expirado"
                    resend.Emails.send({
                        "from": "Arteris <noreply@arterismed.com>",
                        "to": email,
                        "subject": "Tu monitoreo HBPM finalizó · Arteris",
                        "html": html_mail_final(nombre, motivo),
                    })
                    enviados_final += 1
                    # Marcar como enviado
                    sb.table("pacientes").update({
                        "mail_expiracion_enviado_at": now_arg_iso(),
                    }).eq("codigo", codigo).execute()
                except Exception as e:
                    print(f"Error mail final {email}: {e}")
            else:
                saltados += 1
            continue

        # Caso 4: protocolo activo (días 1-7) → recordatorio normal
        try:
            resend.Emails.send({
                "from": "Arteris <noreply@arterismed.com>",
                "to": email,
                "subject": "Recordatorio · Cargá tu presión arterial en Arteris",
                "html": html_recordatorio(nombre),
            })
            enviados_recordatorio += 1
        except Exception as e:
            print(f"Error con {email}: {e}")

    print(f"Recordatorios enviados: {enviados_recordatorio} · "
          f"Mails finales enviados: {enviados_final} · "
          f"Pacientes salteados: {saltados} / "
          f"Total evaluados: {len(pacientes)}")


if __name__ == "__main__":
    main()
