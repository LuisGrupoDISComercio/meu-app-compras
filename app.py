import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from itertools import combinations
from collections import Counter

st.set_page_config(
    page_title="Motor de Compras — Ar Condicionado",
    page_icon="❄️",
    layout="wide",
)

# ─────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────
FABRICANTES_IGNORAR = {900, 995, 998, 999}

MAPA_FABRICANTES_ESTOQUE = {
    2: "LG",
    3: "Samsung",
    4: "Midea",
    5: "Daikin",
    6: "Agratto",
    7: "Gree",
    10: "Trane",
    11: "TCL",
}

LOGOS = {
    "LG": "images/LG_logo_2014svg.png",
    "Samsung": "images/Samsung_Logo.png",
    "Midea": "images/Midea_Logo.jpg",
    "Daikin": "images/daikin_logo.png",
    "Agratto": "images/aGRATTO_LOGO.jpg",
    "Gree": "images/gree_LOGO.png",
    "Trane": "images/pngtransparenttraneredhorizontallogo.png",
    "TCL": "images/TCL_logo.png",
}

COR_ABC = {
    "A+": {"bg": "#8B6914", "fg": "#FFFFFF"},
    "A": {"bg": "#FFD700", "fg": "#1a1a1a"},
    "B": {"bg": "#FFA500", "fg": "#1a1a1a"},
    "C": {"bg": "#FFFF99", "fg": "#1a1a1a"},
    "X": {"bg": "#D3D3D3", "fg": "#1a1a1a"},
}


# ─────────────────────────────────────────────
# UTILITÁRIOS
# ─────────────────────────────────────────────
def fmt_brl(valor):
    try:
        return f"R$ {valor:_.2f}".replace(".", ",").replace("_", ".")
    except Exception:
        return valor


def fmt_qtde(valor):
    try:
        return f"{int(valor):,}".replace(",", ".")
    except Exception:
        return valor


def colorir_abc_valor(classe):
    if pd.isna(classe):
        return ""
    info = COR_ABC.get(str(classe), COR_ABC["X"])
    return f"background-color: {info['bg']}; color: {info['fg']}; font-weight: bold;"


