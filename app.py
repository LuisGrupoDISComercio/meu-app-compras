import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

st.set_page_config(
    page_title="Motor de Compras — Ar Condicionado",
    page_icon="❄️",
    layout="wide",
)

# =========================================================
# UTILITÁRIOS
# =========================================================
def fmt_brl(valor):
    try:
        v = float(valor)
        inteiro = int(v)
        decimal = round((v - inteiro) * 100)
        inteiro_fmt = f"{inteiro:,}".replace(",", ".")
        return f"R$ {inteiro_fmt},{decimal:02d}"
    except Exception:
        return str(valor)


def fmt_qtde(valor):
    try:
        return f"{int(float(valor)):,}".replace(",", ".")
    except Exception:
        return str(valor)


def colorir_abc(classe):
    cores = {
        "A+": ("#8B6914", "#FFFFFF"),
        "A": ("#FFD700", "#1a1a1a"),
        "B": ("#FFA500", "#1a1a1a"),
        "C": ("#FFFF99", "#1a1a1a"),
        "X": ("#D3D3D3", "#1a1a1a"),
    }
    if pd.isna(classe):
        return ""
    bg, fg = cores.get(str(classe).strip().upper(), cores["X"])
    return f"background-color: {bg}; color: {fg}; font-weight:bold; text-align:center;"


def parse_brl(series: pd.Series) -> pd.Series:
    """
    Converte série de strings em formato PT-BR (1.234.567,89)
    para float, sem estourar valores.
    """
    s = (
        series.astype(str)
        .str.replace(r"\s+", "", regex=True)
        .str.replace(".", "", regex=False)   # remove separador de milhar
        .str.replace(",", ".", regex=False)  # vírgula -> ponto decimal
    )
    return pd.to_numeric(s, errors="coerce")


# =========================================================
# CARREGAMENTO DE ESTOQUE
# =========================================================
@st.cache_data
def carregar_estoque(file_obj):
    """
    Lê Estoque.xlsx e padroniza:
    produto, descricao, qtde, vl_total (Custo Entrada Total),
    curva_sistema, marca, grupo, btu, ciclo, vl_custo.
    """
    try:
        df = pd.read_excel(file_obj, sheet_name=0, header=0, dtype=str)
        df.columns = df.columns.astype(str).str.strip()

        rename = {}
        col_custo_entrada_total = None

        for col in df.columns:
            lo = col.lower()
            if lo == "produto":
                rename[col] = "produto"
            elif "descri" in lo:
                rename[col] = "descricao"
            elif "grupo" in lo:
                rename[col] = "grupo"
            elif "btu" in lo:
                rename[col] = "btu"
            elif "ciclo" in lo:
                rename[col] = "ciclo"
            elif lo in ("qtde", "qtd", "quantidade", "saldo"):
                rename[col] = "qtde"
            # custo unitário
            elif "custo entrada" in lo and "unit" in lo:
                rename[col] = "vl_custo"
            # VALOR TOTAL DO ESTOQUE (Custo Entrada Total)
            elif "custo entrada total" in lo:
                rename[col] = "vl_total"
                col_custo_entrada_total = col  # guarda nome original
            elif "vl total" in lo or "valor total" in lo:
                rename[col] = "vl_total"
            elif "marca" in lo or "fabr" in lo or "fabricante" in lo:
                rename[col] = "marca"
            elif lo in ("curva", "curva abc", "classe", "abc", "curva_abc"):
                rename[col] = "curva_sistema"

        df = df.rename(columns=rename)

        # essenciais
        for c in ["produto", "qtde"]:
            if c not in df.columns:
                st.error(f"Estoque: coluna obrigatória '{c}' não encontrada.")
                return pd.DataFrame()

        # --------- CONVERSÃO NUMÉRICA SEGURA ----------
        # qtde
        df["qtde"] = parse_brl(df["qtde"])

        # custo unitário, se existir
        if "vl_custo" in df.columns:
            df["vl_custo"] = parse_brl(df["vl_custo"])

        # valor total:
        # 1) se veio do "Custo Entrada Total", converte só essa coluna
        if col_custo_entrada_total is not None:
            bruto = df["vl_total"].copy()  # já renomeado
            df["vl_total"] = parse_brl(bruto)
            df["vl_total_bruto"] = bruto   # opcional: guardar texto original
        # 2) senão, tenta converter normalmente
        elif "vl_total" in df.columns:
            df["vl_total"] = parse_brl(df["vl_total"])
        # 3) se não existir, mas temos qtde e custo unitário, calcula
        elif "vl_custo" in df.columns:
            df["vl_total"] = df["qtde"].fillna(0) * df["vl_custo"].fillna(0)

        # limpar strings básicas
        for c in ["produto", "descricao", "grupo", "btu", "ciclo", "marca", "curva_sistema"]:
            if c in df.columns:
                df[c] = df[c].astype(str).str.strip()

        df = df[df["qtde"] > 0]
        df = df.reset_index(drop=True)
        df["id"] = df.index

        return df

    except Exception as e:
        st.error(f"Erro ao carregar estoque: {e}")
        return pd.DataFrame()


