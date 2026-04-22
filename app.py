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
# CARREGAMENTO ESTOQUE
# =========================================================
def carregar_estoque(file):
    """
    Lê exatamente o layout do Estoque.xlsx (aba RelEstoqueVenda)
    e prepara para uso no app.
    """
    try:
        df_raw = pd.read_excel(file, sheet_name="RelEstoqueVenda", header=0)

        # Renomear colunas para nomes internos fixos
        rename_map = {
            "Fabr": "fabr",
            "Produto": "produto",
            "Descrição": "descricao",
            "ABC": "curva_sistema",
            "Cubagem (Un)": "cubagem_un",
            "Qtde": "qtde",
            "Custo Entrada Unitário Médio": "custo_unit",
            "Custo Entrada Total": "vl_total",
        }
        df = df_raw.rename(columns=rename_map)

        # Remover linhas totalmente vazias
        df = df.dropna(how="all")

        # Remover linha TOTAL (descricao == 'TOTAL' ou produto NaN)
        df = df[~df["descricao"].astype(str).str.upper().eq("TOTAL")]
        df = df[~df["produto"].isna()]

        # Excluir fabricantes auxiliares (900, 995, 998, 999)
        df["fabr"] = pd.to_numeric(df["fabr"], errors="coerce").astype("Int64")
        df = df[~df["fabr"].isin(FABRICANTES_IGNORAR)]

        # Tipos numéricos
        df["produto"] = pd.to_numeric(df["produto"], errors="coerce").astype("Int64")
        df["qtde"] = pd.to_numeric(df["qtde"], errors="coerce").fillna(0)
        df["vl_total"] = pd.to_numeric(df["vl_total"], errors="coerce").fillna(0.0)

        # Marca / fabricante legível
        df["marca"] = df["fabr"].map(MAPA_FABRICANTES).fillna("Outros")

        # Garantir string em curva_sistema
        df["curva_sistema"] = df["curva_sistema"].astype(str).fillna("")

        return df

    except Exception as e:
        st.error(f"Erro ao carregar estoque: {e}")
        return pd.DataFrame()


# =========================================================
# CARREGAMENTO VENDAS
# =========================================================
def carregar_vendas(file):
    """
    CSV de vendas com pelo menos:
    - produto
    - data (ou dt_venda)
    - qtde
    """
    try:
        df = pd.read_csv(file, sep=";", decimal=",", encoding="utf-8")

        # Normalizar nomes de coluna prováveis
        cols_lower = {c.lower(): c for c in df.columns}
        col_prod = cols_lower.get("produto") or cols_lower.get("idproduto") or list(df.columns)[0]
        col_qtde = cols_lower.get("qtde") or cols_lower.get("quantidade") or list(df.columns)[1]

        # tenta achar coluna de data
        col_data = None
        for key in ["data", "dt_venda", "data_venda", "emissao"]:
            if key in cols_lower:
                col_data = cols_lower[key]
                break

        df = df.rename(
            columns={
                col_prod: "produto",
                col_qtde: "qtde",
                **({col_data: "data"} if col_data else {}),
            }
        )

        df["produto"] = pd.to_numeric(df["produto"], errors="coerce").astype("Int64")
        df["qtde"] = pd.to_numeric(df["qtde"], errors="coerce").fillna(0)

        if "data" in df.columns:
            df["data"] = pd.to_datetime(df["data"], errors="coerce")
            df = df.dropna(subset=["data"])

        # descarta linhas sem produto
        df = df.dropna(subset=["produto"])

        return df

    except Exception as e:
        st.error(f"Erro ao carregar vendas: {e}")
        return pd.DataFrame()


