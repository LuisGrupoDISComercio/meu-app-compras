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
        "A":  ("#FFD700", "#1a1a1a"),
        "B":  ("#FFA500", "#1a1a1a"),
        "C":  ("#FFFF99", "#1a1a1a"),
        "X":  ("#D3D3D3", "#1a1a1a"),
    }
    if pd.isna(classe):
        return ""
    bg, fg = cores.get(str(classe).strip(), cores["X"])
    return f"background-color: {bg}; color: {fg}; font-weight:bold; text-align:center;"


# =========================================================
# CARREGAMENTO DE ESTOQUE (FOCADO NO SEU LAYOUT)
# =========================================================
@st.cache_data
def carregar_estoque(file_obj):
    """
    Lê Estoque.xlsx. Aceita variações nos nomes das colunas e
    padroniza para: produto, descricao, grupo, btu, ciclo, qtde,
    vl_custo, vl_total, marca (se existir).
    """
    try:
        df = pd.read_excel(file_obj, sheet_name=0, header=0, dtype=str)
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
            elif ("vl total" in lo) or ("valor total" in lo) or lo == "total":
                rename[col] = "vl_total"
            elif "marca" in lo or "fabricante" in lo:
                rename[col] = "marca"

        df = df.rename(columns=rename)

        # checa colunas mínimas
        if "produto" not in df.columns or "qtde" not in df.columns:
            st.error("Estoque: não encontrei colunas 'Produto' e 'Qtde' após mapeamento.")
            return pd.DataFrame()

        # numéricos
        for c in ["qtde", "vl_custo", "vl_total"]:
            if c in df.columns:
                df[c] = (
                    df[c]
                    .astype(str)
                    .str.replace(r"\.", "", regex=True)
                    .str.replace(",", ".", regex=False)
                )
                df[c] = pd.to_numeric(df[c], errors="coerce")

        # se não tiver vl_total, tenta calcular
        if "vl_total" not in df.columns and "vl_custo" in df.columns:
            df["vl_total"] = df["qtde"].fillna(0) * df["vl_custo"].fillna(0)

        # strings
        df["produto"] = df["produto"].astype(str).str.strip()
        if "descricao" in df.columns:
            df["descricao"] = df["descricao"].astype(str).str.strip()
        else:
            df["descricao"] = ""

        # filtra linhas válidas
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

        # datas
        if "data" in df.columns:
            df["data"] = pd.to_datetime(
                df["data"].astype(str).str.strip(),
                format="%d/%m/%Y",
                errors="coerce",
            )

        # numéricos
        def _num(s):
            return pd.to_numeric(
                s.astype(str)
                .str.strip()
                .str.replace(r"\.", "", regex=True)
                .str.replace(",", ".", regex=False),
                errors="coerce",
            ).fillna(0.0)

        for c in ["qtde", "vl_custo", "vl_total"]:
            if c in df.columns:
                df[c] = _num(df[c])

        # calcula vl_total se não tiver / estiver 0
        if "vl_total" not in df.columns:
            df["vl_total"] = 0.0
        if "vl_custo" in df.columns and "qtde" in df.columns:
            mask = (df["vl_total"].isna()) | (df["vl_total"] == 0)
            df.loc[mask, "vl_total"] = df.loc[mask, "vl_custo"] * df.loc[mask, "qtde"]

        # strings
        for c in ["marca", "grupo", "btu", "ciclo", "produto", "descricao"]:
            if c in df.columns:
                df[c] = df[c].astype(str).str.strip()

        return df.reset_index(drop=True)
    except Exception as e:
        st.error(f"Erro ao carregar vendas: {e}")
        return pd.DataFrame()


# =========================================================
# CÁLCULO ABC
# =========================================================
def calcular_abc(df, col_qtde="qtde", col_valor="vl_total"):
    """
    df: DataFrame com colunas 'produto', col_qtde e opcionalmente col_valor.
    Retorna df com colunas: classe_unid, classe_valor.
    Se col_valor não existir, classe_valor vira 'X' para todos.
    """
    if df.empty or "produto" not in df.columns or col_qtde not in df.columns:
        return df.assign(classe_unid="X", classe_valor="X")

    base = df.copy()
    base[col_qtde] = base[col_qtde].fillna(0).astype(float)

    grp = (
        base.groupby("produto", as_index=False)[col_qtde]
        .sum()
        .rename(columns={col_qtde: "total_qtde"})
    ).sort_values("total_qtde", ascending=False)

    total = grp["total_qtde"].sum()
    if total == 0:
        grp["classe_unid"] = "X"
    else:
        grp["perc_acum"] = grp["total_qtde"].cumsum() / total
        bins = [-0.001, 0.50, 0.80, 0.95, 0.99, 1.001]
        labels = ["A+", "A", "B", "C", "X"]
        grp["classe_unid"] = pd.cut(grp["perc_acum"], bins=bins, labels=labels)

    # valor
    if col_valor in base.columns:
        base[col_valor] = base[col_valor].fillna(0).astype(float)
        grp_val = (
            base.groupby("produto", as_index=False)[col_valor]
            .sum()
            .rename(columns={col_valor: "total_valor"})
        ).sort_values("total_valor", ascending=False)

        total_v = grp_val["total_valor"].sum()
        if total_v == 0:
            grp_val["classe_valor"] = "X"
        else:
            grp_val["perc_acum_v"] = grp_val["total_valor"].cumsum() / total_v
            grp_val["classe_valor"] = pd.cut(
                grp_val["perc_acum_v"], bins=bins, labels=labels
            )

        grp = grp.merge(grp_val[["produto", "classe_valor"]], on="produto", how="left")
    else:
        grp["classe_valor"] = "X"

    # volta para o df original
    out = base.merge(grp[["produto", "classe_unid", "classe_valor"]], on="produto", how="left")
    return out


