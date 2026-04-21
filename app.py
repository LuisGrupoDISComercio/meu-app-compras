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


# =========================================================
# CARREGAMENTO DE ESTOQUE
# =========================================================
@st.cache_data
def carregar_estoque(file_obj):
    """
    Lê Estoque.xlsx e padroniza colunas:
    produto, descricao, grupo, btu, ciclo, qtde,
    vl_custo, vl_total (custo entrada total), marca, curva_sistema.
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
            # custo unitário
            elif "vl custo" in lo or ("custo" in lo and "ult" in lo):
                rename[col] = "vl_custo"
            # NOVO: custo entrada total / custo total estoque
            elif ("custo" in lo and "total" in lo) or ("entrada" in lo and "total" in lo):
                rename[col] = "vl_total"
            elif "vl total" in lo or "valor total" in lo:
                rename[col] = "vl_total"
            elif "marca" in lo or "fabricante" in lo:
                rename[col] = "marca"
            elif lo in ("curva", "curva abc", "classe", "abc", "curva_abc"):
                rename[col] = "curva_sistema"

        df = df.rename(columns=rename)

        # essenciais
        for c in ["produto", "qtde"]:
            if c not in df.columns:
                st.error(f"Estoque: coluna obrigatória '{c}' não encontrada.")
                return pd.DataFrame()

        # se não tiver custo unitário/total, cria para não quebrar
        if "vl_custo" not in df.columns:
            df["vl_custo"] = 0
        if "vl_total" not in df.columns:
            df["vl_total"] = 0

        # numéricos
        for c in ["qtde", "vl_custo", "vl_total"]:
            df[c] = (
                df[c].astype(str)
                .str.replace(r"\.", "", regex=True)
                .str.replace(",", ".", regex=False)
            )
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

        # se vl_total veio 0, mas existe custo unitário, calcula como qtde * vl_custo
        if (df["vl_total"] == 0).all() and (df["vl_custo"] != 0).any():
            df["vl_total"] = df["qtde"] * df["vl_custo"]

        df["produto"] = df["produto"].astype(str).str.strip()
        if "descricao" in df.columns:
            df["descricao"] = df["descricao"].astype(str).str.strip()
        else:
            df["descricao"] = ""

        if "curva_sistema" in df.columns:
            df["curva_sistema"] = (
                df["curva_sistema"].astype(str).str.strip().str.upper()
            )

        # filtra linhas válidas
        df = df[df["produto"].notna()]
        df = df[df["qtde"].fillna(0) >= 0]

        return df.reset_index(drop=True)

    except Exception as e:
        st.error(f"Erro ao carregar estoque: {e}")
        return pd.DataFrame()


# =========================================================
# CARREGAMENTO DE VENDAS
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
            elif "descri" in lo:
                rename[col] = "descricao"
            elif lo in ("qtde", "qtd", "quantidade"):
                rename[col] = "qtde"
            elif "vl custo" in lo or ("custo" in lo and "ult" in lo):
                rename[col] = "vl_custo"
            elif "vl total" in lo or "valor total" in lo:
                rename[col] = "vl_total"

        df = df.rename(columns=rename)

        for c in ["qtde", "vl_custo", "vl_total"]:
            if c in df.columns:
                df[c] = (
                    df[c].astype(str)
                    .str.replace(r"\.", "", regex=True)
                    .str.replace(",", ".", regex=False)
                )
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

        if "data" in df.columns:
            df["data"] = pd.to_datetime(df["data"], errors="coerce", dayfirst=True)

        if "descricao" in df.columns:
            df["descricao"] = df["descricao"].astype(str)

        return df.reset_index(drop=True)

    except Exception as e:
        st.error(f"Erro ao carregar vendas: {e}")
        return pd.DataFrame()


# =========================================================
# ABC IA
# =========================================================
def calcular_abc(df, col_qtde="qtde", col_valor="vl_total"):
    base = df.copy()
    base[col_qtde] = base[col_qtde].fillna(0)

    # ABC por unidades
    unid = (
        base.groupby("produto", as_index=False)[col_qtde]
        .sum()
        .rename(columns={col_qtde: "qtde_total"})
        .sort_values("qtde_total", ascending=False)
    )
    soma_unid = unid["qtde_total"].sum()
    unid["perc_unid"] = np.where(
        soma_unid > 0, unid["qtde_total"] / soma_unid * 100, 0
    )
    unid["perc_unid_acum"] = unid["perc_unid"].cumsum()

    def classe_unid(p):
        if p <= 80:
            return "A"
        elif p <= 95:
            return "B"
        else:
            return "C"

    unid["classe_unid"] = unid["perc_unid_acum"].apply(classe_unid)

    # ABC por valor (se houver)
    if col_valor in base.columns:
        base[col_valor] = base[col_valor].fillna(0)
        val = (
            base.groupby("produto", as_index=False)[col_valor]
            .sum()
            .rename(columns={col_valor: "valor_total"})
            .sort_values("valor_total", ascending=False)
        )
        soma_val = val["valor_total"].sum()
        val["perc_val"] = np.where(
            soma_val > 0, val["valor_total"] / soma_val * 100, 0
        )
        val["perc_val_acum"] = val["perc_val"].cumsum()

        def classe_val(p):
            if p <= 80:
                return "A"
            elif p <= 95:
                return "B"
            else:
                return "C"

        val["classe_valor"] = val["perc_val_acum"].apply(classe_val)

        merged = base.merge(
            unid[["produto", "classe_unid"]],
            on="produto",
            how="left",
        ).merge(
            val[["produto", "classe_valor"]],
            on="produto",
            how="left",
        )
    else:
        merged = base.merge(
            unid[["produto", "classe_unid"]],
            on="produto",
            how="left",
        )
        merged["classe_valor"] = None

    return merged


# =========================================================
# ABA ESTOQUE & ABC
# =========================================================
def aba_estoque(estoque_df, vendas_df):
    st.header("📦 Estoque & ABC IA")

    if estoque_df.empty:
        st.warning("Carregue o arquivo de estoque.")
        return

    df = estoque_df.copy()
    df_abc = calcular_abc(df, col_qtde="qtde", col_valor="vl_total")

    qtd_total = df_abc["qtde"].sum()
    valor_total = df_abc["vl_total"].sum() if "vl_total" in df_abc.columns else 0
    skus = df_abc["produto"].nunique()

    col1, col2, col3 = st.columns(3)
    col1.metric("SKUs em estoque", fmt_qtde(skus))
    col2.metric("Qtd total em estoque", fmt_qtde(qtd_total))
    col3.metric(
        "Valor total em estoque",
        fmt_brl(valor_total) if valor_total > 0 else "—",
    )

    # Curva sistema agregada
    if "curva_sistema" in df_abc.columns:
        dist = (
            df_abc["curva_sistema"]
            .fillna("X")
            .astype(str)
            .str.upper()
            .value_counts()
            .sort_index()
        )
        curva_txt = ", ".join(f"{k}: {v}" for k, v in dist.items())
        st.markdown(f"**Curva Sistema (SKUs):** {curva_txt}")

    st.markdown("---")
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
                labels={"ano_mes": "Mês", "valor": "R$"},
            )
            st.plotly_chart(fig1, use_container_width=True)
        with col2:
            fig2 = px.line(
                grup,
                x="ano_mes",
                y="qtde",
                markers=True,
                title="Unidades vendidas por mês",
                labels={"ano_mes": "Mês", "qtde": "Unid"},
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
# OUTRAS ABAS
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
