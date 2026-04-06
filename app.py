import streamlit as st
import pandas as pd
import numpy as np
import re
from io import StringIO

# ─────────────────────────────────────────────
# CONFIGURAÇÃO DA PÁGINA
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Gestão de Compras",
    page_icon="❄️",
    layout="wide",
)

# ─────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────
MAPA_FABRICANTES = {
    "002": "LG",
    "003": "Samsung",
    "004": "Midea",
    "005": "Daikin",
    "006": "Agratto",
    "007": "Gree",
    "010": "Trane",
    "011": "TCL",
}

FABRICANTES_IGNORAR = {"900", "995", "998", "999"}

NORMALIZA_MARCA = {
    "SPRINGER MIDEA": "Midea",
    "SPRINGER":       "Midea",
    "MIDEA":          "Midea",
    "DAIKIN":         "Daikin",
    "LG":             "LG",
    "SAMSUNG":        "Samsung",
    "GREE":           "Gree",
    "TRANE":          "Trane",
    "TCL":            "TCL",
    "AGRATTO":        "Agratto",
}

MESES_PT = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr",
    5: "Mai", 6: "Jun", 7: "Jul", 8: "Ago",
    9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
}

COBERTURA_CRITICA = 1.5   # meses
COBERTURA_ALERTA  = 3.0   # meses
MESES_SUGESTAO    = 3     # quantos meses de estoque sugerido

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def extrair_btu_desc(descricao: str) -> float | None:
    """Tenta extrair BTU da descrição do produto."""
    if not isinstance(descricao, str):
        return None
    m = re.search(r'\b(7000|9000|9500|12000|18000|21000|24000|28000|30000|34000|36000|38000|42000|48000|56000|57000|60000)\b', descricao)
    if m:
        return float(m.group(1))
    m2 = re.search(r'\b(\d{2})\s*(?:BTU|btu|Btu)', descricao)
    if m2:
        return float(m2.group(1)) * 1000
    return None


def limpar_numero(series: pd.Series) -> pd.Series:
    """Converte strings com vírgula decimal para float."""
    return pd.to_numeric(
        series.astype(str)
        .str.strip()
        .str.replace(r'\s', '', regex=True)
        .str.replace('.', '', regex=False)
        .str.replace(',', '.', regex=False),
        errors='coerce'
    )


def decode_bytes(conteudo: bytes) -> str:
    """Detecta encoding de arquivos exportados por ERPs brasileiros."""
    for enc in ["utf-8-sig", "latin-1", "cp1252", "iso-8859-1", "utf-8"]:
        try:
            return conteudo.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return conteudo.decode("latin-1", errors="replace")


