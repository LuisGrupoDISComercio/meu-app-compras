import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from itertools import combinations
from collections import Counter

st.set_page_config(
    page_title="Motor de Compras — Ar Condicionado",
    page_icon="❄️",
    layout="wide"
)

# ─────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────
FABRICANTES_IGNORAR = {900, 995, 998, 999}

MAPA_FABRICANTES_ESTOQUE = {
    2:  "LG",
    3:  "Samsung",
    4:  "Midea",
    5:  "Daikin",
    6:  "Agratto",
    7:  "Gree",
    10: "Trane",
    11: "TCL",
}

LOGOS = {
    "LG":      "images/LG_logo_2014svg.png",
    "Samsung": "images/Samsung_Logo.png",
    "Midea":   "images/Midea_Logo.jpg",
    "Daikin":  "images/daikin_logo.png",
    "Agratto": "images/aGRATTO_LOGO.jpg",
    "Gree":    "images/gree_LOGO.png",
    "Trane":   "images/pngtransparenttraneredhorizontallogo.png",
    "TCL":     "images/TCL_logo.png",
}

# ─────────────────────────────────────────────
# UTILITÁRIOS
# ─────────────────────────────────────────────
def fmt_brl(valor):
    try:
        return f"R$ {valor:_.2f}".replace(".", ",").replace("_", ".")
    except Exception:
        return valor

def colorir_abc(classe):
    cores = {
        "A+": "background-color: #b8860b; color: white;",
        "A":  "background-color: #ffd700; color: black;",
        "B":  "background-color: #ffa500; color: black;",
        "C":  "background-color: #fff59d; color: black;",
        "X":  "background-color: #e0e0e0; color: black;",
    }
    return cores.get(str(classe), "")

# ─────────────────────────────────────────────
# CARREGAMENTO DE DADOS
# ─────────────────────────────────────────────
@st.cache_data
def carregar_estoque(file_obj):
    try:
        xls = pd.ExcelFile(file_obj)
        aba = xls.sheet_names[0]
        df_raw = xls.parse(aba, header=None)

        # Detecta linha de cabeçalho procurando "Produto"
        header_row = None
        for i, row in df_raw.iterrows():
            if row.astype(str).str.contains("Produto", case=False).any():
                header_row = i
                break
        if header_row is None:
            return pd.DataFrame()

        df = xls.parse(aba, header=header_row)

        # Normaliza nomes de colunas
        cols_norm = [str(c).strip() for c in df.columns]
        df.columns = cols_norm

        mapa_cols = {}
        for c in cols_norm:
            c_low = c.lower()
            if "produto" in c_low and "descricao" not in c_low:
                mapa_cols[c] = "produto"
            elif "descri" in c_low:
                mapa_cols[c] = "descricao"
            elif "marca" in c_low:
                mapa_cols[c] = "marca"
            elif "grupo" in c_low:
                mapa_cols[c] = "grupo"
            elif "btu" in c_low:
                mapa_cols[c] = "btu"
            elif "ciclo" in c_low:
                mapa_cols[c] = "ciclo"
            elif "qtd" in c_low or "qtde" in c_low:
                mapa_cols[c] = "estoque_qtde"
            elif "custo" in c_low and "unit" in c_low:
                mapa_cols[c] = "custo_unit"
            elif "valor total" in c_low or ("vl" in c_low and "total" in c_low):
                mapa_cols[c] = "custo_total"

        df = df.rename(columns=mapa_cols)

        # Mantém apenas colunas úteis
        colunas_uteis = [
            "produto", "descricao", "marca", "grupo", "btu", "ciclo",
            "estoque_qtde", "custo_unit", "custo_total"
        ]
        df = df[[c for c in colunas_uteis if c in df.columns]].copy()

        # Conversões numéricas
        for col in ["estoque_qtde", "custo_unit", "custo_total"]:
            if col in df.columns:
                df[col] = (
                    df[col]
                    .astype(str)
                    .str.replace(".", "", regex=False)
                    .str.replace(",", ".", regex=False)
                )
                df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df[df.get("produto").notna()].copy()

        return df
    except Exception as e:
        st.sidebar.error(f"Erro ao carregar estoque: {e}")
        return pd.DataFrame()

