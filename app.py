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

# =========================================================
# CARREGAMENTO DE ESTOQUE (ESPECÍFICO PRO SEU LAYOUT)
# =========================================================
@st.cache_data
def carregar_estoque(file_obj):
    """
    Lê o Estoque.xlsx no formato conhecido do Protheus.
    Espera colunas como:
      - Produto
      - Descricao / Descrição
      - Grupo
      - BTU
      - Ciclo
      - Qtde
      - VL Custo (Últ Entrada)
      - VL Total  (opcional – calculo se faltar)
    """
    try:
        # Lê a primeira aba usando a primeira linha como cabeçalho
        df = pd.read_excel(file_obj, sheet_name=0, header=0, dtype=str)

        # Normaliza nomes
        df.columns = df.columns.astype(str).str.strip()

        rename = {}
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
            elif "vl custo" in lo or ("custo" in lo and "ult" in lo):
                rename[col] = "vl_custo"
            elif "vl total" in lo or "valor total" in lo:
                rename[col] = "vl_total"
            elif "marca" in lo or "fabricante" in lo:
                rename[col] = "marca"

        df = df.rename(columns=rename)

        # Verifica colunas essenciais
        obrig = ["produto", "qtde"]
        for c in obrig:
            if c not in df.columns:
                st.error(f"Estoque: coluna obrigatória '{c}' não encontrada.")
                return pd.DataFrame()

        # Converte numéricos
        for c in ["qtde", "vl_custo", "vl_total"]:
            if c in df.columns:
                df[c] = (
                    df[c].astype(str)
                    .str.replace(r"\.", "", regex=True)
                    .str.replace(",", ".", regex=False)
                )
                df[c] = pd.to_numeric(df[c], errors="coerce")

        # Calcula vl_total se não existir
        if "vl_total" not in df.columns and "vl_custo" in df.columns:
            df["vl_total"] = df["qtde"].fillna(0) * df["vl_custo"].fillna(0)

        # Limpa strings
        df["produto"] = df["produto"].astype(str).str.strip()
        if "descricao" in df.columns:
            df["descricao"] = df["descricao"].astype(str).str.strip()
        else:
            df["descricao"] = ""

        # Mantém apenas linhas com produto e qtde > 0
        df = df[df["produto"].notna()]
        df = df[df["qtde"].fillna(0) > 0]

        return df.reset_index(drop=True)

    except Exception as e:
        st.error(f"Erro ao carregar estoque: {e}")
        return pd.DataFrame()

# =========================================================
# CARREGAMENTO DE VENDAS (SEU VENDAS.CSV)
# =========================================================
@st.cache_data
def carregar_vendas(file_obj):
    """
    Lê Vendas.csv com separador ;, decimal ,.
    Aceita com ou sem coluna Pedido.
    """
    try:
        df = pd.read_csv(
            file_obj,
            sep=";",
            encoding="latin-1",
            dtype=str,
            skip_blank_lines=True,
        )
        df.columns = df.columns.astype(str).str.strip()

        rename = {}
        for col in df.columns:
            lo = col.lower()
            if "emiss" in lo:
                rename[col] = "data"
            elif lo == "pedido":
                rename[col] = "pedido"
            elif "marca" in lo:
                rename[col] = "marca"
            elif "grupo" in lo:
                rename[col] = "grupo"
            elif "btu" in lo:
                rename[col] = "btu"
            elif "ciclo" in lo:
                rename[col] = "ciclo"
            elif lo == "produto":
                rename[col] = "produto"
            elif "descr" in lo:
                rename[col] = "descricao"
            elif lo in ("qtde", "qtd", "quantidade"):
                rename[col] = "qtde"
            elif "custo" in lo and "total" not in lo:
                rename[col] = "vl_custo"
            elif "total" in lo:
                rename[col] = "vl_total"

        df = df.rename(columns=rename)

        # Data
        if "data" in df.columns:
            df["data"] = pd.to_datetime(
                df["data"].astype(str).str.strip(),
                format="%d/%m/%Y",
                errors="coerce",
            )

        # Numéricos
        def _num(s):
            return (
                pd.to_numeric(
                    s.astype(str)
                    .str.strip()
                    .str.replace(r"\.", "", regex=True)
                    .str.replace(",", ".", regex=False),
                    errors="coerce",
                )
                .fillna(0.0)
            )

        for c in ["qtde", "vl_custo", "vl_total"]:
            if c in df.columns:
                df[c] = _num(df[c])

        if "vl_total" not in df.columns:
            df["vl_total"] = 0.0
        if "vl_custo" in df.columns and "qtde" in df.columns:
            mask = (df["vl_total"] == 0)
            df.loc[mask, "vl_total"] = df.loc[mask, "vl_custo"] * df.loc[mask, "qtde"]

        # Strings
        for c in ["marca", "grupo", "btu", "ciclo", "produto", "descricao"]:
            if c in df.columns:
                df[c] = df[c].astype(str).str.strip()

        return df.reset_index(drop=True)

    except Exception as e:
        st.error(f"Erro ao carregar vendas: {e}")
        return pd.DataFrame()