# ─────────────────────────────────────────────
# CARREGAMENTO: ESTOQUE
# ─────────────────────────────────────────────
@st.cache_data
def carregar_estoque(file) -> pd.DataFrame:
    df_raw = pd.read_excel(file, header=None)

    # Localiza linha de cabeçalho real
    header_row = None
    for i, row in df_raw.iterrows():
        vals = row.astype(str).str.lower().tolist()
        if any("fabr" in v for v in vals) and any("produto" in v for v in vals):
            header_row = i
            break

    if header_row is None:
        st.error("Não encontrei o cabeçalho no Estoque.xlsx. Verifique o arquivo.")
        return pd.DataFrame()

    df = pd.read_excel(file, header=header_row)
    df.columns = [str(c).strip() for c in df.columns]

    # Renomeia colunas para padrão interno
    rename = {}
    for c in df.columns:
        cl = c.lower()
        if "fabr" in cl and "fabricante" not in rename.values():
            rename[c] = "fabricante_codigo"
        elif "produto" in cl and "produto_codigo" not in rename.values():
            rename[c] = "produto_codigo"
        elif "descri" in cl and "descricao" not in rename.values():
            rename[c] = "descricao"
        elif "abc" in cl and "abc" not in rename.values():
            rename[c] = "abc"
        elif "qtde" in cl and "qtde_estoque" not in rename.values():
            rename[c] = "qtde_estoque"
        elif "unit" in cl and "custo_unitario" not in rename.values():
            rename[c] = "custo_unitario"
        elif "total" in cl and "custo_total" not in rename.values():
            rename[c] = "custo_total"
        elif "cubagem" in cl and "cubagem" not in rename.values():
            rename[c] = "cubagem"
    df = df.rename(columns=rename)

    colunas_necessarias = ["fabricante_codigo", "produto_codigo", "descricao", "qtde_estoque"]
    for col in colunas_necessarias:
        if col not in df.columns:
            st.error(f"Coluna '{col}' não encontrada no Estoque.xlsx.")
            return pd.DataFrame()

    # Remove linhas totalmente vazias e linha de TOTAL
    df = df.dropna(how="all")
    if "descricao" in df.columns:
        df = df[~df["descricao"].astype(str).str.upper().str.strip().isin(["TOTAL", "NAN", ""])]

    # Normaliza código do fabricante
    df["fabricante_codigo"] = (
        df["fabricante_codigo"]
        .astype(str)
        .str.strip()
        .str.zfill(3)
    )

    # Remove fabricantes ignorados (900-999)
    df = df[~df["fabricante_codigo"].isin(FABRICANTES_IGNORAR)]

    # Remove linhas onde código não é numérico
    df = df[df["fabricante_codigo"].str.match(r'^\d{3}$')]

    # Mapeia nome do fabricante
    df["fabricante_nome"] = df["fabricante_codigo"].map(MAPA_FABRICANTES).fillna("Outros")

    # Produto como string com zero-fill
    df["produto_codigo"] = df["produto_codigo"].astype(str).str.strip().str.zfill(6)

    # Quantidades e custos
    df["qtde_estoque"] = limpar_numero(df["qtde_estoque"]).fillna(0)

    if "custo_unitario" in df.columns:
        df["custo_unitario"] = limpar_numero(df["custo_unitario"]).fillna(0)
    else:
        df["custo_unitario"] = 0.0

    if "custo_total" in df.columns:
        df["custo_total"] = limpar_numero(df["custo_total"]).fillna(0)
    else:
        df["custo_total"] = df["qtde_estoque"] * df["custo_unitario"]

    # Flag para itens com custo zero (mas NÃO remove — para bater com planilha)
    df["flag_custo_zero"] = df["custo_total"].eq(0) & df["qtde_estoque"].gt(0)

    # BTU
    if "btu" not in df.columns:
        df["btu"] = df["descricao"].apply(extrair_btu_desc)

    return df.reset_index(drop=True)


# ─────────────────────────────────────────────
# CARREGAMENTO: VENDAS
# ─────────────────────────────────────────────
@st.cache_data
def carregar_vendas(file) -> pd.DataFrame:
    conteudo = file.read()
    texto = decode_bytes(conteudo)

    df = pd.read_csv(StringIO(texto), sep=";", on_bad_lines="skip")
    df.columns = [c.strip() for c in df.columns]

    rename_map = {
        "Emissao NF":  "data_emissao",
        "Marca":       "marca",
        "Grupo":       "grupo",
        "BTU":         "btu",
        "Ciclo":       "ciclo",
        "Produto":     "produto_codigo",
        "Descricao":   "descricao",
        "Qtde":        "quantidade",
        "VL Total":    "valor_total",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    # Datas
    df["data_emissao"] = pd.to_datetime(df["data_emissao"], dayfirst=True, errors="coerce")
    df["ano"]  = df["data_emissao"].dt.year
    df["mes"]  = df["data_emissao"].dt.month

    # Normaliza marca
    df["marca"] = df["marca"].astype(str).str.strip()
    df["fabricante_nome"] = df["marca"].str.upper().map(NORMALIZA_MARCA).fillna(df["marca"].str.title())

    # Produto
    df["produto_codigo"] = df["produto_codigo"].astype(str).str.strip().str.zfill(6)

    # Quantidades e valores
    df["quantidade"]  = limpar_numero(df["quantidade"])
    df["valor_total"] = limpar_numero(df["valor_total"])

    # BTU
    df["btu"] = pd.to_numeric(df.get("btu", pd.Series(dtype=float)), errors="coerce")
    mask_btu = df["btu"].isna()
    if mask_btu.any() and "descricao" in df.columns:
        df.loc[mask_btu, "btu"] = df.loc[mask_btu, "descricao"].apply(extrair_btu_desc)

    return df.reset_index(drop=True)


# ─────────────────────────────────────────────
# SIDEBAR – UPLOAD
# ─────────────────────────────────────────────
st.sidebar.title("📂 Arquivos")
file_estoque = st.sidebar.file_uploader("Estoque.xlsx", type=["xlsx", "xls"])
file_vendas  = st.sidebar.file_uploader("Vendas.csv",   type=["csv", "txt"])

st.title("❄️ Gestão de Compras – Ar Condicionado")

if not file_estoque or not file_vendas:
    st.info("Faça o upload do **Estoque.xlsx** e do **Vendas.csv** na barra lateral para começar.")
    st.stop()

# ─────────────────────────────────────────────
# CARREGA DADOS
# ─────────────────────────────────────────────
with st.spinner("Carregando dados..."):
    estoque = carregar_estoque(file_estoque)
    vendas  = carregar_vendas(file_vendas)

if estoque.empty or vendas.empty:
    st.error("Erro ao carregar um dos arquivos. Verifique o formato e tente novamente.")
    st.stop()

# ─────────────────────────────────────────────
# ABAS
# ─────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "📦 Estoque & ABC",
    "📈 Vendas & Demanda",
    "🛒 Sugestão de Compras",
    "🔍 Consulta por Produto",
])


