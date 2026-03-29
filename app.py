import streamlit as st
import pandas as pd
import io
import plotly.express as px
from itertools import cycle

# Configuración
st.set_page_config(page_title="Dashboard Ejecutivo UT", layout="wide")
st.title("📊 Dashboard Ejecutivo - Asignación por Bloque de Barrio")

# Cargar archivo
archivo = st.file_uploader("Sube el archivo de Seguimiento", type=["xls", "xlsx", "xlsm", "xlsb"])

# Columnas
col_barrio = "BARRIO"
col_ciclo = "CICLO_FACTURACION"
col_direccion = "DIRECCION"
col_tecnico = "TECNICOS_INTEGRALES"
col_deuda = "DEUDA_TOTAL"
col_edad = "RANGO_EDAD"
col_subcat = "SUBCATEGORIA"

if archivo:
    try:
        # =========================
        # 1. LECTURA
        # =========================
        if archivo.name.lower().endswith(".xls"):
            df = pd.read_excel(archivo, engine="xlrd")
        else:
            df = pd.read_excel(archivo, engine="openpyxl")

        df.columns = df.columns.str.strip()

        # Limpieza general
        df[col_subcat] = df[col_subcat].astype(str).str.strip()

        # Limpieza deuda
        df["_deuda_num"] = (
            df[col_deuda].astype(str)
            .str.replace("$", "", regex=False)
            .str.replace(",", "", regex=False)
            .str.replace(".", "", regex=False)
            .str.strip()
        )
        df["_deuda_num"] = pd.to_numeric(df["_deuda_num"], errors="coerce").fillna(0)

        # =========================
        # TABS
        # =========================
        tab_filtros, tab1, tab2 = st.tabs(["⚙️ Filtros", "📋 Tabla y Descarga", "📊 Dashboard"])

        # =========================
        # FILTROS
        # =========================
        with tab_filtros:
            st.subheader("⚙️ Configuración de Filtros")

            ciclos_disp = sorted(df[col_ciclo].dropna().astype(str).unique())
            ciclos_sel = st.multiselect("Filtrar Ciclos", ciclos_disp, default=ciclos_disp)

            tecnicos_disp = sorted(df[col_tecnico].dropna().astype(str).str.strip().unique())
            tecnicos_sel = st.multiselect("Técnicos a Procesar", tecnicos_disp, default=tecnicos_disp)

            edades_disp = sorted(df[col_edad].dropna().astype(str).unique())
            edades_sel = st.multiselect("Filtrar por Rango de Edad", edades_disp, default=edades_disp)

            subcat_disp = sorted(df[col_subcat].dropna().unique())
            subcat_sel = st.multiselect("Filtrar por Subcategoría", subcat_disp, default=subcat_disp)

        # =========================
        # FILTRADO BASE
        # =========================
        df_pool = df[
            (df[col_ciclo].astype(str).isin(ciclos_sel)) &
            (df[col_edad].astype(str).isin(edades_sel)) &
            (df[col_subcat].isin(subcat_sel))
        ].copy()

        # =========================
        # SEPARAR SIN TÉCNICO
        # =========================
        df_sin_tecnico = df_pool[
            df_pool[col_tecnico].isna() |
            (df_pool[col_tecnico].astype(str).str.strip() == "")
        ].copy()

        df_con_tecnico = df_pool.drop(df_sin_tecnico.index).copy()
        df_con_tecnico[col_tecnico] = df_con_tecnico[col_tecnico].astype(str).str.strip()

        # =========================
        # LÓGICA DE ASIGNACIÓN
        # =========================
        unidades_ph = [
            "ITA SUSPENSION BQ 15 PH", "ITA SUSPENSION BQ 31 PH", "ITA SUSPE
