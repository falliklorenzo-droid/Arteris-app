"""
Fuente única de verdad para evaluar el estado de un monitoreo HBPM.

La usan los DOS caminos que deciden si un monitoreo concluyó:
  - app.py                  (tiempo real: cuando el paciente carga tomas / abre la app)
  - enviar_recordatorios.py (job de expiración a los 7 días, GitHub Actions)

Tener una sola función evita el bug de los DOS mails contradictorios:
antes, el camino en tiempo real evaluaba la finalización con una lógica
(ventana de 6 días, descarte del día 1, mínimo 12 tomas) y el job la
evaluaba con otra (len() crudo y "pasaron 7 días"), por lo que un mismo
paciente recibía a la vez el PDF de "concluido" y el mail de "insuficiente".

Reglas clínicas (ART-aware):
  - La fecha de cada toma se guarda en UTC. Se convierte SIEMPRE a hora de
    Argentina (America/Argentina/Buenos_Aires) ANTES de agrupar por día.
    Nunca usar ::date sobre el timestamp UTC: parte mal los días de las
    tomas de la tarde/noche.
  - El inicio del protocolo se ancla a la PRIMERA toma real del paciente.
  - El día 1 del protocolo se DESCARTA (se evalúan los días 2 a 7).
  - Mínimo 12 tomas válidas (en la ventana, sin el día 1) para considerar
    el monitoreo CONCLUIDO con informe clínicamente útil.

Sin dependencias de pandas: solo stdlib, para poder usarse dentro del job
de GitHub Actions (que solo instala `supabase` y `resend`).
"""
from datetime import datetime, timezone, timedelta

try:
    from zoneinfo import ZoneInfo
    ARG_TZ = ZoneInfo("America/Argentina/Buenos_Aires")
except Exception:  # pragma: no cover - fallback si no hay tzdata en el runner
    ARG_TZ = timezone(timedelta(hours=-3))

DURACION_PROTOCOLO_DIAS = 7
MIN_TOMAS_VALIDAS = 12


def fecha_local(val):
    """Convierte un timestamp ISO (cualquier tz; asume UTC si no trae) a la
    fecha calendario local de Argentina. Devuelve None si no parsea."""
    if not val:
        return None
    try:
        dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ARG_TZ).date()


def evaluar_hbpm(mediciones, hoy=None):
    """Evalúa el estado de un monitoreo HBPM a partir de la lista cruda de
    mediciones (cada una un dict con al menos la clave 'fecha').

    Devuelve un dict:
      tiene_tomas   bool  -- hay al menos una toma cargada
      inicio        date  -- fecha local del día 1 (primera toma) o None
      dia_actual    int   -- número de día del protocolo (1..7+); 0 si no arrancó
      expirado      bool  -- pasaron los 7 días del protocolo
      tomas_validas int   -- tomas en la ventana de evaluación (sin el día 1)
      concluido     bool  -- tomas_validas >= 12 (informe clínicamente útil)
      dias_validos  list  -- fechas locales usadas para la evaluación
    """
    if hoy is None:
        hoy = datetime.now(ARG_TZ).date()

    fechas = [fecha_local(m.get("fecha")) for m in (mediciones or [])]
    fechas = [f for f in fechas if f is not None]

    if not fechas:
        return {
            "tiene_tomas": False,
            "inicio": None,
            "dia_actual": 0,
            "expirado": False,
            "tomas_validas": 0,
            "concluido": False,
            "dias_validos": [],
        }

    inicio = min(fechas)                       # ancla: primera toma real
    dias_transcurridos = (hoy - inicio).days
    dia_actual = dias_transcurridos + 1
    expirado = dias_transcurridos >= DURACION_PROTOCOLO_DIAS

    dias_ordenados = sorted(set(fechas))
    # Ventana de evaluación: días 2..7 (descartamos el día 1).
    if len(dias_ordenados) >= DURACION_PROTOCOLO_DIAS:
        dias_validos = dias_ordenados[-(DURACION_PROTOCOLO_DIAS - 1):]  # últimos 6
    elif len(dias_ordenados) >= 2:
        dias_validos = dias_ordenados[1:]      # descartamos el día 1
    else:
        dias_validos = []                      # un solo día: el día 1 se descarta

    dias_validos_set = set(dias_validos)
    tomas_validas = sum(1 for f in fechas if f in dias_validos_set)
    concluido = tomas_validas >= MIN_TOMAS_VALIDAS

    return {
        "tiene_tomas": True,
        "inicio": inicio,
        "dia_actual": dia_actual,
        "expirado": expirado,
        "tomas_validas": tomas_validas,
        "concluido": concluido,
        "dias_validos": dias_validos,
    }
