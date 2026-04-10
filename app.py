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
        # Formato BR: ponto como milhar, vírgula como decimal
        if "," in txt and "." in txt:
            txt = txt.replace(".", "").replace(",", ".")
        elif "," in txt:
            txt = txt.replace(",", ".")
        return float(txt)
    except Exception:
        return 0.0

# ─────────────────────────────────────────────
# CARREGAMENTO
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def carregar_estoque(file_obj) -> pd.DataFrame:
    """
    Lê o Estoque.xlsx por POSIÇÃO de coluna.
    Estrutura real confirmada:
      col0 = Fabr              → fabricante_id
      col1 = Produto           → produto_id
      col2 = Descrição         → descricao
      col3 = ABC               → classe_abc
      col4 = Cubagem (Un)      → volume
      col5 = Qtde              → qtde
      col6 = Custo Unit. Médio → custo_unit
      col7 = Custo Total       → custo_total
    """
    file_obj.seek(0)
    df = pd.read_excel(file_obj, header=0)
    file_obj.seek(0)

    # Garante pelo menos 8 colunas
    if df.shape[1] < 8:
        raise ValueError(
            f"Excel tem {df.shape[1]} colunas, esperava ao menos 8. "
            f"Colunas encontradas: {list(df.columns)}"
        )

    # Pega as 8 primeiras por posição e renomeia
    df = df.iloc[:, :8].copy()
    df.columns = [
        "fabricante_id", "produto_id", "descricao",
        "classe_abc", "volume", "qtde",
        "custo_unit", "custo_total"
    ]

    # Remove linha de TOTAL e linhas completamente vazias
    df = df[df["descricao"].astype(str).str.strip().str.upper() != "TOTAL"]
    df = df.dropna(subset=["fabricante_id", "produto_id"])

    # Converte fabricante_id e produto_id para int
    df["fabricante_id"] = pd.to_numeric(df["fabricante_id"], errors="coerce")
    df["produto_id"]    = pd.to_numeric(df["produto_id"],    errors="coerce")
    df = df.dropna(subset=["fabricante_id", "produto_id"])
    df["fabricante_id"] = df["fabricante_id"].astype(int)
    df["produto_id"]    = df["produto_id"].astype(int)

    # Converte numéricos
    df["volume"]      = pd.to_numeric(df["volume"],      errors="coerce").fillna(0.0)
    df["qtde"]        = pd.to_numeric(df["qtde"],        errors="coerce").fillna(0.0)
    df["custo_unit"]  = pd.to_numeric(df["custo_unit"],  errors="coerce").fillna(0.0)
    df["custo_total"] = pd.to_numeric(df["custo_total"], errors="coerce").fillna(0.0)

    # Limpa textos
    df["descricao"]  = df["descricao"].fillna("").astype(str).str.strip()
    df["classe_abc"] = df["classe_abc"].fillna("").astype(str).str.strip()

    # Remove fabricantes ignorados
    df = df[~df["fabricante_id"].isin(FABRICANTES_IGNORAR)]

    # Adiciona nome do fabricante
    df["fabricante_nome"] = (
        df["fabricante_id"]
        .map(MAPA_FABRICANTES_ESTOQUE)
        .fillna("Outros")
    )

    return df.reset_index(drop=True)