# =========================================================
# ABA ESTOQUE & ABC
# =========================================================
def aba_estoque(estoque_df, vendas_df):
    st.header("📦 Estoque & ABC IA")

    if estoque_df.empty:
        st.warning("Carregue o arquivo de estoque.")
        return

    df = estoque_df.copy()

    # garante vl_total (de novo aqui, por segurança)
    if "vl_total" not in df.columns and "vl_custo" in df.columns:
        df["vl_total"] = df["qtde"].fillna(0) * df["vl_custo"].fillna(0)

    # se ainda não existir vl_total, faz ABC só por quantidade
    col_valor = "vl_total" if "vl_total" in df.columns else None

    df_abc = calcular_abc(df, col_qtde="qtde", col_valor=col_valor if col_valor else "NÃO_EXISTE")

    st.subheader("Resumo")
    c1, c2 = st.columns(2)
    c1.metric("SKUs", fmt_qtde(len(df_abc)))
    c2.metric("Qtd Total", fmt_qtde(df_abc["qtde"].sum()))

    # tabela
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

    styler = view.style
    if "classe_unid" in view.columns:
        styler = styler.map(colorir_abc, subset=["classe_unid"])
    if "classe_valor" in view.columns:
        styler = styler.map(colorir_abc, subset=["classe_valor"])

    st.dataframe(styler, use_container_width=True, height=600)


# =========================================================
# ABA VENDAS & DEMANDA (SIMPLES)
# =========================================================
def aba_vendas(vendas_df):
    st.header("📈 Vendas & Demanda")

    if vendas_df.empty:
        st.warning("Carregue o arquivo de vendas.")
        return

    df = vendas_df.copy()

    st.subheader("Resumo")
    c1, c2, c3 = st.columns(3)
    c1.metric("Registros", fmt_qtde(len(df)))
    if "qtde" in df.columns:
        c2.metric("Unidades", fmt_qtde(df["qtde"].sum()))
    if "vl_total" in df.columns:
        c3.metric("Valor", fmt_brl(df["vl_total"].sum()))

    if "data" in df.columns and "vl_total" in df.columns:
        df_mes = df[df["data"].notna()].copy()
        df_mes["ano_mes"] = df_mes["data"].dt.to_period("M").astype(str)
        grup = (
            df_mes.groupby("ano_mes", as_index=False)
            .agg(qtde=("qtde", "sum"), valor=("vl_total", "sum"))
        )
        grup["qtde"] = grup["qtde"].astype(float)
        grup["valor"] = grup["valor"].astype(float)

        col1, col2 = st.columns(2)
        with col1:
            fig1 = px.bar(
                grup,
                x="ano_mes",
                y="valor",
                title="Valor vendido por mês",
                labels={"ano_mes": "Ano-Mês", "valor": "R$"},
            )
            st.plotly_chart(fig1, use_container_width=True)
        with col2:
            fig2 = px.line(
                grup,
                x="ano_mes",
                y="qtde",
                markers=True,
                title="Unidades vendidas por mês",
                labels={"ano_mes": "Ano-Mês", "qtde": "Unid"},
            )
            st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Amostra de Vendas")
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
    if "vl_custo" in sample.columns:
        sample["vl_custo"] = sample["vl_custo"].apply(fmt_brl)
    if "vl_total" in sample.columns:
        sample["vl_total"] = sample["vl_total"].apply(fmt_brl)
    st.dataframe(sample, use_container_width=True, height=400)


# =========================================================
# ABAS SIMPLIFICADAS
# =========================================================
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
    resumo = (
        df.groupby("marca", as_index=False)
        .agg(
            SKUs=("produto", "nunique"),
            Unidades=("qtde", "sum"),
            Valor=("vl_total", "sum") if "vl_total" in df.columns else ("qtde", "sum"),
        )
        .sort_values("Valor", ascending=False)
    )
    resumo["Unidades"] = resumo["Unidades"].apply(fmt_qtde)
    resumo["Valor_fmt"] = resumo["Valor"].apply(fmt_brl)
    st.dataframe(
        resumo[["marca", "SKUs", "Unidades", "Valor_fmt"]].rename(
            columns={"marca": "Fabricante", "Valor_fmt": "Valor (R$)"}
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
