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
    df["hora_decimal"] = (
        df["fecha_hora"].dt.hour
        + df["fecha_hora"].dt.minute / 60
        + df["fecha_hora"].dt.second / 3600
    )

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


# ------------------------------------------------------
# Helpers
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


def calcular_tiempo_promedio_estancia(df: pd.DataFrame) -> float | None:
    """
    Empareja ENTRADA -> SALIDA por usuario.
    Devuelve promedio en minutos.
    """
    if df.empty:
        return None

    base = df[
        df["id_usuario"].notna()
        & df["resultado"].isin(["PERMITIDO", "ANOMALIA"])
        & df["modo_evento"].isin(["ENTRADA", "SALIDA"])
    ].copy()

    if base.empty:
        return None

    base = base.sort_values(["id_usuario", "fecha_hora"]).reset_index(drop=True)

    duraciones = []

    for _, grupo in base.groupby("id_usuario"):
        grupo = grupo.sort_values("fecha_hora").reset_index(drop=True)

        for i in range(len(grupo)):
            evento = grupo.iloc[i]

            if evento["modo_evento"] != "ENTRADA":
                continue

            posteriores = grupo.iloc[i + 1 :]
            salidas = posteriores[posteriores["modo_evento"] == "SALIDA"]

            if salidas.empty:
                continue

            salida = salidas.iloc[0]
            minutos = (salida["fecha_hora"] - evento["fecha_hora"]).total_seconds() / 60

            # filtro básico para evitar emparejamientos absurdos
            if 0 < minutos <= 24 * 60:
                duraciones.append(minutos)

    if not duraciones:
        return None

    return round(sum(duraciones) / len(duraciones), 2)


def horas_a_hhmm(valor: float | None) -> str:
    if valor is None:
        return "N/D"
    horas = int(valor)
    minutos = int(round((valor - horas) * 60))
    return f"{horas:02d}:{minutos:02d}"


def minutos_a_hhmm(valor: float | None) -> str:
    if valor is None:
        return "N/D"
    horas = int(valor // 60)
    minutos = int(round(valor % 60))
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
    """
    Asigna una entrada al bloque escolar más cercano válido.
    Acepta hasta 20 min antes del inicio del bloque.
    """
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

    conteo = (
        entradas.groupby("bloque_entrada", as_index=False)
        .size()
        .rename(columns={"size": "total"})
        .sort_values(["total", "bloque_entrada"], ascending=[False, True])
    )

    if conteo.empty:
        return "N/D"

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

    fuera = int((entradas["motivo_codigo"] == "HORARIO_FUERA_DE_BLOQUE").sum())
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
# UI
# ------------------------------------------------------
st.title("🎫 Dashboard de Control de Acceso Inteligente")
st.caption("Lectura de métricas y eventos desde PostgreSQL")

if st.button("Actualizar datos"):
    st.cache_data.clear()
    st.rerun()

eventos_df = load_eventos()
usuarios_df = load_usuarios()

if eventos_df.empty:
    st.warning("No hay eventos registrados todavía en la base de datos.")
    st.stop()

min_fecha = eventos_df["fecha"].min()
max_fecha = eventos_df["fecha"].max()

if pd.isna(min_fecha) or pd.isna(max_fecha):
    st.warning("No se pudieron determinar las fechas de los eventos.")
    st.stop()

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

if df.empty:
    st.warning("No hay eventos para los filtros seleccionados.")
    st.stop()

# ------------------------------------------------------
# KPIs
# ------------------------------------------------------
total_eventos = len(df)
entradas_validas = contar_entradas_validas(df)
salidas_validas = contar_salidas_validas(df)
denegados = int((df["resultado"] == "DENEGADO").sum())
incompletos = int((df["resultado"] == "INCOMPLETO").sum())
anomalias = int(((df["resultado"] == "ANOMALIA") | (df["anomalia_score"] > 0)).sum())

tiempo_promedio_estancia = calcular_tiempo_promedio_estancia(df)
bloque_mas_frecuente = obtener_bloque_mas_frecuente(df)
fuera_horario_total, fuera_horario_pct = calcular_fuera_de_horario(df)
llegadas_tarde = contar_llegadas_tarde(df)

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
# Gráficas
# ------------------------------------------------------
g1, g2 = st.columns(2)

# Eventos por día
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

# Resultados
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

g3, g4 = st.columns(2)

# Eventos por hora
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

# Top usuarios con incidencias
incidencias_df = df[
    (df["resultado"].isin(["DENEGADO", "INCOMPLETO", "ANOMALIA"]))
    | (df["anomalia_score"] > 0)
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

st.divider()

# ------------------------------------------------------
# Tabla de eventos recientes
# ------------------------------------------------------
st.subheader("Eventos recientes")

tabla = df[
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

tabla = tabla.rename(
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
    tabla.sort_values("Fecha y hora", ascending=False),
    use_container_width=True,
    hide_index=True,
)

st.divider()

# ------------------------------------------------------
# Estado actual de usuarios
# ------------------------------------------------------
st.subheader("Estado actual de usuarios")

usuarios_tabla = usuarios_df[
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