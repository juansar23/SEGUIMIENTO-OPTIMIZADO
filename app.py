import streamlit as st
import pandas as pd
import io
import plotly.express as px
import re

st.set_page_config(page_title="UT Optimizado", layout="wide")

st.title("📊 Dashboard UT - Asignación Inteligente PRO")

archivo = st.file_uploader("Sube archivo", type=["xlsx"])

col_barrio = "BARRIO"
col_ciclo = "CICLO_FACTURACION"
col_direccion = "DIRECCION"
col_tecnico = "TECNICOS_INTEGRALES"
col_deuda = "DEUDA_TOTAL"
col_edad = "RANGO_EDAD"
col_subcat = "SUBCATEGORIA"

# =========================
# NORMALIZAR DIRECCIÓN
# =========================
def normalizar_direccion(dir):
    try:
        d = str(dir).upper()
        d = d.replace("CARRERA", "CR").replace("CRA", "CR")
        d = d.replace("CALLE", "CL")
        nums = re.findall(r'\d+', d)
        partes = d.split()

        if len(partes) >= 2:
            if len(nums) >= 2:
                return f"{partes[0]} {partes[1]} #{nums[0]}-{nums[1]}"
            return f"{partes[0]} {partes[1]}"
        return d
    except:
        return str(dir)

# =========================
# ORDENAR RANGOS
# =========================
def ordenar_rangos(rangos):
    orden = ["0-30", "31-60", "61-90", "91-120", "121-360", "361-1080", ">1080"]
    rangos = list(map(str, rangos))
    return sorted(rangos, key=lambda x: orden.index(x) if x in orden else 999)

