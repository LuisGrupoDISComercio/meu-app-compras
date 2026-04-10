import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import re
import io

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
    "TCL":     "images/pngtransparenttclhdlogo.png",
    "Grupo":   "images/DIS_NEW.jpg",
}

# ─────────────────────────────────────────────
# CARREGAR ESTOQUE
# ─────────────────────────────────────────────
@st.cache_data
def carregar_estoque(file) -> pd.DataFrame:
    try:
        file.seek(0)
        df = pd.read_excel(file, header=0)

        # Remove a primeira coluna Unnamed: 0, se existir
        if "Unnamed: 0" in df.columns:
            df = df.drop(columns=["Unnamed: 0"])

        # Garante apenas as 8 colunas principais, por posição
        df = df.iloc[:, :8]
        df.columns = [
            "fabr",          # Fabr
            "produto_id",    # Produto
            "descricao",     # Descrição
            "classe_abc",    # ABC
            "cubagem_un",    # Cubagem (Un)
            "qtde",          # Qtde
            "custo_unit",    # Custo Entrada Unitário Médio
            "custo_total",   # Custo Entrada Total
        ]

        # Remove linha TOTAL e linhas totalmente vazias
        df = df.dropna(how="all")
        df = df[~df["descricao"].astype(str).str.upper().eq("TOTAL")]

        # Converte numéricos
        df["fabr"]       = pd.to_numeric(df["fabr"], errors="coerce")
        df["produto_id"] = pd.to_numeric(df["produto_id"], errors="coerce")
        df["qtde"]       = pd.to_numeric(df["qtde"], errors="coerce").fillna(0)
        df["cubagem_un"] = pd.to_numeric(df["cubagem_un"], errors="coerce").fillna(0)
        df["custo_unit"] = pd.to_numeric(df["custo_unit"], errors="coerce").fillna(0)
        df["custo_total"]= pd.to_numeric(df["custo_total"], errors="coerce").fillna(0)

        # Remove fabricantes genéricos / danificados / semi etc.
        df = df.dropna(subset=["fabr"])
        df["fabr"] = df["fabr"].astype(int)
        df = df[~df["fabr"].isin(FABRICANTES_IGNORAR)]

        # Mapeia fabricante para nome
        df["fabricante_nome"] = df["fabr"].map(MAPA_FABRICANTES_ESTOQUE).fillna("Outros")
        df["fabricante_codigo"] = df["fabr"].apply(lambda x: f"{int(x):03d}")

        # Ajustes finais
        df["produto_id"] = df["produto_id"].astype("Int64")

        # Coluna auxiliar de valor total em estoque
        df["estoque_valor_total"] = df["custo_total"]

        return df

    except Exception as e:
        st.sidebar.error(f"Erro ao carregar estoque: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────
# CARREGAR VENDAS
# (mantendo a lógica que já funcionou pra você)
# ─────────────────────────────────────────────
@st.cache_data
def carregar_vendas(file) -> pd.DataFrame:
    try:
        content = file.read()
        for enc in ["utf-8-sig", "latin-1", "cp1252"]:
            try:
                text = content.decode(enc)
                break
            except Exception:
                continue
        else:
            text = content.decode("latin-1")

        linhas = [l for l in text.splitlines() if l.strip()]
        if not linhas:
            raise ValueError("Arquivo de vendas vazio.")

        header = linhas[0].split(";")
        dados = [l.split(";") for l in linhas[1:]]

        colunas = [
            "emissao_nf",  # data
            "marca",
            "grupo",
            "btu",
            "ciclo",
            "produto_id",
            "descricao",
            "qtde",
            "valor_bruto",
        ]

        rows = []
        for row in dados:
            if len(row) < 9:
                continue
            rows.append(row[:9])

        df = pd.DataFrame(rows, columns=colunas)

        # Filtra só linhas com data dd/mm/aaaa
        df = df[df["emissao_nf"].str.match(r"\d{2}/\d{2}/\d{4}", na=False)]

        df["data_emissao"] = pd.to_datetime(df["emissao_nf"], format="%d/%m/%Y", errors="coerce")

        df["produto_id"] = pd.to_numeric(df["produto_id"], errors="coerce")
        df["qtde"] = pd.to_numeric(df["qtde"], errors="coerce").fillna(0)

        def limpar_valor(v):
            v = str(v)
            v = v.replace("R$", "").replace(".", "").replace(" ", "")
            v = v.replace(",", ".")
            try:
                return float(v)
            except ValueError:
                return 0.0

        df["valor_bruto"] = df["valor_bruto"].apply(limpar_valor)

        df = df.dropna(subset=["produto_id"])
        df["produto_id"] = df["produto_id"].astype("Int64")

        return df

    except Exception as e:
        st.sidebar.error(f"Erro ao carregar vendas: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────
# ABAS
# ─────────────────────────────────────────────
def aba_estoque(df: pd.DataFrame):
    st.markdown("## Estoque & ABC")

    if df.empty:
        st.info("Carregue o arquivo de estoque.")
        return

    linhas = len(df)
    skus   = df["produto_id"].nunique()
    valor  = df["estoque_valor_total"].sum()
    volume = df["cubagem_un"].sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Linhas de estoque", f"{linhas}")
    c2.metric("SKUs distintos", f"{skus}")
    c3.metric("Valor total em estoque", f"R$ {valor:,.0f}".replace(",", "X").replace(".", ",").replace("X", "."))
    c4.metric("Volume total (m³)", f"{volume:,.1f}".replace(",", "X").replace(".", ",").replace("X", "."))

    st.markdown("### Tabela de estoque (amostra)")
    st.dataframe(
        df[
            [
                "fabricante_codigo",
                "fabricante_nome",
                "produto_id",
                "descricao",
                "classe_abc",
                "cubagem_un",
                "qtde",
                "custo_unit",
                "custo_total",
            ]
        ].sort_values(["fabricante_nome", "produto_id"]),
        use_container_width=True,
    )


def aba_vendas(df: pd.DataFrame):
    st.markdown("## Vendas & Demanda")
    if df.empty:
        st.info("Carregue o arquivo de vendas.")
        return

    st.write(f"Registros de vendas: {len(df):,}".replace(",", "."))

    st.dataframe(
        df[["data_emissao", "marca", "grupo", "btu", "ciclo", "produto_id", "descricao", "qtde", "valor_bruto"]]
        .sort_values("data_emissao", ascending=False),
        use_container_width=True,
    )


def aba_cobertura(estoque_df: pd.DataFrame, vendas_df: pd.DataFrame):
    st.markdown("## Cobertura")
    st.info("(cálculo detalhado de cobertura ainda não implementado nesta versão compacta)")


def aba_sugestao(estoque_df: pd.DataFrame, vendas_df: pd.DataFrame):
    st.markdown("## Sugestão de Compras")
    st.info("(sugestão automática de compras ainda não implementada nesta versão compacta)")


def aba_fornecedores(estoque_df: pd.DataFrame):
    st.markdown("## Fornecedores")
    if estoque_df.empty:
        st.info("Carregue o arquivo de estoque.")
        return

    por_fab = (
        estoque_df.groupby("fabricante_nome", as_index=False)["estoque_valor_total"].sum()
        .sort_values("estoque_valor_total", ascending=False)
    )

    fig = px.pie(
        por_fab,
        values="estoque_valor_total",
        names="fabricante_nome",
        title="Participação no valor de estoque por fabricante",
    )
    st.plotly_chart(fig, use_container_width=True)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    try:
        st.sidebar.image(LOGOS["Grupo"], use_container_width=True)
    except Exception:
        st.sidebar.title("Motor de Compras ❄️")

    st.sidebar.markdown("### Arquivos")
    estoque_file = st.sidebar.file_uploader("Estoque (.xlsx)", type=["xlsx"])
    vendas_file  = st.sidebar.file_uploader("Vendas (.csv)", type=["csv"])

    estoque_df = pd.DataFrame()
    vendas_df  = pd.DataFrame()

    if estoque_file is not None:
        estoque_df = carregar_estoque(estoque_file)
        st.sidebar.success(f"Estoque: {len(estoque_df)} linhas carregadas")

    if vendas_file is not None:
        vendas_df = carregar_vendas(vendas_file)
        st.sidebar.success(f"Vendas: {len(vendas_df):,} registros carregados".replace(",", "."))

    tabs = st.tabs(
        ["📦 Estoque & ABC", "📈 Vendas & Demanda", "📊 Cobertura", "🛒 Sugestão de Compras", "🏭 Fornecedores"]
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
