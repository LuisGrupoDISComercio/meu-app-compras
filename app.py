import streamlit as st
import pandas as pd
import plotly.express as px
import re

st.set_page_config(page_title="Motor de Compras AC", layout="wide")
st.title("🌡️ Motor de Compras — Ar Condicionado")

# ─────────────────────────────────────────
# MAPA DE FABRICANTES (código → nome)
# Ajuste os códigos conforme seu ERP
# ─────────────────────────────────────────
MAPA_FABRICANTES = {
    2:  "LG",
    3:  "Samsung",
    7:  "Gree",
    8:  "Daikin",
    9:  "Midea",
    10: "Trane",
    11: "TCL",
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
# FUNÇÕES DE LIMPEZA
# ─────────────────────────────────────────

def inferir_grupo(desc):
    if pd.isna(desc):
        return "OUTROS"
    d = str(desc).upper()
    if "VRF" in d or "TVR" in d or "DVM" in d:
        return "VRF"
    if "MULTI" in d or "BI-SPLIT" in d or "BISPLIT" in d:
        return "MSP"
    if any(x in d for x in ["CASSETE", "PISO TETO", "TETO INV", "K7 INV", "K7 RED", "DUTO", " DT ", " PT "]):
        return "LCIN"
    if "AR COND" in d or "EVAP" in d or "COND." in d:
        return "INV"
    return "OUTROS"

def extrair_btu(desc):
    if pd.isna(desc):
        return None
    d = str(desc).upper()
    match = re.search(r"\b(7|9|09|12|18|24|30|36|48|55|60)\b", d)
    if match:
        val = int(match.group())
        return 9 if val in (7, 9) else val
    return None

def classificar_tipo_item(fabr):
    try:
        f = int(fabr)
    except:
        return "desconhecido"
    return {900: "acessorio", 995: "obra", 998: "danificado", 999: "semi"}.get(f, "giro")

@st.cache_data
def carregar_estoque(arquivo):
    df_raw = pd.read_excel(arquivo, header=None)
    # Encontra linha do cabeçalho
    for i, row in df_raw.iterrows():
        if "Fabr" in row.values:
            header_idx = i
            break
    df = df_raw.iloc[header_idx + 1:].copy()
    df.columns = df_raw.iloc[header_idx].tolist()
    df = df.dropna(how="all")
    df = df[df.iloc[:, 2] != "TOTAL"]
    df = df.rename(columns={
        "Fabr": "fabricante_codigo",
        "Produto": "produto_codigo",
        "Descrição": "descricao",
        "ABC": "abc_erp",
        "Cubagem (Un)": "cubagem_un",
        "Qtde": "qtde_estoque",
        "Custo Entrada Unitário Médio": "custo_medio_unit",
        "Custo Entrada Total": "custo_total",
    })
    for col in ["fabricante_codigo", "qtde_estoque", "custo_medio_unit", "custo_total"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["tipo_item"]       = df["fabricante_codigo"].apply(classificar_tipo_item)
    df["fabricante_nome"] = df["fabricante_codigo"].map(MAPA_FABRICANTES).fillna("Outros")
    df["grupo"]           = df["descricao"].apply(inferir_grupo)
    df["btu"]             = df["descricao"].apply(extrair_btu)
    return df[df["tipo_item"] == "giro"].copy()

@st.cache_data
def carregar_vendas(arquivo):
    df = pd.read_csv(arquivo, sep=";", encoding="utf-8", on_bad_lines="skip")
    df.columns = [c.strip() for c in df.columns]

    # Renomeia colunas conhecidas (ajuste se necessário)
    rename_map = {}
    for c in df.columns:
        cu = c.upper()
        if "EMISSAO" in cu or "EMISSÃO" in cu:
            rename_map[c] = "data_emissao"
        elif cu == "MARCA":
            rename_map[c] = "marca"
        elif cu == "GRUPO":
            rename_map[c] = "grupo"
        elif "BTU" in cu:
            rename_map[c] = "btu"
        elif cu in ("QTD", "QTDE", "QUANTIDADE"):
            rename_map[c] = "quantidade"
        elif "VL" in cu and "TOTAL" in cu:
            rename_map[c] = "valor_total"
        elif "PRODUTO" in cu or "COD" in cu:
            rename_map[c] = "produto_codigo"
    df = df.rename(columns=rename_map)

    df["data_emissao"] = pd.to_datetime(df["data_emissao"], dayfirst=True, errors="coerce")
    df["ano"] = df["data_emissao"].dt.year
    df["mes"] = df["data_emissao"].dt.month

    for col in ["quantidade", "valor_total"]:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False),
                errors="coerce"
            )
    return df

