import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import re
from io import StringIO

st.set_page_config(
    page_title="Motor de Compras — Ar Condicionado",
    page_icon="❄️",
    layout="wide"
)

# ─────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────
MAPA_FABRICANTES_ESTOQUE = {
    2:  "LG",
    3:  "Samsung",
    4:  "Springer Midea",
    5:  "Daikin",
    6:  "Agratto",
    7:  "Gree",
    10: "Trane",
    11: "TCL",
}

FABRICANTES_IGNORAR = {900, 995, 998, 999}

NORMALIZA_MARCA_VENDAS = {
    "SPRINGER MIDEA": "Springer Midea",
    "SPRINGER":       "Springer Midea",
    "MIDEA":          "Springer Midea",
    "DAIKIN":         "Daikin",
    "LG":             "LG",
    "SAMSUNG":        "Samsung",
    "GREE":           "Gree",
    "TRANE":          "Trane",
    "TCL":            "TCL",
    "AGRATTO":        "Agratto",
    "DANIFICADO":     "DANIFICADOS",
    "DANIFICADOS":    "DANIFICADOS",
    "SEMI NOVOS":     "SEMI NOVOS",
    "SEMI":           "SEMI NOVOS",
    "ELGIN":          "ELGIN",
}

CONDICOES = {
    "LG":            {"limite": 3_500_000, "prazo": 28},
    "Samsung":       {"limite": 2_000_000, "prazo": 28},
    "Springer Midea":{"limite": 1_500_000, "prazo": 28},
    "Daikin":        {"limite": 5_000_000, "prazo": 35},
    "Agratto":       {"limite":   500_000, "prazo": 28},
    "Gree":          {"limite": 3_000_000, "prazo": 28},
    "Trane":         {"limite": 2_000_000, "prazo": 35},
    "TCL":           {"limite": 3_000_000, "prazo": 28},
}

