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
    try:
        txt = str(s).strip()
        txt = re.sub(r"[R$\s]", "", txt)
        txt = txt.strip()
        if not txt:
            return 0.0
        tem_virgula = "," in txt
        tem_ponto   = "." in txt
        if tem_virgula and tem_ponto:
            # formato BR: 6.265.053,00
            txt = txt.replace(".", "").replace(",", ".")
        elif tem_virgula and not tem_ponto:
            txt = txt.replace(",", ".")
        elif tem_ponto and not tem_virgula:
            partes = txt.split(".")
            if len(partes) == 2 and len(partes[1]) == 3:
                # ponto como milhar: 1.067 → 1067
                txt = txt.replace(".", "")
            # senão mantém como decimal: 1067.50
        return float(txt)
    except Exception:
        return 0.0

# ─────────────────────────────────────────────
# CARREGAMENTO
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def carregar_estoque(file_obj) -> pd.DataFrame:
    """
    Lê o Estoque.xlsx detectando automaticamente a linha do cabeçalho.
    Colunas esperadas no Excel (nomes reais):
        Fabr | Produto | Descrição | Classe | M³ | Qtde | Custo Unit. | Custo Total
    Mapeamento para nomes internos:
        fabricante_id | produto_id | descricao | classe_abc | volume | qtde | custo_unit | custo_total
    """
    # Mapeamento: substring da coluna real → nome interno
    MAPA_COLUNAS = {
        "fabr":       "fabricante_id",
        "produto":    "produto_id",
        "descri":     "descricao",
        "classe":     "classe_abc",
        "m³":         "volume",
        "m3":         "volume",
        "qtde":       "qtde",
        "quant":      "qtde",
        "custo unit": "custo_unit",
        "custo tot":  "custo_total",
    }

    # 1. Detecta qual linha é o cabeçalho (procura linha com "Fabr" e "Produto")
    preview = pd.read_excel(file_obj, header=None, nrows=10)
    file_obj.seek(0)

    header_row = 0
    for i, row in preview.iterrows():
        valores = [str(v).strip().lower() for v in row if pd.notna(v)]
        tem_fabr    = any("fabr" in v for v in valores)
        tem_produto = any("produto" in v for v in valores)
        if tem_fabr and tem_produto:
            header_row = i
            break

    # 2. Lê com o cabeçalho correto
    df = pd.read_excel(file_obj, header=header_row, dtype=str)
    file_obj.seek(0)

    # 3. Normaliza os nomes das colunas e mapeia para nomes internos
    rename_map = {}
    for col in df.columns:
        col_lower = str(col).strip().lower()
        for chave, nome_interno in MAPA_COLUNAS.items():
            if chave in col_lower:
                rename_map[col] = nome_interno
                break

    df = df.rename(columns=rename_map)

    # 4. Verifica colunas obrigatórias
    obrigatorias = ["fabricante_id", "produto_id", "descricao",
                    "classe_abc", "volume", "qtde", "custo_unit", "custo_total"]
    faltando = [c for c in obrigatorias if c not in df.columns]
    if faltando:
        raise ValueError(f"Colunas não encontradas no Excel de estoque: {faltando}")

    # 5. Converte tipos
    df["fabricante_id"] = pd.to_numeric(df["fabricante_id"], errors="coerce")
    df["produto_id"]    = pd.to_numeric(df["produto_id"],    errors="coerce")
    df["volume"]        = pd.to_numeric(df["volume"],        errors="coerce").fillna(0.0)
    df["qtde"]          = pd.to_numeric(df["qtde"],          errors="coerce").fillna(0.0)
    df["custo_unit"]    = df["custo_unit"].apply(limpa_valor)
    df["custo_total"]   = df["custo_total"].apply(limpa_valor)

    # 6. Remove linhas sem fabricante ou produto válidos
    df = df.dropna(subset=["fabricante_id", "produto_id"])

    # 7. Filtra fabricantes a ignorar
    df = df[~df["fabricante_id"].isin(FABRICANTES_IGNORAR)]

    # 8. Mapeia nome do fabricante
    df["fabricante_nome"] = df["fabricante_id"].map(MAPA_FABRICANTES_ESTOQUE).fillna("Outros")

    # 9. Limpa classe_abc
    df["classe_abc"] = df["classe_abc"].fillna("S").str.strip()

    return df.reset_index(drop=True)


