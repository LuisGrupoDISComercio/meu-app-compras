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
MAPA_FABRICANTES = {
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

NORMALIZA_MARCA = {
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
    1:"Jan",2:"Fev",3:"Mar",4:"Abr",
    5:"Mai",6:"Jun",7:"Jul",8:"Ago",
    9:"Set",10:"Out",11:"Nov",12:"Dez"
}

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


def inferir_grupo(desc: str) -> str:
    if not isinstance(desc, str):
        return "OUTROS"
    d = desc.upper()
    if any(x in d for x in ["VRF", "TVR", "DVM", "GMV"]):
        return "VRF"
    if any(x in d for x in ["MULTI", "BI-SPLIT", "BISPLIT", "MSP"]):
        return "MSP"
    if any(x in d for x in ["CASSETE", "PISO TETO", "TETO INV", "TETO LEVE",
                              "K7 INV", "K7 RED", "K7 LEVE", "K7 REDONDO",
                              "DUTO", " DT ", " PT "]):
        return "LCIN"
    if "CORTINA" in d:
        return "CRT"
    if any(x in d for x in ["AR COND", "EVAP", "COND.", "SPLIT", "INVERTER", "INV"]):
        return "INV"
    return "OUTROS"


def extrair_btu(desc: str):
    if not isinstance(desc, str):
        return None
    m = re.search(
        r'\b(7000|9000|9500|12000|18000|21000|24000|28000|30000|'
        r'34000|36000|38000|42000|48000|56000|57000|60000)\b', desc
    )
    if m:
        return int(m.group(1))
    m2 = re.search(r'\b(07|09|12|18|24|30|36|48|56|60)\b', desc)
    if m2:
        return int(m2.group(1)) * 1000
    return None


def calcular_curva_abc(df: pd.DataFrame, col_valor: str) -> pd.DataFrame:
    df = df.copy().sort_values(col_valor, ascending=False)
    total = df[col_valor].sum()
    if total <= 0:
        df["curva_abc"] = "C"
        return df
    df["pct_acum"] = df[col_valor].cumsum() / total
    df["curva_abc"] = "C"
    df.loc[df["pct_acum"] <= 0.80, "curva_abc"] = "A"
    df.loc[(df["pct_acum"] > 0.80) & (df["pct_acum"] <= 0.95), "curva_abc"] = "B"
    return df

# ─────────────────────────────────────────────
# CARREGAMENTO: ESTOQUE
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def carregar_estoque(file) -> pd.DataFrame:
    try:
        df_raw = pd.read_excel(file, header=None)

        # ── CORREÇÃO PRINCIPAL ──────────────────────────────────────────
        # Converte tudo para string antes de checar, evitando TypeError
        # quando a célula é float (NaN) ou int
        header_row = None
        for i, row in df_raw.iterrows():
            vals = [str(c).strip().lower() for c in row.values]
            if any("fabr" in v for v in vals) and any("produto" in v for v in vals):
                header_row = i
                break
        # ────────────────────────────────────────────────────────────────

        if header_row is None:
            st.error("Cabeçalho não encontrado no Estoque.xlsx. "
                     "Verifique se as colunas 'Fabr' e 'Produto' existem.")
            return pd.DataFrame()

        df = pd.read_excel(file, header=header_row)
        df.columns = [str(c).strip() for c in df.columns]

        # Renomeia colunas para padrão interno
        rename_map = {
            "Fabr":                         "fabr_codigo",
            "Produto":                      "produto_codigo",
            "Descrição":                    "descricao",
            "ABC":                          "abc",
            "Cubagem (Un)":                 "cubagem",
            "Qtde":                         "qtde_estoque",
            "Custo Entrada Unitário Médio": "custo_unitario",
            "Custo Entrada Total":          "custo_total",
        }
        df = df.rename(columns=rename_map)

        # Remove linhas totalmente vazias
        df = df.dropna(how="all")

        # Remove linha de TOTAL
        if "descricao" in df.columns:
            df = df[~df["descricao"].astype(str).str.strip().str.upper().isin(["TOTAL", "NAN", ""])]

        # Converte código do fabricante para inteiro
        df["fabr_codigo"] = pd.to_numeric(df["fabr_codigo"], errors="coerce")
        df = df.dropna(subset=["fabr_codigo"])
        df["fabr_codigo"] = df["fabr_codigo"].astype(int)

        # Remove fabricantes ignorados (900–999)
        df = df[~df["fabr_codigo"].isin(FABRICANTES_IGNORAR)]

        # Filtra apenas fabricantes conhecidos
        df = df[df["fabr_codigo"].isin(MAPA_FABRICANTES.keys())]

        # Mapeia nome do fabricante
        df["fabricante_nome"] = df["fabr_codigo"].map(MAPA_FABRICANTES)

        # Converte numéricos
        for col in ["qtde_estoque", "custo_unitario", "custo_total", "cubagem"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        # Flag custo zero (NÃO remove, apenas marca)
        df["flag_custo_zero"] = (df["custo_total"] == 0).astype(int)

        # Produto código como string
        df["produto_codigo"] = df["produto_codigo"].astype(str).str.strip().str.zfill(6)

        # Infere grupo e BTU
        df["grupo"]   = df["descricao"].apply(inferir_grupo)
        df["btu"]     = df["descricao"].apply(extrair_btu)

        return df.reset_index(drop=True)

    except Exception as e:
        st.error(f"Erro ao carregar estoque: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────
# CARREGAMENTO: VENDAS
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def carregar_vendas(file) -> pd.DataFrame:
    try:
        raw = file.read()
        texto = decode_bytes(raw)
        df = pd.read_csv(StringIO(texto), sep=";", on_bad_lines="skip")

        df = df.rename(columns={
            "Emissao NF":  "data_emissao",
            "Marca":       "fabricante_raw",
            "Grupo":       "grupo_codigo",
            "BTU":         "btu",
            "Ciclo":       "ciclo",
            "Produto":     "produto_codigo",
            "Descricao":   "descricao",
            "Qtde":        "quantidade",
            "VL Total":    "valor_total",
        })

        df["data_emissao"] = pd.to_datetime(df["data_emissao"], dayfirst=True, errors="coerce")
        df = df.dropna(subset=["data_emissao"])

        df["ano"]     = df["data_emissao"].dt.year
        df["mes"]     = df["data_emissao"].dt.month
        df["ano_mes"] = df["data_emissao"].dt.to_period("M").astype(str)

        df["quantidade"]  = pd.to_numeric(df["quantidade"],  errors="coerce").fillna(0)
        df["valor_total"] = pd.to_numeric(df["valor_total"], errors="coerce").fillna(0)
        df["btu"]         = pd.to_numeric(df["btu"],         errors="coerce")

        df["fabricante_raw"] = df["fabricante_raw"].astype(str).str.strip().str.upper()
        df["fabricante_nome"] = df["fabricante_raw"].map(NORMALIZA_MARCA).fillna(df["fabricante_raw"].str.title())

        df["produto_codigo"] = df["produto_codigo"].astype(str).str.strip().str.zfill(6)

        return df[df["valor_total"] > 0].reset_index(drop=True)

    except Exception as e:
        st.error(f"Erro ao carregar vendas: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────
# LÓGICA: COBERTURA E SUGESTÃO
# ─────────────────────────────────────────────
def calcular_cobertura(estoque: pd.DataFrame, vendas: pd.DataFrame, meses: int) -> pd.DataFrame:
    ultimo_mes = vendas["ano_mes"].max()
    periodos   = sorted(vendas["ano_mes"].unique())
    periodos_base = periodos[-meses:] if len(periodos) >= meses else periodos

    giro = (
        vendas[vendas["ano_mes"].isin(periodos_base)]
        .groupby("produto_codigo")["quantidade"]
        .sum()
        .reset_index()
        .rename(columns={"quantidade": "qtde_vendida"})
    )
    giro["giro_mensal"] = giro["qtde_vendida"] / len(periodos_base)

    df = estoque.merge(giro, on="produto_codigo", how="left")
    df["giro_mensal"]  = df["giro_mensal"].fillna(0)
    df["qtde_vendida"] = df["qtde_vendida"].fillna(0)

    df["cobertura_meses"] = np.where(
        df["giro_mensal"] > 0,
        df["qtde_estoque"] / df["giro_mensal"],
        np.inf
    )
    return df


def sugestao_compras(
    estoque: pd.DataFrame,
    vendas: pd.DataFrame,
    cenario_pct: float,
    cobertura_alvo: int,
    meses_base: int
) -> pd.DataFrame:
    df = calcular_cobertura(estoque, vendas, meses_base)
    df["giro_ajustado"]   = df["giro_mensal"] * (1 + cenario_pct / 100)
    df["estoque_alvo"]    = df["giro_ajustado"] * cobertura_alvo
    df["necessidade"]     = np.maximum(0, df["estoque_alvo"] - df["qtde_estoque"])
    df["valor_estimado"]  = df["necessidade"] * df["custo_unitario"]

    df["status"] = "🟢 OK"
    df.loc[df["cobertura_meses"] < cobertura_alvo,     "status"] = "🟡 Alerta"
    df.loc[df["cobertura_meses"] < cobertura_alvo / 2, "status"] = "🔴 Crítico"
    df.loc[df["cobertura_meses"] == np.inf,            "status"] = "⚪ Sem giro"

    return df


# ─────────────────────────────────────────────
# INTERFACE
# ─────────────────────────────────────────────
def main():
    st.sidebar.header("📂 Arquivos")
    file_estoque = st.sidebar.file_uploader("Estoque.xlsx", type=["xlsx"])
    file_vendas  = st.sidebar.file_uploader("Vendas.csv",   type=["csv"])

    st.sidebar.divider()
    st.sidebar.header("⚙️ Parâmetros")
    cenario_pct    = st.sidebar.slider("Cenário de crescimento (%)", -30, 50, 0, 5)
    cobertura_alvo = st.sidebar.slider("Cobertura alvo (meses)",      1,  6,  3)
    meses_base     = st.sidebar.slider("Meses para cálculo de giro",  1, 12,  3)

    estoque_df = pd.DataFrame()
    vendas_df  = pd.DataFrame()

    if file_estoque:
        with st.spinner("Carregando estoque..."):
            estoque_df = carregar_estoque(file_estoque)
        if not estoque_df.empty:
            n_sku  = estoque_df["produto_codigo"].nunique()
            n_un   = int(estoque_df["qtde_estoque"].sum())
            v_est  = estoque_df["custo_total"].sum()
            c1, c2, c3 = st.columns(3)
            c1.metric("SKUs em estoque",   f"{n_sku}")
            c2.metric("Unidades",          f"{n_un:,}")
            c3.metric("Valor de estoque",  f"R$ {v_est:,.0f}")

            if estoque_df["flag_custo_zero"].sum() > 0:
                custo_zero = estoque_df[estoque_df["flag_custo_zero"] == 1]
                with st.expander(f"⚠️ {len(custo_zero)} SKU(s) com custo zero — precisam de ajuste no ERP"):
                    st.dataframe(
                        custo_zero[["fabricante_nome","produto_codigo","descricao","qtde_estoque"]],
                        use_container_width=True
                    )

    if file_vendas:
        with st.spinner("Carregando vendas..."):
            vendas_df = carregar_vendas(file_vendas)

    abas = st.tabs([
        "📦 Estoque & ABC",
        "📈 Vendas",
        "🔄 Cobertura",
        "🛒 Sugestão de Compras",
        "💳 Fornecedores",
    ])

    # ══════════════════════════════════
    # ABA 1 – ESTOQUE & ABC
    # ══════════════════════════════════
    with abas[0]:
        st.subheader("Posição de Estoque & Curva ABC")
        if estoque_df.empty:
            st.info("Faça upload do Estoque.xlsx para começar.")
        else:
            fab_opts = ["Todos"] + sorted(estoque_df["fabricante_nome"].dropna().unique().tolist())
            fab_sel  = st.selectbox("Fabricante", fab_opts, key="fab_est")
            grp_opts = ["Todos"] + sorted(estoque_df["grupo"].dropna().unique().tolist())
            grp_sel  = st.selectbox("Grupo", grp_opts, key="grp_est")
            flag_sel = st.radio("Custo", ["Todos", "Com custo", "Custo zero"], horizontal=True)

            df_e = estoque_df.copy()
            if fab_sel != "Todos":
                df_e = df_e[df_e["fabricante_nome"] == fab_sel]
            if grp_sel != "Todos":
                df_e = df_e[df_e["grupo"] == grp_sel]
            if flag_sel == "Com custo":
                df_e = df_e[df_e["flag_custo_zero"] == 0]
            elif flag_sel == "Custo zero":
                df_e = df_e[df_e["flag_custo_zero"] == 1]

            df_e = calcular_curva_abc(df_e, "custo_total")

            st.dataframe(
                df_e[[
                    "curva_abc","fabricante_nome","grupo","produto_codigo",
                    "descricao","abc","qtde_estoque","custo_unitario","custo_total","flag_custo_zero"
                ]].rename(columns={
                    "curva_abc":       "ABC (app)",
                    "fabricante_nome": "Fabricante",
                    "grupo":           "Grupo",
                    "produto_codigo":  "Produto",
                    "descricao":       "Descrição",
                    "abc":             "ABC (ERP)",
                    "qtde_estoque":    "Qtde",
                    "custo_unitario":  "Custo Unit.",
                    "custo_total":     "Custo Total",
                    "flag_custo_zero": "Custo Zero?",
                }),
                use_container_width=True,
                height=500
            )

            col_g1, col_g2 = st.columns(2)
            with col_g1:
                fig1 = px.bar(
                    df_e.groupby("fabricante_nome")["custo_total"].sum().reset_index(),
                    x="fabricante_nome", y="custo_total",
                    title="Estoque por fabricante (R$)",
                    labels={"fabricante_nome":"Fabricante","custo_total":"R$"}
                )
                st.plotly_chart(fig1, use_container_width=True)
            with col_g2:
                fig2 = px.pie(
                    df_e.groupby("curva_abc")["custo_total"].sum().reset_index(),
                    names="curva_abc", values="custo_total",
                    title="Distribuição ABC"
                )
                st.plotly_chart(fig2, use_container_width=True)

            csv_est = df_e.to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇️ Exportar estoque filtrado", csv_est, "estoque.csv", "text/csv")

    # ══════════════════════════════════
    # ABA 2 – VENDAS
    # ══════════════════════════════════
    with abas[1]:
        st.subheader("Histórico de Vendas")
        if vendas_df.empty:
            st.info("Faça upload do Vendas.csv para começar.")
        else:
            fab_v = ["Todos"] + sorted(vendas_df["fabricante_nome"].dropna().unique().tolist())
            fab_v_sel = st.selectbox("Fabricante", fab_v, key="fab_vnd")
            grp_v = ["Todos"] + sorted(vendas_df["grupo_codigo"].dropna().unique().tolist())
            grp_v_sel = st.selectbox("Grupo", grp_v, key="grp_vnd")

            df_v = vendas_df.copy()
            if fab_v_sel != "Todos":
                df_v = df_v[df_v["fabricante_nome"] == fab_v_sel]
            if grp_v_sel != "Todos":
                df_v = df_v[df_v["grupo_codigo"] == grp_v_sel]

            mensal = (
                df_v.groupby(["ano_mes","fabricante_nome"])["valor_total"]
                .sum().reset_index()
            )
            fig_v = px.bar(
                mensal, x="ano_mes", y="valor_total", color="fabricante_nome",
                title="Faturamento mensal por fabricante",
                labels={"ano_mes":"Mês","valor_total":"R$","fabricante_nome":"Fabricante"}
            )
            st.plotly_chart(fig_v, use_container_width=True)

            kv1, kv2, kv3 = st.columns(3)
            kv1.metric("Total faturado",   f"R$ {df_v['valor_total'].sum():,.0f}")
            kv2.metric("SKUs vendidos",    f"{df_v['produto_codigo'].nunique()}")
            kv3.metric("Unidades vendidas",f"{int(df_v['quantidade'].sum()):,}")

            st.dataframe(
                df_v[["data_emissao","fabricante_nome","grupo_codigo","produto_codigo",
                       "descricao","quantidade","valor_total"]]
                .sort_values("data_emissao", ascending=False),
                use_container_width=True, height=400
            )

    # ══════════════════════════════════
    # ABA 3 – COBERTURA
    # ══════════════════════════════════
    with abas[2]:
        st.subheader("Cobertura de Estoque por SKU")
        if estoque_df.empty or vendas_df.empty:
            st.info("Carregue os dois arquivos para ver a cobertura.")
        else:
            df_cob = calcular_cobertura(estoque_df, vendas_df, meses_base)

            fab_c = ["Todos"] + sorted(df_cob["fabricante_nome"].dropna().unique().tolist())
            fab_c_sel = st.selectbox("Fabricante", fab_c, key="fab_cob")
            if fab_c_sel != "Todos":
                df_cob = df_cob[df_cob["fabricante_nome"] == fab_c_sel]

            df_cob["cobertura_fmt"] = df_cob["cobertura_meses"].apply(
                lambda x: "∞" if x == np.inf else f"{x:.1f}"
            )
            st.dataframe(
                df_cob[[
                    "fabricante_nome","grupo","produto_codigo","descricao",
                    "abc","qtde_estoque","giro_mensal","cobertura_fmt","flag_custo_zero"
                ]].rename(columns={
                    "fabricante_nome": "Fabricante",
                    "grupo":           "Grupo",
                    "produto_codigo":  "Produto",
                    "descricao":       "Descrição",
                    "abc":             "ABC",
                    "qtde_estoque":    "Estoque",
                    "giro_mensal":     "Giro/Mês",
                    "cobertura_fmt":   "Cobertura (meses)",
                    "flag_custo_zero": "Custo Zero?",
                }).sort_values("Cobertura (meses)"),
                use_container_width=True,
                height=500
            )

    # ══════════════════════════════════
    # ABA 4 – SUGESTÃO DE COMPRAS
    # ══════════════════════════════════
    with abas[3]:
        st.subheader("Sugestão de Compras")
        if estoque_df.empty or vendas_df.empty:
            st.info("Carregue os dois arquivos para gerar sugestão.")
        else:
            df_sug = sugestao_compras(estoque_df, vendas_df, cenario_pct, cobertura_alvo, meses_base)

            fab_s = ["Todos"] + sorted(df_sug["fabricante_nome"].dropna().unique().tolist())
            fab_s_sel   = st.selectbox("Fabricante", fab_s, key="fab_sug")
            so_criticos = st.checkbox("Mostrar apenas críticos e em alerta", value=True)

            df_s = df_sug.copy()
            if fab_s_sel != "Todos":
                df_s = df_s[df_s["fabricante_nome"] == fab_s_sel]
            if so_criticos:
                df_s = df_s[df_s["status"].isin(["🔴 Crítico", "🟡 Alerta"])]

            k1, k2, k3 = st.columns(3)
            k1.metric("Críticos",           int((df_sug["status"] == "🔴 Crítico").sum()))
            k2.metric("Em alerta",          int((df_sug["status"] == "🟡 Alerta").sum()))
            k3.metric("Valor est. compra",  f"R$ {df_s['valor_estimado'].sum():,.0f}")

            st.dataframe(
                df_s[[
                    "status","fabricante_nome","grupo","produto_codigo","descricao",
                    "qtde_estoque","giro_mensal","cobertura_meses","necessidade",
                    "custo_unitario","valor_estimado"
                ]].rename(columns={
                    "status":           "Status",
                    "fabricante_nome":  "Fabricante",
                    "grupo":            "Grupo",
                    "produto_codigo":   "Produto",
                    "descricao":        "Descrição",
                    "qtde_estoque":     "Estoque",
                    "giro_mensal":      "Giro/Mês",
                    "cobertura_meses":  "Cobertura (meses)",
                    "necessidade":      "Comprar (un)",
                    "custo_unitario":   "Custo Unit.",
                    "valor_estimado":   "Valor Est. (R$)",
                }).sort_values(["Status","Fabricante"]),
                use_container_width=True,
                height=500
            )

            csv_sug = df_s.to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇️ Exportar sugestão", csv_sug, "sugestao_compras.csv", "text/csv")

    # ══════════════════════════════════
    # ABA 5 – FORNECEDORES
    # ══════════════════════════════════
    with abas[4]:
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