MESES_PT = {
    1:"Jan", 2:"Fev", 3:"Mar", 4:"Abr", 5:"Mai", 6:"Jun",
    7:"Jul", 8:"Ago", 9:"Set", 10:"Out", 11:"Nov", 12:"Dez"
}

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def decode_bytes(raw: bytes) -> str:
    for enc in ("utf-8-sig", "latin-1", "cp1252", "iso-8859-1", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")

def normaliza_marca(valor: str) -> str:
    v = str(valor).strip().upper()
    for chave, nome in NORMALIZA_MARCA_VENDAS.items():
        if v == chave or v.startswith(chave):
            return nome
    return valor.strip().title()

def limpa_valor(s) -> float:
    """
    Converte qualquer formato monetário BR para float.
    'R$ 6.265.053,00' -> 6265053.0
    'R$ 1.067'        -> 1067.0
    '1067,50'         -> 1067.5
    '1067.50'         -> 1067.5
    '6265053'         -> 6265053.0
    """
    try:
        txt = str(s).strip()
        txt = re.sub(r"[R$\s]", "", txt)
        txt = txt.strip()
        if not txt:
            return 0.0
        tem_virgula = "," in txt
        tem_ponto   = "." in txt
        if tem_virgula and tem_ponto:
            txt = txt.replace(".", "").replace(",", ".")
        elif tem_virgula and not tem_ponto:
            txt = txt.replace(",", ".")
        elif tem_ponto and not tem_virgula:
            partes = txt.split(".")
            if len(partes) > 2:
                txt = txt.replace(".", "")
            elif len(partes) == 2 and len(partes[1]) == 3:
                txt = txt.replace(".", "")
        return float(txt)
    except Exception:
        return 0.0

# ─────────────────────────────────────────────
# CARREGAMENTO DE DADOS
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def carregar_estoque(file_obj):
    """
    Lê o Estoque.xlsx de forma robusta:
    - Detecta automaticamente em qual linha está o cabeçalho
    - Mapeia os nomes reais das colunas para os nomes internos
    - Filtra fabricantes inválidos
    """
    # Lê sem cabeçalho para inspecionar as primeiras linhas
    df_raw = pd.read_excel(file_obj, header=None, dtype=str)

    # Procura a linha onde aparecem "Fabr" e "Produto" (cabeçalho real)
    header_row = 0
    for i, row in df_raw.iterrows():
        valores = [str(v).strip() for v in row.values]
        if any("Fabr" in v for v in valores) and any("Produto" in v for v in valores):
            header_row = i
            break

    # Relê com o cabeçalho correto
    file_obj.seek(0)
    df = pd.read_excel(file_obj, header=header_row, dtype=str)

    # Remove colunas totalmente vazias e linhas totalmente vazias
    df = df.dropna(how="all", axis=1).dropna(how="all", axis=0)

    # Normaliza os nomes das colunas (strip + lower para mapeamento)
    df.columns = [str(c).strip() for c in df.columns]

    # ── Mapeamento flexível de colunas ──────────────────────────────
    # Chave: substring que identifica a coluna real
    # Valor: nome interno que o app usa
    MAPA_COLUNAS = {
        "Fabr":       "fabricante_id",
        "Produto":    "produto_id",
        "Descri":     "descricao",      # "Descrição" ou "Descrição"
        "Classe":     "classe_abc",
        "M":          "volume",         # "M³" ou "M3"
        "Qtde":       "qtde",
        "Custo Unit": "custo_unit",
        "Custo Tot":  "custo_total",
    }

    rename_map = {}
    for col in df.columns:
        col_upper = col.upper()
        for chave, nome_interno in MAPA_COLUNAS.items():
            if chave.upper() in col_upper and nome_interno not in rename_map.values():
                rename_map[col] = nome_interno
                break

    df = df.rename(columns=rename_map)

    # Verifica se as colunas obrigatórias foram encontradas
    obrigatorias = ["fabricante_id", "produto_id", "qtde", "custo_unit", "custo_total"]
    faltando = [c for c in obrigatorias if c not in df.columns]
    if faltando:
        raise KeyError(faltando)

    # Adiciona colunas opcionais se não existirem
    for col in ["descricao", "classe_abc", "volume"]:
        if col not in df.columns:
            df[col] = ""

    # ── Limpeza e tipagem ───────────────────────────────────────────
    df["fabricante_id"] = pd.to_numeric(df["fabricante_id"], errors="coerce")
    df["produto_id"]    = pd.to_numeric(df["produto_id"],    errors="coerce")

    # Remove linhas sem fabricante ou produto válido
    df = df.dropna(subset=["fabricante_id", "produto_id"])

    # Filtra fabricantes a ignorar
    df = df[~df["fabricante_id"].isin(FABRICANTES_IGNORAR)].copy()

    # Converte campos numéricos
    df["qtde"]       = df["qtde"].apply(limpa_valor)
    df["custo_unit"] = df["custo_unit"].apply(limpa_valor)
    df["custo_total"]= df["custo_total"].apply(limpa_valor)
    df["volume"]     = df["volume"].apply(limpa_valor)

    df["fabricante_id"] = df["fabricante_id"].astype(int)
    df["produto_id"]    = df["produto_id"].astype(int)

    # Mapeia nome do fabricante
    df["fabricante_nome"] = df["fabricante_id"].map(MAPA_FABRICANTES_ESTOQUE).fillna("Outros")

    # Garante que descrição é string
    df["descricao"] = df["descricao"].fillna("").astype(str).str.strip()
    df["classe_abc"]= df["classe_abc"].fillna("").astype(str).str.strip()

    return df.reset_index(drop=True)


@st.cache_data(show_spinner=False)
def carregar_vendas(file_obj):
    raw   = file_obj.read()
    texto = decode_bytes(raw)

    COLUNAS = ["data_emissao", "marca", "segmento", "potencia",
               "ciclo", "codigo", "descricao", "quantidade", "valor"]

    df = pd.read_csv(
        StringIO(texto),
        sep=";",
        header=None,
        names=COLUNAS,
        dtype=str,
        keep_default_na=False,
    )

    # Remove colunas duplicadas
    df = df.loc[:, ~df.columns.duplicated()]

    # Descarta linhas onde data_emissao não é dd/mm/aaaa
    df = df[df["data_emissao"].str.match(r"^\d{2}/\d{2}/\d{4}$", na=False)].copy()

    # Converte data via apply (evita bug duplicate-keys do pandas moderno)
    df["data_emissao"] = df["data_emissao"].apply(
        lambda x: pd.to_datetime(x, dayfirst=True, errors="coerce")
    )

    df = df.dropna(subset=["data_emissao"]).copy()

    df["quantidade"] = df["quantidade"].apply(limpa_valor)
    df["valor"]      = df["valor"].apply(limpa_valor)
    df["marca"]      = df["marca"].apply(normaliza_marca)
    df["codigo"]     = df["codigo"].astype(str).str.strip().str.lstrip("0")
    df["ano"]        = df["data_emissao"].dt.year
    df["mes"]        = df["data_emissao"].dt.month

    return df.reset_index(drop=True)


# ─────────────────────────────────────────────
# ABAS
# ─────────────────────────────────────────────
def aba_estoque(estoque_df):
    st.header("📦 Estoque & Curva ABC")

    # ── KPIs ────────────────────────────────────────────────────────
    total_itens   = len(estoque_df)
    total_unid    = int(estoque_df["qtde"].sum())
    total_valor   = estoque_df["custo_total"].sum()
    total_volume  = estoque_df["volume"].sum()

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("SKUs ativos",      f"{total_itens:,}")
    k2.metric("Unidades em estoque", f"{total_unid:,}")
    k3.metric("Valor total (R$)", f"R$ {total_valor:,.0f}")
    k4.metric("Volume total (m³)",f"{total_volume:,.2f}")

    st.divider()

    # ── Por fabricante ───────────────────────────────────────────────
    st.subheader("Estoque por fabricante")
    fab_df = (
        estoque_df.groupby("fabricante_nome")
        .agg(SKUs=("produto_id","count"),
             Unidades=("qtde","sum"),
             Valor=("custo_total","sum"))
        .sort_values("Valor", ascending=False)
        .reset_index()
    )
    fab_df["% Valor"] = (fab_df["Valor"] / fab_df["Valor"].sum() * 100).round(1)

    col1, col2 = st.columns([1, 1])
    with col1:
        st.dataframe(
            fab_df.rename(columns={"fabricante_nome":"Fabricante",
                                   "SKUs":"SKUs","Unidades":"Unid.",
                                   "Valor":"Valor (R$)","% Valor":"% Valor"}),
            use_container_width=True, hide_index=True
        )
    with col2:
        fig = px.pie(fab_df, values="Valor", names="fabricante_nome",
                     title="Participação por valor (R$)")
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Curva ABC ────────────────────────────────────────────────────
    st.subheader("Curva ABC (por valor de estoque)")
    abc = estoque_df.copy().sort_values("custo_total", ascending=False)
    abc["acum_pct"] = abc["custo_total"].cumsum() / abc["custo_total"].sum() * 100
    abc["curva"] = pd.cut(abc["acum_pct"],
                          bins=[0, 80, 95, 100],
                          labels=["A","B","C"])

    resumo_abc = (
        abc.groupby("curva", observed=True)
        .agg(SKUs=("produto_id","count"),
             Valor=("custo_total","sum"))
        .reset_index()
    )
    resumo_abc["% Valor"] = (resumo_abc["Valor"] / resumo_abc["Valor"].sum() * 100).round(1)

    col3, col4 = st.columns([1, 1])
    with col3:
        st.dataframe(resumo_abc, use_container_width=True, hide_index=True)
    with col4:
        fig2 = px.bar(resumo_abc, x="curva", y="Valor",
                      color="curva", title="Valor por classe ABC",
                      labels={"curva":"Classe","Valor":"R$"})
        st.plotly_chart(fig2, use_container_width=True)

    st.divider()

    # ── Tabela completa ──────────────────────────────────────────────
    with st.expander("📋 Tabela completa do estoque"):
        st.dataframe(
            estoque_df[[
                "fabricante_nome","produto_id","descricao",
                "classe_abc","qtde","custo_unit","custo_total","volume"
            ]].rename(columns={
                "fabricante_nome":"Marca","produto_id":"Código",
                "descricao":"Descrição","classe_abc":"ABC",
                "qtde":"Qtde","custo_unit":"Custo Unit.",
                "custo_total":"Custo Total","volume":"M³"
            }),
            use_container_width=True, hide_index=True
        )


def aba_vendas(vendas_df):
    st.header("📈 Vendas & Demanda")

    anos_disp = sorted(vendas_df["ano"].unique(), reverse=True)
    ano_sel   = st.selectbox("Ano de referência", anos_disp)
    df_ano    = vendas_df[vendas_df["ano"] == ano_sel].copy()

    # KPIs
    total_receita = df_ano["valor"].sum()
    total_unid    = int(df_ano["quantidade"].sum())
    total_nf      = df_ano["data_emissao"].nunique()

    k1, k2, k3 = st.columns(3)
    k1.metric("Faturamento",       f"R$ {total_receita:,.2f}")
    k2.metric("Unidades vendidas", f"{total_unid:,}")
    k3.metric("Dias com movimento",f"{total_nf:,}")

    st.divider()

    # ── Vendas mensais ───────────────────────────────────────────────
    st.subheader("Faturamento mensal")
    mensal = (
        df_ano.groupby("mes")["valor"].sum()
        .reset_index()
        .sort_values("mes")
    )
    mensal["mes_nome"] = mensal["mes"].map(MESES_PT)
    fig_m = px.bar(mensal, x="mes_nome", y="valor",
                   title=f"Faturamento mensal — {ano_sel}",
                   labels={"mes_nome":"Mês","valor":"R$"})
    st.plotly_chart(fig_m, use_container_width=True)

    st.divider()

    # ── Por marca ────────────────────────────────────────────────────
    st.subheader("Faturamento por marca")
    por_marca = (
        df_ano.groupby("marca")
        .agg(Faturamento=("valor","sum"),
             Unidades=("quantidade","sum"))
        .sort_values("Faturamento", ascending=False)
        .reset_index()
    )
    por_marca["% Fat."] = (por_marca["Faturamento"] / por_marca["Faturamento"].sum() * 100).round(1)

    col1, col2 = st.columns([1, 1])
    with col1:
        st.dataframe(por_marca, use_container_width=True, hide_index=True)
    with col2:
        fig_marca = px.pie(por_marca, values="Faturamento", names="marca",
                           title="Participação por marca (%)")
        st.plotly_chart(fig_marca, use_container_width=True)

    st.divider()

    # ── Top SKUs ─────────────────────────────────────────────────────
    st.subheader("Top 20 SKUs mais vendidos (por faturamento)")
    top_sku = (
        df_ano.groupby(["codigo","descricao"])
        .agg(Faturamento=("valor","sum"),
             Unidades=("quantidade","sum"))
        .sort_values("Faturamento", ascending=False)
        .head(20)
        .reset_index()
    )
    st.dataframe(top_sku, use_container_width=True, hide_index=True)


def aba_cobertura(estoque_df, vendas_df):
    st.header("📊 Cobertura de Estoque")

    if estoque_df.empty or vendas_df.empty:
        st.info("Carregue os dois arquivos para ver a cobertura.")
        return

    anos_disp = sorted(vendas_df["ano"].unique(), reverse=True)
    ano_ref   = st.selectbox("Ano de referência para média", anos_disp, key="cob_ano")

    meses_disp = sorted(vendas_df[vendas_df["ano"] == ano_ref]["mes"].unique())
    meses_sel  = st.multiselect(
        "Meses para calcular média",
        options=meses_disp,
        default=meses_disp[-3:] if len(meses_disp) >= 3 else meses_disp,
        format_func=lambda m: MESES_PT.get(m, m),
        key="cob_meses"
    )

    if not meses_sel:
        st.warning("Selecione ao menos um mês.")
        return

    df_ref = vendas_df[
        (vendas_df["ano"] == ano_ref) &
        (vendas_df["mes"].isin(meses_sel))
    ].copy()

    n_meses = len(meses_sel)
    media_mes = (
        df_ref.groupby("codigo")["quantidade"]
        .sum()
        .div(n_meses)
        .reset_index()
        .rename(columns={"quantidade": "media_mensal"})
    )

    est = estoque_df[["produto_id","fabricante_nome","descricao","qtde"]].copy()
    est["produto_id"]   = est["produto_id"].astype(str).str.strip().str.lstrip("0")
    media_mes["codigo"] = media_mes["codigo"].astype(str).str.strip().str.lstrip("0")

    df_cob = est.merge(media_mes, left_on="produto_id", right_on="codigo", how="left")
    df_cob["media_mensal"] = df_cob["media_mensal"].fillna(0)
    df_cob["cobertura_meses"] = np.where(
        df_cob["media_mensal"] > 0,
        df_cob["qtde"] / df_cob["media_mensal"],
        np.nan
    )

    # KPIs
    sem_giro   = int((df_cob["media_mensal"] == 0).sum())
    cob_baixa  = int((df_cob["cobertura_meses"] < 1).sum())
    cob_ok     = int(((df_cob["cobertura_meses"] >= 1) & (df_cob["cobertura_meses"] <= 3)).sum())
    cob_alta   = int((df_cob["cobertura_meses"] > 3).sum())

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Sem giro",         f"{sem_giro}")
    k2.metric("Cobertura < 1 mês",f"{cob_baixa}")
    k3.metric("Cobertura 1–3 m",  f"{cob_ok}")
    k4.metric("Cobertura > 3 m",  f"{cob_alta}")

    st.divider()

    fig_cob = px.histogram(
        df_cob.dropna(subset=["cobertura_meses"]),
        x="cobertura_meses",
        nbins=30,
        title="Distribuição de cobertura (meses)",
        labels={"cobertura_meses":"Cobertura (meses)","count":"SKUs"}
    )
    st.plotly_chart(fig_cob, use_container_width=True)

    st.divider()

    with st.expander("📋 Tabela de cobertura por SKU"):
        st.dataframe(
            df_cob[[
                "fabricante_nome","produto_id","descricao",
                "qtde","media_mensal","cobertura_meses"
            ]].rename(columns={
                "fabricante_nome":"Marca","produto_id":"Código",
                "descricao":"Descrição","qtde":"Estoque",
                "media_mensal":"Média/Mês","cobertura_meses":"Cobertura (m)"
            }).sort_values("Cobertura (m)"),
            use_container_width=True, hide_index=True
        )


def aba_sugestao(estoque_df, vendas_df):
    st.header("🛒 Sugestão de Compras")

    if estoque_df.empty or vendas_df.empty:
        st.info("Carregue os dois arquivos para gerar sugestão de compras.")
        return

    anos_disp = sorted(vendas_df["ano"].unique(), reverse=True)
    ano_ref   = st.selectbox("Ano de referência", anos_disp, key="sug_ano")

    meses_disp = sorted(vendas_df[vendas_df["ano"] == ano_ref]["mes"].unique())
    meses_sel  = st.multiselect(
        "Meses para calcular média de vendas",
        options=meses_disp,
        default=meses_disp[-3:] if len(meses_disp) >= 3 else meses_disp,
        format_func=lambda m: MESES_PT.get(m, m),
        key="sug_meses"
    )

    if not meses_sel:
        st.warning("Selecione ao menos um mês.")
        return

    cobertura_alvo = st.slider("Cobertura desejada (meses)", 1, 6, 3)

    df_ref  = vendas_df[
        (vendas_df["ano"] == ano_ref) &
        (vendas_df["mes"].isin(meses_sel))
    ].copy()

    n_meses = len(meses_sel)
    media_mes = (
        df_ref.groupby("codigo")["quantidade"]
        .sum()
        .div(n_meses)
        .reset_index()
        .rename(columns={"quantidade": "media_mensal"})
    )

    est = estoque_df[["produto_id","fabricante_nome","descricao","qtde","custo_unit"]].copy()
    est["produto_id"]   = est["produto_id"].astype(str).str.strip().str.lstrip("0")
    media_mes["codigo"] = media_mes["codigo"].astype(str).str.strip().str.lstrip("0")

    df_s = est.merge(media_mes, left_on="produto_id", right_on="codigo", how="left")
    df_s["media_mensal"]    = df_s["media_mensal"].fillna(0)
    df_s["estoque_alvo"]    = (df_s["media_mensal"] * cobertura_alvo).apply(np.ceil)
    df_s["sugestao_compra"] = (df_s["estoque_alvo"] - df_s["qtde"]).clip(lower=0).apply(np.ceil)
    df_s["valor_estimado"]  = df_s["sugestao_compra"] * df_s["custo_unit"]

    df_s = df_s[df_s["sugestao_compra"] > 0].sort_values("valor_estimado", ascending=False)

    if df_s.empty:
        st.success("Nenhuma compra sugerida com os parâmetros selecionados.")
        return

    k1, k2, k3 = st.columns(3)
    k1.metric("SKUs p/ comprar",   f"{len(df_s):,}")
    k2.metric("Unidades totais",   f"{int(df_s['sugestao_compra'].sum()):,}")
    k3.metric("Valor est. compra", f"R$ {df_s['valor_estimado'].sum():,.0f}")

    cols_sug = ["produto_id","fabricante_nome","descricao","qtde",
                "media_mensal","estoque_alvo","sugestao_compra","valor_estimado"]
    st.dataframe(
        df_s[cols_sug].rename(columns={
            "produto_id":"Código","fabricante_nome":"Marca","descricao":"Descrição",
            "qtde":"Estoque Atual","media_mensal":"Média/Mês","estoque_alvo":"Alvo",
            "sugestao_compra":"Sugestão","valor_estimado":"Valor Est. (R$)"
        }),
        use_container_width=True, hide_index=True
    )

    st.download_button(
        "⬇️ Exportar sugestão (CSV)",
        df_s[cols_sug].to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
        "sugestao_compras.csv",
        "text/csv",
    )


def aba_fornecedores(estoque_df):
    st.header("🏭 Fornecedores")

    dados_cond = [
        {
            "Fornecedor":  fab,
            "Limite (R$)": f"R$ {c['limite']:,.0f}" if c["limite"] > 0 else "—",
            "Prazo (dias)":c["prazo"] if c["prazo"] > 0 else "Antecipado",
        }
        for fab, c in CONDICOES.items()
    ]
    st.subheader("Condições Comerciais")
    st.dataframe(pd.DataFrame(dados_cond), use_container_width=True, hide_index=True)

    if not estoque_df.empty:
        st.divider()
        st.subheader("Estoque atual vs Limite de crédito")
        est_fab = estoque_df.groupby("fabricante_nome")["custo_total"].sum().reset_index()
        est_fab.columns = ["Fornecedor","Estoque Atual (R$)"]
        df_cred = pd.DataFrame([
            {"Fornecedor": k, "Limite (R$)": v["limite"]}
            for k, v in CONDICOES.items()
        ]).merge(est_fab, on="Fornecedor", how="left")
        df_cred["Estoque Atual (R$)"] = df_cred["Estoque Atual (R$)"].fillna(0)
        df_cred["% do Limite"] = (
            df_cred["Estoque Atual (R$)"] /
            df_cred["Limite (R$)"].replace(0, np.nan) * 100
        ).round(1)

        fig_c = px.bar(
            df_cred[df_cred["Limite (R$)"] > 0],
            x="Fornecedor",
            y=["Limite (R$)", "Estoque Atual (R$)"],
            barmode="group",
            title="Limite de crédito x Estoque atual",
            labels={"value":"R$","variable":""}
        )
        st.plotly_chart(fig_c, use_container_width=True)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    st.title("❄️ Motor de Compras — Ar Condicionado")

    with st.sidebar:
        st.header("📂 Arquivos")
        file_estoque = st.file_uploader("Estoque (.xlsx)", type=["xlsx"])
        file_vendas  = st.file_uploader("Vendas (.csv)",  type=["csv"])

    estoque_df = pd.DataFrame()
    vendas_df  = pd.DataFrame()

    if file_estoque:
        try:
            estoque_df = carregar_estoque(file_estoque)
        except Exception as e:
            st.error(f"Erro ao carregar estoque: {e}")

    if file_vendas:
        try:
            vendas_df = carregar_vendas(file_vendas)
        except Exception as e:
            st.error(f"Erro ao carregar vendas: {e}")

    tabs = st.tabs([
        "📦 Estoque & ABC",
        "📈 Vendas & Demanda",
        "📊 Cobertura",
        "🛒 Sugestão de Compras",
        "🏭 Fornecedores"
    ])

    with tabs[0]:
        if not estoque_df.empty:
            aba_estoque(estoque_df)
        else:
            st.info("Carregue o arquivo de estoque.")

    with tabs[1]:
        if not vendas_df.empty:
            aba_vendas(vendas_df)
        else:
            st.info("Carregue o arquivo de vendas.")

    with tabs[2]:
        aba_cobertura(estoque_df, vendas_df)

    with tabs[3]:
        aba_sugestao(estoque_df, vendas_df)

    with tabs[4]:
        aba_fornecedores(estoque_df)


if __name__ == "__main__":
    main()