def calcular_abc(df, coluna_valor, coluna_id):
    df = df.copy()
    df = df[df[coluna_valor] > 0].copy()
    df = df.sort_values(coluna_valor, ascending=False)
    total = df[coluna_valor].sum()
    df["acum_%"] = df[coluna_valor].cumsum() / total * 100
    df["curva_abc"] = df["acum_%"].apply(
        lambda x: "A" if x <= 70 else ("B" if x <= 90 else "C")
    )
    return df

# ─────────────────────────────────────────
# SIDEBAR — UPLOAD
# ─────────────────────────────────────────
st.sidebar.header("📂 Carregar Dados")
arq_estoque = st.sidebar.file_uploader("Estoque (.xlsx)", type=["xlsx"])
arq_vendas  = st.sidebar.file_uploader("Vendas (.csv)",  type=["csv"])

cobertura_alvo = st.sidebar.slider(
    "Cobertura alvo (dias de estoque)", 30, 120, 60, step=10
)
cenario = st.sidebar.selectbox(
    "Cenário de demanda",
    ["Manutenção (0%)", "Alta (+10%)", "Alta (+20%)", "Redução (-10%)", "Redução (-20%)"]
)
fator_cenario = {
    "Manutenção (0%)": 1.0,
    "Alta (+10%)": 1.1,
    "Alta (+20%)": 1.2,
    "Redução (-10%)": 0.9,
    "Redução (-20%)": 0.8,
}[cenario]

# ─────────────────────────────────────────
# TABS PRINCIPAIS
# ─────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "📦 Estoque & ABC",
    "📈 Vendas & Demanda",
    "🛒 Sugestão de Compras",
    "💳 Crédito por Fornecedor"
])

# ════════════════════════════════════════
# TAB 1 — ESTOQUE & ABC
# ════════════════════════════════════════
with tab1:
    if arq_estoque:
        estoque = carregar_estoque(arq_estoque)

        st.subheader("Visão Geral do Estoque")
        col1, col2, col3 = st.columns(3)
        col1.metric("Total SKUs (giro)", f"{len(estoque):,}")
        col2.metric("Total Unidades",    f"{estoque['qtde_estoque'].sum():,.0f}")
        col3.metric("Custo Total (R$)",  f"R$ {estoque['custo_total'].sum():,.0f}")

        # Filtros
        fab_opts  = ["Todos"] + sorted(estoque["fabricante_nome"].dropna().unique().tolist())
        grp_opts  = ["Todos"] + sorted(estoque["grupo"].dropna().unique().tolist())
        fab_sel   = st.selectbox("Filtrar Fabricante", fab_opts)
        grp_sel   = st.selectbox("Filtrar Grupo",      grp_opts)

        df_est = estoque.copy()
        if fab_sel != "Todos":
            df_est = df_est[df_est["fabricante_nome"] == fab_sel]
        if grp_sel != "Todos":
            df_est = df_est[df_est["grupo"] == grp_sel]

        # Curva ABC por custo total
        df_abc = calcular_abc(df_est, "custo_total", "produto_codigo")

        st.subheader("Curva ABC — por Valor em Estoque")
        fig_abc = px.pie(
            df_abc.groupby("curva_abc")["custo_total"].sum().reset_index(),
            names="curva_abc", values="custo_total",
            color="curva_abc",
            color_discrete_map={"A": "#2ecc71", "B": "#f39c12", "C": "#e74c3c"},
            title="Distribuição ABC (% do valor)"
        )
        st.plotly_chart(fig_abc, use_container_width=True)

        st.subheader("Tabela de Estoque com ABC")
        cols_show = ["fabricante_nome", "produto_codigo", "descricao",
                     "grupo", "btu", "abc_erp", "curva_abc",
                     "qtde_estoque", "custo_medio_unit", "custo_total"]
        cols_show = [c for c in cols_show if c in df_abc.columns]
        st.dataframe(df_abc[cols_show].reset_index(drop=True), use_container_width=True)

        csv_estoque = df_abc[cols_show].to_csv(index=False, sep=";", decimal=",").encode("utf-8")
        st.download_button("⬇️ Baixar Estoque com ABC", csv_estoque,
                           "estoque_abc.csv", "text/csv")
    else:
        st.info("Faça upload do arquivo de Estoque no menu lateral.")

