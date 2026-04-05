import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import re
from io import StringIO

st.set_page_config(page_title="Motor de Compras AC", layout="wide")
st.title("Motor de Compras — Ar Condicionado")

# ─────────────────────────────────────────
# MAPA DE FABRICANTES (código ERP → nome)
# Baseado nos dados reais do Estoque.xlsx
# ─────────────────────────────────────────
MAPA_FABRICANTES = {
    2:   "LG",
    3:   "Samsung",
    7:   "Gree",
    8:   "Daikin",
    9:   "Midea",
    10:  "Trane",
    11:  "TCL",
    900: "Acessório/Serviço",
    995: "Indicação de Obra",
    998: "Danificado",
    999: "Semi",
}

# Mapa de normalização de nomes vindos do CSV de vendas
NORMALIZA_MARCA = {
    "SPRINGER MIDEA": "Midea",
    "SPRINGER":       "Midea",
    "MIDEA":          "Midea",
    "LG":             "LG",
    "TCL":            "TCL",
    "DAIKIN":         "Daikin",
    "GREE":           "Gree",
    "SAMSUNG":        "Samsung",
    "TRANE":          "Trane",
}

LIMITES_CREDITO = {
    "LG":     {"limite": 3_500_000,  "prazo_dias": 30},
    "TCL":    {"limite": 19_000_000, "prazo_dias": 90},
    "Midea":  {"limite": 28_000_000, "prazo_dias": 90},
    "Gree":   {"limite": 45_000_000, "prazo_dias": 120},
    "Daikin": {"limite": 45_000_000, "prazo_dias": 150},
    "Samsung":{"limite": 0,          "prazo_dias": 0},
    "Trane":  {"limite": 0,          "prazo_dias": 0},
}

# ─────────────────────────────────────────
# FUNÇÕES AUXILIARES
# ─────────────────────────────────────────

def inferir_grupo(desc: str) -> str:
    if pd.isna(desc):
        return "OUTROS"
    d = str(desc).upper()
    if "VRF" in d or "TVR" in d or "DVM" in d:
        return "VRF"
    if "MULTI" in d or "BI-SPLIT" in d or "BISPLIT" in d:
        return "MSP"
    if any(x in d for x in ["CASSETE", "PISO TETO", "TETO INV", "TETO LEVE",
                              "TETO INV", "K7 INV", "K7 RED", "K7 LEVE",
                              "DUTO", " DT ", " PT ", "K7 REDONDO"]):
        return "LCIN"
    if any(x in d for x in ["AR COND", "EVAP.", "COND.", "SPLIT"]):
        return "INV"
    return "OUTROS"

def extrair_btu_desc(desc: str):
    if pd.isna(desc):
        return np.nan
    d = str(desc).upper()
    match = re.search(r"\b(7|9|09|12|18|24|30|36|48|55|60)\b", d)
    if match:
        v = int(match.group())
        return 9 if v in (7, 9) else v
    return np.nan

def classificar_tipo_item(fabr):
    try:
        f = int(fabr)
    except:
        return "desconhecido"
    if f == 900: return "acessorio_servico"
    if f == 995: return "indicacao_obra"
    if f == 998: return "danificado"
    if f == 999: return "semi"
    return "giro"

def calcular_abc(df, coluna_valor):
    df = df.copy()
    df = df[df[coluna_valor] > 0].copy()
    df = df.sort_values(coluna_valor, ascending=False)
    total = df[coluna_valor].sum()
    if total <= 0:
        df["curva_abc"] = "C"
        return df
    df["acum_%"] = df[coluna_valor].cumsum() / total * 100
    df["curva_abc"] = df["acum_%"].apply(
        lambda x: "A" if x <= 70 else ("B" if x <= 90 else "C")
    )
    return df

def ler_bytes_com_encoding(file):
    """Lê bytes de um arquivo e detecta encoding automaticamente."""
    conteudo = file.read()
    for enc in ["utf-8-sig", "latin-1", "iso-8859-1", "cp1252", "utf-8"]:
        try:
            return conteudo.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
    raise ValueError("Não foi possível detectar o encoding do arquivo.")

# ─────────────────────────────────────────
# LEITURA DO ESTOQUE
# ─────────────────────────────────────────