# =========================================================
# ESTATÍSTICA DE DEMANDA (BASE PARA COBERTURA/SUGESTÃO)
# =========================================================
def calcular_demanda_media(vendas_df):
    """
    Retorna dataframe com:
    - produto
    - qtde_vendida
    - dias_periodo
    - media_dia
    """
    if vendas_df.empty or "data" not in vendas_df.columns:
        return pd.DataFrame()

    df = vendas_df.copy()

    # Período total em dias
    data_min = df["data"].min()
    data_max = df["data"].max()
    dias_periodo = max((data_max - data_min).days + 1, 1)

    agrupado = (
        df.groupby("produto")["qtde"]
        .sum()
        .reset_index()
        .rename(columns={"qtde": "qtde_vendida"})
    )

    agrupado["dias_periodo"] = dias_periodo
    agrupado["media_dia"] = agrupado["qtde_vendida"] / dias_periodo

    return agrupado


# =========================================================
# ABA ESTOQUE & ABC
# =========================================================
def aba_estoque(estoque_df, vendas_df):
    st.header("📦 Estoque & ABC")

    if estoque_df.empty:
        st.warning("Carregue o arquivo de estoque na barra lateral.")
        return

    df = estoque_df.copy()

    # KPIs principais
    skus = df["produto"].nunique()
    qtde_total = df["qtde"].sum()
    vl_total = df["vl_total"].sum()

    c1, c2, c3 = st.columns(3)
    c1.metric("SKUs em estoque", fmt_qtde(skus))
    c2.metric("Qtd total em estoque", fmt_qtde(qtde_total))
    c3.metric("Valor total em estoque", fmt_brl(vl_total))

    st.markdown("---")

    # Filtros
    st.subheader("Detalhe por produto")

    col1, col2 = st.columns([2, 3])

    with col1:
        fabricantes = sorted(df["fabr"].dropna().unique())
        fab_sel = st.multiselect(
            "Filtrar por fabricante (código):",
            options=fabricantes,
            default=fabricantes,
        )

    with col2:
        curvas = sorted(df["curva_sistema"].dropna().unique())
        curva_sel = st.multiselect(
            "Filtrar por Curva Sistema:",
            options=curvas,
            default=curvas,
        )

    df_f = df[
        df["fabr"].isin(fab_sel)
        & df["curva_sistema"].isin(curva_sel)
    ].copy()

    df_f["vl_total_fmt"] = df_f["vl_total"].apply(fmt_brl)

    df_view = df_f[
        [
            "fabr",
            "produto",
            "descricao",
            "curva_sistema",
            "qtde",
            "vl_total_fmt",
        ]
    ].rename(
        columns={
            "fabr": "Fabr",
            "produto": "Produto",
            "descricao": "Descrição",
            "curva_sistema": "Curva Sistema",
            "qtde": "Qtde",
            "vl_total_fmt": "Custo Entrada Total",
        }
    )

    st.dataframe(df_view, use_container_width=True, height=520)


# =========================================================
# ABA VENDAS & DEMANDA
# =========================================================
def aba_vendas(vendas_df):
    st.header("📈 Vendas & Demanda")

    if vendas_df.empty:
        st.warning("Carregue o arquivo de vendas na barra lateral.")
        return

    df = vendas_df.copy()

    st.caption(
        f"Período disponível: {df['data'].min().date()} até {df['data'].max().date()} "
        f"({len(df):,} registros)".replace(",", ".")
        if "data" in df.columns
        else f"{len(df):,} registros de vendas".replace(",", ".")
    )

    # Evolução mensal (se tiver data)
    if "data" in df.columns:
        df["ano_mes"] = df["data"].dt.to_period("M").astype(str)
        mensal = (
            df.groupby("ano_mes")["qtde"]
            .sum()
            .reset_index()
            .rename(columns={"ano_mes": "Mês", "qtde": "Qtde Vendida"})
        )
        mensal["Qtde Vendida"] = mensal["Qtde Vendida"].astype(float)

        fig = px.bar(
            mensal,
            x="Mês",
            y="Qtde Vendida",
            title="Vendas Mensais (Qtde)",
        )
        st.plotly_chart(fig, use_container_width=True)

    # Top 20 produtos
    top = (
        df.groupby("produto")["qtde"]
        .sum()
        .reset_index()
        .sort_values("qtde", ascending=False)
        .head(20)
    )
    top["qtde"] = top["qtde"].astype(float)
    fig2 = px.bar(
        top,
        x="produto",
        y="qtde",
        title="Top 20 Produtos Mais Vendidos (Qtde)",
    )
    st.plotly_chart(fig2, use_container_width=True)


