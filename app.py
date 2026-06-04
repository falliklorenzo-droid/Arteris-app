import streamlit as st
from supabase import create_client, Client
from datetime import datetime, date, timezone, timedelta
import resend
import uuid
import os
import io
import json
import secrets as _secrets
import hashlib
import bcrypt
import pandas as pd
import altair as alt

# ── Helpers de medicación múltiple ────────────────────────────────────────────
def parse_medicaciones(paciente):
    """Devuelve la lista de {nombre, dosis} desde el paciente. Soporta el formato
    nuevo (JSON list en 'medicacion') y el viejo (medicacion + dosis como strings)."""
    raw = (paciente.get("medicacion") or "").strip()
    if raw.startswith("[") and raw.endswith("]"):
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                out = []
                for it in data:
                    if isinstance(it, dict) and it.get("nombre", "").strip():
                        out.append({"nombre": it.get("nombre", "").strip(), "dosis": it.get("dosis", "").strip()})
                return out
        except Exception:
            pass
    # Formato viejo: una sola medicación
    if raw:
        return [{"nombre": raw, "dosis": (paciente.get("dosis") or "").strip()}]
    return []

def serializar_medicaciones(lista):
    """Convierte una lista de dicts a JSON string para guardar en Supabase."""
    cleaned = [{"nombre": (m.get("nombre") or "").strip(), "dosis": (m.get("dosis") or "").strip()}
               for m in lista if (m.get("nombre") or "").strip()]
    return json.dumps(cleaned, ensure_ascii=False) if cleaned else ""

def medicaciones_texto(paciente):
    """Devuelve un texto plano de las medicaciones para mostrar."""
    lista = parse_medicaciones(paciente)
    if not lista:
        return "Ninguna"
    return "; ".join(f"{m['nombre']}" + (f" ({m['dosis']})" if m['dosis'] else "") for m in lista)

# Zona horaria fija Argentina (UTC-3). Toda la lógica de "día actual" usa esta zona.
ARG_TZ = timezone(timedelta(hours=-3))
def hoy_arg():
    return datetime.now(ARG_TZ).date()
def now_arg():
    return datetime.now(ARG_TZ)

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

