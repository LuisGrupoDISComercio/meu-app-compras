import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import re
from io import StringIO, BytesIO

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
    "LG":             {"limite": 3_500_000,  "prazo": 30},
    "Gree":           {"limite": 45_000_000, "prazo": 120},
    "TCL":            {"limite": 19_000_000, "prazo": 90},
    "Daikin":         {"limite": 45_000_000, "prazo": 150},
    "Springer Midea": {"limite": 28_000_000, "prazo": 90},
    "Samsung":        {"limite": 0,          "prazo": 0},
    "Trane":          {"limite": 0,          "prazo": 0},
    "Agratto":        {"limite": 0,          "prazo": 0},
}

MESES_PT = {
    1:"Jan", 2:"Fev", 3:"Mar", 4:"Abr",
    5:"Mai", 6:"Jun", 7:"Jul", 8:"Ago",
    9:"Set", 10:"Out", 11:"Nov", 12:"Dez"
}

FABRICANTES_ESTRATEGICOS = list(CONDICOES.keys())

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def decode_bytes(raw: bytes) -> str:
    for enc in ["utf-8-sig", "latin-1", "cp1252", "iso-8859-1", "utf-8"]:
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("latin-1", errors="replace")


def normaliza_marca(valor: str) -> str:
    if not isinstance(valor, str):
        return "Outros"
    v = valor.strip().upper()
    for chave, nome in NORMALIZA_MARCA_VENDAS.items():
        if v == chave or v.startswith(chave):
            return nome
    return valor.strip().title()


