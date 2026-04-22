import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

st.set_page_config(
    page_title="Motor de Compras — Ar Condicionado",
    page_icon="❄️",
    layout="wide",
)

# -------------------------------------------------------------------
# CONSTANTES
# -------------------------------------------------------------------
FABRICANTES_IGNORAR = {900, 995, 998, 999}

# -------------------------------------------------------------------
# FORMATAÇÃO
# -------------------------------------------------------------------
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
    bg, fg = cores.get(primeira, ("#cccccc", "#000000"))
    return (
        f"background-color: {bg}; "
        f"color: {fg}; font-weight: bold; text-align: center;"
    )

# -------------------------------------------------------------------
# CARREGAMENTO DO ESTOQUE
# -------------------------------------------------------------------
def carregar_estoque(file) -> pd.DataFrame:
    """
    Carrega o Estoque.xlsx no layout específico que você enviou.

    Colunas originais:
    - Fabr
    - Produto
    - Descrição
    - ABC
    - Cubagem (Un)
    - Qtde
    - Custo Entrada Unitário Médio
    - Custo Entrada Total
    """
    try:
        # Se o arquivo tiver várias abas, tenta achar "RelEstoqueVenda".
        try:
            df = pd.read_excel(file, sheet_name="RelEstoqueVenda", header=0)
        except Exception:
            df = pd.read_excel(file, header=0)

        # Renomeia colunas exatamente
        rename_map = {
            "Fabr": "fabr",
            "Produto": "produto",
            "Descrição": "descricao",
            "ABC": "curva_sistema",
            "Cubagem (Un)": "cubagem",
            "Qtde": "qtde",
            "Custo Entrada Unitário Médio": "vl_unit",
            "Custo Entrada Total": "vl_total",
        }
        df = df.rename(columns=rename_map)

        # Garante existência de colunas obrigatórias
        obrigatorias = ["fabr", "produto", "descricao", "qtde", "vl_total"]
        faltando = [c for c in obrigatorias if c not in df.columns]
        if faltando:
            raise ValueError(f"[fabr, 'produto']")

        # Remove linha TOTAL (na amostra: produto NaN e descricao == 'TOTAL')
        df = df[~df["descricao"].astype(str).str.upper().eq("TOTAL")]
        # Remove linhas totalmente vazias
        df = df.dropna(how="all")

        # Converte tipos
        df["fabr"] = pd.to_numeric(df["fabr"], errors="coerce").astype("Int64")
        df["produto"] = pd.to_numeric(df["produto"], errors="coerce").astype("Int64")
        df["qtde"] = pd.to_numeric(df["qtde"], errors="coerce").fillna(0).astype(float)
        df["vl_total"] = pd.to_numeric(df["vl_total"], errors="coerce").fillna(0.0)

        # Remove fabricantes a ignorar (900, 995, 998, 999)
        mask_valid_fabr = ~df["fabr"].isin(list(FABRICANTES_IGNORAR))
        df = df[mask_valid_fabr]

        # Remove linhas sem produto
        df = df.dropna(subset=["produto"])

        df["descricao"] = df["descricao"].astype(str)
        if "curva_sistema" in df.columns:
            df["curva_sistema"] = df["curva_sistema"].astype(str)

        df = df.reset_index(drop=True)
        return df

    except Exception as e:
        st.sidebar.error(f"Erro ao carregar estoque: {e}")
        return pd.DataFrame()

# -------------------------------------------------------------------
# ABA ESTOQUE & ABC
# -------------------------------------------------------------------
def aba_estoque(estoque_df: pd.DataFrame):
    st.header("📦 Estoque & ABC")

    if estoque_df.empty:
        st.warning("Carregue o arquivo de estoque na barra lateral.")
        return

    df = estoque_df.copy()

    # SKUs
    skus = df["produto"].nunique()

    # Quantidade total
    qtde_total = df["qtde"].sum()

    # Valor total em estoque (R$)
    # -> soma direta de vl_total, pois já vem como total por linha
    vl_total_sum = df["vl_total"].sum()

    col1, col2, col3 = st.columns(3)
    col1.metric("SKUs em estoque", fmt_qtde(skus))
    col2.metric("Qtd total em estoque", fmt_qtde(qtde_total))
    col3.metric("Valor total em estoque", fmt_brl(vl_total_sum))

    st.markdown("---")

    st.subheader("Detalhe por produto")

    col_fabr, col_curva = st.columns(2)
    fabrs_unicos = df["fabr"].dropna().unique()
    fabrs_unicos = sorted(list(fabrs_unicos))

    fabr_sel = col_fabr.multiselect(
        "Filtrar por fabricante (código):",
        options=fabrs_unicos,
        default=fabrs_unicos,
    )

    curva_opts = sorted(df["curva_sistema"].dropna().unique())
    curva_sel = col_curva.multiselect(
        "Filtrar por Curva Sistema:",
        options=curva_opts,
        default=curva_opts,
    )

    if fabr_sel:
        df = df[df["fabr"].isin(fabr_sel)]
    if curva_sel:
        df = df[df["curva_sistema"].isin(curva_sel)]

    df_view = df[["fabr", "produto", "descricao", "curva_sistema", "qtde", "vl_total"]].copy()
    df_view = df_view.sort_values(["fabr", "produto"])

    df_view["qtde"] = df_view["qtde"].astype(float)
    df_view["vl_total"] = df_view["vl_total"].astype(float)

    df_view_ren = df_view.rename(
        columns={
            "fabr": "Fabr",
            "produto": "Produto",
            "descricao": "Descrição",
            "curva_sistema": "Curva Sistema",
            "qtde": "Qtde",
            "vl_total": "Custo Entrada Total",
        }
    )

    styler = df_view_ren.style.format(
        {
            "Qtde": lambda v: fmt_qtde(v),
            "Custo Entrada Total": lambda v: fmt_brl(v),
        }
    )

    styler = styler.map(colorir_abc, subset=["Curva Sistema"])

    st.dataframe(styler, use_container_width=True, height=500)

# -------------------------------------------------------------------
# ABAS PLACEHOLDER
# -------------------------------------------------------------------
def carregar_vendas(file) -> pd.DataFrame:
    try:
        return pd.read_csv(file, sep=";", encoding="utf-8")
    except Exception:
        return pd.DataFrame()

def aba_vendas(vendas_df: pd.DataFrame):
    st.header("📈 Vendas & Demanda")
    st.info("Placeholder. Foco atual está na aba Estoque & ABC.")

def aba_cobertura(estoque_df: pd.DataFrame, vendas_df: pd.DataFrame):
    st.header("📊 Cobertura")
    st.info("Placeholder. Lógica será conectada depois que o estoque estiver 100% ok.")

def aba_sugestao(estoque_df: pd.DataFrame, vendas_df: pd.DataFrame):
    st.header("🛒 Sugestão de Compra")
    st.info("Placeholder. Lógica será conectada depois que o estoque estiver 100% ok.")

def aba_fornecedores(estoque_df: pd.DataFrame):
    st.header("🏭 Fornecedores")
    st.info("Placeholder. Foco atual está na aba Estoque & ABC.")

# -------------------------------------------------------------------
# MAIN
# -------------------------------------------------------------------
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
        aba_estoque(estoque_df)
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
