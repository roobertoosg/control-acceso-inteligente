"""
Dashboard Analítico y de Monitoreo.

Esta es la interfaz visual del sistema construida con Streamlit. 
Se conecta directamente a la base de datos de solo lectura (vistas) para extraer
y procesar métricas en tiempo casi-real mediante DataFrames de Pandas.
Utiliza el decorador `@st.cache_data` intensivamente para optimizar rendimiento.
"""
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import psycopg2
import streamlit as st

from app.config import Config


st.set_page_config(
    page_title="Dashboard - Control de Acceso Inteligente",
    page_icon="🎫",
    layout="wide",
)


# ------------------------------------------------------
# Conexión
# ------------------------------------------------------
def get_connection():
    return psycopg2.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        dbname=Config.DB_NAME,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
    )


# ------------------------------------------------------
# Carga de datos
# ------------------------------------------------------
@st.cache_data(ttl=20)
def load_eventos() -> pd.DataFrame:
    """
    Carga y enriquece los eventos recientes. 
    Mantiene la info cacheada por 20 segundos para evitar saturar PostgreSQL.
    """
    sql = """
        SELECT *
        FROM acceso.vw_eventos_detalle
        ORDER BY fecha_hora DESC, id_evento DESC
    """
    with get_connection() as conn:
        df = pd.read_sql(sql, conn)

    if df.empty:
        return df

    df["fecha_hora"] = pd.to_datetime(df["fecha_hora"])
    df["fecha"] = df["fecha_hora"].dt.date
    df["hora"] = df["fecha_hora"].dt.hour

    df["usuario_nombre"] = (
        df[["nombre", "apellido_paterno", "apellido_materno"]]
        .fillna("")
        .agg(" ".join, axis=1)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )

    df["usuario_label"] = df.apply(
        lambda row: f"{row['usuario_nombre']} ({row['matricula']})"
        if pd.notna(row["matricula"]) and str(row["matricula"]).strip() != ""
        else row["usuario_nombre"],
        axis=1,
    )

    return df


@st.cache_data(ttl=20)
def load_usuarios() -> pd.DataFrame:
    sql = """
        SELECT
            id_usuario,
            nombre,
            apellido_paterno,
            apellido_materno,
            matricula,
            uid_rfid,
            estado_actual,
            activo
        FROM acceso.usuarios
        ORDER BY nombre, apellido_paterno, apellido_materno
    """
    with get_connection() as conn:
        df = pd.read_sql(sql, conn)

    if df.empty:
        return df

    df["usuario_nombre"] = (
        df[["nombre", "apellido_paterno", "apellido_materno"]]
        .fillna("")
        .agg(" ".join, axis=1)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )

    df["usuario_label"] = df.apply(
        lambda row: f"{row['usuario_nombre']} ({row['matricula']})"
        if pd.notna(row["matricula"]) and str(row["matricula"]).strip() != ""
        else row["usuario_nombre"],
        axis=1,
    )

    return df


@st.cache_data(ttl=20)
def load_inasistencias() -> pd.DataFrame:
    sql = """
        SELECT *
        FROM acceso.vw_inasistencias_detalle
        ORDER BY fecha DESC, hora_inicio ASC, id_inasistencia DESC
    """
    with get_connection() as conn:
        df = pd.read_sql(sql, conn)

    if df.empty:
        return df

    df["fecha"] = pd.to_datetime(df["fecha"]).dt.date
    df["hora_inicio"] = pd.to_datetime(df["hora_inicio"], format="%H:%M:%S", errors="coerce")
    df["hora_fin"] = pd.to_datetime(df["hora_fin"], format="%H:%M:%S", errors="coerce")

    df["usuario_nombre"] = (
        df[["nombre", "apellido_paterno", "apellido_materno"]]
        .fillna("")
        .agg(" ".join, axis=1)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )

    df["usuario_label"] = df.apply(
        lambda row: f"{row['usuario_nombre']} ({row['matricula']})"
        if pd.notna(row["matricula"]) and str(row["matricula"]).strip() != ""
        else row["usuario_nombre"],
        axis=1,
    )

    return df


# ------------------------------------------------------
# Helpers de filtrado
# ------------------------------------------------------
def filtrar_eventos(
    df: pd.DataFrame,
    fecha_inicio: date,
    fecha_fin: date,
    usuarios_seleccionados: list[str],
) -> pd.DataFrame:
    if df.empty:
        return df

    mask_fecha = (df["fecha"] >= fecha_inicio) & (df["fecha"] <= fecha_fin)
    filtrado = df.loc[mask_fecha].copy()

    if usuarios_seleccionados:
        filtrado = filtrado[filtrado["usuario_label"].isin(usuarios_seleccionados)].copy()

    return filtrado