# ════════════════════════════════════════
# TAB 2 — VENDAS & DEMANDA
# ════════════════════════════════════════
with tab2:
    if arq_vendas:
        vendas = carregar_vendas(arq_vendas)
        st.subheader("Histórico de Vendas")

        anos = sorted(vendas["ano"].dropna().unique().tolist())
        col1, col2 = st.columns(2)
        marca_sel = col1.selectbox("Marca", ["Todas"] + sorted(vendas["marca"].dropna().unique().tolist()))
        grupo_sel = col2.selectbox("Grupo", ["Todos"] + sorted(vendas["grupo"].dropna().unique().tolist()))

        df_v = vendas.copy()
        if marca_sel != "Todas":
            df_v = df_v[df_v["marca"] == marca_sel]
        if grupo_sel != "Todos":
            df_v = df_v[df_v["grupo"] == grupo_sel]

        if "quantidade" in df_v.columns:
            df_mensal = (df_v.groupby(["ano", "mes"])["quantidade"]
                         .sum().reset_index()
                         .sort_values(["ano", "mes"]))
            df_mensal["periodo"] = df_mensal["ano"].astype(str) + "-" + df_mensal["mes"].astype(str).str.zfill(2)

            fig_v = px.bar(df_mensal, x="periodo", y="quantidade",
                           color="ano", barmode="group",
                           title="Vendas mensais por período",
                           labels={"quantidade": "Unidades", "periodo": "Mês"})
            st.plotly_chart(fig_v, use_container_width=True)

            # Projeção próximos 3 meses
            st.subheader(f"Projeção de Demanda — Cenário: {cenario}")
            ano_ref = vendas["ano"].max() - 1
            df_ref  = df_v[df_v["ano"] == ano_ref]
            media_mensal = df_ref.groupby("mes")["quantidade"].sum() / max(1, df_ref["ano"].nunique())

            mes_atual = pd.Timestamp.now().month
            proximos  = [(mes_atual + i - 1) % 12 + 1 for i in range(1, 4)]
            proj = pd.DataFrame({
                "mes": proximos,
                "demanda_historica": [media_mensal.get(m, 0) for m in proximos],
            })
            proj["demanda_projetada"] = (proj["demanda_historica"] * fator_cenario).round(0)
            st.dataframe(proj, use_container_width=True)
        else:
            st.warning("Coluna de quantidade não encontrada. Verifique o nome da coluna no CSV.")
            st.write("Colunas detectadas:", list(df_v.columns))
    else:
        st.info("Faça upload do arquivo de Vendas no menu lateral.")

