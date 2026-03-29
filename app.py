import streamlit as st
import pandas as pd
import io
import plotly.express as px
from itertools import cycle

# =========================
# CONFIG
# =========================
st.set_page_config(page_title="Dashboard Ejecutivo UT", layout="wide")
st.title("📊 Dashboard Ejecutivo - Asignación por Bloque de Barrio")

archivo = st.file_uploader("Sube el archivo de Seguimiento", type=["xls", "xlsx", "xlsm", "xlsb"])

# Columnas
col_barrio = "BARRIO"
col_ciclo = "CICLO_FACTURACION"
col_direccion = "DIRECCION"
col_tecnico = "TECNICOS_INTEGRALES"
col_deuda = "DEUDA_TOTAL"
col_edad = "RANGO_EDAD"
col_subcat = "SUBCATEGORIA"

@st.cache_data
def cargar_datos(file):
    if file.name.lower().endswith(".xls"):
        return pd.read_excel(file, engine="xlrd")
    else:
        return pd.read_excel(file, engine="openpyxl")

if archivo:
    try:
        df = cargar_datos(archivo)
        df.columns = df.columns.str.strip()

        # Limpieza
        df[col_subcat] = df[col_subcat].astype(str).str.strip()

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

            st.markdown("### 🎯 Prioridad de Rango de Edad")
            edad_prioridad = st.text_area(
                "Orden (una por línea, arriba = mayor prioridad)",
                "\n".join(edades_disp)
            ).split("\n")

        # =========================
        # FILTRADO
        # =========================
        df_pool = df[
            (df[col_ciclo].astype(str).isin(ciclos_sel)) &
            (df[col_edad].astype(str).isin(edades_sel)) &
            (df[col_subcat].isin(subcat_sel))
        ].copy()

        # =========================
        # PRIORIDAD EDAD
        # =========================
        orden_edad = {edad.strip(): i for i, edad in enumerate(edad_prioridad)}
        df_pool["_prioridad_edad"] = df_pool[col_edad].astype(str).map(orden_edad)
        df_pool["_prioridad_edad"] = df_pool["_prioridad_edad"].fillna(999)

        # =========================
        # SIN TÉCNICO
        # =========================
        df_sin_tecnico = df_pool[
            df_pool[col_tecnico].isna() |
            (df_pool[col_tecnico].astype(str).str.strip() == "")
        ].copy()

        df_con_tecnico = df_pool.drop(df_sin_tecnico.index).copy()
        df_con_tecnico[col_tecnico] = df_con_tecnico[col_tecnico].astype(str).str.strip()

        # =========================
        # PH
        # =========================
        unidades_ph = [
            "ITA SUSPENSION BQ 15 PH", "ITA SUSPENSION BQ 31 PH", "ITA SUSPENSION BQ 32 PH",
            "ITA SUSPENSION BQ 34 PH", "ITA SUSPENSION BQ 35 PH", "ITA SUS-PENSION BQ 36 PH",
            "ITA SUSPENSION BQ 37 PH"
        ]

        df_ph_final = (
            df_con_tecnico[df_con_tecnico[col_tecnico].isin(unidades_ph)]
            .sort_values(by="_deuda_num", ascending=False)
            .groupby(col_tecnico)
            .head(50)
        )

        # =========================
        # OTROS + SIN TÉCNICO
        # =========================
        df_otros = pd.concat([
            df_con_tecnico[~df_con_tecnico[col_tecnico].isin(unidades_ph)],
            df_sin_tecnico
        ]).copy()

        # 🔥 AQUI SE APLICA PRIORIDAD
        df_otros = df_otros.sort_values(
            by=["_prioridad_edad", col_ciclo, col_barrio, col_direccion]
        )

        lista_final_otros = []

        tecnicos_no_ph = [t for t in tecnicos_sel if t not in unidades_ph]
        cupo_por_tecnico = {tec: 50 for tec in tecnicos_no_ph}
        ciclo_tecnicos = cycle(tecnicos_no_ph)

        indices_disponibles = df_otros.index.tolist()

        while indices_disponibles:
            tec = next(ciclo_tecnicos)

            if cupo_por_tecnico[tec] <= 0:
                continue

            idx_base = indices_disponibles[0]
            barrio_actual = df_otros.loc[idx_base, col_barrio]

            bloque_idx = [
                idx for idx in indices_disponibles
                if df_otros.loc[idx, col_barrio] == barrio_actual
            ][:cupo_por_tecnico[tec]]

            if not bloque_idx:
                indices_disponibles.pop(0)
                continue

            bloque = df_otros.loc[bloque_idx].copy()
            bloque[col_tecnico] = tec

            lista_final_otros.append(bloque)

            indices_disponibles = [i for i in indices_disponibles if i not in bloque_idx]
            cupo_por_tecnico[tec] -= len(bloque_idx)

        df_resultado = pd.concat([df_ph_final] + lista_final_otros, ignore_index=True)

        # Asegurar todos los técnicos
        presentes = set(df_resultado[col_tecnico].dropna().unique())
        faltantes = [t for t in tecnicos_sel if t not in presentes]

        if faltantes:
            df_resultado = pd.concat([df_resultado, pd.DataFrame({col_tecnico: faltantes})])

        # =========================
        # TABLA
        # =========================
        with tab1:
            st.dataframe(df_resultado.drop(columns=["_deuda_num"]), use_container_width=True)

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                df_resultado.drop(columns=["_deuda_num"]).to_excel(writer, index=False)

            st.download_button("📥 Descargar Excel", data=output.getvalue(), file_name="Asignacion_UT.xlsx")

        # =========================
        # DASHBOARD
        # =========================
        with tab2:
            c1, c2 = st.columns(2)

            with c1:
                st.subheader("🏆 Top 10 Técnicos (Deuda)")
                ranking = df_resultado.groupby(col_tecnico)["_deuda_num"].sum().sort_values(ascending=False).head(10).reset_index()
                ranking.columns = ["Técnico", "Deuda"]
                ranking["Deuda"] = ranking["Deuda"].apply(lambda x: f"$ {x:,.0f}")
                st.table(ranking)

            with c2:
                st.subheader("🥧 Distribución por Subcategoría")
                conteo_sub = df_resultado[col_subcat].value_counts().reset_index()
                conteo_sub.columns = [col_subcat, "cantidad"]
                fig_pie = px.pie(conteo_sub, names=col_subcat, values="cantidad", hole=0.4)
                st.plotly_chart(fig_pie, use_container_width=True)

            st.divider()

            st.subheader("📊 Pólizas por Rango de Edad")
            conteo_edad = df_resultado[col_edad].value_counts().reset_index()
            conteo_edad.columns = [col_edad, "cantidad"]
            fig_bar = px.bar(conteo_edad, x=col_edad, y="cantidad", color=col_edad, text_auto=True)
            st.plotly_chart(fig_bar, use_container_width=True)

    except Exception as e:
        st.error(f"Error detectado: {e}")
