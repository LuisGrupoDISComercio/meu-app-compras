import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO

# ─────────────────────────────────────────────
# CONFIGURAÇÃO DA PÁGINA
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Gestão de Compras | Ar Condicionado",
    page_icon="❄️",
    layout="wide"
)

# ─────────────────────────────────────────────
# MAPA DE FABRICANTES (Coluna "Fabr" do ERP)
# ─────────────────────────────────────────────
MAPA_FABRICANTES = {
    2:   "LG",
    3:   "SAMSUNG",
    4:   "SPRINGER MIDEA",
    5:   "DAIKIN",
    6:   "AGRATTO",
    7:   "GREE",
    10:  "TRANE",
    11:  "TCL",
}

# Fabricantes estratégicos (motor de compras)
FABRICANTES_ESTRATEGICOS = ["LG", "GREE", "TCL", "DAIKIN", "SPRINGER MIDEA", "SAMSUNG", "TRANE"]

# Limites de crédito e condições por fornecedor
CONDICOES_FORNECEDOR = {
    "LG":             {"limite": 3_500_000,  "prazos": [30],                    "antecipado": False},
    "GREE":           {"limite": 45_000_000, "prazos": [120],                   "antecipado": False},
    "TCL":            {"limite": 19_000_000, "prazos": [90],                    "antecipado": False},
    "DAIKIN":         {"limite": 45_000_000, "prazos": [150, 180, 210, 240],    "antecipado": False},
    "SPRINGER MIDEA": {"limite": 28_000_000, "prazos": [90],                    "antecipado": False},
    "SAMSUNG":        {"limite": 0,          "prazos": [],                      "antecipado": True},
    "TRANE":          {"limite": 0,          "prazos": [],                      "antecipado": True},
}

# Grupos de produto
GRUPOS = {
    "MSP":  "Multi Split",
    "INV":  "Split Hiwall",
    "LCIN": "Linha Comercial",
    "LCFI": "Linha Comercial",
    "VRF":  "VRF",
    "CRT":  "Cortina de Ar",
}

