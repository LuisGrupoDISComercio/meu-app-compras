import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import re

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
    "Samsung":       {"limite": 4_000_000, "prazo": 28},
    "Springer Midea":{"limite": 2_000_000, "prazo": 21},
    "Daikin":        {"limite": 1_500_000, "prazo": 21},
    "Gree":          {"limite": 2_500_000, "prazo": 28},
    "Trane":         {"limite": 1_000_000, "prazo": 30},
    "TCL":           {"limite": 1_000_000, "prazo": 21},
    "Agratto":       {"limite":   500_000, "prazo": 28},
}

# ─────────────────────────────────────────────
# CARREGAMENTO DE DADOS
# ─────────────────────────────────────────────

def carregar_estoque(file_obj):
    """
    Lê o Estoque.xlsx por POSIÇÃO de coluna (0-indexed),
    independente do nome real no cabeçalho.
    Estrutura esperada:
      col0=fabricante_id, col1=produto_id, col2=descricao,
      col3=classe_abc,    col4=volume,     col5=qtde,
      col6=custo_unit,    col7=custo_total
    """
    file_obj.seek(0)

    # Lê tentando header na linha 0
    df_test = pd.read_excel(file_obj, header=0, nrows=3)
    file_obj.seek(0)

    # Determina se a primeira linha é realmente o cabeçalho
    # (verifica se col0 é texto, não número)
    primeira_col = str(df_test.columns[0]).strip()
    if primeira_col.replace(".", "").replace(",", "").isdigit():
        # cabeçalho está na linha 1
        file_obj.seek(0)
        df = pd.read_excel(file_obj, header=1)
    else:
        file_obj.seek(0)
        df = pd.read_excel(file_obj, header=0)

    # Garante que temos pelo menos 8 colunas
    if df.shape[1] < 8:
        raise ValueError(f"Excel tem apenas {df.shape[1]} colunas, esperava ao menos 8.")

    # Pega exatamente as 8 primeiras colunas por posição
    df = df.iloc[:, :8].copy()
    df.columns = [
        "fabricante_id", "produto_id", "descricao",
        "classe_abc", "volume", "qtde",
        "custo_unit", "custo_total"
    ]

    # Remove linhas de totais / cabeçalhos duplicados / completamente vazias
    df = df.dropna(subset=["fabricante_id", "produto_id"], how="any")
    df = df[df["fabricante_id"].apply(
        lambda x: str(x).replace(".", "").replace(",", "").strip().isdigit()
        if pd.notna(x) else False
    )]

    # Converte tipos
    df["fabricante_id"] = pd.to_numeric(df["fabricante_id"], errors="coerce").astype("Int64")
    df["produto_id"]    = pd.to_numeric(df["produto_id"],    errors="coerce").astype("Int64")
    df["volume"]        = pd.to_numeric(df["volume"],        errors="coerce").fillna(0)
    df["qtde"]          = pd.to_numeric(df["qtde"],          errors="coerce").fillna(0)
    df["custo_unit"]    = pd.to_numeric(df["custo_unit"],    errors="coerce").fillna(0)
    df["custo_total"]   = pd.to_numeric(df["custo_total"],   errors="coerce").fillna(0)
    df["descricao"]     = df["descricao"].astype(str).str.strip()
    df["classe_abc"]    = df["classe_abc"].astype(str).str.strip().replace("nan", "")

    # Filtra fabricantes inválidos
    df = df[~df["fabricante_id"].isin(FABRICANTES_IGNORAR)]
    df = df[df["fabricante_id"].notna()]

    # Adiciona nome do fabricante
    df["fabricante"] = df["fabricante_id"].map(MAPA_FABRICANTES_ESTOQUE).fillna("Outros")

    return df.reset_index(drop=True)


