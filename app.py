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
    Exemplos tratados:
      'R$ 6.265.053,00'  -> 6265053.0
      'R$ 1.067'         -> 1067.0
      '1067,50'          -> 1067.5
      '1067.50'          -> 1067.5
      '6265053'          -> 6265053.0
    """
    try:
        txt = str(s).strip()
        # Remove R$, espaços e caracteres não numéricos exceto . e ,
        txt = re.sub(r"[R$\s]", "", txt)
        txt = txt.strip()

        if not txt:
            return 0.0

        tem_virgula = "," in txt
        tem_ponto   = "." in txt

        if tem_virgula and tem_ponto:
            # Formato BR clássico: 6.265.053,00
            # Remove todos os pontos (separador de milhar) e troca vírgula por ponto
            txt = txt.replace(".", "").replace(",", ".")
        elif tem_virgula and not tem_ponto:
            # Só vírgula: pode ser decimal BR '1067,50' ou milhar '1.067' sem ponto
            # Assume vírgula = decimal
            txt = txt.replace(",", ".")
        elif tem_ponto and not tem_virgula:
            # Só ponto: heurística
            partes = txt.split(".")
            # Se mais de um ponto → todos são milhar: '1.234.567'
            if len(partes) > 2:
                txt = txt.replace(".", "")
            # Se um ponto e parte decimal com 3 dígitos → milhar: '1.067'
            elif len(partes) == 2 and len(partes[1]) == 3:
                txt = txt.replace(".", "")
            # Caso contrário → decimal normal: '1067.50'
        # else: sem ponto nem vírgula → número inteiro puro

        return float(txt)
    except Exception:
        return 0.0

# ─────────────────────────────────────────────
# CARREGAMENTO DE DADOS
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def carregar_vendas(file_obj):
    raw = file_obj.read()
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

    # Remove colunas duplicadas caso existam
    df = df.loc[:, ~df.columns.duplicated()]

    # Descarta linhas onde data_emissao não parece uma data
    df = df[df["data_emissao"].str.match(r"\d{2}/\d{2}/\d{4}", na=False)].copy()

    # Converte data via apply (evita bug de duplicate keys do pandas)
    df["data_emissao"] = df["data_emissao"].apply(
        lambda x: pd.to_datetime(x, dayfirst=True, errors="coerce")
    )

    # Normaliza marca
    df["marca"] = df["marca"].apply(normaliza_marca)

    # Converte valor
    df["valor"] = df["valor"].apply(limpa_valor)

    # Converte quantidade (mantém só dígitos)
    df["quantidade"] = pd.to_numeric(
        df["quantidade"].str.replace(r"\D", "", regex=True),
        errors="coerce"
    ).fillna(0).astype(int)

    # Colunas auxiliares de tempo
    df["ano"]      = df["data_emissao"].dt.year
    df["mes"]      = df["data_emissao"].dt.month
    df["mes_nome"] = df["mes"].map(MESES_PT)

    return df


@st.cache_data(show_spinner=False)
def carregar_estoque(file_obj):
    # ── Tenta descobrir em qual linha está o cabeçalho real ──────────────────
    # Lê as primeiras linhas sem cabeçalho para inspecionar
    df_raw = pd.read_excel(file_obj, header=None, nrows=5)

    header_row = 0  # default
    for i, row in df_raw.iterrows():
        valores = [str(v).strip() for v in row.values]
        # Procura a linha que contenha "Fabr" ou "Produto"
        if "Fabr" in valores or "Produto" in valores:
            header_row = i
            break

    # Relê o arquivo a partir da linha do cabeçalho real
    # (file_obj já foi lido, mas o Streamlit UploadedFile suporta seek)
    file_obj.seek(0)
    df = pd.read_excel(file_obj, header=header_row)
    df.columns = [str(c).strip() for c in df.columns]

    # ── Renomeia para nomes internos ─────────────────────────────────────────
    rename = {
        "Fabr":                         "fabricante_id",
        "Produto":                      "produto_id",
        "Descrição":                    "descricao",
        "ABC":                          "abc",
        "Cubagem (Un)":                 "cubagem",
        "Qtde":                         "qtde",
        "Custo Entrada Unitário Médio": "custo_unit",
        "Custo Entrada Total":          "custo_total",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    # ── Valida que as colunas essenciais existem ─────────────────────────────
    faltando = [c for c in ("fabricante_id", "produto_id") if c not in df.columns]
    if faltando:
        raise KeyError(
            f"Colunas não encontradas no Excel: {faltando}. "
            f"Colunas disponíveis: {list(df.columns)}"
        )

    # ── Limpeza ──────────────────────────────────────────────────────────────
    df = df.dropna(subset=["fabricante_id", "produto_id"])
    df["fabricante_id"] = pd.to_numeric(df["fabricante_id"], errors="coerce")
    df = df.dropna(subset=["fabricante_id"])  # remove linhas onde não virou número
    df = df[~df["fabricante_id"].isin(FABRICANTES_IGNORAR)]
    df["fabricante_nome"] = (
        df["fabricante_id"].map(MAPA_FABRICANTES_ESTOQUE).fillna("Outros")
    )

    for col in ["qtde", "custo_unit", "custo_total", "cubagem"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        else:
            df[col] = 0.0

    return df

# ─────────────────────────────────────────────
# ABAS
# ─────────────────────────────────────────────
def aba_estoque(estoque_df):
    st.header("📦 Estoque & ABC")

    col1, col2, col3, col4 = st.columns(4)
    total_itens = len(estoque_df)
    total_unid  = int(estoque_df["qtde"].sum())
    total_custo = estoque_df["custo_total"].sum()
    sem_custo   = int((estoque_df["custo_unit"] == 0).sum())

    col1.metric("SKUs",            f"{total_itens:,}")
    col2.metric("Unidades",        f"{total_unid:,}")
    col3.metric("Custo Total (R$)",f"R$ {total_custo:,.0f}")
    col4.metric("SKUs s/ custo",   f"{sem_custo}")

    st.divider()

    fab_df = (
        estoque_df.groupby("fabricante_nome")
        .agg(SKUs=("produto_id","count"),
             Unidades=("qtde","sum"),
             Custo_Total=("custo_total","sum"))
        .reset_index()
        .sort_values("Custo_Total", ascending=False)
    )
    fab_df["Custo_Total"] = fab_df["Custo_Total"].apply(lambda x: f"R$ {x:,.0f}")

    st.subheader("Resumo por Fabricante")
    st.dataframe(fab_df, use_container_width=True, hide_index=True)

    st.divider()

    st.subheader("Curva ABC")
    abc_col = "abc" if "abc" in estoque_df.columns else None
    if abc_col:
        abc_df = (
            estoque_df[estoque_df[abc_col].notna() & (estoque_df[abc_col] != "")]
            .groupby(abc_col)
            .agg(SKUs=("produto_id","count"),
                 Unidades=("qtde","sum"),
                 Custo=("custo_total","sum"))
            .reset_index()
            .sort_values("Custo", ascending=False)
        )
        fig = px.bar(abc_df, x=abc_col, y="Custo", color=abc_col,
                     title="Custo de Estoque por Curva ABC",
                     labels={abc_col:"Curva","Custo":"R$"})
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(abc_df, use_container_width=True, hide_index=True)
    else:
        st.info("Coluna ABC não encontrada no arquivo.")


def aba_vendas(vendas_df):
    st.header("📈 Vendas & Demanda")

    anos_disp = sorted(vendas_df["ano"].dropna().unique().astype(int), reverse=True)
    if not anos_disp:
        st.warning("Sem dados de vendas.")
        return

    col_ano, col_mes = st.columns(2)
    ano_sel = col_ano.selectbox("Ano", anos_disp, index=0)

    meses_disp = sorted(
        vendas_df[vendas_df["ano"] == ano_sel]["mes"].dropna().unique().astype(int)
    )
    opcoes_mes = ["Todos"] + [MESES_PT[m] for m in meses_disp]
    mes_sel = col_mes.selectbox("Mês (ou Todos)", opcoes_mes, index=0)

    df_f = vendas_df[vendas_df["ano"] == ano_sel].copy()
    if mes_sel != "Todos":
        num_mes = {v: k for k, v in MESES_PT.items()}[mes_sel]
        df_f = df_f[df_f["mes"] == num_mes]

    faturamento = df_f["valor"].sum()
    unidades    = int(df_f["quantidade"].sum())
    nf_linhas   = len(df_f)

    k1, k2, k3 = st.columns(3)
    k1.metric("Faturamento", f"R$ {faturamento:,.0f}")
    k2.metric("Unidades",    f"{unidades:,}")
    k3.metric("NFs / linhas",f"{nf_linhas:,}")

    st.divider()

    st.subheader("Vendas por Marca")
    marca_df = (
        df_f.groupby("marca")
        .agg(VL_Total=("valor","sum"), Unidades=("quantidade","sum"))
        .reset_index()
        .sort_values("VL_Total", ascending=False)
    )
    marca_df["VL_Total_fmt"] = marca_df["VL_Total"].apply(lambda x: f"R$ {x:,.2f}")
    st.dataframe(
        marca_df[["marca","VL_Total_fmt","Unidades"]].rename(columns={
            "marca":"Marca","VL_Total_fmt":"VL Total (R$)","Unidades":"Unidades"
        }),
        use_container_width=True, hide_index=True
    )

    fig = px.bar(
        marca_df.sort_values("VL_Total"),
        x="VL_Total", y="marca", orientation="h",
        title=f"Faturamento por Marca — {mes_sel}/{ano_sel}",
        labels={"VL_Total":"R$","marca":"Marca"},
        color="marca"
    )
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    st.subheader("Evolução Mensal")
    ev_df = (
        vendas_df[vendas_df["ano"] == ano_sel]
        .groupby(["mes","mes_nome","marca"])
        .agg(VL_Total=("valor","sum"))
        .reset_index()
        .sort_values("mes")
    )
    fig2 = px.line(
        ev_df, x="mes_nome", y="VL_Total", color="marca",
        title=f"Evolução Mensal por Marca — {ano_sel}",
        labels={"mes_nome":"Mês","VL_Total":"R$","marca":"Marca"},
        markers=True
    )
    st.plotly_chart(fig2, use_container_width=True)


def aba_cobertura(estoque_df, vendas_df):
    st.header("📊 Cobertura de Estoque")

    if vendas_df.empty or estoque_df.empty:
        st.warning("Carregue os dois arquivos para calcular a cobertura.")
        return

    ultimo_ano = int(vendas_df["ano"].max())
    ultimo_mes = int(vendas_df[vendas_df["ano"] == ultimo_ano]["mes"].max())

    meses_ref = []
    m, a = ultimo_mes, ultimo_ano
    for _ in range(3):
        meses_ref.append((a, m))
        m -= 1
        if m == 0:
            m, a = 12, a - 1

    meses_set = set(meses_ref)
    df_ref = vendas_df[
        vendas_df.apply(lambda r: (int(r["ano"]), int(r["mes"])) in meses_set, axis=1)
    ]

    media_mes = (
        df_ref.groupby(["codigo","marca"])["quantidade"]
        .sum()
        .div(3)
        .reset_index()
        .rename(columns={"quantidade":"media_mensal"})
    )

    est = estoque_df[["produto_id","fabricante_nome","qtde","custo_unit"]].copy()
    est["produto_id"]      = est["produto_id"].astype(str).str.strip().str.lstrip("0")
    media_mes["codigo"]    = media_mes["codigo"].astype(str).str.strip().str.lstrip("0")

    merged = est.merge(media_mes, left_on="produto_id", right_on="codigo", how="left")
    merged["media_mensal"] = merged["media_mensal"].fillna(0)
    merged["cobertura_meses"] = np.where(
        merged["media_mensal"] > 0,
        merged["qtde"] / merged["media_mensal"],
        np.inf
    )

    merged["status"] = pd.cut(
        merged["cobertura_meses"],
        bins=[-np.inf, 1, 2, 3, np.inf],
        labels=["🔴 Crítico (<1m)", "🟡 Baixo (1-2m)", "🟢 OK (2-3m)", "⚪ Alto (>3m)"]
    )

    st.dataframe(
        merged[["produto_id","fabricante_nome","qtde","media_mensal",
                "cobertura_meses","status"]]
        .rename(columns={
            "produto_id":"Código","fabricante_nome":"Marca","qtde":"Estoque",
            "media_mensal":"Média/Mês","cobertura_meses":"Cobertura (meses)","status":"Status"
        })
        .sort_values("Cobertura (meses)"),
        use_container_width=True, hide_index=True
    )


def aba_sugestao(estoque_df, vendas_df):
    st.header("🛒 Sugestão de Compras")

    if vendas_df.empty or estoque_df.empty:
        st.warning("Carregue os dois arquivos para gerar sugestão.")
        return

    ultimo_ano = int(vendas_df["ano"].max())
    ultimo_mes = int(vendas_df[vendas_df["ano"] == ultimo_ano]["mes"].max())

    meses_ref = []
    m, a = ultimo_mes, ultimo_ano
    for _ in range(3):
        meses_ref.append((a, m))
        m -= 1
        if m == 0:
            m, a = 12, a - 1

    meses_set = set(meses_ref)
    df_ref = vendas_df[
        vendas_df.apply(lambda r: (int(r["ano"]), int(r["mes"])) in meses_set, axis=1)
    ]

    media_mes = (
        df_ref.groupby("codigo")["quantidade"]
        .sum()
        .div(3)
        .reset_index()
        .rename(columns={"quantidade":"media_mensal"})
    )

    cobertura_alvo = st.slider("Cobertura desejada (meses)", 1, 6, 3)

    est = estoque_df[["produto_id","fabricante_nome","descricao","qtde","custo_unit"]].copy()
    est["produto_id"]   = est["produto_id"].astype(str).str.strip().str.lstrip("0")
    media_mes["codigo"] = media_mes["codigo"].astype(str).str.strip().str.lstrip("0")

    df_s = est.merge(media_mes, left_on="produto_id", right_on="codigo", how="left")
    df_s["media_mensal"]    = df_s["media_mensal"].fillna(0)
    df_s["estoque_alvo"]    = (df_s["media_mensal"] * cobertura_alvo).apply(np.ceil)
    df_s["sugestao_compra"] = (df_s["estoque_alvo"] - df_s["qtde"]).clip(lower=0).apply(np.ceil)
    df_s["valor_estimado"]  = df_s["sugestao_compra"] * df_s["custo_unit"]

    df_s = df_s[df_s["sugestao_compra"] > 0].sort_values("valor_estimado", ascending=False)

    k1, k2, k3 = st.columns(3)
    k1.metric("SKUs p/ comprar",  f"{len(df_s):,}")
    k2.metric("Unidades totais",  f"{int(df_s['sugestao_compra'].sum()):,}")
    k3.metric("Valor est. compra",f"R$ {df_s['valor_estimado'].sum():,.0f}")

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