# ══════════════════════════════════════════════
# TAB 1 – ESTOQUE & ABC
# ══════════════════════════════════════════════
with tab1:
    st.subheader("Estoque atual por fabricante")

    fabricantes_est = ["Todos"] + sorted(estoque["fabricante_nome"].dropna().unique().tolist())
    fab_sel = st.selectbox("Filtrar fabricante", fabricantes_est, key="fab_est")

    df_est = estoque.copy()
    if fab_sel != "Todos":
        df_est = df_est[df_est["fabricante_nome"] == fab_sel]

    # KPIs
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("SKUs",           f'{df_est["produto_codigo"].nunique():,}')
    col2.metric("Unidades",       f'{df_est["qtde_estoque"].sum():,.0f}')
    col3.metric("Valor total (R$)", f'R$ {df_est["custo_total"].sum():,.2f}')
    itens_custo_zero = int(df_est["flag_custo_zero"].sum())
    col4.metric("Itens c/ custo zero", itens_custo_zero,
                help="Itens com qtde > 0 mas custo = 0 (ajustar no ERP)")

    st.divider()

    # Tabela de estoque
    cols_show = [c for c in ["fabricante_nome", "produto_codigo", "descricao", "abc",
                              "qtde_estoque", "custo_unitario", "custo_total", "flag_custo_zero"]
                 if c in df_est.columns]

    st.dataframe(
        df_est[cols_show].rename(columns={
            "fabricante_nome":  "Fabricante",
            "produto_codigo":   "Produto",
            "descricao":        "Descrição",
            "abc":              "ABC",
            "qtde_estoque":     "Qtde",
            "custo_unitario":   "Custo Unit.",
            "custo_total":      "Custo Total",
            "flag_custo_zero":  "⚠️ Custo Zero",
        }).sort_values(["Fabricante", "Produto"]),
        use_container_width=True,
        height=500,
    )

    # Resumo por fabricante
    st.subheader("Resumo por fabricante")
    resumo = (
        estoque.groupby("fabricante_nome")
        .agg(
            SKUs=("produto_codigo", "nunique"),
            Unidades=("qtde_estoque", "sum"),
            Valor_Total=("custo_total", "sum"),
        )
        .reset_index()
        .rename(columns={"fabricante_nome": "Fabricante", "Valor_Total": "Valor Total (R$)"})
        .sort_values("Valor Total (R$)", ascending=False)
    )
    st.dataframe(resumo, use_container_width=True)