@st.cache_data
def carregar_vendas(file_obj):
    try:
        # CSV vindo do Protheus com ; e decimal , ou .
        df = pd.read_csv(
            file_obj,
            sep=";",
            decimal=",",
            encoding="latin1",
            dtype=str,
            engine="python",
        )

        # Normaliza colunas
        df.columns = [c.strip() for c in df.columns]

        mapa_cols = {}
        for c in df.columns:
            c_low = c.lower()
            if "emissao" in c_low or "emissão" in c_low:
                mapa_cols[c] = "emissao_nf"
            elif "marca" in c_low:
                mapa_cols[c] = "marca"
            elif "grupo" in c_low:
                mapa_cols[c] = "grupo"
            elif "btu" in c_low:
                mapa_cols[c] = "btu"
            elif "ciclo" in c_low:
                mapa_cols[c] = "ciclo"
            elif c_low == "produto":
                mapa_cols[c] = "produto"
            elif "descri" in c_low:
                mapa_cols[c] = "descricao"
            elif "qtde" in c_low or "qtd" in c_low:
                mapa_cols[c] = "qtde"
            elif "vl custo" in c_low:
                mapa_cols[c] = "vl_custo_ult_entrada"
            elif "vl total" in c_low or ("valor" in c_low and "total" in c_low):
                mapa_cols[c] = "vl_total"
            elif "pedido" in c_low:
                mapa_cols[c] = "pedido"

        df = df.rename(columns=mapa_cols)

        # Conversão de data
        if "emissao_nf" in df.columns:
            df["emissao_nf"] = pd.to_datetime(
                df["emissao_nf"], format="%d/%m/%Y", errors="coerce"
            )

        # Conversão numérica
        for col in ["qtde", "vl_custo_ult_entrada", "vl_total"]:
            if col in df.columns:
                df[col] = (
                    df[col]
                    .astype(str)
                    .str.replace(".", "", regex=False)
                    .str.replace(",", ".", regex=False)
                )
                df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df[df["emissao_nf"].notna()].copy()

        return df
    except Exception as e:
        st.sidebar.error(f"Erro ao carregar vendas: {e}")
        return pd.DataFrame()

# ─────────────────────────────────────────────
# ABC IA (com base nas vendas)
# ─────────────────────────────────────────────
def classificar_abc_ia(vendas_df, periodo_meses=12):
    if vendas_df.empty:
        return pd.DataFrame()

    df = vendas_df.copy()

    # Filtra período
    if "emissao_nf" in df.columns:
        data_max = df["emissao_nf"].max()
        if pd.notna(data_max):
            limite = data_max - pd.DateOffset(months=periodo_meses)
            df = df[df["emissao_nf"] >= limite]

    # Agrega por produto
    grp = df.groupby("produto", as_index=False).agg(
        qtde_total=("qtde", "sum"),
        vl_total=("vl_total", "sum"),
        descricao=("descricao", "first"),
        marca=("marca", "first"),
        grupo=("grupo", "first"),
        btu=("btu", "first"),
        ciclo=("ciclo", "first"),
    )

    grp = grp.sort_values("vl_total", ascending=False).reset_index(drop=True)

    # Percentual acumulado em unidades
    grp["perc_unid"] = grp["qtde_total"] / grp["qtde_total"].sum()
    grp["perc_unid_acum"] = grp["perc_unid"].cumsum()

    # Percentual acumulado em valor
    if grp["vl_total"].sum() > 0:
        grp["perc_valor"] = grp["vl_total"] / grp["vl_total"].sum()
        grp["perc_valor_acum"] = grp["perc_valor"].cumsum()
    else:
        grp["perc_valor"] = 0
        grp["perc_valor_acum"] = 0

    # Classes ABC em unidades
    conds_u = [
        grp["perc_unid_acum"] <= 0.10,
        grp["perc_unid_acum"].between(0.10, 0.30, inclusive="right"),
        grp["perc_unid_acum"].between(0.30, 0.60, inclusive="right"),
        grp["perc_unid_acum"] > 0.60,
    ]
    choices = ["A+", "A", "B", "C"]
    grp["classe_abc_ia_unid"] = np.select(conds_u, choices, default="X")

    # Classes ABC em valor
    conds_v = [
        grp["perc_valor_acum"] <= 0.10,
        grp["perc_valor_acum"].between(0.10, 0.30, inclusive="right"),
        grp["perc_valor_acum"].between(0.30, 0.60, inclusive="right"),
        grp["perc_valor_acum"] > 0.60,
    ]
    grp["classe_abc_ia_valor"] = np.select(conds_v, choices, default="X")

    return grp

