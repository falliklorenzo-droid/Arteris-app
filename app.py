import streamlit as st
from supabase import create_client
from datetime import datetime

# ── Configuración de la página ───────────────────────────────────────────────
st.set_page_config(
    page_title="Monitor de Presión Arterial",
    page_icon="🩺",
    layout="centered"
)

# ── Conexión a Supabase ──────────────────────────────────────────────────────
@st.cache_resource
def conectar_supabase():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

supabase = conectar_supabase()

# ── Funciones de base de datos ───────────────────────────────────────────────
def buscar_paciente(codigo):
    resultado = supabase.table("pacientes")\
        .select("*")\
        .eq("codigo", codigo)\
        .execute()
    if resultado.data:
        return resultado.data[0]
    return None

def registrar_paciente(codigo, nombre, apellido, edad, sexo):
    supabase.table("pacientes").insert({
        "codigo": codigo,
        "nombre": nombre,
        "apellido": apellido,
        "edad": edad,
        "sexo": sexo,
        "consentimiento_aceptado": True,
        "fecha_registro": datetime.now().isoformat()
    }).execute()

def guardar_medicion(codigo, sistolica, diastolica):
    supabase.table("mediciones").insert({
        "codigo_paciente": codigo,
        "sistolica": sistolica,
        "diastolica": diastolica,
        "fecha": datetime.now().isoformat()
    }).execute()

def obtener_mediciones(codigo):
    resultado = supabase.table("mediciones")\
        .select("*")\
        .eq("codigo_paciente", codigo)\
        .order("fecha")\
        .execute()
    return resultado.data

def calcular_resultado(prom_sis, prom_dia):
    if prom_sis < 120 and prom_dia < 80:
        return "✅ Normal", "Tu presión está dentro del rango normal. Seguí con tus controles habituales.", "success"
    elif prom_sis < 130 and prom_dia < 80:
        return "⚠️ Elevada", "Tu presión está levemente elevada. Te recomendamos consultar con tu médico pronto.", "warning"
    elif prom_sis < 140 or prom_dia < 90:
        return "🟠 Hipertensión grado 1", "Tenés hipertensión de grado 1. Consultá con tu médico a la brevedad.", "warning"
    else:
        return "🔴 Hipertensión grado 2", "Tenés hipertensión de grado 2. Debés consultar con tu médico urgentemente.", "error"

# ── Interfaz principal ───────────────────────────────────────────────────────
st.title("🩺 Monitor de Presión Arterial")
st.markdown("---")

# Leer código desde la URL
params = st.query_params
codigo_url = params.get("codigo", "")

if "codigo_paciente" not in st.session_state:
    st.session_state.codigo_paciente = codigo_url
if "consentimiento_dado" not in st.session_state:
    st.session_state.consentimiento_dado = False

# ── Pantalla 1: Ingresar código ──────────────────────────────────────────────
if not st.session_state.codigo_paciente:
    st.subheader("Ingresá tu código de acceso")
    codigo_input = st.text_input("Código proporcionado por tu médico:")
    if st.button("Ingresar"):
        if codigo_input:
            paciente = buscar_paciente(codigo_input.strip())
            if paciente is None:
                st.error("❌ Código inválido. Verificá el código que te dio tu médico.")
            else:
                st.session_state.codigo_paciente = codigo_input.strip()
                st.rerun()
        else:
            st.error("Por favor ingresá un código.")

