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
# FUNÇÕES AUXILIARES
# ─────────────────────────────────────────────
def fmt_brl(valor):
    try:
        return f"R$ {valor:_.2f}".replace(".", ",").replace("_", ".")
    except Exception:
        return valor


# ─────────────────────────────────────────────
# CARREGAMENTO DE DADOS
# ─────────────────────────────────────────────
@st.cache_data
def carregar_estoque(file_obj):
    """Lê o Estoque.xlsx a partir do próprio file-like do uploader (NÃO usar .read())."""
    try:
        # Usa o objeto de arquivo diretamente
        xls = pd.ExcelFile(file_obj)
        aba = xls.sheet_names[0]
        df_raw = xls.parse(aba, header=None)

        # Procura a linha do cabeçalho pela coluna "Produto"
        header_row = None
        for i, row in df_raw.iterrows():
            if row.astype(str).str.contains("Produto", case=False).any():
                header_row = i
                break

        if header_row is None:
            return pd.DataFrame()

        df = xls.parse(aba, header=header_row)
        df.columns = df.columns.str.strip()
        df = df.dropna(axis=1, how="all")

        # Normalização de nomes de colunas
        renomear = {}
        for col in df.columns:
            c = col.strip().lower()
            if "produto" in c and "descri" not in c:
                renomear[col] = "Produto"
            elif "descri" in c:
                renomear[col] = "Descricao"
            elif c.startswith("qtd") or c.startswith("qtde") or c.startswith("quant"):
                renomear[col] = "Qtde"
            elif "vl custo" in c or ("custo" in c and "ult" in c):
                renomear[col] = "VL Custo (Últ Entrada)"
            elif ("vl total" in c) or ("valor total" in c):
                renomear[col] = "VL Total"
            elif "grupo" in c:
                renomear[col] = "Grupo"
            elif "marca" in c or "fabricante" in c:
                renomear[col] = "Marca"
            elif "btu" in c:
                renomear[col] = "BTU"
            elif "ciclo" in c:
                renomear[col] = "Ciclo"

        df = df.rename(columns=renomear)

        colunas_obrigatorias = ["Produto", "Descricao", "Qtde"]
        if not all(c in df.columns for c in colunas_obrigatorias):
            return pd.DataFrame()

        # Garante tipos numéricos
        for col in ["Qtde", "VL Custo (Últ Entrada)", "VL Total"]:
            if col in df.columns:
                df[col] = (
                    df[col]
                    .astype(str)
                    .str.replace(".", "", regex=False)
                    .str.replace(",", ".", regex=False)
                )
                df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=["Produto", "Descricao"])
        df["Produto"] = df["Produto"].astype(str).str.strip()
        df["Descricao"] = df["Descricao"].astype(str).str.strip()

        if "VL Total" not in df.columns and "VL Custo (Últ Entrada)" in df.columns:
            df["VL Total"] = df["Qtde"].fillna(0) * df["VL Custo (Últ Entrada)"].fillna(0)

        # Marca/fabricante
        if "Marca" in df.columns:
            df["Marca"] = df["Marca"].astype(str).str.strip().str.upper()
        else:
            df["Marca"] = "DESCONHECIDO"

        return df

    except Exception as e:
        st.error(f"Erro ao carregar estoque: {e}")
        return pd.DataFrame()