/* Day pills */
.day-dots { display: flex; gap: 6px; margin: 12px 0; flex-wrap: wrap; }
.day-dot { padding: 6px 14px; border-radius: 999px; display: inline-flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 500; border: 1px solid transparent; white-space: nowrap; }
.day-done { background: rgba(16,185,129,0.15); color: #10b981; border-color: rgba(16,185,129,0.3); }
.day-today { background: #1d4ed8; color: white; border-color: #3b82f6; }
.day-pending { background: rgba(255,255,255,0.04); color: #64748b; border-color: rgba(255,255,255,0.06); }

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
    .day-dot { padding: 5px 10px; font-size: 11px; }
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

def guardar_medicion(codigo, sistolica, diastolica, momento, pulso=None, fecha_dia=None, atrasada=False):
    """Guarda una medición. Si fecha_dia se especifica, la toma se asigna a ese día
    (formato YYYY-MM-DD). El flag 'atrasada' debe pasarse explícitamente.
    Si las columnas nuevas no existen todavía en Supabase, intenta de nuevo sin ellas."""
    ahora = now_arg()
    if fecha_dia:
        fecha_iso = f"{fecha_dia}T{ahora.strftime('%H:%M:%S')}-03:00"
    else:
        fecha_iso = ahora.isoformat()
    payload = {
        "codigo_paciente": codigo,
        "sistolica": sistolica,
        "diastolica": diastolica,
        "momento": momento,
        "fecha": fecha_iso,
        "cargada_atrasada": atrasada,
        "creada_at": ahora.isoformat(),
    }
    if pulso is not None:
        payload["pulso"] = pulso
    try:
        get_sb().table("mediciones").insert(payload).execute()
    except Exception as ex:
        # Fallback: re-intentar sin las columnas que podrían no existir aún
        msg = str(ex)
        for col in ("cargada_atrasada", "creada_at", "pulso"):
            if col in msg and col in payload:
                payload.pop(col, None)
        get_sb().table("mediciones").insert(payload).execute()
    # Alerta automática por toma elevada
    if sistolica >= 180 or diastolica >= 110:
        generar_alerta(codigo, "toma_elevada",
                       f"Toma elevada registrada: {sistolica}/{diastolica} mmHg ({momento}).")
    # Alerta automática por taquicardia
    if pulso is not None and pulso >= 110:
        generar_alerta(codigo, "pulso_elevado",
                       f"Frecuencia cardíaca elevada: {pulso} bpm ({momento}).")
    # Alerta automática + envío de PDF al completar el monitoreo
    try:
        meds = obtener_mediciones(codigo)
        if len(meds) >= 28:
            res = calcular_resultado(meds)
            if res and res.get("categoria") not in ("controlada", "insuficiente"):
                generar_alerta(codigo, "resultado",
                               f"Resultado del HBPM: {res.get('titulo','')} "
                               f"({res.get('sis_general','-')}/{res.get('dia_general','-')} mmHg promedio).")
            # Envío automático del PDF (una sola vez por procedimiento)
            try:
                p = buscar_paciente(codigo)
                if p and not p.get("ultimo_pdf_enviado_at") and p.get("email"):
                    eventos = obtener_eventos_adversos(codigo)
                    alertas = obtener_alertas(codigo)
                    pdf_bytes = generar_pdf_hbpm(p, meds, res, eventos, alertas)
                    if enviar_pdf_informe(p.get("email"), p.get("nombre", ""), pdf_bytes):
                        actualizar_paciente(codigo, {"ultimo_pdf_enviado_at": now_arg().isoformat()})
            except Exception as e:
                print(f"Error envío PDF automático: {e}")
    except Exception:
        pass

def editar_medicion(medicion_id, sistolica, diastolica, pulso=None):
    """Edita una medición existente (solo dentro del plazo de 12hs validado en UI)."""
    payload = {
        "sistolica": sistolica,
        "diastolica": diastolica,
        "editada_at": now_arg().isoformat(),
    }
    if pulso is not None:
        payload["pulso"] = pulso
    try:
        get_sb().table("mediciones").update(payload).eq("id", medicion_id).execute()
        return True
    except Exception:
        return False

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

# ── Sesión persistente ("recordarme 30 días") ────────────────────────────────
def crear_session_paciente(codigo):
    token = _secrets.token_urlsafe(32)
    expires = now_arg() + timedelta(days=30)
    try:
        actualizar_paciente(codigo, {"session_token": token, "session_expires": expires.isoformat()})
        return token
    except Exception:
        return None

def crear_session_medico(email):
    token = _secrets.token_urlsafe(32)
    expires = now_arg() + timedelta(days=30)
    try:
        actualizar_medico(email, {"session_token": token, "session_expires": expires.isoformat()})
        return token
    except Exception:
        return None

def validar_session(token):
    """Devuelve (tipo, registro) si el token es válido y no expiró. Si no, (None, None).
    Normaliza todo a UTC para evitar problemas de comparación con tz."""
    if not token:
        return None, None
    try:
        now_utc = pd.to_datetime(now_arg(), utc=True)
    except Exception:
        now_utc = pd.Timestamp.utcnow()
    for tabla in ("pacientes", "medicos"):
        try:
            r = get_sb().table(tabla).select("*").eq("session_token", token).execute()
            if r.data:
                u = r.data[0]
                exp_raw = u.get("session_expires")
                if exp_raw:
                    try:
                        exp_utc = pd.to_datetime(exp_raw, utc=True)
                        if exp_utc > now_utc:
                            return ("paciente" if tabla == "pacientes" else "medico"), u
                    except Exception:
                        # Si no podemos parsear la expiración, validamos por las dudas
                        return ("paciente" if tabla == "pacientes" else "medico"), u
        except Exception:
            pass
    return None, None

def invalidar_session(token):
    """Borra el token de la DB al cerrar sesión."""
    if not token:
        return
    try:
        get_sb().table("pacientes").update({"session_token": None, "session_expires": None}).eq("session_token", token).execute()
    except Exception:
        pass
    try:
        get_sb().table("medicos").update({"session_token": None, "session_expires": None}).eq("session_token", token).execute()
    except Exception:
        pass

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
        "fecha": now_arg().isoformat()
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
            "fecha": now_arg().isoformat()
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
            "fecha": now_arg().isoformat()
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

def enviar_mail_expiracion(email, nombre=""):
    """Mail único que se envía cuando se cumplieron los 7 días del protocolo y el monitoreo
    quedó incompleto (no se llegó al mínimo de 12 tomas en los últimos 6 días)."""
    try:
        resend.api_key = get_secret("resend", "api_key")
        url = f"{APP_URL}/?vista=paciente"
        resend.Emails.send({
            "from": "Arteris <noreply@arterismed.com>",
            "to": email,
            "subject": "Tu monitoreo HBPM finalizó sin resultado · Arteris",
            "html": f"""
            <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;background:#0a1628;color:#e8eef7;border-radius:12px;overflow:hidden;">
              <div style="background:#1d4ed8;padding:24px 32px;">
                <h1 style="font-size:24px;margin:0;color:white;font-weight:400;">Arteris</h1>
                <p style="font-size:12px;color:rgba(255,255,255,0.7);margin:4px 0 0;letter-spacing:1px;text-transform:uppercase;">Monitoreo Domiciliario de Presión Arterial</p>
              </div>
              <div style="padding:32px;">
                <p style="font-size:16px;">Hola{(' ' + nombre) if nombre else ''},</p>
                <p style="color:#94a3b8;line-height:1.6;">Pasaron los <strong style="color:#e8eef7;">7 días</strong> del protocolo HBPM y tu monitoreo no llegó al mínimo de tomas que requieren los estándares clínicos actuales (12 tomas en los últimos 6 días).</p>
                <p style="color:#94a3b8;line-height:1.6;">Por eso no pudimos calcular un resultado útil. Si querés volver a empezar el monitoreo:</p>
                <div style="text-align:center;margin:24px 0;">
                  <a href="{url}" style="background:#1d4ed8;color:white;padding:14px 32px;text-decoration:none;border-radius:8px;font-size:15px;display:inline-block;">Reiniciar el monitoreo →</a>
                </div>
                <p style="color:#94a3b8;line-height:1.6;font-size:14px;">También te recomendamos consultar con tu médico tratante para evaluar el siguiente paso.</p>
                <p style="font-size:11px;color:#64748b;margin-top:20px;">No vas a recibir más recordatorios por mail hasta que reinicies el monitoreo.</p>
              </div>
            </div>"""
        })
        return True
    except Exception as e:
        print(f"Error enviando mail expiración: {e}")
        return False

def enviar_pdf_informe(email, nombre, pdf_bytes):
    """Envía el PDF del informe HBPM adjunto al paciente cuando completa el monitoreo."""
    try:
        import base64
        resend.api_key = get_secret("resend", "api_key")
        resend.Emails.send({
            "from": "Arteris <noreply@arterismed.com>",
            "to": email,
            "subject": "Tu informe de Monitoreo Domiciliario de Presión Arterial · Arteris",
            "html": f"""
            <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;background:#0a1628;color:#e8eef7;border-radius:12px;overflow:hidden;">
              <div style="background:#1d4ed8;padding:24px 32px;">
                <h1 style="font-size:24px;margin:0;color:white;font-weight:400;">Arteris</h1>
                <p style="font-size:12px;color:rgba(255,255,255,0.7);margin:4px 0 0;letter-spacing:1px;text-transform:uppercase;">Monitoreo Domiciliario de Presión Arterial</p>
              </div>
              <div style="padding:32px;">
                <p style="font-size:16px;">Hola{(' ' + nombre) if nombre else ''},</p>
                <p style="color:#94a3b8;line-height:1.6;">Completaste tu monitoreo domiciliario de presión arterial. Te adjuntamos el informe HBPM en PDF — guardalo y compartilo con tu médico tratante.</p>
                <p style="font-size:11px;color:#64748b;margin-top:20px;">Este informe es orientativo y no reemplaza una consulta médica.</p>
              </div>
            </div>""",
            "attachments": [
                {
                    "filename": "Informe_HBPM_Arteris.pdf",
                    "content": list(pdf_bytes) if isinstance(pdf_bytes, (bytes, bytearray)) else pdf_bytes,
                }
            ],
        })
        return True
    except Exception as e:
        print(f"Error enviando PDF: {e}")
        return False

def archivar_procedimiento(codigo, paciente_data, mediciones, resultado, eventos, alertas):
    """Guarda una copia del procedimiento actual en historial_procedimientos."""
    try:
        df_meds = pd.DataFrame(mediciones) if mediciones else pd.DataFrame()
        if not df_meds.empty and "fecha" in df_meds.columns:
            df_meds["fecha_local"] = df_meds["fecha"].apply(parse_fecha_local)
            fechas = [f for f in df_meds["fecha_local"].tolist() if f is not None]
            fecha_inicio_iso = min(fechas).isoformat() if fechas else None
        else:
            fecha_inicio_iso = None
        get_sb().table("historial_procedimientos").insert({
            "codigo_paciente": codigo,
            "fecha_inicio": fecha_inicio_iso,
            "fecha_fin": now_arg().isoformat(),
            "resultado": resultado,
            "mediciones": mediciones,
            "eventos": eventos,
            "alertas": alertas,
        }).execute()
        return True
    except Exception as e:
        print(f"Error archivando procedimiento: {e}")
        return False

def obtener_historial_paciente(codigo):
    """Lista de procedimientos completados para un paciente, más reciente primero."""
    try:
        r = get_sb().table("historial_procedimientos").select("*")\
            .eq("codigo_paciente", codigo)\
            .order("fecha_fin", desc=True).execute()
        return r.data or []
    except Exception:
        return []

def reiniciar_procedimiento_paciente(codigo):
    """Borra las mediciones, eventos y alertas del procedimiento actual.
    Asume que ya se archivó en historial. Conserva el paciente y su medicación."""
    sb = get_sb()
    try:
        sb.table("mediciones").delete().eq("codigo_paciente", codigo).execute()
    except Exception:
        pass
    try:
        sb.table("eventos_adversos").delete().eq("codigo_paciente", codigo).execute()
    except Exception:
        pass
    try:
        sb.table("alertas").delete().eq("codigo_paciente", codigo).execute()
    except Exception:
        pass
    try:
        sb.table("pacientes").update({
            "ultimo_pdf_enviado_at": None,
            "mail_expiracion_enviado_at": None,
        }).eq("codigo", codigo).execute()
    except Exception:
        pass

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
def parse_fecha_local(val):
    """Convierte una fecha (cualquiera sea su tz) a la fecha local de Argentina."""
    if not val:
        return None
    try:
        dt = pd.to_datetime(val, format="mixed", errors="coerce", utc=True)
        if pd.isna(dt):
            return None
        return dt.tz_convert(ARG_TZ).date()
    except Exception:
        try:
            return pd.to_datetime(val, errors="coerce").date()
        except Exception:
            return None

def fecha_inicio_protocolo(mediciones):
    """Devuelve la fecha del día 1 del protocolo (fecha de la primera medición).
    Si no hay mediciones aún, devuelve la fecha de hoy en Argentina."""
    if not mediciones:
        return hoy_arg()
    fechas = [parse_fecha_local(m.get("fecha")) for m in mediciones]
    fechas = [f for f in fechas if f is not None]
    return min(fechas) if fechas else hoy_arg()

def dia_protocolo_actual(mediciones):
    """Devuelve el número de día del protocolo (1 a 7) según la fecha de hoy en Argentina."""
    if not mediciones:
        return 1
    inicio = fecha_inicio_protocolo(mediciones)
    transcurridos = (hoy_arg() - inicio).days + 1
    return max(1, min(transcurridos, 7))

def protocolo_expirado(mediciones):
    """True si ya pasaron los 7 días del protocolo (estamos en día 8 o posterior)."""
    if not mediciones:
        return False
    inicio = fecha_inicio_protocolo(mediciones)
    return (hoy_arg() - inicio).days >= 7

def protocolo_abandonado(mediciones):
    """True si el protocolo no va a llegar al mínimo clínico (12 tomas).
    Se considera abandonado si:
    (A) Es matemáticamente imposible llegar a 12 tomas en lo que queda del protocolo,
        asumiendo que cargara perfecto los días restantes (4 tomas/día):
        total + 4 × (días restantes) < 12.
    (B) Muy baja adherencia: desde el día 4 en adelante, menos de 1 toma/día promedio
        (total < día actual). Catch de los casos donde matemáticamente todavía es posible
        pero clínicamente improbable (ej: día 5 con 2 tomas)."""
    if not mediciones:
        return False
    dia_act = dia_protocolo_actual(mediciones)
    total = len(mediciones)

    # (A) Imposibilidad matemática
    dias_restantes = max(0, 7 - dia_act + 1)  # incluye el día actual
    if (total + 4 * dias_restantes) < 12:
        return True

    # (B) Adherencia muy baja
    if dia_act >= 4 and total < dia_act:
        return True

    return False

def protocolo_cerrado(mediciones):
    """True si el monitoreo está cerrado por cualquier motivo:
    - Se completaron las 28 tomas, o
    - Pasaron los 7 días del protocolo, o
    - El paciente abandonó (adherencia <1 toma/día desde día 4)."""
    return (len(mediciones) >= 28) or protocolo_expirado(mediciones) or protocolo_abandonado(mediciones)

def fecha_de_dia(mediciones, dia_num):
    """Devuelve la fecha calendario que corresponde al día N del protocolo."""
    inicio = fecha_inicio_protocolo(mediciones)
    return inicio + timedelta(days=dia_num - 1)

def tomas_de_dia(mediciones, dia_num):
    """Devuelve la lista de tomas (registros) que corresponden al día N del protocolo."""
    fecha_dia = fecha_de_dia(mediciones, dia_num)
    out = []
    for m in mediciones:
        f = parse_fecha_local(m.get("fecha"))
        if f == fecha_dia:
            out.append(m)
    return out

def dias_con_faltantes(mediciones, hasta_dia=None):
    """Devuelve los días anteriores al actual que NO tienen las 4 tomas completas."""
    if not mediciones:
        return []
    dia_actual = dia_protocolo_actual(mediciones)
    tope = hasta_dia if hasta_dia is not None else dia_actual
    faltantes = []
    for d in range(1, tope):  # solo días pasados
        tomas = tomas_de_dia(mediciones, d)
        if len(tomas) < 4:
            faltantes.append({
                "dia": d,
                "fecha": fecha_de_dia(mediciones, d),
                "tomas_cargadas": len(tomas),
                "momentos_cargados": [t["momento"] for t in tomas],
            })
    return faltantes

def puede_editar(medicion):
    """Una medición se puede editar dentro de las 12hs de creada (carga atrasada sigue valiendo desde su creación)."""
    creada = medicion.get("creada_at") or medicion.get("fecha")
    if not creada:
        return False
    try:
        creada_dt = pd.to_datetime(creada, format="mixed", utc=True, errors="coerce")
        if pd.isna(creada_dt):
            return False
        ahora = pd.to_datetime(now_arg(), utc=True)
        return (ahora - creada_dt) < pd.Timedelta(hours=12)
    except Exception:
        return False

def calcular_resultado(mediciones):
    """Calcula promedios y categoría del HBPM según el algoritmo clínico actualizado:
    - Toma los últimos 6 días (descarta el día 1 según protocolo HBPM).
    - Si esos 6 días tienen las 24 tomas (ideal) o al menos 12 tomas (mínimo aceptable),
      calcula el resultado.
    - Si tienen menos de 12 → resultado "insuficiente" (no útil clínicamente).
    - Reporta % de adherencia sobre 28 (base 100%)."""
    if not mediciones:
        return None
    df = pd.DataFrame(mediciones)
    df["fecha_local"] = df["fecha"].apply(parse_fecha_local)
    df = df.dropna(subset=["fecha_local"])
    if df.empty:
        return None

    # Últimos 6 días: los 6 días más recientes con tomas, descartando los más viejos.
    dias_ordenados = sorted(df["fecha_local"].unique())
    if len(dias_ordenados) >= 7:
        dias_para_promedio = dias_ordenados[-6:]  # los últimos 6 días
    elif len(dias_ordenados) >= 2:
        dias_para_promedio = dias_ordenados[1:]   # descartamos el día 1, usamos lo que haya
    else:
        dias_para_promedio = dias_ordenados        # único día

    df_promedio = df[df["fecha_local"].isin(dias_para_promedio)]
    total_tomas_seguimiento = len(df)  # total cargadas en todo el protocolo
    tomas_ult6 = len(df_promedio)
    adherencia_pct = round(min(total_tomas_seguimiento / 28 * 100, 100), 1)

    # Categoría de calidad del informe
    if tomas_ult6 >= 24:
        calidad = "ideal"
        calidad_msg = f"Informe ideal: {tomas_ult6}/24 tomas en los últimos 6 días."
    elif tomas_ult6 >= 12:
        calidad = "util"
        calidad_msg = f"Informe útil pero incompleto: {tomas_ult6} tomas en los últimos 6 días (mínimo recomendado: 12)."
    else:
        calidad = "insuficiente"
        calidad_msg = (
            f"Informe insuficiente: solo {tomas_ult6} tomas en los últimos 6 días. "
            "Según los estándares actuales (mínimo 12 tomas en 6 días) no es posible "
            "dar un informe clínicamente útil."
        )

    if df_promedio.empty:
        return {
            "calidad": "insuficiente",
            "calidad_msg": calidad_msg,
            "adherencia_pct": adherencia_pct,
            "total_tomas_seguimiento": total_tomas_seguimiento,
            "tomas_ult6": tomas_ult6,
            "tipo": "warning",
            "titulo": "⚠️ Informe insuficiente",
            "mensaje": calidad_msg,
            "categoria": "insuficiente",
            "dias_usados": 0,
            "sis_manana": None, "dia_manana": None,
            "sis_tarde": None, "dia_tarde": None,
            "sis_general": None, "dia_general": None,
            "pulso_general": None,
            "promedios_diarios": [],
        }

    df_promedio = df_promedio.copy()
    df_promedio["periodo"] = df_promedio["momento"].fillna("").apply(
        lambda m: "mañana" if str(m).startswith("mañana")
        else ("tarde" if str(m).startswith("tarde") else "otro"))
    manana = df_promedio[df_promedio["periodo"] == "mañana"]
    tarde = df_promedio[df_promedio["periodo"] == "tarde"]

    pulso_general = None
    if "pulso" in df_promedio.columns:
        pulso_num = pd.to_numeric(df_promedio["pulso"], errors="coerce")
        if pulso_num.notna().any():
            pulso_general = round(float(pulso_num.mean()), 1)

    res = {
        "sis_manana": round(manana["sistolica"].mean(), 1) if not manana.empty else None,
        "dia_manana": round(manana["diastolica"].mean(), 1) if not manana.empty else None,
        "sis_tarde": round(tarde["sistolica"].mean(), 1) if not tarde.empty else None,
        "dia_tarde": round(tarde["diastolica"].mean(), 1) if not tarde.empty else None,
        "sis_general": round(df_promedio["sistolica"].mean(), 1),
        "dia_general": round(df_promedio["diastolica"].mean(), 1),
        "pulso_general": pulso_general,
        "dias_usados": len(dias_para_promedio),
        "tomas_ult6": tomas_ult6,
        "total_tomas_seguimiento": total_tomas_seguimiento,
        "adherencia_pct": adherencia_pct,
        "calidad": calidad,
        "calidad_msg": calidad_msg,
    }

    diarios = df_promedio.groupby("fecha_local").agg(
        sis_m=("sistolica", "mean"), dia_m=("diastolica", "mean")).reset_index()
    res["promedios_diarios"] = [
        {"fecha": str(r["fecha_local"]), "sis": round(r["sis_m"], 1), "dia": round(r["dia_m"], 1)}
        for _, r in diarios.iterrows()
    ]

    # Si la calidad es insuficiente, devolvemos info pero con categoría especial
    if calidad == "insuficiente":
        res.update({
            "categoria": "insuficiente",
            "titulo": "⚠️ Informe insuficiente",
            "mensaje": calidad_msg,
            "tipo": "warning",
        })
        return res

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
    df["fecha_dt"] = pd.to_datetime(df["fecha"], format="mixed", errors="coerce")
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
    ).properties(height=280, background="#0a1628").configure_view(stroke="#1e293b")
    st.altair_chart(chart, use_container_width=True)


def generar_conclusion(resultado, mediciones):
    """Genera una mini-conclusión clínica orientativa basada en presión, pulso y adherencia.
    NO es diagnóstico: es un resumen orientativo para que médico y paciente lo vean rápido."""
    if not resultado:
        return "Sin datos suficientes para una conclusión."
    categoria = resultado.get("categoria", "")
    calidad = resultado.get("calidad", "")
    adherencia = resultado.get("adherencia_pct")
    total_seg = resultado.get("total_tomas_seguimiento", 0)
    tomas_ult6 = resultado.get("tomas_ult6", 0)
    partes = []

    # Caso insuficiente: el informe no es clínicamente útil
    if categoria == "insuficiente" or calidad == "insuficiente":
        partes.append(f"<strong>Informe insuficiente.</strong> Solo {tomas_ult6} tomas en los últimos 6 días (mínimo recomendado: 12). Según los estándares actuales no es posible elaborar un informe clínico útil.")
        if adherencia is not None:
            partes.append(f"Adherencia al protocolo: {adherencia}% ({total_seg}/28 tomas).")
        return " ".join(partes) + " <em style='color:#94a3b8;'>(Conclusión orientativa, no constituye diagnóstico médico.)</em>"

    s = resultado.get("sis_general")
    d = resultado.get("dia_general")
    p = resultado.get("pulso_general")

    # Resumen de PA
    if categoria == "urgente":
        partes.append(f"<strong>Presión arterial muy elevada</strong> (promedio {s}/{d} mmHg). Se sugiere atención médica urgente.")
    elif categoria == "baja":
        partes.append(f"<strong>Presión arterial baja</strong> (promedio {s}/{d} mmHg). Se recomienda control.")
    elif categoria == "controlada":
        partes.append(f"<strong>Presión arterial controlada</strong> (promedio {s}/{d} mmHg).")
    elif categoria == "no_controlada":
        partes.append(f"<strong>Presión arterial no controlada</strong> (promedio {s}/{d} mmHg). Se sugiere consulta médica.")

    # Calidad del informe
    if calidad == "util":
        partes.append(f"Informe útil pero parcial: {tomas_ult6} tomas en los últimos 6 días (ideal: 24).")
    elif calidad == "ideal":
        partes.append(f"Registro completo de los últimos 6 días ({tomas_ult6}/24).")

    # Variabilidad mañana/tarde
    sm = resultado.get("sis_manana")
    st_ = resultado.get("sis_tarde")
    if sm and st_ and abs(sm - st_) >= 15:
        cual = "mayor por la mañana" if sm > st_ else "mayor por la tarde"
        partes.append(f"Variabilidad notable entre mañana y tarde ({cual}).")

    # Pulso
    if p is not None:
        if p >= 100:
            partes.append(f"Frecuencia cardíaca promedio elevada ({p} bpm): podría ser taquicardia, evaluar contexto clínico.")
        elif p < 60:
            partes.append(f"Frecuencia cardíaca promedio baja ({p} bpm): podría ser bradicardia, evaluar contexto clínico.")
        else:
            partes.append(f"Frecuencia cardíaca promedio en rango normal ({p} bpm).")

    # Adherencia
    if adherencia is not None:
        partes.append(f"Adherencia al protocolo: {adherencia}% ({total_seg}/28 tomas).")
    try:
        atrasadas = sum(1 for m in mediciones if m.get("cargada_atrasada"))
        if atrasadas:
            partes.append(f"{atrasadas} toma(s) cargada(s) con atraso.")
    except Exception:
        pass

    return " ".join(partes) + " <em style='color:#94a3b8;'>(Conclusión orientativa, no constituye diagnóstico médico.)</em>"


def grafico_pulso(mediciones):
    """Gráfico de evolución de frecuencia cardíaca con línea de promedio."""
    df = pd.DataFrame(mediciones)
    if "pulso" not in df.columns:
        st.caption("Todavía no hay datos de frecuencia cardíaca para graficar.")
        return
    df["pulso_num"] = pd.to_numeric(df["pulso"], errors="coerce")
    df = df.dropna(subset=["pulso_num"])
    if df.empty:
        st.caption("Todavía no hay datos de frecuencia cardíaca para graficar.")
        return
    df["fecha_dt"] = pd.to_datetime(df["fecha"], format="mixed", errors="coerce")
    df = df.sort_values("fecha_dt")
    df["etiqueta"] = df["fecha_dt"].dt.strftime("%d/%m") + " · " + df["momento"].fillna("")
    promedio = round(float(df["pulso_num"].mean()), 1)
    df_avg = pd.DataFrame({"promedio": [promedio]})

    linea = alt.Chart(df).mark_line(point=True, color="#ef4444").encode(
        x=alt.X("etiqueta:N", title="", sort=None,
                axis=alt.Axis(labelAngle=-45, labelColor="#94a3b8", gridColor="#1e293b")),
        y=alt.Y("pulso_num:Q", title="bpm",
                axis=alt.Axis(labelColor="#94a3b8", gridColor="#1e293b"),
                scale=alt.Scale(zero=False)),
        tooltip=["etiqueta:N", alt.Tooltip("pulso_num:Q", title="pulso (bpm)"), "momento:N"],
    )
    regla_promedio = alt.Chart(df_avg).mark_rule(
        color="#f59e0b", strokeDash=[6, 4], size=2
    ).encode(y="promedio:Q")
    texto_promedio = alt.Chart(df_avg).mark_text(
        align="right", baseline="bottom", dx=-5, dy=-5,
        color="#f59e0b", fontSize=12, fontWeight=500,
    ).encode(y="promedio:Q", text=alt.value(f"Promedio: {promedio} bpm"))

    chart = (linea + regla_promedio + texto_promedio).properties(
        height=240, background="#0a1628"
    ).configure_view(stroke="#1e293b")
    st.altair_chart(chart, use_container_width=True)

# ── Exportación PDF ───────────────────────────────────────────────────────────
def _grafico_png(mediciones):
    """Devuelve un buffer PNG con la tendencia, o None si matplotlib no está disponible."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        df = pd.DataFrame(mediciones)
        df["fecha_dt"] = pd.to_datetime(df["fecha"], format="mixed", errors="coerce")
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

def _grafico_pulso_png(mediciones):
    """Gráfico PNG de pulso para el PDF. None si no hay datos o matplotlib falla."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        df = pd.DataFrame(mediciones)
        if "pulso" not in df.columns:
            return None
        df["pulso_num"] = pd.to_numeric(df["pulso"], errors="coerce")
        df = df.dropna(subset=["pulso_num"])
        if df.empty:
            return None
        df["fecha_dt"] = pd.to_datetime(df["fecha"], format="mixed", errors="coerce")
        df = df.sort_values("fecha_dt")
        promedio = float(df["pulso_num"].mean())
        fig, ax = plt.subplots(figsize=(7, 2.3))
        x = list(range(len(df)))
        ax.plot(x, df["pulso_num"], marker="o", markersize=3, color="#ef4444", label="Pulso (bpm)")
        ax.axhline(promedio, color="#f59e0b", linestyle="--", linewidth=0.8, label=f"Promedio: {promedio:.1f} bpm")
        ax.set_ylabel("bpm", fontsize=8)
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
    pdf.cell(0, 6, t(f"Fecha del informe: {now_arg().strftime('%d/%m/%Y')}"), 0, 1)
    pdf.ln(3)

    # Tratamiento médico
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, t("Tratamiento médico"), ln=1)
    pdf.set_font("Helvetica", "", 10)
    if paciente.get("toma_medicacion"):
        meds_lista = parse_medicaciones(paciente)
        if meds_lista:
            for idx, m in enumerate(meds_lista, start=1):
                etiqueta = "Medicación" if len(meds_lista) == 1 else f"Medicación {idx}"
                pdf.cell(0, 6, t(f"{etiqueta}: {m['nombre']}" + (f" - {m['dosis']}" if m['dosis'] else "")), 0, 1)
        else:
            pdf.cell(0, 6, t("Medicación: -"), 0, 1)
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
        df["fecha_dt"] = pd.to_datetime(df["fecha"], format="mixed", errors="coerce")
        df["dia"] = df["fecha_dt"].dt.date
        for i, dia in enumerate(sorted(df["dia"].unique()), start=1):
            sub = df[df["dia"] == dia]
            pdf.cell(anchos[0], 7, t(f"Día {i} ({dia.strftime('%d/%m')})"), 1, 0, "C")
            for j, mom in enumerate(orden):
                fila = sub[sub["momento"] == mom]
                if not fila.empty:
                    r0 = fila.iloc[0]
                    sis_v = int(r0["sistolica"])
                    dia_v = int(r0["diastolica"])
                    pulso_v = r0.get("pulso") if "pulso" in fila.columns else None
                    v = f"{sis_v}/{dia_v}"
                    if pulso_v is not None and pd.notna(pulso_v):
                        v += f" · {int(pulso_v)} bpm"
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
        if resultado.get("pulso_general") is not None:
            pdf.cell(0, 6, t(f"Frecuencia cardíaca promedio: {resultado.get('pulso_general')} bpm"), 0, 1)
        pdf.ln(1)
        titulo_limpio = "".join(c for c in resultado.get("titulo", "") if ord(c) < 256).strip()
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_x(pdf.l_margin)
        try:
            pdf.multi_cell(180, 6, t(titulo_limpio))
        except Exception:
            pdf.cell(180, 6, t(titulo_limpio), 0, 1)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_x(pdf.l_margin)
        try:
            pdf.multi_cell(180, 5, t(resultado.get("mensaje", "")))
        except Exception:
            pdf.cell(180, 5, t(resultado.get("mensaje", "")[:200]), 0, 1)
    else:
        pdf.cell(0, 6, t("Monitoreo incompleto: faltan registros para calcular el resultado."), 0, 1)
    pdf.ln(3)

    # Tendencia gráfica de presión arterial
    grafico = _grafico_png(mediciones)
    if grafico is not None:
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, t("Tendencia gráfica - Presión arterial"), ln=1)
        try:
            pdf.image(grafico, w=180)
        except Exception:
            pass
        pdf.ln(3)

    # Tendencia gráfica de frecuencia cardíaca
    grafico_p = _grafico_pulso_png(mediciones)
    if grafico_p is not None:
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, t("Tendencia gráfica - Frecuencia cardíaca"), ln=1)
        try:
            pdf.image(grafico_p, w=180)
        except Exception:
            pass
        pdf.ln(3)

    # Conclusión orientativa
    if resultado:
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, t("Conclusión orientativa"), ln=1)
        pdf.set_font("Helvetica", "", 9)
        conclusion_plana = generar_conclusion(resultado, mediciones)
        import re as _re
        conclusion_plana = _re.sub(r"<[^>]+>", "", conclusion_plana).strip()
        try:
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(180, 5, t(conclusion_plana))
        except Exception:
            # Si falla por cualquier motivo, intentamos un fallback simple
            try:
                pdf.cell(0, 5, t(conclusion_plana[:200] + "..."), ln=1)
            except Exception:
                pass
        pdf.ln(3)

    # Eventos adversos
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, t("Eventos adversos / clínicos reportados"), ln=1)
    pdf.set_font("Helvetica", "", 9)
    if eventos:
        for ev in eventos:
            pdf.set_x(pdf.l_margin)
            try:
                pdf.multi_cell(180, 5, t(f"- [{str(ev.get('fecha',''))[:10]}] {ev.get('descripcion','')}"))
            except Exception:
                pdf.cell(180, 5, t(f"- [{str(ev.get('fecha',''))[:10]}] {str(ev.get('descripcion',''))[:100]}"), 0, 1)
    else:
        pdf.cell(0, 6, t("Sin eventos reportados."), 0, 1)
    pdf.ln(2)

    # Alertas
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, t("Alertas generadas"), ln=1)
    pdf.set_font("Helvetica", "", 9)
    if alertas:
        for al in alertas:
            pdf.set_x(pdf.l_margin)
            try:
                pdf.multi_cell(180, 5, t(f"- [{str(al.get('fecha',''))[:10]}] {al.get('mensaje','')}"))
            except Exception:
                pdf.cell(180, 5, t(f"- [{str(al.get('fecha',''))[:10]}] {str(al.get('mensaje',''))[:100]}"), 0, 1)
    else:
        pdf.cell(0, 6, t("Sin alertas generadas."), 0, 1)
    pdf.ln(4)

    # Pie / descargo
    pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(120, 120, 120)
    pdf.set_x(pdf.l_margin)
    try:
        pdf.multi_cell(180, 4, t(
            "Informe orientativo generado por la plataforma Arteris. No constituye un diagnóstico médico "
            "y no reemplaza la consulta con un profesional de la salud. Datos tratados conforme a la "
            "Ley 25.326 de Protección de Datos Personales."))
    except Exception:
        pass

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
    elif vista_url == "paciente":
        st.session_state.vista = "paciente_login"
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