# =========================================================
# ABC IA (SIMPLES)
# =========================================================
def calcular_abc(df, col_qtde="qtde", col_valor="vl_total"):
    if df.empty:
        return df

    # ABC por unidades
    abc_u = (
        df.groupby("produto", as_index=False)[col_qtde]
        .sum()
        .rename(columns={col_qtde: "qtde_total"})
        .sort_values("qtde_total", ascending=False)
    )
    total_u = abc_u["qtde_total"].sum()
    if total_u == 0:
        abc_u["classe_unid"] = "X"
    else:
        abc_u["acum"] = abc_u["qtde_total"].cumsum() / total_u

        def faixa_u(p):
            if p <= 0.5:  return "A+"
            if p <= 0.8:  return "A"
            if p <= 0.95: return "B"
            if p <= 0.99: return "C"
            return "X"

        abc_u["classe_unid"] = abc_u["acum"].apply(faixa_u)

    # ABC por valor
    abc_v = (
        df.groupby("produto", as_index=False)[col_valor]
        .sum()
        .rename(columns={col_valor: "valor_total"})
        .sort_values("valor_total", ascending=False)
    )
    total_v = abc_v["valor_total"].sum()
    if total_v == 0:
        abc_v["classe_valor"] = "X"
    else:
        abc_v["acum_v"] = abc_v["valor_total"].cumsum() / total_v

        def faixa_v(p):
            if p <= 0.5:  return "A+"
            if p <= 0.8:  return "A"
            if p <= 0.95: return "B"
            if p <= 0.99: return "C"
            return "X"

        abc_v["classe_valor"] = abc_v["acum_v"].apply(faixa_v)

    out = df.merge(abc_u[["produto", "classe_unid"]], on="produto", how="left")
    out = out.merge(abc_v[["produto", "classe_valor"]], on="produto", how="left")
    return out

# =========================================================
# ABA ESTOQUE & ABC
# =========================================================
def aba_estoque(estoque_df, vendas_df):
    st.header("📦 Estoque & ABC IA")

    if estoque_df.empty:
        st.warning("Carregue o arquivo de estoque para ver esta aba.")
        return

    df = estoque_df.copy()

    # Aplica ABC IA em cima do próprio estoque (por qtde e valor)
    df_abc = calcular_abc(df, col_qtde="qtde", col_valor="vl_total")

    # KPIs
    st.subheader("Visão Geral do Estoque")
    c1, c2, c3 = st.columns(3)
    c1.metric("SKUs", fmt_qtde(df_abc["produto"].nunique()))
    c2.metric("Unidades", fmt_qtde(df_abc["qtde"].sum()))
    c3.metric("Valor em Custo", fmt_brl(df_abc["vl_total"].sum()))

    # Tabela
    st.subheader("Tabela de Estoque com ABC IA")
    cols = [
        "produto",
        "descricao",
        "grupo",
        "btu",
        "ciclo",
        "qtde",
        "vl_custo",
        "vl_total",
        "classe_unid",
        "classe_valor",
    ]
    cols = [c for c in cols if c in df_abc.columns]
    view = df_abc[cols].copy()

    if "qtde" in view.columns:
        view["qtde"] = view["qtde"].apply(fmt_qtde)
    if "vl_custo" in view.columns:
        view["vl_custo"] = view["vl_custo"].apply(fmt_brl)
    if "vl_total" in view.columns:
        view["vl_total"] = view["vl_total"].apply(fmt_brl)

    def style_func(s):
        return [colorir_abc(v) for v in s]

    if "classe_unid" in view.columns or "classe_valor" in view.columns:
        styler = view.style
        if "classe_unid" in view.columns:
            styler = styler.apply(style_func, subset=["classe_unid"])
        if "classe_valor" in view.columns:
            styler = styler.apply(style_func, subset=["classe_valor"])
        st.dataframe(styler, use_container_width=True, height=600)
    else:
        st.dataframe(view, use_container_width=True, height=600)