def limpa_valor(v):
    """Converte string de valor monetário brasileiro para float."""
    if pd.isna(v):
        return 0.0
    s = str(v).strip()
    # Remove R$, espaços, aspas
    s = re.sub(r"[R$\s\"']", "", s)
    if not s:
        return 0.0
    # Formato brasileiro: 1.234.567,89
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        # Pode ser separador decimal: 1234,89
        partes = s.split(",")
        if len(partes) == 2 and len(partes[1]) <= 2:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    # Se só tem ponto, pode ser decimal ou milhar
    elif "." in s:
        partes = s.split(".")
        if len(partes) == 2 and len(partes[1]) <= 2:
            pass  # decimal normal: 1234.89
        else:
            s = s.replace(".", "")  # milhar: 1.234.567
    try:
        return float(s)
    except ValueError:
        return 0.0


def carregar_vendas(file_obj):
    """Lê o Vendas.csv com separador ; e trata os valores monetários."""
    file_obj.seek(0)
    raw = file_obj.read()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")

    # Remove BOM se houver
    raw = raw.lstrip("\ufeff")

    # Lê o CSV
    from io import StringIO
    df = pd.read_csv(
        StringIO(raw),
        sep=";",
        dtype=str,
        skip_blank_lines=True,
    )

    # Limpa nomes de colunas
    df.columns = [c.strip().strip('"') for c in df.columns]

    # Renomeia colunas para nomes internos
    rename = {}
    for c in df.columns:
        cl = c.lower().strip()
        if "emis" in cl and "nf" in cl:
            rename[c] = "data_emissao"
        elif cl == "marca":
            rename[c] = "marca"
        elif cl == "grupo":
            rename[c] = "grupo"
        elif cl == "btu":
            rename[c] = "btu"
        elif cl == "ciclo":
            rename[c] = "ciclo"
        elif cl == "produto":
            rename[c] = "produto_id"
        elif "desc" in cl:
            rename[c] = "descricao"
        elif cl == "qtde":
            rename[c] = "qtde"
        elif "vl" in cl or "total" in cl or "valor" in cl:
            rename[c] = "vl_total"
    df = df.rename(columns=rename)

    colunas_necessarias = ["data_emissao", "marca", "produto_id", "qtde", "vl_total"]
    faltando = [c for c in colunas_necessarias if c not in df.columns]
    if faltando:
        raise ValueError(f"Colunas não encontradas no CSV de vendas: {faltando}")

    # Filtra apenas linhas com data válida dd/mm/aaaa
    df = df[df["data_emissao"].str.match(r"^\d{2}/\d{2}/\d{4}$", na=False)].copy()

    # Converte
    df["data_emissao"] = pd.to_datetime(df["data_emissao"], format="%d/%m/%Y", errors="coerce")
    df = df[df["data_emissao"].notna()].copy()

    df["qtde"]     = pd.to_numeric(df["qtde"].str.strip(), errors="coerce").fillna(0)
    df["vl_total"] = df["vl_total"].apply(limpa_valor)

    df["produto_id"] = pd.to_numeric(df["produto_id"].str.strip(), errors="coerce").astype("Int64")

    # Normaliza marca
    df["marca_raw"] = df["marca"].astype(str).str.strip().str.upper()
    df["marca"] = df["marca_raw"].map(NORMALIZA_MARCA_VENDAS).fillna(df["marca_raw"].str.title())
    df = df.drop(columns=["marca_raw"])

    # Colunas opcionais
    for col in ["grupo", "btu", "ciclo", "descricao"]:
        if col not in df.columns:
            df[col] = ""
        else:
            df[col] = df[col].astype(str).str.strip()

    df["btu"] = pd.to_numeric(df["btu"], errors="coerce").fillna(0).astype(int)

    return df.reset_index(drop=True)


# ─────────────────────────────────────────────
# ABAS
# ─────────────────────────────────────────────

