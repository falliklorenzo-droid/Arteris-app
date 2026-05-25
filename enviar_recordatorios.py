"""
Envío de recordatorios por email a pacientes con un monitoreo HBPM en curso.

Este script NO corre dentro de la app de Streamlit: se ejecuta de forma
programada (ver .github/workflows/recordatorios.yml), dos veces por día.

Variables de entorno requeridas:
    SUPABASE_URL, SUPABASE_KEY, RESEND_API_KEY
    APP_BASE_URL  (opcional, por defecto https://arterismed.com)
"""
import os
import resend
from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
RESEND_API_KEY = os.environ["RESEND_API_KEY"]
APP_URL = os.environ.get("APP_BASE_URL", "https://arterismed.com")

sb = create_client(SUPABASE_URL, SUPABASE_KEY)
resend.api_key = RESEND_API_KEY


def contar_mediciones(codigo):
    try:
        r = sb.table("mediciones").select("codigo_paciente", count="exact")\
            .eq("codigo_paciente", codigo).execute()
        return r.count or 0
    except Exception:
        return 0


def html_recordatorio(nombre):
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;background:#0a1628;color:#e8eef7;border-radius:12px;overflow:hidden;">
      <div style="background:#1d4ed8;padding:24px 32px;">
        <h1 style="font-size:24px;margin:0;color:white;font-weight:400;">Arteris</h1>
        <p style="font-size:12px;color:rgba(255,255,255,0.7);margin:4px 0 0;letter-spacing:1px;text-transform:uppercase;">Monitoreo Domiciliario de Presión Arterial</p>
      </div>
      <div style="padding:32px;">
        <p style="font-size:16px;">Hola {nombre},</p>
        <p style="color:#94a3b8;line-height:1.6;">Es momento de cargar tu presión arterial en Arteris.
        Recordá tomar la medición en reposo y registrar los dos valores.</p>
        <div style="text-align:center;margin:32px 0;">
          <a href="{APP_URL}" style="background:#1d4ed8;color:white;padding:14px 32px;text-decoration:none;border-radius:8px;font-size:15px;display:inline-block;">Cargar mi presión</a>
        </div>
        <p style="font-size:11px;color:#64748b;">Podés desactivar estos recordatorios desde Ajustes en la plataforma.</p>
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

    enviados = 0
    for p in pacientes:
        codigo = p.get("codigo")
        email = p.get("email")
        if not codigo or not email or not p.get("edad"):
            continue  # registro incompleto
        total = contar_mediciones(codigo)
        if total >= 28:
            continue  # monitoreo ya completado
        try:
            resend.Emails.send({
                "from": "Arteris <noreply@arterismed.com>",
                "to": email,
                "subject": "Recordatorio · Cargá tu presión arterial en Arteris",
                "html": html_recordatorio(p.get("nombre", "")),
            })
            enviados += 1
        except Exception as e:
            print(f"Error con {email}: {e}")

    print(f"Recordatorios enviados: {enviados} / pacientes evaluados: {len(pacientes)}")


if __name__ == "__main__":
    main()