# ── Sesión persistente 30 días (localStorage + cookie como backup) ────────────
# Usamos streamlit_javascript para leer/escribir localStorage del navegador.
# localStorage es más persistente que cookies y no depende de timing del componente.
try:
    from streamlit_javascript import st_javascript
    _SJ_OK = True
except Exception:
    _SJ_OK = False

try:
    from streamlit_cookies_controller import CookieController
    cookie_controller = CookieController()
except Exception:
    cookie_controller = None
cookie_manager = cookie_controller  # compat con código viejo

def _ls_save(token):
    """Guarda token en localStorage del navegador via JS."""
    if not _SJ_OK or not token:
        return
    try:
        st_javascript(
            f"localStorage.setItem('arteris_session', '{token}'); 'ok';",
            key=f"_ls_save_{token[:10]}",
        )
    except Exception:
        pass

def _ls_read():
    """Lee token de localStorage del navegador via JS. Devuelve None si no hay
    o si todavía no respondió (primer render)."""
    if not _SJ_OK:
        return None
    try:
        val = st_javascript(
            "localStorage.getItem('arteris_session') || ''",
            key="_ls_read_session",
        )
        if isinstance(val, str) and val.strip():
            return val.strip()
        return None
    except Exception:
        return None

def _ls_clear():
    """Borra el token del localStorage."""
    if not _SJ_OK:
        return
    try:
        st_javascript(
            "localStorage.removeItem('arteris_session'); 'ok';",
            key=f"_ls_clear_{_secrets.token_hex(4)}",
        )
    except Exception:
        pass

