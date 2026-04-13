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

def fmt_brl(valor):
    try:
        return f"R$ {valor:_.2f}".replace(".", ",").replace("_", ".")
    except Exception:
        return valor

# ─────────────────────────────────────────────
# CARREGAMENTO DE DADOS
# ─────────────────────────────────────────────
@st.cache_data
def carregar_estoque(file_bytes):
    try:
        xls = pd.ExcelFile(file_bytes)
        aba = xls.sheet_names[0]
        df_raw = xls.parse(aba, header=None)

        # Encontra linha do cabeçalho buscando pela coluna "Produto"
        header_row = None
        for i, row in df_raw.iterrows():
            if row.astype(str).str.contains("Produto", case=False).any():
                header_row = i
                break

        if header_row is None:
            return pd.DataFrame()

        df = xls.parse(aba, header=header_row)
        df.columns = df.columns.str.strip()

        # Remove colunas completamente vazias
        df = df.dropna(axis=1, how="all")

        # Renomeia colunas relevantes
        rename_map = {}
        for col in df.columns:
            col_lower = str(col).lower().strip()
            if "fabr" in col_lower and "fabricante" not in rename_map.values():
                rename_map[col] = "fabricante"
            elif col_lower == "produto":
                rename_map[col] = "produto"
            elif "desc" in col_lower and "descricao" not in rename_map.values():
                rename_map[col] = "descricao"
            elif "grupo" in col_lower:
                rename_map[col] = "grupo"
            elif "btu" in col_lower:
                rename_map[col] = "btu"
            elif "ciclo" in col_lower:
                rename_map[col] = "ciclo"
            elif col_lower in ["qtde", "qtd", "quantidade", "saldo"]:
                rename_map[col] = "qtde"
            elif "custo" in col_lower or ("vl" in col_lower and "unit" in col_lower):
                rename_map[col] = "custo_unit"
            elif "total" in col_lower and "vl" in col_lower:
                rename_map[col] = "custo_total"

        df = df.rename(columns=rename_map)

        colunas_necessarias = ["fabricante", "produto", "descricao", "qtde"]
        for col in colunas_necessarias:
            if col not in df.columns:
                return pd.DataFrame()

        # Filtra fabricantes inválidos
        df["fabricante"] = pd.to_numeric(df["fabricante"], errors="coerce")
        df = df[~df["fabricante"].isin(FABRICANTES_IGNORAR)]
        df = df.dropna(subset=["fabricante", "produto"])

        # Converte numéricos
        df["qtde"] = pd.to_numeric(df["qtde"], errors="coerce").fillna(0)
        if "custo_unit" in df.columns:
            df["custo_unit"] = pd.to_numeric(df["custo_unit"], errors="coerce").fillna(0)
        if "custo_total" in df.columns:
            df["custo_total"] = pd.to_numeric(df["custo_total"], errors="coerce").fillna(0)

        # Mapeia nome do fabricante
        df["nome_fabricante"] = df["fabricante"].map(MAPA_FABRICANTES_ESTOQUE).fillna("Outros")

        df = df[df["qtde"] > 0].reset_index(drop=True)
        return df

    except Exception as e:
        st.error(f"Erro ao carregar estoque: {e}")
        return pd.DataFrame()