# =========================================================
# ABA COBERTURA
# =========================================================
def aba_cobertura(estoque_df, vendas_df):
    st.header("📊 Cobertura")

    if estoque_df.empty:
        st.warning("Carregue o arquivo de estoque.")
        return
    if vendas_df.empty or "data" not in vendas_df.columns:
        st.warning("Carregue o arquivo de vendas com coluna de data para calcular cobertura.")
        return

    df_estoque = estoque_df.copy()
    demanda = calcular_demanda_media(vendas_df)

    if demanda.empty:
        st.warning("Não foi possível calcular a demanda média. Verifique o arquivo de vendas.")
        return

    # Join estoque x demanda
    base = df_estoque.merge(demanda, on="produto", how="left")

    base["media_dia"] = base["media_dia"].fillna(0)

    # Cobertura em dias
    base["cobertura_dias"] = np.where(
        base["media_dia"] > 0,
        base["qtde"] / base["media_dia"],
        np.inf,
    )

    # Filtro: foco em itens com venda
    mostrar_so_com_venda = st.checkbox(
        "Mostrar apenas itens com vendas no período", value=True
    )
    if mostrar_so_com_venda:
        base = base[base["media_dia"] > 0]

    # Tabela
    base["vl_total_fmt"] = base["vl_total"].apply(fmt_brl)
    base["media_dia_fmt"] = base["media_dia"].round(2)
    base["cobertura_dias_fmt"] = base["cobertura_dias"].replace(np.inf, np.nan).round(1)

    df_view = base[
        [
            "fabr",
            "produto",
            "descricao",
            "curva_sistema",
            "qtde",
            "vl_total_fmt",
            "qtde_vendida",
            "media_dia_fmt",
            "cobertura_dias_fmt",
        ]
    ].rename(
        columns={
            "fabr": "Fabr",
            "produto": "Produto",
            "descricao": "Descrição",
            "curva_sistema": "Curva Sistema",
            "qtde": "Qtde Estoque",
            "vl_total_fmt": "Custo Entrada Total",
            "qtde_vendida": "Qtde Vendida (período)",
            "media_dia_fmt": "Média Diária",
            "cobertura_dias_fmt": "Cobertura (dias)",
        }
    )

    st.dataframe(df_view, use_container_width=True, height=600)