@st.cache_data(show_spinner=False)
def carregar_vendas(file_obj) -> pd.DataFrame:
    raw   = file_obj.read()
    texto = decode_bytes(raw)

    COLUNAS = [
        "data_emissao", "marca", "segmento", "potencia",
        "ciclo", "codigo", "descricao", "quantidade", "valor"
    ]

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

    # Mantém só linhas com data válida dd/mm/aaaa
    df = df[df["data_emissao"].str.match(r"^\d{2}/\d{2}/\d{4}$", na=False)].copy()

    # Converte data
    df["data_emissao"] = pd.to_datetime(df["data_emissao"], format="%d/%m/%Y", errors="coerce")
    df = df.dropna(subset=["data_emissao"])

    # Normaliza marca
    df["marca"] = df["marca"].apply(normaliza_marca)

    # Converte quantidade e valor
    df["qtde"]     = pd.to_numeric(df["quantidade"].str.replace(",", "."), errors="coerce").fillna(0.0)
    df["vl_total"] = df["valor"].apply(limpa_valor)

    # Extrai produto_id do campo codigo
    df["produto_id"] = pd.to_numeric(
        df["codigo"].astype(str).str.extract(r"(\d+)")[0],
        errors="coerce"
    ).fillna(0).astype(int)

    # Extrai BTU da descrição
    df["btu"] = df["descricao"].str.extract(r"(\d{2})\s*[Bb][Tt][Uu]?")[0]
    df["btu"] = pd.to_numeric(df["btu"], errors="coerce")

    # Grupo/segmento limpo
    df["grupo"] = df["segmento"].astype(str).str.strip().str.title()

    # Ano e mês
    df["ano"] = df["data_emissao"].dt.year
    df["mes"] = df["data_emissao"].dt.month

    return df.reset_index(drop=True)


# ─────────────────────────────────────────────
# CURVA ABC
# ─────────────────────────────────────────────
def calcular_abc(df: pd.DataFrame, col_valor: str) -> pd.DataFrame:
    df = df.copy().sort_values(col_valor, ascending=False)
    total = df[col_valor].sum()
    if total == 0:
        df["pct_acum"] = 0.0
        df["curva"]    = "C"
        return df
    df["pct_acum"] = df[col_valor].cumsum() / total * 100
    df["curva"] = pd.cut(
        df["pct_acum"],
        bins=[-np.inf, 80, 95, np.inf],
        labels=["A", "B", "C"]
    )
    return df


# ─────────────────────────────────────────────
# ABAS
# ─────────────────────────────────────────────
def aba_estoque(estoque_df: pd.DataFrame):
    st.header("📦 Estoque & Curva ABC")

    # ── KPIs ──────────────────────────────────────────────────────────────
    total_itens  = len(estoque_df)
    total_pecas  = int(estoque_df["qtde"].sum())
    total_valor  = estoque_df["custo_total"].sum()
    n_fabricantes = estoque_df["fabricante_nome"].nunique()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("SKUs",            f"{total_itens:,}")
    c2.metric("Peças em estoque",f"{total_pecas:,}")
    c3.metric("Valor total",     f"R$ {total_valor:,.0f}")
    c4.metric("Fabricantes",     n_fabricantes)

    st.divider()

        # ── Estoque por fabricante ─────────────────────────────────────────────
    st.subheader("Estoque por fabricante")
    fab_group = (
        estoque_df.groupby("fabricante_nome")
        .agg(
            SKUs  =("produto_id",  "count"),
            Pecas =("qtde",        "sum"),
            Valor =("custo_total", "sum"),
        )
        .reset_index()
        .sort_values("Valor", ascending=False)
    )
    fab_group["Valor_fmt"] = fab_group["Valor"].apply(lambda x: f"R$ {x:,.0f}")

    col_tabela, col_pizza = st.columns([1, 1])
    with col_tabela:
        st.dataframe(
            fab_group.rename(columns={
                "fabricante_nome": "Fabricante",
                "SKUs":            "SKUs",
                "Pecas":           "Qtde",
                "Valor_fmt":       "Valor (R$)",
            })[["Fabricante", "SKUs", "Qtde", "Valor (R$)"]],
            use_container_width=True,
            hide_index=True,
        )
    with col_pizza:
        fig_fab = px.pie(
            fab_group,
            names="fabricante_nome",
            values="Valor",
            title="Participação por valor (R$)",
            hole=0.4,
        )
        st.plotly_chart(fig_fab, use_container_width=True)

    st.divider()

    # ── Curva ABC ──────────────────────────────────────────────────────────
    st.subheader("Curva ABC — por valor de estoque")
    abc_df = calcular_abc(estoque_df, "custo_total")

    fab_sel = st.selectbox(
        "Filtrar fabricante",
        ["Todos"] + sorted(estoque_df["fabricante_nome"].unique().tolist())
    )
    if fab_sel != "Todos":
        abc_df = abc_df[abc_df["fabricante_nome"] == fab_sel]

    resumo_abc = (
        abc_df.groupby("curva", observed=True)
        .agg(SKUs=("produto_id","count"), Valor=("custo_total","sum"))
        .reset_index()
    )
    st.dataframe(resumo_abc, use_container_width=True, hide_index=True)

    abc_show = abc_df[[
        "fabricante_nome","produto_id","descricao",
        "classe_abc","qtde","custo_unit","custo_total","curva","pct_acum"
    ]].copy()
    abc_show["custo_unit"]  = abc_show["custo_unit"].apply(lambda x: f"R$ {x:,.2f}")
    abc_show["custo_total"] = abc_show["custo_total"].apply(lambda x: f"R$ {x:,.0f}")
    abc_show["pct_acum"]    = abc_show["pct_acum"].apply(lambda x: f"{x:.1f}%")

    st.dataframe(abc_show, use_container_width=True, height=400, hide_index=True)


