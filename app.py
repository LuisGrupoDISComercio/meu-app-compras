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

    "LG":             "LG",
    "SAMSUNG":        "Samsung",
    "GREE":           "Gree",
    "TRANE":          "Trane",
    "TCL":            "TCL",
    "AGRATTO":        "Agratto",

    # categorias especiais que você usa no Excel
    "DANIFICADO":     "DANIFICADOS",
    "DANIFICADOS":    "DANIFICADOS",
    "SEMI":           "SEMI NOVOS",
    "SEMI NOVOS":     "SEMI NOVOS",
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

        header_row = None
        for i, row in df_raw.iterrows():
            vals = [str(c).strip().lower() for c in row.values]
            if any("fabr" in v for v in vals) and any("produto" in v for v in vals):
                header_row = i
                break

        if header_row is None:
            st.error("Cabeçalho não encontrado no Estoque.xlsx. "
                     "Verifique se as colunas 'Fabr' e 'Produto' existem.")
            return pd.DataFrame()

        df = pd.read_excel(file, header=header_row)
        df.columns = [str(c).strip() for c in df.columns]

        df = df.rename(columns={
            "Fabr":                         "fabr_codigo",
            "Produto":                      "produto_codigo",
            "Descrição":                    "descricao",
            "ABC":                          "abc",
            "Cubagem (Un)":                 "cubagem",
            "Qtde":                         "qtde_estoque",
            "Custo Entrada Unitário Médio": "custo_unitario",
            "Custo Entrada Total":          "custo_total",
        })

        df = df.dropna(how="all")

        if "descricao" in df.columns:
            df = df[~df["descricao"].astype(str).str.strip().str.upper().isin(["TOTAL", "NAN", ""])]

        df["fabr_codigo"] = pd.to_numeric(df["fabr_codigo"], errors="coerce")
        df = df.dropna(subset=["fabr_codigo"])
        df["fabr_codigo"] = df["fabr_codigo"].astype(int)

        df = df[~df["fabr_codigo"].isin(FABRICANTES_IGNORAR)]
        df = df[df["fabr_codigo"].isin(MAPA_FABRICANTES_ESTOQUE.keys())]

        df["fabricante_nome"] = df["fabr_codigo"].map(MAPA_FABRICANTES_ESTOQUE)

        for col in ["qtde_estoque", "custo_unitario", "custo_total", "cubagem"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        # flag de custo zero
        df["flag_custo_zero"] = (df["custo_total"] == 0).astype(int)

        df["produto_codigo"] = df["produto_codigo"].astype(str).str.strip().str.zfill(6)
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
        df.columns = [c.strip() for c in df.columns]

        df = df.rename(columns={
            "Emissao NF":  "data_emissao",
            "Marca":       "marca_raw",
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

        df["marca_raw"] = df["marca_raw"].astype(str).strip().str.upper()

        # normalização de marca para bater com o Excel
        def normaliza_marca(m):
            m_up = str(m).upper().strip()
            if m_up in NORMALIZA_MARCA_VENDAS:
                return NORMALIZA_MARCA_VENDAS[m_up]
            # DANIFICADO / SEMI / ELGIN na descrição
            d = ""
            try:
                d = str(df.at[df.index[df['marca_raw'] == m][0], 'descricao']).upper()
            except Exception:
                d = ""
            if "DANIFICADO" in d:
                return "DANIFICADOS"
            if "SEMI" in d:
                return "SEMI NOVOS"
            if "ELGIN" in d:
                return "ELGIN"
            return m_up.title()

        df["fabricante_nome"] = df["marca_raw"].apply(
            lambda x: NORMALIZA_MARCA_VENDAS.get(x, x.title())
        )

        df["produto_codigo"] = df["produto_codigo"].astype(str).str.strip().str.zfill(6)

        # só vendas com valor > 0 (como no relatório)
        df = df[df["valor_total"] > 0]

        return df.reset_index(drop=True)

    except Exception as e:
        st.error(f"Erro ao carregar vendas: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────
# LÓGICA: COBERTURA & SUGESTÃO (mantida)
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
    df.loc[df["cobertura_meses"] < cobertura_alvo/2.0, "status"] = "🔴 Crítico"

    return df


# ─────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────
def main():
    st.title("❄️ Gestão de Compras — Ar Condicionado")

    st.sidebar.title("📂 Arquivos")
    file_estoque = st.sidebar.file_uploader("Estoque.xlsx", type=["xlsx", "xls"])
    file_vendas  = st.sidebar.file_uploader("Vendas.csv",   type=["csv", "txt"])

    if file_estoque:
        estoque_df = carregar_estoque(file_estoque)
    else:
        estoque_df = pd.DataFrame()

    if file_vendas:
        vendas_df = carregar_vendas(file_vendas)
    else:
        vendas_df = pd.DataFrame()

    if not estoque_df.empty:
        st.sidebar.markdown(
            f"**Estoque:** {estoque_df['produto_codigo'].nunique()} SKUs · "
            f"{int(estoque_df['qtde_estoque'].sum()):,} un."
        )
    if not vendas_df.empty:
        st.sidebar.markdown(
            f"**Vendas:** {vendas_df['produto_codigo'].nunique()} SKUs · "
            f"R$ {vendas_df['valor_total'].sum():,.0f}"
        )

    c1, c2, c3 = st.sidebar.columns(3)
    cenario_pct = c1.number_input("% cenário", -50.0, 100.0, 0.0, 5.0)
    cobertura_alvo = c2.number_input("Cobertura (meses)", 1, 12, 3, 1)
    meses_base = c3.number_input("Média (meses)", 1, 12, 3, 1)

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Estoque & ABC", "Vendas & Demanda", "Cobertura", "Sugestão", "Fornecedores"
    ])

    # ─────────────────────────────────────
    # TAB 1 – ESTOQUE & ABC
    # ─────────────────────────────────────
    with tab1:
        st.subheader("Estoque & Curva ABC")
        if estoque_df.empty:
            st.info("Faça upload do Estoque.xlsx para ver o estoque.")
        else:
            fab_opts = ["Todos"] + sorted(estoque_df["fabricante_nome"].dropna().unique().tolist())
            grp_opts = ["Todos"] + sorted(estoque_df["grupo"].dropna().unique().tolist())

            c1, c2, c3 = st.columns(3)
            fab_sel = c1.selectbox("Fabricante", fab_opts, key="fab_est")
            grp_sel = c2.selectbox("Grupo",      grp_opts, key="grp_est")
            flag_sel = c3.selectbox(
                "Itens de custo",
                ["Todos", "Somente com custo", "Somente custo zero"],
                key="flag_custo"
            )

            df_e = estoque_df.copy()
            if fab_sel != "Todos":
                df_e = df_e[df_e["fabricante_nome"] == fab_sel]
            if grp_sel != "Todos":
                df_e = df_e[df_e["grupo"] == grp_sel]
            if flag_sel == "Somente com custo":
                df_e = df_e[df_e["flag_custo_zero"] == 0]
            elif flag_sel == "Somente custo zero":
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

    # ─────────────────────────────────────
    # TAB 2 – VENDAS & DEMANDA (AJUSTADO)
    # ─────────────────────────────────────
    with tab2:
        st.subheader("Vendas & Demanda — igual ao relatório de Excel")

        if vendas_df.empty:
            st.info("Faça upload do Vendas.csv para começar.")
        else:
            anos_disp = sorted(vendas_df["ano"].unique().tolist())
            ano_sel = st.selectbox("Ano", anos_disp, index=len(anos_disp)-1)

            meses_ano = sorted(vendas_df.loc[vendas_df["ano"] == ano_sel, "mes"].unique())
            meses_labels = [f"{MESES_PT[m]} ({m:02d})" for m in meses_ano]
            mes_map = dict(zip(meses_labels, meses_ano))
            mes_label_sel = st.selectbox("Mês", meses_labels, index=2 if 3 in meses_ano else 0)  # tenta deixar "Mar"
            mes_sel = mes_map[mes_label_sel]

            # esse filtro reproduz o que você faz na Tabela Dinâmica
            df_vm = vendas_df[(vendas_df["ano"] == ano_sel) & (vendas_df["mes"] == mes_sel)].copy()

            # TABELA: total VL por Marca, igual ao Excel
            resumo_marca = (
                df_vm.groupby("fabricante_nome")["valor_total"]
                .sum()
                .reset_index()
                .sort_values("valor_total", ascending=False)
            )

            total_mes = resumo_marca["valor_total"].sum()

            st.markdown(f"**Resumo de vendas – {MESES_PT[mes_sel]}/{ano_sel}**")
            st.dataframe(
                resumo_marca.rename(columns={
                    "fabricante_nome":"Marca",
                    "valor_total":    "Soma de VL Total (R$)"
                }),
                use_container_width=True,
                height=350
            )
            st.markdown(
                f"**Total Geral:** R$ {total_mes:,.2f}"
            )

            # Gráfico para visual
            fig = px.bar(
                resumo_marca,
                x="fabricante_nome",
                y="valor_total",
                title=f"Vendas por Marca — {MESES_PT[mes_sel]}/{ano_sel}",
                labels={"fabricante_nome":"Marca","valor_total":"R$"},
            )
            st.plotly_chart(fig, use_container_width=True)

    # ─────────────────────────────────────
    # TAB 3 – COBERTURA
    # ─────────────────────────────────────
    with tab3:
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

    # ─────────────────────────────────────
    # TAB 4 – SUGESTÃO
    # ─────────────────────────────────────
    with tab4:
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

    # ─────────────────────────────────────
    # TAB 5 – FORNECEDORES
    # ─────────────────────────────────────
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