@st.cache_data
def carregar_vendas(file_obj):
    """Lê o Vendas.csv, aceitando versões com e sem coluna Pedido."""
    try:
        # Aqui sim usamos o bytes, pois read_csv aceita objeto de arquivo ou bytes
        df = pd.read_csv(
            file_obj,
            sep=";",
            encoding="latin1",
            decimal=",",
            thousands=".",
        )

        df.columns = df.columns.str.strip()
        df = df.dropna(how="all")

        # Padroniza nomes
        renomear = {}
        for col in df.columns:
            c = col.strip().lower()
            if "emissao" in c:
                renomear[col] = "Emissao NF"
            elif c == "pedido":
                renomear[col] = "Pedido"
            elif "marca" in c:
                renomear[col] = "Marca"
            elif "grupo" in c:
                renomear[col] = "Grupo"
            elif "btu" in c:
                renomear[col] = "BTU"
            elif "ciclo" in c:
                renomear[col] = "Ciclo"
            elif "produto" in c and "descri" not in c:
                renomear[col] = "Produto"
            elif "descri" in c:
                renomear[col] = "Descricao"
            elif c.startswith("qtd") or c.startswith("qtde") or c.startswith("quant"):
                renomear[col] = "Qtde"
            elif "vl custo" in c or ("custo" in c and "ult" in c):
                renomear[col] = "VL Custo (Últ Entrada)"
            elif "vl total" in c:
                renomear[col] = "VL Total"

        df = df.rename(columns=renomear)

        # Emissao NF como data
        if "Emissao NF" in df.columns:
            df["Emissao NF"] = pd.to_datetime(df["Emissao NF"], dayfirst=True, errors="coerce")

        # Numéricos
        for col in ["Qtde", "VL Custo (Últ Entrada)", "VL Total"]:
            if col in df.columns:
                df[col] = (
                    df[col]
                    .astype(str)
                    .str.replace(".", "", regex=False)
                    .str.replace(",", ".", regex=False)
                )
                df[col] = pd.to_numeric(df[col], errors="coerce")

        df["Produto"] = df["Produto"].astype(str).str.strip()
        df["Descricao"] = df["Descricao"].astype(str).str.strip()
        if "Marca" in df.columns:
            df["Marca"] = df["Marca"].astype(str).str.strip().str.upper()

        return df

    except Exception as e:
        st.error(f"Erro ao carregar vendas: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────
# ABC IA
# ─────────────────────────────────────────────
def classificar_abc_ia(df_vendas_filtrado):
    if df_vendas_filtrado.empty:
        return pd.DataFrame()

    resumo = (
        df_vendas_filtrado
        .groupby("Produto", as_index=False)
        .agg({
            "Descricao": "first",
            "Marca": "first",
            "Grupo": "first",
            "BTU": "first",
            "Ciclo": "first",
            "Qtde": "sum",
            "VL Total": "sum",
        })
    )

    resumo = resumo.sort_values("Qtde", ascending=False)
    resumo["perc_acum_unid"] = resumo["Qtde"].cumsum() / resumo["Qtde"].sum() * 100

    def faixa_unid(p):
        if p <= 40:
            return "A+"
        elif p <= 70:
            return "A"
        elif p <= 90:
            return "B"
        elif p <= 100:
            return "C"
        return "X"

    resumo["ABC IA (Unid)"] = resumo["perc_acum_unid"].apply(faixa_unid)

    resumo = resumo.sort_values("VL Total", ascending=False)
    resumo["perc_acum_valor"] = resumo["VL Total"].cumsum() / resumo["VL Total"].sum() * 100

    def faixa_valor(p):
        if p <= 40:
            return "A+"
        elif p <= 70:
            return "A"
        elif p <= 90:
            return "B"
        elif p <= 100:
            return "C"
        return "X"

    resumo["ABC IA (R$)"] = resumo["perc_acum_valor"].apply(faixa_valor)

    return resumo


def colorir_abc(valor):
    cores = {
        "A+": "background-color: #b8860b; color: white;",
        "A":  "background-color: #ffd700; color: black;",
        "B":  "background-color: #ffa500; color: black;",
        "C":  "background-color: #fff176; color: black;",
        "X":  "background-color: #b0bec5; color: black;",
    }
    return cores.get(str(valor), "")


# ─────────────────────────────────────────────
# ABAS
# ─────────────────────────────────────────────
def aba_estoque(estoque_df, vendas_df):
    st.header("📦 Estoque & Classificação ABC IA")

    if estoque_df is None or estoque_df.empty:
        st.info("Carregue o arquivo de estoque para visualizar esta aba.")
        return

    # Filtros de período e marca usando as vendas
    if vendas_df is None or vendas_df.empty or "Emissao NF" not in vendas_df.columns:
        st.warning("Vendas não carregadas ou sem data de emissão. ABC IA por período não será aplicado.")
        vendas_filtradas = pd.DataFrame()
    else:
        col1, col2 = st.columns(2)
        with col1:
            data_min = vendas_df["Emissao NF"].min()
            data_max = vendas_df["Emissao NF"].max()
            periodo = st.date_input(
                "Período de análise (vendas)",
                value=(data_min, data_max),
                min_value=data_min,
                max_value=data_max,
                format="DD/MM/YYYY",
            )
            if isinstance(periodo, tuple):
                dt_ini, dt_fim = periodo
            else:
                dt_ini = data_min
                dt_fim = data_max

        with col2:
            marcas = sorted(vendas_df["Marca"].dropna().unique().tolist())
            marcas_sel = st.multiselect(
                "Marca (vendas) para cálculo de ABC IA",
                options=marcas,
                default=marcas,
            )

        vendas_filtradas = vendas_df[
            (vendas_df["Emissao NF"] >= pd.to_datetime(dt_ini)) &
            (vendas_df["Emissao NF"] <= pd.to_datetime(dt_fim))
        ]
        if marcas_sel:
            vendas_filtradas = vendas_filtradas[vendas_filtradas["Marca"].isin(marcas_sel)]

    # Calcula ABC IA com base nas vendas filtradas
    abc_df = classificar_abc_ia(vendas_filtradas)
    mapa_abc_unid = dict(zip(abc_df["Produto"], abc_df["ABC IA (Unid)"]))
    mapa_abc_valor = dict(zip(abc_df["Produto"], abc_df["ABC IA (R$)"]))

    estoque = estoque_df.copy()
    estoque["ABC IA (Unid)"] = estoque["Produto"].map(mapa_abc_unid).fillna("X")
    estoque["ABC IA (R$)"] = estoque["Produto"].map(mapa_abc_valor).fillna("X")

    # Resumo
    estoque["Qtde"] = pd.to_numeric(estoque["Qtde"], errors="coerce").fillna(0)
    if "VL Custo (Últ Entrada)" in estoque.columns:
        estoque["VL Custo (Últ Entrada)"] = pd.to_numeric(
            estoque["VL Custo (Últ Entrada)"], errors="coerce"
        ).fillna(0)
        estoque["VL Total"] = estoque["Qtde"] * estoque["VL Custo (Últ Entrada)"]
    elif "VL Total" in estoque.columns:
        estoque["VL Total"] = pd.to_numeric(estoque["VL Total"], errors="coerce").fillna(0)
    else:
        estoque["VL Total"] = 0

    total_unid = estoque["Qtde"].sum()
    total_valor = estoque["VL Total"].sum()

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Unidades em estoque", f"{int(total_unid):,}".replace(",", "."))
    with col2:
        st.metric("Valor total em estoque", fmt_brl(total_valor))

    # Tabela de estoque
    colunas_exibir = [
        "Produto", "Descricao", "Marca", "Grupo", "BTU", "Ciclo",
        "Qtde", "VL Custo (Últ Entrada)", "VL Total",
        "ABC IA (Unid)", "ABC IA (R$)",
    ]
    colunas_exibir = [c for c in colunas_exibir if c in estoque.columns]

    df_view = estoque[colunas_exibir].copy()
    if "VL Custo (Últ Entrada)" in df_view.columns:
        df_view["VL Custo (Últ Entrada)"] = df_view["VL Custo (Últ Entrada)"].apply(fmt_brl)
    if "VL Total" in df_view.columns:
        df_view["VL Total"] = df_view["VL Total"].apply(fmt_brl)

    st.subheader("Tabela de Estoque com ABC IA")
    st.dataframe(
        df_view.style.map(
            colorir_abc,
            subset=[c for c in ["ABC IA (Unid)", "ABC IA (R$)"] if c in df_view.columns],
        ),
        use_container_width=True,
        height=600,
    )


def aba_vendas(vendas_df):
    st.header("📈 Vendas & Demanda")
    if vendas_df is None or vendas_df.empty:
        st.info("Carregue o arquivo de vendas para visualizar esta aba.")
        return

    st.write(f"Total de registros de vendas: {len(vendas_df):,}".replace(",", "."))

    if "Emissao NF" in vendas_df.columns:
        vendas_df = vendas_df.sort_values("Emissao NF")
        fig = px.bar(
            vendas_df.groupby(vendas_df["Emissao NF"].dt.to_period("M"))["VL Total"].sum().reset_index(),
            x="Emissao NF",
            y="VL Total",
            title="Vendas por mês (R$)",
        )
        fig.update_traces(marker_color="#29b6f6")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Tabela bruta de vendas")
    df_view = vendas_df.copy()
    if "VL Custo (Últ Entrada)" in df_view.columns:
        df_view["VL Custo (Últ Entrada)"] = df_view["VL Custo (Últ Entrada)"].apply(fmt_brl)
    if "VL Total" in df_view.columns:
        df_view["VL Total"] = df_view["VL Total"].apply(fmt_brl)

    st.dataframe(df_view, use_container_width=True, height=600)


def aba_cobertura(estoque_df, vendas_df):
    st.header("📊 Cobertura")
    st.info("Lógica de cobertura ainda será detalhada nesta versão do app.")
    # Placeholder para futura implementação


def aba_sugestao(estoque_df, vendas_df):
    st.header("🛒 Sugestão de Compra")
    st.info("Módulo de sugestão de compras será implementado em seguida, após estabilizar Estoque & ABC.")


def aba_fornecedores(estoque_df):
    st.header("🏭 Fornecedores")
    st.info("Análise de fornecedores será acoplada após finalizarmos cobertura e sugestão de compras.")


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
            st.sidebar.success(f"✅ Vendas: {len(vendas_df):,} registros carregados".replace(",", "."))
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