def aba_vendas(vendas_df: pd.DataFrame):
    st.header("📈 Vendas & Demanda")

    # ── KPIs ──────────────────────────────────────────────────────────────
    total_valor  = vendas_df["vl_total"].sum()
    total_pecas  = int(vendas_df["qtde"].sum())
    n_marcas     = vendas_df["marca"].nunique()
    periodo_dias = max(
        (vendas_df["data_emissao"].max() - vendas_df["data_emissao"].min()).days, 1
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Faturamento total",  f"R$ {total_valor/1e6:.1f}M")
    c2.metric("Peças vendidas",     f"{total_pecas:,}")
    c3.metric("Marcas",             n_marcas)
    c4.metric("Período (dias)",     periodo_dias)

    st.divider()

    # ── Vendas mensais ─────────────────────────────────────────────────────
    st.subheader("Vendas mensais por marca")
    mensal = (
        vendas_df.groupby(["ano","mes","marca"], as_index=False)
        .agg(vl_total=("vl_total","sum"))
    )
    mensal["periodo"] = mensal.apply(
        lambda r: f"{MESES_PT.get(int(r['mes']),str(int(r['mes'])))}/{int(r['ano'])}", axis=1
    )
    fig_m = px.bar(
        mensal, x="periodo", y="vl_total", color="marca",
        title="Faturamento mensal por marca",
        labels={"vl_total":"R$","periodo":"Mês","marca":"Marca"},
        barmode="stack"
    )
    st.plotly_chart(fig_m, use_container_width=True)

    st.divider()

    # ── Tabela detalhada ───────────────────────────────────────────────────
    st.subheader("Detalhe de vendas")
    marcas_disp = sorted(vendas_df["marca"].dropna().unique().tolist())
    filtro_marca = st.multiselect("Filtrar marca", marcas_disp)
    df_show = vendas_df.copy()
    if filtro_marca:
        df_show = df_show[df_show["marca"].isin(filtro_marca)]

    df_show["vl_total_fmt"] = df_show["vl_total"].apply(lambda x: f"R$ {x:,.0f}")
    df_show["data_fmt"]     = df_show["data_emissao"].dt.strftime("%d/%m/%Y")

    st.dataframe(
        df_show[[
            "data_fmt","marca","grupo","btu",
            "produto_id","descricao","qtde","vl_total_fmt"
        ]].rename(columns={
            "data_fmt":"Data","marca":"Marca","grupo":"Grupo",
            "btu":"BTU","produto_id":"Produto","descricao":"Descrição",
            "qtde":"Qtde","vl_total_fmt":"Valor (R$)"
        }),
        use_container_width=True, height=400, hide_index=True
    )


def aba_cobertura(estoque_df: pd.DataFrame, vendas_df: pd.DataFrame):
    st.header("📊 Cobertura de Estoque")

    if estoque_df.empty or vendas_df.empty:
        st.info("Carregue os arquivos de estoque e vendas para ver a cobertura.")
        return

    dias = max(
        (vendas_df["data_emissao"].max() - vendas_df["data_emissao"].min()).days, 1
    )
    demanda = (
        vendas_df.groupby("produto_id", as_index=False)
        .agg(qtde_vendida=("qtde","sum"))
    )
    demanda["demanda_dia"] = demanda["qtde_vendida"] / dias

    cob = estoque_df.merge(demanda, on="produto_id", how="left")
    cob["demanda_dia"]  = cob["demanda_dia"].fillna(0)
    cob["qtde_vendida"] = cob["qtde_vendida"].fillna(0)
    cob["cobertura_dias"] = np.where(
        cob["demanda_dia"] > 0,
        cob["qtde"] / cob["demanda_dia"],
        np.inf
    )

    def classifica(d):
        if d == np.inf:   return "Sem giro"
        elif d < 30:      return "Crítico"
        elif d < 60:      return "Atenção"
        else:             return "OK"

    cob["status"] = cob["cobertura_dias"].apply(classifica)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🔴 Crítico (<30d)",   (cob["status"]=="Crítico").sum())
    c2.metric("🟡 Atenção (30-60d)", (cob["status"]=="Atenção").sum())
    c3.metric("🟢 OK (>60d)",        (cob["status"]=="OK").sum())
    c4.metric("⚪ Sem Giro",         (cob["status"]=="Sem giro").sum())

    st.divider()

    status_sel = st.multiselect(
        "Filtrar Status",
        ["Crítico","Atenção","OK","Sem giro"],
        default=["Crítico","Atenção"]
    )
    cob_show = cob[cob["status"].isin(status_sel)].copy() if status_sel else cob.copy()
    cob_show["cobertura_fmt"]  = cob_show["cobertura_dias"].apply(
        lambda x: "∞" if x == np.inf else f"{x:.0f} dias"
    )
    cob_show["custo_total_fmt"] = cob_show["custo_total"].apply(lambda x: f"R$ {x:,.0f}")

    st.dataframe(
        cob_show[[
            "fabricante_nome","produto_id","descricao",
            "qtde","custo_total_fmt","cobertura_fmt","status"
        ]].rename(columns={
            "fabricante_nome":"Fabricante","produto_id":"Produto",
            "descricao":"Descrição","qtde":"Qtde",
            "custo_total_fmt":"Valor (R$)","cobertura_fmt":"Cobertura","status":"Status"
        }).sort_values("cobertura_dias" if "cobertura_dias" in cob_show.columns else "status"),
        use_container_width=True, height=450, hide_index=True
    )


def aba_sugestao(estoque_df: pd.DataFrame, vendas_df: pd.DataFrame):
    st.header("🛒 Sugestão de Compras")

    if estoque_df.empty or vendas_df.empty:
        st.info("Carregue os arquivos de estoque e vendas para gerar sugestões.")
        return

    dias_alvo = st.slider("Dias de cobertura alvo", 30, 180, 90)

    dias = max(
        (vendas_df["data_emissao"].max() - vendas_df["data_emissao"].min()).days, 1
    )
    demanda = (
        vendas_df.groupby("produto_id", as_index=False)
        .agg(qtde_vendida=("qtde","sum"))
    )
    demanda["demanda_dia"] = demanda["qtde_vendida"] / dias

    sug = estoque_df.merge(demanda, on="produto_id", how="left")
    sug["demanda_dia"]  = sug["demanda_dia"].fillna(0)
    sug["estoque_alvo"] = sug["demanda_dia"] * dias_alvo
    sug["comprar"]      = (sug["estoque_alvo"] - sug["qtde"]).clip(lower=0).round(0)
    sug["valor_compra"] = sug["comprar"] * sug["custo_unit"]

    sug = sug[sug["comprar"] > 0].copy()

    if sug.empty:
        st.success("Nenhuma compra necessária para o período selecionado.")
        return

    # Resumo por fabricante
    resumo = (
        sug.groupby("fabricante_nome")
        .agg(SKUs=("produto_id","count"), Valor=("valor_compra","sum"))
        .reset_index()
        .sort_values("Valor", ascending=False)
    )
    resumo["Valor_fmt"] = resumo["Valor"].apply(lambda x: f"R$ {x:,.0f}")

    st.subheader("Resumo por fabricante")
    col_r, col_g = st.columns([1, 1])
    with col_r:
        st.dataframe(
            resumo.rename(columns={
                "fabricante_nome":"Fabricante","SKUs":"SKUs","Valor_fmt":"Valor (R$)"
            })[["Fabricante","SKUs","Valor (R$)"]],
            use_container_width=True, hide_index=True
        )
    with col_g:
        fig_s = px.bar(
            resumo, x="fabricante_nome", y="Valor",
            title="Valor de compra por fabricante",
            labels={"fabricante_nome":"Fabricante","Valor":"R$"}
        )
        st.plotly_chart(fig_s, use_container_width=True)

    st.divider()
    st.subheader("Detalhe por produto")

    fab_sel = st.selectbox(
        "Filtrar fabricante",
        ["Todos"] + sorted(sug["fabricante_nome"].unique().tolist())
    )
    sug_show = sug if fab_sel == "Todos" else sug[sug["fabricante_nome"] == fab_sel]
    sug_show = sug_show.copy()
    sug_show["custo_unit_fmt"]  = sug_show["custo_unit"].apply(lambda x: f"R$ {x:,.2f}")
    sug_show["valor_compra_fmt"]= sug_show["valor_compra"].apply(lambda x: f"R$ {x:,.0f}")

    st.dataframe(
        sug_show[[
            "fabricante_nome","produto_id","descricao","classe_abc",
            "qtde","estoque_alvo","comprar","custo_unit_fmt","valor_compra_fmt"
        ]].rename(columns={
            "fabricante_nome":"Fabricante","produto_id":"Produto",
            "descricao":"Descrição","classe_abc":"ABC",
            "qtde":"Estoque Atual","estoque_alvo":"Alvo",
            "comprar":"Comprar","custo_unit_fmt":"Custo Unit.",
            "valor_compra_fmt":"Valor Compra"
        }).sort_values("valor_compra", ascending=False),
        use_container_width=True, height=450, hide_index=True
    )

    # Botão download CSV
    csv = sug_show[[
        "fabricante_nome","produto_id","descricao",
        "qtde","comprar","custo_unit","valor_compra"
    ]].to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")
    st.download_button(
        "⬇️ Baixar sugestão (.csv)",
        data=csv,
        file_name="sugestao_compras.csv",
        mime="text/csv"
    )


def aba_fornecedores(estoque_df: pd.DataFrame):
    st.header("🏭 Fornecedores & Limites de Crédito")

    dados_cond = [
        {
            "Fornecedor":  k,
            "Limite (R$)": f"R$ {v['limite']:,.0f}",
            "Prazo (dias)": v["prazo"],
        }
        for k, v in CONDICOES.items()
    ]
    st.dataframe(
        pd.DataFrame(dados_cond),
        use_container_width=True,
        hide_index=True
    )

    if not estoque_df.empty:
        st.divider()
        st.subheader("Estoque atual vs Limite de crédito")

        est_fab = (
            estoque_df.groupby("fabricante_nome")["custo_total"]
            .sum()
            .reset_index()
        )
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

        st.dataframe(
            df_cred.assign(**{
                "Limite (R$)":        df_cred["Limite (R$)"].apply(lambda x: f"R$ {x:,.0f}"),
                "Estoque Atual (R$)": df_cred["Estoque Atual (R$)"].apply(lambda x: f"R$ {x:,.0f}"),
                "% do Limite":        df_cred["% do Limite"].apply(lambda x: f"{x:.1f}%"),
            }),
            use_container_width=True,
            hide_index=True
        )

        fig_c = px.bar(
            df_cred[df_cred["Limite (R$)"] > 0],
            x="Fornecedor",
            y=["Limite (R$)","Estoque Atual (R$)"],
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
            st.sidebar.success(f"Estoque: {len(estoque_df):,} produtos carregados")
        except Exception as e:
            st.sidebar.error(f"Erro ao carregar estoque: {e}")

    if file_vendas:
        try:
            vendas_df = carregar_vendas(file_vendas)
            st.sidebar.success(f"Vendas: {len(vendas_df):,} registros carregados")
        except Exception as e:
            st.sidebar.error(f"Erro ao carregar vendas: {e}")

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
