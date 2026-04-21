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
    bg, fg = cores.get(str(classe).strip().upper(), cores["X"])
    return f"background-color: {bg}; color: {fg}; font-weight:bold; text-align:center;"


# =========================================================
# CARREGAMENTO DE ESTOQUE
# =========================================================
@st.cache_data
def carregar_estoque(file_obj):
    """
    Lê Estoque.xlsx, padronizando colunas para:
    produto, descricao, grupo, btu, ciclo, qtde, vl_custo, vl_total, marca, curva_sistema.
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
            elif "vl total" in lo or "valor total" in lo:
                rename[col] = "vl_total"
            elif "marca" in lo or "fabricante" in lo:
                rename[col] = "marca"
            elif lo in ("curva", "curva abc", "classe", "abc", "curva_abc"):
                rename[col] = "curva_sistema"

        df = df.rename(columns=rename)

        # Essenciais
        for c in ["produto", "qtde"]:
            if c not in df.columns:
                st.error(f"Estoque: coluna obrigatória '{c}' não encontrada.")
                return pd.DataFrame()

        # Numéricos
        for c in ["qtde", "vl_custo", "vl_total"]:
            if c in df.columns:
                df[c] = (
                    df[c].astype(str)
                    .str.replace(r"\.", "", regex=True)
                    .str.replace(",", ".", regex=False)
                )
                df[c] = pd.to_numeric(df[c], errors="coerce")

        if "vl_total" not in df.columns and "vl_custo" in df.columns:
            df["vl_total"] = df["qtde"].fillna(0) * df["vl_custo"].fillna(0)

        df["produto"] = df["produto"].astype(str).str.strip()
        if "descricao" in df.columns:
            df["descricao"] = df["descricao"].astype(str).str.strip()
        else:
            df["descricao"] = ""

        if "curva_sistema" in df.columns:
            df["curva_sistema"] = (
                df["curva_sistema"].astype(str).str.strip().str.upper()
            )

        df = df[df["produto"].notna()]
        df = df[df["qtde"].fillna(0) > 0]

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
    Lê Vendas.csv com ; e ,.
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

        # Datas
        if "data" in df.columns:
            df["data"] = pd.to_datetime(
                df["data"].astype(str).str[:10],
                format="%d/%m/%Y",
                errors="coerce",
            )

        # Numéricos
        for c in ["qtde", "vl_custo", "vl_total"]:
            if c in df.columns:
                df[c] = (
                    df[c].astype(str)
                    .str.replace(r"\.", "", regex=True)
                    .str.replace(",", ".", regex=False)
                )
                df[c] = pd.to_numeric(df[c], errors="coerce")

        # Limpeza básica
        if "produto" in df.columns:
            df["produto"] = df["produto"].astype(str).str.strip()
        if "descricao" in df.columns:
            df["descricao"] = df["descricao"].astype(str).str.strip()

        df = df.dropna(how="all")
        return df.reset_index(drop=True)

    except Exception as e:
        st.error(f"Erro ao carregar vendas: {e}")
        return pd.DataFrame()


# =========================================================
# CÁLCULO ABC
# =========================================================
def calcular_abc(df, col_qtde="qtde", col_valor="vl_total"):
    base = df.copy()

    base[col_qtde] = base[col_qtde].fillna(0)
    if col_valor in base.columns:
        base[col_valor] = base[col_valor].fillna(0)
    else:
        base[col_valor] = 0

    # ABC por quantidade
    grp_qtd = (
        base.groupby("produto", as_index=False)[col_qtde]
        .sum()
        .rename(columns={col_qtde: "qtde"})
        .sort_values("qtde", ascending=False)
    )
    grp_qtd["perc_qtde"] = grp_qtd["qtde"] / grp_qtd["qtde"].sum() * 100
    grp_qtd["perc_qtde_acum"] = grp_qtd["perc_qtde"].cumsum()

    conds_q = [
        grp_qtd["perc_qtde_acum"] <= 80,
        (grp_qtd["perc_qtde_acum"] > 80) & (grp_qtd["perc_qtde_acum"] <= 95),
        grp_qtd["perc_qtde_acum"] > 95,
    ]
    values = ["A", "B", "C"]
    grp_qtd["classe_unid"] = np.select(conds_q, values, default="C")

    # ABC por valor (se houver)
    grp_val = (
        base.groupby("produto", as_index=False)[col_valor]
        .sum()
        .rename(columns={col_valor: "vl_total"})
        .sort_values("vl_total", ascending=False)
    )
    if grp_val["vl_total"].sum() > 0:
        grp_val["perc_valor"] = grp_val["vl_total"] / grp_val["vl_total"].sum() * 100
        grp_val["perc_valor_acum"] = grp_val["perc_valor"].cumsum()
        conds_v = [
            grp_val["perc_valor_acum"] <= 80,
            (grp_val["perc_valor_acum"] > 80) & (grp_val["perc_valor_acum"] <= 95),
            grp_val["perc_valor_acum"] > 95,
        ]
        grp_val["classe_valor"] = np.select(conds_v, values, default="C")
    else:
        grp_val["classe_valor"] = "X"

    # Junta
    df_abc = base.merge(grp_qtd[["produto", "classe_unid"]], on="produto", how="left")
    df_abc = df_abc.merge(
        grp_val[["produto", "classe_valor", "vl_total"]], on="produto", how="left"
    )

    return df_abc


# =========================================================
# ABA ESTOQUE & ABC IA
# =========================================================
def aba_estoque(estoque_df, vendas_df):
    st.header("📦 Estoque & ABC IA")

    if estoque_df.empty:
        st.warning("Carregue o arquivo de estoque.")
        return

    df = estoque_df.copy()

    # Garante vl_total
    if "vl_total" not in df.columns and "vl_custo" in df.columns:
        df["vl_total"] = df["qtde"].fillna(0) * df["vl_custo"].fillna(0)
    if "vl_total" not in df.columns:
        df["vl_total"] = 0

    df_abc = calcular_abc(df, col_qtde="qtde", col_valor="vl_total")

    # RESUMO (agora com valor total e curva do sistema)
    st.subheader("Resumo")
    c1, c2, c3, c4 = st.columns(4)

    total_skus = len(df_abc["produto"].unique())
    total_qtde = df_abc["qtde"].sum()
    total_valor = df_abc["vl_total"].sum()

    c1.metric("SKUs", fmt_qtde(total_skus))
    c2.metric("Qtd Total", fmt_qtde(total_qtde))
    c3.metric("Valor Total", fmt_brl(total_valor))

    # distribuição da curva do sistema
    if "curva_sistema" in df_abc.columns:
        dist = (
            df_abc.groupby("curva_sistema", as_index=False)["produto"]
            .nunique()
            .rename(columns={"produto": "SKUs"})
            .sort_values("SKUs", ascending=False)
        )
        curva_txt = " • ".join(
            f"{row['curva_sistema']}: {fmt_qtde(row['SKUs'])}"
            for _, row in dist.iterrows()
        )
        c4.metric("Curva Sistema (SKUs)", curva_txt if curva_txt else "-")
    else:
        c4.metric("Curva Sistema (SKUs)", "-")

    # TABELA
    st.subheader("Detalhamento de Estoque")

    cols = [
        "produto",
        "descricao",
        "grupo",
        "btu",
        "ciclo",
        "qtde",
        "vl_custo",
        "vl_total",
        "curva_sistema",
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
# ABA VENDAS & DEMANDA
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
            .sort_values("ano_mes")
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