# ─────────────────────────────────────────────
# ABA ESTOQUE & ABC
# ─────────────────────────────────────────────
def aba_estoque(estoque_df, vendas_df):
    st.header("📦 Estoque & ABC IA")

    if estoque_df.empty:
        st.info("Carregue o arquivo de estoque para visualizar esta aba.")
        return

    col1, col2 = st.columns(2)
    with col1:
        periodo = st.slider(
            "Período para cálculo do ABC IA (meses)",
            min_value=3,
            max_value=24,
            value=12,
            step=3,
        )
    with col2:
        fab_filtro = st.multiselect(
            "Filtrar por marca (estoque)",
            options=sorted(estoque_df["marca"].dropna().unique()),
        )

    # Calcula ABC
    abc_df = classificar_abc_ia(vendas_df, periodo_meses=periodo)
    estoque = estoque_df.copy()

    # Merge com ABC pelas colunas em comum (produto)
    if not abc_df.empty:
        estoque = estoque.merge(
            abc_df[["produto", "classe_abc_ia_unid", "classe_abc_ia_valor"]],
            on="produto",
            how="left",
        )

    if fab_filtro:
        estoque = estoque[estoque["marca"].isin(fab_filtro)]

    # Valor total em estoque
    if "custo_total" not in estoque.columns and \
       {"estoque_qtde", "custo_unit"}.issubset(estoque.columns):
        estoque["custo_total"] = estoque["estoque_qtde"] * estoque["custo_unit"]

    valor_total = estoque.get("custo_total", pd.Series(dtype=float)).sum()
    st.metric("Valor total em estoque", fmt_brl(valor_total))

    # Tabela
    cols_ordem = [
        "produto", "descricao", "marca", "grupo", "btu", "ciclo",
        "estoque_qtde", "custo_unit", "custo_total",
        "classe_abc_ia_unid", "classe_abc_ia_valor",
    ]
    cols_ordem = [c for c in cols_ordem if c in estoque.columns]
    tabela = estoque[cols_ordem].copy()

    for c in ["custo_unit", "custo_total"]:
        if c in tabela.columns:
            tabela[c] = tabela[c].apply(fmt_brl)

    st.subheader("Tabela de Estoque com ABC IA")

    if {"classe_abc_ia_unid", "classe_abc_ia_valor"}.issubset(tabela.columns):
        styled = (
            tabela.style
            .map(colorir_abc, subset=["classe_abc_ia_unid"])
            .map(colorir_abc, subset=["classe_abc_ia_valor"])
        )
        st.dataframe(styled, use_container_width=True)
    else:
        st.dataframe(tabela, use_container_width=True)

