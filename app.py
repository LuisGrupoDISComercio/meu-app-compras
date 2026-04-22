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
# CONSTANTES
# =========================================================
FABRICANTES_IGNORAR = {900, 995, 998, 999}

MAPA_FABRICANTES = {
    2: "LG",
    3: "Samsung",
    4: "Midea",
    5: "Daikin",
    6: "Agratto",
    7: "Gree",
    10: "Trane",
    11: "TCL",
}

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
        "A": ("#1a6b1a", "#FFFFFF"),
        "B": ("#2980b9", "#FFFFFF"),
        "C": ("#e67e22", "#FFFFFF"),
        "S": ("#8e44ad", "#FFFFFF"),
        "X": ("#7f8c8d", "#FFFFFF"),
    }
    if not isinstance(classe, str):
        return ""
    primeira = classe[0].upper() if classe else ""
    cor = cores.get(primeira, ("#cccccc", "#000000"))
    return (
        f"background-color: {cor[0]}; color: {cor[1]}; "
        f"font-weight: bold; text-align: center;"
    )

# =========================================================
# CARREGAMENTO DE DADOS
# =========================================================
def carregar_estoque(file):
    """Lê exatamente o layout do Estoque.xlsx que você enviou."""
    try:
        df = pd.read_excel(file, sheet_name="RelEstoqueVenda", header=0)

        # Renomear colunas para nomes internos fixos
        df = df.rename(
            columns={
                "Fabr": "fabr",
                "Produto": "produto",
                "Descrição": "descricao",
                "ABC": "curva_sistema",
                "Cubagem (Un)": "cubagem_un",
                "Qtde": "qtde",
                "Custo Entrada Unitário Médio": "custo_unit_medio",
                "Custo Entrada Total": "vl_total",
            }
        )

        # Remover linha TOTAL (última, com descrição = TOTAL) e linhas totalmente vazias
        df = df.dropna(subset=["descricao"], how="all")
        df = df[df["descricao"].str.upper() != "TOTAL"]

        # Tipos
        df["fabr"] = pd.to_numeric(df["fabr"], errors="coerce").astype("Int64")
        df["produto"] = pd.to_numeric(df["produto"], errors="coerce").astype("Int64")
        df["qtde"] = pd.to_numeric(df["qtde"], errors="coerce").fillna(0).astype(float)
        df["vl_total"] = pd.to_numeric(df["vl_total"], errors="coerce").fillna(0.0)

        # Remover fabricantes de serviço/danificados
        df = df[~df["fabr"].isin(FABRICANTES_IGNORAR)]

        # Nome do fabricante
        df["fabricante_nome"] = df["fabr"].map(MAPA_FABRICANTES).fillna("Outro")

        return df.reset_index(drop=True)

    except Exception as e:
        st.error(f"Erro ao carregar estoque: {e}")
        return pd.DataFrame()


def carregar_vendas(file):
    try:
        df = pd.read_csv(file, sep=";", encoding="latin1")
        # ajuste mínimo – mantém sua estrutura original
        return df
    except Exception as e:
        st.error(f"Erro ao carregar vendas: {e}")
        return pd.DataFrame()