def filtrar_inasistencias(
    df: pd.DataFrame,
    fecha_inicio: date,
    fecha_fin: date,
    usuarios_seleccionados: list[str],
) -> pd.DataFrame:
    if df.empty:
        return df

    mask_fecha = (df["fecha"] >= fecha_inicio) & (df["fecha"] <= fecha_fin)
    filtrado = df.loc[mask_fecha].copy()

    if usuarios_seleccionados:
        filtrado = filtrado[filtrado["usuario_label"].isin(usuarios_seleccionados)].copy()

    return filtrado


def filtrar_usuarios(
    df: pd.DataFrame,
    usuarios_seleccionados: list[str],
) -> pd.DataFrame:
    if df.empty:
        return df

    if usuarios_seleccionados:
        return df[df["usuario_label"].isin(usuarios_seleccionados)].copy()

    return df.copy()


# ------------------------------------------------------
# Helpers de métricas de acceso
# ------------------------------------------------------
def calcular_tiempo_promedio_estancia(df: pd.DataFrame) -> float | None:
    """
    Analítica: Empareja secuencialmente eventos ENTRADA -> SALIDA por usuario.
    Esto nos permite calcular el KPI de "Tiempo promedio que un estudiante/docente
    pasa dentro del campus por visita".
    Ignora eventos atípicos mayores a 24h.
    """
    if df.empty:
        return None

    base = df[
        df["id_usuario"].notna()
        & df["resultado"].isin(["PERMITIDO", "ANOMALIA"])
        & df["modo_evento"].isin(["ENTRADA", "SALIDA"])
        & (df["paso_detectado"] == True)
    ].copy()

    if base.empty:
        return None

    base = base.sort_values(["id_usuario", "fecha_hora", "id_evento"]).reset_index(drop=True)

    duraciones = []

    for _, grupo in base.groupby("id_usuario"):
        grupo = grupo.sort_values(["fecha_hora", "id_evento"]).reset_index(drop=True)
        entrada_abierta = None

        for _, evento in grupo.iterrows():
            if evento["modo_evento"] == "ENTRADA":
                entrada_abierta = evento["fecha_hora"]

            elif evento["modo_evento"] == "SALIDA" and entrada_abierta is not None:
                minutos = (evento["fecha_hora"] - entrada_abierta).total_seconds() / 60

                if 0 < minutos <= 24 * 60:
                    duraciones.append(minutos)

                entrada_abierta = None

    if not duraciones:
        return None

    return round(sum(duraciones) / len(duraciones), 2)