@st.cache_data
def carregar_estoque(file):
    df_raw = pd.read_excel(file, header=None)

    # Encontra linha onde aparece "Fabr"
    header_idx = None
    for i, row in df_raw.iterrows():
        if "Fabr" in row.values:
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("Cabeçalho 'Fabr' não encontrado no Estoque.xlsx.")

    df = df_raw.iloc[header_idx + 1:].copy()
    df.columns = df_raw.iloc[header_idx].tolist()
    df = df.dropna(how="all")

    # Remove linha de TOTAL
    desc_col = "Descrição" if "Descrição" in df.columns else df.columns[2]
    df = df[df[desc_col].astype(str) != "TOTAL"]

    df = df.rename(columns={
        "Fabr":                          "fabricante_codigo",
        "Produto":                       "produto_codigo",
        "Descrição":                     "descricao",
        "ABC":                           "abc_erp",
        "Cubagem (Un)":                  "cubagem_un",
        "Qtde":                          "qtde_estoque",
        "Custo Entrada Unitário Médio":  "custo_medio_unit",
        "Custo Entrada Total":           "custo_total",
    })

    for col in ["fabricante_codigo", "qtde_estoque", "custo_medio_unit", "custo_total"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["tipo_item"]       = df["fabricante_codigo"].apply(classificar_tipo_item)
    df["fabricante_nome"] = df["fabricante_codigo"].map(MAPA_FABRICANTES).fillna("Outros")
    df["grupo"]           = df["descricao"].apply(inferir_grupo)
    df["btu"]             = df["descricao"].apply(extrair_btu_desc)

    # Apenas itens de giro para as análises
    return df[df["tipo_item"] == "giro"].copy()

# ─────────────────────────────────────────
# LEITURA DAS VENDAS
# ─────────────────────────────────────────

@st.cache_data
def carregar_vendas(file):
    # Detecta encoding automaticamente (resolve o UnicodeDecodeError)
    texto, enc_usado = ler_bytes_com_encoding(file)
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
        "Descrição":   "descricao",
        "Qtde":        "quantidade",
        "VL Total":    "valor_total",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    df["data_emissao"] = pd.to_datetime(df["data_emissao"], dayfirst=True, errors="coerce")
    df["ano"] = df["data_emissao"].dt.year
    df["mes"] = df["data_emissao"].dt.month

    for col in ["quantidade", "valor_total"]:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str)
                .str.replace(".", "", regex=False)
                .str.replace(",", ".", regex=False),
                errors="coerce"
            )

    # Normaliza nome da marca (SPRINGER MIDEA → Midea, DAIKIN → Daikin etc.)
    if "marca" in df.columns:
        df["marca"] = (df["marca"].astype(str).str.strip().str.upper()
                       .map(NORMALIZA_MARCA)
                       .fillna(df["marca"].astype(str).str.strip().str.title()))

    # BTU
    if "btu" in df.columns:
        df["btu"] = pd.to_numeric(df["btu"], errors="coerce")
        if "descricao" in df.columns:
            mask = df["btu"].isna()
            df.loc[mask, "btu"] = df.loc[mask, "descricao"].apply(extrair_btu_desc)
    elif "descricao" in df.columns:
        df["btu"] = df["descricao"].apply(extrair_btu_desc)

    return df

# ─────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────

st.sidebar.header("Carregar dados")
file_estoque = st.sidebar.file_uploader("Estoque (.xlsx)", type=["xlsx"])
file_vendas  = st.sidebar.file_uploader("Vendas (.csv)",  type=["csv"])

cobertura_alvo = st.sidebar.slider(
    "Cobertura alvo (dias de estoque)", 30, 120, 60, step=10
)
cenario = st.sidebar.selectbox(
    "Cenário de demanda",
    ["Manutenção (0%)", "Alta (+10%)", "Alta (+20%)", "Redução (-10%)", "Redução (-20%)"]
)
fator_cenario = {
    "Manutenção (0%)":  1.00,
    "Alta (+10%)":      1.10,
    "Alta (+20%)":      1.20,
    "Redução (-10%)":   0.90,
    "Redução (-20%)":   0.80,
}[cenario]

# ─────────────────────────────────────────
# TABS
# ─────────────────────────────────────────

tab1, tab2, tab3, tab4 = st.tabs([
    "Estoque & ABC",
    "Vendas & Demanda",
    "Sugestão de Compras",
    "Crédito por Fornecedor",
])

