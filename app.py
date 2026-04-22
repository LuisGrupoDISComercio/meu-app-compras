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
    return f"background-color: {cor[0]}; color: {cor[1]}; font-weight: bold; text-align: center;"


# =========================================================
# CARREGAMENTO
# =========================================================
def carregar_estoque(file):
    try:
        df = pd.read_excel(file, header=1)

        # Renomear colunas para nomes internos
        rename_map = {}
        for col in df.columns:
            col_lower = str(col).lower().strip()
            if "fabr" in col_lower:
                rename_map[col] = "fabr"
            elif "produto" in col_lower:
                rename_map[col] = "produto"
            elif col_lower in ["descrição", "descricao", "descrição"]:
                rename_map[col] = "descricao"
            elif col_lower == "abc":
                rename_map[col] = "curva_sistema"
            elif "cubagem" in col_lower:
                rename_map[col] = "cubagem"
            elif "qtde" in col_lower or col_lower == "qtd":
                rename_map[col] = "qtde"
            elif "unit" in col_lower and "custo" in col_lower:
                rename_map[col] = "custo_unitario"
            elif "custo" in col_lower and "total" in col_lower:
                rename_map[col] = "vl_total"

        df = df.rename(columns=rename_map)

        # Garantir que colunas essenciais existam
        for col in ["fabr", "produto", "qtde", "vl_total"]:
            if col not in df.columns:
                df[col] = np.nan

        # Converter tipos
        df["fabr"] = pd.to_numeric(df["fabr"], errors="coerce")
        df["produto"] = pd.to_numeric(df["produto"], errors="coerce")
        df["qtde"] = pd.to_numeric(df["qtde"], errors="coerce").fillna(0)
        df["vl_total"] = pd.to_numeric(df["vl_total"], errors="coerce").fillna(0)

        # ── REMOVER LINHA DE TOTAL (Fabr e Produto ambos NaN) ──
        df = df.dropna(subset=["fabr", "produto"], how="all")

        # ── REMOVER FABRICANTES IGNORADOS ──
        df = df[~df["fabr"].isin(FABRICANTES_IGNORAR)]

        # ── REMOVER LINHAS SEM PRODUTO VÁLIDO ──
        df = df.dropna(subset=["produto"])

        # Adicionar nome do fabricante
        df["marca"] = df["fabr"].map(MAPA_FABRICANTES).fillna("Outros")

        # Garantir descricao
        if "descricao" not in df.columns:
            df["descricao"] = ""
        df["descricao"] = df["descricao"].fillna("").astype(str)

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
            if "produto" in col or "cod" in col:
                rename_map[col] = "produto"
            elif "qtde" in col or "qtd" in col or "quant" in col:
                rename_map[col] = "qtde"
            elif "valor" in col or "total" in col or "vl" in col:
                rename_map[col] = "vl_total"
            elif "mes" in col or "mês" in col or "data" in col or "period" in col:
                rename_map[col] = "mes"
            elif "fabr" in col or "marca" in col:
                rename_map[col] = "fabr"
        df = df.rename(columns=rename_map)

        for col in ["produto", "qtde", "vl_total"]:
            if col not in df.columns:
                df[col] = 0

        df["produto"] = pd.to_numeric(df["produto"], errors="coerce")
        df["qtde"] = pd.to_numeric(df["qtde"], errors="coerce").fillna(0)
        df["vl_total"] = pd.to_numeric(df["vl_total"], errors="coerce").fillna(0)

        if "fabr" in df.columns:
            df["fabr"] = pd.to_numeric(df["fabr"], errors="coerce")
            df = df[~df["fabr"].isin(FABRICANTES_IGNORAR)]

        if "mes" in df.columns:
            df["mes"] = df["mes"].astype(str)

        df = df.dropna(subset=["produto"])
        df = df.reset_index(drop=True)
        return df

    except Exception as e:
        st.sidebar.error(f"Erro ao carregar vendas: {e}")
        return pd.DataFrame()