@st.cache_data(show_spinner=False)
def carregar_vendas(file_obj) -> pd.DataFrame:
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

    # Converte data
    df["data_emissao"] = pd.to_datetime(
        df["data_emissao"], format="%d/%m/%Y", errors="coerce"
    )
    df = df.dropna(subset=["data_emissao"])

    df["ano"]  = df["data_emissao"].dt.year
    df["mes"]  = df["data_emissao"].dt.month

    # Normaliza marca
    df["marca"] = df["marca"].apply(normaliza_marca)

    # Converte numéricos
    df["quantidade"] = pd.to_numeric(df["quantidade"], errors="coerce").fillna(0.0)
    df["valor"]      = df["valor"].apply(limpa_valor)

    # Potência numérica
    df["potencia_num"] = pd.to_numeric(df["potencia"], errors="coerce")

    return df.reset_index(drop=True)


# ─────────────────────────────────────────────
# ABAS
# ─────────────────────────────────────────────
def aba_estoque(estoque_df: pd.DataFrame):
    st.subheader("📦 Visão Geral do Estoque")

    fabricantes = ["Todos"] + sorted(estoque_df["fabricante_nome"].unique().tolist())
    fab_sel = st.selectbox("Filtrar por fabricante", fabricantes, key="est_fab")

    df = estoque_df if fab_sel == "Todos" else estoque_df[estoque_df["fabricante_nome"] == fab_sel]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total SKUs",         f"{len(df):,.0f}")
    col2.metric("Total Peças",        f"{df['qtde'].sum():,.0f}")
    col3.metric("Custo Total (R$)",   f"R$ {df['custo_total'].sum():,.0f}")
    col4.metric("Volume Total (m³)",  f"{df['volume'].sum():,.2f}")

    st.divider()

    # Estoque por fabricante
    st.subheader("Estoque por Fabricante")
    est_fab = (
        estoque_df.groupby("fabricante_nome")
        .agg(skus=("produto_id","count"), pecas=("qtde","sum"), custo=("custo_total","sum"))
        .reset_index()
        .rename(columns={"fabricante_nome":"Fabricante","skus":"SKUs","pecas":"Peças","custo":"Custo Total (R$)"})
        .sort_values("Custo Total (R$)", ascending=False)
    )
    st.dataframe(est_fab, use_container_width=True, hide_index=True)

    fig_fab = px.bar(
        est_fab, x="Fabricante", y="Custo Total (R$)",
        title="Custo total em estoque por fabricante",
        text_auto=".2s"
    )
    st.plotly_chart(fig_fab, use_container_width=True)

    st.divider()

    # Curva ABC
    st.subheader("Curva ABC")
    classes = ["Todos"] + sorted(df["classe_abc"].dropna().unique().tolist())
    cls_sel = st.selectbox("Filtrar por classe", classes, key="est_cls")
    df_abc = df if cls_sel == "Todos" else df[df["classe_abc"] == cls_sel]

    contagem_abc = df_abc["classe_abc"].value_counts().reset_index()
    contagem_abc.columns = ["Classe", "Qtde SKUs"]
    fig_abc = px.pie(contagem_abc, names="Classe", values="Qtde SKUs", title="Distribuição Curva ABC")
    st.plotly_chart(fig_abc, use_container_width=True)

    st.dataframe(
        df_abc[["fabricante_nome","produto_id","descricao","classe_abc","qtde","custo_unit","custo_total"]]
        .sort_values("custo_total", ascending=False),
        use_container_width=True, hide_index=True
    )


