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
    "TCL":     "images/pngtransparenttclhdlogo.png",
    "Grupo":   "images/DIS_NEW.jpg",
}

COR_ABC = {
    "A+": {"bg": "#8B6914", "fg": "#FFFFFF"},
    "A":  {"bg": "#FFD700", "fg": "#1a1a1a"},
    "B":  {"bg": "#FFA500", "fg": "#1a1a1a"},
    "C":  {"bg": "#FFE033", "fg": "#1a1a1a"},
    "X":  {"bg": "#C0C0C0", "fg": "#1a1a1a"},
}

# ─────────────────────────────────────────────
# FORMATADORES
# ─────────────────────────────────────────────
def fmt_brl(valor):
    try:
        return f"R$ {valor:_.2f}".replace("_", ".").replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return valor

def fmt_qtde(valor):
    try:
        return f"{int(valor):,}".replace(",", ".")
    except Exception:
        return valor

# ─────────────────────────────────────────────
# CARREGAMENTO DE DADOS
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def carregar_estoque(file):
    try:
        xl = pd.ExcelFile(file)
        aba = xl.sheet_names[0]
        df = xl.parse(aba, header=None)

        # Encontrar linha do cabeçalho procurando por "Produto" ou "Fabr"
        header_row = None
        for i, row in df.iterrows():
            vals = [str(v).strip().lower() for v in row.values]
            if "produto" in vals or "fabr" in vals:
                header_row = i
                break

        if header_row is None:
            return pd.DataFrame()

        df.columns = df.iloc[header_row].values
        df = df.iloc[header_row + 1:].reset_index(drop=True)

        # Remover colunas completamente vazias ou unnamed sem dados
        df = df.loc[:, df.columns.notna()]
        df.columns = [str(c).strip() for c in df.columns]
        df = df[[c for c in df.columns if not c.lower().startswith("unnamed")]]

        # Mapear colunas esperadas (flexível a variações de nome)
        rename_map = {}
        for col in df.columns:
            cl = col.strip().lower()
            if cl in ["fabr", "fabricante"]:
                rename_map[col] = "fabr"
            elif cl in ["produto", "cod", "codigo", "código"]:
                rename_map[col] = "produto"
            elif cl in ["descrição", "descricao", "descr", "description"]:
                rename_map[col] = "descricao"
            elif cl in ["abc"]:
                rename_map[col] = "abc"
            elif "cubagem" in cl:
                rename_map[col] = "cubagem"
            elif cl in ["qtde", "quantidade", "qty", "estoque"]:
                rename_map[col] = "qtde"
            elif "custo" in cl and "total" in cl:
                rename_map[col] = "custo_total"
            elif "custo" in cl and ("unit" in cl or "médio" in cl or "medio" in cl or "entrada" in cl):
                rename_map[col] = "custo_unit"

        df = df.rename(columns=rename_map)

        colunas_obrigatorias = ["produto", "descricao", "qtde"]
        for c in colunas_obrigatorias:
            if c not in df.columns:
                return pd.DataFrame()

        # Converter tipos
        df["qtde"] = pd.to_numeric(df["qtde"], errors="coerce").fillna(0)
        if "custo_unit" in df.columns:
            df["custo_unit"] = pd.to_numeric(df["custo_unit"], errors="coerce").fillna(0)
        if "custo_total" in df.columns:
            df["custo_total"] = pd.to_numeric(df["custo_total"], errors="coerce").fillna(0)
        if "fabr" in df.columns:
            df["fabr"] = pd.to_numeric(df["fabr"], errors="coerce")

        # Filtrar fabricantes irrelevantes
        if "fabr" in df.columns:
            df = df[~df["fabr"].isin(FABRICANTES_IGNORAR)]

        # Adicionar nome do fabricante
        if "fabr" in df.columns:
            df["fabricante"] = df["fabr"].map(MAPA_FABRICANTES_ESTOQUE).fillna("Outros")
        else:
            df["fabricante"] = "Outros"

        df = df[df["qtde"] > 0].reset_index(drop=True)
        return df

    except Exception as e:
        st.error(f"Erro ao carregar estoque: {e}")
        return pd.DataFrame()