def set_session_cookie(token, expires):
    """Guarda el token de sesión en localStorage Y cookie (doble redundancia)."""
    if not token:
        return
    _ls_save(token)
    if cookie_controller is not None:
        try:
            max_age = int((expires - now_arg()).total_seconds())
            cookie_controller.set("arteris_session", token, max_age=max_age, path="/", same_site="lax")
        except Exception:
            try:
                cookie_controller.set("arteris_session", token)
            except Exception:
                pass

def clear_session_cookie():
    """Borra el token de localStorage Y cookie."""
    _ls_clear()
    if cookie_controller is not None:
        try:
            cookie_controller.remove("arteris_session", path="/")
        except Exception:
            try:
                cookie_controller.remove("arteris_session")
            except Exception:
                pass

def leer_session_cookie():
    """Lee el token primero de localStorage, luego de cookie como fallback."""
    tok = _ls_read()
    if tok:
        return tok
    if cookie_controller is not None:
        try:
            return cookie_controller.get("arteris_session")
        except Exception:
            return None
    return None

def iniciar_sesion_persistente(tipo, ident):
    """Crea un token de sesión en DB y lo guarda en localStorage + cookie (30 días)."""
    expires = now_arg() + timedelta(days=30)
    token = None
    if tipo == "paciente":
        token = crear_session_paciente(ident)
    elif tipo == "medico":
        token = crear_session_medico(ident)
    if token:
        set_session_cookie(token, expires)

# Restaurar sesión si todavía no hay rol cargado.
# Damos hasta 3 reruns para que localStorage / cookies estén listos.
if not st.session_state.get("rol"):
    tok_persistente = leer_session_cookie()
    if tok_persistente:
        tipo, registro = validar_session(tok_persistente)
        if registro:
            if tipo == "paciente":
                st.session_state.paciente_data = registro
                st.session_state.codigo_paciente = registro.get("codigo", "")
                st.session_state.rol = "paciente"
                st.session_state.vista = "paciente_home"
            elif tipo == "medico":
                st.session_state.medico_data = registro
                st.session_state.rol = "medico"
                st.session_state.vista = "medico_home"
    else:
        retries = int(st.session_state.get("_persist_retry", 0) or 0)
        if retries < 3:
            st.session_state["_persist_retry"] = retries + 1
            st.rerun()