def aba_vendas(vendas_df: pd.DataFrame):
    st.subheader("📈 Análise de Vendas")

    anos = sorted(vendas_df["ano"].unique(), reverse=True)
    ano_sel = st.selectbox("Ano", anos, key="vnd_ano")
    df = vendas_df[vendas_df["ano"] == ano_sel]

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Vendas (R$)", f"R$ {df['valor'].sum():,.0f}")
    col2.metric("Total Peças",       f"{df['quantidade'].sum():,.0f}")
    col3.metric("Marcas",            df["marca"].nunique())

    st.divider()

    # Vendas por marca
    vnd_marca = (
        df.groupby("marca")["valor"].sum()
        .reset_index().rename(columns={"marca":"Marca","valor":"Vendas (R$)"})
        .sort_values("Vendas (R$)", ascending=False)
    )
    fig_m = px.bar(vnd_marca, x="Marca", y="Vendas (R$)", title="Vendas por Marca", text_auto=".2s")
    st.plotly_chart(fig_m, use_container_width=True)

    # Evolução mensal
    vnd_mes = (
        df.groupby("mes")["valor"].sum()
        .reset_index().rename(columns={"mes":"Mês","valor":"Vendas (R$)"})
    )
    vnd_mes["Mês"] = vnd_mes["Mês"].map(MESES_PT)
    fig_mensal = px.line(vnd_mes, x="Mês", y="Vendas (R$)", markers=True, title="Evolução Mensal de Vendas")
    st.plotly_chart(fig_mensal, use_container_width=True)

    st.divider()
    st.subheader("Vendas por Segmento e Potência")
    seg_pot = (
        df.groupby(["segmento","potencia"])["quantidade"].sum()
        .reset_index().rename(columns={"segmento":"Segmento","potencia":"Potência (BTU)","quantidade":"Qtde"})
        .sort_values("Qtde", ascending=False)
    )
    st.dataframe(seg_pot, use_container_width=True, hide_index=True)


def aba_cobertura(estoque_df: pd.DataFrame, vendas_df: pd.DataFrame):
    st.subheader("📊 Cobertura de Estoque")

    if estoque_df.empty or vendas_df.empty:
        st.info("Carregue os dois arquivos (estoque e vendas) para ver a cobertura.")
        return

    # Demanda média mensal por produto (últimos 3 meses)
    ultimo_mes  = vendas_df["data_emissao"].max()
    tres_meses  = ultimo_mes - pd.DateOffset(months=3)
    vnd_recente = vendas_df[vendas_df["data_emissao"] >= tres_meses]

    demanda = (
        vnd_recente.groupby("codigo")["quantidade"].sum() / 3
    ).reset_index().rename(columns={"codigo":"produto_id_str","quantidade":"demanda_mensal"})

    estoque_df["produto_id_str"] = estoque_df["produto_id"].astype(int).astype(str)
    vendas_df["codigo"] = vendas_df["codigo"].astype(str).str.strip()

    df_cob = estoque_df.merge(
        demanda.rename(columns={"produto_id_str":"produto_id_str"}),
        left_on="produto_id_str", right_on="produto_id_str", how="left"
    )
    df_cob["demanda_mensal"] = df_cob["demanda_mensal"].fillna(0)
    df_cob["cobertura_meses"] = np.where(
        df_cob["demanda_mensal"] > 0,
        df_cob["qtde"] / df_cob["demanda_mensal"],
        np.inf
    )

    st.dataframe(
        df_cob[["fabricante_nome","produto_id","descricao","qtde","demanda_mensal","cobertura_meses"]]
        .sort_values("cobertura_meses"),
        use_container_width=True, hide_index=True
    )

    # Alertas de ruptura (cobertura < 1 mês)
    ruptura = df_cob[df_cob["cobertura_meses"] < 1]
    if not ruptura.empty:
        st.warning(f"⚠️ {len(ruptura)} produtos com cobertura inferior a 1 mês!")
        st.dataframe(
            ruptura[["fabricante_nome","produto_id","descricao","qtde","demanda_mensal","cobertura_meses"]],
            use_container_width=True, hide_index=True
        )