# ── Pantallas siguientes ─────────────────────────────────────────────────────
else:
    codigo = st.session_state.codigo_paciente
    paciente = buscar_paciente(codigo)

    if paciente is None:
        st.error("❌ Código inválido. Volvé al inicio.")
        if st.button("Volver al inicio"):
            st.session_state.codigo_paciente = ""
            st.rerun()

    # Sub-pantalla A: Consentimiento informado
    elif not paciente.get("consentimiento_aceptado", False) and not st.session_state.consentimiento_dado:
        st.subheader("📄 Consentimiento informado")
        st.info("""
**Antes de continuar, leé atentamente:**

Esta plataforma recopila y almacena los siguientes datos personales:
- Nombre, apellido, edad y sexo biológico
- Valores de presión arterial durante 7 días

**¿Para qué se usan tus datos?**
Únicamente para calcular el promedio de tu presión arterial y mostrarte un resultado orientativo. 
Tus datos son accesibles solo por vos y tu médico tratante.

**Tus derechos (Ley 25.326):**
Tenés derecho a acceder, rectificar y suprimir tus datos personales en cualquier momento, 
comunicándote con tu médico tratante.

⚠️ *Esta plataforma no reemplaza la consulta médica profesional.*
        """)
        aceptar = st.checkbox("Leí y acepto el uso de mis datos personales según lo descrito arriba")
        if st.button("Continuar", disabled=not aceptar):
            st.session_state.consentimiento_dado = True
            st.rerun()

    # Sub-pantalla B: Registro de datos personales
    elif paciente.get("nombre", "") == "":
        st.subheader("📋 Registro de datos personales")
        st.info("Es tu primera vez. Por favor completá tus datos.")
        with st.form("form_registro"):
            nombre   = st.text_input("Nombre")
            apellido = st.text_input("Apellido")
            edad     = st.number_input("Edad", min_value=1, max_value=120, step=1)
            sexo     = st.selectbox("Sexo biológico", ["Femenino", "Masculino", "Otro"])
            enviado  = st.form_submit_button("Registrarme")
        if enviado:
            if nombre and apellido:
                registrar_paciente(codigo, nombre, apellido, int(edad), sexo)
                st.success("¡Registro exitoso!")
                st.rerun()
            else:
                st.error("Por favor completá nombre y apellido.")

    # Sub-pantalla C: Carga de mediciones
    else:
        nombre_paciente = paciente.get("nombre", "Paciente")
        st.subheader(f"Hola, {nombre_paciente} 👋")
        mediciones = obtener_mediciones(codigo)
        dias_cargados = len(mediciones)
        st.markdown(f"**Días registrados:** {dias_cargados} / 7")
        st.progress(dias_cargados / 7)

        if dias_cargados < 7:
            st.markdown("### Cargar medición de hoy")
            with st.form("form_medicion"):
                st.caption("Ingresá los valores tal como aparecen en tu tensiómetro")
                sistolica  = st.number_input("Presión sistólica (número mayor)",
                                              min_value=60, max_value=250, step=1, value=120)
                diastolica = st.number_input("Presión diastólica (número menor)",
                                              min_value=40, max_value=150, step=1, value=80)
                enviado = st.form_submit_button("Guardar medición")
            if enviado:
                guardar_medicion(codigo, sistolica, diastolica)
                st.success("✅ Medición guardada correctamente.")
                st.rerun()
        else:
            st.markdown("### 🎯 Resultado de tus 7 días")
            prom_sis = sum(m["sistolica"]  for m in mediciones) / 7
            prom_dia = sum(m["diastolica"] for m in mediciones) / 7
            titulo, mensaje, tipo = calcular_resultado(prom_sis, prom_dia)

            col1, col2 = st.columns(2)
            with col1:
                st.metric("Promedio sistólica",  f"{prom_sis:.0f} mmHg")
            with col2:
                st.metric("Promedio diastólica", f"{prom_dia:.0f} mmHg")

            if tipo == "success":
                st.success(f"**{titulo}** — {mensaje}")
            elif tipo == "warning":
                st.warning(f"**{titulo}** — {mensaje}")
            else:
                st.error(f"**{titulo}** — {mensaje}")

            st.markdown("---")
            st.markdown("#### Historial de mediciones")
            for m in mediciones:
                st.write(f"📅 {m['fecha'][:10]} — Sistólica: {m['sistolica']} / Diastólica: {m['diastolica']}")

        st.markdown("---")
        st.caption("⚠️ Esta plataforma es orientativa y no reemplaza la consulta médica profesional.")