# ══════════════════════════════════════════════
# TAB 2 – VENDAS & DEMANDA
# ══════════════════════════════════════════════
with tab2:
    st.subheader("Histórico de vendas")

    # Filtros
    c1, c2, c3 = st.columns(3)
    anos_disp = sorted(vendas["ano"].dropna().unique().astype(int).tolist(), reverse=True)
    ano_sel   = c1.multiselect("Ano", anos_disp, default=anos_disp)

    fabricantes_venda = ["Todos"] + sorted(vendas["fabricante_nome"].dropna().unique().tolist())
    fab_venda_sel = c2.selectbox("Fabricante", fabricantes_venda, key="fab_venda")

    grupos_disp = ["Todos"] + sorted(vendas["grupo"].dropna().unique().tolist())
    grupo_sel   = c3.selectbox("Grupo", grupos_disp, key="grupo_venda")

    df_v = vendas[vendas["ano"].isin(ano_sel)].copy()
    if fab_venda_sel != "Todos":
        df_v = df_v[df_v["fabricante_nome"] == fab_venda_sel]
    if grupo_sel != "Todos":
        df_v = df_v[df_v["grupo"] == grupo_sel]

    # KPIs
    c1, c2, c3 = st.columns(3)
    c1.metric("Pedidos",        f'{len(df_v):,}')
    c2.metric("Unidades",       f'{df_v["quantidade"].sum():,.0f}')
    c3.metric("Faturamento (R$)", f'R$ {df_v["valor_total"].sum():,.2f}')

    st.divider()

    # Vendas por mês
    st.subheader("Unidades vendidas por mês")
    vend_mes = (
        df_v.groupby(["ano", "mes"])["quantidade"]
        .sum()
        .reset_index()
    )
    vend_mes["periodo"] = vend_mes.apply(
        lambda r: f'{MESES_PT.get(int(r["mes"]), r["mes"])}/{int(r["ano"])}', axis=1
    )
    st.bar_chart(vend_mes.set_index("periodo")["quantidade"])

    st.divider()

    # Ranking de produtos
    st.subheader("Ranking de produtos mais vendidos")
    ranking = (
        df_v.groupby(["produto_codigo", "descricao", "fabricante_nome"])
        .agg(Unidades=("quantidade", "sum"), Faturamento=("valor_total", "sum"))
        .reset_index()
        .rename(columns={"produto_codigo": "Produto", "descricao": "Descrição",
                          "fabricante_nome": "Fabricante"})
        .sort_values("Unidades", ascending=False)
        .head(50)
    )
    st.dataframe(ranking, use_container_width=True, height=400)


# ══════════════════════════════════════════════
# TAB 3 – SUGESTÃO DE COMPRAS
# ══════════════════════════════════════════════
with tab3:
    st.subheader("Sugestão de compras")

    # Parâmetros
    c1, c2 = st.columns(2)
    meses_cobertura = c1.slider(
        "Cobertura desejada (meses)", min_value=1, max_value=6, value=MESES_SUGESTAO
    )
    anos_ref = c2.multiselect(
        "Anos de referência para giro", anos_disp, default=anos_disp, key="anos_ref"
    )

    df_ref = vendas[vendas["ano"].isin(anos_ref)].copy()

    # Giro mensal por produto (fabricante_nome + produto_codigo + descricao)
    n_meses = df_ref["data_emissao"].dt.to_period("M").nunique()
    n_meses = max(n_meses, 1)

    giro = (
        df_ref.groupby(["fabricante_nome", "produto_codigo", "descricao"])["quantidade"]
        .sum()
        .reset_index()
    )
    giro["giro_mensal"] = giro["quantidade"] / n_meses
    giro["sugestao_compra"] = np.ceil(giro["giro_mensal"] * meses_cobertura)

    # Estoque atual por produto
    est_prod = (
        estoque.groupby(["fabricante_nome", "produto_codigo"])
        .agg(qtde_estoque=("qtde_estoque", "sum"),
             custo_medio=("custo_unitario", "mean"))
        .reset_index()
    )

    # Merge: vendas como base (right = mantém todos os produtos vendidos)
    sugestao = giro.merge(est_prod, on=["fabricante_nome", "produto_codigo"], how="left")
    sugestao["qtde_estoque"] = sugestao["qtde_estoque"].fillna(0)
    sugestao["custo_medio"]  = sugestao["custo_medio"].fillna(0)

    # Cobertura atual (em meses)
    sugestao["cobertura_meses"] = np.where(
        sugestao["giro_mensal"] > 0,
        sugestao["qtde_estoque"] / sugestao["giro_mensal"],
        np.inf
    )

    # Necessidade de compra
    sugestao["necessidade"] = np.maximum(
        0,
        sugestao["sugestao_compra"] - sugestao["qtde_estoque"]
    )

    # Status
    def status(cob):
        if cob == np.inf:
            return "✅ Sem giro"
        elif cob < COBERTURA_CRITICA:
            return "🔴 Crítico"
        elif cob < COBERTURA_ALERTA:
            return "🟡 Alerta"
        else:
            return "🟢 OK"

    sugestao["status"] = sugestao["cobertura_meses"].apply(status)

    # Valor estimado da compra
    sugestao["valor_estimado"] = sugestao["necessidade"] * sugestao["custo_medio"]

    # Filtro de fabricante
    fabs_sug = ["Todos"] + sorted(sugestao["fabricante_nome"].dropna().unique().tolist())
    fab_sug_sel = st.selectbox("Filtrar fabricante", fabs_sug, key="fab_sug")

    mostrar_criticos = st.checkbox("Mostrar apenas críticos e em alerta", value=True)

    df_sug = sugestao.copy()
    if fab_sug_sel != "Todos":
        df_sug = df_sug[df_sug["fabricante_nome"] == fab_sug_sel]
    if mostrar_criticos:
        df_sug = df_sug[df_sug["status"].isin(["🔴 Crítico", "🟡 Alerta"])]

    # KPIs
    c1, c2, c3 = st.columns(3)
    c1.metric("Itens críticos",  int((sugestao["status"] == "🔴 Crítico").sum()))
    c2.metric("Itens em alerta", int((sugestao["status"] == "🟡 Alerta").sum()))
    c3.metric("Valor estimado compra (R$)", f'R$ {df_sug["valor_estimado"].sum():,.2f}')

    st.dataframe(
        df_sug[[
            "status", "fabricante_nome", "produto_codigo", "descricao",
            "giro_mensal", "qtde_estoque", "cobertura_meses",
            "sugestao_compra", "necessidade", "custo_medio", "valor_estimado"
        ]].rename(columns={
            "status":           "Status",
            "fabricante_nome":  "Fabricante",
            "produto_codigo":   "Produto",
            "descricao":        "Descrição",
            "giro_mensal":      "Giro/Mês",
            "qtde_estoque":     "Estoque",
            "cobertura_meses":  "Cobertura (meses)",
            "sugestao_compra":  "Sugestão",
            "necessidade":      "Comprar",
            "custo_medio":      "Custo Médio",
            "valor_estimado":   "Valor Est. (R$)",
        }).sort_values(["Status", "Fabricante", "Produto"]),
        use_container_width=True,
        height=500,
    )

    # Download
    csv_sug = df_sug.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇️ Baixar sugestão (.csv)",
        data=csv_sug,
        file_name="sugestao_compras.csv",
        mime="text/csv",
    )