# =========================================================
# CÁLCULO ABC
# =========================================================
def calcular_abc(df, col_qtde="qtde", col_valor="vl_total"):
    colunas_ok = [c for c in ["produto", "descricao", "marca", "curva_sistema", col_qtde, col_valor] if c in df.columns]
    resumo = df[colunas_ok].copy()

    agg = {"produto": "first"}
    if "descricao" in resumo.columns:
        agg["descricao"] = "first"
    if "marca" in resumo.columns:
        agg["marca"] = "first"
    if "curva_sistema" in resumo.columns:
        agg["curva_sistema"] = "first"
    agg[col_qtde] = "sum"
    agg[col_valor] = "sum"

    resumo = resumo.groupby("produto", as_index=False).agg(agg)
    resumo[col_qtde] = pd.to_numeric(resumo[col_qtde], errors="coerce").fillna(0)
    resumo[col_valor] = pd.to_numeric(resumo[col_valor], errors="coerce").fillna(0)

    total_qtde = resumo[col_qtde].sum()
    total_valor = resumo[col_valor].sum()

    # ABC por unidade
    resumo = resumo.sort_values(col_qtde, ascending=False)
    resumo["pct_qtde"] = resumo[col_qtde] / total_qtde if total_qtde > 0 else 0
    resumo["pct_qtde_acum"] = resumo["pct_qtde"].cumsum()
    resumo["classe_unid"] = resumo["pct_qtde_acum"].apply(
        lambda x: "A" if x <= 0.70 else ("B" if x <= 0.90 else "C")
    )

    # ABC por valor
    resumo = resumo.sort_values(col_valor, ascending=False)
    resumo["pct_valor"] = resumo[col_valor] / total_valor if total_valor > 0 else 0
    resumo["pct_valor_acum"] = resumo["pct_valor"].cumsum()
    resumo["classe_valor"] = resumo["pct_valor_acum"].apply(
        lambda x: "A" if x <= 0.70 else ("B" if x <= 0.90 else "C")
    )

    return resumo


# =========================================================
# ABAS
# =========================================================
def aba_estoque(estoque_df, vendas_df):
    st.header("📦 Estoque & ABC")

    if estoque_df.empty:
        st.warning("Carregue o arquivo de estoque na barra lateral.")
        return

    df = estoque_df.copy()

    # ── MÉTRICAS ──
    total_skus = len(df)
    total_qtde = df["qtde"].sum() if "qtde" in df.columns else 0
    total_valor = df["vl_total"].sum() if "vl_total" in df.columns else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("SKUs em estoque", fmt_qtde(total_skus))
    c2.metric("Qtd total (unidades)", fmt_qtde(total_qtde))
    c3.metric("Valor total em estoque", fmt_brl(total_valor))

    st.divider()

    # ── ABC ──
    df_abc = calcular_abc(df, col_qtde="qtde", col_valor="vl_total")

    # Gráfico distribuição ABC valor
    if not df_abc.empty:
        dist = df_abc.groupby("classe_valor")["vl_total"].sum().reset_index()
        dist.columns = ["Classe", "Valor"]
        dist["Valor"] = dist["Valor"].astype(float)
        fig = px.pie(dist, names="Classe", values="Valor",
                     title="Distribuição ABC por Valor de Estoque",
                     color_discrete_map={"A": "#1a6b1a", "B": "#2980b9", "C": "#e67e22"})
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Detalhe por produto")

    # Montar tabela de exibição
    cols_exibir = []
    rename_exibir = {}

    if "produto" in df_abc.columns:
        cols_exibir.append("produto")
        rename_exibir["produto"] = "Produto"
    if "descricao" in df_abc.columns:
        cols_exibir.append("descricao")
        rename_exibir["descricao"] = "Descrição"
    if "marca" in df_abc.columns:
        cols_exibir.append("marca")
        rename_exibir["marca"] = "Marca"
    if "curva_sistema" in df_abc.columns:
        cols_exibir.append("curva_sistema")
        rename_exibir["curva_sistema"] = "Curva Sistema"
    if "qtde" in df_abc.columns:
        cols_exibir.append("qtde")
        rename_exibir["qtde"] = "Qtde"
    if "vl_total" in df_abc.columns:
        cols_exibir.append("vl_total")
        rename_exibir["vl_total"] = "Custo Total"
    if "classe_unid" in df_abc.columns:
        cols_exibir.append("classe_unid")
        rename_exibir["classe_unid"] = "ABC Unid. IA"
    if "classe_valor" in df_abc.columns:
        cols_exibir.append("classe_valor")
        rename_exibir["classe_valor"] = "ABC Valor IA"

    df_view = df_abc[cols_exibir].rename(columns=rename_exibir).copy()

    styler = df_view.style.format(
        {
            "Qtde": lambda x: fmt_qtde(x),
            "Custo Total": lambda x: fmt_brl(x),
        }
    )

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
        st.plotly_chart(fig2, use_container_width=True)

    st.dataframe(df.head(500), use_container_width=True)


