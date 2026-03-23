import streamlit as st
import pandas as pd
import io
import plotly.express as px

# Configuración
st.set_page_config(page_title="Dashboard Ejecutivo UT", layout="wide")

st.title("📊 Dashboard Ejecutivo - Asignación por Bloque de Barrio")

archivo = st.sidebar.file_uploader(
    "Sube el archivo de Seguimiento",
    type=["xls", "xlsx", "xlsm", "xlsb"]
)

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
        # LECTURA
        # =========================
        df = pd.read_excel(archivo)
        df.columns = df.columns.str.strip()

        # =========================
        # LIMPIAR DEUDA
        # =========================
        df["_deuda_num"] = (
            df[col_deuda].astype(str)
            .str.replace("$", "", regex=False)
            .str.replace(",", "", regex=False)
            .str.replace(".", "", regex=False)
            .str.strip()
        )
        df["_deuda_num"] = pd.to_numeric(df["_deuda_num"], errors="coerce").fillna(0)

        # =========================
        # FILTROS
        # =========================
        ciclos_disp = sorted(df[col_ciclo].astype(str).unique())
        ciclos_sel = st.sidebar.multiselect("Filtrar Ciclos", ciclos_disp, default=ciclos_disp)

        tecnicos_all = sorted(df[col_tecnico].dropna().astype(str).unique())
        tecnicos_sel = st.sidebar.multiselect("Técnicos a Procesar", tecnicos_all, default=tecnicos_all)

        # =========================
        # POOL (INCLUYE SIN TÉCNICO)
        # =========================
        df_pool = df[df[col_ciclo].astype(str).isin(ciclos_sel)].copy()

        df_con_tecnico = df_pool[df_pool[col_tecnico].isin(tecnicos_sel)].copy()
        df_sin_tecnico = df_pool[~df_pool.index.isin(df_con_tecnico.index)].copy()

        # =========================
        # LÓGICA DE ASIGNACIÓN
        # =========================
        unidades_ph = [
            "ITA SUSPENSION BQ 15 PH", "ITA SUSPENSION BQ 31 PH",
            "ITA SUSPENSION BQ 32 PH", "ITA SUSPENSION BQ 34 PH",
            "ITA SUSPENSION BQ 35 PH", "ITA SUS-PENSION BQ 36 PH",
            "ITA SUSPENSION BQ 37 PH"
        ]

        # -------- PH --------
        df_ph_final = (
            df_con_tecnico[df_con_tecnico[col_tecnico].isin(unidades_ph)]
            .sort_values(by="_deuda_num", ascending=False)
            .groupby(col_tecnico)
            .head(50)
        )

        # -------- OTROS --------
        df_otros = df_con_tecnico[~df_con_tecnico[col_tecnico].isin(unidades_ph)].copy()
        df_otros = df_otros.sort_values(by=[col_ciclo, col_barrio, col_direccion])

        lista_final = []
        indices_asignados = set()

        # CONTROL DE CUPOS
        conteo = {tec: 0 for tec in tecnicos_sel}

        # --------------------------
        # 1. RESPETAR ASIGNADOS
        # --------------------------
        for tec in [t for t in tecnicos_sel if t not in unidades_ph]:

            pols = df_otros[
                (df_otros[col_tecnico] == tec) &
                (~df_otros.index.isin(indices_asignados))
            ]

            while conteo[tec] < 50 and not pols.empty:

                barrio = pols.iloc[0][col_barrio]

                restante = 50 - conteo[tec]

                bloque = pols[pols[col_barrio] == barrio].head(restante)

                lista_final.append(bloque)
                indices_asignados.update(bloque.index)

                conteo[tec] += len(bloque)

                pols = df_otros[
                    (df_otros[col_tecnico] == tec) &
                    (~df_otros.index.isin(indices_asignados))
                ]

        # --------------------------
        # 2. ASIGNAR SIN TÉCNICO
        # --------------------------
        df_sin_tecnico = df_sin_tecnico.sort_values(
            by=[col_ciclo, col_barrio, col_direccion]
        )

        for tec in [t for t in tecnicos_sel if t not in unidades_ph]:

            disponibles = df_sin_tecnico[
                ~df_sin_tecnico.index.isin(indices_asignados)
            ]

            while conteo[tec] < 50 and not disponibles.empty:

                barrio = disponibles.iloc[0][col_barrio]

                restante = 50 - conteo[tec]

                bloque = disponibles[disponibles[col_barrio] == barrio].head(restante)

                temp = bloque.copy()
                temp[col_tecnico] = tec

                lista_final.append(temp)
                indices_asignados.update(bloque.index)

                conteo[tec] += len(bloque)

                disponibles = df_sin_tecnico[
                    ~df_sin_tecnico.index.isin(indices_asignados)
                ]

        # =========================
        # RESULTADO FINAL
        # =========================
        df_resultado = pd.concat([df_ph_final] + lista_final, ignore_index=True)

        # =========================
        # TABS
        # =========================
        tab1, tab2 = st.tabs(["📋 Tabla y Descarga", "📊 Dashboard"])

        # =========================
        # TABLA
        # =========================
        with tab1:
            st.dataframe(df_resultado.drop(columns=["_deuda_num"]), use_container_width=True)

            output = io.BytesIO()
            df_export = df_resultado.drop(columns=["_deuda_num"], errors="ignore")

            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                df_export.to_excel(writer, index=False)

            st.download_button(
                "📥 Descargar Excel",
                data=output.getvalue(),
                file_name="Asignacion_UT.xlsx"
            )

        # =========================
        # DASHBOARD
        # =========================
        with tab2:

            col1, col2 = st.columns(2)

            with col1:
                st.subheader("🏆 Top 10 Técnicos (Deuda)")
                ranking = (
                    df_resultado.groupby(col_tecnico)["_deuda_num"]
                    .sum()
                    .sort_values(ascending=False)
                    .head(10)
                    .reset_index()
                )
                ranking.columns = ["Técnico", "Deuda"]
                ranking["Deuda"] = ranking["Deuda"].apply(lambda x: f"$ {x:,.0f}")
                st.table(ranking)

            with col2:
                st.subheader("🥧 Subcategoría")
                conteo_sub = df_resultado[col_subcat].value_counts().reset_index()
                conteo_sub.columns = [col_subcat, "cantidad"]
                fig_pie = px.pie(conteo_sub, names=col_subcat, values="cantidad", hole=0.4)
                st.plotly_chart(fig_pie, use_container_width=True)

            st.divider()

            st.subheader("📊 Pólizas por Rango de Edad")
            conteo_edad = df_resultado[col_edad].value_counts().reset_index()
            conteo_edad.columns = [col_edad, "cantidad"]

            fig_bar = px.bar(conteo_edad, x=col_edad, y="cantidad", text_auto=True)
            st.plotly_chart(fig_bar, use_container_width=True)

    except Exception as e:
        st.error(f"Error detectado: {e}")
