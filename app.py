import streamlit as st
import pandas as pd
import io
import plotly.express as px
import re

st.set_page_config(page_title="Dashboard Ejecutivo UT", layout="wide")

st.title("📊 Dashboard Ejecutivo - Asignación Inteligente UT")

archivo = st.file_uploader("Sube el archivo", type=["xlsx", "xls"])

# Columnas
col_barrio = "BARRIO"
col_ciclo = "CICLO_FACTURACION"
col_direccion = "DIRECCION"
col_tecnico = "TECNICOS_INTEGRALES"
col_deuda = "DEUDA_TOTAL"
col_edad = "RANGO_EDAD"
col_subcat = "SUBCATEGORIA"

# =========================
# 🧠 NORMALIZAR DIRECCIÓN PRO
# =========================
def normalizar_direccion(dir):
    try:
        d = str(dir).upper()

        # Unificar nombres
        d = d.replace("CARRERA", "CR").replace("CRA", "CR")
        d = d.replace("CALLE", "CL")

        # Extraer números
        nums = re.findall(r'\d+', d)

        partes = d.split()

        if len(partes) >= 2:
            via = partes[0]
            numero_via = partes[1]

            if len(nums) >= 2:
                return f"{via} {numero_via} #{nums[0]}-{nums[1]}"
            else:
                return f"{via} {numero_via}"
        else:
            return d

    except:
        return str(dir)

# =========================
if archivo:
    try:
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
        # NORMALIZAR DIRECCIONES
        # =========================
        df["DIR_BASE"] = df[col_direccion].apply(normalizar_direccion)

        # =========================
        # TABS
        # =========================
        tab1, tab2, tab3 = st.tabs([
            "📋 Tabla",
            "🎯 Filtros",
            "📊 Dashboard"
        ])

        # =========================
        # FILTROS
        # =========================
        with tab2:

            ciclos = sorted(df[col_ciclo].astype(str).unique())
            ciclos_sel = st.multiselect("Ciclo", ciclos, default=ciclos)

            tecnicos = sorted(df[col_tecnico].astype(str).unique())

            tecnicos_sel = st.multiselect("Técnicos", tecnicos, default=tecnicos)

            tecnicos_excluir = st.multiselect("🚫 Excluir técnicos", tecnicos)

            deuda_min = st.number_input("💰 Deuda mínima", 0, value=0, step=50000)

            st.session_state["ciclos"] = ciclos_sel
            st.session_state["tecnicos"] = tecnicos_sel
            st.session_state["excluir"] = tecnicos_excluir
            st.session_state["deuda"] = deuda_min

        # =========================
        # FILTRADO BASE
        # =========================
        ciclos_sel = st.session_state.get("ciclos", ciclos)
        tecnicos_sel = st.session_state.get("tecnicos", tecnicos)
        excluir = st.session_state.get("excluir", [])
        deuda_min = st.session_state.get("deuda", 0)

        df_pool = df[
            (df[col_ciclo].astype(str).isin(ciclos_sel)) &
            (df[col_tecnico].isin(tecnicos_sel)) &
            (~df[col_tecnico].isin(excluir)) &
            (df["_deuda_num"] >= deuda_min)
        ].copy()

        # =========================
        # SEPARAR PH
        # =========================
        unidades_ph = [
            "ITA SUSPENSION BQ 15 PH",
            "ITA SUSPENSION BQ 31 PH",
            "ITA SUSPENSION BQ 32 PH",
            "ITA SUSPENSION BQ 34 PH",
            "ITA SUSPENSION BQ 35 PH",
            "ITA SUS-PENSION BQ 36 PH",
            "ITA SUSPENSION BQ 37 PH"
        ]

        df_ph = df_pool[df_pool[col_tecnico].isin(unidades_ph)].copy()

        df_ph_final = (
            df_ph.sort_values("_deuda_num", ascending=False)
            .groupby(col_tecnico)
            .head(50)
        )

        # =========================
        # NO PH → LÓGICA DIOS
        # =========================
        df_np = df_pool[~df_pool[col_tecnico].isin(unidades_ph)].copy()

        # ORDEN INTELIGENTE
        df_np = df_np.sort_values(
            by=[col_ciclo, col_barrio, "DIR_BASE", "_deuda_num"],
            ascending=[True, True, True, False]
        )

        asignados = []
        usados = set()

        tecnicos_finales = [t for t in tecnicos_sel if t not in excluir and t not in unidades_ph]

        for tec in tecnicos_finales:

            cupo = 50

            disponibles = df_np[~df_np.index.isin(usados)]

            for (ciclo, barrio, dirb), grupo in disponibles.groupby([col_ciclo, col_barrio, "DIR_BASE"]):

                if cupo <= 0:
                    break

                bloque = grupo.head(cupo)

                bloque = bloque.copy()
                bloque[col_tecnico] = tec

                asignados.append(bloque)

                usados.update(bloque.index)

                cupo -= len(bloque)

        df_final = pd.concat([df_ph_final] + asignados, ignore_index=True)

        # =========================
        # TABLA
        # =========================
        with tab1:
            st.success(f"Total pólizas asignadas: {len(df_final)}")
            st.dataframe(df_final.drop(columns=["_deuda_num"]), use_container_width=True)

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                df_final.drop(columns=["_deuda_num"]).to_excel(writer, index=False)

            st.download_button("📥 Descargar Excel", data=output.getvalue(), file_name="Asignacion_DI0S.xlsx")

        # =========================
        # DASHBOARD
        # =========================
        with tab3:

            col1, col2 = st.columns(2)

            with col1:
                st.subheader("🏆 Top Técnicos por Deuda")

                ranking = (
                    df_final.groupby(col_tecnico)["_deuda_num"]
                    .sum()
                    .sort_values(ascending=False)
                    .reset_index()
                )

                ranking["_deuda_num"] = ranking["_deuda_num"].apply(lambda x: f"$ {x:,.0f}")
                st.dataframe(ranking, use_container_width=True)

            with col2:
                st.subheader("🥧 Subcategoría")

                sub = df_final[col_subcat].value_counts().reset_index()
                sub.columns = ["Subcategoría", "Cantidad"]

                fig1 = px.pie(sub, names="Subcategoría", values="Cantidad")
                st.plotly_chart(fig1, use_container_width=True, key="pie")

            st.divider()

            st.subheader("📊 Rango Edad")

            edad = df_final[col_edad].value_counts().reset_index()
            edad.columns = ["Rango", "Cantidad"]

            fig2 = px.bar(edad, x="Rango", y="Cantidad", text_auto=True)
            st.plotly_chart(fig2, use_container_width=True, key="bar")

    except Exception as e:
        st.error(f"❌ Error: {e}")

else:
    st.info("👆 Sube el archivo para comenzar")