def aba_estoque(df):
    st.header("📦 Estoque & ABC")

    # KPIs
    total_itens  = int(df["qtde"].sum())
    total_valor  = df["custo_total"].sum()
    total_skus   = df["produto_id"].nunique()
    total_volume = df["volume"].sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Peças",    f"{total_itens:,.0f}")
    c2.metric("Valor em Estoque", f"R$ {total_valor:,.0f}")
    c3.metric("SKUs",           f"{total_skus:,.0f}")
    c4.metric("Volume Total m³", f"{total_volume:,.1f}")

    st.divider()

    # Estoque por fabricante
    st.subheader("Estoque por Fabricante")
    fab_df = (
        df.groupby("fabricante", as_index=False)
        .agg(qtde=("qtde", "sum"), valor=("custo_total", "sum"), skus=("produto_id", "nunique"))
        .sort_values("valor", ascending=False)
    )
    fab_df["valor_fmt"] = fab_df["valor"].apply(lambda x: f"R$ {x:,.0f}")
    fig_fab = px.bar(
        fab_df, x="fabricante", y="valor",
        text="valor_fmt", color="fabricante",
        labels={"valor": "Valor (R$)", "fabricante": "Fabricante"},
        title="Valor em Estoque por Fabricante"
    )
    fig_fab.update_traces(textposition="outside")
    fig_fab.update_layout(showlegend=False)
    st.plotly_chart(fig_fab, use_container_width=True)

    st.divider()

    # Curva ABC
    st.subheader("Curva ABC")
    abc_df = (
        df.groupby(["produto_id", "descricao", "fabricante", "classe_abc"], as_index=False)
        .agg(qtde=("qtde", "sum"), custo_total=("custo_total", "sum"))
        .sort_values("custo_total", ascending=False)
    )
    abc_df["% Acum"] = (abc_df["custo_total"].cumsum() / abc_df["custo_total"].sum() * 100).round(1)
    abc_df["custo_total_fmt"] = abc_df["custo_total"].apply(lambda x: f"R$ {x:,.0f}")

    filtro_fab = st.multiselect(
        "Filtrar por Fabricante", options=sorted(df["fabricante"].unique()), default=[]
    )
    if filtro_fab:
        abc_df = abc_df[abc_df["fabricante"].isin(filtro_fab)]

    st.dataframe(
        abc_df[["produto_id", "descricao", "fabricante", "classe_abc", "qtde", "custo_total_fmt", "% Acum"]],
        use_container_width=True, height=400
    )


def aba_vendas(df):
    st.header("📈 Vendas & Demanda")

    total_vl    = df["vl_total"].sum()
    total_qtde  = int(df["qtde"].sum())
    total_nfs   = df["data_emissao"].nunique()
    total_marcas= df["marca"].nunique()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Receita Total",  f"R$ {total_vl:,.0f}")
    c2.metric("Peças Vendidas", f"{total_qtde:,.0f}")
    c3.metric("Dias com NF",    f"{total_nfs}")
    c4.metric("Marcas",         f"{total_marcas}")

    st.divider()

    # Vendas por marca
    st.subheader("Vendas por Marca")
    marca_df = (
        df.groupby("marca", as_index=False)
        .agg(receita=("vl_total", "sum"), qtde=("qtde", "sum"))
        .sort_values("receita", ascending=False)
    )
    marca_df["receita_fmt"] = marca_df["receita"].apply(lambda x: f"R$ {x:,.0f}")
    fig_marca = px.bar(
        marca_df, x="marca", y="receita",
        text="receita_fmt", color="marca",
        labels={"receita": "Receita (R$)", "marca": "Marca"},
        title="Receita por Marca"
    )
    fig_marca.update_traces(textposition="outside")
    fig_marca.update_layout(showlegend=False)
    st.plotly_chart(fig_marca, use_container_width=True)

    st.divider()

    # Evolução mensal
    st.subheader("Evolução Mensal")
    df2 = df.copy()
    df2["mes"] = df2["data_emissao"].dt.to_period("M").astype(str)
    mensal = df2.groupby("mes", as_index=False).agg(receita=("vl_total", "sum"))
    fig_mensal = px.line(mensal, x="mes", y="receita", markers=True, title="Receita Mensal")
    st.plotly_chart(fig_mensal, use_container_width=True)

    st.divider()

    # Tabela detalhada
    st.subheader("Detalhe de Vendas")
    filtro_marca = st.multiselect("Filtrar Marca", options=sorted(df["marca"].unique()), default=[])
    df_show = df.copy()
    if filtro_marca:
        df_show = df_show[df_show["marca"].isin(filtro_marca)]
    df_show["vl_total_fmt"] = df_show["vl_total"].apply(lambda x: f"R$ {x:,.0f}")
    df_show["data_fmt"] = df_show["data_emissao"].dt.strftime("%d/%m/%Y")
    st.dataframe(
        df_show[["data_fmt", "marca", "grupo", "btu", "produto_id", "descricao", "qtde", "vl_total_fmt"]],
        use_container_width=True, height=400
    )


