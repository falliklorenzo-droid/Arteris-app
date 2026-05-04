import streamlit as st
from supabase import create_client, Client
from datetime import datetime, date
import resend
import uuid
import pandas as pd
import altair as alt

st.set_page_config(
    page_title="Arteris · Monitor de Presión Arterial",
    page_icon="🩺",
    layout="wide"
)

# ── CSS Global ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=DM+Serif+Display:ital@0;1&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif !important;
    background-color: #0a1628 !important;
    color: #e8eef7 !important;
}
.stApp { background-color: #0a1628 !important; }
section[data-testid="stSidebar"] { display: none; }

/* Navbar */
.arteris-nav {
    background: rgba(10,22,40,0.98);
    border-bottom: 1px solid rgba(59,130,246,0.2);
    padding: 0 2rem;
    height: 60px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: relative;
    margin: -1rem -1rem 2rem -1rem;
}
.arteris-nav::after {
    content: '';
    position: absolute;
    bottom: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, #1d4ed8, #3b82f6, #06b6d4, transparent);
}
.logo-wrap { display: flex; align-items: center; gap: 10px; }
.logo-text {
    font-family: 'DM Serif Display', serif;
    font-size: 24px;
    color: #e8eef7;
    letter-spacing: -0.5px;
}
.logo-text span { color: #3b82f6; }
.logo-tag {
    font-size: 10px;
    color: #64748b;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    margin-top: 1px;
}

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

/* Metric */
.art-metric {
    text-align: center;
    padding: 1rem;
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 10px;
}
.art-metric-num {
    font-family: 'DM Serif Display', serif;
    font-size: 36px;
    color: #3b82f6;
    line-height: 1;
}
.art-metric-label {
    font-size: 12px;
    color: #64748b;
    margin-top: 4px;
    letter-spacing: 0.5px;
}

/* Status badges */
.badge-ok { background: rgba(34,197,94,0.12); color: #22c55e; padding: 4px 12px; border-radius: 20px; font-size: 12px; }
.badge-warn { background: rgba(234,179,8,0.12); color: #eab308; padding: 4px 12px; border-radius: 20px; font-size: 12px; }
.badge-alert { background: rgba(239,68,68,0.12); color: #ef4444; padding: 4px 12px; border-radius: 20px; font-size: 12px; }

/* Buttons override */
.stButton > button {
    background: #1d4ed8 !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 14px !important;
    padding: 0.5rem 1.5rem !important;
    transition: background 0.2s !important;
}
.stButton > button:hover { background: #1e40af !important; }
.stButton > button[kind="secondary"] {
    background: transparent !important;
    border: 1px solid rgba(148,163,184,0.3) !important;
    color: #94a3b8 !important;
}

/* Inputs */
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stSelectbox > div > div,
.stRadio > div {
    background: rgba(255,255,255,0.05) !important;
    border-color: rgba(59,130,246,0.2) !important;
    color: #e8eef7 !important;
    border-radius: 8px !important;
}

/* Footer */
.arteris-footer {
    background: rgba(0,0,0,0.3);
    border-top: 1px solid rgba(255,255,255,0.06);
    padding: 2rem;
    margin: 3rem -1rem -1rem -1rem;
}
.footer-institutions {
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
    margin: 1rem 0;
}
.inst-badge {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 11px;
    color: #64748b;
}
.inst-badge strong { color: #94a3b8; font-size: 12px; }
.footer-bottom {
    border-top: 1px solid rgba(255,255,255,0.05);
    padding-top: 1rem;
    font-size: 11px;
    color: #475569;
    display: flex;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 8px;
}

/* Progress bar */
.art-progress-wrap {
    background: rgba(255,255,255,0.08);
    border-radius: 4px;
    height: 6px;
    overflow: hidden;
    margin: 8px 0;
}
.art-progress-fill {
    height: 100%;
    border-radius: 4px;
    background: linear-gradient(90deg, #1d4ed8, #06b6d4);
    transition: width 0.5s ease;
}

/* Day dots */
.day-dots { display: flex; gap: 8px; margin: 12px 0; }
.day-dot {
    width: 32px; height: 32px;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 11px; font-weight: 500;
}
.day-done { background: rgba(59,130,246,0.2); color: #3b82f6; }
.day-today { background: #1d4ed8; color: white; }
.day-pending { background: rgba(255,255,255,0.05); color: #475569; }

/* Section title */
.section-eyebrow {
    font-size: 11px;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: #3b82f6;
    margin-bottom: 6px;
}
.section-title {
    font-family: 'DM Serif Display', serif;
    font-size: 28px;
    color: #e8eef7;
    margin-bottom: 8px;
    line-height: 1.2;
}
.section-sub {
    font-size: 14px;
    color: #94a3b8;
    line-height: 1.6;
    margin-bottom: 1.5rem;
}

/* Patient row */
.patient-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 0;
    border-bottom: 1px solid rgba(255,255,255,0.04);
}
.patient-avatar {
    width: 36px; height: 36px;
    border-radius: 50%;
    background: rgba(59,130,246,0.2);
    display: flex; align-items: center; justify-content: center;
    font-size: 12px; font-weight: 500; color: #3b82f6;
}

/* Hide streamlit default elements */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header { visibility: hidden; }
.block-container { padding-top: 0 !important; max-width: 1100px; }
</style>
""", unsafe_allow_html=True)



def navbar(subtitulo=""):
    st.markdown(f"""
    <div class="arteris-nav">
        <div class="logo-wrap">
            <svg width="36" height="36" viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect width="36" height="36" rx="9" fill="#1d4ed8"/>
              <path d="M4 20 L9 20 L12 13 L15 25 L18 9 L21 22 L24 16 L27 20 L32 20"
                    stroke="white" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
            </svg>
            <div>
                <div class="logo-text">Arteri<span>s</span></div>
                <div class="logo-tag">Monitor de Presión Arterial</div>
            </div>
        </div>
        <div style="font-size:13px;color:#64748b;">{subtitulo}</div>
    </div>
    """, unsafe_allow_html=True)

def footer():
    st.markdown("""
    <div class="arteris-footer">
        <div style="font-size:12px;color:#64748b;margin-bottom:8px;letter-spacing:1px;text-transform:uppercase;">
            Avalado por instituciones médicas
        </div>
        <div class="footer-institutions">
            <div class="inst-badge"><strong>ESH</strong> · European Society of Hypertension</div>
            <div class="inst-badge"><strong>FAC</strong> · Federación Argentina de Cardiología</div>
            <div class="inst-badge"><strong>AHA</strong> · American Heart Association</div>
            <div class="inst-badge"><strong>SAH</strong> · Sociedad Argentina de Hipertensión</div>
        </div>
        <div class="footer-bottom">
            <span>© 2025 Arteris · Plataforma orientativa, no reemplaza la consulta médica profesional</span>
            <span>Privacidad · Términos de uso · Ley 25.326 · Contacto</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

# ── Supabase ──────────────────────────────────────────────────────────────────
def get_sb() -> Client:
    return create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])

def buscar_paciente(codigo):
    try:
        r = get_sb().table("pacientes").select("*").eq("codigo", codigo).execute()
        return r.data[0] if r.data else None
    except:
        return None

def actualizar_paciente(codigo, datos):
    get_sb().table("pacientes").update(datos).eq("codigo", codigo).execute()

def crear_paciente(nombre, apellido, email):
    sb = get_sb()
    codigo = str(uuid.uuid4())[:8].upper()
    sb.table("pacientes").insert({
        "codigo": codigo,
        "nombre": nombre,
        "apellido": apellido,
        "email": email,
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

def obtener_mediciones(codigo):
    r = get_sb().table("mediciones").select("*").eq("codigo_paciente", codigo).order("fecha").execute()
    return r.data

def obtener_todos_pacientes():
    r = get_sb().table("pacientes").select("*").order("fecha_registro", desc=True).execute()
    return r.data

# ── Email ─────────────────────────────────────────────────────────────────────
def enviar_bienvenida(nombre, email, codigo):
    try:
        resend.api_key = st.secrets["resend"]["api_key"]
        url = f"https://arteris-app.streamlit.app/?codigo={codigo}"
        resend.Emails.send({
            "from": "Arteris <onboarding@resend.dev>",
            "to": email,
            "subject": "Tu acceso a Arteris · Monitor de Presión Arterial",
            "html": f"""
            <div style="font-family:'DM Sans',Arial,sans-serif;max-width:560px;margin:0 auto;background:#0a1628;color:#e8eef7;border-radius:12px;overflow:hidden;">
              <div style="background:#1d4ed8;padding:24px 32px;">
                <h1 style="font-size:24px;margin:0;color:white;font-weight:400;">Arteris</h1>
                <p style="font-size:12px;color:rgba(255,255,255,0.6);margin:4px 0 0;letter-spacing:1px;text-transform:uppercase;">Monitor de Presión Arterial</p>
              </div>
              <div style="padding:32px;">
                <p style="font-size:16px;color:#e8eef7;">Hola <strong>{nombre}</strong>,</p>
                <p style="color:#94a3b8;line-height:1.6;">Tu médico te habilitó el acceso a Arteris. Durante los próximos 7 días vas a registrar tu presión arterial 2 veces por la mañana y 2 veces por la tarde.</p>
                <div style="text-align:center;margin:32px 0;">
                  <a href="{url}" style="background:#1d4ed8;color:white;padding:14px 32px;text-decoration:none;border-radius:8px;font-size:15px;display:inline-block;">
                    Acceder a Arteris →
                  </a>
                </div>
                <p style="font-size:12px;color:#475569;">O copiá este enlace: {url}</p>
                <hr style="border-color:rgba(255,255,255,0.08);margin:24px 0;">
                <p style="font-size:11px;color:#475569;">Esta plataforma es orientativa y no reemplaza la consulta médica profesional.</p>
              </div>
            </div>
            """
        })
        return True
    except Exception as e:
        st.error(f"Error de email: {e}")
        return False

# ── Lógica de resultados ──────────────────────────────────────────────────────
def calcular_resultado(mediciones):
    if len(mediciones) < 4:
        return None, None, None, None
    df = pd.DataFrame(mediciones)
    df["fecha_dt"] = pd.to_datetime(df["fecha"])
    df["dia"] = df["fecha_dt"].dt.date
    dias = sorted(df["dia"].unique())
    if len(dias) >= 7:
        df = df[df["dia"].isin(dias[1:7])]
    prom_sis = df["sistolica"].mean()
    prom_dia = df["diastolica"].mean()
    if prom_sis <= 135 and prom_dia <= 85:
        return "✅ Presión controlada", "Tu presión arterial está dentro del rango normal. Realizá tu próximo control en 3 meses.", "success", (round(prom_sis,1), round(prom_dia,1))
    elif prom_sis >= 180 or prom_dia >= 110:
        return "🔴 Urgencia hipertensiva", "Tus valores son muy elevados. Consultá una guardia médica de inmediato.", "error", (round(prom_sis,1), round(prom_dia,1))
    else:
        return "⚠️ Presión no controlada", "Tu presión no está dentro del rango normal. Consultá con tu médico a la brevedad.", "warning", (round(prom_sis,1), round(prom_dia,1))

def grafico_evolucion(mediciones):
    df = pd.DataFrame(mediciones)
    df["fecha_dt"] = pd.to_datetime(df["fecha"])
    df["etiqueta"] = df["fecha_dt"].dt.strftime("%d/%m") + " · " + df["momento"].fillna("")
    chart = alt.Chart(df).transform_fold(
        ["sistolica", "diastolica"], as_=["tipo", "valor"]
    ).mark_line(point=True).encode(
        x=alt.X("etiqueta:N", title="", sort=None, axis=alt.Axis(labelAngle=-45, labelColor="#64748b", gridColor="#1e293b")),
        y=alt.Y("valor:Q", title="mmHg", axis=alt.Axis(labelColor="#64748b", gridColor="#1e293b")),
        color=alt.Color("tipo:N", scale=alt.Scale(domain=["sistolica","diastolica"], range=["#3b82f6","#06b6d4"]),
                        legend=alt.Legend(labelColor="#94a3b8", titleColor="#94a3b8")),
        tooltip=["etiqueta:N","sistolica:Q","diastolica:Q","momento:N"]
    ).properties(height=280, background="#0a1628").configure_view(
        strokeColor="#1e293b"
    )
    st.altair_chart(chart, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════════════════════════════
params = st.query_params
codigo_url = params.get("codigo", "")

if "vista" not in st.session_state:
    st.session_state.vista = "paciente" if codigo_url else "inicio"
if "codigo_paciente" not in st.session_state:
    st.session_state.codigo_paciente = codigo_url
if "medico_ok" not in st.session_state:
    st.session_state.medico_ok = False
if "consentimiento_ok" not in st.session_state:
    st.session_state.consentimiento_ok = False

# ══════════════════════════════════════════════════════════════════════════════
# VISTA: INICIO
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.vista == "inicio":
    navbar()
    col_left, col_right = st.columns([1.2, 1], gap="large")
    with col_left:
        st.markdown("""
        <div class="section-eyebrow">Monitoreo de presión arterial</div>
        <div class="section-title">Control preciso.<br><em style="color:#3b82f6;font-style:italic;">Resultados claros.</em></div>
        <div class="section-sub">
            Registrá tu presión durante 7 días y recibí un diagnóstico orientativo
            basado en protocolos médicos internacionales. Simple, seguro y accesible.
        </div>
        """, unsafe_allow_html=True)
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("🙋 Soy paciente", use_container_width=True):
                st.session_state.vista = "paciente"
                st.rerun()
        with col_b:
            if st.button("👨‍⚕️ Soy médico", use_container_width=True):
                st.session_state.vista = "medico"
                st.rerun()
        st.markdown("""
        <div style="display:flex;gap:2rem;margin-top:2rem;">
            <div style="text-align:center;">
                <div style="font-family:'DM Serif Display',serif;font-size:28px;color:#3b82f6;">+200</div>
                <div style="font-size:12px;color:#64748b;">Pacientes</div>
            </div>
            <div style="text-align:center;">
                <div style="font-family:'DM Serif Display',serif;font-size:28px;color:#3b82f6;">7</div>
                <div style="font-size:12px;color:#64748b;">Días de seguimiento</div>
            </div>
            <div style="text-align:center;">
                <div style="font-family:'DM Serif Display',serif;font-size:28px;color:#3b82f6;">135/85</div>
                <div style="font-size:12px;color:#64748b;">Umbral de control</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col_right:
        st.markdown("""
        <div class="art-card">
            <div style="font-size:11px;color:#64748b;letter-spacing:1px;text-transform:uppercase;margin-bottom:12px;">
                ¿Cómo funciona?
            </div>
            <div style="display:flex;flex-direction:column;gap:14px;">
                <div style="display:flex;gap:12px;align-items:flex-start;">
                    <div style="width:28px;height:28px;border-radius:50%;background:#1d4ed8;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:500;flex-shrink:0;">1</div>
                    <div><div style="font-size:14px;color:#e8eef7;font-weight:500;">Tu médico te envía el acceso</div><div style="font-size:12px;color:#64748b;margin-top:2px;">Recibís un enlace por email directo a tu cuenta</div></div>
                </div>
                <div style="display:flex;gap:12px;align-items:flex-start;">
                    <div style="width:28px;height:28px;border-radius:50%;background:#1d4ed8;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:500;flex-shrink:0;">2</div>
                    <div><div style="font-size:14px;color:#e8eef7;font-weight:500;">Registrás tu presión 7 días</div><div style="font-size:12px;color:#64748b;margin-top:2px;">2 tomas a la mañana y 2 a la tarde cada día</div></div>
                </div>
                <div style="display:flex;gap:12px;align-items:flex-start;">
                    <div style="width:28px;height:28px;border-radius:50%;background:#1d4ed8;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:500;flex-shrink:0;">3</div>
                    <div><div style="font-size:14px;color:#e8eef7;font-weight:500;">Recibís tu resultado</div><div style="font-size:12px;color:#64748b;margin-top:2px;">La plataforma calcula tu promedio y te da un diagnóstico</div></div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    footer()

# ══════════════════════════════════════════════════════════════════════════════
# VISTA: MÉDICO
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.vista == "medico":
    navbar("Panel del médico")

    if st.button("← Volver al inicio"):
        st.session_state.vista = "inicio"
        st.session_state.medico_ok = False
        st.rerun()

    if not st.session_state.medico_ok:
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            st.markdown('<div class="art-card">', unsafe_allow_html=True)
            st.markdown("### 🔐 Acceso médico")
            pwd = st.text_input("Contraseña:", type="password")
            if st.button("Ingresar al panel", use_container_width=True):
                if pwd == st.secrets.get("medico", {}).get("password", "medico123"):
                    st.session_state.medico_ok = True
                    st.rerun()
                else:
                    st.error("Contraseña incorrecta.")
            st.markdown('</div>', unsafe_allow_html=True)
    else:
        tab1, tab2 = st.tabs(["➕ Nuevo paciente", "📋 Mis pacientes"])

        with tab1:
            col1, col2 = st.columns([1,1], gap="large")
            with col1:
                st.markdown('<div class="art-card">', unsafe_allow_html=True)
                st.markdown("#### Agregar paciente")
                nombre = st.text_input("Nombre")
                apellido = st.text_input("Apellido")
                email = st.text_input("Email")
                if st.button("Crear paciente y enviar acceso", use_container_width=True):
                    if nombre and apellido and email:
                        with st.spinner("Creando acceso y enviando email..."):
                            codigo = crear_paciente(nombre, apellido, email)
                            ok = enviar_bienvenida(nombre, email, codigo)
                        if ok:
                            st.success(f"✅ Acceso enviado a {email}")
                            url = f"https://arteris-app.streamlit.app/?codigo={codigo}"
                            st.info(f"Enlace: {url}")
                        else:
                            st.warning(f"Paciente creado. Código manual: **{codigo}**")
                    else:
                        st.error("Completá todos los campos.")
                st.markdown('</div>', unsafe_allow_html=True)
            with col2:
                st.markdown("""
                <div class="art-card-white">
                    <div style="font-size:12px;color:#64748b;margin-bottom:12px;letter-spacing:1px;text-transform:uppercase;">
                        ¿Qué recibe el paciente?
                    </div>
                    <p style="font-size:13px;color:#94a3b8;line-height:1.6;">
                        El paciente recibe un email con un enlace único. Al hacer clic entra directamente
                        a Arteris, acepta el consentimiento informado, completa sus datos y empieza
                        a registrar su presión arterial.
                    </p>
                    <p style="font-size:12px;color:#64748b;margin-top:12px;">
                        El seguimiento dura 7 días con 4 tomas diarias.
                    </p>
                </div>
                """, unsafe_allow_html=True)

        with tab2:
            pacientes = obtener_todos_pacientes()
            if not pacientes:
                st.info("Aún no hay pacientes registrados.")
            else:
                for p in pacientes:
                    mediciones = obtener_mediciones(p["codigo"])
                    nombre_completo = f"{p.get('nombre','?')} {p.get('apellido','?')}"
                    iniciales = f"{p.get('nombre','?')[0]}{p.get('apellido','?')[0]}".upper()
                    total = len(mediciones)
                    _, _, tipo, promedios = calcular_resultado(mediciones)
                    if tipo == "success":
                        badge = '<span class="badge-ok">Controlada</span>'
                    elif tipo == "error":
                        badge = '<span class="badge-alert">Urgente</span>'
                    elif tipo == "warning":
                        badge = '<span class="badge-warn">No controlada</span>'
                    else:
                        badge = f'<span style="font-size:12px;color:#64748b;">{total}/28 tomas</span>'

                    with st.expander(f"{nombre_completo} · {p.get('email','?')}"):
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            st.markdown(f'<div class="art-metric"><div class="art-metric-num">{total}</div><div class="art-metric-label">Tomas registradas</div></div>', unsafe_allow_html=True)
                        with c2:
                            prom_txt = f"{promedios[0]}/{promedios[1]}" if promedios else "—"
                            st.markdown(f'<div class="art-metric"><div class="art-metric-num" style="font-size:24px;">{prom_txt}</div><div class="art-metric-label">Promedio mmHg</div></div>', unsafe_allow_html=True)
                        with c3:
                            st.markdown(f'<div class="art-metric">{badge}</div>', unsafe_allow_html=True)
                        if total >= 4:
                            grafico_evolucion(mediciones)
    footer()

# ══════════════════════════════════════════════════════════════════════════════
# VISTA: PACIENTE
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.vista == "paciente":
    navbar("Portal del paciente")

    if not st.session_state.codigo_paciente:
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            if st.button("← Volver"):
                st.session_state.vista = "inicio"
                st.rerun()
            st.markdown('<div class="art-card">', unsafe_allow_html=True)
            st.markdown("### Ingresá tu código de acceso")
            st.markdown('<p style="font-size:13px;color:#94a3b8;">Tu médico te proporcionó un código o un enlace de acceso.</p>', unsafe_allow_html=True)
            codigo_input = st.text_input("Código:", placeholder="Ej: A1B2C3D4")
            if st.button("Ingresar →", use_container_width=True):
                if codigo_input:
                    p = buscar_paciente(codigo_input.strip().upper())
                    if p is None:
                        st.error("❌ Código inválido. Verificá el código que te envió tu médico.")
                    else:
                        st.session_state.codigo_paciente = codigo_input.strip().upper()
                        st.rerun()
                else:
                    st.error("Por favor ingresá tu código.")
            st.markdown('</div>', unsafe_allow_html=True)

    else:
        codigo = st.session_state.codigo_paciente
        paciente = buscar_paciente(codigo)

        if paciente is None:
            st.error("❌ Código inválido.")
            if st.button("Volver"):
                st.session_state.codigo_paciente = ""
                st.rerun()

        # CONSENTIMIENTO
        elif not paciente.get("consentimiento_aceptado") and not st.session_state.consentimiento_ok:
            col1, col2, col3 = st.columns([1,2,1])
            with col2:
                st.markdown('<div class="art-card">', unsafe_allow_html=True)
                st.markdown("### 📄 Consentimiento informado")
                st.markdown("""
<div style="background:rgba(59,130,246,0.08);border:1px solid rgba(59,130,246,0.2);border-radius:10px;padding:1.25rem;font-size:13px;color:#94a3b8;line-height:1.7;">
<strong style="color:#e8eef7;">Esta plataforma almacena los siguientes datos personales:</strong><br>
- Nombre, apellido, edad y sexo biológico<br>
- Medicación actual y dosis<br>
- Valores de presión arterial durante 7 días<br><br>
<strong style="color:#e8eef7;">¿Para qué se usan?</strong><br>
Únicamente para calcular el promedio de tu presión arterial y mostrarte un resultado orientativo.
Tus datos son accesibles solo por vos y tu médico tratante.<br><br>
<strong style="color:#e8eef7;">Tus derechos (Ley 25.326):</strong><br>
Podés acceder, rectificar y suprimir tus datos en cualquier momento contactando a tu médico.
</div>
                """, unsafe_allow_html=True)
                aceptar = st.checkbox("Leí y acepto el uso de mis datos personales")
                if st.button("Continuar →", use_container_width=True, disabled=not aceptar):
                    st.session_state.consentimiento_ok = True
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

        # REGISTRO
        elif not paciente.get("edad"):
            col1, col2, col3 = st.columns([1,2,1])
            with col2:
                st.markdown('<div class="art-card">', unsafe_allow_html=True)
                st.markdown(f"### 📋 Hola, {paciente.get('nombre', '')} 👋")
                st.markdown('<p style="font-size:13px;color:#94a3b8;margin-bottom:1rem;">Completá tus datos para comenzar el seguimiento.</p>', unsafe_allow_html=True)
                with st.form("form_registro"):
                    edad = st.number_input("Edad", min_value=1, max_value=120, step=1)
                    sexo = st.selectbox("Sexo biológico", ["Femenino", "Masculino", "Otro"])
                    toma_med = st.radio("¿Tomás medicación para la presión arterial?", ["No", "Sí"], horizontal=True)
                    medicacion = ""
                    dosis = ""
                    if toma_med == "Sí":
                        medicacion = st.text_input("¿Qué medicación tomás?", placeholder="Ej: Enalapril")
                        dosis = st.text_input("¿Cuál es la dosis?", placeholder="Ej: 10mg cada 12hs")
                    enviado = st.form_submit_button("Guardar y comenzar →", use_container_width=True)
                if enviado:
                    if edad:
                        actualizar_paciente(codigo, {
                            "edad": int(edad), "sexo": sexo,
                            "toma_medicacion": toma_med == "Sí",
                            "medicacion": medicacion, "dosis": dosis,
                            "consentimiento_aceptado": True
                        })
                        st.success("✅ ¡Registro completado!")
                        st.rerun()
                    else:
                        st.error("Por favor completá tu edad.")
                st.markdown('</div>', unsafe_allow_html=True)

        # HOMEPAGE DEL PACIENTE
        else:
            nombre = paciente.get("nombre", "Paciente")
            mediciones = obtener_mediciones(codigo)
            total = len(mediciones)
            hoy = date.today()
            med_hoy = [m for m in mediciones if pd.to_datetime(m["fecha"]).date() == hoy]
            momentos_hoy = [m["momento"] for m in med_hoy]
            tomas_orden = ["mañana-1", "mañana-2", "tarde-1", "tarde-2"]
            proxima = next((t for t in tomas_orden if t not in momentos_hoy), None)

            # Header paciente
            col_h1, col_h2 = st.columns([2,1])
            with col_h1:
                st.markdown(f"""
                <div style="margin-bottom:1.5rem;">
                    <div class="section-eyebrow">Bienvenido de nuevo</div>
                    <div class="section-title">{nombre} 👋</div>
                </div>
                """, unsafe_allow_html=True)
            with col_h2:
                dias_completos = len(set(pd.to_datetime(m["fecha"]).date() for m in mediciones))
                st.markdown(f"""
                <div class="art-metric">
                    <div class="art-metric-num">{dias_completos}/7</div>
                    <div class="art-metric-label">Días completados</div>
                </div>
                """, unsafe_allow_html=True)

            # Progreso
            pct = min(total / 28, 1.0)
            dias_labels = ["L","M","M","J","V","S","D"]
            dias_html = ""
            for i, l in enumerate(dias_labels):
                if i < dias_completos - 1:
                    cls = "day-done"
                elif i == dias_completos - 1:
                    cls = "day-today"
                else:
                    cls = "day-pending"
                dias_html += f'<div class="day-dot {cls}">{l}</div>'

            st.markdown(f"""
            <div class="art-card-white">
                <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
                    <span style="font-size:13px;color:#94a3b8;">Progreso del seguimiento</span>
                    <span style="font-size:13px;color:#3b82f6;font-weight:500;">{total}/28 tomas</span>
                </div>
                <div class="art-progress-wrap">
                    <div class="art-progress-fill" style="width:{pct*100:.0f}%"></div>
                </div>
                <div class="day-dots">{dias_html}</div>
            </div>
            """, unsafe_allow_html=True)

            # Instructivo
            with st.expander("ℹ️ ¿Cómo tomarme la presión correctamente?"):
                st.markdown("""
                <div style="font-size:13px;color:#94a3b8;line-height:1.8;">
                <strong style="color:#e8eef7;">Antes de medirte:</strong><br>
                • Descansá 5 minutos sentado antes de la medición<br>
                • No tomes café, alcohol ni hagas ejercicio 30 minutos antes<br>
                • Vaciá la vejiga antes de medirte<br><br>
                <strong style="color:#e8eef7;">Durante la medición:</strong><br>
                • Sentate con la espalda apoyada y los pies en el suelo<br>
                • Apoyá el brazo a la altura del corazón<br>
                • No hables ni te muevas durante la medición<br>
                • Esperá 1-2 minutos entre la primera y la segunda toma
                </div>
                """, unsafe_allow_html=True)

            st.markdown("---")

            # RESULTADO FINAL o CARGA DE MEDICIÓN
            if total >= 28:
                resultado, mensaje, tipo, promedios = calcular_resultado(mediciones)
                st.markdown("### 🎯 Resultado de tu semana")
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.markdown(f'<div class="art-metric"><div class="art-metric-num">{promedios[0]}</div><div class="art-metric-label">Sistólica promedio</div></div>', unsafe_allow_html=True)
                with c2:
                    st.markdown(f'<div class="art-metric"><div class="art-metric-num">{promedios[1]}</div><div class="art-metric-label">Diastólica promedio</div></div>', unsafe_allow_html=True)
                with c3:
                    st.markdown(f'<div class="art-metric"><div class="art-metric-num" style="font-size:18px;">{promedios[0]}/{promedios[1]}</div><div class="art-metric-label">mmHg general</div></div>', unsafe_allow_html=True)
                grafico_evolucion(mediciones)
                if tipo == "success":
                    st.success(f"**{resultado}** — {mensaje}")
                elif tipo == "warning":
                    st.warning(f"**{resultado}** — {mensaje}")
                else:
                    st.error(f"**{resultado}** — {mensaje}")

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
                    st.info("⏱ Esperá 1-2 minutos desde la toma anterior antes de registrar este valor.")
                with st.form("form_medicion"):
                    col_f1, col_f2 = st.columns(2)
                    with col_f1:
                        sis = st.number_input("Sistólica (número mayor)", min_value=60, max_value=250, value=120, step=1)
                    with col_f2:
                        dia = st.number_input("Diastólica (número menor)", min_value=40, max_value=150, value=80, step=1)
                    if st.form_submit_button("Guardar medición →", use_container_width=True):
                        guardar_medicion(codigo, sis, dia, proxima)
                        st.success("✅ Medición guardada.")
                        st.rerun()
                if total >= 2:
                    with st.expander("📈 Ver evolución hasta ahora"):
                        grafico_evolucion(mediciones)

    footer()