# =========================================================
# ABA VENDAS & DEMANDA
# =========================================================
def aba_vendas(vendas_df):
    st.header("📈 Vendas & Demanda")

    if vendas_df.empty:
        st.warning("Carregue o arquivo de vendas.")
        return

    df = vendas_df.copy()

    st.subheader("Visão Geral")
    c1, c2, c3 = st.columns(3)
    c1.metric("Registros", fmt_qtde(len(df)))
    if "qtde" in df.columns:
        c2.metric("Unidades Vendidas", fmt_qtde(df["qtde"].sum()))
    if "vl_total" in df.columns:
        c3.metric("Valor Vendido", fmt_brl(df["vl_total"].sum()))

    if "data" in df.columns and "vl_total" in df.columns:
        df_mes = df.copy()
        df_mes = df_mes[df_mes["data"].notna()]
        df_mes["ano_mes"] = df_mes["data"].dt.to_period("M").astype(str)
        grup = (
            df_mes.groupby("ano_mes", as_index=False)
            .agg(qtde=("qtde", "sum"), valor=("vl_total", "sum"))
        )
        grup["valor"] = grup["valor"].astype(float)
        grup["qtde"] = grup["qtde"].astype(float)

        col1, col2 = st.columns(2)

        with col1:
            fig1 = px.bar(
                grup,
                x="ano_mes",
                y="valor",
                title="Vendas em Valor por Mês",
                labels={"ano_mes": "Ano-Mês", "valor": "R$"},
            )
            st.plotly_chart(fig1, use_container_width=True)

        with col2:
            fig2 = px.line(
                grup,
                x="ano_mes",
                y="qtde",
                markers=True,
                title="Vendas em Unidades por Mês",
                labels={"ano_mes": "Ano-Mês", "qtde": "Unidades"},
            )
            st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Amostra de Vendas")
    cols = [c for c in ["data", "marca", "grupo", "btu", "ciclo", "produto", "descricao", "qtde", "vl_custo", "vl_total"] if c in df.columns]
    sample = df[cols].head(200).copy()
    if "vl_custo" in sample.columns:
        sample["vl_custo"] = sample["vl_custo"].apply(fmt_brl)
    if "vl_total" in sample.columns:
        sample["vl_total"] = sample["vl_total"].apply(fmt_brl)
    st.dataframe(sample, use_container_width=True, height=400)

# =========================================================
# ABAS COBERTURA / SUGESTÃO / FORNECEDORES (SIMPLIFICADAS)
# =========================================================
def aba_cobertura(estoque_df, vendas_df):
    st.header("📊 Cobertura de Estoque")
    st.info("Cobertura detalhada será implementada na próxima etapa, depois de estabilizarmos Estoque & Vendas.")

def aba_sugestao(estoque_df, vendas_df):
    st.header("🛒 Sugestão de Compra")
    st.info("Sugestão de compra será implementada na próxima etapa, usando a cobertura e o ABC IA.")

def aba_fornecedores(estoque_df):
    st.header("🏭 Fornecedores")
    if estoque_df.empty:
        st.warning("Carregue o arquivo de estoque.")
        return
    col_marca = "marca" if "marca" in estoque_df.columns else None
    if not col_marca:
        st.info("Coluna de fabricante não encontrada no estoque.")
        return
    resumo = (
        estoque_df.groupby(col_marca, as_index=False)
        .agg(
            SKUs=("produto", "nunique"),
            Unidades=("qtde", "sum"),
            Valor=("vl_total", "sum"),
        )
        .sort_values("Valor", ascending=False)
    )
    resumo["Unidades"] = resumo["Unidades"].apply(fmt_qtde)
    resumo["Valor_fmt"] = resumo["Valor"].apply(fmt_brl)
    st.dataframe(
        resumo[[col_marca, "SKUs", "Unidades", "Valor_fmt"]].rename(
            columns={col_marca: "Fabricante", "Valor_fmt": "Valor (R$)"}
        ),
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
        st.sidebar.success(f"Estoque: {fmt_qtde(len(estoque_df))} produtos") if not estoque_df.empty else st.sidebar.error("Estoque: 0 produtos")

    if vnd_file is not None:
        vendas_df = carregar_vendas(vnd_file)
        st.sidebar.success(f"Vendas: {fmt_qtde(len(vendas_df))} registros") if not vendas_df.empty else st.sidebar.error("Vendas: 0 registros")

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