# ─────────────────────────────────────────────
# FUNÇÕES DE CARREGAMENTO
# ─────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def carregar_estoque(file):
    """Lê o relatório de estoque do ERP, pulando o cabeçalho textual."""
    try:
        df_raw = pd.read_excel(file, header=None)

        # Encontra a linha que contém "Fabr" para usar como cabeçalho
        header_row = None
        for i, row in df_raw.iterrows():
            if any(str(c).strip() == "Fabr" for c in row.values):
                header_row = i
                break

        if header_row is None:
            st.error("Coluna 'Fabr' não encontrada no arquivo de estoque.")
            return pd.DataFrame()

        df = pd.read_excel(file, header=header_row)

        # Remove coluna unnamed inicial se existir
        df = df.loc[:, ~df.columns.str.startswith("Unnamed")]

        # Renomeia colunas para padrão interno
        df = df.rename(columns={
            "Fabr":                           "fabr_codigo",
            "Produto":                        "sku",
            "Descrição":                      "descricao",
            "ABC":                            "abc_erp",
            "Cubagem (Un)":                   "cubagem_un",
            "Qtde":                           "qtde_estoque",
            "Custo Entrada Unitário Médio":   "custo_medio_unit",
            "Custo Entrada Total":            "custo_total",
        })

        # Converte código do fabricante para inteiro
        df["fabr_codigo"] = pd.to_numeric(df["fabr_codigo"], errors="coerce")

        # Remove linhas sem código de fabricante
        df = df.dropna(subset=["fabr_codigo"])
        df["fabr_codigo"] = df["fabr_codigo"].astype(int)

        # Filtra apenas fabricantes estratégicos (exclui 900–999)
        df = df[df["fabr_codigo"].isin(MAPA_FABRICANTES.keys())]

        # Adiciona nome do fabricante
        df["fabricante"] = df["fabr_codigo"].map(MAPA_FABRICANTES)

        # Converte numéricos
        for col in ["qtde_estoque", "custo_medio_unit", "custo_total", "cubagem_un"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        # Remove itens sem custo (serviços, acessórios sem valor)
        df = df[df["custo_total"] > 0]

        # Infere grupo a partir da descrição
        df["grupo"] = df["descricao"].apply(inferir_grupo)

        return df.reset_index(drop=True)

    except Exception as e:
        st.error(f"Erro ao carregar estoque: {e}")
        return pd.DataFrame()


@st.cache_data(show_spinner=False)
def carregar_vendas(file):
    """Lê o CSV de vendas."""
    try:
        # Tenta UTF-8, depois latin-1
        try:
            df = pd.read_csv(file, sep=";", encoding="utf-8", on_bad_lines="skip")
        except UnicodeDecodeError:
            file.seek(0)
            df = pd.read_csv(file, sep=";", encoding="latin-1", on_bad_lines="skip")

        df = df.rename(columns={
            "Emissao NF":  "data_emissao",
            "Marca":       "fabricante",
            "Grupo":       "grupo_codigo",
            "BTU":         "btu",
            "Ciclo":       "ciclo",
            "Produto":     "sku",
            "Descricao":   "descricao",
            "Qtde":        "quantidade",
            "VL Total":    "valor_total",
        })

        # Parse de data
        df["data_emissao"] = pd.to_datetime(df["data_emissao"], dayfirst=True, errors="coerce")
        df = df.dropna(subset=["data_emissao"])

        df["ano"]  = df["data_emissao"].dt.year
        df["mes"]  = df["data_emissao"].dt.month
        df["ano_mes"] = df["data_emissao"].dt.to_period("M").astype(str)

        # Converte numéricos
        df["quantidade"]  = pd.to_numeric(df["quantidade"],  errors="coerce").fillna(0)
        df["valor_total"] = pd.to_numeric(df["valor_total"],  errors="coerce").fillna(0)
        df["btu"]         = pd.to_numeric(df["btu"],          errors="coerce")

        # Normaliza fabricante
        df["fabricante"] = df["fabricante"].str.upper().str.strip()

        # Grupo legível
        df["grupo_desc"] = df["grupo_codigo"].map(GRUPOS).fillna(df["grupo_codigo"])

        # Filtra valor zero (devoluções / notas internas)
        df = df[df["valor_total"] > 0]

        return df.reset_index(drop=True)

    except Exception as e:
        st.error(f"Erro ao carregar vendas: {e}")
        return pd.DataFrame()


def inferir_grupo(descricao):
    """Infere o grupo do produto a partir da descrição."""
    if pd.isna(descricao):
        return "OUTROS"
    d = str(descricao).upper()
    if any(x in d for x in ["MULTI", "BI-SPLIT", "BISPLIT", "GMV", "DVM", "VRF", "TVR"]):
        if any(x in d for x in ["GMV", "DVM", "VRF", "TVR"]):
            return "VRF"
        return "MSP"
    if any(x in d for x in ["CASSETE", "PISO TETO", "DUTO", "DUTOS", "TETO INV", "K7 INV", "SKYAIR", "SKY AIR", "MINI SKY"]):
        return "LCIN"
    if "CORTINA" in d:
        return "CRT"
    return "INV"


# ─────────────────────────────────────────────
# FUNÇÕES DE ANÁLISE
# ─────────────────────────────────────────────

def calcular_abc(df, coluna_valor, coluna_id, label="ABC"):
    """Calcula curva ABC pelo critério 80/95/100."""
    df = df.copy()
    df = df.sort_values(coluna_valor, ascending=False)
    df["acum_%"] = df[coluna_valor].cumsum() / df[coluna_valor].sum() * 100
    df[label] = "C"
    df.loc[df["acum_%"] <= 80, label] = "A"
    df.loc[(df["acum_%"] > 80) & (df["acum_%"] <= 95), label] = "B"
    return df


def calcular_cobertura(estoque_df, vendas_df, meses_media=3):
    """Calcula cobertura de estoque em meses por SKU."""
    # Venda média mensal por SKU nos últimos N meses
    ultimo_mes = vendas_df["data_emissao"].max()
    inicio = ultimo_mes - pd.DateOffset(months=meses_media)
    vendas_recentes = vendas_df[vendas_df["data_emissao"] >= inicio]

    media_mensal = (
        vendas_recentes.groupby("sku")["quantidade"]
        .sum()
        .div(meses_media)
        .reset_index()
        .rename(columns={"quantidade": "venda_media_mensal"})
    )

    df = estoque_df.merge(media_mensal, on="sku", how="left")
    df["venda_media_mensal"] = df["venda_media_mensal"].fillna(0)
    df["cobertura_meses"] = np.where(
        df["venda_media_mensal"] > 0,
        df["qtde_estoque"] / df["venda_media_mensal"],
        np.nan
    )
    return df


def projecao_demanda(vendas_df, cenario_pct=0):
    """
    Projeta demanda mensal para os próximos 6 meses
    com base na média do mesmo período do ano anterior.
    cenario_pct: +10 = alta 10%, -10 = baixa 10%, 0 = neutro
    """
    hoje = pd.Timestamp.today()
    meses_futuros = [(hoje + pd.DateOffset(months=i)).month for i in range(1, 7)]
    anos_futuros  = [(hoje + pd.DateOffset(months=i)).year  for i in range(1, 7)]

    resultados = []
    for mes, ano in zip(meses_futuros, anos_futuros):
        ano_ref = ano - 1
        historico = vendas_df[
            (vendas_df["mes"] == mes) &
            (vendas_df["ano"] == ano_ref)
        ]
        if historico.empty:
            continue

        por_grupo = (
            historico.groupby(["fabricante", "grupo_codigo"])
            .agg(qtde=("quantidade", "sum"), valor=("valor_total", "sum"))
            .reset_index()
        )
        por_grupo["mes_projetado"] = mes
        por_grupo["ano_projetado"] = ano
        por_grupo["qtde_projetada"]  = por_grupo["qtde"]  * (1 + cenario_pct / 100)
        por_grupo["valor_projetado"] = por_grupo["valor"] * (1 + cenario_pct / 100)
        resultados.append(por_grupo)

    if resultados:
        return pd.concat(resultados, ignore_index=True)
    return pd.DataFrame()


def sugestao_compras(estoque_df, vendas_df, cenario_pct=0, cobertura_alvo=2):
    """
    Sugere quantidade e valor a comprar por fabricante + grupo,
    respeitando limites de crédito.
    cobertura_alvo: meses de estoque desejados
    """
    df_cob = calcular_cobertura(estoque_df, vendas_df)
    df_cob["necessidade_unid"] = np.where(
        df_cob["venda_media_mensal"] > 0,
        np.maximum(0, (cobertura_alvo * df_cob["venda_media_mensal"]) - df_cob["qtde_estoque"]),
        0
    )
    df_cob["valor_necessidade"] = df_cob["necessidade_unid"] * df_cob["custo_medio_unit"]
    df_cob["valor_necessidade"] *= (1 + cenario_pct / 100)

    sugestao = (
        df_cob.groupby("fabricante")
        .agg(
            valor_sugerido=("valor_necessidade", "sum"),
            skus_repor=("necessidade_unid", lambda x: (x > 0).sum())
        )
        .reset_index()
    )

    # Aplica restrição de crédito
    def aplicar_limite(row):
        cond = CONDICOES_FORNECEDOR.get(row["fabricante"], {})
        limite = cond.get("limite", 0)
        antecipado = cond.get("antecipado", False)
        if antecipado:
            row["observacao"] = "⚠️ Pagamento antecipado – verificar caixa disponível"
            row["valor_aprovado"] = row["valor_sugerido"]
        elif limite > 0:
            row["valor_aprovado"] = min(row["valor_sugerido"], limite)
            row["observacao"] = "✅ Dentro do limite" if row["valor_sugerido"] <= limite else f"🔴 Excede limite em R$ {row['valor_sugerido'] - limite:,.0f}"
        else:
            row["valor_aprovado"] = 0
            row["observacao"] = "❌ Sem crédito definido"
        return row

    sugestao = sugestao.apply(aplicar_limite, axis=1)
    return sugestao


# ─────────────────────────────────────────────
# INTERFACE STREAMLIT
# ─────────────────────────────────────────────

def main():
    st.title("❄️ Gestão de Compras – Ar Condicionado")
    st.caption("Ferramenta de apoio ao comprador | Distribuidora de climatização")

    # ── Sidebar: Upload de arquivos ──
    with st.sidebar:
        st.header("📂 Dados")
        file_estoque = st.file_uploader("Relatório de Estoque (.xlsx)", type=["xlsx", "xls"])
        file_vendas  = st.file_uploader("Histórico de Vendas (.csv)",   type=["csv"])

        st.divider()
        st.header("⚙️ Parâmetros")
        meses_media     = st.slider("Meses p/ média de vendas", 1, 12, 3)
        cobertura_alvo  = st.slider("Cobertura alvo (meses)", 1, 6, 2)
        cenario_pct     = st.select_slider(
            "Cenário de vendas",
            options=[-30, -20, -10, 0, 10, 20, 30],
            value=0,
            format_func=lambda x: f"{'Alta' if x > 0 else 'Baixa' if x < 0 else 'Neutro'} {abs(x)}%" if x != 0 else "Neutro"
        )

    if not file_estoque and not file_vendas:
        st.info("👈 Faça o upload do Estoque e das Vendas na barra lateral para começar.")
        _exibir_painel_condicoes()
        return

    # ── Carregamento ──
    estoque_df = pd.DataFrame()
    vendas_df  = pd.DataFrame()

    if file_estoque:
        with st.spinner("Carregando estoque..."):
            estoque_df = carregar_estoque(file_estoque)

    if file_vendas:
        with st.spinner("Carregando vendas..."):
            vendas_df = carregar_vendas(file_vendas)

    # ── Abas principais ──
    abas = st.tabs([
        "📦 Estoque",
        "📊 Curva ABC",
        "📈 Vendas & Tendência",
        "🔮 Projeção de Demanda",
        "🛒 Sugestão de Compras",
        "💳 Condições de Fornecedores",
    ])

    # ══════════════════════════════════
    # ABA 1 – ESTOQUE
    # ══════════════════════════════════
    with abas[0]:
        st.subheader("📦 Visão de Estoque")
        if estoque_df.empty:
            st.warning("Faça upload do arquivo de estoque.")
        else:
            # KPIs
            total_valor = estoque_df["custo_total"].sum()
            total_skus  = estoque_df["sku"].nunique()
            total_unid  = estoque_df["qtde_estoque"].sum()

            col1, col2, col3 = st.columns(3)
            col1.metric("Valor Total em Estoque", f"R$ {total_valor:,.0f}".replace(",", "."))
            col2.metric("SKUs Ativos", f"{total_skus:,}")
            col3.metric("Unidades em Estoque", f"{total_unid:,.0f}".replace(",", "."))

            st.divider()

            # Filtros
            fab_opcoes = ["Todos"] + sorted(estoque_df["fabricante"].dropna().unique().tolist())
            fab_sel    = st.selectbox("Filtrar por Fabricante", fab_opcoes, key="est_fab")
            grp_opcoes = ["Todos"] + sorted(estoque_df["grupo"].dropna().unique().tolist())
            grp_sel    = st.selectbox("Filtrar por Grupo", grp_opcoes, key="est_grp")

            df_view = estoque_df.copy()
            if fab_sel != "Todos":
                df_view = df_view[df_view["fabricante"] == fab_sel]
            if grp_sel != "Todos":
                df_view = df_view[df_view["grupo"] == grp_sel]

            st.dataframe(
                df_view[[
                    "fabricante", "grupo", "sku", "descricao",
                    "abc_erp", "qtde_estoque", "custo_medio_unit", "custo_total"
                ]].sort_values("custo_total", ascending=False),
                use_container_width=True,
                height=420
            )

            # Gráfico por fabricante
            por_fab = estoque_df.groupby("fabricante")["custo_total"].sum().reset_index()
            fig = px.bar(
                por_fab.sort_values("custo_total", ascending=False),
                x="fabricante", y="custo_total",
                title="Valor em Estoque por Fabricante",
                labels={"custo_total": "Valor (R$)", "fabricante": "Fabricante"},
                color="fabricante"
            )
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

    # ══════════════════════════════════
    # ABA 2 – CURVA ABC
    # ══════════════════════════════════
    with abas[1]:
        st.subheader("📊 Curva ABC de Estoque")
        if estoque_df.empty:
            st.warning("Faça upload do arquivo de estoque.")
        else:
            df_abc = calcular_abc(estoque_df, "custo_total", "sku", label="ABC_calculado")

            col1, col2, col3 = st.columns(3)
            for classe, col in zip(["A", "B", "C"], [col1, col2, col3]):
                sub = df_abc[df_abc["ABC_calculado"] == classe]
                col.metric(
                    f"Classe {classe}",
                    f"{len(sub)} SKUs",
                    f"R$ {sub['custo_total'].sum():,.0f}".replace(",", ".")
                )

            # Pizza
            resumo_abc = df_abc.groupby("ABC_calculado")["custo_total"].sum().reset_index()
            fig_pizza = px.pie(
                resumo_abc,
                names="ABC_calculado",
                values="custo_total",
                title="Distribuição de Valor por Classe ABC",
                color_discrete_map={"A": "#2ecc71", "B": "#f39c12", "C": "#e74c3c"}
            )
            st.plotly_chart(fig_pizza, use_container_width=True)

            # Tabela detalhada
            st.dataframe(
                df_abc[[
                    "fabricante", "grupo", "sku", "descricao",
                    "abc_erp", "ABC_calculado", "qtde_estoque",
                    "custo_total", "acum_%"
                ]].sort_values("custo_total", ascending=False),
                use_container_width=True,
                height=400
            )

    # ══════════════════════════════════
    # ABA 3 – VENDAS & TENDÊNCIA
    # ══════════════════════════════════
    with abas[2]:
        st.subheader("📈 Histórico de Vendas")
        if vendas_df.empty:
            st.warning("Faça upload do arquivo de vendas.")
        else:
            # KPIs
            total_vend  = vendas_df["valor_total"].sum()
            total_qtde  = vendas_df["quantidade"].sum()
            periodo     = f"{vendas_df['data_emissao'].min().strftime('%d/%m/%Y')} a {vendas_df['data_emissao'].max().strftime('%d/%m/%Y')}"

            col1, col2, col3 = st.columns(3)
            col1.metric("Faturamento Total", f"R$ {total_vend:,.0f}".replace(",", "."))
            col2.metric("Unidades Vendidas", f"{total_qtde:,.0f}".replace(",", "."))
            col3.metric("Período", periodo)

            st.divider()

            # Vendas mensais
            vendas_mensais = vendas_df.groupby("ano_mes")["valor_total"].sum().reset_index()
            fig_line = px.line(
                vendas_mensais,
                x="ano_mes", y="valor_total",
                title="Faturamento Mensal",
                labels={"ano_mes": "Mês", "valor_total": "Faturamento (R$)"},
                markers=True
            )
            st.plotly_chart(fig_line, use_container_width=True)

            # Por fabricante
            col_a, col_b = st.columns(2)
            with col_a:
                por_fab = vendas_df.groupby("fabricante")["valor_total"].sum().reset_index()
                fig_fab = px.bar(
                    por_fab.sort_values("valor_total", ascending=False),
                    x="fabricante", y="valor_total",
                    title="Faturamento por Fabricante",
                    color="fabricante"
                )
                fig_fab.update_layout(showlegend=False)
                st.plotly_chart(fig_fab, use_container_width=True)

            with col_b:
                por_grupo = vendas_df.groupby("grupo_codigo")["valor_total"].sum().reset_index()
                fig_grp = px.pie(
                    por_grupo,
                    names="grupo_codigo",
                    values="valor_total",
                    title="Faturamento por Grupo de Produto"
                )
                st.plotly_chart(fig_grp, use_container_width=True)

            # ABC de vendas
            st.subheader("Curva ABC – Vendas por SKU")
            abc_vendas = vendas_df.groupby(["sku", "descricao", "fabricante"])["valor_total"].sum().reset_index()
            abc_vendas = calcular_abc(abc_vendas, "valor_total", "sku", label="ABC_vendas")
            st.dataframe(
                abc_vendas[[
                    "fabricante", "sku", "descricao",
                    "ABC_vendas", "valor_total", "acum_%"
                ]].sort_values("valor_total", ascending=False),
                use_container_width=True,
                height=380
            )

    # ══════════════════════════════════
    # ABA 4 – PROJEÇÃO DE DEMANDA
    # ══════════════════════════════════
    with abas[3]:
        st.subheader("🔮 Projeção de Demanda – Próximos 6 Meses")
        if vendas_df.empty:
            st.warning("Faça upload do arquivo de vendas.")
        else:
            label_cenario = (
                f"Alta {cenario_pct}%" if cenario_pct > 0
                else f"Baixa {abs(cenario_pct)}%" if cenario_pct < 0
                else "Neutro"
            )
            st.info(f"Cenário aplicado: **{label_cenario}** | Base: mesmo período do ano anterior")

            proj = projecao_demanda(vendas_df, cenario_pct)

            if proj.empty:
                st.warning("Histórico insuficiente para projeção. É necessário pelo menos 1 ano de vendas.")
            else:
                proj["mes_ano"] = proj["ano_projetado"].astype(str) + "-" + proj["mes_projetado"].astype(str).str.zfill(2)

                # Gráfico geral
                proj_mensal = proj.groupby("mes_ano")["valor_projetado"].sum().reset_index()
                fig_proj = px.bar(
                    proj_mensal,
                    x="mes_ano", y="valor_projetado",
                    title="Projeção de Faturamento por Mês",
                    labels={"mes_ano": "Mês", "valor_projetado": "Valor Projetado (R$)"},
                    color_discrete_sequence=["#3498db"]
                )
                st.plotly_chart(fig_proj, use_container_width=True)

                # Por fabricante
                proj_fab = proj.groupby(["mes_ano", "fabricante"])["valor_projetado"].sum().reset_index()
                fig_fab  = px.line(
                    proj_fab,
                    x="mes_ano", y="valor_projetado",
                    color="fabricante",
                    title="Projeção por Fabricante",
                    markers=True
                )
                st.plotly_chart(fig_fab, use_container_width=True)

                st.dataframe(proj, use_container_width=True, height=350)

    # ══════════════════════════════════
    # ABA 5 – SUGESTÃO DE COMPRAS
    # ══════════════════════════════════
    with abas[4]:
        st.subheader("🛒 Sugestão de Compras por Fornecedor")

        if estoque_df.empty or vendas_df.empty:
            st.warning("É necessário carregar Estoque e Vendas para calcular sugestão de compras.")
        else:
            label_cenario = (
                f"Alta {cenario_pct}%" if cenario_pct > 0
                else f"Baixa {abs(cenario_pct)}%" if cenario_pct < 0
                else "Neutro"
            )
            st.info(
                f"Cenário: **{label_cenario}** | "
                f"Cobertura alvo: **{cobertura_alvo} meses** | "
                f"Média baseada em: **{meses_media} meses**"
            )

            sug = sugestao_compras(estoque_df, vendas_df, cenario_pct, cobertura_alvo)

            # KPI total
            total_aprovado = sug["valor_aprovado"].sum()
            st.metric("Total Aprovado para Compra", f"R$ {total_aprovado:,.0f}".replace(",", "."))

            # Gráfico
            fig_sug = px.bar(
                sug.sort_values("valor_aprovado", ascending=False),
                x="fabricante", y=["valor_sugerido", "valor_aprovado"],
                barmode="group",
                title="Necessidade vs. Valor Aprovado por Fornecedor",
                labels={"value": "Valor (R$)", "fabricante": "Fornecedor", "variable": ""},
                color_discrete_map={"valor_sugerido": "#95a5a6", "valor_aprovado": "#2ecc71"}
            )
            st.plotly_chart(fig_sug, use_container_width=True)

            # Tabela
            st.dataframe(
                sug[["fabricante", "skus_repor", "valor_sugerido", "valor_aprovado", "observacao"]]
                .sort_values("valor_aprovado", ascending=False)
                .rename(columns={
                    "fabricante":     "Fornecedor",
                    "skus_repor":     "SKUs a Repor",
                    "valor_sugerido": "Valor Necessidade (R$)",
                    "valor_aprovado": "Valor Aprovado (R$)",
                    "observacao":     "Status / Observação"
                }),
                use_container_width=True
            )

            # Cobertura detalhada
            st.subheader("Cobertura de Estoque por SKU")
            df_cob = calcular_cobertura(estoque_df, vendas_df, meses_media)
            st.dataframe(
                df_cob[[
                    "fabricante", "grupo", "sku", "descricao",
                    "qtde_estoque", "venda_media_mensal", "cobertura_meses"
                ]].sort_values("cobertura_meses"),
                use_container_width=True,
                height=400
            )

    # ══════════════════════════════════
    # ABA 6 – CONDIÇÕES DE FORNECEDORES
    # ══════════════════════════════════
    with abas[5]:
        _exibir_painel_condicoes()


def _exibir_painel_condicoes():
    st.subheader("💳 Condições Comerciais por Fornecedor")
    dados = []
    for fab, cond in CONDICOES_FORNECEDOR.items():
        dados.append({
            "Fornecedor":       fab,
            "Limite de Crédito": f"R$ {cond['limite']:,.0f}".replace(",", ".") if cond["limite"] > 0 else "—",
            "Prazos (dias)":    ", ".join(map(str, cond["prazos"])) if cond["prazos"] else "Antecipado",
            "Pagamento Antec.": "✅ Sim" if cond["antecipado"] else "Não",
        })
    st.dataframe(pd.DataFrame(dados), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("📋 Perfil de Recebíveis dos Clientes")
    col1, col2, col3 = st.columns(3)
    col1.metric("À Vista", "30%")
    col2.metric("Parcelado", "70%")
    col3.metric("Parcelado em 10x", "85% do parcelado")
    st.caption("Fonte: parâmetros informados pela equipe comercial.")


if __name__ == "__main__":
    main()