# ════════════════════════════════════════
# TAB 1 — ESTOQUE & ABC
# ════════════════════════════════════════
with tab1:
    if not file_estoque:
        st.info("Faça upload do arquivo de Estoque no menu lateral.")
    else:
        estoque = carregar_estoque(file_estoque)

        st.subheader("Visão geral do Estoque")
        c1, c2, c3 = st.columns(3)
        c1.metric("SKUs de giro",      f"{estoque['produto_codigo'].nunique():,}")
        c2.metric("Unidades totais",   f"{estoque['qtde_estoque'].sum():,.0f}")
        c3.metric("Custo total (R$)",  f"R$ {estoque['custo_total'].sum():,.0f}")

        fab_opts = ["Todos"] + sorted(estoque["fabricante_nome"].dropna().unique().tolist())
        grp_opts = ["Todos"] + sorted(estoque["grupo"].dropna().unique().tolist())
        col1, col2 = st.columns(2)
        fab_sel = col1.selectbox("Filtrar fabricante", fab_opts)
        grp_sel = col2.selectbox("Filtrar grupo",      grp_opts)

        df_est = estoque.copy()
        if fab_sel != "Todos":
            df_est = df_est[df_est["fabricante_nome"] == fab_sel]
        if grp_sel != "Todos":
            df_est = df_est[df_est["grupo"] == grp_sel]

        df_abc = calcular_abc(df_est, "custo_total")

        st.subheader("Curva ABC por valor em estoque")
        resumo_abc = df_abc.groupby("curva_abc")["custo_total"].sum().reset_index()
        if not resumo_abc.empty:
            fig = px.pie(
                resumo_abc,
                names="curva_abc", values="custo_total",
                color="curva_abc",
                color_discrete_map={"A": "#2ecc71", "B": "#f1c40f", "C": "#e74c3c"},
                title="Participação por classe ABC (valor em estoque)",
            )
            st.plotly_chart(fig, use_container_width=True)

        cols_show = [c for c in [
            "fabricante_nome", "produto_codigo", "descricao",
            "grupo", "btu", "abc_erp", "curva_abc",
            "qtde_estoque", "custo_medio_unit", "custo_total"
        ] if c in df_abc.columns]

        st.dataframe(df_abc[cols_show].reset_index(drop=True), use_container_width=True)

        st.download_button(
            "Baixar estoque com ABC (CSV)",
            df_abc[cols_show].to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
            "estoque_abc.csv", "text/csv",
        )

# ════════════════════════════════════════
# TAB 2 — VENDAS & DEMANDA
# ════════════════════════════════════════
with tab2:
    if not file_vendas:
        st.info("Faça upload do arquivo de Vendas no menu lateral.")
    else:
        vendas = carregar_vendas(file_vendas)

        st.subheader("Histórico de vendas")

        col1, col2 = st.columns(2)
        marca_opts = ["Todas"] + sorted(vendas["marca"].dropna().unique().tolist())
        grupo_opts = ["Todos"] + sorted(vendas["grupo"].dropna().unique().tolist())
        marca_sel  = col1.selectbox("Marca", marca_opts)
        grupo_sel  = col2.selectbox("Grupo", grupo_opts)

        df_v = vendas.copy()
        if marca_sel != "Todas":
            df_v = df_v[df_v["marca"] == marca_sel]
        if grupo_sel != "Todos":
            df_v = df_v[df_v["grupo"] == grupo_sel]

        if "quantidade" in df_v.columns:
            df_mensal = (
                df_v.groupby(["ano", "mes"])["quantidade"]
                .sum().reset_index()
                .sort_values(["ano", "mes"])
            )
            df_mensal["periodo"] = (df_mensal["ano"].astype(str) + "-"
                                    + df_mensal["mes"].astype(str).str.zfill(2))

            fig = px.bar(
                df_mensal, x="periodo", y="quantidade",
                color="ano", barmode="group",
                labels={"quantidade": "Unidades", "periodo": "Mês"},
                title="Vendas mensais",
            )
            st.plotly_chart(fig, use_container_width=True)

            # Projeção próximos 3 meses
            st.subheader(f"Projeção de demanda — {cenario}")
            ano_max = int(df_v["ano"].max())
            ano_ref = ano_max - 1
            df_ref  = df_v[df_v["ano"] == ano_ref]
            media_mes = df_ref.groupby("mes")["quantidade"].sum()

            mes_atual = pd.Timestamp.now().month
            proximos  = [(mes_atual + i - 1) % 12 + 1 for i in range(1, 4)]
            proj = pd.DataFrame({
                "mes": proximos,
                "demanda_historica (un)": [round(media_mes.get(m, 0), 0) for m in proximos],
            })
            proj["demanda_projetada (un)"] = (proj["demanda_historica (un)"] * fator_cenario).round(0)
            st.dataframe(proj, use_container_width=True)
        else:
            st.warning("Coluna de quantidade não encontrada.")
            st.write("Colunas disponíveis:", list(df_v.columns))

