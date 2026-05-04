import streamlit as st
from supabase import create_client, Client
from datetime import datetime, date
import resend
import uuid
import pandas as pd
import altair as alt

st.set_page_config(
    page_title="Arteris - Monitor de Presión Arterial",
    page_icon="🩺",
    layout="centered"
)

# ── Conexión Supabase ─────────────────────────────────────────────────────────
def get_supabase() -> Client:
    return create_client(
        st.secrets["supabase"]["url"],
        st.secrets["supabase"]["key"]
    )

# ── Funciones de base de datos ────────────────────────────────────────────────
def buscar_paciente(codigo):
    try:
        sb = get_supabase()
        r = sb.table("pacientes").select("*").eq("codigo", codigo).execute()
        return r.data[0] if r.data else None
    except:
        return None

def actualizar_paciente(codigo, datos):
    sb = get_supabase()
    sb.table("pacientes").update(datos).eq("codigo", codigo).execute()

def crear_paciente(nombre, apellido, email):
    sb = get_supabase()
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
    sb = get_supabase()
    sb.table("mediciones").insert({
        "codigo_paciente": codigo,
        "sistolica": sistolica,
        "diastolica": diastolica,
        "momento": momento,
        "fecha": datetime.now().isoformat()
    }).execute()

def obtener_mediciones(codigo):
    sb = get_supabase()
    r = sb.table("mediciones").select("*")\
        .eq("codigo_paciente", codigo)\
        .order("fecha").execute()
    return r.data

def obtener_todos_pacientes():
    sb = get_supabase()
    r = sb.table("pacientes").select("*").order("fecha_registro", desc=True).execute()
    return r.data

