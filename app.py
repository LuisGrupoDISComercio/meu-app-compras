import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import io
import re

st.set_page_config(
    page_title="Motor de Compras — Ar Condicionado",
    page_icon="❄️",
    layout="wide"
)

# ─────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────
MAPA_FABRICANTES_ESTOQUE = {
    2:  "LG",
    3:  "Samsung",
    4:  "Springer Midea",
    5:  "Daikin",
    6:  "Agratto",
    7:  "Gree",
    10: "Trane",
    11: "TCL",
}
FABRICANTES_IGNORAR = {900, 995, 998, 999}

# ─────────────────────────────────────────────
# FUNÇÕES DE CARGA
# ─────────────────────────────────────────────
def carregar_estoque(file) -> pd.DataFrame:
    """
    Lê o Estoque.xlsx que você mandou:
    Colunas: Fabr | Produto | Descrição | ABC | Cubagem (Un) | Qtde | Custo Entrada Unitário Médio | Custo Entrada Total
    """
    # garante que podemos ler mais de uma vez
    if hasattr(file, "seek"):
        file.seek(0)

    df_raw = pd.read_excel(file, header=0)

    # Mantém só as 8 primeiras colunas, na ordem
    df = df_raw.iloc[:, :8].copy()
    df.columns = [
        "Fabr",
        "Produto",
        "Descricao",
        "ABC",
        "Cubagem_Un",
        "Qtde",
        "Custo_Entrada_Unitario_Medio",
        "Custo_Entrada_Total",
    ]

    # remove linha TOTAL (última linha do relatório)
    df = df[~df["ABC"].astype(str).str.upper().eq("TOTAL")].copy()

    # remove linhas totalmente vazias
    df = df.dropna(how="all")

    # converte tipos numéricos
    for col in ["Fabr", "Produto"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in ["Cubagem_Un", "Qtde", "Custo_Entrada_Unitario_Medio", "Custo_Entrada_Total"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # renomeia para nomes internos usados depois
    df = df.rename(columns={
        "Fabr":  "fabricante_id",
        "Produto": "produto_id",
        "Descricao": "descricao",
        "ABC": "classe_abc",
        "Cubagem_Un": "volume",
        "Qtde": "qtde",
        "Custo_Entrada_Unitario_Medio": "custo_unit",
        "Custo_Entrada_Total": "custo_total",
    })

    # remove fabricantes que não interessam
    df = df[~df["fabricante_id"].isin(FABRICANTES_IGNORAR)].copy()

    # adiciona nome do fabricante mapeado
    df["fabricante"] = df["fabricante_id"].map(MAPA_FABRICANTES_ESTOQUE).fillna("Outros")

    return df


def detectar_delimitador(sample: str) -> str:
    # heurística simples para CSV de vendas
    if sample.count(";") > sample.count(","):
        return ";"
    return ","


def carregar_vendas(file) -> pd.DataFrame:
    """
    Lê o Vendas.csv. Vamos só garantir:
    - tentativa com ; e , como separador
    - coluna de data convertida
    """
    if hasattr(file, "seek"):
        file.seek(0)
    raw = file.read()
    if isinstance(raw, bytes):
        raw_str = raw.decode("utf-8", errors="replace")
    else:
        raw_str = raw

    # volta o ponteiro para reler via StringIO
    buffer = io.StringIO(raw_str)

    sep = detectar_delimitador(raw_str.splitlines()[0])
    df = pd.read_csv(buffer, sep=sep)

    # tenta encontrar uma coluna de data
    col_data = None
    for c in df.columns:
        if str(c).lower() in ["data", "data_emissao", "emissao"]:
            col_data = c
            break
    if col_data is not None:
        df["data_emissao"] = pd.to_datetime(df[col_data], errors="coerce", dayfirst=True)

    # tenta achar produto
    for c in df.columns:
        if "produto" in str(c).lower() and "id" in str(c).lower():
            df = df.rename(columns={c: "produto_id"})
        if "quant" in str(c).lower():
            df = df.rename(columns={c: "qtde"})

    return df


# ─────────────────────────────────────────────
# ABAS
# ─────────────────────────────────────────────
def aba_estoque(estoque_df: pd.DataFrame):
    st.header("📦 Estoque & ABC")

    st.write(f"{len(estoque_df):,} linhas de estoque carregadas.")

    st.subheader("Prévia do estoque")
    st.dataframe(estoque_df.head(50), use_container_width=True)

    # Estoque por fabricante (resumo simples)
    st.subheader("Estoque por fabricante (R$)")
    resumo = (
        estoque_df
        .groupby("fabricante", as_index=False)["custo_total"]
        .sum()
        .sort_values("custo_total", ascending=False)
    )
    resumo["Valor_R"] = resumo["custo_total"]

    col_tabela, col_pizza = st.columns(2)
    with col_tabela:
        st.dataframe(
            resumo[["fabricante", "Valor_R"]],
            use_container_width=True,
            hide_index=True
        )
    with col_pizza:
        fig = px.pie(
            resumo,
            names="fabricante",
            values="Valor_R",
            title="Participação no valor de estoque"
        )
        st.plotly_chart(fig, use_container_width=True)


def aba_vendas(vendas_df: pd.DataFrame):
    st.header("📈 Vendas & Demanda")

    st.write(f"{len(vendas_df):,} registros de vendas carregados.")

    st.subheader("Prévia das vendas")
    st.dataframe(vendas_df.head(50), use_container_width=True)

    if "data_emissao" in vendas_df.columns:
        st.subheader("Vendas ao longo do tempo (contagem de registros)")
        tmp = (
            vendas_df
            .dropna(subset=["data_emissao"])
            .assign(data=vendas_df["data_emissao"].dt.date)
            .groupby("data", as_index=False)
            .size()
        )
        fig = px.line(tmp, x="data", y="size", title="Registros de venda por dia")
        st.plotly_chart(fig, use_container_width=True)


def aba_cobertura(estoque_df, vendas_df):
    st.header("📊 Cobertura")
    st.info("Vamos implementar a cobertura depois que a carga estiver 100% estável.")


def aba_sugestao(estoque_df, vendas_df):
    st.header("🛒 Sugestão de Compras")
    st.info("Sugestão de compras será calculada depois que validarmos estoque e vendas.")


def aba_fornecedores(estoque_df):
    st.header("🏭 Fornecedores")
    st.info("Análise de fornecedores será implementada na próxima etapa.")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    st.title("❄️ Motor de Compras — Ar Condicionado")

    with st.sidebar:
        st.header("📂 Arquivos")
        file_estoque = st.file_uploader("Estoque (.xlsx)", type=["xlsx"])
        file_vendas  = st.file_uploader("Vendas (.csv)", type=["csv"])

    estoque_df = pd.DataFrame()
    vendas_df  = pd.DataFrame()

    if file_estoque:
        try:
            estoque_df = carregar_estoque(file_estoque)
            st.sidebar.success(f"Estoque: {len(estoque_df):,} produtos carregados")
        except Exception as e:
            st.sidebar.error(f"Erro ao carregar estoque: {e}")

    if file_vendas:
        try:
            # importante: voltar o ponteiro antes de reler
            file_vendas.seek(0)
            vendas_df = carregar_vendas(file_vendas)
            st.sidebar.success(f"Vendas: {len(vendas_df):,} registros carregados")
        except Exception as e:
            st.sidebar.error(f"Erro ao carregar vendas: {e}")

    tabs = st.tabs([
        "📦 Estoque & ABC",
        "📈 Vendas & Demanda",
        "📊 Cobertura",
        "🛒 Sugestão de Compras",
        "🏭 Fornecedores"
    ])

    with tabs[0]:
        if not estoque_df.empty:
            aba_estoque(estoque_df)
        else:
            st.info("Carregue o arquivo de estoque.")

    with tabs[1]:
        if not vendas_df.empty:
            aba_vendas(vendas_df)
        else:
            st.info("Carregue o arquivo de vendas.")

    with tabs[2]:
        aba_cobertura(estoque_df, vendas_df)

    with tabs[3]:
        aba_sugestao(estoque_df, vendas_df)

    with tabs[4]:
        aba_fornecedores(estoque_df)


if __name__ == "__main__":
    main()