@st.cache_data
def carregar_vendas(file_bytes):
    try:
        conteudo = file_bytes.decode("utf-8", errors="replace")
    except Exception:
        conteudo = file_bytes.decode("latin-1", errors="replace")

    from io import StringIO
    # Detecta separador
    primeira_linha = conteudo.split("\n")[0]
    sep = ";" if ";" in primeira_linha else ","

    df = pd.read_csv(StringIO(conteudo), sep=sep, dtype=str, on_bad_lines="skip")
    df.columns = df.columns.str.strip()

    # Normaliza nomes de colunas
    rename_map = {}
    for col in df.columns:
        col_lower = col.lower().strip()
        if "emissao" in col_lower or "emissão" in col_lower:
            rename_map[col] = "data"
        elif "pedido" in col_lower:
            rename_map[col] = "pedido"
        elif "marca" in col_lower:
            rename_map[col] = "marca"
        elif "grupo" in col_lower:
            rename_map[col] = "grupo"
        elif col_lower == "btu":
            rename_map[col] = "btu"
        elif "ciclo" in col_lower:
            rename_map[col] = "ciclo"
        elif col_lower == "produto":
            rename_map[col] = "produto"
        elif "desc" in col_lower:
            rename_map[col] = "descricao"
        elif col_lower in ["qtde", "qtd", "quantidade"]:
            rename_map[col] = "qtde"
        elif "custo" in col_lower:
            rename_map[col] = "custo_unit"
        elif "total" in col_lower:
            rename_map[col] = "vl_total"

    df = df.rename(columns=rename_map)

    if "pedido" not in df.columns:
        df["pedido"] = None

    df["data"] = pd.to_datetime(df["data"], dayfirst=True, errors="coerce")
    df["qtde"] = pd.to_numeric(df["qtde"], errors="coerce").fillna(0)
    df["custo_unit"] = pd.to_numeric(df.get("custo_unit", 0), errors="coerce").fillna(0)
    df["vl_total"] = pd.to_numeric(df.get("vl_total", 0), errors="coerce").fillna(0)
    df["produto"] = df["produto"].astype(str).str.strip()

    df = df.dropna(subset=["data"]).reset_index(drop=True)
    return df


# ─────────────────────────────────────────────
# FUNÇÕES AUXILIARES
# ─────────────────────────────────────────────
def classificar_abc(df_vendas, coluna_ref="qtde"):
    if df_vendas.empty:
        return pd.DataFrame()
    resumo = (
        df_vendas.groupby("produto")[coluna_ref]
        .sum()
        .reset_index()
        .sort_values(coluna_ref, ascending=False)
    )
    resumo["pct_acum"] = resumo[coluna_ref].cumsum() / resumo[coluna_ref].sum()
    resumo["classe"] = resumo["pct_acum"].apply(
        lambda x: "A" if x <= 0.80 else ("B" if x <= 0.95 else "C")
    )
    return resumo


def classificar_abc_ia(df_vendas, df_estoque):
    """ABC IA com faixas A+/A/B/C/X baseadas em unidades e valor."""
    if df_vendas.empty or df_estoque.empty:
        return df_estoque.copy()

    # ABC por unidades
    resumo_unid = (
        df_vendas.groupby("produto")["qtde"]
        .sum()
        .reset_index()
        .rename(columns={"qtde": "total_unid"})
        .sort_values("total_unid", ascending=False)
    )
    resumo_unid["pct_acum_unid"] = (
        resumo_unid["total_unid"].cumsum() / resumo_unid["total_unid"].sum()
    )

    def faixa_abc(pct):
        if pct <= 0.50:
            return "A+"
        elif pct <= 0.80:
            return "A"
        elif pct <= 0.95:
            return "B"
        else:
            return "C"

    resumo_unid["classe_abc_unid"] = resumo_unid["pct_acum_unid"].apply(faixa_abc)

    # ABC por valor
    resumo_valor = (
        df_vendas.groupby("produto")["vl_total"]
        .sum()
        .reset_index()
        .rename(columns={"vl_total": "total_valor"})
        .sort_values("total_valor", ascending=False)
    )
    resumo_valor["pct_acum_valor"] = (
        resumo_valor["total_valor"].cumsum() / resumo_valor["total_valor"].sum()
    )
    resumo_valor["classe_abc_valor"] = resumo_valor["pct_acum_valor"].apply(faixa_abc)

    df_out = df_estoque.copy()
    df_out["produto"] = df_out["produto"].astype(str).str.strip()

    df_out = df_out.merge(
        resumo_unid[["produto", "total_unid", "classe_abc_unid"]],
        on="produto", how="left"
    )
    df_out = df_out.merge(
        resumo_valor[["produto", "total_valor", "classe_abc_valor"]],
        on="produto", how="left"
    )

    # Produtos sem venda = X
    df_out["classe_abc_unid"] = df_out["classe_abc_unid"].fillna("X")
    df_out["classe_abc_valor"] = df_out["classe_abc_valor"].fillna("X")
    df_out["total_unid"] = df_out["total_unid"].fillna(0)
    df_out["total_valor"] = df_out["total_valor"].fillna(0)

    return df_out


