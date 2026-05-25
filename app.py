import streamlit as st
from supabase import create_client, Client
from datetime import datetime, date
import resend
import uuid
import os
import io
import hashlib
import bcrypt
import pandas as pd
import altair as alt

st.set_page_config(
    page_title="Monitoreo Domiciliario de Presión Arterial · Arteris",
    page_icon="🩺",
    layout="wide"
)

# ── Configuración (secrets o variables de entorno) ────────────────────────────
def get_secret(section, key, default=None):
    """Lee primero de variables de entorno (SECTION_KEY) y luego de st.secrets."""
    env_key = f"{section}_{key}".upper()
    val = os.environ.get(env_key)
    if val:
        return val
    try:
        return st.secrets[section][key]
    except Exception:
        return default

APP_URL = get_secret("app", "base_url", "https://arterismed.com")

# ── CSS Global ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=DM+Serif+Display:ital@0;1&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif !important;
    background-color: #0a1628 !important;
    color: #e8eef7 !important;
}
.stApp {
    background-color: #0a1628 !important;
    min-height: 100vh;
}
section[data-testid="stSidebar"] { display: none; }

/* Layout centrado y contenido */
.block-container {
    padding: 1rem 2rem 0 2rem !important;
    max-width: 1100px !important;
    margin: 0 auto !important;
}
.arteris-nav {
    margin-bottom: 3rem !important;
}