if archivo:
    try:
        columnas = [
            col_barrio, col_ciclo, col_direccion,
            col_tecnico, col_deuda, col_edad, col_subcat
        ]

        df = pd.read_excel(archivo, usecols=columnas)
        df.columns = df.columns.str.strip()

        # =========================
        # OPTIMIZACIÓN
        # =========================
        df[col_barrio] = df[col_barrio].astype("category")
        df[col_ciclo] = df[col_ciclo].astype("category")

        # =========================
        # LIMPIAR DEUDA
        # =========================
        df["_deuda_num"] = (
            df[col_deuda].astype(str)
            .str.replace("$", "", regex=False)
            .str.replace(",", "", regex=False)
            .str.replace(".", "", regex=False)
        )
        df["_deuda_num"] = pd.to_numeric(df["_deuda_num"], errors="coerce").fillna(0)

        # =========================
        # LIMPIAR RANGO
        # =========================
        df[col_edad] = df[col_edad].fillna("SIN DATO").astype(str)

        # =========================
        # NORMALIZAR DIRECCIÓN
        # =========================
        df["DIR_BASE"] = df[col_direccion].apply(normalizar_direccion)

        # =========================
        # FILTROS
        # =========================
        with st.expander("🎯 Filtros", expanded=True):

            ciclos_sel = st.multiselect(
                "Ciclo",
                sorted(df[col_ciclo].unique()),
                default=list(df[col_ciclo].unique())
            )

            tecnicos_all = df[col_tecnico].dropna().astype(str).unique()

            tecnicos_sel = st.multiselect(
                "Técnicos",
                tecnicos_all,
                default=tecnicos_all
            )

            excluir = st.multiselect(
                "🚫 Técnicos a excluir",
                tecnicos_all
            )

            rangos_disp = ordenar_rangos(df[col_edad].unique())

            rangos_sel = st.multiselect(
                "📊 Rango Edad",
                rangos_disp,
                default=rangos_disp
            )

            deuda_min = st.number_input(
                "💰 Deuda mínima",
                min_value=0,
                value=0,
                step=50000,
                format="%d"
            )

        # =========================
        # FILTRADO
        # =========================
        mask = (
            df[col_ciclo].isin(ciclos_sel) &
            (df["_deuda_num"] >= deuda_min) &
            df[col_edad].isin(rangos_sel)
        )

        df_filtrado = df.loc[mask].copy()

        # =========================
        # SEPARAR
        # =========================
        df_con_tecnico = df_filtrado[df_filtrado[col_tecnico].notna()].copy()
        df_sin_tecnico = df_filtrado[df_filtrado[col_tecnico].isna()].copy()

        df_con_tecnico = df_con_tecnico[
            df_con_tecnico[col_tecnico].isin(tecnicos_sel)
        ]

        df_con_tecnico = df_con_tecnico[
            ~df_con_tecnico[col_tecnico].isin(excluir)
        ]

        # =========================
        # ORDEN
        # =========================
        df_con_tecnico = df_con_tecnico.sort_values(
            by=[col_ciclo, col_barrio, "DIR_BASE"]
        )

        df_sin_tecnico = df_sin_tecnico.sort_values(
            by=[col_ciclo, col_barrio, "DIR_BASE"]
        )

        # =========================
        # ASIGNACIÓN PRO (MAX 50 REAL)
        # =========================
        asignados = []
        usados = set()

        tecnicos_final = [t for t in tecnicos_sel if t not in excluir]

        conteo_tecnicos = {tec: 0 for tec in tecnicos_final}

        # -------- 1. RESPETAR --------
        for tec in tecnicos_final:

            df_tec = df_con_tecnico[
                (df_con_tecnico[col_tecnico] == tec) &
                (~df_con_tecnico.index.isin(usados))
            ]

            for _, grupo in df_tec.groupby([col_ciclo, col_barrio, "DIR_BASE"]):

                restante = 50 - conteo_tecnicos[tec]

                if restante <= 0:
                    break

                bloque = grupo.head(restante)

                asignados.append(bloque)
                usados.update(bloque.index)

                conteo_tecnicos[tec] += len(bloque)

        # -------- 2. REPARTIR VACÍOS --------
        for tec in tecnicos_final:

            disponibles = df_sin_tecnico.loc[
                ~df_sin_tecnico.index.isin(usados)
            ]

            for _, grupo in disponibles.groupby([col_ciclo, col_barrio, "DIR_BASE"]):

                restante = 50 - conteo_tecnicos[tec]

                if restante <= 0:
                    break

                bloque = grupo.head(restante)

                temp = bloque.copy()
                temp[col_tecnico] = tec

                asignados.append(temp)
                usados.update(bloque.index)

                conteo_tecnicos[tec] += len(bloque)

        # =========================
        # RESULTADO
        # =========================
        if asignados:
            df_final = pd.concat(asignados, ignore_index=True)
        else:
            df_final = pd.DataFrame()

        # =========================
        # TABLA
        # =========================
        st.success(f"Total asignado: {len(df_final)}")
        st.dataframe(df_final, use_container_width=True)

        # =========================
        # CONTROL
        # =========================
        st.subheader("📊 Control por Técnico")
        control = df_final[col_tecnico].value_counts().reset_index()
        control.columns = ["Técnico", "Cantidad"]
        st.dataframe(control, use_container_width=True)

        # =========================
        # DASHBOARD
        # =========================
        if not df_final.empty:

            col1, col2 = st.columns(2)

            with col1:
                st.subheader("🏆 Top Técnicos (Deuda)")
                ranking = (
                    df_final.groupby(col_tecnico)["_deuda_num"]
                    .sum()
                    .sort_values(ascending=False)
                    .reset_index()
                )
                ranking.columns = ["Técnico", "Deuda"]
                ranking["Deuda"] = ranking["Deuda"].apply(lambda x: f"$ {x:,.0f}")
                st.dataframe(ranking, use_container_width=True)

            with col2:
                st.subheader("🥧 Subcategoría")
                fig_pie = px.pie(df_final, names=col_subcat)
                st.plotly_chart(fig_pie, use_container_width=True)

            st.subheader("📊 Rango Edad")

            conteo = (
                df_final[col_edad]
                .value_counts()
                .reindex(ordenar_rangos(df_final[col_edad].unique()))
                .reset_index()
            )

            conteo.columns = ["Rango", "Cantidad"]

            fig_bar = px.bar(conteo, x="Rango", y="Cantidad", text_auto=True)
            st.plotly_chart(fig_bar, use_container_width=True)

        # =========================
        # DESCARGA
        # =========================
        output = io.BytesIO()
        df_final.drop(columns=["_deuda_num"], errors="ignore").to_excel(output, index=False)

        st.download_button(
            "📥 Descargar Excel",
            data=output.getvalue(),
            file_name="asignacion_ut.xlsx"
        )

    except Exception as e:
        st.error(f"Error: {e}")