def analisar_kits_msp(df_vendas, top_n=10):
    """Analisa combinações de produtos MSP vendidos juntos no mesmo pedido."""
    if "pedido" not in df_vendas.columns or df_vendas["pedido"].isna().all():
        return pd.DataFrame()

    df_msp = df_vendas[df_vendas["grupo"].str.upper().str.strip() == "MSP"].copy()
    if df_msp.empty:
        return pd.DataFrame()

    pedidos = df_msp.groupby("pedido")["produto"].apply(list)
    contagem = Counter()
    for produtos in pedidos:
        produtos_unicos = list(set(produtos))
        if len(produtos_unicos) >= 2:
            for combo in combinations(sorted(produtos_unicos), 2):
                contagem[combo] += 1

    if not contagem:
        return pd.DataFrame()

    df_kits = pd.DataFrame(
        [(a, b, n) for (a, b), n in contagem.most_common(top_n)],
        columns=["Produto A", "Produto B", "Frequência"]
    )
    return df_kits


# ─────────────────────────────────────────────
# CORES ABC
# ─────────────────────────────────────────────
COR_ABC = {
    "A+": ("background-color: #B8860B; color: #FFFFFF; font-weight: bold;"),
    "A":  ("background-color: #FFD700; color: #1a1a1a; font-weight: bold;"),
    "B":  ("background-color: #FFA500; color: #1a1a1a; font-weight: bold;"),
    "C":  ("background-color: #FFFF99; color: #1a1a1a;"),
    "X":  ("background-color: #CCCCCC; color: #555555;"),
}

def colorir_abc(val):
    return COR_ABC.get(str(val).strip(), "")