# ─────────────────────────────────────────────
# CARREGAMENTO DE ESTOQUE
# ─────────────────────────────────────────────
@st.cache_data
def carregar_estoque(file_obj):
    try:
        xls = pd.ExcelFile(file_obj)
        aba = xls.sheet_names[0]
        df_raw = xls.parse(aba, header=None)

        # encontra linha de cabeçalho pela palavra "Produto"
        header_row = None
        for i, row in df_raw.iterrows():
            if row.astype(str).str.contains("Produto", case=False).any():
                header_row = i
                break

        if header_row is None:
            return pd.DataFrame()

        df = xls.parse(aba, header=header_row)
        df.columns = df.columns.astype(str).str.strip()

        # remove colunas totalmente vazias
        df = df.dropna(axis=1, how="all")

        # padronizar nomes importantes
        rename_map = {}
        for col in df.columns:
            lower = col.lower().strip()
            if "produto" == lower:
                rename_map[col] = "produto"
            elif "descr" in lower:
                rename_map[col] = "descricao"
            elif "grupo" in lower:
                rename_map[col] = "grupo"
            elif "btu" in lower:
                rename_map[col] = "btu"
            elif "ciclo" in lower:
                rename_map[col] = "ciclo"
            elif "qtde" in lower or "qtd" in lower:
                rename_map[col] = "qtde"
            elif "vl custo" in lower:
                rename_map[col] = "vl_custo"
            elif "vl total" in lower or "valor total" in lower:
                rename_map[col] = "vl_total"
            elif "marca" in lower:
                rename_map[col] = "marca"

        df = df.rename(columns=rename_map)

        # garantir colunas numéricas
        for c in ["qtde", "vl_custo", "vl_total"]:
            if c in df.columns:
                df[c] = (
                    df[c]
                    .astype(str)
                    .str.replace(".", "", regex=False)
                    .str.replace(",", ".", regex=False)
                )
                df[c] = pd.to_numeric(df[c], errors="coerce")

        return df
    except Exception as e:
        st.error(f"Erro ao carregar estoque: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────
# CARREGAMENTO DE VENDAS
# ─────────────────────────────────────────────
@st.cache_data
def carregar_vendas(file_obj):
    try:
        df = pd.read_csv(
            file_obj,
            sep=";",
            decimal=",",
            encoding="latin-1",
        )
        df.columns = df.columns.astype(str).str.strip()

        # normalizar datas
        if "Emissao NF" in df.columns:
            df["Emissao NF"] = pd.to_datetime(
                df["Emissao NF"], format="%d/%m/%Y", errors="coerce"
            )

        # normalizar campos numéricos
        for col in ["Qtde", "VL Custo (Últ Entrada)", "VL Total"]:
            if col in df.columns:
                df[col] = (
                    df[col]
                    .astype(str)
                    .str.replace(".", "", regex=False)
                    .str.replace(",", ".", regex=False)
                )
                df[col] = pd.to_numeric(df[col], errors="coerce")

        return df
    except Exception as e:
        st.error(f"Erro ao carregar vendas: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────
# CÁLCULO ABC IA
# ─────────────────────────────────────────────
def classificar_abc_ia(df, col_qtde, col_valor):
    df = df.copy()
    df["qtde_total"] = df[col_qtde].fillna(0)
    df["valor_total"] = df[col_valor].fillna(0)

    df = df.sort_values("qtde_total", ascending=False)
    df["perc_acum_unid"] = df["qtde_total"].cumsum() / df["qtde_total"].sum()

    def faixa_unid(p):
        if p <= 0.5:
            return "A+"
        elif p <= 0.8:
            return "A"
        elif p <= 0.95:
            return "B"
        elif p <= 0.99:
            return "C"
        else:
            return "X"

    df["classe_abc_IA_unid"] = df["perc_acum_unid"].apply(faixa_unid)

    df = df.sort_values("valor_total", ascending=False)
    df["perc_acum_valor"] = df["valor_total"].cumsum() / df["valor_total"].sum()

    def faixa_valor(p):
        if p <= 0.5:
            return "A+"
        elif p <= 0.8:
            return "A"
        elif p <= 0.95:
            return "B"
        elif p <= 0.99:
            return "C"
        else:
            return "X"

    df["classe_abc_IA_$"] = df["perc_acum_valor"].apply(faixa_valor)

    return df


# ─────────────────────────────────────────────
# ABA ESTOQUE & ABC
# ─────────────────────────────────────────────
def aba_estoque(estoque_df, vendas_df):
    st.header("📦 Estoque & ABC IA")

    if estoque_df.empty:
        st.warning("Carregue o arquivo de estoque para ver esta aba.")
        return

    # filtro período para cálculo ABC
    meses = st.slider(
        "Período para cálculo do ABC IA (meses)",
        min_value=3,
        max_value=24,
        value=9,
        step=1,
    )

    # Filtro de fabricante / marca — corrigido para não quebrar se coluna não existir
    if "marca" in estoque_df.columns:
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            marcas_disponiveis = sorted(
                estoque_df["marca"].dropna().astype(str).unique()
            )
            marca_sel = st.multiselect(
                "Filtrar por marca (estoque)",
                options=marcas_disponiveis,
                default=marcas_disponiveis,
            )
            if marca_sel:
                estoque_df = estoque_df[estoque_df["marca"].isin(marca_sel)]
    else:
        st.info(
            "Arquivo de estoque não possui coluna 'marca'. "
            "Os filtros por fabricante/brand foram desativados."
        )

    # cálculo ABC baseado no valor total em estoque
    if "vl_total" not in estoque_df.columns:
        st.error(
            "A planilha de estoque precisa ter uma coluna de valor total "
            "(`VL Total`, `Valor total` etc.)."
        )
        return

    if "qtde" not in estoque_df.columns:
        st.error(
            "A planilha de estoque precisa ter uma coluna de quantidade "
            "(`Qtde`, `Qtd` etc.)."
        )
        return

    base_abc = estoque_df.copy()
    base_abc = base_abc.rename(
        columns={
            "qtde": "Qtde_Estoque",
            "vl_total": "VL_Total_Estoque",
        }
    )

    base_abc = classificar_abc_ia(
        base_abc, col_qtde="Qtde_Estoque", col_valor="VL_Total_Estoque"
    )

    # tabela
    cols_visiveis = [
        c
        for c in [
            "marca",
            "grupo",
            "btu",
            "ciclo",
            "produto",
            "descricao",
            "Qtde_Estoque",
            "VL_Total_Estoque",
            "classe_abc_IA_unid",
            "classe_abc_IA_$",
        ]
        if c in base_abc.columns
    ]

    df_view = base_abc[cols_visiveis].copy()

    if "Qtde_Estoque" in df_view.columns:
        df_view["Qtde_Estoque"] = df_view["Qtde_Estoque"].apply(fmt_qtde)
    if "VL_Total_Estoque" in df_view.columns:
        df_view["VL_Total_Estoque"] = df_view["VL_Total_Estoque"].apply(fmt_brl)

    st.subheader("Visão de Estoque com ABC IA")

    styler = df_view.style

    if "classe_abc_IA_unid" in df_view.columns:
        styler = styler.map(colorir_abc_valor, subset=["classe_abc_IA_unid"])
    if "classe_abc_IA_$" in df_view.columns:
        styler = styler.map(colorir_