# ── Email ─────────────────────────────────────────────────────────────────────
def enviar_email_bienvenida(nombre, email, codigo):
    try:
        resend.api_key = st.secrets["resend"]["api_key"]
        url_acceso = f"https://arteris-app.streamlit.app/?codigo={codigo}"
        resend.Emails.send({
            "from": "Arteris <onboarding@resend.dev>",
            "to": email,
            "subject": "Tu acceso al Monitor de Presión Arterial",
            "html": f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #0066CC;">🩺 Monitor de Presión Arterial</h2>
                <p>Hola <strong>{nombre}</strong>,</p>
                <p>Tu médico te ha dado acceso a la plataforma de monitoreo de presión arterial.</p>
                <p>Durante los próximos 7 días, vas a registrar tu presión arterial 2 veces por la mañana y 2 veces por la tarde.</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{url_acceso}"
                       style="background-color: #0066CC; color: white; padding: 15px 30px;
                              text-decoration: none; border-radius: 8px; font-size: 16px;">
                        Acceder a la plataforma
                    </a>
                </div>
                <p style="color: #666;">O copiá este enlace en tu navegador:<br>
                <small>{url_acceso}</small></p>
                <hr>
                <p style="color: #999; font-size: 12px;">
                Esta plataforma es orientativa y no reemplaza la consulta médica profesional.
                </p>
            </div>
            """
        })
        return True
    except Exception as e:
        st.error(f"Error enviando email: {e}")
        return False

# ── Lógica de resultados ──────────────────────────────────────────────────────
def calcular_resultado(mediciones):
    if len(mediciones) < 2:
        return None, None, None, None, None

    df = pd.DataFrame(mediciones)
    df["fecha_dia"] = pd.to_datetime(df["fecha"]).dt.date

    dias_unicos = sorted(df["fecha_dia"].unique())
    if len(dias_unicos) >= 7:
        dias_a_usar = dias_unicos[1:7]
        df = df[df["fecha_dia"].isin(dias_a_usar)]

    prom_sis = df["sistolica"].mean()
    prom_dia = df["diastolica"].mean()
    prom_sis_man = df[df["momento"].str.contains("mañana", na=False)]["sistolica"].mean()
    prom_dia_man = df[df["momento"].str.contains("mañana", na=False)]["diastolica"].mean()
    prom_sis_tar = df[df["momento"].str.contains("tarde", na=False)]["sistolica"].mean()
    prom_dia_tar = df[df["momento"].str.contains("tarde", na=False)]["diastolica"].mean()

    if prom_sis <= 135 and prom_dia <= 85:
        resultado = "✅ Presión controlada"
        mensaje = "Tu presión arterial está controlada. Realizá tu próximo control en 3 meses."
        tipo = "success"
    elif prom_sis >= 180 or prom_dia >= 110:
        resultado = "🔴 Urgencia hipertensiva"
        mensaje = "Tus valores son muy elevados. Consultá una guardia médica de inmediato."
        tipo = "error"
    else:
        resultado = "⚠️ Presión no controlada"
        mensaje = "Tu presión no está controlada. Consultá con tu médico a la brevedad."
        tipo = "warning"

    return resultado, mensaje, tipo, \
           {"sis": round(prom_sis, 1), "dia": round(prom_dia, 1),
            "sis_man": round(prom_sis_man, 1) if not pd.isna(prom_sis_man) else "-",
            "dia_man": round(prom_dia_man, 1) if not pd.isna(prom_dia_man) else "-",
            "sis_tar": round(prom_sis_tar, 1) if not pd.isna(prom_sis_tar) else "-",
            "dia_tar": round(prom_dia_tar, 1) if not pd.isna(prom_dia_tar) else "-"}, df

# ── Gráfico ───────────────────────────────────────────────────────────────────
def mostrar_grafico(mediciones):
    df = pd.DataFrame(mediciones)
    df["fecha"] = pd.to_datetime(df["fecha"])
    df["dia"] = df["fecha"].dt.strftime("%d/%m %H:%M")

    base = alt.Chart(df).encode(
        x=alt.X("dia:N", title="Fecha y hora", sort=None)
    )
    line_sis = base.mark_line(color="#E74C3C", point=True).encode(
        y=alt.Y("sistolica:Q", title="mmHg"),
        tooltip=["dia", "sistolica", "diastolica", "momento"]
    )
    line_dia = base.mark_line(color="#3498DB", point=True).encode(
        y=alt.Y("diastolica:Q"),
        tooltip=["dia", "sistolica", "diastolica", "momento"]
    )
    chart = (line_sis + line_dia).properties(
        title="Evolución de tu presión arterial",
        width="container", height=300
    )
    st.altair_chart(chart, use_container_width=True)
    st.caption("🔴 Sistólica  🔵 Diastólica")

# ══════════════════════════════════════════════════════════════════════════════
# INTERFAZ
# ══════════════════════════════════════════════════════════════════════════════

params = st.query_params
codigo_url = params.get("codigo", "")

if "seccion" not in st.session_state:
    st.session_state.seccion = "medico" if not codigo_url else "paciente"
if "codigo_paciente" not in st.session_state:
    st.session_state.codigo_paciente = codigo_url
if "consentimiento_dado" not in st.session_state:
    st.session_state.consentimiento_dado = False

# ── Selector de sección ───────────────────────────────────────────────────────
if not codigo_url:
    col1, col2 = st.columns(2)
    with col1:
        if st.button("👨‍⚕️ Soy médico", use_container_width=True):
            st.session_state.seccion = "medico"
    with col2:
        if st.button("🙋 Soy paciente", use_container_width=True):
            st.session_state.seccion = "paciente"

# ══════════════════════════════════════════════════════════════════════════════
# PANEL DEL MÉDICO
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.seccion == "medico":
    st.title("👨‍⚕️ Panel del Médico")
    st.markdown("---")

    password = st.text_input("Contraseña de acceso:", type="password")
    if password != st.secrets.get("medico", {}).get("password", "medico123"):
        st.warning("Ingresá la contraseña para acceder al panel.")
        st.stop()

    tab1, tab2 = st.tabs(["➕ Nuevo paciente", "📋 Ver pacientes"])

    with tab1:
        st.subheader("Crear nuevo paciente")
        with st.form("form_nuevo_paciente"):
            nombre   = st.text_input("Nombre del paciente")
            apellido = st.text_input("Apellido del paciente")
            email    = st.text_input("Email del paciente")
            enviar   = st.form_submit_button("Crear paciente y enviar acceso")

        if enviar:
            if nombre and apellido and email:
                with st.spinner("Creando paciente y enviando email..."):
                    codigo = crear_paciente(nombre, apellido, email)
                    enviado = enviar_email_bienvenida(nombre, email, codigo)
                if enviado:
                    st.success(f"✅ Paciente creado. Email enviado a {email}")
                    url = f"https://arteris-app.streamlit.app/?codigo={codigo}"
                    st.info(f"Enlace de acceso: {url}")
                else:
                    st.warning(f"Paciente creado pero hubo un problema con el email. Código: **{codigo}**")
            else:
                st.error("Completá todos los campos.")

    with tab2:
        st.subheader("Pacientes registrados")
        pacientes = obtener_todos_pacientes()
        if not pacientes:
            st.info("No hay pacientes registrados aún.")
        else:
            for p in pacientes:
                with st.expander(f"{p.get('nombre','?')} {p.get('apellido','?')} — {p.get('email','?')}"):
                    mediciones = obtener_mediciones(p["codigo"])
                    st.write(f"**Código:** {p['codigo']}")
                    st.write(f"**Mediciones cargadas:** {len(mediciones)} / 28")
                    if len(mediciones) >= 4:
                        resultado, mensaje, tipo, promedios, _ = calcular_resultado(mediciones)
                        if resultado:
                            st.write(f"**Resultado:** {resultado}")
                            st.write(f"**Promedio general:** {promedios['sis']}/{promedios['dia']} mmHg")

# ══════════════════════════════════════════════════════════════════════════════
# PANEL DEL PACIENTE
# ══════════════════════════════════════════════════════════════════════════════
else:
    st.title("🩺 Monitor de Presión Arterial")
    st.markdown("---")

    # Ingresar código manualmente
    if not st.session_state.codigo_paciente:
        st.subheader("Ingresá tu código de acceso")
        codigo_input = st.text_input("Código proporcionado por tu médico:")
        if st.button("Ingresar"):
            if codigo_input:
                paciente = buscar_paciente(codigo_input.strip())
                if paciente is None:
                    st.error("❌ Código inválido.")
                else:
                    st.session_state.codigo_paciente = codigo_input.strip()
                    st.rerun()
            else:
                st.error("Por favor ingresá un código.")

    else:
        codigo = st.session_state.codigo_paciente
        paciente = buscar_paciente(codigo)

        if paciente is None:
            st.error("❌ Código inválido.")
            if st.button("Volver"):
                st.session_state.codigo_paciente = ""
                st.rerun()

        # ── Consentimiento ────────────────────────────────────────────────────
        elif not paciente.get("consentimiento_aceptado") and not st.session_state.consentimiento_dado:
            st.subheader("📄 Consentimiento informado")
            st.info("""
**Antes de continuar, leé atentamente:**

Esta plataforma recopila y almacena los siguientes datos personales:
- Nombre, apellido, edad, sexo biológico y medicación
- Valores de presión arterial durante 7 días

**¿Para qué se usan tus datos?**
Únicamente para calcular el promedio de tu presión arterial y mostrarte un resultado orientativo.
Tus datos son accesibles solo por vos y tu médico tratante.

**Tus derechos (Ley 25.326):**
Tenés derecho a acceder, rectificar y suprimir tus datos en cualquier momento
comunicándote con tu médico tratante.

⚠️ *Esta plataforma no reemplaza la consulta médica profesional.*
            """)
            aceptar = st.checkbox("Leí y acepto el uso de mis datos personales")
            if st.button("Continuar", disabled=not aceptar):
                st.session_state.consentimiento_dado = True
                st.rerun()

        # ── Registro ──────────────────────────────────────────────────────────
        elif not paciente.get("edad"):
            st.subheader("📋 Completá tus datos")
            with st.form("form_registro"):
                edad = st.number_input("Edad", min_value=1, max_value=120, step=1)
                sexo = st.selectbox("Sexo biológico", ["Femenino", "Masculino", "Otro"])
                toma_medicacion = st.radio("¿Tomás medicación para la presión?", ["No", "Sí"])
                medicacion = ""
                dosis = ""
                if toma_medicacion == "Sí":
                    medicacion = st.text_input("¿Qué medicación tomás?")
                    dosis = st.text_input("¿Cuál es la dosis?")
                enviado = st.form_submit_button("Guardar y continuar")
            if enviado:
                if edad:
                    actualizar_paciente(codigo, {
                        "edad": int(edad),
                        "sexo": sexo,
                        "toma_medicacion": toma_medicacion == "Sí",
                        "medicacion": medicacion,
                        "dosis": dosis,
                        "consentimiento_aceptado": True
                    })
                    st.success("✅ Datos guardados.")
                    st.rerun()

        # ── Homepage + mediciones ─────────────────────────────────────────────
        else:
            nombre_paciente = paciente.get("nombre", "Paciente")
            mediciones = obtener_mediciones(codigo)
            total = len(mediciones)

            st.subheader(f"Hola, {nombre_paciente} 👋")
            st.progress(min(total / 28, 1.0))
            st.caption(f"Mediciones registradas: {total} / 28")

            # Instructivo
            with st.expander("ℹ️ ¿Cómo tomarme la presión correctamente?"):
                st.markdown("""
**Antes de medirte:**
- Descansá 5 minutos sentado antes de tomar la medición
- No tomes café, alcohol ni hagas ejercicio 30 minutos antes
- Vacía la vejiga antes de medirte
- Sentate con la espalda apoyada y los pies en el suelo

**Durante la medición:**
- Apoyá el brazo a la altura del corazón
- No hables ni te muevas durante la medición
- Tomá 2 mediciones con 1-2 minutos de diferencia

**Anotá ambos valores** tal como aparecen en el aparato (ej: 120/80)
                """)

            st.markdown("---")

            # Determinar qué toma corresponde
            hoy = date.today()
            mediciones_hoy = [m for m in mediciones
                               if pd.to_datetime(m["fecha"]).date() == hoy]
            momentos_hoy = [m["momento"] for m in mediciones_hoy]

            tomas_orden = ["mañana-1", "mañana-2", "tarde-1", "tarde-2"]
            proxima_toma = None
            for t in tomas_orden:
                if t not in momentos_hoy:
                    proxima_toma = t
                    break

            if total >= 28:
                # Mostrar resultado final
                st.markdown("### 🎯 Resultado de tu semana")
                resultado, mensaje, tipo, promedios, df_calc = calcular_resultado(mediciones)

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Promedio general", f"{promedios['sis']}/{promedios['dia']}")
                with col2:
                    st.metric("Promedio mañana", f"{promedios['sis_man']}/{promedios['dia_man']}")
                with col3:
                    st.metric("Promedio tarde", f"{promedios['sis_tar']}/{promedios['dia_tar']}")

                mostrar_grafico(mediciones)

                if tipo == "success":
                    st.success(f"**{resultado}**\n\n{mensaje}")
                elif tipo == "warning":
                    st.warning(f"**{resultado}**\n\n{mensaje}")
                else:
                    st.error(f"**{resultado}**\n\n{mensaje}")

            elif proxima_toma is None:
                st.success("✅ Ya completaste todas las mediciones de hoy. Volvé mañana.")
                mostrar_grafico(mediciones)

            else:
                momento_label = proxima_toma.replace("-", " toma ").replace("mañana", "🌅 Mañana").replace("tarde", "🌇 Tarde")
                st.markdown(f"### Cargar medición: {momento_label}")

                if proxima_toma in ["mañana-2", "tarde-2"]:
                    st.info("⏱ Esperá 1-2 minutos desde la toma anterior antes de cargar este valor.")

                with st.form("form_medicion"):
                    st.caption("Ingresá los valores tal como aparecen en tu tensiómetro")
                    sistolica  = st.number_input("Presión sistólica (número mayor)",
                                                  min_value=60, max_value=250, step=1, value=120)
                    diastolica = st.number_input("Presión diastólica (número menor)",
                                                  min_value=40, max_value=150, step=1, value=80)
                    enviado = st.form_submit_button("Guardar medición")

                if enviado:
                    guardar_medicion(codigo, sistolica, diastolica, proxima_toma)
                    st.success("✅ Medición guardada.")
                    st.rerun()

                if total > 0:
                    with st.expander("📈 Ver mi progreso"):
                        mostrar_grafico(mediciones)

            st.markdown("---")
            st.caption("⚠️ Esta plataforma es orientativa y no reemplaza la consulta médica profesional.")