def minutos_a_hhmm(valor: float | None) -> str:
    if valor is None:
        return "N/D"

    horas = int(valor // 60)
    minutos = int(round(valor % 60))

    if minutos == 60:
        horas += 1
        minutos = 0

    return f"{horas:02d}:{minutos:02d}"


def contar_entradas_validas(df: pd.DataFrame) -> int:
    return int(
        len(
            df[
                (df["modo_evento"] == "ENTRADA")
                & (df["resultado"].isin(["PERMITIDO", "ANOMALIA"]))
                & (df["paso_detectado"] == True)
            ]
        )
    )


def contar_salidas_validas(df: pd.DataFrame) -> int:
    return int(
        len(
            df[
                (df["modo_evento"] == "SALIDA")
                & (df["resultado"].isin(["PERMITIDO", "ANOMALIA"]))
                & (df["paso_detectado"] == True)
            ]
        )
    )


# ------------------------------------------------------
# Helpers de bloques horarios
# ------------------------------------------------------
BLOQUES_ESCOLARES = [
    ("07:00", "09:00"),
    ("09:00", "11:00"),
    ("11:00", "13:00"),
    ("13:00", "15:00"),
    ("16:00", "18:00"),
    ("18:00", "20:00"),
    ("20:00", "22:00"),
]

TOLERANCIA_ANTICIPADA_MIN = 20


def _hhmm_a_minutos(valor: str) -> int:
    h, m = map(int, valor.split(":"))
    return h * 60 + m


def clasificar_bloque_entrada(ts) -> str:
    if pd.isna(ts):
        return "Fuera de bloque"

    minutos = ts.hour * 60 + ts.minute

    for inicio, fin in BLOQUES_ESCOLARES:
        inicio_min = _hhmm_a_minutos(inicio)
        fin_min = _hhmm_a_minutos(fin)

        if (inicio_min - TOLERANCIA_ANTICIPADA_MIN) <= minutos <= fin_min:
            return f"{inicio} - {fin}"

    return "Fuera de bloque"


def obtener_bloque_mas_frecuente(df: pd.DataFrame) -> str:
    if df.empty:
        return "N/D"

    entradas = df[
        (df["modo_evento"] == "ENTRADA")
        & (df["resultado"].isin(["PERMITIDO", "ANOMALIA"]))
        & (df["paso_detectado"] == True)
    ].copy()

    if entradas.empty:
        return "N/D"

    entradas["bloque_entrada"] = entradas["fecha_hora"].apply(clasificar_bloque_entrada)
    entradas_validas_bloque = entradas[entradas["bloque_entrada"] != "Fuera de bloque"].copy()

    if entradas_validas_bloque.empty:
        return "N/D"

    conteo = (
        entradas_validas_bloque.groupby("bloque_entrada", as_index=False)
        .size()
        .rename(columns={"size": "total"})
        .sort_values(["total", "bloque_entrada"], ascending=[False, True])
    )

    return str(conteo.iloc[0]["bloque_entrada"])


def calcular_fuera_de_horario(df: pd.DataFrame) -> tuple[int, float]:
    if df.empty:
        return 0, 0.0

    entradas = df[
        (df["modo_evento"] == "ENTRADA")
        & (df["resultado"].isin(["PERMITIDO", "ANOMALIA"]))
        & (df["paso_detectado"] == True)
    ].copy()

    if entradas.empty:
        return 0, 0.0

    codigos_fuera_horario = {
        "HORARIO_FUERA_DE_BLOQUE",
        "DIA_NO_HABITUAL",
        "ACCESO_EN_DOMINGO",
        "HORARIO_EXTREMO",
        "SIN_CLASE_PROGRAMADA",
    }

    fuera = int(entradas["motivo_codigo"].isin(codigos_fuera_horario).sum())
    porcentaje = round((fuera / len(entradas)) * 100, 2) if len(entradas) > 0 else 0.0

    return fuera, porcentaje


def contar_llegadas_tarde(df: pd.DataFrame) -> int:
    if df.empty:
        return 0

    return int(
        len(
            df[
                (df["modo_evento"] == "ENTRADA")
                & (df["resultado"] == "ANOMALIA")
                & (df["motivo_codigo"] == "LLEGADA_TARDE")
            ]
        )
    )


# ------------------------------------------------------
# Helpers de inasistencias
# ------------------------------------------------------
def total_inasistencias(df: pd.DataFrame) -> int:
    return int(len(df)) if not df.empty else 0


def contar_inasistencias_tipo(df: pd.DataFrame, tipo: str) -> int:
    if df.empty:
        return 0
    return int((df["tipo"] == tipo).sum())


# ------------------------------------------------------
# UI
# ------------------------------------------------------
st.title("🎫 Dashboard de Control de Acceso Inteligente")
st.caption("Lectura de métricas y eventos desde PostgreSQL")

if st.button("Actualizar datos"):
    st.cache_data.clear()
    st.rerun()

eventos_df = load_eventos()
usuarios_df = load_usuarios()
inasistencias_df = load_inasistencias()

if eventos_df.empty and inasistencias_df.empty:
    st.warning("No hay eventos ni inasistencias registradas todavía en la base de datos.")
    st.stop()

fechas_candidatas = []
if not eventos_df.empty:
    fechas_candidatas.extend([eventos_df["fecha"].min(), eventos_df["fecha"].max()])
if not inasistencias_df.empty:
    fechas_candidatas.extend([inasistencias_df["fecha"].min(), inasistencias_df["fecha"].max()])

fechas_candidatas = [f for f in fechas_candidatas if pd.notna(f)]

if not fechas_candidatas:
    st.warning("No se pudieron determinar las fechas de los datos.")
    st.stop()

min_fecha = min(fechas_candidatas)
max_fecha = max(fechas_candidatas)

fecha_default_inicio = max(min_fecha, max_fecha - timedelta(days=7))
fecha_default_fin = max_fecha

st.sidebar.header("Filtros")

rango = st.sidebar.date_input(
    "Rango de fechas",
    value=(fecha_default_inicio, fecha_default_fin),
    min_value=min_fecha,
    max_value=max_fecha,
)

if isinstance(rango, tuple) and len(rango) == 2:
    fecha_inicio, fecha_fin = rango
else:
    fecha_inicio = fecha_default_inicio
    fecha_fin = fecha_default_fin

usuarios_options = []
if not usuarios_df.empty:
    usuarios_options = usuarios_df["usuario_label"].dropna().unique().tolist()

usuarios_seleccionados = st.sidebar.multiselect(
    "Usuarios",
    options=usuarios_options,
    default=[],
)

df = filtrar_eventos(eventos_df, fecha_inicio, fecha_fin, usuarios_seleccionados)
inas_df = filtrar_inasistencias(inasistencias_df, fecha_inicio, fecha_fin, usuarios_seleccionados)
usuarios_filtrados_df = filtrar_usuarios(usuarios_df, usuarios_seleccionados)

if df.empty and inas_df.empty:
    st.warning("No hay datos para los filtros seleccionados.")
    st.stop()

# ------------------------------------------------------
# KPIs de acceso
# ------------------------------------------------------
st.subheader("Accesos")

total_eventos = len(df) if not df.empty else 0
entradas_validas = contar_entradas_validas(df) if not df.empty else 0
salidas_validas = contar_salidas_validas(df) if not df.empty else 0
denegados = int((df["resultado"] == "DENEGADO").sum()) if not df.empty else 0
incompletos = int((df["resultado"] == "INCOMPLETO").sum()) if not df.empty else 0
anomalias = int((df["resultado"] == "ANOMALIA").sum()) if not df.empty else 0

tiempo_promedio_estancia = calcular_tiempo_promedio_estancia(df) if not df.empty else None
bloque_mas_frecuente = obtener_bloque_mas_frecuente(df) if not df.empty else "N/D"
fuera_horario_total, fuera_horario_pct = calcular_fuera_de_horario(df) if not df.empty else (0, 0.0)
llegadas_tarde = contar_llegadas_tarde(df) if not df.empty else 0

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Total eventos", total_eventos)
c2.metric("Entradas válidas", entradas_validas)
c3.metric("Salidas válidas", salidas_validas)
c4.metric("Denegados", denegados)
c5.metric("Incompletos", incompletos)
c6.metric("Anomalías", anomalias)

c7, c8, c9, c10 = st.columns(4)
c7.metric("Tiempo promedio de estancia", minutos_a_hhmm(tiempo_promedio_estancia))
c8.metric("Bloque más frecuente", bloque_mas_frecuente)
c9.metric("Entradas fuera de horario", f"{fuera_horario_total} ({fuera_horario_pct}%)")
c10.metric("Llegadas tarde", llegadas_tarde)

st.divider()

# ------------------------------------------------------
# KPIs de inasistencias
# ------------------------------------------------------
st.subheader("Asistencia")

faltas_total = total_inasistencias(inas_df)
faltas_totales = contar_inasistencias_tipo(inas_df, "TOTAL")
faltas_parciales = contar_inasistencias_tipo(inas_df, "PARCIAL")
retardos_graves = contar_inasistencias_tipo(inas_df, "RETARDO_GRAVE")

f1, f2, f3, f4 = st.columns(4)
f1.metric("Total inasistencias", faltas_total)
f2.metric("Faltas totales", faltas_totales)
f3.metric("Faltas parciales", faltas_parciales)
f4.metric("Retardos graves", retardos_graves)

st.divider()

# ------------------------------------------------------
# Gráficas de acceso
# ------------------------------------------------------
g1, g2 = st.columns(2)

if not df.empty:
    eventos_por_dia = (
        df.groupby("fecha", as_index=False)
        .size()
        .rename(columns={"size": "total"})
        .sort_values("fecha")
    )

    fig_dia = px.bar(
        eventos_por_dia,
        x="fecha",
        y="total",
        title="Eventos por día",
        labels={"fecha": "Fecha", "total": "Eventos"},
    )
    g1.plotly_chart(fig_dia, use_container_width=True)

    resultados_df = (
        df.groupby("resultado", as_index=False)
        .size()
        .rename(columns={"size": "total"})
        .sort_values("total", ascending=False)
    )

    fig_resultado = px.pie(
        resultados_df,
        names="resultado",
        values="total",
        title="Distribución por resultado",
    )
    g2.plotly_chart(fig_resultado, use_container_width=True)
else:
    g1.info("No hay eventos de acceso para los filtros seleccionados.")
    g2.info("No hay distribución de resultados para mostrar.")

g3, g4 = st.columns(2)

if not df.empty:
    eventos_por_hora = (
        df.groupby("hora", as_index=False)
        .size()
        .rename(columns={"size": "total"})
        .sort_values("hora")
    )

    fig_hora = px.bar(
        eventos_por_hora,
        x="hora",
        y="total",
        title="Eventos por hora",
        labels={"hora": "Hora", "total": "Eventos"},
    )
    g3.plotly_chart(fig_hora, use_container_width=True)

    incidencias_df = df[
        df["resultado"].isin(["DENEGADO", "INCOMPLETO", "ANOMALIA"])
    ].copy()

    if not incidencias_df.empty:
        top_incidencias = (
            incidencias_df.groupby("usuario_label", as_index=False)
            .size()
            .rename(columns={"size": "total"})
            .sort_values("total", ascending=False)
            .head(10)
        )

        fig_incidencias = px.bar(
            top_incidencias,
            x="usuario_label",
            y="total",
            title="Top usuarios con incidencias",
            labels={"usuario_label": "Usuario", "total": "Incidencias"},
        )
        g4.plotly_chart(fig_incidencias, use_container_width=True)
    else:
        g4.info("No hay incidencias para los filtros seleccionados.")
else:
    g3.info("No hay eventos por hora para mostrar.")
    g4.info("No hay incidencias para mostrar.")

st.divider()

# ------------------------------------------------------
# Tabla de eventos recientes
# ------------------------------------------------------
st.subheader("Eventos recientes")

if not df.empty:
    tabla_eventos = df[
        [
            "fecha_hora",
            "usuario_label",
            "uid_rfid_leido",
            "modo_evento",
            "resultado",
            "motivo_codigo",
            "motivo_descripcion",
            "paso_detectado",
            "estado_anterior",
            "estado_nuevo",
            "anomalia_score",
            "detalle",
        ]
    ].copy()

    tabla_eventos = tabla_eventos.rename(
        columns={
            "fecha_hora": "Fecha y hora",
            "usuario_label": "Usuario",
            "uid_rfid_leido": "UID leído",
            "modo_evento": "Modo",
            "resultado": "Resultado",
            "motivo_codigo": "Código motivo",
            "motivo_descripcion": "Motivo",
            "paso_detectado": "Paso detectado",
            "estado_anterior": "Estado anterior",
            "estado_nuevo": "Estado nuevo",
            "anomalia_score": "Score anomalía",
            "detalle": "Detalle",
        }
    )

    st.dataframe(
        tabla_eventos.sort_values("Fecha y hora", ascending=False),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No hay eventos recientes para los filtros seleccionados.")

st.divider()

# ------------------------------------------------------
# Tabla de inasistencias recientes
# ------------------------------------------------------
st.subheader("Inasistencias recientes")

if not inas_df.empty:
    tabla_inas = inas_df[
        [
            "fecha",
            "usuario_label",
            "dia_semana",
            "hora_inicio",
            "hora_fin",
            "tipo",
            "justificacion",
            "detectada_automaticamente",
            "detalle",
        ]
    ].copy()

    tabla_inas["hora_inicio"] = tabla_inas["hora_inicio"].dt.strftime("%H:%M")
    tabla_inas["hora_fin"] = tabla_inas["hora_fin"].dt.strftime("%H:%M")

    tabla_inas = tabla_inas.rename(
        columns={
            "fecha": "Fecha",
            "usuario_label": "Usuario",
            "dia_semana": "Día semana",
            "hora_inicio": "Hora inicio",
            "hora_fin": "Hora fin",
            "tipo": "Tipo",
            "justificacion": "Justificación",
            "detectada_automaticamente": "Automática",
            "detalle": "Detalle",
        }
    )

    st.dataframe(
        tabla_inas.sort_values(["Fecha", "Hora inicio"], ascending=[False, True]),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No hay inasistencias recientes para los filtros seleccionados.")

st.divider()

# ------------------------------------------------------
# Estado actual de usuarios
# ------------------------------------------------------
st.subheader("Estado actual de usuarios")

if not usuarios_filtrados_df.empty:
    usuarios_tabla = usuarios_filtrados_df[
        ["usuario_label", "uid_rfid", "estado_actual", "activo"]
    ].rename(
        columns={
            "usuario_label": "Usuario",
            "uid_rfid": "UID RFID",
            "estado_actual": "Estado actual",
            "activo": "Activo",
        }
    )

    st.dataframe(usuarios_tabla, use_container_width=True, hide_index=True)
else:
    st.info("No hay usuarios para los filtros seleccionados.")