def aba_cobertura(estoque_df, vendas_df):
    st.header("📊 Cobertura de Estoque")

    if estoque_df.empty or vendas_df.empty:
        st.warning("Carregue estoque e vendas para calcular a cobertura.")
        return

    df_est = estoque_df[["produto", "qtde", "marca"]].copy()
    df_est.columns = ["produto", "qtde_estoque", "marca"]

    df_vnd = vendas_df.copy()
    if "mes" in df_vnd.columns:
        n_meses = df_vnd["mes"].nunique()
    else:
        n_meses = 1

    media_mensal = (
        df_vnd.groupby("produto")["qtde"]
        .sum()
        .reset_index()
        .rename(columns={"qtde": "total_vendido"})
    )
    media_mensal["media_mensal"] = media_mensal["total_vendido"] / max(n_meses, 1)

    cob = df_est.merge(media_mensal, on="produto", how="left").fillna(0)
    cob["cobertura_meses"] = np.where(
        cob["media_mensal"] > 0,
        cob["qtde_estoque"] / cob["media_mensal"],
        np.inf,
    )

    def classificar(x):
        if x == np.inf:
            return "Sem venda"
        elif x < 1:
            return "🔴 Crítico"
        elif x < 2:
            return "🟠 Baixo"
        elif x <= 4:
            return "🟢 Adequado"
        else:
            return "🔵 Excesso"

    cob["status"] = cob["cobertura_meses"].apply(classificar)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🔴 Crítico", len(cob[cob["status"] == "🔴 Crítico"]))
    c2.metric("🟠 Baixo", len(cob[cob["status"] == "🟠 Baixo"]))
    c3.metric("🟢 Adequado", len(cob[cob["status"] == "🟢 Adequado"]))
    c4.metric("🔵 Excesso", len(cob[cob["status"] == "🔵 Excesso"]))

    st.dataframe(
        cob[["produto", "marca", "qtde_estoque", "media_mensal", "cobertura_meses", "status"]]
        .sort_values("cobertura_meses"),
        use_container_width=True,
        height=500,
    )


def aba_sugestao(estoque_df, vendas_df):
    st.header("🛒 Sugestão de Compra")

    if estoque_df.empty or vendas_df.empty:
        st.warning("Carregue estoque e vendas para gerar sugestões.")
        return

    cobertura_alvo = st.slider("Cobertura alvo (meses)", 1, 6, 3)

    df_est = estoque_df[["produto", "qtde", "marca", "descricao"]].copy()
    df_est.columns = ["produto", "qtde_estoque", "marca", "descricao"]

    df_vnd = vendas_df.copy()
    n_meses = df_vnd["mes"].nunique() if "mes" in df_vnd.columns else 1

    media_mensal = (
        df_vnd.groupby("produto")["qtde"]
        .sum()
        .reset_index()
        .rename(columns={"qtde": "total_vendido"})
    )
    media_mensal["media_mensal"] = media_mensal["total_vendido"] / max(n_meses, 1)

    sug = df_est.merge(media_mensal, on="produto", how="left").fillna(0)
    sug["estoque_alvo"] = sug["media_mensal"] * cobertura_alvo
    sug["sugestao_compra"] = (sug["estoque_alvo"] - sug["qtde_estoque"]).clip(lower=0)
    sug["sugestao_compra"] = sug["sugestao_compra"].round(0).astype(int)

    sug_filtrado = sug[sug["sugestao_compra"] > 0].sort_values("sugestao_compra", ascending=False)

    st.metric("Produtos com necessidade de compra", len(sug_filtrado))

    st.dataframe(
        sug_filtrado[["produto", "descricao", "marca", "qtde_estoque", "media_mensal", "estoque_alvo", "sugestao_compra"]].rename(
            columns={
                "produto": "Produto",
                "descricao": "Descrição",
                "marca": "Marca",
                "qtde_estoque": "Estoque Atual",
                "media_mensal": "Média Mensal",
                "estoque_alvo": "Estoque Alvo",
                "sugestao_compra": "Sugestão Compra",
            }
        ),
        use_container_width=True,
        height=500,
    )


def aba_fornecedores(estoque_df):
    st.header("🏭 Fornecedores")

    if estoque_df.empty:
        st.warning("Carregue o arquivo de estoque na barra lateral.")
        return

    df = estoque_df.copy()

    por_marca = (
        df.groupby("marca")
        .agg(skus=("produto", "count"), qtde_total=("qtde", "sum"), valor_total=("vl_total", "sum"))
        .reset_index()
        .sort_values("valor_total", ascending=False)
    )

    por_marca["valor_total"] = por_marca["valor_total"].astype(float)
    fig = px.bar(
        por_marca,
        x="marca",
        y="valor_total",
        title="Valor de Estoque por Fabricante",
        labels={"marca": "Fabricante", "valor_total": "Valor Total (R$)"},
        color="marca",
    )
    st.plotly_chart(fig, use_container_width=True)

    por_marca_fmt = por_marca.copy()
    por_marca_fmt["valor_total"] = por_marca_fmt["valor_total"].apply(fmt_brl)
    por_marca_fmt["qtde_total"] = por_marca_fmt["qtde_total"].apply(fmt_qtde)

    st.dataframe(
        por_marca_fmt.rename(
            columns={
                "marca": "Fabricante",
                "skus": "SKUs",
                "qtde_total": "Qtde Total",
                "valor_total": "Valor Total",
            }
        ),
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