# ════════════════════════════════════════
# TAB 3 — SUGESTÃO DE COMPRAS
# ════════════════════════════════════════
with tab3:
    if not (file_estoque and file_vendas):
        st.info("Carregue Estoque e Vendas para gerar a sugestão de compras.")
    else:
        estoque = carregar_estoque(file_estoque)
        vendas  = carregar_vendas(file_vendas)

        st.subheader(f"Sugestão de compras — Cobertura alvo: {cobertura_alvo} dias | {cenario}")

        if "quantidade" not in vendas.columns:
            st.warning("Coluna de quantidade não encontrada em Vendas.")
        else:
            ano_max = int(vendas["ano"].max())
            ano_ref = ano_max - 1
            df_ref  = vendas[vendas["ano"] == ano_ref]

            # Giro mensal médio por marca + grupo (ano anterior)
            giro = (
                df_ref.groupby(["marca", "grupo"])["quantidade"]
                .sum() / 12 * fator_cenario
            ).reset_index()
            giro.columns = ["fabricante_nome", "grupo", "giro_mensal"]

            # Estoque atual por fabricante + grupo
            est_grp = (
                estoque.groupby(["fabricante_nome", "grupo"])
                .agg(
                    qtde_estoque=("qtde_estoque", "sum"),
                    custo_medio=("custo_medio_unit", "mean"),
                )
                .reset_index()
            )

            # Merge: começa pelo giro para não perder marcas sem estoque
            sugestao = giro.merge(est_grp, on=["fabricante_nome", "grupo"], how="left")
            sugestao["qtde_estoque"] = sugestao["qtde_estoque"].fillna(0)
            sugestao["custo_medio"]  = sugestao["custo_medio"].fillna(0)

            # Cobertura atual e necessidade
            sugestao["cobertura_dias"] = (
                sugestao["qtde_estoque"] /
                sugestao["giro_mensal"].replace(0, np.nan) * 30
            ).round(0)

            sugestao["qtde_sugerida"] = (
                (sugestao["giro_mensal"] * cobertura_alvo / 30) - sugestao["qtde_estoque"]
            ).clip(lower=0).round(0)

            sugestao["valor_sugerido"] = (
                sugestao["qtde_sugerida"] * sugestao["custo_medio"]
            ).round(0)

            def alerta(x):
                if pd.isna(x) or np.isinf(x): return "Sem histórico"
                if x < 15:  return "Crítico (<15d)"
                if x < 30:  return "Atenção (15–30d)"
                return "OK (≥30d)"

            sugestao["alerta"] = sugestao["cobertura_dias"].apply(alerta)

            st.dataframe(
                sugestao[[
                    "fabricante_nome", "grupo",
                    "qtde_estoque", "giro_mensal",
                    "cobertura_dias", "alerta",
                    "qtde_sugerida", "valor_sugerido",
                ]].sort_values(["fabricante_nome", "grupo"]),
                use_container_width=True,
            )

            st.download_button(
                "Baixar sugestão de compras (CSV)",
                sugestao.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                "sugestao_compras.csv", "text/csv",
            )

# ════════════════════════════════════════
# TAB 4 — CRÉDITO POR FORNECEDOR
# ════════════════════════════════════════
with tab4:
    st.subheader("Limites de crédito por fornecedor")

    df_cred = pd.DataFrame([
        {
            "Fornecedor":   nome,
            "Limite (R$)":  info["limite"],
            "Prazo (dias)": info["prazo_dias"],
            "Condição":     "Antecipado" if info["limite"] == 0 else f"{info['prazo_dias']} dias",
        }
        for nome, info in LIMITES_CREDITO.items()
    ])

    if file_estoque:
        estoque  = carregar_estoque(file_estoque)
        est_fab  = estoque.groupby("fabricante_nome")["custo_total"].sum().reset_index()
        est_fab.columns = ["Fornecedor", "Estoque Atual (R$)"]
        df_cred  = df_cred.merge(est_fab, on="Fornecedor", how="left")
        df_cred["Estoque Atual (R$)"] = df_cred["Estoque Atual (R$)"].fillna(0).round(0)
        df_cred["% do Limite"] = (
            df_cred["Estoque Atual (R$)"] /
            df_cred["Limite (R$)"].replace(0, np.nan) * 100
        ).round(1)

    st.dataframe(df_cred, use_container_width=True)

    fig = px.bar(
        df_cred[df_cred["Limite (R$)"] > 0],
        x="Fornecedor",
        y=["Limite (R$)", "Estoque Atual (R$)"],
        barmode="group",
        title="Limite de crédito x Estoque atual por fornecedor",
        labels={"value": "R$", "variable": ""},
    )
    st.plotly_chart(fig, use_container_width=True)
