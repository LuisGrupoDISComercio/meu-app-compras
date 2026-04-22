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
    if not isinstance(classe, str):
        return ""
    c = classe.strip().upper()
    cores = {
        "A": "background-color:#FFD700;color:#1a1a1a",
        "B": "background-color:#FFA500;color:#1a1a1a",
        "C": "background-color:#FF6347;color:#ffffff",
        "S": "background-color:#6495ED;color:#ffffff",
        "X": "background-color:#D3D3D3;color:#1a1a1a",
    }
    for k, v in cores.items():
        if c.startswith(k):
            return v
    return ""


# =========================================================
# CARGA DE DADOS
# =========================================================
def carregar_estoque(file):
    try:
        df = pd.read_excel(file, sheet_name=0, header=0)

        # Renomear colunas para padrão interno
        rename_map = {}
        for col in df.columns:
            col_lower = str(col).lower().strip()
            if col_lower in ["fabr", "fabricante", "fab"]:
                rename_map[col] = "fabr"
            elif col_lower in ["produto", "cod", "codigo", "código"]:
                rename_map[col] = "produto"
            elif col_lower in ["descrição", "descricao", "descrição", "desc"]:
                rename_map[col] = "descricao"
            elif col_lower in ["abc", "curva", "curva abc", "classe"]:
                rename_map[col] = "curva_sistema"
            elif col_lower in ["qtde", "quantidade", "qty", "estoque"]:
                rename_map[col] = "qtde"
            elif "custo" in col_lower and "unit" in col_lower:
                rename_map[col] = "custo_unitario"
            elif "custo" in col_lower and "total" in col_lower:
                rename_map[col] = "vl_total"
            elif "cubagem" in col_lower:
                rename_map[col] = "cubagem"

        df = df.rename(columns=rename_map)

        # Garantir colunas mínimas
        for col in ["fabr", "produto", "qtde", "vl_total"]:
            if col not in df.columns:
                df[col] = np.nan

        # Converter tipos
        df["fabr"] = pd.to_numeric(df["fabr"], errors="coerce")
        df["produto"] = pd.to_numeric(df["produto"], errors="coerce")
        df["qtde"] = pd.to_numeric(df["qtde"], errors="coerce")
        df["vl_total"] = pd.to_numeric(df["vl_total"], errors="coerce")

        # REMOVER linha de TOTAL (última linha com produto NaN mas vl_total preenchido)
        df = df[df["produto"].notna()]

        # REMOVER fabricantes ignorados (900, 995, 998, 999)
        df = df[~df["fabr"].isin(FABRICANTES_IGNORAR)]

        # REMOVER linhas onde qtde e vl_total são ambos 0 ou NaN
        df = df[~((df["qtde"].fillna(0) == 0) & (df["vl_total"].fillna(0) == 0))]

        # Adicionar nome do fabricante
        df["marca"] = df["fabr"].map(MAPA_FABRICANTES).fillna("Outros")

        # Garantir curva_sistema
        if "curva_sistema" not in df.columns:
            df["curva_sistema"] = ""
        df["curva_sistema"] = df["curva_sistema"].fillna("").astype(str)

        df = df.reset_index(drop=True)
        return df

    except Exception as e:
        st.sidebar.error(f"Erro ao carregar estoque: {e}")
        return pd.DataFrame()


def carregar_vendas(file):
    try:
        df = pd.read_csv(
            file,
            sep=None,
            engine="python",
            encoding="utf-8",
            on_bad_lines="skip",
        )
        df.columns = [str(c).strip().lower() for c in df.columns]

        rename_map = {}
        for col in df.columns:
            if col in ["produto", "cod", "codigo"]:
                rename_map[col] = "produto"
            elif col in ["qtde", "quantidade", "qty"]:
                rename_map[col] = "qtde"
            elif col in ["valor", "vl_venda", "total", "receita"]:
                rename_map[col] = "vl_venda"
            elif "mes" in col or "mês" in col or "month" in col:
                rename_map[col] = "mes"
            elif "data" in col or "date" in col:
                rename_map[col] = "data"

        df = df.rename(columns=rename_map)

        for col in ["produto", "qtde", "vl_venda"]:
            if col not in df.columns:
                df[col] = np.nan

        df["produto"] = pd.to_numeric(df["produto"], errors="coerce")
        df["qtde"] = pd.to_numeric(df["qtde"], errors="coerce")
        df["vl_venda"] = pd.to_numeric(df["vl_venda"], errors="coerce")

        if "data" in df.columns and "mes" not in df.columns:
            df["data"] = pd.to_datetime(df["data"], errors="coerce")
            df["mes"] = df["data"].dt.to_period("M").astype(str)

        df = df[df["produto"].notna()]
        df = df.reset_index(drop=True)
        return df

    except Exception as e:
        st.sidebar.error(f"Erro ao carregar vendas: {e}")
        return pd.DataFrame()


# =========================================================
# ABC IA
# =========================================================
def calcular_abc(df, col_qtde="qtde", col_valor="vl_total"):
    if df.empty:
        return df

    colunas_existem = all(c in df.columns for c in ["produto", col_qtde, col_valor])
    if not colunas_existem:
        return df

    agg = (
        df.groupby("produto", as_index=False)[[col_qtde, col_valor]]
        .sum()
    )
    agg = agg[agg[col_qtde] > 0]

    # ABC por unidade
    agg = agg.sort_values(col_qtde, ascending=False).reset_index(drop=True)
    total_qtde = agg[col_qtde].sum()
    agg["pct_qtde"] = agg[col_qtde].cumsum() / total_qtde * 100
    agg["classe_unid"] = agg["pct_qtde"].apply(
        lambda x: "A" if x <= 70 else ("B" if x <= 90 else "C")
    )

    # ABC por valor
    agg = agg.sort_values(col_valor, ascending=False).reset_index(drop=True)
    total_valor = agg[col_valor].sum()
    agg["pct_valor"] = agg[col_valor].cumsum() / total_valor * 100
    agg["classe_valor"] = agg["pct_valor"].apply(
        lambda x: "A" if x <= 70 else ("B" if x <= 90 else "C")
    )

    df = df.merge(
        agg[["produto", "classe_unid", "classe_valor"]],
        on="produto",
        how="left",
    )
    return df