def cerrar_sesion():
    """Cierra sesión: invalida token en DB + borra localStorage + cookie + session_state."""
    tok = leer_session_cookie()
    if tok:
        invalidar_session(tok)
    clear_session_cookie()
    for k in ["vista", "usuario", "rol", "medico_data", "paciente_data",
              "codigo_paciente", "consentimiento_ok", "_persist_retry"]:
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
                    iniciar_sesion_persistente("medico", medico["email"])
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

    col_nav1, col_nav2, col_nav3 = st.columns([2, 4, 1])
    with col_nav1:
        if st.button("← Volver al inicio", key="btn_volver_top"):
            st.session_state.vista = "paciente_home"
            st.rerun()
    with col_nav3:
        with st.popover("⚙️ " + nombre[:10]):
            st.markdown(f'<p style="font-size:13px;color:#94a3b8;margin-bottom:8px;">Sesión activa como<br><strong style="color:#e8eef7;">{nombre}</strong></p>', unsafe_allow_html=True)
            st.divider()
            if st.button("🏠 Inicio", use_container_width=True, key="pop_inicio"):
                st.session_state.vista = "paciente_home"
                st.rerun()
            if st.button("📚 Historial", use_container_width=True, key="pop_ajustes_historial"):
                st.session_state.vista = "paciente_historial"
                st.rerun()
            if st.button("🚪 Cerrar sesión", use_container_width=True, key="pop_cerrar"):
                cerrar_sesion()

    st.markdown("### ⚙️ Ajustes de tu cuenta")
    st.markdown("---")

    col1, col2 = st.columns([1, 1], gap="large")

    with col1:
        st.markdown('<div class="art-card">', unsafe_allow_html=True)
        st.markdown("#### 📧 Recordatorios por email")
        st.markdown('<p style="font-size:13px;color:#94a3b8;">Recibirás un recordatorio para cargar tu presión arterial a las 7 hs y a las 19 hs cada día.</p>', unsafe_allow_html=True)
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

    st.markdown('<div class="art-card" style="margin-top:1rem;"><h4 style="margin-top:0;">💊 Mi medicación</h4>', unsafe_allow_html=True)
    st.markdown('<p style="font-size:13px;color:#94a3b8;margin-bottom:1rem;">Podés cargar varias medicaciones (con su dosis). Usá el botón "Agregar otra" para sumar más.</p>', unsafe_allow_html=True)
    toma_med_actual = bool(paciente.get("toma_medicacion"))
    toma_med_edit = st.radio(
        "¿Tomás medicación para la presión arterial?",
        ["No", "Sí"],
        index=1 if toma_med_actual else 0,
        horizontal=True,
        key="edit_toma_med",
    )
    # Inicializar la lista editable en session_state
    if "edit_meds_lista" not in st.session_state or st.session_state.get("edit_meds_para_codigo") != paciente["codigo"]:
        lista_actual = parse_medicaciones(paciente)
        st.session_state.edit_meds_lista = lista_actual if lista_actual else [{"nombre": "", "dosis": ""}]
        st.session_state.edit_meds_para_codigo = paciente["codigo"]

    if toma_med_edit == "Sí":
        for i, m in enumerate(st.session_state.edit_meds_lista):
            cols_med = st.columns([5, 5, 1])
            with cols_med[0]:
                st.session_state.edit_meds_lista[i]["nombre"] = st.text_input(
                    f"Medicación {i+1}", value=m.get("nombre", ""), placeholder="Ej: Enalapril",
                    key=f"med_nombre_{i}", label_visibility="visible" if i == 0 else "collapsed",
                )
            with cols_med[1]:
                st.session_state.edit_meds_lista[i]["dosis"] = st.text_input(
                    f"Dosis {i+1}", value=m.get("dosis", ""), placeholder="Ej: 10mg cada 12hs",
                    key=f"med_dosis_{i}", label_visibility="visible" if i == 0 else "collapsed",
                )
            with cols_med[2]:
                if i == 0:
                    st.markdown('<div style="height:28px;"></div>', unsafe_allow_html=True)
                if len(st.session_state.edit_meds_lista) > 1:
                    if st.button("🗑️", key=f"del_med_{i}"):
                        st.session_state.edit_meds_lista.pop(i)
                        st.rerun()
        if st.button("➕ Agregar otra medicación", key="btn_add_med"):
            st.session_state.edit_meds_lista.append({"nombre": "", "dosis": ""})
            st.rerun()

    if st.button("Guardar cambios de medicación", use_container_width=True, key="btn_guardar_med", type="primary"):
        if toma_med_edit == "Sí":
            cleaned = [m for m in st.session_state.edit_meds_lista if (m.get("nombre") or "").strip()]
            if not cleaned:
                st.error("Cargá al menos una medicación con nombre, o seleccioná \"No\".")
            else:
                for m in cleaned:
                    if not m.get("dosis", "").strip():
                        st.error(f'Completá la dosis de "{m["nombre"]}".')
                        break
                else:
                    actualizar_paciente(paciente["codigo"], {
                        "toma_medicacion": True,
                        "medicacion": serializar_medicaciones(cleaned),
                        "dosis": cleaned[0].get("dosis", ""),  # backward compat
                    })
                    st.session_state.paciente_data = buscar_paciente(paciente["codigo"])
                    st.success("✅ Medicación actualizada correctamente.")
                    st.session_state.pop("edit_meds_lista", None)
                    st.session_state.pop("edit_meds_para_codigo", None)
                    st.rerun()
        else:
            actualizar_paciente(paciente["codigo"], {
                "toma_medicacion": False,
                "medicacion": "",
                "dosis": "",
            })
            st.session_state.paciente_data = buscar_paciente(paciente["codigo"])
            st.success("✅ Medicación actualizada correctamente.")
            st.session_state.pop("edit_meds_lista", None)
            st.session_state.pop("edit_meds_para_codigo", None)
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="art-card" style="margin-top:1rem;"><h4 style="margin-top:0;">👤 Mis datos personales</h4>', unsafe_allow_html=True)
    col_d1, col_d2, col_d3 = st.columns(3)
    with col_d1:
        st.markdown(f'<div class="art-metric"><div class="art-metric-num" style="font-size:24px;">{paciente.get("edad","—")}</div><div class="art-metric-label">Edad</div></div>', unsafe_allow_html=True)
    with col_d2:
        st.markdown(f'<div class="art-metric"><div class="art-metric-num" style="font-size:18px;">{paciente.get("sexo","—")}</div><div class="art-metric-label">Sexo biológico</div></div>', unsafe_allow_html=True)
    with col_d3:
        med_txt = medicaciones_texto(paciente)
        st.markdown(f'<div class="art-metric"><div class="art-metric-num" style="font-size:14px;line-height:1.3;">{med_txt}</div><div class="art-metric-label">Medicación</div></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    if st.button("← Volver al inicio", key="btn_volver_bottom"):
        st.session_state.vista = "paciente_home"
        st.rerun()

    footer()

# ══════════════════════════════════════════════════════════════════════════════
# VISTA: HISTORIAL DE PROCEDIMIENTOS DEL PACIENTE
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.vista == "paciente_historial":
    paciente = st.session_state.paciente_data
    if not paciente:
        st.session_state.vista = "paciente_login"
        st.rerun()
    nombre = paciente.get("nombre", "Paciente")
    navbar(f"Historial · {nombre}")

    col_h1, col_h2, col_h3 = st.columns([2, 4, 1])
    with col_h1:
        if st.button("← Volver al inicio", key="hist_volver_top"):
            st.session_state.vista = "paciente_home"
            st.rerun()
    with col_h3:
        with st.popover("⚙️ " + nombre[:10]):
            if st.button("🏠 Inicio", use_container_width=True, key="pop_hist_inicio"):
                st.session_state.vista = "paciente_home"
                st.rerun()
            if st.button("⚙️ Ajustes", use_container_width=True, key="pop_hist_ajustes"):
                st.session_state.vista = "paciente_ajustes"
                st.rerun()
            if st.button("🚪 Cerrar sesión", use_container_width=True, key="pop_hist_cerrar"):
                cerrar_sesion()

    st.markdown("### 📚 Historial de monitoreos completados")
    st.markdown('<p style="font-size:13px;color:#94a3b8;margin-bottom:1rem;">Acá vas a encontrar los procedimientos de HBPM que ya completaste, ordenados del más reciente al más antiguo.</p>', unsafe_allow_html=True)

    historial = obtener_historial_paciente(paciente["codigo"])
    if not historial:
        st.info("Todavía no tenés procedimientos completados archivados. El procedimiento actual va a archivarse acá cuando lo reinicies.")
    else:
        for h in historial:
            fecha_ini = str(h.get("fecha_inicio", ""))[:10] or "—"
            fecha_fin = str(h.get("fecha_fin", ""))[:10] or "—"
            res = h.get("resultado") or {}
            titulo = res.get("titulo", "—")
            adh = res.get("adherencia_pct")
            adh_str = f" · Adherencia {adh}%" if adh is not None else ""
            with st.expander(f"📋 {fecha_ini} → {fecha_fin} · {titulo}{adh_str}", expanded=False):
                cA, cB, cC, cD = st.columns(4)
                with cA:
                    st.markdown(f'<div class="art-metric"><div class="art-metric-num" style="font-size:20px;">{res.get("sis_manana","—")}/{res.get("dia_manana","—")}</div><div class="art-metric-label">Prom. mañana</div></div>', unsafe_allow_html=True)
                with cB:
                    st.markdown(f'<div class="art-metric"><div class="art-metric-num" style="font-size:20px;">{res.get("sis_tarde","—")}/{res.get("dia_tarde","—")}</div><div class="art-metric-label">Prom. tarde</div></div>', unsafe_allow_html=True)
                with cC:
                    st.markdown(f'<div class="art-metric"><div class="art-metric-num" style="font-size:20px;">{res.get("sis_general","—")}/{res.get("dia_general","—")}</div><div class="art-metric-label">Prom. general</div></div>', unsafe_allow_html=True)
                with cD:
                    pulso_h = res.get("pulso_general")
                    st.markdown(f'<div class="art-metric"><div class="art-metric-num" style="font-size:20px;">{pulso_h or "—"}{" bpm" if pulso_h else ""}</div><div class="art-metric-label">Pulso prom.</div></div>', unsafe_allow_html=True)
                if res.get("mensaje"):
                    st.caption(res["mensaje"])
                if res.get("calidad_msg"):
                    st.caption(res["calidad_msg"])
                # Botón de descarga del PDF reconstruido
                try:
                    pdf_bytes = generar_pdf_hbpm(paciente, h.get("mediciones") or [], res, h.get("eventos") or [], h.get("alertas") or [])
                    st.download_button(
                        "📄 Descargar informe HBPM en PDF",
                        data=pdf_bytes,
                        file_name=f"HBPM_{paciente.get('apellido','')}_{fecha_fin}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                        key=f"dl_hist_{h.get('id','')}",
                    )
                except Exception as ex:
                    st.warning(f"No se pudo regenerar el PDF de este informe: {ex}")

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
                        iniciar_sesion_persistente("paciente", paciente["codigo"])
                        st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
            elif paciente and paciente.get("password_set"):
                # Cuenta ya activada → limpiar codigo y caer al login normal con tabs (incluye "Olvidé mi contraseña")
                st.session_state.codigo_paciente = ""
                try:
                    st.query_params.clear()
                except Exception:
                    pass
                st.rerun()
            else:
                st.error("❌ El enlace no es válido. Pedile a tu médico que te reenvíe el acceso.")
        else:
            # Login normal con email y contraseña
            tab_login, tab_reset = st.tabs(["Iniciar sesión", "Olvidé mi contraseña"])
            with tab_login:
                st.markdown('<div class="art-card"><h3 style="margin-top:0;">Ingresar a Arteris</h3>', unsafe_allow_html=True)
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
                            iniciar_sesion_persistente("paciente", paciente["codigo"])
                            st.rerun()
                        else:
                            st.error("❌ Contraseña incorrecta.")
                    else:
                        st.error("❌ Email no encontrado o cuenta no activada.")
                st.markdown('</div>', unsafe_allow_html=True)
            with tab_reset:
                st.markdown('<div class="art-card"><h3 style="margin-top:0;">Recuperar contraseña</h3>', unsafe_allow_html=True)
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
            if st.button("⚙️ Ajustes", use_container_width=True, key="pop_home_ajustes"):
                st.session_state.vista = "paciente_ajustes"
                st.rerun()
            if st.button("📚 Historial", use_container_width=True, key="pop_home_historial"):
                st.session_state.vista = "paciente_historial"
                st.rerun()
            if st.button("🚪 Cerrar sesión", use_container_width=True, key="pop_home_cerrar"):
                cerrar_sesion()

    # Consentimiento
    if not paciente.get("consentimiento_aceptado") and not st.session_state.consentimiento_ok:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown('<div class="art-card"><h3 style="margin-top:0;">📄 Consentimiento y términos de uso</h3>', unsafe_allow_html=True)
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
            st.markdown('<div class="art-card"><h3 style="margin-top:0;">📋 Completá tus datos</h3>', unsafe_allow_html=True)
            edad = st.number_input("Edad", min_value=1, max_value=120, step=1)
            sexo = st.selectbox("Sexo biológico", ["Femenino", "Masculino", "Otro"])
            toma_med = st.radio("¿Tomás medicación para la presión arterial?", ["No", "Sí"], horizontal=True)

            if "reg_meds_lista" not in st.session_state:
                st.session_state.reg_meds_lista = [{"nombre": "", "dosis": ""}]

            if toma_med == "Sí":
                st.caption("Podés agregar varias medicaciones con su dosis.")
                for i, m in enumerate(st.session_state.reg_meds_lista):
                    cols_reg = st.columns([5, 5, 1])
                    with cols_reg[0]:
                        st.session_state.reg_meds_lista[i]["nombre"] = st.text_input(
                            f"Medicación {i+1}", value=m.get("nombre", ""),
                            placeholder="Ej: Enalapril", key=f"reg_med_n_{i}",
                            label_visibility="visible" if i == 0 else "collapsed",
                        )
                    with cols_reg[1]:
                        st.session_state.reg_meds_lista[i]["dosis"] = st.text_input(
                            f"Dosis {i+1}", value=m.get("dosis", ""),
                            placeholder="Ej: 10mg cada 12hs", key=f"reg_med_d_{i}",
                            label_visibility="visible" if i == 0 else "collapsed",
                        )
                    with cols_reg[2]:
                        if len(st.session_state.reg_meds_lista) > 1:
                            if st.button("🗑️", key=f"reg_del_med_{i}"):
                                st.session_state.reg_meds_lista.pop(i)
                                st.rerun()
                if st.button("➕ Agregar otra medicación", key="reg_btn_add_med"):
                    st.session_state.reg_meds_lista.append({"nombre": "", "dosis": ""})
                    st.rerun()

            recordatorios = st.checkbox("✉️ Quiero recibir recordatorios por email para cargar mi presión arterial", value=True)
            st.markdown('<div style="font-size:11px;color:#64748b;margin-top:-8px;">Recibirás un recordatorio a las 7 hs y a las 19 hs cada día durante los 7 días del seguimiento.</div>', unsafe_allow_html=True)
            enviado = st.button("Guardar y comenzar →", use_container_width=True, key="btn_registro_paciente")
            if enviado and edad:
                meds_valid = [m for m in st.session_state.reg_meds_lista if (m.get("nombre") or "").strip()]
                if toma_med == "Sí" and not meds_valid:
                    st.error("Cargá al menos una medicación con nombre, o seleccioná \"No\".")
                elif toma_med == "Sí" and any(not (m.get("dosis") or "").strip() for m in meds_valid):
                    st.error("Completá la dosis de todas las medicaciones cargadas.")
                else:
                    actualizar_paciente(codigo, {
                        "edad": int(edad), "sexo": sexo,
                        "toma_medicacion": toma_med == "Sí",
                        "medicacion": serializar_medicaciones(meds_valid) if toma_med == "Sí" else "",
                        "dosis": (meds_valid[0]["dosis"] if (toma_med == "Sí" and meds_valid) else ""),
                        "recordatorios_email": recordatorios,
                        "consentimiento_aceptado": True
                    })
                    st.session_state.paciente_data = buscar_paciente(codigo)
                    st.session_state.pop("reg_meds_lista", None)
                    st.success("✅ ¡Registro completado!")
                    st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    # Homepage principal
    else:
        mediciones = obtener_mediciones(codigo)
        total = len(mediciones)
        dia_actual = dia_protocolo_actual(mediciones) if mediciones else 1
        # Si no hay mediciones todavía, hoy es el día 1
        fecha_dia_actual = fecha_de_dia(mediciones, dia_actual) if mediciones else hoy_arg()

        med_dia = tomas_de_dia(mediciones, dia_actual) if mediciones else []
        momentos_dia = [m["momento"] for m in med_dia]
        tomas_orden = ["mañana-1", "mañana-2", "tarde-1", "tarde-2"]
        proxima = next((tt for tt in tomas_orden if tt not in momentos_dia), None)
        # Día completo = tiene los 4 momentos únicos (mañana-1/2, tarde-1/2)
        dias_completos = sum(
            1 for d in range(1, 8)
            if len(set(t.get("momento", "") for t in tomas_de_dia(mediciones, d))) >= 4
        )
        faltantes = dias_con_faltantes(mediciones) if mediciones else []

        # Flags de cierre del protocolo
        expirado = protocolo_expirado(mediciones)
        abandonado = protocolo_abandonado(mediciones)
        cerrado = protocolo_cerrado(mediciones)

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

        # Banner del día actual: "Este es el día N de tu seguimiento"
        es_manana = proxima is not None and proxima.startswith("mañana")
        es_tarde = proxima is not None and proxima.startswith("tarde")
        terminada_manana = "mañana-1" in momentos_dia and "mañana-2" in momentos_dia
        terminado_dia = proxima is None
        if total < 28 and not cerrado:
            if terminado_dia:
                banner_color = "#10b981"
                banner_emoji = "✅"
                banner_texto = f"Día {dia_actual} — Completaste todas las tomas de hoy"
            elif es_tarde:
                banner_color = "#f59e0b"  # naranja para tarde
                banner_emoji = "🌇"
                banner_texto = f"Día {dia_actual} — Tomas de la TARDE"
            else:
                banner_color = "#3b82f6"  # azul para mañana
                banner_emoji = "🌅"
                banner_texto = f"Día {dia_actual} — Tomas de la MAÑANA"
            st.markdown(f"""
            <div style="background:linear-gradient(90deg,{banner_color}1f,{banner_color}0a);border:1px solid {banner_color}55;border-radius:12px;padding:1rem 1.25rem;margin-bottom:1rem;">
              <div style="font-size:14px;color:#94a3b8;letter-spacing:1px;text-transform:uppercase;">Este es</div>
              <div style="font-size:22px;color:#e8eef7;font-weight:500;margin-top:4px;">{banner_emoji} {banner_texto}</div>
              <div style="font-size:12px;color:#64748b;margin-top:6px;">Fecha del día: {fecha_dia_actual.strftime('%d/%m/%Y')}</div>
            </div>
            """, unsafe_allow_html=True)

        dias_html = ""
        for d_num in range(1, 8):
            momentos_dia_x = set(t.get("momento", "") for t in tomas_de_dia(mediciones, d_num)) if mediciones else set()
            if len(momentos_dia_x) >= 4:
                cls = "day-done"
            elif d_num == dia_actual:
                cls = "day-today"
            else:
                cls = "day-pending"
            dias_html += f'<div class="day-dot {cls}">Día {d_num}</div>'

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

        # Aviso si la data tiene tomas fuera del protocolo de 7 días (datos viejos con bug)
        try:
            fechas_unicas = sorted({parse_fecha_local(m.get("fecha")) for m in mediciones if parse_fecha_local(m.get("fecha"))})
            if len(fechas_unicas) > 7:
                st.warning(
                    f"⚠️ Tu monitoreo tiene tomas distribuidas en **{len(fechas_unicas)} días** "
                    f"(el protocolo es de 7 días). Esto puede pasar si una toma se cargó muy tarde "
                    f"por la noche o quedó asignada a un día distinto. **No afecta el resultado** "
                    f"(usamos los últimos 6 días según el protocolo), pero si querés empezar limpio "
                    f"podés usar el botón **Reiniciar procedimiento** cuando lo completes."
                )
        except Exception:
            pass

        # Aviso de tomas atrasadas — banner grande y visible para que adultos mayores no lo pasen por alto
        # Solo se muestra mientras el protocolo está activo (no cerrado por ningún motivo).
        if faltantes and not cerrado:
            tomas_pendientes_total = sum(4 - f["tomas_cargadas"] for f in faltantes)
            st.markdown(f"""
            <div style="background:linear-gradient(135deg,rgba(245,158,11,0.22),rgba(245,158,11,0.06));
                        border:2px solid #f59e0b;border-radius:14px;padding:1.5rem 1.75rem;margin:1rem 0;">
              <div style="display:flex;align-items:center;gap:14px;margin-bottom:8px;">
                <div style="font-size:42px;line-height:1;">⚠️</div>
                <div>
                  <div style="font-family:'DM Serif Display',serif;font-size:24px;color:#f59e0b;font-weight:500;line-height:1.2;">
                    Tenés {tomas_pendientes_total} toma{'s' if tomas_pendientes_total != 1 else ''} pendiente{'s' if tomas_pendientes_total != 1 else ''} de cargar
                  </div>
                  <div style="font-size:15px;color:#e8eef7;margin-top:4px;">
                    En {len(faltantes)} día{'s' if len(faltantes)>1 else ''} anterior{'es' if len(faltantes)>1 else ''} te faltó cargar la presión.
                  </div>
                </div>
              </div>
              <p style="font-size:14px;color:#cbd5e1;line-height:1.5;margin:8px 0 0 0;">
                Si tomaste la presión esos días pero te olvidaste de cargarla en la app, podés agregarla ahora.
                <strong style="color:#e8eef7;">Hacé clic en el botón "Cargar" al lado de cada toma faltante</strong> y completá los datos.
              </p>
            </div>
            """, unsafe_allow_html=True)
            with st.expander(f"👉 Ver y completar las {tomas_pendientes_total} toma{'s' if tomas_pendientes_total != 1 else ''} pendiente{'s' if tomas_pendientes_total != 1 else ''}", expanded=True):
                st.markdown('<p style="font-size:13px;color:#94a3b8;">Las tomas atrasadas quedan marcadas como "cargadas con atraso" para tu médico.</p>', unsafe_allow_html=True)
                for f in faltantes:
                    tomas_faltantes_lista = [t for t in tomas_orden if t not in f["momentos_cargados"]]
                    st.markdown(f"**Día {f['dia']}** ({f['fecha'].strftime('%d/%m/%Y')}) — {f['tomas_cargadas']}/4 tomas cargadas.")
                    for tt in tomas_faltantes_lista:
                        atr_key = f"{f['dia']}_{tt}"
                        cols_f = st.columns([3, 1])
                        with cols_f[0]:
                            momento_disp = tt.replace("mañana", "🌅 Mañana").replace("tarde", "🌇 Tarde").replace("-", " · Toma ")
                            st.caption(f"Falta: {momento_disp}")
                        with cols_f[1]:
                            if st.button("Cargar", key=f"btn_atrasada_{atr_key}", use_container_width=True):
                                if st.session_state.get("atrasada_activa") == atr_key:
                                    st.session_state.pop("atrasada_activa", None)
                                else:
                                    st.session_state["atrasada_activa"] = atr_key
                                    st.session_state["atrasada_data"] = {"dia": f["dia"], "fecha": f["fecha"].isoformat(), "momento": tt}
                                st.rerun()
                        # Form inline justo debajo si esta toma es la seleccionada
                        if st.session_state.get("atrasada_activa") == atr_key:
                            with st.form(f"form_atr_{atr_key}"):
                                cf1, cf2, cf3 = st.columns(3)
                                with cf1:
                                    sis_a = st.number_input("Sistólica", min_value=60, max_value=250, value=120, step=1, key=f"sis_atr_{atr_key}")
                                with cf2:
                                    dia_a = st.number_input("Diastólica", min_value=40, max_value=150, value=80, step=1, key=f"dia_atr_{atr_key}")
                                with cf3:
                                    pulso_a = st.number_input("Pulso (bpm)", min_value=30, max_value=220, value=70, step=1, key=f"pul_atr_{atr_key}")
                                confirmar_a = st.checkbox("Confirmo valores correctos (si son elevados)", key=f"conf_atr_{atr_key}")
                                cb1, cb2 = st.columns(2)
                                with cb1:
                                    cancelar_a = st.form_submit_button("Cancelar", use_container_width=True)
                                with cb2:
                                    guardar_a = st.form_submit_button("Guardar", use_container_width=True, type="primary")
                            if guardar_a:
                                if (sis_a > 200 or dia_a > 120) and not confirmar_a:
                                    st.warning(f"⚠️ Los valores {sis_a}/{dia_a} son muy elevados. Marcá la casilla de confirmación si son correctos.")
                                else:
                                    try:
                                        guardar_medicion(codigo, sis_a, dia_a, tt, pulso=int(pulso_a),
                                                         fecha_dia=f["fecha"].isoformat(), atrasada=True)
                                        st.session_state.pop("atrasada_activa", None)
                                        st.session_state.pop("atrasada_data", None)
                                        st.success("✅ Toma atrasada guardada.")
                                        st.rerun()
                                    except Exception as ex:
                                        st.error(f"No se pudo guardar la toma: {ex}")
                            if cancelar_a:
                                st.session_state.pop("atrasada_activa", None)
                                st.session_state.pop("atrasada_data", None)
                                st.rerun()
                    st.markdown("---")

        if cerrado:
            resultado = calcular_resultado(mediciones)
            # Banner de "cierre forzado" si el protocolo se cerró por abandono o expiración
            if abandonado and not (total >= 28):
                dias_rest = max(0, 7 - dia_actual + 1)
                max_pos = total + 4 * dias_rest
                if max_pos < 12:
                    explicacion = (
                        f"Al día {dia_actual} hay solo {total} toma{'s' if total != 1 else ''} cargada{'s' if total != 1 else ''} "
                        f"y quedan {dias_rest} día{'s' if dias_rest != 1 else ''} del protocolo. "
                        f"Aunque cargaras todas las tomas restantes (4 por día), solo llegarías a {max_pos}, "
                        f"y el mínimo clínico requerido es 12."
                    )
                else:
                    explicacion = (
                        f"Al día {dia_actual} hay solo {total} toma{'s' if total != 1 else ''} cargada{'s' if total != 1 else ''} "
                        f"(menos de 1 toma/día). Por adherencia tan baja es muy improbable alcanzar el mínimo clínico "
                        f"(12 tomas en los últimos 6 días)."
                    )
                st.markdown(f"""
                <div style="background:linear-gradient(135deg,rgba(239,68,68,0.20),rgba(239,68,68,0.05));border:2px solid #ef4444;border-radius:14px;padding:1.5rem 1.75rem;margin:1rem 0;">
                  <div style="display:flex;align-items:center;gap:14px;">
                    <div style="font-size:42px;line-height:1;">🛑</div>
                    <div>
                      <div style="font-family:'DM Serif Display',serif;font-size:24px;color:#ef4444;font-weight:500;">Procedimiento cancelado: tomas insuficientes</div>
                      <div style="font-size:15px;color:#e8eef7;margin-top:6px;">{explicacion}</div>
                    </div>
                  </div>
                  <p style="font-size:14px;color:#cbd5e1;line-height:1.5;margin:14px 0 0 0;">Te recomendamos <strong style="color:#e8eef7;">reiniciar el monitoreo</strong> cuando estés listo para hacerlo en los 7 días seguidos. El procedimiento actual se archivará en tu Historial.</p>
                </div>
                """, unsafe_allow_html=True)
            elif expirado and not (total >= 28):
                st.markdown(f"""
                <div style="background:linear-gradient(135deg,rgba(239,68,68,0.20),rgba(239,68,68,0.05));border:2px solid #ef4444;border-radius:14px;padding:1.5rem 1.75rem;margin:1rem 0;">
                  <div style="display:flex;align-items:center;gap:14px;">
                    <div style="font-size:42px;line-height:1;">⏰</div>
                    <div>
                      <div style="font-family:'DM Serif Display',serif;font-size:24px;color:#ef4444;font-weight:500;">El protocolo de 7 días finalizó</div>
                      <div style="font-size:15px;color:#e8eef7;margin-top:6px;">Pasaron los 7 días del seguimiento. Ya no se pueden cargar más tomas en este procedimiento.</div>
                    </div>
                  </div>
                </div>
                """, unsafe_allow_html=True)

            st.markdown("### 🎯 Resultado de tu monitoreo")
            if resultado:
                def _disp(v, suf=""):
                    return f"{v}{suf}" if v is not None else "—"
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.markdown(f'<div class="art-metric"><div class="art-metric-num" style="font-size:22px;">{_disp(resultado.get("sis_manana"))}/{_disp(resultado.get("dia_manana"))}</div><div class="art-metric-label">Promedio mañana</div></div>', unsafe_allow_html=True)
                with c2:
                    st.markdown(f'<div class="art-metric"><div class="art-metric-num" style="font-size:22px;">{_disp(resultado.get("sis_tarde"))}/{_disp(resultado.get("dia_tarde"))}</div><div class="art-metric-label">Promedio tarde</div></div>', unsafe_allow_html=True)
                with c3:
                    st.markdown(f'<div class="art-metric"><div class="art-metric-num" style="font-size:22px;">{_disp(resultado.get("sis_general"))}/{_disp(resultado.get("dia_general"))}</div><div class="art-metric-label">Promedio general</div></div>', unsafe_allow_html=True)
                with c4:
                    pulso_avg = resultado.get("pulso_general")
                    pulso_disp = f"{pulso_avg} bpm" if pulso_avg else "—"
                    st.markdown(f'<div class="art-metric"><div class="art-metric-num" style="font-size:22px;">{pulso_disp}</div><div class="art-metric-label">Pulso promedio</div></div>', unsafe_allow_html=True)

                # Métrica de adherencia + calidad
                adh = resultado.get("adherencia_pct")
                tomas_ult6 = resultado.get("tomas_ult6", 0)
                calidad = resultado.get("calidad", "")
                col_a1, col_a2 = st.columns(2)
                with col_a1:
                    st.markdown(f'<div class="art-metric"><div class="art-metric-num" style="font-size:22px;">{adh}%</div><div class="art-metric-label">Adherencia (sobre 28 tomas)</div></div>', unsafe_allow_html=True)
                with col_a2:
                    cal_color = {"ideal": "#10b981", "util": "#f59e0b", "insuficiente": "#ef4444"}.get(calidad, "#94a3b8")
                    cal_label = {"ideal": "Ideal", "util": "Útil (parcial)", "insuficiente": "Insuficiente"}.get(calidad, "—")
                    st.markdown(f'<div class="art-metric"><div class="art-metric-num" style="font-size:18px;color:{cal_color};">{cal_label}</div><div class="art-metric-label">Calidad del informe · {tomas_ult6}/24 tomas últimos 6 días</div></div>', unsafe_allow_html=True)

                st.caption("El resultado promedia los registros de los días 2 a 7 (se descarta el día 1, según protocolo).")
                if calidad != "insuficiente":
                    st.markdown("**Presión arterial**")
                    grafico_evolucion(mediciones)
                    st.markdown("**Frecuencia cardíaca**")
                    grafico_pulso(mediciones)
                if resultado.get("tipo") == "success":
                    st.success(f"**{resultado['titulo']}** — {resultado['mensaje']}")
                elif resultado.get("tipo") == "warning":
                    st.warning(f"**{resultado['titulo']}** — {resultado['mensaje']}")
                else:
                    st.error(f"**{resultado['titulo']}** — {resultado['mensaje']}")

                # Mini conclusión orientativa
                st.markdown(
                    f'<div style="background:rgba(59,130,246,0.06);border-left:3px solid #3b82f6;'
                    f'padding:12px 16px;border-radius:6px;margin-top:0.75rem;font-size:14px;color:#cbd5e1;line-height:1.6;">'
                    f'<strong style="color:#e8eef7;">🩺 Conclusión orientativa:</strong><br>'
                    f'{generar_conclusion(resultado, mediciones)}'
                    f'</div>',
                    unsafe_allow_html=True)

                # Exportar PDF + envío diferido por mail si todavía no se envió
                eventos = obtener_eventos_adversos(codigo)
                alertas = obtener_alertas(codigo)
                pdf_bytes = None
                try:
                    pdf_bytes = generar_pdf_hbpm(paciente, mediciones, resultado, eventos, alertas)
                except Exception:
                    pdf_bytes = None

                # Si no llegó a enviarse el PDF en su momento, lo enviamos ahora
                if pdf_bytes and not paciente.get("ultimo_pdf_enviado_at") and paciente.get("email"):
                    try:
                        if enviar_pdf_informe(paciente.get("email"), paciente.get("nombre", ""), pdf_bytes):
                            actualizar_paciente(codigo, {"ultimo_pdf_enviado_at": now_arg().isoformat()})
                            st.session_state.paciente_data = buscar_paciente(codigo)
                            paciente = st.session_state.paciente_data
                    except Exception:
                        pass

                if paciente.get("ultimo_pdf_enviado_at"):
                    st.info("📧 El informe en PDF se envió a tu email. Revisalo y guardalo. También podés descargarlo abajo.")

                if pdf_bytes:
                    st.download_button(
                        "📄 Descargar informe HBPM en PDF",
                        data=pdf_bytes,
                        file_name=f"HBPM_{paciente.get('apellido','')}_{codigo}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )

                # Botón de reiniciar procedimiento (con confirmación)
                st.markdown("---")
                st.markdown("#### 🔄 ¿Necesitás empezar un nuevo monitoreo?")
                st.markdown('<p style="font-size:13px;color:#94a3b8;">Al reiniciar, este informe queda guardado en tu Historial y empezás un monitoreo nuevo de 7 días desde cero. Tus datos personales y tu medicación se conservan.</p>', unsafe_allow_html=True)
                if not st.session_state.get("confirmar_reiniciar"):
                    if st.button("🔄 Reiniciar procedimiento", use_container_width=True, key="btn_reiniciar"):
                        st.session_state.confirmar_reiniciar = True
                        st.rerun()
                else:
                    st.warning("⚠️ Vas a archivar este monitoreo en tu Historial y empezar uno nuevo. ¿Continuar?")
                    cR1, cR2 = st.columns(2)
                    with cR1:
                        if st.button("Cancelar", use_container_width=True, key="btn_cancelar_reiniciar"):
                            st.session_state.pop("confirmar_reiniciar", None)
                            st.rerun()
                    with cR2:
                        if st.button("Sí, reiniciar", type="primary", use_container_width=True, key="btn_confirmar_reiniciar"):
                            if archivar_procedimiento(codigo, paciente, mediciones, resultado, eventos, alertas):
                                reiniciar_procedimiento_paciente(codigo)
                                st.session_state.paciente_data = buscar_paciente(codigo)
                                st.session_state.pop("confirmar_reiniciar", None)
                                st.success("✅ Procedimiento archivado. ¡Empezamos uno nuevo!")
                                st.rerun()
                            else:
                                st.error("No se pudo archivar el procedimiento. Probá de nuevo en unos segundos.")

        elif terminado_dia:
            # Mensaje grande cuando completó el día
            st.markdown(f"""
            <div style="background:linear-gradient(135deg,rgba(16,185,129,0.18),rgba(16,185,129,0.05));border:1px solid rgba(16,185,129,0.5);border-radius:14px;padding:2rem;text-align:center;margin:1rem 0;">
              <div style="font-size:60px;line-height:1;">✅</div>
              <div style="font-family:'DM Serif Display',serif;font-size:28px;color:#e8eef7;margin-top:1rem;">¡Listo por hoy!</div>
              <p style="color:#94a3b8;margin-top:0.75rem;font-size:15px;">Completaste las 4 tomas del Día {dia_actual}.<br>El sistema avanza automáticamente al Día {min(dia_actual+1,7)} cuando cambie la fecha.</p>
            </div>
            """, unsafe_allow_html=True)
            if total >= 4:
                with st.expander("📈 Ver evolución hasta ahora"):
                    st.markdown("**Presión arterial**")
                    grafico_evolucion(mediciones)
                    st.markdown("**Frecuencia cardíaca**")
                    grafico_pulso(mediciones)
        else:
            # Mensaje grande de transición cuando terminó la mañana y faltan tomas de la tarde
            if terminada_manana and es_tarde:
                st.markdown("""
                <div style="background:linear-gradient(135deg,rgba(245,158,11,0.18),rgba(245,158,11,0.05));border:1px solid rgba(245,158,11,0.5);border-radius:14px;padding:1.5rem;text-align:center;margin:1rem 0;">
                  <div style="font-size:50px;line-height:1;">🌇</div>
                  <div style="font-family:'DM Serif Display',serif;font-size:24px;color:#e8eef7;margin-top:0.5rem;">Terminaste la mañana</div>
                  <p style="color:#94a3b8;margin-top:0.5rem;font-size:14px;">Ahora corresponden las <strong style="color:#f59e0b;">tomas de la TARDE</strong> (idealmente entre las 18 y 21 hs).<br>Volvé a esta misma pantalla más tarde.</p>
                </div>
                """, unsafe_allow_html=True)

            momento_display = proxima.replace("mañana", "🌅 Mañana").replace("tarde", "🌇 Tarde").replace("-", " · Toma ")
            color_proxima = "#3b82f6" if es_manana else "#f59e0b"
            st.markdown(f"""
            <div class="section-eyebrow">Próxima toma</div>
            <div style="font-family:'DM Serif Display',serif;font-size:24px;color:{color_proxima};margin-bottom:1rem;">{momento_display}</div>
            """, unsafe_allow_html=True)
            if proxima in ["mañana-2", "tarde-2"]:
                st.info("⏱ Esperá 1-2 minutos desde la toma anterior.")

            with st.form("form_medicion"):
                col_f1, col_f2, col_f3 = st.columns(3)
                with col_f1:
                    sis = st.number_input("Sistólica (mayor)", min_value=60, max_value=250, value=120, step=1)
                with col_f2:
                    dia = st.number_input("Diastólica (menor)", min_value=40, max_value=150, value=80, step=1)
                with col_f3:
                    pulso = st.number_input("Pulso (bpm)", min_value=30, max_value=220, value=70, step=1, help="Frecuencia cardíaca que muestra tu tensiómetro")
                confirmar_alto = st.checkbox("Confirmo que los valores son correctos (requerido si son muy elevados)")
                guardar_btn = st.form_submit_button("Guardar medición →", use_container_width=True)
            if guardar_btn:
                if (sis > 200 or dia > 120) and not confirmar_alto:
                    st.warning(f"⚠️ Los valores {sis}/{dia} son muy elevados. Marcá la casilla de confirmación si son correctos.")
                else:
                    # Fijamos la fecha del día N del protocolo (no del calendario actual)
                    # para que tomas hechas tarde por la noche o con un día de retraso queden
                    # en el día correcto del seguimiento.
                    fecha_protocolo = fecha_de_dia(mediciones, dia_actual).isoformat() if mediciones else hoy_arg().isoformat()
                    guardar_medicion(codigo, sis, dia, proxima, pulso=int(pulso),
                                     fecha_dia=fecha_protocolo, atrasada=False)
                    st.success("✅ Medición guardada.")
                    st.rerun()

            if total >= 2:
                with st.expander("📈 Ver evolución hasta ahora"):
                    st.markdown("**Presión arterial**")
                    grafico_evolucion(mediciones)
                    st.markdown("**Frecuencia cardíaca**")
                    grafico_pulso(mediciones)

        # Editor de tomas del día (editables solo si <12hs)
        if med_dia:
            with st.expander(f"✏️ Tomas cargadas hoy ({len(med_dia)}/4) — podés editar dentro de las 12hs"):
                for m in med_dia:
                    momento_disp = m["momento"].replace("mañana", "🌅 Mañana").replace("tarde", "🌇 Tarde").replace("-", " · Toma ")
                    editable = puede_editar(m)
                    pulso_disp = f"· {m.get('pulso','—')} bpm" if m.get("pulso") else ""
                    edit_state_key = f"editando_{m['id']}"

                    if st.session_state.get(edit_state_key):
                        st.markdown(f"**Editando: {momento_disp}**")
                        with st.form(f"form_edit_{m['id']}"):
                            cE1, cE2, cE3 = st.columns(3)
                            with cE1:
                                sis_e = st.number_input("Sistólica", min_value=60, max_value=250, value=int(m.get("sistolica") or 120), step=1, key=f"e_sis_{m['id']}")
                            with cE2:
                                dia_e = st.number_input("Diastólica", min_value=40, max_value=150, value=int(m.get("diastolica") or 80), step=1, key=f"e_dia_{m['id']}")
                            with cE3:
                                pulso_e = st.number_input("Pulso", min_value=30, max_value=220, value=int(m.get("pulso") or 70), step=1, key=f"e_pul_{m['id']}")
                            cBE1, cBE2 = st.columns(2)
                            with cBE1:
                                ok_edit = st.form_submit_button("Guardar cambios", use_container_width=True)
                            with cBE2:
                                cancel_edit = st.form_submit_button("Cancelar", use_container_width=True)
                        if ok_edit:
                            if editar_medicion(m["id"], sis_e, dia_e, pulso=int(pulso_e)):
                                st.success("✅ Toma actualizada.")
                                del st.session_state[edit_state_key]
                                st.rerun()
                            else:
                                st.error("No se pudo guardar la edición.")
                        if cancel_edit:
                            del st.session_state[edit_state_key]
                            st.rerun()
                    else:
                        cL, cR = st.columns([4, 1])
                        with cL:
                            atrasada_lbl = " · ⚠️ atrasada" if m.get("cargada_atrasada") else ""
                            editada_lbl = " · editada" if m.get("editada_at") else ""
                            st.markdown(f"**{momento_disp}** — {m.get('sistolica')}/{m.get('diastolica')} mmHg {pulso_disp}{atrasada_lbl}{editada_lbl}")
                        with cR:
                            if editable:
                                if st.button("Editar", key=f"btn_edit_{m['id']}"):
                                    st.session_state[edit_state_key] = True
                                    st.rerun()
                            else:
                                st.caption("No editable (>12hs)")

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

        # Pasos a seguir como referencia (al final, plegado por defecto)
        with st.expander("📖 Cómo medir bien tu presión (pasos a seguir)"):
            seccion_pasos()

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
            st.markdown('<div class="art-card"><h3 style="margin-top:0;">👨‍⚕️ Acceso médico</h3>', unsafe_allow_html=True)
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
                            iniciar_sesion_persistente("medico", medico["email"])
                            st.rerun()
                        else:
                            st.error("❌ Contraseña incorrecta.")
                    elif medico and not medico.get("password_set"):
                        st.warning("Tu cuenta no está activada. Revisá tu email para activarla.")
                    else:
                        st.error("❌ Email no encontrado.")
            st.markdown('</div>', unsafe_allow_html=True)
        with tab_reset:
            st.markdown('<div class="art-card"><h3 style="margin-top:0;">Recuperar contraseña</h3>', unsafe_allow_html=True)
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
                        st.markdown("**Presión arterial**")
                        grafico_evolucion(mediciones)
                        st.markdown("**Frecuencia cardíaca**")
                        grafico_pulso(mediciones)

                    # Mini conclusión clínica
                    if resultado:
                        st.markdown(f'<div style="background:rgba(59,130,246,0.06);border-left:3px solid #3b82f6;padding:10px 14px;border-radius:6px;margin-top:0.5rem;font-size:13px;color:#cbd5e1;line-height:1.5;">{generar_conclusion(resultado, mediciones)}</div>', unsafe_allow_html=True)

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