# =========================================================
# CARREGAMENTO DE VENDAS
# =========================================================
@st.cache_data
def carregar_vendas(file_obj):
    try:
        df = pd.read_csv(file_obj, sep=";", decimal=",", encoding="latin1")
    except Exception:
        df = pd.read_csv(file_obj)

    df.columns = df.columns.astype(str).str.strip()

    rename = {}
    for col in df.columns:
        lo = col.lower()
        if "data" in lo:
            rename[col] = "data"
        elif lo == "produto":
            rename[col] = "produto"
        elif "descri" in lo:
            rename[col] = "descricao"
        elif "grupo" in lo:
            rename[col] = "grupo"
        elif "btu" in lo:
            rename[col] = "btu"
        elif "ciclo" in lo:
            rename[col] = "ciclo"
        elif "marca" in lo or "fabr" in lo or "fabricante" in lo:
            rename[col] = "marca"
        elif lo in ("qtde", "qtd", "quantidade"):
            rename[col] = "qtde"
        elif "vl custo" in lo or ("custo" in lo and "unit" in lo):
            rename[col] = "vl_custo"
        elif "vl total" in lo or "valor total" in lo:
            rename[col] = "vl_total"

    df = df.rename(columns=rename)

    if "qtde" in df.columns:
        df["qtde"] = parse_brl(df["qtde"])
    if "vl_custo" in df.columns:
        df["vl_custo"] = parse_brl(df["vl_custo"])
    if "vl_total" in df.columns:
        df["vl_total"] = parse_brl(df["vl_total"])
    if "data" in df.columns:
        df["data"] = pd.to_datetime(df["data"], errors="coerce", dayfirst=True)

    for c in ["produto", "descricao", "grupo", "btu", "ciclo", "marca"]:
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip()

    df = df[df.get("qtde", 0) > 0]
    df = df.reset_index(drop=True)
    return df


# =========================================================
# ABC
# =========================================================
def calcular_abc(df, col_qtde="qtde", col_valor="vl_total"):
    df = df.copy()
    df["valor_abc"] = df[col_valor] if col_valor in df.columns else df[col_qtde]

    total_valor = df["valor_abc"].sum()
    if total_valor == 0:
        df["classe_valor"] = "X"
        df["classe_unid"] = "X"
        return df

    df = df.sort_values("valor_abc", ascending=False)
    df["perc_acum_valor"] = df["valor_abc"].cumsum() / total_valor

    def classe_valor(p):
        if p <= 0.8:
            return "A"
        elif p <= 0.95:
            return "B"
        else:
            return "C"

    df["classe_valor"] = df["perc_acum_valor"].apply(classe_valor)

    total_qtde = df[col_qtde].sum()
    if total_qtde == 0:
        df["classe_unid"] = "X"
        return df

    df = df.sort_values(col_qtde, ascending=False)
    df["perc_acum_unid"] = df[col_qtde].cumsum() / total_qtde

    def classe_unid(p):
        if p <= 0.8:
            return "A"
        elif p <= 0.95:
            return "B"
        else:
            return "C"

    df["classe_unid"] = df["perc_acum_unid"].apply(classe_unid)
    return df


# =========================================================
# ABA ESTOQUE & ABC
# =========================================================
def aba_estoque(estoque_df, vendas_df):
    st.header("📦 Estoque & ABC IA")

    if estoque_df.empty:
        st.warning("Carregue o arquivo de estoque (.xlsx) na barra lateral.")
        return

    df = estoque_df.copy()
    df_abc = calcular_abc(df, col_qtde="qtde", col_valor="vl_total")

    # Cards
    col1, col2, col3 = st.columns(3)
    col1.metric("SKUs em estoque", fmt_qtde(df_abc["produto"].nunique()))
    col2.metric("Qtd total em estoque", fmt_qtde(df_abc["qtde"].sum()))
    if "vl_total" in df_abc.columns:
        col3.metric("Valor total em estoque", fmt_brl(df_abc["vl_total"].sum()))
    else:
        col3.metric("Valor total em estoque", "—")

    # Tabela detalhada
    st.subheader("Detalhe por produto (ABC IA x Curva Sistema)")
    cols = [
        "produto",
        "descricao",
        "qtde",
        "curva_sistema",
        "classe_unid",
        "classe_valor",
    ]
    cols = [c for c in cols if c in df_abc.columns]
    view = df_abc[cols].copy()

    view["qtde"] = view["qtde"].apply(fmt_qtde)

    styler = view.style
    if "classe_unid" in view.columns:
        styler = styler.map(colorir_abc, subset=["classe_unid"])
    if "classe_valor" in view.columns:
        styler = styler.map(colorir_abc, subset=["classe_valor"])

    st.dataframe(styler, use_container_width=True)