@st.cache_data(show_spinner=False)
def carregar_vendas(file):
    try:
        raw = file.read()
        file.seek(0)

        # Tentar detectar separador
        for sep in [";", ",", "\t"]:
            try:
                df = pd.read_csv(file, sep=sep, encoding="utf-8", on_bad_lines="skip")
                file.seek(0)
                if len(df.columns) >= 5:
                    break
            except Exception:
                file.seek(0)
                continue

        # Normalizar nomes de colunas
        df.columns = [str(c).strip() for c in df.columns]

        rename_map = {}
        for col in df.columns:
            cl = col.strip().lower()
            if "emiss" in cl or "data" in cl or "dt" in cl:
                rename_map[col] = "data"
            elif cl in ["pedido", "nf", "nota"]:
                rename_map[col] = "pedido"
            elif cl in ["marca", "fabricante"]:
                rename_map[col] = "marca"
            elif cl in ["grupo"]:
                rename_map[col] = "grupo"
            elif cl in ["btu"]:
                rename_map[col] = "btu"
            elif cl in ["ciclo"]:
                rename_map[col] = "ciclo"
            elif cl in ["produto", "cod", "codigo", "sku"]:
                rename_map[col] = "produto"
            elif cl in ["descricao", "descrição", "descr"]:
                rename_map[col] = "descricao"
            elif cl in ["qtde", "quantidade", "qty"]:
                rename_map[col] = "qtde"
            elif "custo" in cl and "ú" in cl or ("vl" in cl and "custo" in cl and "total" not in cl):
                rename_map[col] = "custo_unit"
            elif "total" in cl or ("vl" in cl and "total" in cl):
                rename_map[col] = "vl_total"

        df = df.rename(columns=rename_map)

        if "data" in df.columns:
            df["data"] = pd.to_datetime(df["data"], dayfirst=True, errors="coerce")
        if "qtde" in df.columns:
            df["qtde"] = pd.to_numeric(df["qtde"], errors="coerce").fillna(0)
        if "vl_total" in df.columns:
            df["vl_total"] = pd.to_numeric(df["vl_total"], errors="coerce").fillna(0)
        if "custo_unit" in df.columns:
            df["custo_unit"] = pd.to_numeric(df["custo_unit"], errors="coerce").fillna(0)

        return df

    except Exception as e:
        st.error(f"Erro ao carregar vendas: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────
# CLASSIFICAÇÃO ABC IA
# ─────────────────────────────────────────────
def classificar_abc_ia(estoque_df, vendas_df, data_ini, data_fim):
    """
    Retorna estoque_df com colunas extras:
      - qtde_vendida   (unidades vendidas no período)
      - vl_vendido     (R$ vendidos no período)
      - classe_abc_unid
      - classe_abc_valor
    """
    df = estoque_df.copy()

    if vendas_df.empty or "produto" not in vendas_df.columns:
        for col in ["qtde_vendida", "vl_vendido", "classe_abc_unid", "classe_abc_valor"]:
            df[col] = 0 if "qtde" in col or "vl" in col else "X"
        return df

    mask = pd.Series([True] * len(vendas_df))
    if "data" in vendas_df.columns:
        mask = (
            (vendas_df["data"] >= pd.Timestamp(data_ini)) &
            (vendas_df["data"] <= pd.Timestamp(data_fim))
        )

    vf = vendas_df[mask].copy()
    vf["produto"] = vf["produto"].astype(str).str.strip()
    df["produto"] = df["produto"].astype(str).str.strip()

    agg = vf.groupby("produto").agg(
        qtde_vendida=("qtde", "sum"),
        vl_vendido=("vl_total", "sum") if "vl_total" in vf.columns else ("qtde", "sum")
    ).reset_index()

    df = df.merge(agg, on="produto", how="left")
    df["qtde_vendida"] = df["qtde_vendida"].fillna(0)
    df["vl_vendido"] = df["vl_vendido"].fillna(0)

    def _classe(serie):
        total = serie.sum()
        if total == 0:
            return pd.Series(["X"] * len(serie), index=serie.index)
        pct = serie / total
        cum = pct.sort_values(ascending=False).cumsum()
        classes = []
        for idx in serie.index:
            v = cum[idx] if idx in cum.index else 1.0
            if v <= 0.50:
                classes.append("A+")
            elif v <= 0.70:
                classes.append("A")
            elif v <= 0.85:
                classes.append("B")
            elif v <= 0.95:
                classes.append("C")
            else:
                classes.append("X")
        return pd.Series(classes, index=serie.index)

    df["classe_abc_unid"] = _classe(df["qtde_vendida"])
    df["classe_abc_valor"] = _classe(df["vl_vendido"])

    return df


# ─────────────────────────────────────────────
# ESTILO ABC (usa .map em vez de .applymap)
# ─────────────────────────────────────────────
def colorir_abc(val):
    info = COR_ABC.get(str(val).strip(), {"bg": "transparent", "fg": "inherit"})
    return f"background-color: {info['bg']}; color: {info['fg']}; font-weight: bold; text-align: center;"


# ─────────────────────────────────────────────
# ABA ESTOQUE & ABC
# ─────────────────────────────────────────────
def aba_estoque(estoque_df, vendas_df):
    st.title("📦 Estoque & ABC")

    if estoque_df.empty:
        st.info("Carregue o arquivo de estoque.")
        return

    # ── Parâmetros de análise ──
    st.subheader("⚙️ Parâmetros de Análise")
    col1, col2, col3 = st.columns(3)

    data_min = pd.Timestamp("2025-01-01")
    data_max = pd.Timestamp("today")
    if not vendas_df.empty and "data" in vendas_df.columns:
        datas_validas = vendas_df["data"].dropna()
        if not datas_validas.empty:
            data_min = datas_validas.min()
            data_max = datas_validas.max()

    with col1:
        data_ini = st.date_input("De", value=data_min.date(), key="est_ini")
    with col2:
        data_fim = st.date_input("Até", value=data_max.date(), key="est_fim")
    with col3:
        fabricantes_disp = ["Todos"] + sorted(estoque_df["fabricante"].dropna().unique().tolist())
        fab_sel = st.selectbox("Fabricante", fabricantes_disp, key="est_fab")

    # ── Filtrar estoque por fabricante ──
    df_filtrado = estoque_df.copy()
    if fab_sel != "Todos":
        df_filtrado = df_filtrado[df_filtrado["fabricante"] == fab_sel]

    # ── Calcular ABC IA ──
    df_abc = classificar_abc_ia(df_filtrado, vendas_df, data_ini, data_fim)

    # ── KPIs ──
    st.markdown("---")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("SKUs no Estoque", fmt_qtde(len(df_abc)))
    k2.metric("Total de Unidades", fmt_qtde(df_abc["qtde"].sum()))
    custo_total = df_abc["custo_total"].sum() if "custo_total" in df_abc.columns else 0
    k3.metric("Valor Total (Custo)", fmt_brl(custo_total))
    k4.metric("Fabricantes Ativos", df_abc["fabricante"].nunique())

    st.markdown("---")

    # ── Tabela de Estoque ──
    st.subheader("📋 Tabela de Estoque")

    colunas_exibir = []
    col_rename = {}

    for c, label in [
        ("fabricante", "Fabricante"),
        ("produto",    "Produto"),
        ("descricao",  "Descrição"),
        ("abc",        "ABC Orig."),
        ("qtde",       "Qtde"),
        ("custo_unit", "Custo Unit. (R$)"),
        ("custo_total","Custo Total (R$)"),
        ("qtde_vendida","Vendas (Unid)"),
        ("vl_vendido", "Vendas (R$)"),
        ("classe_abc_unid", "ABC IA (Unid)"),
        ("classe_abc_valor", "ABC IA (R$)"),
    ]:
        if c in df_abc.columns:
            colunas_exibir.append(c)
            col_rename[c] = label

    df_show = df_abc[colunas_exibir].rename(columns=col_rename).reset_index(drop=True)

    # Formatar colunas monetárias
    for col_label in ["Custo Unit. (R$)", "Custo Total (R$)", "Vendas (R$)"]:
        if col_label in df_show.columns:
            df_show[col_label] = df_show[col_label].apply(fmt_brl)

    # Aplicar cores nas colunas ABC IA usando .map (pandas moderno)
    cols_abc_ia = [c for c in ["ABC IA (Unid)", "ABC IA (R$)"] if c in df_show.columns]

    if cols_abc_ia:
        styled = df_show.style.map(colorir_abc, subset=cols_abc_ia)
    else:
        styled = df_show.style

    st.dataframe(styled, use_container_width=True, height=500)

    # ── Gráfico ABC ──
    if "classe_abc_unid" in df_abc.columns:
        st.markdown("---")
        st.subheader("📊 Distribuição ABC IA (Unidades)")
        contagem = df_abc["classe_abc_unid"].value_counts().reset_index()
        contagem.columns = ["Classe", "Qtde SKUs"]
        ordem = ["A+", "A", "B", "C", "X"]
        contagem["Classe"] = pd.Categorical(contagem["Classe"], categories=ordem, ordered=True)
        contagem = contagem.sort_values("Classe")
        cores = [COR_ABC.get(c, {}).get("bg", "#888") for c in contagem["Classe"]]
        fig = px.bar(
            contagem,
            x="Classe",
            y="Qtde SKUs",
            color="Classe",
            color_discrete_sequence=cores,
            text="Qtde SKUs",
            title="SKUs por Classe ABC IA (Unidades Vendidas)",
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(showlegend=False, plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)


# ─────────────────────────────────────────────
# ABA VENDAS & DEMANDA
# ─────────────────────────────────────────────
def aba_vendas(vendas_df):
    st.title("📈 Vendas & Demanda")

    if vendas_df.empty:
        st.info("Carregue o arquivo de vendas.")
        return

    col1, col2 = st.columns(2)
    with col1:
        marcas = ["Todas"] + sorted(vendas_df["marca"].dropna().unique().tolist()) if "marca" in vendas_df.columns else ["Todas"]
        marca_sel = st.selectbox("Marca", marcas, key="vnd_marca")
    with col2:
        grupos = ["Todos"] + sorted(vendas_df["grupo"].dropna().unique().tolist()) if "grupo" in vendas_df.columns else ["Todos"]
        grupo_sel = st.selectbox("Grupo", grupos, key="vnd_grupo")

    df = vendas_df.copy()
    if marca_sel != "Todas" and "marca" in df.columns:
        df = df[df["marca"] == marca_sel]
    if grupo_sel != "Todos" and "grupo" in df.columns:
        df = df[df["grupo"] == grupo_sel]

    st.markdown("---")
    k1, k2, k3 = st.columns(3)
    k1.metric("Registros", fmt_qtde(len(df)))
    if "qtde" in df.columns:
        k2.metric("Unidades Vendidas", fmt_qtde(df["qtde"].sum()))
    if "vl_total" in df.columns:
        k3.metric("Valor Total", fmt_brl(df["vl_total"].sum()))

    if "data" in df.columns and "vl_total" in df.columns:
        st.markdown("---")
        df_mes = df.groupby(df["data"].dt.to_period("M")).agg(
            vl_total=("vl_total", "sum"),
            qtde=("qtde", "sum")
        ).reset_index()
        df_mes["data"] = df_mes["data"].astype(str)
        fig = px.bar(df_mes, x="data", y="vl_total", title="Vendas Mensais (R$)", text_auto=True)
        fig.update_layout(plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.subheader("📋 Detalhes das Vendas")
    st.dataframe(df.head(5000), use_container_width=True, height=400)


# ─────────────────────────────────────────────
# ABA COBERTURA
# ─────────────────────────────────────────────
def aba_cobertura(estoque_df, vendas_df):
    st.title("📊 Cobertura de Estoque")

    if estoque_df.empty:
        st.info("Carregue o arquivo de estoque.")
        return
    if vendas_df.empty:
        st.info("Carregue o arquivo de vendas.")
        return

    # Calcular média diária de vendas por produto
    if "data" in vendas_df.columns and "produto" in vendas_df.columns and "qtde" in vendas_df.columns:
        dias = max((vendas_df["data"].max() - vendas_df["data"].min()).days, 1)
        media = vendas_df.groupby("produto")["qtde"].sum() / dias
        media = media.reset_index()
        media.columns = ["produto", "media_diaria"]

        df = estoque_df.copy()
        df["produto"] = df["produto"].astype(str).str.strip()
        media["produto"] = media["produto"].astype(str).str.strip()
        df = df.merge(media, on="produto", how="left")
        df["media_diaria"] = df["media_diaria"].fillna(0)
        df["cobertura_dias"] = df.apply(
            lambda r: round(r["qtde"] / r["media_diaria"]) if r["media_diaria"] > 0 else None, axis=1
        )

        st.markdown("---")
        col_exibir = [c for c in ["fabricante", "produto", "descricao", "qtde", "media_diaria", "cobertura_dias"] if c in df.columns]
        col_labels = {
            "fabricante": "Fabricante",
            "produto": "Produto",
            "descricao": "Descrição",
            "qtde": "Estoque Atual",
            "media_diaria": "Média Diária Vendas",
            "cobertura_dias": "Cobertura (dias)",
        }
        st.dataframe(
            df[col_exibir].rename(columns=col_labels).sort_values("Cobertura (dias)"),
            use_container_width=True,
            height=500,
        )
    else:
        st.warning("Dados insuficientes para calcular cobertura.")


# ─────────────────────────────────────────────
# ABA SUGESTÃO DE COMPRA
# ─────────────────────────────────────────────
def aba_sugestao(estoque_df, vendas_df):
    st.title("🛒 Sugestão de Compra")

    if estoque_df.empty or vendas_df.empty:
        st.info("Carregue estoque e vendas para gerar sugestões.")
        return

    cobertura_alvo = st.slider("Cobertura desejada (dias)", 15, 120, 45, key="sug_cob")

    if "data" in vendas_df.columns and "produto" in vendas_df.columns and "qtde" in vendas_df.columns:
        dias = max((vendas_df["data"].max() - vendas_df["data"].min()).days, 1)
        media = vendas_df.groupby("produto")["qtde"].sum() / dias
        media = media.reset_index()
        media.columns = ["produto", "media_diaria"]

        df = estoque_df.copy()
        df["produto"] = df["produto"].astype(str).str.strip()
        media["produto"] = media["produto"].astype(str).str.strip()
        df = df.merge(media, on="produto", how="left")
        df["media_diaria"] = df["media_diaria"].fillna(0)
        df["necessidade"] = df["media_diaria"] * cobertura_alvo
        df["sugestao_compra"] = (df["necessidade"] - df["qtde"]).clip(lower=0).round()
        df = df[df["sugestao_compra"] > 0]

        if "custo_unit" in df.columns:
            df["valor_sugestao"] = df["sugestao_compra"] * df["custo_unit"]

        col_exibir = [c for c in ["fabricante", "produto", "descricao", "qtde", "media_diaria", "sugestao_compra", "valor_sugestao"] if c in df.columns]
        col_labels = {
            "fabricante": "Fabricante",
            "produto": "Produto",
            "descricao": "Descrição",
            "qtde": "Estoque Atual",
            "media_diaria": "Média Diária",
            "sugestao_compra": "Sugestão (Unid)",
            "valor_sugestao": "Valor Sugestão (R$)",
        }

        df_show = df[col_exibir].rename(columns=col_labels).sort_values("Sugestão (Unid)", ascending=False)
        if "Valor Sugestão (R$)" in df_show.columns:
            df_show["Valor Sugestão (R$)"] = df_show["Valor Sugestão (R$)"].apply(fmt_brl)

        st.markdown("---")
        st.metric("Total de SKUs com sugestão", fmt_qtde(len(df_show)))
        st.dataframe(df_show, use_cont