# ─────────────────────────────────────────────
# ABA ESTOQUE & ABC
# ─────────────────────────────────────────────
def aba_estoque(estoque_df, vendas_df):
    st.header("📦 Estoque & Classificação ABC IA")

    if estoque_df.empty:
        st.warning("Carregue o arquivo de estoque para visualizar esta aba.")
        return

    # ── Sidebar filtros ──
    st.sidebar.markdown("---")
    st.sidebar.subheader("Filtros — Estoque & ABC")

    fabricantes_disp = sorted(estoque_df["nome_fabricante"].dropna().unique().tolist())
    fab_sel = st.sidebar.multiselect(
        "Fabricante", fabricantes_disp, default=fabricantes_disp, key="fab_estoque"
    )

    data_min = vendas_df["data"].min() if not vendas_df.empty else pd.Timestamp("2024-01-01")
    data_max = vendas_df["data"].max() if not vendas_df.empty else pd.Timestamp.today()
    periodo = st.sidebar.date_input(
        "Período de vendas para ABC",
        value=(data_min.date(), data_max.date()),
        key="periodo_estoque"
    )

    # Aplica filtro de fabricante no estoque
    df_est = estoque_df[estoque_df["nome_fabricante"].isin(fab_sel)].copy()

    # Aplica filtro de período nas vendas
    df_vend = vendas_df.copy()
    if len(periodo) == 2:
        d0, d1 = pd.Timestamp(periodo[0]), pd.Timestamp(periodo[1])
        df_vend = df_vend[(df_vend["data"] >= d0) & (df_vend["data"] <= d1)]

    # Classifica ABC IA
    df_abc = classificar_abc_ia(df_vend, df_est)

    # ── Métricas topo ──
    total_produtos = len(df_abc)
    total_qtde = df_abc["qtde"].sum()
    total_valor = df_abc["custo_total"].sum() if "custo_total" in df_abc.columns else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("Produtos distintos", f"{total_produtos:,}".replace(",", "."))
    col2.metric("Total de unidades", f"{total_qtde:,.0f}".replace(",", "."))
    col3.metric("Valor total em estoque", fmt_brl(total_valor))

    st.markdown("---")

    # ── Tabela principal ──
    colunas_exibir = {
        "nome_fabricante": "Fabricante",
        "produto":         "Cód. Produto",
        "descricao":       "Descrição",
        "grupo":           "Grupo",
        "btu":             "BTU",
        "ciclo":           "Ciclo",
        "qtde":            "Qtde",
        "custo_unit":      "Custo Unit.",
        "custo_total":     "Custo Total",
        "total_unid":      "Venda (Unid)",
        "total_valor":     "Venda (R$)",
        "classe_abc_unid": "ABC IA (Unid)",
        "classe_abc_valor":"ABC IA (R$)",
    }

    colunas_presentes = {k: v for k, v in colunas_exibir.items() if k in df_abc.columns}
    df_tabela = df_abc[list(colunas_presentes.keys())].rename(columns=colunas_presentes)

    # Formatação monetária
    for col_orig, col_novo in colunas_presentes.items():
        if col_orig in ["custo_unit", "custo_total", "total_valor"]:
            df_tabela[col_novo] = df_tabela[col_novo].apply(fmt_brl)

    # Formatação numérica
    for col_orig, col_novo in colunas_presentes.items():
        if col_orig in ["qtde", "total_unid"]:
            df_tabela[col_novo] = df_tabela[col_novo].apply(
                lambda x: f"{int(x):,}".replace(",", ".") if pd.notna(x) else "0"
            )

    # Aplica cores ABC com .map() (pandas 2.x)
    cols_abc_exib = [v for k, v in colunas_presentes.items() if k in ["classe_abc_unid", "classe_abc_valor"]]
    styled = df_tabela.style
    for col in cols_abc_exib:
        styled = styled.map(colorir_abc, subset=[col])

    st.dataframe(styled, use_container_width=True, height=500)

    # ── Gráfico distribuição ABC ──
    st.markdown("### Distribuição ABC IA por Unidades")
    if "ABC IA (Unid)" in df_tabela.columns:
        contagem_abc = df_tabela["ABC IA (Unid)"].value_counts().reset_index()
        contagem_abc.columns = ["Classe", "Quantidade"]
        ordem = ["A+", "A", "B", "C", "X"]
        contagem_abc["Classe"] = pd.Categorical(contagem_abc["Classe"], categories=ordem, ordered=True)
        contagem_abc = contagem_abc.sort_values("Classe")
        cores_graf = {"A+": "#B8860B", "A": "#FFD700", "B": "#FFA500", "C": "#FFFF99", "X": "#CCCCCC"}
        fig = px.bar(
            contagem_abc, x="Classe", y="Quantidade",
            color="Classe", color_discrete_map=cores_graf,
            title="Produtos por Classe ABC IA (Unidades)"
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── Análise Kits MSP ──
    if "pedido" in df_vend.columns and not df_vend["pedido"].isna().all():
        st.markdown("### 🔗 Kits MSP mais frequentes")
        df_kits = analisar_kits_msp(df_vend)
        if not df_kits.empty:
            st.dataframe(df_kits, use_container_width=True)
        else:
            st.info("Nenhum kit MSP identificado no período selecionado.")


# ─────────────────────────────────────────────
# ABA VENDAS & DEMANDA
# ─────────────────────────────────────────────
def aba_vendas(vendas_df):
    st.header("📈 Vendas & Demanda")

    if vendas_df.empty:
        st.warning("Carregue o arquivo de vendas para visualizar esta aba.")
        return

    st.sidebar.markdown("---")
    st.sidebar.subheader("Filtros — Vendas")

    data_min = vendas_df["data"].min().date()
    data_max = vendas_df["data"].max().date()
    periodo = st.sidebar.date_input(
        "Período", value=(data_min, data_max), key="periodo_vendas"
    )

    marcas_disp = sorted(vendas_df["marca"].dropna().unique().tolist()) if "marca" in vendas_df.columns else []
    marcas_sel = st.sidebar.multiselect("Marca", marcas_disp, default=marcas_disp, key="marcas_vendas")

    df = vendas_df.copy()
    if len(periodo) == 2:
        d0, d1 = pd.Timestamp(periodo[0]), pd.Timestamp(periodo[1])
        df = df[(df["data"] >= d0) & (df["data"] <= d1)]
    if marcas_sel and "marca" in df.columns:
        df = df[df["marca"].isin(marcas_sel)]

    col1, col2, col3 = st.columns(3)
    col1.metric("Registros", f"{len(df):,}".replace(",", "."))
    col2.metric("Unidades vendidas", f"{df['qtde'].sum():,.0f}".replace(",", "."))
    col3.metric("Faturamento total", fmt_brl(df["vl_total"].sum()))

    st.markdown("---")

    # Vendas por mês
    df["mes"] = df["data"].dt.to_period("M").astype(str)
    vendas_mes = df.groupby("mes")["qtde"].sum().reset_index()
    fig = px.bar(vendas_mes, x="mes", y="qtde", title="Vendas mensais (unidades)")
    st.plotly_chart(fig, use_container_width=True)

    # Top 20 produtos
    st.markdown("### Top 20 produtos mais vendidos")
    top20 = (
        df.groupby(["produto", "descricao"])["qtde"]
        .sum()
        .reset_index()
        .sort_values("qtde", ascending=False)
        .head(20)
    )
    top20["qtde"] = top20["qtde"].apply(lambda x: f"{int(x):,}".replace(",", "."))
    st.dataframe(top20, use_container_width=True)

    # Vendas por marca
    if "marca" in df.columns:
        st.markdown("### Vendas por Marca")
        por_marca = df.groupby("marca")["qtde"].sum().reset_index().sort_values("qtde", ascending=False)
        fig2 = px.pie(por_marca, names="marca", values="qtde", title="Participação por Marca")
        st.plotly_chart(fig2, use_container_width=True)


# ─────────────────────────────────────────────
# ABA COBERTURA
# ─────────────────────────────────────────────
def aba_cobertura(estoque_df, vendas_df):
    st.header("📊 Cobertura de Estoque")

    if estoque_df.empty or vendas_df.empty:
        st.warning("Carregue ambos os arquivos para calcular a cobertura.")
        return

    st.sidebar.markdown("---")
    st.sidebar.subheader("Filtros — Cobertura")

    data_min = vendas_df["data"].min().date()
    data_max = vendas_df["data"].max().date()
    periodo = st.sidebar.date_input(
        "Período de referência", value=(data_min, data_max), key="periodo_cobertura"
    )

    df_vend = vendas_df.copy()
    if len(periodo) == 2:
        d0, d1 = pd.Timestamp(periodo[0]), pd.Timestamp(periodo[1])
        df_vend = df_vend[(df_vend["data"] >= d0) & (df_vend["data"] <= d1)]

    n_meses = max(1, (pd.Timestamp(periodo[1]) - pd.Timestamp(periodo[0])).days / 30)

    media_mensal = (
        df_vend.groupby("produto")["qtde"]
        .sum()
        .reset_index()
        .rename(columns={"qtde": "total_vendido"})
    )
    media_mensal["media_mes"] = media_mensal["total_vendido"] / n_meses

    df_cob = estoque_df[["produto", "descricao", "nome_fabricante", "qtde"]].copy()
    df_cob = df_cob.merge(media_mensal[["produto", "media_mes"]], on="produto", how="left")
    df_cob["media_mes"] = df_cob["media_mes"].fillna(0)
    df_cob["cobertura_meses"] = df_cob.apply(
        lambda r: round(r["qtde"] / r["media_mes"], 1) if r["media_mes"] > 0 else None, axis=1
    )

    def status_cob(v):
        if v is None:
            return "⚠️ Sem venda"
        if v < 1:
            return "🔴 Crítico"
        if v < 2:
            return "🟡 Baixo"
        if v > 6:
            return "🔵 Excesso"
        return "🟢 OK"

    df_cob["Status"] = df_cob["cobertura_meses"].apply(status_cob)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Crítico (<1 mês)", len(df_cob[df_cob["Status"] == "🔴 Crítico"]))
    col2.metric("Baixo (1-2 meses)", len(df_cob[df_cob["Status"] == "🟡 Baixo"]))
    col3.metric("OK (2-6 meses)", len(df_cob[df_cob["Status"] == "🟢 OK"]))
    col4.metric("Excesso (>6 meses)", len(df_cob[df_cob["Status"] == "🔵 Excesso"]))

    st.dataframe(
        df_cob.rename(columns={
            "nome_fabricante": "Fabricante",
            "produto": "Produto",
            "descricao": "Descrição",
            "qtde": "Qtde Estoque",
            "media_mes": "Média/Mês",
            "cobertura_meses": "Cobertura (meses)"
        }),
        use_container_width=True,
        height=500
    )


# ─────────────────────────────────────────────
# ABA SUGESTÃO DE COMPRA
# ─────────────────────────────────────────────
def aba_sugestao(estoque_df, vendas_df):
    st.header("🛒 Sugestão de Compra")

    if estoque_df.empty or vendas_df.empty:
        st.warning("Carregue ambos os arquivos para gerar sugestões.")
        return

    st.sidebar.markdown("---")
    st.sidebar.subheader("Parâmetros — Sugestão")

    cobertura_alvo = st.sidebar.slider(
        "Cobertura alvo (meses)", min_value=1, max_value=6, value=3, key="cob_alvo"
    )
    data_min = vendas_df["data"].min().date()
    data_max = vendas_df["data"].max().date()
    periodo = st.sidebar.date_input(
        "Período de referência", value=(data_min, data_max), key="periodo_sugestao"
    )

    df_vend = vendas_df.copy()
    if len(periodo) == 2:
        d0, d1 = pd.Timestamp(periodo[0]), pd.Timestamp(periodo[1])
        df_vend = df_vend[(df_vend["data"] >= d0) & (df_vend["data"] <= d1)]

    n_meses = max(1, (pd.Timestamp(periodo[1]) - pd.Timestamp(periodo[0])).days / 30)

    media_mensal = (
        df_vend.groupby("produto")["qtde"]
        .sum()
        .reset_index()
        .rename(columns={"qtde": "total_vendido"})
    )
    media_mensal["media_mes"] = media_mensal["total_vendido"] / n_meses

    df_sug = estoque_df[["produto", "descricao", "nome_fabricante", "grupo", "qtde", "custo_unit"]].copy()
    df_sug = df_sug.merge(media_mensal[["produto", "media_mes"]], on="produto", how="left")
    df_sug["media_mes"] = df_sug["media_mes"].fillna(0)

    df_sug["estoque_alvo"] = df_sug["media_mes"] * cobertura_alvo
    df_sug["sugestao_compra"] = (df_sug["estoque_alvo"] - df_sug["qtde"]).clip(lower=0).round(0).astype(int)
    df_sug["valor_sugestao"] = df_sug["sugestao_compra"] * df_sug["custo_unit"]

    df_sug = df_sug[df_sug["sugestao_compra"] > 0].sort_values("valor_sugestao", ascending=False)

    col1, col2 = st.columns(2)
    col1.metric("Itens para comprar", f"{len(df_sug):,}".replace(",", "."))
    col2.metric("Investimento estimado", fmt_brl(df_sug["valor_sugestao"].sum()))

    df_exib = df_sug.rename(columns={
        "nome_fabricante": "Fabricante",
        "produto": "Produto",
        "descricao": "Descrição",
        "grupo": "Grupo",
        "qtde": "Qtde Atual",
        "media_mes": "Média/Mês",
        "estoque_alvo": "Alvo",
        "sugestao_compra": "Sugestão",
        "custo_unit": "Custo Unit.",
        "valor_sugestao": "Valor Total",
    })

    for col in ["Custo Unit.", "Valor Total"]:
        if col in df_exib.columns:
            df_exib[col] = df_exib[col].apply(fmt_brl)

    st.dataframe(df_exib, use_container_width=True, height=500)


# ─────────────────────────────────────────────
# ABA FORNECEDORES
# ─────────────────────────────────────────────
def aba_fornecedores(estoque_df):
    st.header("🏭 Fornecedores")

    if estoque_df.empty:
        st.warning("Carregue o arquivo de estoque para visualizar esta aba.")
        return

    resumo = (
        estoque_df.groupby("nome_fabricante")
        .agg(
            produtos=("produto", "count"),
            unidades=("qtde", "sum"),
            valor_total=("custo_total", "sum"),
        )
        .reset_index()
        .sort_values("valor_total", ascending=False)
    )

    col1, col2 = st.columns(2)
    with col1:
        fig = px.bar(
            resumo, x="nome_fabricante", y="unidades",
            title="Unidades em estoque por fabricante",
            color="nome_fabricante"
        )
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        fig2 = px.pie(
            resumo, names="nome_fabricante", values="valor_total",
            title="Valor em estoque por fabricante"
        )
        st.plotly_chart(fig2, use_container_width=True)

    resumo["valor_total"] = resumo["valor_total"].apply(fmt_brl)
    resumo["unidades"] = resumo["unidades"].apply(lambda x: f"{int(x):,}".replace(",", "."))

    st.dataframe(
        resumo.rename(columns={
            "nome_fabricante": "Fabricante",
            "produtos": "Produtos",
            "unidades": "Unidades",
            "valor_total": "Valor Total"
        }),
        use_container_width=True
    )

    # Logos
    st.markdown("### Fabricantes com logo")
    cols = st.columns(len(LOGOS))
    for i, (nome, path) in enumerate(LOGOS.items()):
        with cols[i]:
            try:
                st.image(path, caption=nome, width=80)
            except Exception:
                st.caption(nome)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    st.title("❄️ Motor de Compras — Ar Condicionado")

    st.sidebar.header("📂 Arquivos")
    est_file = st.sidebar.file_uploader("Estoque (.xlsx)", type=["xlsx"], key="est_up")
    vnd_file = st.sidebar.file_uploader("Vendas (.csv)", type=["csv"], key="vnd_up")

    estoque_df = pd.DataFrame()
    vendas_df  = pd.DataFrame()

    if est_file:
        estoque_df = carregar_estoque(est_file.read())
        if not estoque_df.empty:
            st.sidebar.success(f"✅ Estoque: {len(estoque_df)} linhas carregadas")
        else:
            st.sidebar.error("❌ Estoque: 0 produtos — verifique o arquivo")

    if vnd_file:
        vendas_df = carregar_vendas(vnd_file.read())
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

    with tabs[0]: aba_estoque(estoque_df, vendas_df)
    with tabs[1]: aba_vendas(vendas_df)
    with tabs[2]: aba_cobertura(estoque_df, vendas_df)
    with tabs[3]: aba_sugestao(estoque_df, vendas_df)
    with tabs[4]: aba_fornecedores(estoque_df)


if __name__ == "__main__":
    main()