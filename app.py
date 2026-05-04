import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import uuid
from datetime import datetime

# ── Configuración de la página ──────────────────────────────────────────────
st.set_page_config(
    page_title="Monitor de Presión Arterial",
    page_icon="🩺",
    layout="centered"
)

# ── Conexión a Google Sheets ─────────────────────────────────────────────────
@st.cache_resource
def conectar_sheets():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scopes
    )
    client = gspread.authorize(creds)
    return client

# ── Funciones principales ────────────────────────────────────────────────────
def obtener_hoja(nombre):
    client = conectar_sheets()
    spreadsheet = client.open(st.secrets["sheets"]["nombre_planilla"])
    try:
        return spreadsheet.worksheet(nombre)
    except:
        return spreadsheet.add_worksheet(title=nombre, rows=1000, cols=20)

def buscar_paciente_por_codigo(codigo):
    hoja = obtener_hoja("pacientes")
    registros = hoja.get_all_records()
    for r in registros:
        if str(r.get("codigo", "")).strip() == str(codigo).strip():
            return r
    return None

def registrar_paciente(codigo, nombre, apellido, edad, sexo):
    hoja = obtener_hoja("pacientes")
    registros = hoja.get_all_records()
    if not registros:
        hoja.append_row(["codigo", "nombre", "apellido", "edad", "sexo", "registrado"])
    hoja.append_row([codigo, nombre, apellido, edad, sexo,
                     datetime.now().strftime("%Y-%m-%d %H:%M")])

def guardar_medicion(codigo, sistolica, diastolica):
    hoja = obtener_hoja("mediciones")
    registros = hoja.get_all_records()
    if not registros:
        hoja.append_row(["codigo", "sistolica", "diastolica", "fecha"])
    hoja.append_row([codigo, sistolica, diastolica,
                     datetime.now().strftime("%Y-%m-%d %H:%M")])

def obtener_mediciones(codigo):
    hoja = obtener_hoja("mediciones")
    registros = hoja.get_all_records()
    return [r for r in registros if str(r.get("codigo", "")) == str(codigo)]

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

# Leer código desde la URL o input manual
params = st.query_params
codigo_url = params.get("codigo", "")

if "codigo_paciente" not in st.session_state:
    st.session_state.codigo_paciente = codigo_url
if "paciente" not in st.session_state:
    st.session_state.paciente = None

# ── Pantalla 1: Ingresar código ──────────────────────────────────────────────
if not st.session_state.codigo_paciente:
    st.subheader("Ingresá tu código de acceso")
    codigo_input = st.text_input("Código proporcionado por tu médico:")
    if st.button("Ingresar"):
        if codigo_input:
            st.session_state.codigo_paciente = codigo_input.strip()
            st.rerun()
        else:
            st.error("Por favor ingresá un código.")

# ── Pantalla 2: Registro o medición ─────────────────────────────────────────
else:
    codigo = st.session_state.codigo_paciente
    paciente = buscar_paciente_por_codigo(codigo)

    # Sub-pantalla A: Registro de datos personales
    if paciente is None:
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
                registrar_paciente(codigo, nombre, apellido, edad, sexo)
                st.success("¡Registro exitoso! Podés empezar a cargar tus mediciones.")
                st.rerun()
            else:
                st.error("Por favor completá nombre y apellido.")

    # Sub-pantalla B: Carga de mediciones
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
                                              min_value=60, max_value=250, step=1)
                diastolica = st.number_input("Presión diastólica (número menor)", 
                                              min_value=40, max_value=150, step=1)
                enviado = st.form_submit_button("Guardar medición")
            if enviado:
                guardar_medicion(codigo, sistolica, diastolica)
                st.success("✅ Medición guardada correctamente.")
                st.rerun()
        else:
            # Mostrar resultado final
            st.markdown("### 🎯 Resultado de tus 7 días")
            prom_sis = sum(int(m["sistolica"])  for m in mediciones) / 7
            prom_dia = sum(int(m["diastolica"]) for m in mediciones) / 7
            titulo, mensaje, tipo = calcular_resultado(prom_sis, prom_dia)
            st.metric("Promedio sistólica",  f"{prom_sis:.0f} mmHg")
            st.metric("Promedio diastólica", f"{prom_dia:.0f} mmHg")
            if tipo == "success":
                st.success(f"**{titulo}** — {mensaje}")
            elif tipo == "warning":
                st.warning(f"**{titulo}** — {mensaje}")
            else:
                st.error(f"**{titulo}** — {mensaje}")

            st.markdown("---")
            st.markdown("#### Historial de mediciones")
            df = pd.DataFrame(mediciones)[["fecha","sistolica","diastolica"]]
            st.dataframe(df, use_container_width=True)
