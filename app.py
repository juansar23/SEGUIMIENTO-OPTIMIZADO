import streamlit as st
import pandas as pd
import io
import plotly.express as px

# Configuración
st.set_page_config(page_title="Dashboard Ejecutivo UT", layout="wide")
st.title("📊 Dashboard Ejecutivo - Asignación por Bloque de Barrios")

# Mapeo de Unidades PH (Blindado)
mapeo_ph = {
    "ITA SUSPENSION BQ 15 PH": "HENRY CHAPMAN RUIZ",
    "ITA SUSPENSION BQ 31 PH": "SORELI FIGUEROA ALMARALES",
    "ITA SUSPENSION BQ 32 PH": "JENNIFER MARIA ALAMO DEL VALLE",
    "ITA SUSPENSION BQ 34 PH": "MIRANDIS MARIA MARENCO DOMINGUEZ",
    "ITA SUSPENSION BQ 35 PH": "YONELIS DEL CARMEN MORELO MORELO",
    "ITA SUSPENSION BQ 36 PH": "YURANIS PATRICIA OSPINA CARCAMO",
    "ITA SUSPENSION BQ 37 PH": "TATIANA ISABEL CASTRO GUZMAN"
}

# Columnas
col_barrio, col_ciclo, col_direccion = "BARRIO", "CICLO_FACTURACION", "DIRECCION"
col_tecnico, col_unidad, col_deuda = "TECNICOS_INTEGRALES", "UNIDAD_TRABAJO", "DEUDA_TOTAL"
col_edad, col_subcat = "RANGO_EDAD", "SUBCATEGORIA"

archivo = st.file_uploader("Sube el archivo de Seguimiento", type=["xls", "xlsx", "xlsm", "xlsb"])