# =========================================================
# ABAS DE VENDAS / PLACEHOLDER
# =========================================================
def aba_vendas(vendas_df):
    st.header("📈 Vendas & Demanda")
    if vendas_df.empty:
        st.warning("Carregue o arquivo de vendas (.csv) na barra lateral.")
        return

    df = vendas_df.copy()

    col1, col2, col3 = st.columns(3)
    col1.metric("Registros de vendas", fmt_qtde(len(df)))
    col2.metric("SKUs vendidos", fmt_qtde(df["produto"].nunique()))
    if "vl_total" in df.columns:
        col3.metric("Valor total vendido", fmt_brl(df["vl_total"].sum()))
    else:
        col3.metric("Valor total vendido", "—")

    if "data" in df.columns and "vl_total" in df.columns:
        df_mes = df[df["data"].notna()].copy()
        df_mes["ano_mes"] = df_mes["data"].dt.to_period("M").astype(str)
        grup = (
            df_mes.groupby("ano_mes", as_index=False)
            .agg(qtde=("qtde", "sum"), valor=("vl_total", "sum"))
        )
        grup["qtde"] = grup["qtde"].astype(float)
        grup["valor"] = grup["valor"].astype(float)

        g1, g2 = st.columns(2)
        with g1:
            fig1 = px.bar(
                grup,
                x="ano_mes",
                y="valor",
                title="Valor vendido por mês",
                labels={"ano_mes": "Ano-Mês", "valor": "R$"},
            )
            st.plotly_chart(fig1, use_container_width=True)
        with g2:
            fig2 = px.line(
                grup,
                x="ano_mes",
                y="qtde",
                markers=True,
                title="Unidades vendidas por mês",
                labels={"ano_mes": "Ano-Mês", "qtde": "Unid"},
            )
            st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Amostra de vendas")
    cols = [
        c
        for c in [
            "data",
            "marca",
            "grupo",
            "btu",
            "ciclo",
            "produto",
            "descricao",
            "qtde",
            "vl_custo",
            "vl_total",
        ]
        if c in df.columns
    ]
    sample = df[cols].head(200).copy()
    if "qtde" in sample.columns:
        sample["qtde"] = sample["qtde"].apply(fmt_qtde)
    if "vl_custo" in sample.columns:
        sample["vl_custo"] = sample["vl_custo"].apply(fmt_brl)
    if "vl_total" in sample.columns:
        sample["vl_total"] = sample["vl_total"].apply(fmt_brl)
    st.dataframe(sample, use_container_width=True, height=400)


def aba_cobertura(estoque_df, vendas_df):
    st.header("📊 Cobertura")
    st.info("Cobertura detalhada será implementada na próxima etapa.")


def aba_sugestao(estoque_df, vendas_df):
    st.header("🛒 Sugestão de Compra")
    st.info("Sugestão de compra será implementada na próxima etapa.")


def aba_fornecedores(estoque_df):
    st.header("🏭 Fornecedores")
    if estoque_df.empty:
        st.warning("Carregue o arquivo de estoque.")
        return
    if "marca" not in estoque_df.columns:
        st.info("Coluna de fabricante/marca não encontrada no estoque.")
        return
    df = estoque_df
    agg_dict = {"SKUs": ("produto", "nunique"), "Unidades": ("qtde", "sum")}
    if "vl_total" in df.columns:
        agg_dict["Valor"] = ("vl_total", "sum")
    resumo = (
        df.groupby("marca", as_index=False)
        .agg(**agg_dict)
        .sort_values("Valor" if "Valor" in agg_dict else "Unidades", ascending=False)
    )
    resumo["Unidades"] = resumo["Unidades"].apply(fmt_qtde)
    if "Valor" in resumo.columns:
        resumo["Valor_fmt"] = resumo["Valor"].apply(fmt_brl)
        cols_show = ["marca", "SKUs", "Unidades", "Valor_fmt"]
        rename_show = {"marca": "Fabricante", "Valor_fmt": "Valor (R$)"}
    else:
        cols_show = ["marca", "SKUs", "Unidades"]
        rename_show = {"marca": "Fabricante"}
    st.dataframe(
        resumo[cols_show].rename(columns=rename_show),
        use_container_width=True,
    )


# =========================================================
# MAIN
# =========================================================
def main():
    st.sidebar.markdown("### 📂 Dados")

    est_file = st.sidebar.file_uploader("Estoque (.xlsx)", type=["xlsx"], key="up_est")
    vnd_file = st.sidebar.file_uploader("Vendas (.csv)", type=["csv"], key="up_vnd")

    estoque_df = pd.DataFrame()
    vendas_df = pd.DataFrame()

    if est_file is not None:
        estoque_df = carregar_estoque(est_file)
        if not estoque_df.empty:
            st.sidebar.success(f"Estoque: {fmt_qtde(len(estoque_df))} produtos")
        else:
            st.sidebar.error("Estoque: 0 produtos")

    if vnd_file is not None:
        vendas_df = carregar_vendas(vnd_file)
        if not vendas_df.empty:
            st.sidebar.success(f"Vendas: {fmt_qtde(len(vendas_df))} registros")
        else:
            st.sidebar.error("Vendas: 0 registros")

    tabs = st.tabs(
        [
            "📦 Estoque & ABC",
            "📈 Vendas & Demanda",
            "📊 Cobertura",
            "🛒 Sugestão de Compra",
            "🏭 Fornecedores",
        ]
    )

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