def aba_cobertura(estoque_df, vendas_df):
    st.header("📊 Cobertura de Estoque")

    if estoque_df.empty or vendas_df.empty:
        st.info("Carregue os arquivos de estoque e vendas para ver a cobertura.")
        return

    # Demanda média diária por produto
    dias = max((vendas_df["data_emissao"].max() - vendas_df["data_emissao"].min()).days, 1)
    demanda = (
        vendas_df.groupby("produto_id", as_index=False)
        .agg(qtde_vendida=("qtde", "sum"))
    )
    demanda["demanda_dia"] = demanda["qtde_vendida"] / dias

    # Junta com estoque
    cob = estoque_df.merge(demanda, on="produto_id", how="left")
    cob["demanda_dia"]  = cob["demanda_dia"].fillna(0)
    cob["qtde_vendida"] = cob["qtde_vendida"].fillna(0)
    cob["cobertura_dias"] = np.where(
        cob["demanda_dia"] > 0,
        cob["qtde"] / cob["demanda_dia"],
        np.inf
    )

    # Classifica cobertura
    def classifica(d):
        if d == np.inf:
            return "Sem giro"
        elif d < 30:
            return "Crítico"
        elif d < 60:
            return "Atenção"
        else:
            return "OK"

    cob["status"] = cob["cobertura_dias"].apply(classifica)

    # KPIs
    criticos  = (cob["status"] == "Crítico").sum()
    atencao   = (cob["status"] == "Atenção").sum()
    ok        = (cob["status"] == "OK").sum()
    sem_giro  = (cob["status"] == "Sem giro").sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🔴 Crítico (<30d)",    criticos)
    c2.metric("🟡 Atenção (30-60d)",  atencao)
    c3.metric("🟢 OK (>60d)",         ok)
    c4.metric("⚪ Sem Giro",          sem_giro)

    st.divider()

    # Filtro de status
    status_sel = st.multiselect(
        "Filtrar Status", ["Crítico", "Atenção", "OK", "Sem giro"],
        default=["Crítico", "Atenção"]
    )
    cob_show = cob[cob["status"].isin(status_sel)].copy() if status_sel else cob.copy()
    cob_show["cobertura_fmt"] = cob_show["cobertura_dias"].apply(
        lambda x: "∞" if x == np.inf else f"{x:.0f} dias"
    )
    cob_show["custo_total_fmt"] = cob_show["custo_total"].apply(lambda x: f"R$ {x:,.0f}")

    st.dataframe(
        cob_show[[
            "fabricante", "produto_id", "descricao",
            "qtde", "custo_total_fmt", "cobertura_fmt", "status"
        ]].sort_values("cobertura_dias"),
        use_container_width=True, height=450
    )


def aba_sugestao(estoque_df, vendas_df):
    st.header("🛒 Sugestão de Compras")

    if estoque_df.empty or vendas_df.empty:
        st.info("Carregue os arquivos de estoque e vendas para gerar sugestões.")
        return

    dias_cobertura_alvo = st.slider("Dias de cobertura alvo", 30, 180, 90)

    dias = max((vendas_df["data_emissao"].max() - vendas_df["data_emissao"].min()).days, 1)
    demanda = (
        vendas_df.groupby("produto_id", as_index=