# ══════════════════════════════════════════════
# TAB 4 – CONSULTA POR PRODUTO
# ══════════════════════════════════════════════
with tab4:
    st.subheader("Consulta individual por produto")

    busca = st.text_input("Digite o código ou parte da descrição do produto")

    if busca:
        busca_lower = busca.lower().strip()

        est_match = estoque[
            estoque["produto_codigo"].str.lower().str.contains(busca_lower, na=False) |
            estoque["descricao"].str.lower().str.contains(busca_lower, na=False)
        ]

        venda_match = vendas[
            vendas["produto_codigo"].str.lower().str.contains(busca_lower, na=False) |
            vendas["descricao"].str.lower().str.contains(busca_lower, na=False)
        ]

        st.markdown(f"**{len(est_match)} produto(s) encontrado(s) no estoque | "
                    f"{venda_match['produto_codigo'].nunique()} produto(s) encontrado(s) nas vendas**")

        col_e, col_v = st.columns(2)

        with col_e:
            st.markdown("#### Posição de estoque")
            if est_match.empty:
                st.info("Nenhum resultado no estoque.")
            else:
                cols_e = [c for c in ["fabricante_nome", "produto_codigo", "descricao",
                                       "abc", "qtde_estoque", "custo_unitario", "custo_total"]
                          if c in est_match.columns]
                st.dataframe(est_match[cols_e], use_container_width=True)

        with col_v:
            st.markdown("#### Histórico de vendas")
            if venda_match.empty:
                st.info("Nenhuma venda encontrada.")
            else:
                venda_resumo = (
                    venda_match.groupby(["produto_codigo", "descricao", "ano", "mes"])
                    .agg(Unidades=("quantidade", "sum"), Faturamento=("valor_total", "sum"))
                    .reset_index()
                    .sort_values(["ano", "mes"], ascending=False)
                )
                st.dataframe(venda_resumo, use_container_width=True)
    else:
        st.info("Digite um código ou descrição para pesquisar.")