if archivo:
    try:
        df = pd.read_excel(archivo) if not archivo.name.lower().endswith(".xls") else pd.read_excel(archivo, engine="xlrd")
        df.columns = df.columns.str.strip()
        df["_deuda_num"] = pd.to_numeric(df[col_deuda].astype(str).str.replace(r"[\$,.]", "", regex=True), errors="coerce").fillna(0)

        tab_filtros, tab1, tab2 = st.tabs(["⚙️ Configuración", "📋 Tabla Final", "📊 Dashboard"])

        # Clasificar unidades
        def tipo_unidad(nombre):
            n = str(nombre).upper()
            if n in [k.upper() for k in mapeo_ph.keys()]:
                return "PH"
            elif "ITA GESTION" in n:
                return "GESTION"
            elif "ITA SUSPENSION" in n:
                return "SUSPENSION"
            return "OTRO"

        unidades_unicas = df[col_unidad].dropna().unique()
        unidades_ph = [u for u in unidades_unicas if tipo_unidad(u) == "PH"]
        unidades_gestion = [u for u in unidades_unicas if tipo_unidad(u) == "GESTION"]
        unidades_suspension = [u for u in unidades_unicas if tipo_unidad(u) == "SUSPENSION"]

        with tab_filtros:
            excluir_ph = st.checkbox("🚫 EXCLUIR UNIDADES PH", value=False)
            c1, c2, c3 = st.columns(3)
            with c1:
                ciclos_sel = st.multiselect("Ciclos", sorted(df[col_ciclo].dropna().unique().astype(str)), default=df[col_ciclo].dropna().unique().astype(str))
                subcat_sel = st.multiselect("Subcategoría", sorted(df[col_subcat].dropna().unique().astype(str)), default=df[col_subcat].dropna().unique().astype(str))
            with c2:
                edades_disp = sorted(df[col_edad].dropna().astype(str).unique())
                prioridad_edades = st.multiselect("Prioridad de Edad:", edades_disp, default=edades_disp)
            with c3:
                nombres_ph = list(mapeo_ph.values())
                # Separar técnicos por tipo para mostrar info
                tecs_gestion = sorted([t for t in df[col_tecnico].dropna().unique() 
                                       if t not in nombres_ph and 
                                       tipo_unidad(df[df[col_tecnico]==t][col_unidad].iloc[0]) == "GESTION"])
                tecs_suspension = sorted([t for t in df[col_tecnico].dropna().unique() 
                                          if t not in nombres_ph and 
                                          tipo_unidad(df[df[col_tecnico]==t][col_unidad].iloc[0]) == "SUSPENSION"])

                st.caption(f"👷 Técnicos Gestión ({len(tecs_gestion)}) — máx 25 pólizas c/u")
                tecnicos_gestion_sel = st.multiselect("Técnicos Gestión", tecs_gestion, default=tecs_gestion)
                st.caption(f"🔧 Técnicos Suspensión ({len(tecs_suspension)}) — máx 50 pólizas c/u")
                tecnicos_suspension_sel = st.multiselect("Técnicos Suspensión", tecs_suspension, default=tecs_suspension)

        # =========================
        # PROCESAMIENTO
        # =========================
        df_pool = df[(df[col_ciclo].astype(str).isin(ciclos_sel)) &
                     (df[col_edad].astype(str).isin(prioridad_edades)) &
                     (df[col_subcat].astype(str).isin(subcat_sel))].copy()

        df_pool[col_edad] = pd.Categorical(df_pool[col_edad], categories=prioridad_edades, ordered=True)

        indices_asignados = set()

        # 1. ASIGNACIÓN PH (máx 50, desde su propia unidad)
        df_ph_final = pd.DataFrame()
        if not excluir_ph:
            list_ph = []
            for unidad, funcionario in mapeo_ph.items():
                p_ph = df_pool[df_pool[col_unidad] == unidad].sort_values(
                    by=[col_edad, "_deuda_num"], ascending=[True, False]).head(50)
                if not p_ph.empty:
                    p_ph = p_ph.copy()
                    p_ph[col_tecnico] = funcionario
                    list_ph.append(p_ph)
                    indices_asignados.update(p_ph.index)
            if list_ph:
                df_ph_final = pd.concat(list_ph)

        # Pool sin PH, ordenado por prioridad
        df_otros = df_pool[~df_pool[col_unidad].isin(mapeo_ph.keys())].copy()
        df_otros = df_otros.sort_values(by=[col_edad, col_ciclo, col_barrio, col_direccion])

        lista_final = []

        # 2. ASIGNACIÓN GESTIÓN (máx 25, desde sus propias unidades)
        df_gestion_pool = df_otros[df_otros[col_unidad].isin(unidades_gestion)]

        for tec in tecnicos_gestion_sel:
            cupo = 25
            # Pólizas de la unidad del técnico que no estén asignadas
            unidad_tec = df[df[col_tecnico] == tec][col_unidad].iloc[0] if not df[df[col_tecnico] == tec].empty else None
            if unidad_tec is None:
                continue
            pols_libres = df_gestion_pool[
                (df_gestion_pool[col_unidad] == unidad_tec) &
                (~df_gestion_pool.index.isin(indices_asignados))
            ]

            while cupo > 0 and not pols_libres.empty:
                barrio_actual = pols_libres.iloc[0][col_barrio]
                bloque = pols_libres[pols_libres[col_barrio] == barrio_actual].head(cupo).copy()
                bloque[col_tecnico] = tec
                lista_final.append(bloque)
                indices_asignados.update(bloque.index)
                cupo -= len(bloque)
                pols_libres = df_gestion_pool[
                    (df_gestion_pool[col_unidad] == unidad_tec) &
                    (~df_gestion_pool.index.isin(indices_asignados))
                ]

        # 3. ASIGNACIÓN SUSPENSIÓN (máx 50: sus propias unidades + restante de gestión)
        df_suspension_pool = df_otros[
            (df_otros[col_unidad].isin(unidades_suspension)) |  # sus propias unidades
            (df_otros[col_unidad].isin(unidades_gestion))       # restante de gestión no asignado
        ]

        for tec in tecnicos_suspension_sel:
            cupo = 50
            pols_libres = df_suspension_pool[~df_suspension_pool.index.isin(indices_asignados)]

            while cupo > 0 and not pols_libres.empty:
                barrio_actual = pols_libres.iloc[0][col_barrio]
                bloque = pols_libres[pols_libres[col_barrio] == barrio_actual].head(cupo).copy()
                bloque[col_tecnico] = tec
                lista_final.append(bloque)
                indices_asignados.update(bloque.index)
                cupo -= len(bloque)
                pols_libres = df_suspension_pool[~df_suspension_pool.index.isin(indices_asignados)]

        df_resultado = pd.concat(
            ([df_ph_final] if not df_ph_final.empty else []) + lista_final,
            ignore_index=True
        ) if (not df_ph_final.empty or lista_final) else pd.DataFrame()

        # =========================
        # VISTAS
        # =========================
        with tab1:
            if not df_resultado.empty:
                st.dataframe(df_resultado.drop(columns=["_deuda_num"]), use_container_width=True)
                output = io.BytesIO()
                with pd.ExcelWriter(output) as w:
                    df_resultado.drop(columns=["_deuda_num"]).to_excel(w, index=False)
                st.download_button("📥 Descargar", output.getvalue(), "Asignacion.xlsx")

        with tab2:
            if not df_resultado.empty:
                c_d1, c_d2 = st.columns(2)
                with c_d1:
                    st.subheader("🏆 Top 10 Técnicos (Deuda)")
                    rank = df_resultado.groupby(col_tecnico)["_deuda_num"].sum().sort_values(ascending=False).head(10).reset_index()
                    st.table(rank.style.format({"_deuda_num": "$ {:,.0f}"}))
                with c_d2:
                    st.subheader("🥧 Subcategoría")
                    st.plotly_chart(px.pie(df_resultado, names=col_subcat), use_container_width=True)

    except Exception as e:
        st.error(f"Error: {e}")