# ════════════════════════════════════════
# TAB 3 — SUGESTÃO DE COMPRAS
# ════════════════════════════════════════
with tab3:
    if arq_estoque and arq_vendas:
        estoque = carregar_estoque(arq_estoque)
        vendas  = carregar_vendas(arq_vendas)

        st.subheader(f"Sugestão de Compras — Cobertura alvo: {cobertura_alvo} dias | Cenário: {cenario}")

        if "quantidade" in vendas.columns:
            ano_ref   = vendas["ano"].max() - 1
            df_ref    = vendas[vendas["ano"] == ano_ref]
            giro_mensal = (df_ref.groupby(["marca", "grupo"])["quantidade"]
                           .sum() / 12 * fator_cenario).reset_index()
            giro_mensal.columns = ["fabricante_nome", "grupo", "giro_mensal"]
            giro_mensal["fabricante_nome"] = giro_mensal["fabricante_nome"].str.title()

            est_grp = (estoque.groupby(["fabricante_nome", "grupo"])
                       .agg(qtde_estoque=("qtde_estoque", "sum"),
                            custo_medio=("custo_medio_unit", "mean"))
                       .reset_index())

            sugestao = est_grp.merge(giro_mensal, on=["fabricante_nome", "grupo"], how="left")
            sugestao["giro_mensal"]    = sugestao["giro_mensal"].fillna(0)
            sugestao["cobertura_dias"] = (sugestao["qtde_estoque"] /
                                          sugestao["giro_mensal"].replace(0, None) * 30).round(0)
            sugestao["qtde_sugerida"]  = (
                (sugestao["giro_mensal"] * cobertura_alvo / 30) - sugestao["qtde_estoque"]
            ).clip(lower=0).round(0)
            sugestao["valor_sugerido"] = (sugestao["qtde_sugerida"] * sugestao["custo_medio"]).round(0)

            sugestao["alerta"] = sugestao["cobertura_dias"].apply(
                lambda x: "🔴 Crítico" if pd.isna(x) or x < 15
                else ("🟡 Atenção" if x < 30 else "🟢 OK")
            )

            st.dataframe(sugestao[[
                "fabricante_nome", "grupo", "qtde_estoque",
                "giro_mensal", "cobertura_dias", "alerta",
                "qtde_sugerida", "valor_sugerido"
            ]].sort_values("cobertura_dias"), use_container_width=True)

            csv_sug = sugestao.to_csv(index=False, sep=";", decimal=",").encode("utf-8")
            st.download_button("⬇️ Baixar Sugestão de Compras", csv_sug,
                               "sugestao_compras.csv", "text/csv")
        else:
            st.warning("Dados de quantidade não encontrados nas vendas.")
    else:
        st.info("Carregue Estoque e Vendas para ver a sugestão de compras.")

# ════════════════════════════════════════
# TAB 4 — CRÉDITO POR FORNECEDOR
# ════════════════════════════════════════
with tab4:
    st.subheader("Posição de Crédito por Fornecedor")
    df_cred = pd.DataFrame([
        {"Fornecedor": k,
         "Limite (R$)": v["limite"],
         "Prazo (dias)": v["prazo_dias"],
         "Pagamento": "Antecipado" if v["limite"] == 0 else f"{v['prazo_dias']} dias"}
        for k, v in LIMITES_CREDITO.items()
    ])

    if arq_estoque:
        estoque = carregar_estoque(arq_estoque)
        est_fab = estoque.groupby("fabricante_nome")["custo_total"].sum().reset_index()
        est_fab.columns = ["Fornecedor", "Estoque Atual (R$)"]
        df_cred = df_cred.merge(est_fab, on="Fornecedor", how="left").fillna(0)
        df_cred["Estoque Atual (R$)"] = df_cred["Estoque Atual (R$)"].round(0)
        df_cred["% do Limite"] = (df_cred["Estoque Atual (R$)"] /
                                   df_cred["Limite (R$)"].replace(0, None) * 100).round(1)

    st.dataframe(df_cred, use_container_width=True)

    fig_cred = px.bar(
        df_cred[df_cred["Limite (R$)"] > 0],
        x="Fornecedor", y=["Limite (R$)", "Estoque Atual (R$)"],
        barmode="group",
        title="Limite de Crédito vs Estoque Atual por Fornecedor",
        labels={"value": "R$", "variable": ""}
    )
    st.plotly_chart(fig_cred, use_container_width=True)