def aba_sugestao(estoque_df: pd.DataFrame, vendas_df: pd.DataFrame):
    st.subheader("🛒 Sugestão de Compras")

    if estoque_df.empty or vendas_df.empty:
        st.info("Carregue os dois arquivos para gerar sugestões.")
        return

    cobertura_alvo = st.slider("Cobertura alvo (meses)", 1, 6, 3, key="cob_alvo")

    ultimo_mes  = vendas_df["data_emissao"].max()
    tres_meses  = ultimo_mes - pd.DateOffset(months=3)
    vnd_recente = vendas_df[vendas_df["data_emissao"] >= tres_meses]

    demanda = (
        vnd_recente.groupby("codigo")["quantidade"].sum() / 3
    ).reset_index().rename(columns={"quantidade":"demanda_mensal"})

    estoque_df["produto_id_str"] = estoque_df["produto_id"].astype(int).astype(str)
    demanda["codigo"] = demanda["codigo"].astype(str).str.strip()

    df_sug = estoque_df.merge(
        demanda.rename(columns={"codigo":"produto_id_str"}),
        on="produto_id_str", how="left"
    )
    df_sug["demanda_mensal"] = df_sug["demanda_mensal"].fillna(0)
    df_sug["estoque_alvo"]   = df_sug["demanda_mensal"] * cobertura_alvo
    df_sug["sugestao_compra"]= (df_sug["estoque_alvo"] - df_sug["qtde"]).clip(lower=0)
    df_sug["valor_compra"]   = df_sug["sugestao_compra"] * df_sug["custo_unit"]

    df_sug = df_sug[df_sug["sugestao_compra"] > 0].sort_values("valor_compra", ascending=False)

    col1, col2 = st.columns(2)
    col1.metric("SKUs para comprar",   f"{len(df_sug):,}")
    col2.metric("Valor total sugerido",f"R$ {df_sug['valor_compra'].sum():,.0f}")

    st.dataframe(
        df_sug[["fabricante_nome","produto_id","descricao","qtde",
                "demanda_mensal","estoque_alvo","sugestao_compra","valor_compra"]]
        .rename(columns={
            "fabricante_nome":"Fabricante","produto_id":"Produto","descricao":"Descrição",
            "qtde":"Qtde Atual","demanda_mensal":"Dem. Mensal","estoque_alvo":"Estoque Alvo",
            "sugestao_compra":"Sugestão","valor_compra":"Valor (R$)"
        }),
        use_container_width=True, hide_index=True
    )

    # Por fabricante
    por_fab = (
        df_sug.groupby("fabricante_nome")["valor_compra"].sum()
        .reset_index().rename(columns={"fabricante_nome":"Fabricante","valor_compra":"Valor (R$)"})
        .sort_values("Valor (R$)", ascending=False)
    )
    fig_sug = px.bar(por_fab, x="Fabricante", y="Valor (R$)", title="Sugestão de compras por fabricante", text_auto=".2s")
    st.plotly_chart(fig_sug, use_container_width=True)


def aba_fornecedores(estoque_df: pd.DataFrame):
    st.subheader("🏭 Fornecedores e Condições Comerciais")

    dados_cond = [
        {
            "Fornecedor":   fab,
            "Limite (R$)":  f"R$ {c['limite']:,.0f}" if c["limite"] > 0 else "—",
            "Prazo (dias)": c["prazo"] if c["prazo"] > 0 else "Antecipado",
        }
        for fab, c in CONDICOES.items()
    ]
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
