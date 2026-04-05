import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import re

st.set_page_config(page_title="Motor de Compras AC", layout="wide")
st.title("Motor de Compras — Ar Condicionado")

# ─────────────────────────────────────────
# MAPA DE FABRICANTES (código → nome)
# Ajuste se algum código estiver diferente no seu ERP
# ─────────────────────────────────────────
MAPA_FABRICANTES = {
    2:  "LG",
    7:  "Gree",          # ajuste se aparecer código real da Gree no seu estoque
    8:  "Daikin",        # idem
    9:  "Midea",         # idem (SPRINGER MIDEA)
    10: "Trane",
    11: "TCL",
    3:  "Samsung",       # caso apareça no estoque
}

LIMITES_CREDITO = {
    "LG":     {"limite": 3_500_000,  "prazo_dias": 30},
    "TCL":    {"limite": 19_000_000, "prazo_dias": 90},
    "Midea":  {"limite": 28_000_000, "prazo_dias": 90},
    "Gree":   {"limite": 45_000_000, "prazo_dias": 120},
    "Daikin": {"limite": 45_000_000, "prazo_dias": 150},  # simplificado (primeira faixa)
    "Samsung":{"limite": 0,          "prazo_dias": 0},
    "Trane":  {"limite": 0,          "prazo_dias": 0},
}

# ─────────────────────────────────────────
# FUNÇÕES DE LIMPEZA / DERIVAÇÃO
# ─────────────────────────────────────────

def inferir_grupo(desc: str) -> str:
    if pd.isna(desc):
        return "OUTROS"
    d = str(desc).upper()
    if "VRF" in d or "TVR" in d or "DVM" in d:
        return "VRF"
    if "MULTI" in d or "BI-SPLIT" in d or "BISPLIT" in d:
        return "MSP"
    if any(x in d for x in ["CASSETE", "PISO TETO", "TETO INV", "K7 ", "K-7", "DUTO", " DT ", " PT "]):
        return "LCIN"
    if "AR COND" in d or "AR COND." in d or "EVAP." in d or "COND." in d:
        return "INV"
    return "OUTROS"

def extrair_btu_desc(desc: str):
    if pd.isna(desc):
        return np.nan
    d = str(desc).upper()
    # tenta pegar padrões de BTU típicos
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
    if f == 900:
        return "acessorio_servico"
    if f == 995:
        return "indicacao_obra"
    if f == 998:
        return "danificado"
    if f == 999:
        return "semi"
    return "giro"

def calcular_abc(df, coluna_valor, coluna_id):
    df = df.copy()
    df = df[df[coluna_valor] > 0].copy()
    df = df.sort_values(coluna_valor, ascending=False)
    total = df[coluna_valor].sum()
    if total <= 0:
        df["acum_%"] = 0
        df["curva_abc"] = "C"
        return df
    df["acum_%"] = df[coluna_valor].cumsum() / total * 100
    df["curva_abc"] = df["acum_%"].apply(
        lambda x: "A" if x <= 70 else ("B" if x <= 90 else "C")
    )
    return df

# ─────────────────────────────────────────
# LEITURA DOS ARQUIVOS
# ─────────────────────────────────────────

