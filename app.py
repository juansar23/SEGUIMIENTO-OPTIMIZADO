import streamlit as st
import pandas as pd
import io
import plotly.express as px

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

        # =========================
        # LIMPIEZA DEUDA
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

            # 🔥 FIX: quitar nan
            todos_tecnicos = sorted(df[col_tecnico].dropna().astype(str).str.strip().unique())
            tecnicos_sel = st.multiselect("Técnicos a Procesar", todos_tecnicos, default=todos_tecnicos)

            edades_disp = sorted(df[col_edad].dropna().astype(str).unique())
            edades_sel = st.multiselect("Filtrar por Rango de Edad", edades_disp, default=edades_disp)

        # =========================
        # FILTRADO BASE
        # =========================
        df_pool = df[
            (df[col_ciclo].astype(str).isin(ciclos_sel)) &
            (df[col_edad].astype(str).isin(edades_sel))
        ].copy()

        # =========================
        # SEPARAR SIN TÉCNICO (ANTES DE STRING)
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
            "ITA SUSPENSION BQ 15 PH", "ITA SUSPENSION BQ 31 PH", "ITA SUSPENSION BQ 32 PH",
            "ITA SUSPENSION BQ 34 PH", "ITA SUSPENSION BQ 35 PH", "ITA SUS-PENSION BQ 36 PH",
            "ITA SUSPENSION BQ 37 PH"
        ]

        # PH
        df_ph_final = (
            df_con_tecnico[df_con_tecnico[col_tecnico].isin(unidades_ph)]
            .sort_values(by="_deuda_num", ascending=False)
            .groupby(col_tecnico)
            .head(50)
        )

        # OTROS + SIN TÉCNICO
        df_otros = pd.concat([
            df_con_tecnico[~df_con_tecnico[col_tecnico].isin(unidades_ph)],
            df_sin_tecnico
        ]).copy()

        df_otros = df_otros.sort_values(by=[col_ciclo, col_barrio, col_direccion])

        lista_final_otros = []
        indices_asignados = set()

        tecnicos_no_ph = [t for t in tecnicos_sel if t not in unidades_ph]

        for tec in tecnicos_no_ph:
            cupo = 50
            acumulado_tec = []

            pols_disponibles = df_otros[~df_otros.index.isin(indices_asignados)]

            while cupo > 0 and not pols_disponibles.empty:
                barrio_actual = pols_disponibles.iloc[0][col_barrio]

                bloque_barrio = pols_disponibles[
                    pols_disponibles[col_barrio] == barrio_actual
                ].head(cupo)

                acumulado_tec.append(bloque_barrio)
                indices_asignados.update(bloque_barrio.index)

                cupo -= len(bloque_barrio)
                pols_disponibles = df_otros[~df_otros.index.isin(indices_asignados)]

            if acumulado_tec:
                df_tec_res = pd.concat(acumulado_tec)
                df_tec_res[col_tecnico] = tec
                lista_final_otros.append(df_tec_res)

        df_resultado = pd.concat([df_ph_final] + lista_final_otros, ignore_index=True)

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