# ─────────────────────────────────────────────
# CARGA DE DADOS
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def carregar_estoque(file) -> pd.DataFrame:
    xls = pd.read_excel(file, sheet_name=0, header=None)

    header_row = None
    for i, row in xls.iterrows():
        vals = [str(v).strip().lower() for v in row.values if pd.notna(v)]
        if any("fabr" in v for v in vals) and any("produto" in v for v in vals):
            header_row = i
            break

    if header_row is None:
        st.error("Cabeçalho não encontrado no arquivo de estoque.")
        st.stop()

    df = pd.read_excel(file, sheet_name=0, header=header_row)
    df.columns = [str(c).strip() for c in df.columns]

    # Mapeia colunas para nomes internos
    col_map = {}
    for c in df.columns:
        cl = c.lower()
        if "fabr" in cl and "fabricante" not in col_map.values():
            col_map[c] = "fabricante"
        elif "produto" in cl and "sku" not in col_map.values():
            col_map[c] = "sku"
        elif "descri" in cl and "descricao" not in col_map.values():
            col_map[c] = "descricao"
        elif cl == "abc" and "abc" not in col_map.values():
            col_map[c] = "abc"
        elif "qtde" in cl and "qtde_estoque" not in col_map.values():
            col_map[c] = "qtde_estoque"
        elif "unit" in cl and "custo_unitario" not in col_map.values():
            col_map[c] = "custo_unitario"
        elif "total" in cl and "custo_total" not in col_map.values():
            col_map[c] = "custo_total"

    df = df.rename(columns=col_map)

    cols_needed = ["fabricante", "sku", "descricao", "qtde_estoque", "custo_unitario", "custo_total"]
    for c in cols_needed:
        if c not in df.columns:
            df[c] = np.nan

    df = df[cols_needed + ["abc"] if "abc" in df.columns else cols_needed].copy()

    # Numéricos
    for c in ["fabricante", "sku", "qtde_estoque", "custo_unitario", "custo_total"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Remove linhas sem SKU ou fabricante
    df = df.dropna(subset=["sku", "fabricante"])

    # Exclui fabricantes ignorados
    df = df[~df["fabricante"].isin(FABRICANTES_IGNORAR)]

    # Mapeia nome do fabricante
    df["fabricante_int"] = df["fabricante"].astype(int)
    df["fabricante_nome"] = df["fabricante_int"].map(MAPA_FABRICANTES_ESTOQUE).fillna("Outros")

    # Flag custo zero
    df["flag_custo_zero"] = (df["custo_unitario"].fillna(0) == 0).astype(int)

    df["sku"] = df["sku"].astype(int).astype(str).str.zfill(6)
    df["descricao"] = df["descricao"].astype(str).str.strip()
    df["qtde_estoque"] = df["qtde_estoque"].fillna(0)
    df["custo_unitario"] = df["custo_unitario"].fillna(0)
    df["custo_total"] = df["custo_total"].fillna(0)

    return df.reset_index(drop=True)


@st.cache_data(show_spinner=False)
def carregar_vendas(file) -> pd.DataFrame:
    # ── CORREÇÃO DO UNICODE: lê os bytes brutos e detecta encoding ──
    raw = file.read()
    texto = decode_bytes(raw)
    # ────────────────────────────────────────────────────────────────

    df = pd.read_csv(
        StringIO(texto),
        sep=";",
        dtype=str,
    )

    df.columns = [str(c).strip() for c in df.columns]

    # Mapeia colunas
    col_map = {}
    for c in df.columns:
        cl = c.lower()
        if "emiss" in cl:
            col_map[c] = "data_emissao"
        elif "marca" in cl:
            col_map[c] = "marca"
        elif "grupo" in cl:
            col_map[c] = "grupo"
        elif "btu" in cl:
            col_map[c] = "btu"
        elif "ciclo" in cl:
            col_map[c] = "ciclo"
        elif "produto" in cl:
            col_map[c] = "sku"
        elif "descri" in cl:
            col_map[c] = "descricao"
        elif "qtde" in cl or "quant" in cl:
            col_map[c] = "quantidade"
        elif "vl" in cl or "valor" in cl or "total" in cl:
            col_map[c] = "valor_total"

    df = df.rename(columns=col_map)

    # Garante colunas mínimas
    for c in ["data_emissao", "marca", "sku", "quantidade", "valor_total"]:
        if c not in df.columns:
            df[c] = np.nan

    df["data_emissao"] = pd.to_datetime(df["data_emissao"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["data_emissao"])

    df["ano"]     = df["data_emissao"].dt.year
    df["mes"]     = df["data_emissao"].dt.month
    df["ano_mes"] = df["data_emissao"].dt.to_period("M").astype(str)

    df["quantidade"]  = pd.to_numeric(df["quantidade"],  errors="coerce").fillna(0)
    df["valor_total"] = pd.to_numeric(df["valor_total"], errors="coerce").fillna(0)

    # Normaliza marca — garante que é string antes de qualquer operação
    df["marca"] = df["marca"].apply(
        lambda x: normaliza_marca(str(x)) if pd.notna(x) else "Outros"
    )

    df["sku"] = df["sku"].apply(
        lambda x: str(x).strip().zfill(6) if pd.notna(x) else ""
    )

    return df.reset_index(drop=True)


# ─────────────────────────────────────────────
# APP PRINCIPAL
# ─────────────────────────────────────────────
def main():
    st.title("❄️ Motor de Compras — Ar Condicionado")

    with st.sidebar:
        st.header("📁 Arquivos")
        file_estoque = st.file_uploader("Estoque (.xlsx)", type=["xlsx", "xls"])
        file_vendas  = st.file_uploader("Vendas (.csv)",   type=["csv"])

    if not file_estoque or not file_vendas:
        st.info("Faça upload do Estoque (.xlsx) e das Vendas (.csv) para começar.")
        return

    with st.spinner("Carregando dados..."):
        estoque_df = carregar_estoque(file_estoque)
        df_vendas  = carregar_vendas(file_vendas)

    # ── TABS ──
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📦 Estoque & ABC",
        "📈 Vendas & Demanda",
        "🔄 Cobertura",
        "🛒 Sugestão de Compras",
        "🏭 Fornecedores",
    ])

    # ─────────────────────────────────────────
    # TAB 1 – ESTOQUE & ABC
    # ─────────────────────────────────────────
    with tab1:
        st.subheader("Visão geral do estoque")

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("SKUs",            f"{estoque_df['sku'].nunique():,}")
        k2.metric("Unidades",        f"{estoque_df['qtde_estoque'].sum():,.0f}")
        k3.metric("Custo Total",     f"R$ {estoque_df['custo_total'].sum():,.0f}")
        k4.metric("SKUs custo zero", f"{(estoque_df['flag_custo_zero']==1).sum()}")

        # Alerta custo zero
        df_zero = estoque_df[estoque_df["flag_custo_zero"] == 1]
        if not df_zero.empty:
            with st.expander(f"⚠️ {len(df_zero)} SKU(s) com custo = 0 — clique para ver"):
                st.dataframe(
                    df_zero[["fabricante_nome", "sku", "descricao", "qtde_estoque"]],
                    use_container_width=True
                )

        # Filtros
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            fab_sel = st.multiselect(
                "Fabricante",
                sorted(estoque_df["fabricante_nome"].unique()),
                default=sorted(estoque_df["fabricante_nome"].unique()),
            )
        with col_f2:
            abc_vals = sorted(estoque_df["abc"].dropna().unique()) if "abc" in estoque_df.columns else []
            abc_sel  = st.multiselect("ABC", abc_vals, default=abc_vals)
        with col_f3:
            custo_fil = st.selectbox("Custo", ["Todos", "Somente custo zero", "Somente com custo"])

        df_est = estoque_df[estoque_df["fabricante_nome"].isin(fab_sel)].copy()
        if abc_sel and "abc" in df_est.columns:
            df_est = df_est[df_est["abc"].isin(abc_sel)]
        if custo_fil == "Somente custo zero":
            df_est = df_est[df_est["flag_custo_zero"] == 1]
        elif custo_fil == "Somente com custo":
            df_est = df_est[df_est["flag_custo_zero"] == 0]

        # Destaque visual custo zero
        def highlight_zero(row):
            if row.get("flag_custo_zero", 0) == 1:
                return ["background-color: #ffe0e0"] * len(row)
            return [""] * len(row)

        cols_show = [c for c in ["fabricante_nome", "sku", "descricao", "abc",
                                  "qtde_estoque", "custo_unitario", "custo_total",
                                  "flag_custo_zero"] if c in df_est.columns]

        st.dataframe(
            df_est[cols_show].style.apply(highlight_zero, axis=1),
            use_container_width=True,
            height=450,
        )

        # Gráfico por fabricante
        resumo_fab = (
            df_est.groupby("fabricante_nome")
            .agg(Unidades=("qtde_estoque","sum"), Custo=("custo_total","sum"))
            .reset_index()
            .sort_values("Custo", ascending=False)
        )
        fig_fab = px.bar(
            resumo_fab, x="fabricante_nome", y="Custo",
            title="Custo total em estoque por fabricante",
            labels={"fabricante_nome":"Fabricante","Custo":"R$"}
        )
        st.plotly_chart(fig_fab, use_container_width=True)

    # ─────────────────────────────────────────
    # TAB 2 – VENDAS & DEMANDA
    # ─────────────────────────────────────────
    with tab2:
        st.subheader("Vendas por período e marca")

        anos_disp = sorted(df_vendas["ano"].dropna().unique().astype(int), reverse=True)
        meses_disp = sorted(df_vendas["mes"].dropna().unique().astype(int))

        col_a, col_m = st.columns(2)
        with col_a:
            ano_sel = st.selectbox("Ano", anos_disp, index=0)
        with col_m:
            meses_labels = [MESES_PT[m] for m in meses_disp]
            mes_label_sel = st.selectbox("Mês (ou Todos)", ["Todos"] + meses_labels)

        df_v = df_vendas[df_vendas["ano"] == ano_sel].copy()
        if mes_label_sel != "Todos":
            mes_num = [k for k, v in MESES_PT.items() if v == mes_label_sel][0]
            df_v = df_v[df_v["mes"] == mes_num]

        # KPIs
        k1, k2, k3 = st.columns(3)
        k1.metric("Faturamento",   f"R$ {df_v['valor_total'].sum():,.0f}")
        k2.metric("Unidades",      f"{df_v['quantidade'].sum():,.0f}")
        k3.metric("NFs / linhas",  f"{len(df_v):,}")

        # Pivot por marca (igual ao Excel)
        pivot_marca = (
            df_v.groupby("marca")["valor_total"]
            .sum()
            .reset_index()
            .rename(columns={"marca":"Marca","valor_total":"VL Total (R$)"})
            .sort_values("VL Total (R$)", ascending=False)
        )
        pivot_marca["VL Total (R$)"] = pivot_marca["VL Total (R$)"].map(
            lambda x: f"R$ {x:,.2f}"
        )
        st.dataframe(pivot_marca, use_container_width=True, hide_index=True)

        # Evolução mensal
        st.divider()
        st.markdown("#### Evolução mensal — todas as marcas")
        evol = (
            df_vendas[df_vendas["ano"] == ano_sel]
            .groupby(["mes","marca"])["valor_total"]
            .sum()
            .reset_index()
        )
        evol["mes_label"] = evol["mes"].map(MESES_PT)
        fig_evol = px.bar(
            evol, x="mes_label", y="valor_total", color="marca",
            title=f"Faturamento mensal {ano_sel} por marca",
            labels={"mes_label":"Mês","valor_total":"R$","marca":"Marca"}
        )
        st.plotly_chart(fig_evol, use_container_width=True)

    # ─────────────────────────────────────────
    # TAB 3 – COBERTURA
    # ─────────────────────────────────────────
    with tab3:
        st.subheader("Cobertura de estoque (meses)")

        meses_ref = st.slider("Meses de referência para giro", 1, 12, 3)

        # Giro médio
        ano_max = int(df_vendas["ano"].max())
        mes_max = int(df_vendas[df_vendas["ano"] == ano_max]["mes"].max())
        periodos = []
        for _ in range(meses_ref):
            periodos.append(f"{ano_max}-{mes_max:02d}")
            mes_max -= 1
            if mes_max == 0:
                mes_max = 12
                ano_max -= 1

        giro = (
            df_vendas[df_vendas["ano_mes"].isin(periodos)]
            .groupby("sku")["quantidade"]
            .sum()
            .div(meses_ref)
            .reset_index()
            .rename(columns={"quantidade":"giro_mensal"})
        )

        cob = estoque_df.merge(giro, on="sku", how="left")
        cob["giro_mensal"] = cob["giro_mensal"].fillna(0)
        cob["cobertura_meses"] = np.where(
            cob["giro_mensal"] > 0,
            cob["qtde_estoque"] / cob["giro_mensal"],
            np.inf
        )

        def status_cob(v):
            if v == np.inf:  return "Sem giro"
            if v < 1.5:      return "🔴 Crítico"
            if v < 3.0:      return "🟡 Alerta"
            return "🟢 OK"

        cob["status"] = cob["cobertura_meses"].apply(status_cob)

        # Filtro fabricante
        fab_cob = st.multiselect(
            "Fabricante", sorted(cob["fabricante_nome"].unique()),
            default=sorted(cob["fabricante_nome"].unique()),
            key="cob_fab"
        )
        df_cob = cob[cob["fabricante_nome"].isin(fab_cob)]

        col_c1, col_c2, col_c3 = st.columns(3)
        col_c1.metric("🔴 Crítico", (df_cob["status"] == "🔴 Crítico").sum())
        col_c2.metric("🟡 Alerta",  (df_cob["status"] == "🟡 Alerta").sum())
        col_c3.metric("🟢 OK",      (df_cob["status"] == "🟢 OK").sum())

        cols_cob = [c for c in ["status","fabricante_nome","sku","descricao",
                                 "qtde_estoque","giro_mensal","cobertura_meses",
                                 "flag_custo_zero"] if c in df_cob.columns]
        st.dataframe(
            df_cob[cols_cob].sort_values("cobertura_meses"),
            use_container_width=True, height=450
        )

    # ─────────────────────────────────────────
    # TAB 4 – SUGESTÃO DE COMPRAS
    # ─────────────────────────────────────────
    with tab4:
        st.subheader("Sugestão de compras")

        meta_meses   = st.slider("Meta de cobertura (meses)", 1, 6, 2)
        meses_ref_s  = st.slider("Meses de referência para giro", 1, 12, 3, key="sug_ref")

        ano_max2 = int(df_vendas["ano"].max())
        mes_max2 = int(df_vendas[df_vendas["ano"] == ano_max2]["mes"].max())
        periodos2 = []
        for _ in range(meses_ref_s):
            periodos2.append(f"{ano_max2}-{mes_max2:02d}")
            mes_max2 -= 1
            if mes_max2 == 0:
                mes_max2 = 12
                ano_max2 -= 1

        giro2 = (
            df_vendas[df_vendas["ano_mes"].isin(periodos2)]
            .groupby("sku")["quantidade"]
            .sum()
            .div(meses_ref_s)
            .reset_index()
            .rename(columns={"quantidade":"giro_mensal"})
        )

        sug = estoque_df.merge(giro2, on="sku", how="left")
        sug["giro_mensal"] = sug["giro_mensal"].fillna(0)
        sug["necessidade"] = (sug["giro_mensal"] * meta_meses - sug["qtde_estoque"]).clip(lower=0)
        sug["valor_estimado"] = sug["necessidade"] * sug["custo_unitario"]

        col_s1, col_s2 = st.columns(2)
        with col_s1:
            fab_sug = st.multiselect(
                "Fabricante",
                sorted(sug["fabricante_nome"].unique()),
                default=sorted(sug["fabricante_nome"].unique()),
                key="sug_fab"
            )
        with col_s2:
            apenas_nec = st.checkbox("Somente SKUs que precisam de compra", value=True)

        df_s = sug[sug["fabricante_nome"].isin(fab_sug)]
        if apenas_nec:
            df_s = df_s[df_s["necessidade"] > 0]

        k1, k2, k3 = st.columns(3)
        k1.metric("SKUs p/ comprar",     f"{(df_s['necessidade'] > 0).sum():,}")
        k2.metric("Unidades p/ comprar", f"{df_s['necessidade'].sum():,.0f}")
        k3.metric("Valor est. compra",   f"R$ {df_s['valor_estimado'].sum():,.0f}")

        cols_sug = [c for c in ["fabricante_nome","sku","descricao",
                                  "qtde_estoque","giro_mensal","necessidade",
                                  "custo_unitario","valor_estimado","flag_custo_zero"]
                    if c in df_s.columns]

        st.dataframe(
            df_s[cols_sug].sort_values("valor_estimado", ascending=False).reset_index(drop=True),
            use_container_width=True,
        )

        st.download_button(
            "⬇️ Exportar sugestão de compras (CSV)",
            df_s[cols_sug].to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
            "sugestao_compras.csv",
            "text/csv",
        )

    # ─────────────────────────────────────────
    # TAB 5 – FORNECEDORES
    # ─────────────────────────────────────────
    with tab5:
        st.subheader("Condições Comerciais por Fornecedor")

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


if __name__ == "__main__":
    main()