@st.cache_data
def carregar_estoque(file):
    # lê sem header, porque o relatório traz linhas de texto antes
    df_raw = pd.read_excel(file, header=None)

    # encontra a linha do cabeçalho onde aparece "Fabr"
    header_idx = None
    for i, row in df_raw.iterrows():
        if "Fabr" in row.values:
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("Cabeçalho 'Fabr' não encontrado no arquivo de estoque.")

    df = df_raw.iloc[header_idx + 1:].copy()
    df.columns = df_raw.iloc[header_idx].tolist()

    # remove linhas vazias e linha de TOTAL
    df = df.dropna(how="all")
    if "Descrição" in df.columns:
        df = df[df["Descrição"] != "TOTAL"]

    # renomeia colunas principais
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

    # tipos numéricos
    for col in ["fabricante_codigo", "qtde_estoque", "custo_medio_unit", "custo_total"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # tipo do item
    df["tipo_item"] = df["fabricante_codigo"].apply(classificar_tipo_item)

    # nome do fabricante
    df["fabricante_nome"] = df["fabricante_codigo"].map(MAPA_FABRICANTES).fillna("Outros")

    # grupo e BTU
    df["grupo"] = df["descricao"].apply(inferir_grupo)
    df["btu"]   = df["descricao"].apply(extrair_btu_desc)

    # apenas itens de giro para as análises principais
    df_giro = df[df["tipo_item"] == "giro"].copy()

    return df_giro

@st.cache_data
def carregar_vendas(file):
    df = pd.read_csv(file, sep=";", encoding="utf-8", on_bad_lines="skip")
    df.columns = [c.strip() for c in df.columns]

    # mapeamento direto do cabeçalho real
    rename_map = {
        "Emissao NF": "data_emissao",
        "Marca": "marca",
        "Grupo": "grupo",
        "BTU": "btu",
        "Ciclo": "ciclo",
        "Produto": "produto_codigo",
        "Descricao": "descricao",
        "Qtde": "quantidade",
        "VL Total": "valor_total",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    # datas
    df["data_emissao"] = pd.to_datetime(df["data_emissao"], dayfirst=True, errors="coerce")
    df["ano"] = df["data_emissao"].dt.year
    df["mes"] = df["data_emissao"].dt.month

    # quantidade e valor total
    if "quantidade" in df.columns:
        df["quantidade"] = pd.to_numeric(
            df["quantidade"].astype(str)
            .str.replace(".", "", regex=False)
            .str.replace(",", ".", regex=False),
            errors="coerce"
        )
    if "valor_total" in df.columns:
        df["valor_total"] = pd.to_numeric(
            df["valor_total"].astype(str)
            .str.replace(".", "", regex=False)
            .str.replace(",", ".", regex=False),
            errors="coerce"
        )

    # se BTU não vier preenchido, tenta derivar da descrição
    if "btu" in df.columns:
        df["btu"] = pd.to_numeric(df["btu"], errors="coerce")
        mask_vazio = df["btu"].isna()
        if "descricao" in df.columns:
            df.loc[mask_vazio, "btu"] = df.loc[mask_vazio, "descricao"].apply(extrair_btu_desc)
    else:
        if "descricao" in df.columns:
            df["btu"] = df["descricao"].apply(extrair_btu_desc)

    return df

# ─────────────────────────────────────────
# SIDEBAR — UPLOAD + PARÂMETROS
# ─────────────────────────────────────────

st.sidebar.header("Carregar dados")
file_estoque = st.sidebar.file_uploader("Estoque (.xlsx)", type=["xlsx"])
file_vendas  = st.sidebar.file_uploader("Vendas (.csv)", type=["csv"])

cobertura_alvo = st.sidebar.slider(
    "Cobertura alvo (dias de estoque)", min_value=30, max_value=120, value=60, step=10
)
cenario = st.sidebar.selectbox(
    "Cenário de demanda",
    ["Manutenção (0%)", "Alta (+10%)", "Alta (+20%)", "Redução (-10%)", "Redução (-20%)"]
)
fator_cenario = {
    "Manutenção (0%)": 1.0,
    "Alta (+10%)": 1.10,
    "Alta (+20%)": 1.20,
    "Redução (-10%)": 0.90,
    "Redução (-20%)": 0.80,
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

        st.subheader("Visão geral do Estoque (itens de giro)")
        c1, c2, c3 = st.columns(3)
        c1.metric("SKUs de giro", f"{estoque['produto_codigo'].nunique():,}")
        c2.metric("Unidades totais", f"{estoque['qtde_estoque'].sum():,.0f}")
        c3.metric("Custo total (R$)", f"R$ {estoque['custo_total'].sum():,.0f}")

        fab_opts = ["Todos"] + sorted(estoque["fabricante_nome"].dropna().unique().tolist())
        grp_opts = ["Todos"] + sorted(estoque["grupo"].dropna().unique().tolist())
        fab_sel  = st.selectbox("Filtrar fabricante", fab_opts)
        grp_sel  = st.selectbox("Filtrar grupo",      grp_opts)

        df_est = estoque.copy()
        if fab_sel != "Todos":
            df_est = df_est[df_est["fabricante_nome"] == fab_sel]
        if grp_sel != "Todos":
            df_est = df_est[df_est["grupo"] == grp_sel]

        df_abc = calcular_abc(df_est, "custo_total", "produto_codigo")

        st.subheader("Curva ABC por valor em estoque")
        df_abc_resumo = df_abc.groupby("curva_abc")["custo_total"].sum().reset_index()
        if not df_abc_resumo.empty:
            fig_abc = px.pie(
                df_abc_resumo,
                names="curva_abc",
                values="custo_total",
                title="Participação por classe ABC (valor em estoque)",
                color="curva_abc",
                color_discrete_map={"A": "#2ecc71", "B": "#f1c40f", "C": "#e74c3c"},
            )
            st.plotly_chart(fig_abc, use_container_width=True)

        st.subheader("Tabela de estoque com ABC calculado")
        cols_show = [
            "fabricante_nome", "produto_codigo", "descricao",
            "grupo", "btu", "abc_erp", "curva_abc",
            "qtde_estoque", "custo_medio_unit", "custo_total"
        ]
        cols_show = [c for c in cols_show if c in df_abc.columns]
        st.dataframe(df_abc[cols_show].reset_index(drop=True), use_container_width=True)

        csv_estoque = df_abc[cols_show].to_csv(index=False, sep=";", decimal=",").encode("utf-8")
        st.download_button(
            "Baixar estoque com ABC (CSV)",
            csv_estoque,
            "estoque_abc.csv",
            "text/csv",
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
                .sum()
                .reset_index()
                .sort_values(["ano", "mes"])
            )
            df_mensal["periodo"] = df_mensal["ano"].astype(str) + "-" + df_mensal["mes"].astype(str).str.zfill(2)

            fig = px.bar(
                df_mensal,
                x="periodo", y="quantidade",
                color="ano", barmode="group",
                labels={"quantidade": "Unidades", "periodo": "Mês"},
                title="Vendas mensais (todas as marcas/grupos filtrados)",
            )
            st.plotly_chart(fig, use_container_width=True)

            st.subheader(f"Projeção de demanda — cenário: {cenario}")
            ano_max = df_v["ano"].max()
            ano_ref = ano_max - 1  # mesmo período do ano anterior
            df_ref = df_v[df_v["ano"] == ano_ref]

            media_mensal = df_ref.groupby("mes")["quantidade"].sum()
            meses_prox = [1, 2, 3]  # você pode ajustar para usar o mês atual se quiser

            proj = pd.DataFrame({
                "mes": meses_prox,
                "demanda_historica": [media_mensal.get(m, 0) for m in meses_prox],
            })
            proj["demanda_projetada"] = (proj["demanda_historica"] * fator_cenario).round(0)
            st.dataframe(proj, use_container_width=True)
        else:
            st.warning("Coluna de quantidade não encontrada em Vendas.")
            st.write("Colunas disponíveis:", list(df_v.columns))

# ════════════════════════════════════════
# TAB 3 — SUGESTÃO DE COMPRAS
# ════════════════════════════════════════
with tab3:
    if not (file_estoque and file_vendas):
        st.info("Carregue Estoque e Vendas para gerar sugestão de compras.")
    else:
        estoque = carregar_estoque(file_estoque)
        vendas  = carregar_vendas(file_vendas)

        st.subheader(f"Sugestão de compras — Cobertura alvo: {cobertura_alvo} dias | Cenário: {cenario}")

        if "quantidade" not in vendas.columns:
            st.warning("Não foi possível encontrar a coluna de quantidade em Vendas.")
        else:
            # usa ano anterior como base de giro
            ano_max = vendas["ano"].max()
            ano_ref = ano_max - 1
            df_ref  = vendas[vendas["ano"] == ano_ref]

            giro_mensal = (
                df_ref.groupby(["marca", "grupo"])["quantidade"].sum() / 12
            ).reset_index()
            giro_mensal["giro_mensal"] *= fator_cenario
            giro_mensal.rename(columns={"marca": "fabricante_nome"}, inplace=True)

            # normaliza nome (ex.: SPRINGER MIDEA → Midea)
            giro_mensal["fabricante_nome"] = giro_mensal["fabricante_nome"].str.strip().str.title()
            giro_mensal["fabricante_nome"] = giro_mensal["fabricante_nome"].replace({
                "Springer Midea": "Midea",
            })

            est_grp = (
                estoque.groupby(["fabricante_nome", "grupo"])
                .agg(qtde_estoque=("qtde_estoque", "sum"),
                     custo_medio=("custo_medio_unit", "mean"))
                .reset_index()
            )

            sugestao = est_grp.merge(giro_mensal, on=["fabricante_nome", "grupo"], how="left")
            sugestao["giro_mensal"] = sugestao["giro_mensal"].fillna(0)

            # cobertura atual
            sugestao["cobertura_dias"] = (
                sugestao["qtde_estoque"] /
                sugestao["giro_mensal"].replace(0, np.nan) * 30
            )
            sugestao["cobertura_dias"] = sugestao["cobertura_dias"].round(0)

            # necessidade para atingir cobertura alvo
            sugestao["qtde_alvo"] = (sugestao["giro_mensal"] * cobertura_alvo / 30)
            sugestao["qtde_sugerida"] = (sugestao["qtde_alvo"] - sugestao["qtde_estoque"]).clip(lower=0).round(0)
            sugestao["valor_sugerido"] = (sugestao["qtde_sugerida"] * sugestao["custo_medio"]).round(0)

            def alerta_cobertura(x):
                if pd.isna(x) or x == np.inf:
                    return "Sem histórico"
                if x < 15:
                    return "Crítico (<15d)"
                if x < 30:
                    return "Atenção (15–30d)"
                return "OK (>=30d)"

            sugestao["alerta"] = sugestao["cobertura_dias"].apply(alerta_cobertura)

            st.dataframe(
                sugestao[[
                    "fabricante_nome", "grupo",
                    "qtde_estoque", "giro_mensal",
                    "cobertura_dias", "alerta",
                    "qtde_sugerida", "valor_sugerido",
                ]].sort_values(["fabricante_nome", "grupo"]),
                use_container_width=True,
            )

            csv_sug = sugestao.to_csv(index=False, sep=";", decimal=",").encode("utf-8")
            st.download_button(
                "Baixar sugestão de compras (CSV)",
                csv_sug,
                "sugestao_compras.csv",
                "text/csv",
            )

# ════════════════════════════════════════
# TAB 4 — CRÉDITO POR FORNECEDOR
# ════════════════════════════════════════
with tab4:
    st.subheader("Limites de crédito por fornecedor")

    df_cred = pd.DataFrame([
        {
            "Fornecedor": nome,
            "Limite (R$)": info["limite"],
            "Prazo (dias)": info["prazo_dias"],
            "Condição": "Antecipado" if info["limite"] == 0 else f"{info['prazo_dias']} dias",
        }
        for nome, info in LIMITES_CREDITO.items()
    ])

    if file_estoque:
        estoque = carregar_estoque(file_estoque)
        est_fab = estoque.groupby("fabricante_nome")["custo_total"].sum().reset_index()
        est_fab.columns = ["Fornecedor", "Estoque Atual (R$)"]
        df_cred = df_cred.merge(est_fab, on="Fornecedor", how="left")
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
        title="Limite de crédito x Estoque atual",
        labels={"value": "R$", "variable": ""},
    )
    st.plotly_chart(fig, use_container_width=True)