# =========================================================
# ABA ESTOQUE & ABC
# =========================================================
def aba_estoque(estoque_df: pd.DataFrame, vendas_df: pd.DataFrame):
    st.header("📦 Estoque & ABC")

    if estoque_df.empty:
        st.warning("Carregue o arquivo de estoque na barra lateral.")
        return

    df = estoque_df.copy()

    # KPI 1 – SKUs (linhas)
    skus = len(df)

    # KPI 2 – Qtde total
    qtde_total = df["qtde"].sum()

    # KPI 3 – Valor total (Custo Entrada Total)
    vl_total_sum = df["vl_total"].sum()

    col1, col2, col3 = st.columns(3)
    col1.metric("SKUs em estoque", fmt_qtde(skus))
    col2.metric("Qtd total em estoque", fmt_qtde(qtde_total))
    col3.metric("Valor total em estoque", fmt_brl(vl_total_sum))

    st.markdown("---")

    st.subheader("Detalhe por produto")

    # Filtros por fabricante (código) e curva do sistema
    fabricantes_unicos = sorted(df["fabr"].dropna().unique())
    curvas_unicas = sorted(df["curva_sistema"].dropna().unique())

    with st.expander("Filtros", expanded=True):
        c1, c2 = st.columns(2)

        fabs_sel = c1.multiselect(
            "Filtrar por fabricante (código):",
            options=fabricantes_unicos,
            default=fabricantes_unicos,
            format_func=lambda x: f"{x}",
        )

        curvas_sel = c2.multiselect(
            "Filtrar por Curva Sistema:",
            options=curvas_unicas,
            default=curvas_unicas,
        )

    if fabs_sel:
        df = df[df["fabr"].isin(fabs_sel)]
    if curvas_sel:
        df = df[df["curva_sistema"].isin(curvas_sel)]

    # Tabela final
    df_view = df[
        [
            "fabr",
            "produto",
            "descricao",
            "curva_sistema",
            "qtde",
            "vl_total",
        ]
    ].rename(
        columns={
            "fabr": "Fabr",
            "produto": "Produto",
            "descricao": "Descrição",
            "curva_sistema": "Curva Sistema",
            "qtde": "Qtde",
            "vl_total": "Custo Entrada Total",
        }
    )

    # Formatar valores
    df_view["Qtde"] = df_view["Qtde"].astype(float)
    df_view["Custo Entrada Total"] = df_view["Custo Entrada Total"].astype(float)

    df_view_style = df_view.style.map(
        colorir_abc, subset=["Curva Sistema"]
    )

    # Valor em R$ legível na tabela
    df_view_style = df_view_style.format(
        {
            "Qtde": lambda v: fmt_qtde(v),
            "Custo Entrada Total": lambda v: fmt_brl(v),
        }
    )

    st.dataframe(df_view_style, use_container_width=True, height=600)

# =========================================================
# ABAS AUXILIARES (mantidas simples para não mexer no restante)
# =========================================================
def aba_vendas(vendas_df: pd.DataFrame):
    st.header("📈 Vendas & Demanda")
    if vendas_df.empty:
        st.info("Carregue o arquivo de vendas na barra lateral.")
        return
    st.dataframe(vendas_df.head(100), use_container_width=True)


def aba_cobertura(estoque_df: pd.DataFrame, vendas_df: pd.DataFrame):
    st.header("📊 Cobertura")
    st.info("Lógica de cobertura mantida para próxima etapa, sem alterações.")


def aba_sugestao(estoque_df: pd.DataFrame, vendas_df: pd.DataFrame):
    st.header("🛒 Sugestão de Compra")
    st.info("Lógica de sugestão de compra mantida para próxima etapa, sem alterações.")


def aba_fornecedores(estoque_df: pd.DataFrame):
    st.header("🏭 Fornecedores")
    if estoque_df.empty:
        st.info("Carregue o arquivo de estoque na barra lateral.")
        return
    por_fabr = (
        estoque_df.groupby("fabr")
        .agg(
            skus=("produto", "nunique"),
            qtde_total=("qtde", "sum"),
            valor_total=("vl_total", "sum"),
        )
        .reset_index()
    )
    por_fabr["qtde_total"] = por_fabr["qtde_total"].apply(fmt_qtde)
    por_fabr["valor_total"] = por_fabr["valor_total"].apply(fmt_brl)
    st.dataframe(
        por_fabr.rename(
            columns={
                "fabr": "Fabricante (cód.)",
                "skus": "SKUs",
                "qtde_total": "Qtde Total",
                "valor_total": "Valor Total",
            }
        ),
        use_container_width=True,
    )

# =========================================================
# MAIN
# =========================================================
def main():
    st.title("🧊 Motor de Compras — Ar Condicionado")

    st.sidebar.header("📂 Arquivos")
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