# =========================================================
# ABAS
# =========================================================
def aba_estoque(estoque_df, vendas_df):
    st.header("📦 Estoque & ABC IA")

    if estoque_df.empty:
        st.warning("Carregue o arquivo de estoque na barra lateral.")
        return

    df = estoque_df.copy()
    df = calcular_abc(df, col_qtde="qtde", col_valor="vl_total")

    # ── Filtros ──────────────────────────────────────────
    marcas_disp = sorted(df["marca"].dropna().unique())
    marca_sel = st.multiselect("Filtrar por Fabricante", marcas_disp, default=marcas_disp)
    df = df[df["marca"].isin(marca_sel)]

    curvas_disp = sorted(df["curva_sistema"].dropna().unique())
    curvas_disp = [c for c in curvas_disp if c.strip() != ""]
    if curvas_disp:
        curva_sel = st.multiselect("Filtrar por Curva (sistema)", curvas_disp, default=curvas_disp)
        df = df[df["curva_sistema"].isin(curva_sel)]

    # ── Cards de resumo ───────────────────────────────────
    total_skus = len(df["produto"].unique())
    total_qtde = df["qtde"].sum()
    total_valor = df["vl_total"].sum()

    c1, c2, c3 = st.columns(3)
    c1.metric("SKUs em Estoque", fmt_qtde(total_skus))
    c2.metric("Qtd Total em Estoque", fmt_qtde(total_qtde))
    c3.metric("Valor Total em Estoque", fmt_brl(total_valor))

    # ── Gráfico ABC por valor ─────────────────────────────
    if "classe_valor" in df.columns:
        abc_group = (
            df.groupby("classe_valor")["vl_total"]
            .sum()
            .reset_index()
            .rename(columns={"classe_valor": "Classe", "vl_total": "Valor (R$)"})
        )
        abc_group["Valor (R$)"] = abc_group["Valor (R$)"].astype(float)
        fig = px.bar(
            abc_group,
            x="Classe",
            y="Valor (R$)",
            color="Classe",
            color_discrete_map={"A": "#FFD700", "B": "#FFA500", "C": "#FF6347"},
            title="Distribuição de Valor por Classe ABC IA",
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── Tabela ────────────────────────────────────────────
    cols_exibir = ["produto", "descricao", "marca", "curva_sistema", "qtde",
                   "custo_unitario", "vl_total", "classe_unid", "classe_valor"]
    cols_exibir = [c for c in cols_exibir if c in df.columns]

    df_view = df[cols_exibir].copy()

    # Formatar valores
    if "custo_unitario" in df_view.columns:
        df_view["custo_unitario"] = df_view["custo_unitario"].apply(fmt_brl)
    if "vl_total" in df_view.columns:
        df_view["vl_total"] = df_view["vl_total"].apply(fmt_brl)

    df_view = df_view.rename(columns={
        "produto": "Produto",
        "descricao": "Descrição",
        "marca": "Marca",
        "curva_sistema": "Curva Sistema",
        "qtde": "Qtde",
        "custo_unitario": "Custo Unit.",
        "vl_total": "Custo Total",
        "classe_unid": "ABC Unid. IA",
        "classe_valor": "ABC Valor IA",
    })

    st.subheader("Detalhe por Produto")

    styler = df_view.style
    if "ABC Unid. IA" in df_view.columns:
        styler = styler.map(colorir_abc, subset=["ABC Unid. IA"])
    if "ABC Valor IA" in df_view.columns:
        styler = styler.map(colorir_abc, subset=["ABC Valor IA"])
    if "Curva Sistema" in df_view.columns:
        styler = styler.map(colorir_abc, subset=["Curva Sistema"])

    st.dataframe(styler, use_container_width=True, height=500)


def aba_vendas(vendas_df):
    st.header("📈 Vendas & Demanda")

    if vendas_df.empty:
        st.warning("Carregue o arquivo de vendas na barra lateral.")
        return

    df = vendas_df.copy()

    # Evolução mensal
    if "mes" in df.columns and "qtde" in df.columns:
        mensal = (
            df.groupby("mes")["qtde"]
            .sum()
            .reset_index()
            .rename(columns={"mes": "Mês", "qtde": "Qtde Vendida"})
            .sort_values("Mês")
        )
        mensal["Qtde Vendida"] = mensal["Qtde Vendida"].astype(float)
        fig = px.bar(mensal, x="Mês", y="Qtde Vendida", title="Vendas Mensais (Qtde)")
        st.plotly_chart(fig, use_container_width=True)

    # Top 20 produtos
    if "produto" in df.columns and "qtde" in df.columns:
        top = (
            df.groupby("produto")["qtde"]
            .sum()
            .reset_index()
            .sort_values("qtde", ascending=False)
            .head(20)
        )
        top["qtde"] = top["qtde"].astype(float)
        top["produto"] = top["produto"].astype(str)
        fig2 = px.bar(top, x="produto", y="qtde", title="Top 20 Produtos Mais Vendidos")