# ─────────────────────────────────────────────
# ABA VENDAS & DEMANDA
# ─────────────────────────────────────────────
def aba_vendas(vendas_df):
    st.header("📈 Vendas & Demanda")

    st.write(
        f"Total de registros de vendas: "
        f"{len(vendas_df):,}".replace(",", ".")
    )

    if vendas_df.empty:
        st.info("Carregue o arquivo de vendas para visualizar esta aba.")
        return

    df = vendas_df.copy()

    # Conversão garantida de data e criação de coluna string segura
    if "emissao_nf" in df.columns:
        df["emissao_nf"] = pd.to_datetime(df["emissao_nf"], errors="coerce")
        df = df[df["emissao_nf"].notna()]
        df["emissao_nf_str"] = df["emissao_nf"].dt.strftime("%Y-%m-%d")
    else:
        st.warning("Coluna de data (Emissao NF) não encontrada.")
        return

    # Agregações
    df["ano_mes"] = df["emissao_nf"].dt.to_period("M").astype(str)

    vendas_mes = df.groupby("ano_mes", as_index=False).agg(
        qtde=("qtde", "sum"),
        valor=("vl_total", "sum"),
    )

    vendas_marca = df.groupby("marca", as_index=False).agg(
        qtde=("qtde", "sum"),
        valor=("vl_total", "sum"),
    )

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Vendas em valor por mês")
        fig_valor = px.bar(
            vendas_mes,
            x="ano_mes",
            y="valor",
            labels={"ano_mes": "Ano-Mês", "valor": "Valor vendido"},
            title="Valor vendido por mês",
        )
        fig_valor.update_layout(xaxis_title="Ano-Mês", yaxis_title="Valor vendido")
        st.plotly_chart(fig_valor, use_container_width=True)

    with col2:
        st.subheader("Vendas em unidades por mês")
        fig_qtde = px.line(
            vendas_mes,
            x="ano_mes",
            y="qtde",
            markers=True,
            labels={"ano_mes": "Ano-Mês", "qtde": "Quantidade vendida"},
            title="Quantidade vendida por mês",
        )
        fig_qtde.update_layout(xaxis_title="Ano-Mês", yaxis_title="Quantidade")
        st.plotly_chart(fig_qtde, use_container_width=True)

    st.subheader("Vendas por marca (em valor)")
    vendas_marca = vendas_marca.sort_values("valor", ascending=False)
    fig_marca = px.bar(
        vendas_marca,
        x="marca",
        y="valor",
        labels={"marca": "Marca", "valor": "Valor vendido"},
        title="Valor vendido por marca",
    )
    fig_marca.update_layout(xaxis_title="Marca", yaxis_title="Valor vendido")
    st.plotly_chart(fig_marca, use_container_width=True)

    # Tabela detalhada
    st.subheader("Tabela de vendas (amostra)")
    cols_tabela = [
        "emissao_nf", "marca", "grupo", "btu", "ciclo",
        "produto", "descricao", "qtde", "vl_custo_ult_entrada", "vl_total"
    ]
    cols_tabela = [c for c in cols_tabela if c in df.columns]
    tabela = df[cols_tabela].head(100).copy()

    for c in ["vl_custo_ult_entrada", "vl_total"]:
        if c in tabela.columns:
            tabela[c] = tabela[c].apply(fmt_brl)

    st.dataframe(tabela, use_container_width=True)

# ─────────────────────────────────────────────
# OUTRAS ABAS (placeholders simples por enquanto)
# ─────────────────────────────────────────────
def aba_cobertura(estoque_df, vendas_df):
    st.header("📊 Cobertura")
    st.info("Lógica detalhada de cobertura será implementada depois que Estoque e Vendas estiverem estáveis.")

def aba_sugestao(estoque_df, vendas_df):
    st.header("🛒 Sugestão de Compra")
    st.info("Sugestão de compra será implementada em seguida, usando a cobertura e o ABC IA.")

def aba_fornecedores(estoque_df):
    st.header("🏭 Fornecedores")
    st.info("Análises por fornecedor serão incluídas depois da consolidação de estoque.")

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    st.title("❄️ Motor de Compras — Ar Condicionado")

    st.sidebar.header("📂 Arquivos")
    est_file = st.sidebar.file_uploader("Estoque (.xlsx)", type=["xlsx"], key="est_up")
    vnd_file = st.sidebar.file_uploader("Vendas (.csv)", type=["csv"], key="vnd_up")

    estoque_df = pd.DataFrame()
    vendas_df = pd.DataFrame()

    if est_file is not None:
        estoque_df = carregar_estoque(est_file)
        if not estoque_df.empty:
            st.sidebar.success(f"✅ Estoque: {len(estoque_df)} produtos carregados")
        else:
            st.sidebar.error("❌ Estoque: 0 produtos — verifique o arquivo")

    if vnd_file is not None:
        vendas_df = carregar_vendas(vnd_file)
        if not vendas_df.empty:
            st.sidebar.success(
                f"✅ Vendas: {len(vendas_df):,} registros carregados".replace(",", ".")
            )
        else:
            st.sidebar.error("❌ Vendas: 0 registros — verifique o arquivo")

    tabs = st.tabs([
        "📦 Estoque & ABC",
        "📈 Vendas & Demanda",
        "📊 Cobertura",
        "🛒 Sugestão de Compra",
        "🏭 Fornecedores",
    ])

    with tabs[0]:
        aba_estoque(estoque_df, vendas_df)
    with tabs[1]:
        aba_vendas(vendas_df)
    with tabs[2]:
        aba_cobertura(estoque_df, vendas_df)
    with tabs[3]:
        aba_sugestao(estoque_df, vendas_df)
    with tabs[4]:
        aba_fornecedores(estoque_df)


if __name__ == "__main__":
    main()