/* Navbar */
.arteris-nav {
    background: rgba(10,22,40,0.98);
    border-bottom: 1px solid rgba(59,130,246,0.2);
    padding: 0 2rem;
    height: 64px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: relative;
}
.arteris-nav::after {
    content: '';
    position: absolute;
    bottom: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, #1d4ed8, #3b82f6, #dc2626, transparent);
}
.logo-wrap { display: flex; align-items: center; gap: 10px; }
.logo-text { font-family: 'DM Serif Display', serif; font-size: 26px; color: #e8eef7; letter-spacing: -0.5px; }
.logo-text span { color: #dc2626; }
.logo-tag { font-size: 10px; color: #94a3b8; letter-spacing: 1.5px; text-transform: uppercase; margin-top: 1px; }

/* Cards */
.art-card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(59,130,246,0.15);
    border-radius: 16px;
    padding: 1.5rem;
    margin-bottom: 1rem;
}
.art-card-white {
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 1.25rem;
    margin-bottom: 1rem;
}
.art-metric {
    text-align: center;
    padding: 1.25rem;
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 10px;
}
.art-metric-num { font-family: 'DM Serif Display', serif; font-size: 40px; color: #3b82f6; line-height: 1; }
.art-metric-label { font-size: 13px; color: #94a3b8; margin-top: 4px; }

/* Badges */
.badge-ok { background: rgba(34,197,94,0.12); color: #22c55e; padding: 4px 12px; border-radius: 20px; font-size: 12px; }
.badge-warn { background: rgba(234,179,8,0.12); color: #eab308; padding: 4px 12px; border-radius: 20px; font-size: 12px; }
.badge-alert { background: rgba(220,38,38,0.14); color: #ef4444; padding: 4px 12px; border-radius: 20px; font-size: 12px; }
.badge-low { background: rgba(59,130,246,0.14); color: #60a5fa; padding: 4px 12px; border-radius: 20px; font-size: 12px; }

/* Buttons */
.stButton > button {
    background: #1d4ed8 !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 15px !important;
    padding: 0.6rem 1.5rem !important;
    width: 100%;
}
.stButton > button:hover { background: #1e40af !important; }
.stDownloadButton > button {
    background: #1d4ed8 !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    width: 100%;
}

/* Progress */
.art-progress-wrap { background: rgba(255,255,255,0.08); border-radius: 4px; height: 8px; overflow: hidden; margin: 8px 0; }
.art-progress-fill { height: 100%; border-radius: 4px; background: linear-gradient(90deg, #1d4ed8, #06b6d4); }

/* Day dots */
.day-dots { display: flex; gap: 8px; margin: 12px 0; flex-wrap: wrap; }
.day-dot { width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 500; }
.day-done { background: rgba(59,130,246,0.2); color: #3b82f6; }
.day-today { background: #1d4ed8; color: white; }
.day-pending { background: rgba(255,255,255,0.05); color: #475569; }

/* Typography */
.section-eyebrow { font-size: 12px; letter-spacing: 2px; text-transform: uppercase; color: #3b82f6; margin-bottom: 8px; }
.section-title { font-family: 'DM Serif Display', serif; font-size: 36px; color: #e8eef7; margin-bottom: 12px; line-height: 1.2; }
.section-sub { font-size: 15px; color: #94a3b8; line-height: 1.7; margin-bottom: 1.5rem; }

/* Pasos */
.paso-card { display:flex; gap:12px; align-items:flex-start; margin-bottom:12px; }
.paso-num { width:28px; height:28px; border-radius:50%; background:#1d4ed8; display:flex; align-items:center; justify-content:center; font-size:13px; font-weight:600; flex-shrink:0; color:white; }

/* Footer */
.arteris-footer {
    background: rgba(0,0,0,0.4);
    border-top: 1px solid rgba(255,255,255,0.06);
    padding: 1.5rem 2rem;
    width: 100%;
    margin-top: 4rem;
}
.inst-badge { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; padding: 6px 14px; font-size: 11px; color: #94a3b8; display: inline-block; margin: 4px; }
.footer-bottom { border-top: 1px solid rgba(255,255,255,0.05); padding-top: 1rem; margin-top: 1rem; font-size: 11px; color: #64748b; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
.footer-bottom a { color: #94a3b8; text-decoration: none; }

/* Hide streamlit defaults */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header { visibility: hidden; }

/* Responsive */
@media (max-width: 768px) {
    .arteris-nav { padding: 0 1rem; height: 56px; }
    .logo-text { font-size: 20px; }
    .logo-tag { display: none; }
    .section-title { font-size: 26px; }
    .art-metric-num { font-size: 28px; }
    .day-dot { width: 30px; height: 30px; font-size: 10px; }
}
@media (max-width: 480px) {
    .section-title { font-size: 22px; }
    .art-card { padding: 1rem; }
}
</style>
""", unsafe_allow_html=True)

# ── Componentes UI ────────────────────────────────────────────────────────────
def navbar(subtitulo=""):
    st.markdown(f"""
    <div class="arteris-nav">
        <div class="logo-wrap">
            <svg width="36" height="36" viewBox="0 0 36 36" fill="none">
              <rect width="36" height="36" rx="9" fill="#1d4ed8"/>
              <path d="M4 20 L9 20 L12 13 L15 25 L18 9 L21 22 L24 16 L27 20 L32 20"
                    stroke="#ef4444" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
            </svg>
            <div style="display:flex;flex-direction:column;justify-content:center;line-height:1.2;">
                <div class="logo-text" style="margin:0;padding:0;">Arteri<span>s</span></div>
                <div class="logo-tag" style="margin:0;padding:0;">Monitoreo Domiciliario de Presión Arterial</div>
            </div>
        </div>
        <div style="font-size:13px;color:#94a3b8;">{subtitulo}</div>
    </div>
    """, unsafe_allow_html=True)

def footer():
    st.markdown(f"""
    <div class="arteris-footer">
        <div style="font-size:12px;color:#94a3b8;margin-bottom:8px;letter-spacing:1px;text-transform:uppercase;">Protocolo basado en guías internacionales de hipertensión</div>
        <div style="display:flex;gap:0.5rem;flex-wrap:wrap;margin-bottom:1rem;">
            <div class="inst-badge">Consenso Latinoamericano de HTA 2026</div>
            <div class="inst-badge">Sociedad Latinoamericana de Hipertensión</div>
            <div class="inst-badge">Liga Iberoamericana de Hipertensión</div>
            <div class="inst-badge">Liga Mundial de Hipertensión</div>
            <div class="inst-badge">ESH · European Society of Hypertension</div>
            <div class="inst-badge">AHA · American Heart Association</div>
            <div class="inst-badge">Guías Japonesas de Hipertensión</div>
            <div class="inst-badge">Hope Asia Network</div>
            <div class="inst-badge">Guías NICE</div>
        </div>
        <div class="footer-bottom">
            <span>© 2025 Arteris · Plataforma orientativa, no reemplaza la consulta médica profesional</span>
            <span><a href="?vista=privacidad" target="_self">Privacidad y términos</a> · Ley 25.326 · Contacto</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

def seccion_pasos():
    st.markdown("""
    <div class="art-card">
        <div class="section-eyebrow">Pasos a seguir para el monitoreo</div>
        <div style="font-size:13px;color:#94a3b8;line-height:1.7;margin-bottom:1rem;">
        Durante <strong style="color:#e8eef7;">7 días seguidos</strong> registrá tu presión:
        <strong style="color:#e8eef7;">2 tomas a la mañana</strong> y
        <strong style="color:#e8eef7;">2 tomas a la tarde</strong> (antes de la cena).
        </div>
        <div class="paso-card">
            <div class="paso-num">1</div>
            <div><div style="font-size:14px;color:#e8eef7;font-weight:500;">Usá un tensiómetro automático validado</div>
            <div style="font-size:12px;color:#94a3b8;margin-top:2px;">Equipo de medición automático validado, con brazalete estándar para brazo
            (12 a 13 cm de ancho y 35 cm de largo). Brazalete ancho si el perímetro del brazo supera 32 cm;
            brazalete pequeño si es menor a 22 cm.</div></div>
        </div>
        <div class="paso-card">
            <div class="paso-num">2</div>
            <div><div style="font-size:14px;color:#e8eef7;font-weight:500;">Antes de medir</div>
            <div style="font-size:12px;color:#94a3b8;margin-top:2px;">Descansá 5 minutos sentado. No tomes café ni hagas
            ejercicio 30 minutos antes. Vaciá la vejiga. Sentate con la espalda apoyada y los pies en el piso.</div></div>
        </div>
        <div class="paso-card">
            <div class="paso-num">3</div>
            <div><div style="font-size:14px;color:#e8eef7;font-weight:500;">Durante la medición</div>
            <div style="font-size:12px;color:#94a3b8;margin-top:2px;">Apoyá el brazo a la altura del corazón. No hables
            ni te muevas. Esperá 1 a 2 minutos entre la primera y la segunda toma.</div></div>
        </div>
        <div class="paso-card">
            <div class="paso-num">4</div>
            <div><div style="font-size:14px;color:#e8eef7;font-weight:500;">Cargá los valores</div>
            <div style="font-size:12px;color:#94a3b8;margin-top:2px;">Ingresá la sistólica (número mayor) y la diastólica
            (número menor) en la plataforma luego de cada toma.</div></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# ── Supabase ──────────────────────────────────────────────────────────────────
@st.cache_resource
def get_sb() -> Client:
    return create_client(get_secret("supabase", "url"), get_secret("supabase", "key"))

def buscar_paciente_por_email(email):
    try:
        r = get_sb().table("pacientes").select("*").eq("email", email).execute()
        return r.data[0] if r.data else None
    except Exception:
        return None

def buscar_paciente(codigo):
    try:
        r = get_sb().table("pacientes").select("*").eq("codigo", codigo).execute()
        return r.data[0] if r.data else None
    except Exception:
        return None

def buscar_paciente_por_reset_token(token):
    try:
        r = get_sb().table("pacientes").select("*").eq("reset_token", token).execute()
        return r.data[0] if r.data else None
    except Exception:
        return None

def actualizar_paciente(codigo, datos):
    get_sb().table("pacientes").update(datos).eq("codigo", codigo).execute()

def crear_paciente(nombre, apellido, email, medico_id):
    codigo = str(uuid.uuid4())[:8].upper()
    get_sb().table("pacientes").insert({
        "codigo": codigo,
        "nombre": nombre,
        "apellido": apellido,
        "email": email,
        "medico_id": medico_id,
        "consentimiento_aceptado": False,
    }).execute()
    return codigo

def guardar_medicion(codigo, sistolica, diastolica, momento):
    get_sb().table("mediciones").insert({
        "codigo_paciente": codigo,
        "sistolica": sistolica,
        "diastolica": diastolica,
        "momento": momento,
        "fecha": datetime.now().isoformat()
    }).execute()
    # Alerta automática por toma elevada
    if sistolica >= 180 or diastolica >= 110:
        generar_alerta(codigo, "toma_elevada",
                       f"Toma elevada registrada: {sistolica}/{diastolica} mmHg ({momento}).")
    # Alerta automática al completar el monitoreo
    try:
        meds = obtener_mediciones(codigo)
        if len(meds) == 28:
            res = calcular_resultado(meds)
            if res and res["categoria"] != "controlada":
                generar_alerta(codigo, "resultado",
                               f"Resultado del HBPM: {res['titulo']} "
                               f"({res['sis_general']}/{res['dia_general']} mmHg promedio).")
    except Exception:
        pass

def obtener_mediciones(codigo):
    r = get_sb().table("mediciones").select("*").eq("codigo_paciente", codigo).order("fecha").execute()
    return r.data

def obtener_pacientes_medico(medico_id):
    r = get_sb().table("pacientes").select("*").eq("medico_id", medico_id).order("fecha_registro", desc=True).execute()
    return r.data

def obtener_todos_pacientes():
    r = get_sb().table("pacientes").select("*").order("fecha_registro", desc=True).execute()
    return r.data

def buscar_medico_por_user_id(user_id):
    try:
        r = get_sb().table("medicos").select("*").eq("user_id", user_id).execute()
        return r.data[0] if r.data else None
    except Exception:
        return None

def buscar_medico_por_email(email):
    try:
        r = get_sb().table("medicos").select("*").eq("email", email).execute()
        return r.data[0] if r.data else None
    except Exception:
        return None

def buscar_medico_por_reset_token(token):
    try:
        r = get_sb().table("medicos").select("*").eq("reset_token", token).execute()
        return r.data[0] if r.data else None
    except Exception:
        return None

def actualizar_medico(email, datos):
    get_sb().table("medicos").update(datos).eq("email", email).execute()

def crear_medico(nombre, apellido, email):
    get_sb().table("medicos").insert({
        "nombre": nombre,
        "apellido": apellido,
        "email": email,
        "activo": True
    }).execute()

def guardar_nota_medico(codigo_paciente, medico_id, nota):
    get_sb().table("notas_medico").insert({
        "codigo_paciente": codigo_paciente,
        "medico_id": medico_id,
        "nota": nota,
        "fecha": datetime.now().isoformat()
    }).execute()

def obtener_notas_medico(codigo_paciente, medico_id):
    try:
        r = get_sb().table("notas_medico").select("*")\
            .eq("codigo_paciente", codigo_paciente)\
            .eq("medico_id", medico_id)\
            .order("fecha", desc=True).execute()
        return r.data
    except Exception:
        return []

def guardar_evento_adverso(codigo_paciente, descripcion, reportado_por="paciente"):
    try:
        get_sb().table("eventos_adversos").insert({
            "codigo_paciente": codigo_paciente,
            "descripcion": descripcion,
            "reportado_por": reportado_por,
            "fecha": datetime.now().isoformat()
        }).execute()
        return True
    except Exception:
        return False

def obtener_eventos_adversos(codigo_paciente):
    try:
        r = get_sb().table("eventos_adversos").select("*")\
            .eq("codigo_paciente", codigo_paciente)\
            .order("fecha", desc=True).execute()
        return r.data
    except Exception:
        return []

def generar_alerta(codigo_paciente, tipo, mensaje):
    try:
        get_sb().table("alertas").insert({
            "codigo_paciente": codigo_paciente,
            "tipo": tipo,
            "mensaje": mensaje,
            "fecha": datetime.now().isoformat()
        }).execute()
    except Exception:
        pass

def obtener_alertas(codigo_paciente):
    try:
        r = get_sb().table("alertas").select("*")\
            .eq("codigo_paciente", codigo_paciente)\
            .order("fecha", desc=True).execute()
        return r.data
    except Exception:
        return []

# ── Seguridad: contraseñas ────────────────────────────────────────────────────
def hash_password(pwd: str) -> str:
    return bcrypt.hashpw(pwd.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verificar_password(pwd: str, stored: str):
    """Devuelve (ok, nuevo_hash). nuevo_hash != None si hay que actualizar (upgrade desde SHA-256)."""
    if not pwd or not stored:
        return False, None
    if stored.startswith("$2"):  # bcrypt
        try:
            return bcrypt.checkpw(pwd.encode("utf-8"), stored.encode("utf-8")), None
        except Exception:
            return False, None
    # Legacy SHA-256 (64 caracteres hexadecimales) → verificar y migrar a bcrypt
    legacy = hashlib.sha256(pwd.encode("utf-8")).hexdigest()
    if legacy == stored:
        return True, hash_password(pwd)
    return False, None

# ── Email ─────────────────────────────────────────────────────────────────────
def enviar_bienvenida_paciente(nombre, email, codigo):
    try:
        resend.api_key = get_secret("resend", "api_key")
        url = f"{APP_URL}/?codigo={codigo}"
        resend.Emails.send({
            "from": "Arteris <noreply@arterismed.com>",
            "to": email,
            "subject": "Tu acceso a Arteris · Monitoreo Domiciliario de Presión Arterial",
            "html": f"""
            <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;background:#0a1628;color:#e8eef7;border-radius:12px;overflow:hidden;">
              <div style="background:#1d4ed8;padding:24px 32px;">
                <h1 style="font-size:24px;margin:0;color:white;font-weight:400;">Arteris</h1>
                <p style="font-size:12px;color:rgba(255,255,255,0.7);margin:4px 0 0;letter-spacing:1px;text-transform:uppercase;">Monitoreo Domiciliario de Presión Arterial</p>
              </div>
              <div style="padding:32px;">
                <p style="font-size:16px;">Hola <strong>{nombre}</strong>,</p>
                <p style="color:#94a3b8;line-height:1.6;">Tu médico te habilitó el acceso a Arteris. Hacé clic en el botón para activar tu cuenta y crear tu contraseña.</p>
                <div style="text-align:center;margin:32px 0;">
                  <a href="{url}" style="background:#1d4ed8;color:white;padding:14px 32px;text-decoration:none;border-radius:8px;font-size:15px;display:inline-block;">Activar mi cuenta</a>
                </div>
                <p style="font-size:12px;color:#64748b;">O copiá este enlace: {url}</p>
                <hr style="border-color:rgba(255,255,255,0.08);margin:24px 0;">
                <p style="font-size:11px;color:#64748b;">Esta plataforma es orientativa y no reemplaza la consulta médica.</p>
              </div>
            </div>"""
        })
        return True
    except Exception as e:
        st.error(f"Error al enviar el email: {e}")
        return False

def enviar_activacion_medico(nombre, email):
    try:
        resend.api_key = get_secret("resend", "api_key")
        token = str(uuid.uuid4())
        actualizar_medico(email, {
            "activation_token": token,
            "activation_token_used": False
        })
        link = f"{APP_URL}/?activar_medico={token}"
        resend.Emails.send({
            "from": "Arteris <noreply@arterismed.com>",
            "to": email,
            "subject": "Activá tu cuenta médica en Arteris",
            "html": f"""
            <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;background:#0a1628;color:#e8eef7;border-radius:12px;overflow:hidden;">
              <div style="background:#1d4ed8;padding:24px 32px;">
                <h1 style="font-size:24px;margin:0;color:white;font-weight:400;">Arteris</h1>
                <p style="font-size:12px;color:rgba(255,255,255,0.7);margin:4px 0 0;">Panel Médico</p>
              </div>
              <div style="padding:32px;">
                <p style="font-size:16px;">Hola Dr/Dra <strong>{nombre}</strong>,</p>
                <p style="color:#94a3b8;line-height:1.6;">Tu cuenta médica en Arteris fue creada. Hacé clic para activarla y crear tu contraseña.</p>
                <div style="text-align:center;margin:32px 0;">
                  <a href="{link}" style="background:#1d4ed8;color:white;padding:14px 32px;text-decoration:none;border-radius:8px;font-size:15px;display:inline-block;">Activar cuenta médica</a>
                </div>
                <p style="font-size:12px;color:#64748b;">O copiá este enlace: {link}</p>
                <hr style="border-color:rgba(255,255,255,0.08);margin:24px 0;">
                <p style="font-size:11px;color:#64748b;">Si no solicitaste este acceso, ignorá este email.</p>
              </div>
            </div>"""
        })
        return True
    except Exception as e:
        st.error(f"Error al enviar el email: {e}")
        return False

def enviar_reset_password(email, link, nombre=""):
    try:
        resend.api_key = get_secret("resend", "api_key")
        resend.Emails.send({
            "from": "Arteris <noreply@arterismed.com>",
            "to": email,
            "subject": "Recuperá tu contraseña de Arteris",
            "html": f"""
            <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;background:#0a1628;color:#e8eef7;border-radius:12px;overflow:hidden;">
              <div style="background:#1d4ed8;padding:24px 32px;">
                <h1 style="font-size:24px;margin:0;color:white;font-weight:400;">Arteris</h1>
              </div>
              <div style="padding:32px;">
                <p style="font-size:16px;">Hola{(' ' + nombre) if nombre else ''},</p>
                <p style="color:#94a3b8;line-height:1.6;">Recibimos una solicitud para restablecer tu contraseña. Hacé clic en el botón para crear una nueva.</p>
                <div style="text-align:center;margin:32px 0;">
                  <a href="{link}" style="background:#1d4ed8;color:white;padding:14px 32px;text-decoration:none;border-radius:8px;font-size:15px;display:inline-block;">Crear nueva contraseña</a>
                </div>
                <p style="font-size:12px;color:#64748b;">O copiá este enlace: {link}</p>
                <hr style="border-color:rgba(255,255,255,0.08);margin:24px 0;">
                <p style="font-size:11px;color:#64748b;">Si no solicitaste este cambio, ignorá este email.</p>
              </div>
            </div>"""
        })
        return True
    except Exception:
        return False

# ── Lógica médica ─────────────────────────────────────────────────────────────
def calcular_resultado(mediciones):
    """Calcula promedios y categoría del HBPM. Requiere las 28 tomas (7 días x 4).
    Descarta el día 1 y usa los días 2 a 7. Devuelve un dict o None."""
    if not mediciones or len(mediciones) < 28:
        return None
    df = pd.DataFrame(mediciones)
    df["fecha_dt"] = pd.to_datetime(df["fecha"])
    df["dia"] = df["fecha_dt"].dt.date
    dias = sorted(df["dia"].unique())
    if len(dias) >= 7:
        dias_validos = dias[1:7]
    elif len(dias) > 1:
        dias_validos = dias[1:]
    else:
        dias_validos = dias
    df = df[df["dia"].isin(dias_validos)]
    if df.empty:
        return None

    df["periodo"] = df["momento"].fillna("").apply(
        lambda m: "mañana" if str(m).startswith("mañana")
        else ("tarde" if str(m).startswith("tarde") else "otro"))
    manana = df[df["periodo"] == "mañana"]
    tarde = df[df["periodo"] == "tarde"]

    res = {
        "sis_manana": round(manana["sistolica"].mean(), 1) if not manana.empty else None,
        "dia_manana": round(manana["diastolica"].mean(), 1) if not manana.empty else None,
        "sis_tarde": round(tarde["sistolica"].mean(), 1) if not tarde.empty else None,
        "dia_tarde": round(tarde["diastolica"].mean(), 1) if not tarde.empty else None,
        "sis_general": round(df["sistolica"].mean(), 1),
        "dia_general": round(df["diastolica"].mean(), 1),
        "dias_usados": len(dias_validos),
    }

    diarios = df.groupby("dia").agg(
        sis_m=("sistolica", "mean"), dia_m=("diastolica", "mean")).reset_index()
    res["promedios_diarios"] = [
        {"fecha": str(r["dia"]), "sis": round(r["sis_m"], 1), "dia": round(r["dia_m"], 1)}
        for _, r in diarios.iterrows()
    ]

    s, d = res["sis_general"], res["dia_general"]
    if s >= 180 or d >= 110:
        res.update({
            "categoria": "urgente",
            "titulo": "🔴 Atención médica urgente",
            "mensaje": "En este Monitoreo Domiciliario de Presión Arterial su presión arterial "
                       "no se encuentra controlada según los actuales consensos y requiere de "
                       "atención médica urgente.",
            "tipo": "error",
        })
    elif s < 90 or d < 60:
        res.update({
            "categoria": "baja",
            "titulo": "🔵 Valores por debajo de lo óptimo",
            "mensaje": "Los valores de presión arterial se encuentran por debajo de las cifras "
                       "óptimas. Se sugiere control médico a la brevedad posible.",
            "tipo": "warning",
        })
    elif s < 135 and d < 85:
        res.update({
            "categoria": "controlada",
            "titulo": "✅ Presión arterial controlada",
            "mensaje": "En este Monitoreo Domiciliario de Presión Arterial su presión arterial "
                       "está controlada según los actuales consensos.",
            "tipo": "success",
        })
    else:
        res.update({
            "categoria": "no_controlada",
            "titulo": "⚠️ Presión arterial no controlada",
            "mensaje": "En este Monitoreo Domiciliario de Presión Arterial su presión arterial "
                       "no está controlada según los actuales consensos. Se sugiere consulta médica.",
            "tipo": "warning",
        })
    return res

def grafico_evolucion(mediciones):
    df = pd.DataFrame(mediciones)
    df["fecha_dt"] = pd.to_datetime(df["fecha"])
    df = df.sort_values("fecha_dt")
    df["etiqueta"] = df["fecha_dt"].dt.strftime("%d/%m") + " · " + df["momento"].fillna("")
    chart = alt.Chart(df).transform_fold(
        ["sistolica", "diastolica"], as_=["tipo", "valor"]
    ).mark_line(point=True).encode(
        x=alt.X("etiqueta:N", title="", sort=None, axis=alt.Axis(labelAngle=-45, labelColor="#94a3b8", gridColor="#1e293b")),
        y=alt.Y("valor:Q", title="mmHg", axis=alt.Axis(labelColor="#94a3b8", gridColor="#1e293b")),
        color=alt.Color("tipo:N", scale=alt.Scale(domain=["sistolica", "diastolica"], range=["#3b82f6", "#06b6d4"]),
                        legend=alt.Legend(labelColor="#94a3b8")),
        tooltip=["etiqueta:N", "sistolica:Q", "diastolica:Q", "momento:N"]
    ).properties(height=280, background="#0a1628").configure_view(strokeColor="#1e293b")
    st.altair_chart(chart, use_container_width=True)

# ── Exportación PDF ───────────────────────────────────────────────────────────
def _grafico_png(mediciones):
    """Devuelve un buffer PNG con la tendencia, o None si matplotlib no está disponible."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        df = pd.DataFrame(mediciones)
        df["fecha_dt"] = pd.to_datetime(df["fecha"])
        df = df.sort_values("fecha_dt")
        fig, ax = plt.subplots(figsize=(7, 2.8))
        x = list(range(len(df)))
        ax.plot(x, df["sistolica"], marker="o", markersize=3, color="#1d4ed8", label="Sistólica")
        ax.plot(x, df["diastolica"], marker="o", markersize=3, color="#06b6d4", label="Diastólica")
        ax.axhline(135, color="#dc2626", linestyle="--", linewidth=0.7)
        ax.axhline(85, color="#dc2626", linestyle="--", linewidth=0.7)
        ax.set_ylabel("mmHg", fontsize=8)
        ax.set_xlabel("Tomas (orden cronológico)", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.legend(loc="upper right", fontsize=7)
        ax.grid(alpha=0.2)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=130)
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception:
        return None

def generar_pdf_hbpm(paciente, mediciones, resultado, eventos, alertas):
    """Genera el PDF del informe HBPM. Devuelve bytes."""
    from fpdf import FPDF

    def t(s):
        return str(s if s is not None else "").encode("latin-1", "replace").decode("latin-1")

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Encabezado
    pdf.set_fill_color(29, 78, 216)
    pdf.rect(0, 0, 210, 26, "F")
    pdf.set_xy(12, 7)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 8, t("Arteris"), ln=1)
    pdf.set_x(12)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, t("Monitoreo Domiciliario de Presión Arterial (HBPM)"), ln=1)
    pdf.ln(8)
    pdf.set_text_color(20, 20, 20)

    # Datos del paciente
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, t("Datos del paciente"), ln=1)
    pdf.set_font("Helvetica", "", 10)
    nombre = f"{paciente.get('nombre','')} {paciente.get('apellido','')}".strip()
    pdf.cell(95, 6, t(f"Nombre: {nombre}"), 0, 0)
    pdf.cell(0, 6, t(f"Código: {paciente.get('codigo','')}"), 0, 1)
    pdf.cell(95, 6, t(f"Edad: {paciente.get('edad','-')}"), 0, 0)
    pdf.cell(0, 6, t(f"Sexo: {paciente.get('sexo','-')}"), 0, 1)
    pdf.cell(0, 6, t(f"Fecha del informe: {datetime.now().strftime('%d/%m/%Y')}"), 0, 1)
    pdf.ln(3)

    # Tratamiento médico
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, t("Tratamiento médico"), ln=1)
    pdf.set_font("Helvetica", "", 10)
    if paciente.get("toma_medicacion"):
        pdf.cell(0, 6, t(f"Fármaco: {paciente.get('medicacion','-') or '-'}"), 0, 1)
        pdf.cell(0, 6, t(f"Dosis: {paciente.get('dosis','-') or '-'}"), 0, 1)
    else:
        pdf.cell(0, 6, t("No recibe medicación para la presión arterial."), 0, 1)
    pdf.ln(3)

    # Registros de los 7 días
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, t("Registros del HBPM (7 días)"), ln=1)
    pdf.set_font("Helvetica", "B", 8)
    orden = ["mañana-1", "mañana-2", "tarde-1", "tarde-2"]
    cols = ["Día"] + ["Mañana 1", "Mañana 2", "Tarde 1", "Tarde 2"]
    anchos = [30, 40, 40, 40, 40]
    pdf.set_fill_color(230, 235, 245)
    for c, w in zip(cols, anchos):
        pdf.cell(w, 7, t(c), 1, 0, "C", True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 8)
    if mediciones:
        df = pd.DataFrame(mediciones)
        df["fecha_dt"] = pd.to_datetime(df["fecha"])
        df["dia"] = df["fecha_dt"].dt.date
        for i, dia in enumerate(sorted(df["dia"].unique()), start=1):
            sub = df[df["dia"] == dia]
            pdf.cell(anchos[0], 7, t(f"Día {i} ({dia.strftime('%d/%m')})"), 1, 0, "C")
            for j, mom in enumerate(orden):
                fila = sub[sub["momento"] == mom]
                if not fila.empty:
                    v = f"{int(fila.iloc[0]['sistolica'])}/{int(fila.iloc[0]['diastolica'])}"
                else:
                    v = "-"
                pdf.cell(anchos[j + 1], 7, t(v), 1, 0, "C")
            pdf.ln()
    pdf.ln(3)

    # Resultado
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, t("Resultado del monitoreo"), ln=1)
    pdf.set_font("Helvetica", "", 10)
    if resultado:
        pdf.cell(0, 6, t(f"Promedio mañana: {resultado.get('sis_manana','-')}/{resultado.get('dia_manana','-')} mmHg"), 0, 1)
        pdf.cell(0, 6, t(f"Promedio tarde: {resultado.get('sis_tarde','-')}/{resultado.get('dia_tarde','-')} mmHg"), 0, 1)
        pdf.cell(0, 6, t(f"Promedio general (días 2 a 7): {resultado.get('sis_general','-')}/{resultado.get('dia_general','-')} mmHg"), 0, 1)
        pdf.ln(1)
        titulo_limpio = "".join(c for c in resultado.get("titulo", "") if ord(c) < 256).strip()
        pdf.set_font("Helvetica", "B", 10)
        pdf.multi_cell(0, 6, t(titulo_limpio))
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5, t(resultado.get("mensaje", "")))
    else:
        pdf.cell(0, 6, t("Monitoreo incompleto: faltan registros para calcular el resultado."), 0, 1)
    pdf.ln(3)

    # Tendencia gráfica
    grafico = _grafico_png(mediciones)
    if grafico is not None:
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, t("Tendencia gráfica"), ln=1)
        try:
            pdf.image(grafico, w=180)
        except Exception:
            pass
        pdf.ln(3)

    # Eventos adversos
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, t("Eventos adversos / clínicos reportados"), ln=1)
    pdf.set_font("Helvetica", "", 9)
    if eventos:
        for ev in eventos:
            pdf.multi_cell(0, 5, t(f"- [{str(ev.get('fecha',''))[:10]}] {ev.get('descripcion','')}"))
    else:
        pdf.cell(0, 6, t("Sin eventos reportados."), 0, 1)
    pdf.ln(2)

    # Alertas
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, t("Alertas generadas"), ln=1)
    pdf.set_font("Helvetica", "", 9)
    if alertas:
        for al in alertas:
            pdf.multi_cell(0, 5, t(f"- [{str(al.get('fecha',''))[:10]}] {al.get('mensaje','')}"))
    else:
        pdf.cell(0, 6, t("Sin alertas generadas."), 0, 1)
    pdf.ln(4)

    # Pie / descargo
    pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(120, 120, 120)
    pdf.multi_cell(0, 4, t(
        "Informe orientativo generado por la plataforma Arteris. No constituye un diagnóstico médico "
        "y no reemplaza la consulta con un profesional de la salud. Datos tratados conforme a la "
        "Ley 25.326 de Protección de Datos Personales."))

    out = pdf.output()
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    return out.encode("latin-1")

# ══════════════════════════════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════════════════════════════
params = st.query_params
codigo_url = params.get("codigo", "")
vista_url = params.get("vista", "")

if "vista" not in st.session_state:
    if codigo_url:
        st.session_state.vista = "paciente_login"
    elif vista_url == "medico":
        st.session_state.vista = "medico_login"
    else:
        st.session_state.vista = "inicio"

if "codigo_paciente" not in st.session_state:
    st.session_state.codigo_paciente = codigo_url
if "usuario" not in st.session_state:
    st.session_state.usuario = None
if "rol" not in st.session_state:
    st.session_state.rol = None
if "medico_data" not in st.session_state:
    st.session_state.medico_data = None
if "paciente_data" not in st.session_state:
    st.session_state.paciente_data = None
if "consentimiento_ok" not in st.session_state:
    st.session_state.consentimiento_ok = False
if "activar_medico_token" not in st.session_state:
    st.session_state.activar_medico_token = params.get("activar_medico", "")
if "reset_token" not in st.session_state:
    st.session_state.reset_token = params.get("reset", "")

def cerrar_sesion():
    for k in ["vista", "usuario", "rol", "medico_data", "paciente_data", "codigo_paciente", "consentimiento_ok"]:
        if k in st.session_state:
            del st.session_state[k]
    st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA: POLÍTICA DE PRIVACIDAD Y TÉRMINOS
# ══════════════════════════════════════════════════════════════════════════════
if vista_url == "privacidad":
    navbar("Privacidad y términos")
    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        st.markdown("""
        <div class="art-card">
        <div class="section-eyebrow">Documento legal</div>
        <h2 style="font-family:'DM Serif Display',serif;color:#e8eef7;">Política de privacidad y términos de uso</h2>

        <h4 style="color:#e8eef7;">1. Responsable del tratamiento</h4>
        <p style="color:#94a3b8;font-size:14px;line-height:1.7;">Arteris es una plataforma de monitoreo
        domiciliario de presión arterial. El tratamiento de los datos personales se realiza conforme a la
        <strong style="color:#e8eef7;">Ley 25.326 de Protección de Datos Personales</strong> de la República Argentina.</p>

        <h4 style="color:#e8eef7;">2. Datos que se recopilan</h4>
        <p style="color:#94a3b8;font-size:14px;line-height:1.7;">Nombre, apellido, email, edad y sexo biológico;
        medicación actual y dosis; y los valores de presión arterial cargados durante el monitoreo de 7 días.
        Los valores de presión arterial constituyen <strong style="color:#e8eef7;">datos sensibles de salud</strong>
        y reciben protección reforzada.</p>

        <h4 style="color:#e8eef7;">3. Finalidad del tratamiento</h4>
        <p style="color:#94a3b8;font-size:14px;line-height:1.7;">Los datos se utilizan exclusivamente para
        calcular los promedios de presión arterial, mostrar un resultado orientativo y permitir el seguimiento
        por parte del médico tratante. No se utilizan con fines publicitarios ni se ceden a terceros.</p>

        <h4 style="color:#e8eef7;">4. Acceso a los datos</h4>
        <p style="color:#94a3b8;font-size:14px;line-height:1.7;">Solo el propio paciente y su médico tratante
        acceden a la información del paciente. El acceso está protegido por usuario y contraseña cifrada.</p>

        <h4 style="color:#e8eef7;">5. Derechos del titular (Ley 25.326)</h4>
        <p style="color:#94a3b8;font-size:14px;line-height:1.7;">El titular puede ejercer en cualquier momento
        sus derechos de acceso, rectificación, actualización y supresión de sus datos personales contactando
        a su médico tratante o al responsable de la plataforma.</p>

        <h4 style="color:#e8eef7;">6. Seguridad y conservación</h4>
        <p style="color:#94a3b8;font-size:14px;line-height:1.7;">Los datos se almacenan en servidores con
        cifrado en tránsito y en reposo, con copias de seguridad periódicas. Las contraseñas se guardan
        cifradas (hash). El secreto profesional se encuentra amparado por la Ley 17.132.</p>

        <h4 style="color:#e8eef7;">7. Términos de uso</h4>
        <p style="color:#94a3b8;font-size:14px;line-height:1.7;">Arteris es una herramienta de monitoreo
        <strong style="color:#e8eef7;">orientativa</strong>. Los resultados <strong style="color:#e8eef7;">no
        constituyen un diagnóstico médico</strong> y no reemplazan la consulta con un profesional de la salud.
        El usuario es responsable de ingresar datos correctos. Arteris no se responsabiliza por decisiones
        médicas tomadas sobre la base de los resultados de la plataforma.</p>

        <h4 style="color:#e8eef7;">8. Recordatorios por email</h4>
        <p style="color:#94a3b8;font-size:14px;line-height:1.7;">Si el usuario lo autoriza, recibirá
        recordatorios por email únicamente para cargar sus mediciones de presión arterial. Estos emails no
        contienen publicidad ni información de terceros, y la preferencia puede desactivarse en cualquier momento.</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("← Volver al inicio", use_container_width=True):
            st.query_params.clear()
            st.session_state.vista = "inicio"
            st.rerun()
    footer()
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# RECUPERACIÓN DE CONTRASEÑA (paciente y médico)
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.reset_token:
    token = st.session_state.reset_token
    navbar("Restablecer contraseña")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        paciente = buscar_paciente_por_reset_token(token)
        medico = None if paciente else buscar_medico_por_reset_token(token)

        if not paciente and not medico:
            st.error("❌ Enlace de recuperación inválido o expirado.")
            if st.button("Ir al inicio", use_container_width=True):
                st.session_state.reset_token = ""
                st.query_params.clear()
                st.session_state.vista = "inicio"
                st.rerun()
        else:
            quien = paciente or medico
            nombre = quien.get("nombre", "")
            st.markdown('<div class="art-card">', unsafe_allow_html=True)
            st.markdown(f"### 🔐 Hola {nombre}, creá tu nueva contraseña")
            with st.form("form_reset"):
                p1 = st.text_input("Nueva contraseña", type="password", placeholder="Mínimo 8 caracteres")
                p2 = st.text_input("Confirmá la nueva contraseña", type="password")
                ok = st.form_submit_button("Guardar nueva contraseña", use_container_width=True)
            if ok:
                if len(p1) < 8:
                    st.error("La contraseña debe tener al menos 8 caracteres.")
                elif p1 != p2:
                    st.error("Las contraseñas no coinciden.")
                else:
                    nuevo_hash = hash_password(p1)
                    if paciente:
                        actualizar_paciente(paciente["codigo"], {
                            "password_hash": nuevo_hash,
                            "password_set": True,
                            "reset_token": None
                        })
                    else:
                        actualizar_medico(medico["email"], {
                            "password_hash": nuevo_hash,
                            "password_set": True,
                            "reset_token": None
                        })
                    st.session_state.reset_token = ""
                    st.success("✅ Contraseña actualizada. Ya podés iniciar sesión.")
                    if st.button("Ir al login", use_container_width=True):
                        st.query_params.clear()
                        st.session_state.vista = "paciente_login" if paciente else "medico_login"
                        st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
    footer()
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# ACTIVACIÓN DE MÉDICO
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.activar_medico_token:
    token = st.session_state.activar_medico_token
    try:
        r = get_sb().table("medicos").select("*").eq("activation_token", token).execute()
        medico = r.data[0] if r.data else None
    except Exception:
        medico = None

    navbar("Activación de cuenta médica")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if not medico:
            st.error("❌ Enlace de activación inválido o expirado.")
        elif medico.get("activation_token_used") and medico.get("password_set"):
            st.warning("Este enlace ya fue usado. Iniciá sesión normalmente.")
            if st.button("Ir al login →", use_container_width=True):
                st.session_state.activar_medico_token = ""
                st.session_state.vista = "medico_login"
                st.rerun()
        else:
            st.markdown('<div class="art-card">', unsafe_allow_html=True)
            st.markdown(f"### 👨‍⚕️ Hola, Dr/Dra. {medico.get('nombre','')} {medico.get('apellido','')}")
            st.markdown('<p style="font-size:13px;color:#94a3b8;margin-bottom:1rem;">Creá tu contraseña para acceder al panel médico de Arteris.</p>', unsafe_allow_html=True)
            with st.form("form_activacion_medico"):
                pwd1 = st.text_input("Contraseña", type="password", placeholder="Mínimo 8 caracteres")
                pwd2 = st.text_input("Confirmá la contraseña", type="password")
                ok = st.form_submit_button("Activar mi cuenta →", use_container_width=True)
            if ok:
                if len(pwd1) < 8:
                    st.error("La contraseña debe tener al menos 8 caracteres.")
                elif pwd1 != pwd2:
                    st.error("Las contraseñas no coinciden.")
                else:
                    pwd_hash = hash_password(pwd1)
                    get_sb().table("medicos").update({
                        "password_hash": pwd_hash,
                        "password_set": True,
                        "activation_token_used": True
                    }).eq("activation_token", token).execute()
                    medico["password_set"] = True
                    st.session_state.medico_data = medico
                    st.session_state.rol = "medico"
                    st.session_state.activar_medico_token = ""
                    st.session_state.vista = "medico_home"
                    st.success("✅ ¡Cuenta activada! Bienvenido a Arteris.")
                    st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
    footer()
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# VISTA: INICIO
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.vista == "inicio":
    navbar()
    col_left, col_right = st.columns([1.2, 1], gap="large")
    with col_left:
        st.markdown("""
        <div class="section-eyebrow">Monitoreo Domiciliario de Presión Arterial</div>
        <div class="section-title">Control preciso.<br><em style="color:#3b82f6;font-style:italic;">Resultados claros.</em></div>
        <div class="section-sub">Una herramienta reconocida mundialmente para un mejor control de la presión arterial. Registrá tu presión durante 7 días y recibí un resultado orientativo basado en consensos médicos internacionales.</div>
        """, unsafe_allow_html=True)
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("🙋 Soy paciente", use_container_width=True):
                st.session_state.vista = "paciente_login"
                st.rerun()
        with col_b:
            if st.button("👨‍⚕️ Soy médico", use_container_width=True):
                st.session_state.vista = "medico_login"
                st.rerun()
        st.markdown("""
        <div style="display:flex;gap:2rem;margin-top:2rem;">
            <div style="text-align:center;"><div style="font-family:'DM Serif Display',serif;font-size:28px;color:#3b82f6;">+200</div><div style="font-size:12px;color:#94a3b8;">Pacientes</div></div>
            <div style="text-align:center;"><div style="font-family:'DM Serif Display',serif;font-size:28px;color:#3b82f6;">7</div><div style="font-size:12px;color:#94a3b8;">Días de seguimiento</div></div>
            <div style="text-align:center;"><div style="font-family:'DM Serif Display',serif;font-size:28px;color:#3b82f6;">135/85</div><div style="font-size:12px;color:#94a3b8;">Umbral de control</div></div>
        </div>
        """, unsafe_allow_html=True)
    with col_right:
        st.markdown("""
        <div class="art-card">
            <div style="font-size:11px;color:#94a3b8;letter-spacing:1px;text-transform:uppercase;margin-bottom:12px;">¿Cómo funciona?</div>
            <div style="display:flex;flex-direction:column;gap:14px;">
                <div style="display:flex;gap:12px;align-items:flex-start;">
                    <div style="width:28px;height:28px;border-radius:50%;background:#1d4ed8;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:500;flex-shrink:0;">1</div>
                    <div><div style="font-size:14px;color:#e8eef7;font-weight:500;">Tu médico te envía el acceso</div><div style="font-size:12px;color:#94a3b8;margin-top:2px;">Recibís un email con tu enlace de activación</div></div>
                </div>
                <div style="display:flex;gap:12px;align-items:flex-start;">
                    <div style="width:28px;height:28px;border-radius:50%;background:#1d4ed8;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:500;flex-shrink:0;">2</div>
                    <div><div style="font-size:14px;color:#e8eef7;font-weight:500;">Creás tu contraseña</div><div style="font-size:12px;color:#94a3b8;margin-top:2px;">Activás tu cuenta y completás tus datos</div></div>
                </div>
                <div style="display:flex;gap:12px;align-items:flex-start;">
                    <div style="width:28px;height:28px;border-radius:50%;background:#1d4ed8;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:500;flex-shrink:0;">3</div>
                    <div><div style="font-size:14px;color:#e8eef7;font-weight:500;">Registrás tu presión 7 días</div><div style="font-size:12px;color:#94a3b8;margin-top:2px;">2 tomas mañana y tarde, resultado al final</div></div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    footer()

# ══════════════════════════════════════════════════════════════════════════════
# VISTA: AJUSTES PACIENTE
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.vista == "paciente_ajustes":
    paciente = st.session_state.paciente_data
    if not paciente:
        st.session_state.vista = "paciente_login"
        st.rerun()

    nombre = paciente.get("nombre", "Paciente")
    navbar(f"Ajustes · {nombre}")

    col_nav1, col_nav2 = st.columns([6, 1])
    with col_nav2:
        with st.popover("⚙️ " + nombre[:10]):
            st.markdown(f'<p style="font-size:13px;color:#94a3b8;margin-bottom:8px;">Sesión activa como<br><strong style="color:#e8eef7;">{nombre}</strong></p>', unsafe_allow_html=True)
            st.divider()
            if st.button("🏠 Inicio", use_container_width=True):
                st.session_state.vista = "paciente_home"
                st.rerun()
            if st.button("🚪 Cerrar sesión", use_container_width=True):
                cerrar_sesion()

    st.markdown("### ⚙️ Ajustes de tu cuenta")
    st.markdown("---")

    col1, col2 = st.columns([1, 1], gap="large")

    with col1:
        st.markdown('<div class="art-card">', unsafe_allow_html=True)
        st.markdown("#### 📧 Recordatorios por email")
        st.markdown('<p style="font-size:13px;color:#94a3b8;">Recibirás un recordatorio para cargar tu presión arterial a las 10 y a las 18 hs cada día.</p>', unsafe_allow_html=True)
        recordatorios_actual = paciente.get("recordatorios_email", True)
        nuevo_valor = st.toggle("Activar recordatorios por email", value=recordatorios_actual)
        if nuevo_valor != recordatorios_actual:
            actualizar_paciente(paciente["codigo"], {"recordatorios_email": nuevo_valor})
            st.session_state.paciente_data = buscar_paciente(paciente["codigo"])
            st.success("✅ Preferencia guardada.")
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="art-card">', unsafe_allow_html=True)
        st.markdown("#### 🔐 Cambiar contraseña")
        with st.form("form_cambiar_pwd"):
            pwd_actual = st.text_input("Contraseña actual", type="password")
            pwd_nueva = st.text_input("Nueva contraseña", type="password", placeholder="Mínimo 8 caracteres")
            pwd_conf = st.text_input("Confirmá la nueva contraseña", type="password")
            cambiar = st.form_submit_button("Cambiar contraseña", use_container_width=True)
        if cambiar:
            ok_actual, _ = verificar_password(pwd_actual, paciente.get("password_hash", ""))
            if not ok_actual:
                st.error("❌ La contraseña actual es incorrecta.")
            elif len(pwd_nueva) < 8:
                st.error("La nueva contraseña debe tener al menos 8 caracteres.")
            elif pwd_nueva != pwd_conf:
                st.error("Las contraseñas no coinciden.")
            else:
                actualizar_paciente(paciente["codigo"], {"password_hash": hash_password(pwd_nueva)})
                st.session_state.paciente_data = buscar_paciente(paciente["codigo"])
                st.success("✅ Contraseña actualizada correctamente.")
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="art-card" style="margin-top:1rem;">', unsafe_allow_html=True)
    st.markdown("#### 👤 Mis datos personales")
    col_d1, col_d2, col_d3 = st.columns(3)
    with col_d1:
        st.markdown(f'<div class="art-metric"><div class="art-metric-num" style="font-size:24px;">{paciente.get("edad","—")}</div><div class="art-metric-label">Edad</div></div>', unsafe_allow_html=True)
    with col_d2:
        st.markdown(f'<div class="art-metric"><div class="art-metric-num" style="font-size:18px;">{paciente.get("sexo","—")}</div><div class="art-metric-label">Sexo biológico</div></div>', unsafe_allow_html=True)
    with col_d3:
        med_txt = paciente.get("medicacion", "Ninguna") or "Ninguna"
        st.markdown(f'<div class="art-metric"><div class="art-metric-num" style="font-size:16px;">{med_txt}</div><div class="art-metric-label">Medicación</div></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    if st.button("← Volver al inicio"):
        st.session_state.vista = "paciente_home"
        st.rerun()

    footer()

# ══════════════════════════════════════════════════════════════════════════════
# VISTA: LOGIN PACIENTE
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.vista == "paciente_login":
    navbar("Portal del paciente")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("← Volver"):
            st.session_state.vista = "inicio"
            st.rerun()

        # Si viene con código en la URL → activación de cuenta nueva
        if st.session_state.codigo_paciente:
            paciente = buscar_paciente(st.session_state.codigo_paciente)
            if paciente and not paciente.get("password_set"):
                st.markdown('<div class="art-card">', unsafe_allow_html=True)
                st.markdown("### 🔐 Activá tu cuenta")
                st.markdown(f'<p style="font-size:14px;color:#94a3b8;">Hola <strong style="color:#e8eef7;">{paciente.get("nombre","")}</strong>, creá tu contraseña para acceder a Arteris.</p>', unsafe_allow_html=True)
                with st.form("form_activacion"):
                    pwd1 = st.text_input("Contraseña", type="password", placeholder="Mínimo 8 caracteres")
                    pwd2 = st.text_input("Confirmá la contraseña", type="password")
                    ok = st.form_submit_button("Activar mi cuenta →", use_container_width=True)
                if ok:
                    if len(pwd1) < 8:
                        st.error("La contraseña debe tener al menos 8 caracteres.")
                    elif pwd1 != pwd2:
                        st.error("Las contraseñas no coinciden.")
                    else:
                        actualizar_paciente(st.session_state.codigo_paciente, {
                            "password_hash": hash_password(pwd1),
                            "password_set": True
                        })
                        paciente = buscar_paciente(st.session_state.codigo_paciente)
                        st.session_state.paciente_data = paciente
                        st.session_state.rol = "paciente"
                        st.session_state.vista = "paciente_home"
                        st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
            elif paciente and paciente.get("password_set"):
                # Cuenta ya activada → debe ingresar con email y contraseña (sin auto-login)
                st.info("Tu cuenta ya está activada. Ingresá con tu email y contraseña.")
                st.markdown('<div class="art-card">', unsafe_allow_html=True)
                st.markdown("### Ingresar a Arteris")
                with st.form("form_login_codigo"):
                    email_input = st.text_input("Email", value=paciente.get("email", ""))
                    pwd_input = st.text_input("Contraseña", type="password")
                    login_ok = st.form_submit_button("Ingresar →", use_container_width=True)
                if login_ok:
                    p = buscar_paciente_por_email(email_input.strip().lower())
                    if p and p.get("password_set"):
                        ok_pwd, nuevo_hash = verificar_password(pwd_input, p.get("password_hash", ""))
                        if ok_pwd:
                            if nuevo_hash:
                                actualizar_paciente(p["codigo"], {"password_hash": nuevo_hash})
                            st.session_state.paciente_data = p
                            st.session_state.codigo_paciente = p["codigo"]
                            st.session_state.rol = "paciente"
                            st.session_state.vista = "paciente_home"
                            st.rerun()
                        else:
                            st.error("❌ Contraseña incorrecta.")
                    else:
                        st.error("❌ Email no encontrado o cuenta no activada.")
                st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.error("❌ El enlace no es válido. Pedile a tu médico que te reenvíe el acceso.")
        else:
            # Login normal con email y contraseña
            tab_login, tab_reset = st.tabs(["Iniciar sesión", "Olvidé mi contraseña"])
            with tab_login:
                st.markdown('<div class="art-card">', unsafe_allow_html=True)
                st.markdown("### Ingresar a Arteris")
                with st.form("form_login_paciente"):
                    email_input = st.text_input("Email", placeholder="tu@email.com")
                    pwd_input = st.text_input("Contraseña", type="password")
                    login_ok = st.form_submit_button("Ingresar →", use_container_width=True)
                if login_ok:
                    paciente = buscar_paciente_por_email(email_input.strip().lower())
                    if paciente and paciente.get("password_set"):
                        ok_pwd, nuevo_hash = verificar_password(pwd_input, paciente.get("password_hash", ""))
                        if ok_pwd:
                            if nuevo_hash:
                                actualizar_paciente(paciente["codigo"], {"password_hash": nuevo_hash})
                            st.session_state.paciente_data = paciente
                            st.session_state.codigo_paciente = paciente["codigo"]
                            st.session_state.rol = "paciente"
                            st.session_state.vista = "paciente_home"
                            st.rerun()
                        else:
                            st.error("❌ Contraseña incorrecta.")
                    else:
                        st.error("❌ Email no encontrado o cuenta no activada.")
                st.markdown('</div>', unsafe_allow_html=True)
            with tab_reset:
                st.markdown('<div class="art-card">', unsafe_allow_html=True)
                st.markdown("### Recuperar contraseña")
                email_reset = st.text_input("Tu email registrado")
                if st.button("Enviar instrucciones", use_container_width=True):
                    paciente = buscar_paciente_por_email(email_reset.strip().lower())
                    if paciente:
                        reset_token = str(uuid.uuid4())
                        actualizar_paciente(paciente["codigo"], {"reset_token": reset_token})
                        reset_url = f"{APP_URL}/?reset={reset_token}"
                        enviar_reset_password(email_reset, reset_url, paciente.get("nombre", ""))
                    st.success("✅ Si el email existe, recibirás instrucciones para recuperar tu contraseña.")
                st.markdown('</div>', unsafe_allow_html=True)
    footer()

# ══════════════════════════════════════════════════════════════════════════════
# VISTA: HOME PACIENTE
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.vista == "paciente_home":
    paciente = st.session_state.paciente_data
    if not paciente:
        st.session_state.vista = "paciente_login"
        st.rerun()

    codigo = paciente["codigo"]
    nombre = paciente.get("nombre", "Paciente")
    navbar(f"Hola, {nombre}")

    col_nav1, col_nav2 = st.columns([6, 1])
    with col_nav2:
        with st.popover("⚙️ " + nombre[:10]):
            st.markdown(f'<p style="font-size:13px;color:#94a3b8;margin-bottom:8px;">Sesión activa como<br><strong style="color:#e8eef7;">{nombre} {paciente.get("apellido","")}</strong></p>', unsafe_allow_html=True)
            st.divider()
            if st.button("⚙️ Ajustes", use_container_width=True):
                st.session_state.vista = "paciente_ajustes"
                st.rerun()
            if st.button("🚪 Cerrar sesión", use_container_width=True):
                cerrar_sesion()

    # Consentimiento
    if not paciente.get("consentimiento_aceptado") and not st.session_state.consentimiento_ok:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown('<div class="art-card">', unsafe_allow_html=True)
            st.markdown("### 📄 Consentimiento y términos de uso")
            st.markdown("""
<div style="background:rgba(59,130,246,0.08);border:1px solid rgba(59,130,246,0.2);border-radius:10px;padding:1.25rem;font-size:13px;color:#94a3b8;line-height:1.7;max-height:300px;overflow-y:auto;">
<strong style="color:#e8eef7;font-size:14px;">Consentimiento informado</strong><br><br>
<strong style="color:#e8eef7;">Datos que almacenamos:</strong><br>
- Nombre, apellido, edad y sexo biológico<br>
- Medicación actual y dosis<br>
- Valores de presión arterial durante 7 días<br><br>
<strong style="color:#e8eef7;">Uso de los datos:</strong><br>
Tus datos se utilizan únicamente para calcular el promedio de tu presión arterial y mostrarte un resultado orientativo. Solo vos y tu médico tratante pueden acceder a tu información.<br><br>
<strong style="color:#e8eef7;">Tus derechos (Ley 25.326):</strong><br>
Tenés derecho a acceder, rectificar y suprimir tus datos personales en cualquier momento contactando a tu médico tratante.<br><br>
<hr style="border-color:rgba(255,255,255,0.08);margin:12px 0;">
<strong style="color:#e8eef7;font-size:14px;">Términos y condiciones de uso</strong><br><br>
<strong style="color:#e8eef7;">Naturaleza del servicio:</strong><br>
Arteris es una plataforma de monitoreo orientativo. Los resultados que proporciona <strong style="color:#e8eef7;">no constituyen un diagnóstico médico</strong> y no reemplazan la consulta con un profesional de la salud.<br><br>
<strong style="color:#e8eef7;">Responsabilidad:</strong><br>
El usuario asume la responsabilidad de ingresar datos correctos. Arteris no se responsabiliza por decisiones médicas tomadas en base a los resultados de la plataforma.<br><br>
<strong style="color:#e8eef7;">Seguridad:</strong><br>
Los datos se almacenan de forma segura y cifrada. No se comparten con terceros bajo ninguna circunstancia.
</div>
            """, unsafe_allow_html=True)
            st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)
            aceptar_consentimiento = st.checkbox("Leí y acepto el consentimiento informado y el uso de mis datos personales")
            aceptar_terminos = st.checkbox("Leí y acepto los términos y condiciones de uso de Arteris")
            ambos = aceptar_consentimiento and aceptar_terminos
            if st.button("Continuar →", use_container_width=True, disabled=not ambos):
                st.session_state.consentimiento_ok = True
                actualizar_paciente(codigo, {"consentimiento_aceptado": True})
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    # Registro de datos personales
    elif not paciente.get("edad"):
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown('<div class="art-card">', unsafe_allow_html=True)
            st.markdown("### 📋 Completá tus datos")
            with st.form("form_registro"):
                edad = st.number_input("Edad", min_value=1, max_value=120, step=1)
                sexo = st.selectbox("Sexo biológico", ["Femenino", "Masculino", "Otro"])
                toma_med = st.radio("¿Tomás medicación para la presión arterial?", ["No", "Sí"], horizontal=True)
                medicacion = ""
                dosis = ""
                if toma_med == "Sí":
                    medicacion = st.text_input("¿Qué medicación tomás?", placeholder="Ej: Enalapril")
                    dosis = st.text_input("¿Cuál es la dosis?", placeholder="Ej: 10mg cada 12hs")
                recordatorios = st.checkbox("✉️ Quiero recibir recordatorios por email para cargar mi presión arterial", value=True)
                st.markdown('<div style="font-size:11px;color:#64748b;margin-top:-8px;">Recibirás un recordatorio a las 10 y a las 18 hs cada día durante los 7 días del seguimiento.</div>', unsafe_allow_html=True)
                enviado = st.form_submit_button("Guardar y comenzar →", use_container_width=True)
            if enviado and edad:
                actualizar_paciente(codigo, {
                    "edad": int(edad), "sexo": sexo,
                    "toma_medicacion": toma_med == "Sí",
                    "medicacion": medicacion, "dosis": dosis,
                    "recordatorios_email": recordatorios,
                    "consentimiento_aceptado": True
                })
                st.session_state.paciente_data = buscar_paciente(codigo)
                st.success("✅ ¡Registro completado!")
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    # Homepage principal
    else:
        mediciones = obtener_mediciones(codigo)
        total = len(mediciones)
        hoy = date.today()
        med_hoy = [m for m in mediciones if pd.to_datetime(m["fecha"]).date() == hoy]
        momentos_hoy = [m["momento"] for m in med_hoy]
        tomas_orden = ["mañana-1", "mañana-2", "tarde-1", "tarde-2"]
        proxima = next((tt for tt in tomas_orden if tt not in momentos_hoy), None)
        dias_completos = len(set(pd.to_datetime(m["fecha"]).date() for m in mediciones))

        col_h1, col_h2 = st.columns([2, 1])
        with col_h1:
            st.markdown(f"""
            <div style="margin-bottom:1.5rem;">
                <div class="section-eyebrow">Bienvenido de nuevo</div>
                <div class="section-title">{nombre} 👋</div>
            </div>
            """, unsafe_allow_html=True)
        with col_h2:
            st.markdown(f'<div class="art-metric"><div class="art-metric-num">{dias_completos}/7</div><div class="art-metric-label">Días completados</div></div>', unsafe_allow_html=True)

        dias_labels = ["D1", "D2", "D3", "D4", "D5", "D6", "D7"]
        dias_html = ""
        for i, l in enumerate(dias_labels):
            if i < dias_completos - 1:
                cls = "day-done"
            elif i == dias_completos - 1 and dias_completos > 0:
                cls = "day-today"
            else:
                cls = "day-pending"
            dias_html += f'<div class="day-dot {cls}">{l}</div>'

        pct = min(total / 28, 1.0)
        st.markdown(f"""
        <div class="art-card-white">
            <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
                <span style="font-size:13px;color:#94a3b8;">Progreso del seguimiento</span>
                <span style="font-size:13px;color:#3b82f6;font-weight:500;">{total}/28 tomas</span>
            </div>
            <div class="art-progress-wrap"><div class="art-progress-fill" style="width:{pct*100:.0f}%"></div></div>
            <div class="day-dots">{dias_html}</div>
        </div>
        """, unsafe_allow_html=True)

        seccion_pasos()

        st.markdown("---")

        if total >= 28:
            resultado = calcular_resultado(mediciones)
            st.markdown("### 🎯 Resultado de tu monitoreo")
            if resultado:
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.markdown(f'<div class="art-metric"><div class="art-metric-num" style="font-size:22px;">{resultado["sis_manana"]}/{resultado["dia_manana"]}</div><div class="art-metric-label">Promedio mañana</div></div>', unsafe_allow_html=True)
                with c2:
                    st.markdown(f'<div class="art-metric"><div class="art-metric-num" style="font-size:22px;">{resultado["sis_tarde"]}/{resultado["dia_tarde"]}</div><div class="art-metric-label">Promedio tarde</div></div>', unsafe_allow_html=True)
                with c3:
                    st.markdown(f'<div class="art-metric"><div class="art-metric-num" style="font-size:22px;">{resultado["sis_general"]}/{resultado["dia_general"]}</div><div class="art-metric-label">Promedio general</div></div>', unsafe_allow_html=True)
                with c4:
                    st.markdown(f'<div class="art-metric"><div class="art-metric-num" style="font-size:22px;">{resultado["dias_usados"]}</div><div class="art-metric-label">Días promediados</div></div>', unsafe_allow_html=True)
                st.caption("El resultado promedia los registros de los días 2 a 7 (se descarta el día 1, según protocolo).")
                grafico_evolucion(mediciones)
                if resultado["tipo"] == "success":
                    st.success(f"**{resultado['titulo']}** — {resultado['mensaje']}")
                elif resultado["tipo"] == "warning":
                    st.warning(f"**{resultado['titulo']}** — {resultado['mensaje']}")
                else:
                    st.error(f"**{resultado['titulo']}** — {resultado['mensaje']}")

                # Exportar PDF
                eventos = obtener_eventos_adversos(codigo)
                alertas = obtener_alertas(codigo)
                try:
                    pdf_bytes = generar_pdf_hbpm(paciente, mediciones, resultado, eventos, alertas)
                    st.download_button(
                        "📄 Descargar informe HBPM en PDF",
                        data=pdf_bytes,
                        file_name=f"HBPM_{paciente.get('apellido','')}_{codigo}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                except Exception as e:
                    st.warning(f"No se pudo generar el PDF: {e}")

        elif proxima is None:
            st.success("✅ Completaste todas las tomas de hoy. ¡Volvé mañana!")
            if total >= 4:
                grafico_evolucion(mediciones)
        else:
            momento_display = proxima.replace("mañana", "🌅 Mañana").replace("tarde", "🌇 Tarde").replace("-", " · Toma ")
            st.markdown(f"""
            <div class="section-eyebrow">Próxima toma</div>
            <div style="font-family:'DM Serif Display',serif;font-size:22px;color:#e8eef7;margin-bottom:1rem;">{momento_display}</div>
            """, unsafe_allow_html=True)
            if proxima in ["mañana-2", "tarde-2"]:
                st.info("⏱ Esperá 1-2 minutos desde la toma anterior.")

            with st.form("form_medicion"):
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    sis = st.number_input("Sistólica (número mayor)", min_value=60, max_value=250, value=120, step=1)
                with col_f2:
                    dia = st.number_input("Diastólica (número menor)", min_value=40, max_value=150, value=80, step=1)
                confirmar_alto = st.checkbox("Confirmo que los valores son correctos (requerido si son muy elevados)")
                guardar_btn = st.form_submit_button("Guardar medición →", use_container_width=True)
            if guardar_btn:
                if (sis > 200 or dia > 120) and not confirmar_alto:
                    st.warning(f"⚠️ Los valores {sis}/{dia} son muy elevados. Marcá la casilla de confirmación si son correctos.")
                else:
                    guardar_medicion(codigo, sis, dia, proxima)
                    st.success("✅ Medición guardada.")
                    st.rerun()

            if total >= 2:
                with st.expander("📈 Ver evolución hasta ahora"):
                    grafico_evolucion(mediciones)

        # Reportar evento adverso / síntoma
        with st.expander("➕ Reportar un evento o síntoma"):
            st.markdown('<p style="font-size:13px;color:#94a3b8;">Si tuviste algún síntoma o evento durante el monitoreo (mareo, dolor de cabeza, etc.), registralo acá para que tu médico lo vea.</p>', unsafe_allow_html=True)
            with st.form("form_evento"):
                desc_evento = st.text_area("Descripción del evento o síntoma", height=80)
                ev_btn = st.form_submit_button("Registrar evento")
            if ev_btn and desc_evento.strip():
                if guardar_evento_adverso(codigo, desc_evento.strip(), "paciente"):
                    st.success("✅ Evento registrado.")
                else:
                    st.error("No se pudo registrar el evento.")
            eventos_p = obtener_eventos_adversos(codigo)
            for ev in eventos_p:
                st.markdown(f'<div style="background:rgba(255,255,255,0.03);border-left:3px solid #dc2626;padding:8px 12px;margin-bottom:8px;border-radius:4px;font-size:13px;color:#94a3b8;">{ev.get("descripcion","")}<br><span style="font-size:11px;color:#475569;">{str(ev.get("fecha",""))[:10]}</span></div>', unsafe_allow_html=True)

    footer()

# ══════════════════════════════════════════════════════════════════════════════
# VISTA: LOGIN MÉDICO
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.vista == "medico_login":
    navbar("Panel médico")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("← Volver"):
            st.session_state.vista = "inicio"
            st.rerun()
        tab_login, tab_reset = st.tabs(["Iniciar sesión", "Olvidé mi contraseña"])
        with tab_login:
            st.markdown('<div class="art-card">', unsafe_allow_html=True)
            st.markdown("### 👨‍⚕️ Acceso médico")
            with st.form("form_login_medico"):
                email_m = st.text_input("Email médico")
                pwd_m = st.text_input("Contraseña", type="password")
                login_m = st.form_submit_button("Ingresar →", use_container_width=True)
            if login_m:
                admin_email = get_secret("admin", "email")
                admin_pwd = get_secret("admin", "password")
                email_norm = email_m.strip().lower()
                if admin_email and admin_pwd and email_norm == admin_email.strip().lower() and pwd_m == admin_pwd:
                    st.session_state.rol = "admin"
                    st.session_state.vista = "admin_home"
                    st.rerun()
                else:
                    medico = buscar_medico_por_email(email_norm)
                    if medico and medico.get("password_set"):
                        ok_pwd, nuevo_hash = verificar_password(pwd_m, medico.get("password_hash", ""))
                        if ok_pwd:
                            if nuevo_hash:
                                actualizar_medico(medico["email"], {"password_hash": nuevo_hash})
                            st.session_state.medico_data = medico
                            st.session_state.rol = "medico"
                            st.session_state.vista = "medico_home"
                            st.rerun()
                        else:
                            st.error("❌ Contraseña incorrecta.")
                    elif medico and not medico.get("password_set"):
                        st.warning("Tu cuenta no está activada. Revisá tu email para activarla.")
                    else:
                        st.error("❌ Email no encontrado.")
            st.markdown('</div>', unsafe_allow_html=True)
        with tab_reset:
            st.markdown('<div class="art-card">', unsafe_allow_html=True)
            st.markdown("### Recuperar contraseña")
            email_r = st.text_input("Tu email médico")
            if st.button("Enviar instrucciones", use_container_width=True):
                medico = buscar_medico_por_email(email_r.strip().lower())
                if medico:
                    reset_token = str(uuid.uuid4())
                    actualizar_medico(medico["email"], {"reset_token": reset_token})
                    reset_url = f"{APP_URL}/?reset={reset_token}"
                    enviar_reset_password(email_r, reset_url, medico.get("nombre", ""))
                st.success("✅ Si el email existe, recibirás instrucciones para recuperar tu contraseña.")
            st.markdown('</div>', unsafe_allow_html=True)
    footer()

# ══════════════════════════════════════════════════════════════════════════════
# VISTA: HOME MÉDICO
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.vista == "medico_home":
    medico = st.session_state.medico_data
    if not medico:
        st.session_state.vista = "medico_login"
        st.rerun()

    navbar(f"Dr/Dra. {medico.get('nombre','')} {medico.get('apellido','')}")

    col_nav1, col_nav2 = st.columns([6, 1])
    with col_nav2:
        nombre_med = medico.get('nombre', '')
        with st.popover("⚙️ " + nombre_med[:10]):
            st.markdown(f'<p style="font-size:13px;color:#94a3b8;margin-bottom:8px;">Dr/Dra.<br><strong style="color:#e8eef7;">{medico.get("nombre","")} {medico.get("apellido","")}</strong></p>', unsafe_allow_html=True)
            st.divider()
            if st.button("🚪 Cerrar sesión", use_container_width=True):
                cerrar_sesion()

    tab1, tab2 = st.tabs(["➕ Nuevo paciente", "📋 Mis pacientes"])

    with tab1:
        col1, col2 = st.columns([1, 1], gap="large")
        with col1:
            st.markdown('<div class="art-card">', unsafe_allow_html=True)
            st.markdown("#### Agregar paciente")
            with st.form("form_nuevo_paciente"):
                nombre_p = st.text_input("Nombre")
                apellido_p = st.text_input("Apellido")
                email_p = st.text_input("Email del paciente")
                crear_btn = st.form_submit_button("Crear y enviar acceso →", use_container_width=True)
            if crear_btn:
                if nombre_p and apellido_p and email_p:
                    with st.spinner("Creando acceso..."):
                        codigo = crear_paciente(nombre_p, apellido_p, email_p.lower(), medico["id"])
                        ok = enviar_bienvenida_paciente(nombre_p, email_p, codigo)
                    if ok:
                        st.success(f"✅ Acceso enviado a {email_p}")
                    else:
                        st.warning(f"Paciente creado. Código: **{codigo}**")
                else:
                    st.error("Completá todos los campos.")
            st.markdown('</div>', unsafe_allow_html=True)

    with tab2:
        pacientes = obtener_pacientes_medico(medico["id"])
        if not pacientes:
            st.info("Aún no tenés pacientes registrados.")
        else:
            for p in pacientes:
                mediciones = obtener_mediciones(p["codigo"])
                nombre_completo = f"{p.get('nombre','?')} {p.get('apellido','?')}"
                total = len(mediciones)
                resultado = calcular_resultado(mediciones)
                if resultado and resultado["categoria"] == "controlada":
                    badge = '<span class="badge-ok">Controlada</span>'
                elif resultado and resultado["categoria"] == "urgente":
                    badge = '<span class="badge-alert">Urgente</span>'
                elif resultado and resultado["categoria"] == "no_controlada":
                    badge = '<span class="badge-warn">No controlada</span>'
                elif resultado and resultado["categoria"] == "baja":
                    badge = '<span class="badge-low">Presión baja</span>'
                else:
                    badge = f'<span style="font-size:12px;color:#94a3b8;">{total}/28 tomas</span>'

                with st.expander(f"{nombre_completo} · {p.get('email','?')}"):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.markdown(f'<div class="art-metric"><div class="art-metric-num">{total}</div><div class="art-metric-label">Tomas registradas</div></div>', unsafe_allow_html=True)
                    with c2:
                        prom_txt = f"{resultado['sis_general']}/{resultado['dia_general']}" if resultado else "—"
                        st.markdown(f'<div class="art-metric"><div class="art-metric-num" style="font-size:24px;">{prom_txt}</div><div class="art-metric-label">Promedio mmHg</div></div>', unsafe_allow_html=True)
                    with c3:
                        st.markdown(f'<div class="art-metric">{badge}</div>', unsafe_allow_html=True)

                    if resultado:
                        st.markdown(
                            f'<div style="font-size:13px;color:#94a3b8;margin:8px 0;">'
                            f'Mañana: <strong style="color:#e8eef7;">{resultado["sis_manana"]}/{resultado["dia_manana"]}</strong> · '
                            f'Tarde: <strong style="color:#e8eef7;">{resultado["sis_tarde"]}/{resultado["dia_tarde"]}</strong></div>',
                            unsafe_allow_html=True)

                    if total >= 4:
                        grafico_evolucion(mediciones)

                    # Eventos adversos y alertas
                    eventos_p = obtener_eventos_adversos(p["codigo"])
                    alertas_p = obtener_alertas(p["codigo"])
                    col_e, col_a = st.columns(2)
                    with col_e:
                        st.markdown("##### ⚠️ Eventos reportados")
                        if eventos_p:
                            for ev in eventos_p:
                                st.markdown(f'<div style="font-size:12px;color:#94a3b8;margin-bottom:6px;">• {ev.get("descripcion","")} <span style="color:#475569;">({str(ev.get("fecha",""))[:10]})</span></div>', unsafe_allow_html=True)
                        else:
                            st.caption("Sin eventos.")
                    with col_a:
                        st.markdown("##### 🔔 Alertas generadas")
                        if alertas_p:
                            for al in alertas_p:
                                st.markdown(f'<div style="font-size:12px;color:#94a3b8;margin-bottom:6px;">• {al.get("mensaje","")} <span style="color:#475569;">({str(al.get("fecha",""))[:10]})</span></div>', unsafe_allow_html=True)
                        else:
                            st.caption("Sin alertas.")

                    # Exportar PDF del paciente
                    if total >= 28 and resultado:
                        try:
                            pdf_bytes = generar_pdf_hbpm(p, mediciones, resultado, eventos_p, alertas_p)
                            st.download_button(
                                "📄 Descargar informe HBPM en PDF",
                                data=pdf_bytes,
                                file_name=f"HBPM_{p.get('apellido','')}_{p['codigo']}.pdf",
                                mime="application/pdf",
                                key=f"pdf_{p['codigo']}",
                                use_container_width=True
                            )
                        except Exception as e:
                            st.warning(f"No se pudo generar el PDF: {e}")

                    # Notas privadas del médico
                    st.markdown("##### 📝 Notas privadas")
                    notas = obtener_notas_medico(p["codigo"], medico["id"])
                    for n in notas:
                        st.markdown(f'<div style="background:rgba(255,255,255,0.03);border-left:3px solid #3b82f6;padding:8px 12px;margin-bottom:8px;border-radius:4px;font-size:13px;color:#94a3b8;">{n["nota"]}<br><span style="font-size:11px;color:#475569;">{str(n["fecha"])[:10]}</span></div>', unsafe_allow_html=True)
                    with st.form(f"nota_{p['codigo']}"):
                        nueva_nota = st.text_area("Nueva nota (solo visible para vos)", height=80)
                        if st.form_submit_button("Guardar nota"):
                            if nueva_nota:
                                guardar_nota_medico(p["codigo"], medico["id"], nueva_nota)
                                st.success("Nota guardada.")
                                st.rerun()
    footer()

# ══════════════════════════════════════════════════════════════════════════════
# VISTA: ADMIN
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.vista == "admin_home":
    navbar("Panel de administración")
    col_nav1, col_nav2 = st.columns([6, 1])
    with col_nav2:
        if st.button("Cerrar sesión"):
            cerrar_sesion()

    st.markdown("### ⚙️ Panel de administración")
    tab1, tab2 = st.tabs(["➕ Nuevo médico", "👥 Todos los médicos"])

    with tab1:
        col1, col2 = st.columns([1, 1])
        with col1:
            st.markdown('<div class="art-card">', unsafe_allow_html=True)
            st.markdown("#### Dar de alta médico")
            with st.form("form_nuevo_medico"):
                nombre_m = st.text_input("Nombre del médico")
                apellido_m = st.text_input("Apellido del médico")
                email_m = st.text_input("Email del médico")
                crear_m = st.form_submit_button("Crear y enviar activación →", use_container_width=True)
            if crear_m:
                if nombre_m and apellido_m and email_m:
                    crear_medico(nombre_m, apellido_m, email_m.lower())
                    ok = enviar_activacion_medico(nombre_m, email_m.lower())
                    if ok:
                        st.success(f"✅ Médico creado. Email de activación enviado a {email_m}")
                    else:
                        st.warning("Médico creado pero hubo un error con el email.")
                else:
                    st.error("Completá todos los campos.")
            st.markdown('</div>', unsafe_allow_html=True)

    with tab2:
        try:
            r = get_sb().table("medicos").select("*").order("fecha_registro", desc=True).execute()
            medicos = r.data
        except Exception:
            medicos = []
        if not medicos:
            st.info("No hay médicos registrados aún.")
        else:
            for m in medicos:
                pacientes_m = obtener_pacientes_medico(m["id"])
                estado = "✅ Activo" if m.get("activo") else "❌ Inactivo"
                with st.expander(f"Dr/Dra. {m.get('nombre','')} {m.get('apellido','')} · {m.get('email','')} · {estado}"):
                    st.write(f"**Pacientes:** {len(pacientes_m)}")
                    st.write(f"**Cuenta activada:** {'Sí' if m.get('password_set') else 'No'}")
    footer()