# =========================================================
# ABA SUGESTÃO DE COMPRA
# =========================================================
def aba_sugestao(estoque_df, vendas_df):
    st.header("🛒 Sugestão de Compra")

    if estoque_df.empty:
        st.warning("Carregue o arquivo de estoque.")
        return
    if vendas_df.empty or "data" not in vendas_df.columns:
        st.warning("Carregue o arquivo de vendas com coluna de data para sugerir compras.")
        return

    df_estoque = estoque_df.copy()
    demanda = calcular_demanda_media(vendas_df)

    if demanda.empty:
        st.warning("Não foi possível calcular a demanda média. Verifique o arquivo de vendas.")
        return

    # Parâmetros
    col1, col2 = st.columns(2)
    with col1:
        dias_alvo = st.number_input(
            "Estoque alvo (em dias de cobertura)",
            min_value=1,
            max_value=365,
            value=30,
            step=1,
        )
    with col2:
        curva_prioritaria = st.multiselect(
            "Priorizar Curvas (Sistema)",
            options=sorted(df_estoque["curva_sistema"].dropna().unique()),
            default=["A", "AA", "AB", "B", "BB"] if "A" in df_estoque["curva_sistema"].values else None,
        )

    # Join
    base = df_estoque.merge(demanda, on="produto", how="left")
    base["media_dia"] = base["media_dia"].fillna(0)

    # Estoque alvo e sugestão
    base["estoque_alvo"] = base["media_dia"] * dias_alvo
    base["sugestao_qtde"] = (base["estoque_alvo"] - base["qtde"]).clip(lower=0)
    base["sugestao_qtde"] = base["sugestao_qtde"].round(0)

    # Valor sugerido
    custo_medio_unit = np.where(
        base["qtde"] > 0,
        base["vl_total"] / base["qtde"],
        np.nan,
    )
    base["vl_sugestao"] = base["sugestao_qtde"] * custo_medio_unit
    base["vl_sugestao"] = base["vl_sugestao"].fillna(0)

    # Filtrar apenas itens com sugestão > 0
    base = base[base["sugestao_qtde"] > 0]

    # Ordenação: curva prioritaria + maior valor sugerido
    if curva_prioritaria:
        base["prioridade_curva"] = base["curva_sistema"].apply(
            lambda c: 0 if c in curva_prioritaria else 1
        )
    else:
        base["prioridade_curva"] = 1

    base = base.sort_values(["prioridade_curva", "vl_sugestao"], ascending=[True, False])

    # KPIs
    total_itens = len(base)
    valor_total_sug = base["vl_sugestao"].sum()

    c1, c2 = st.columns(2)
    c1.metric("Itens com sugestão de compra", fmt_qtde(total_itens))
    c2.metric("Valor total sugerido", fmt_brl(valor_total_sug))

    # Tabela
    base["vl_total_fmt"] = base["vl_total"].apply(fmt_brl)
    base["vl_sugestao_fmt"] = base["vl_sugestao"].apply(fmt_brl)

    df_view = base[
        [
            "fabr",
            "produto",
            "descricao",
            "curva_sistema",
            "qtde",
            "vl_total_fmt",
            "media_dia",
            "estoque_alvo",
            "sugestao_qtde",
            "vl_sugestao_fmt",
        ]
    ].rename(
        columns={
            "fabr": "Fabr",
            "produto": "Produto",
            "descricao": "Descrição",
            "curva_sistema": "Curva Sistema",
            "qtde": "Qtde Estoque",
            "vl_total_fmt": "Custo Entrada Total",
            "media_dia": "Média Diária",
            "estoque_alvo": "Estoque Alvo (unid.)",
            "sugestao_qtde": "Sugestão (unid.)",
            "vl_sugestao_fmt": "Valor Sugestão",
        }
    )

    st.dataframe(df_view, use_container_width=True, height=600)


# =========================================================
# ABA FORNECEDORES (placeholder simples)
# =========================================================
def aba_fornecedores(estoque_df):
    st.header("🏭 Fornecedores")

    if estoque_df.empty:
        st.warning("Carregue o arquivo de estoque.")
        return

    df = estoque_df.copy()

    por_marca = (
        df.groupby(["fabr", "marca"])
        .agg(
            skus=("produto", "nunique"),
            qtde_total=("qtde", "sum"),
            valor_total=("vl_total", "sum"),
        )
        .reset_index()
    )

    por_marca["valor_total_fmt"] = por_marca["valor_total"].apply(fmt_brl)
    por_marca["qtde_total_fmt"] = por_marca["qtde_total"].apply(fmt_qtde)

    st.dataframe(
        por_marca.rename(
            columns={
                "fabr": "Código",
                "marca": "Fabricante",
                "skus": "SKUs",
                "qtde_total_fmt": "Qtde Total",
                "valor_total_fmt": "Valor Total",
            }
        )[["Código", "Fabricante", "SKUs", "Qtde Total", "Valor Total"]],
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
