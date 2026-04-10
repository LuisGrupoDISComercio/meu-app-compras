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
    page_title="Gestão de Compras",
    page_icon="❄️",
    layout="wide",
)

# ─────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────
MAPA_FABRICANTES = {
    "002": "LG",
    "003": "Samsung",
    "004": "Carrier / Midea",
    "005": "Daikin",
    "006": "Agratto",
    "007": "Gree",
    "010": "Trane",
    "011": "TCL",
}

FABRICANTES_GIRO = {"002", "003", "004", "005", "006", "007", "010", "011"}

NORMALIZA_MARCA_VENDAS = {
    "SPRINGER MIDEA": "Springer Midea",
    "SPRINGER":       "Springer Midea",
    "MIDEA":          "Springer Midea",
    "DAIKIN":         "Daikin",
    "LG":             "LG",
    "GREE":           "Gree",
    "SAMSUNG":        "Samsung",
    "TRANE":          "Trane",
    "TCL":            "TCL",
    "AGRATTO":        "Agratto",
    "CARRIER":        "Carrier",
}

COBERTURA_META_DIAS = 60   # meta de cobertura em dias
LEAD_TIME_DIAS      = 30   # lead time padrão de reposição

# ─────────────────────────────────────────────
# FUNÇÕES DE CARGA
# ─────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def carregar_estoque(file) -> pd.DataFrame:
    """Lê o relatório de estoque do ERP e retorna o DataFrame de giro."""
    xls = pd.read_excel(file, sheet_name=0, header=None)

    # Localiza a linha de cabeçalho real ("Fabr", "Produto", ...)
    header_row = None
    for i, row in xls.iterrows():
        vals = [str(v).strip().lower() for v in row.values if pd.notna(v)]
        if any("fabr" in v for v in vals) and any("produto" in v for v in vals):
            header_row = i
            break

    if header_row is None:
        st.error("Não foi possível localizar o cabeçalho no arquivo de estoque.")
        st.stop()

    df = pd.read_excel(file, sheet_name=0, header=header_row)
    df.columns = [str(c).strip() for c in df.columns]

    # Renomeia colunas para nomes internos padronizados
    rename_map = {}
    for col in df.columns:
        cl = col.lower()
        if "fabr" in cl and "fabricante" not in cl:
            rename_map[col] = "fabricante_codigo"
        elif col.lower() == "produto":
            rename_map[col] = "sku"
        elif "descri" in cl:
            rename_map[col] = "descricao"
        elif "abc" in cl:
            rename_map[col] = "abc"
        elif "qtde" in cl or "quantidade" in cl:
            rename_map[col] = "qtde_estoque"
        elif "unit" in cl and "custo" in cl:
            rename_map[col] = "custo_unitario"
        elif "total" in cl and "custo" in cl:
            rename_map[col] = "custo_total"

    df = df.rename(columns=rename_map)

    # Remove linhas completamente vazias
    df = df.dropna(how="all")

    # Remove linhas de TOTAL e cabeçalhos repetidos
    if "descricao" in df.columns:
        df = df[~df["descricao"].astype(str).str.upper().str.strip().isin(["TOTAL", "DESCRIÇÃO", "DESCRICAO"])]

    # Garante que fabricante_codigo existe
    if "fabricante_codigo" not in df.columns:
        st.error("Coluna 'Fabr' não encontrada no arquivo de estoque.")
        st.stop()

    # Normaliza fabricante_codigo como string de 3 dígitos
    df["fabricante_codigo"] = (
        df["fabricante_codigo"]
        .astype(str)
        .str.strip()
        .str.split(".")
        .str[0]
        .str.zfill(3)
    )

    # Filtra apenas fabricantes de giro
    df_giro = df[df["fabricante_codigo"].isin(FABRICANTES_GIRO)].copy()

    # Converte colunas numéricas
    for col in ["qtde_estoque", "custo_unitario", "custo_total"]:
        if col in df_giro.columns:
            df_giro[col] = pd.to_numeric(df_giro[col], errors="coerce").fillna(0)

    # Garante que SKU é string
    df_giro["sku"] = df_giro["sku"].astype(str).str.strip().str.split(".").str[0].str.zfill(6)

    # Mapeia fabricante_nome
    df_giro["fabricante_nome"] = df_giro["fabricante_codigo"].map(MAPA_FABRICANTES).fillna("Outros")

    # Corrige fabricante usando descrição quando estiver como "Outros"
    def corrigir_fabricante_com_descricao(row):
        nome = row["fabricante_nome"]
        desc = str(row.get("descricao", "")).upper()
        if nome == "Outros":
            if "DAIKIN" in desc:
                return "Daikin"
            if "MIDEA" in desc or "SPRINGER MIDEA" in desc:
                return "Springer Midea"
            if "GREE" in desc:
                return "Gree"
            if "SAMSUNG" in desc:
                return "Samsung"
            if "AGRATTO" in desc:
                return "Agratto"
            if "TRANE" in desc:
                return "Trane"
            if "TCL" in desc:
                return "TCL"
        return nome

    df_giro["fabricante_nome"] = df_giro.apply(corrigir_fabricante_com_descricao, axis=1)

    # Flag para itens com custo zero (para alertas visuais, sem excluir)
    df_giro["flag_custo_zero"] = df_giro["custo_total"].eq(0)

    return df_giro


@st.cache_data(show_spinner=False)
def carregar_vendas(file) -> pd.DataFrame:
    """Lê o CSV de vendas e retorna o DataFrame normalizado."""
    df = pd.read_csv(
        file,
        sep=";",
        encoding="utf-8",
        on_bad_lines="skip",
        dtype=str,
    )

    df.columns = [c.strip() for c in df.columns]

    # Renomeia colunas
    rename_map = {
        "Emissao NF": "data",
        "Marca":      "marca",
        "Grupo":      "grupo",
        "BTU":        "btu",
        "Ciclo":      "ciclo",
        "Produto":    "sku",
        "Descricao":  "descricao",
        "Qtde":       "qtde_venda",
        "VL Total":   "vl_total",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    # Converte data
    df["data"] = pd.to_datetime(df["data"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["data"])

    # Normaliza marca
    df["marca"] = df["marca"].astype(str).str.strip().str.upper()
    df["marca_norm"] = df["marca"].map(NORMALIZA_MARCA_VENDAS).fillna(df["marca"].str.title())

    # Converte numéricos
    df["qtde_venda"] = pd.to_numeric(df["qtde_venda"], errors="coerce").fillna(0)
    df["vl_total"]   = pd.to_numeric(df["vl_total"],   errors="coerce").fillna(0)

    # SKU como string padronizada
    df["sku"] = df["sku"].astype(str).str.strip().str.zfill(6)

    # Colunas de período
    df["ano"]  = df["data"].dt.year
    df["mes"]  = df["data"].dt.month
    df["ano_mes"] = df["data"].dt.to_period("M").astype(str)

    return df


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    st.title("❄️ Gestão de Compras — Ar Condicionado")

    # ── Sidebar: upload de arquivos ──────────────────────────
    with st.sidebar:
        st.header("📂 Arquivos")
        file_estoque = st.file_uploader("Estoque (.xlsx)", type=["xlsx", "xls"])
        file_vendas  = st.file_uploader("Vendas (.csv)",   type=["csv"])
        st.markdown("---")
        st.caption("Versão 2.0 · Inner AI")

    if not file_estoque or not file_vendas:
        st.info("⬅️ Faça o upload do Estoque (.xlsx) e do Vendas (.csv) para começar.")
        return

    with st.spinner("Carregando dados..."):
        df_estoque = carregar_estoque(file_estoque)
        df_vendas  = carregar_vendas(file_vendas)

    # ── Tabs principais ──────────────────────────────────────
    tab1, tab2, tab3 = st.tabs([
        "📦 Estoque & ABC",
        "📈 Vendas & Demanda",
        "🛒 Sugestão de Compras",
    ])

    # ════════════════════════════════════════════════════════
    # TAB 1 — ESTOQUE & ABC
    # ════════════════════════════════════════════════════════
    with tab1:
        st.subheader("📦 Estoque & ABC")

        # Filtros
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            fabricantes_disp = sorted(df_estoque["fabricante_nome"].unique())
            fab_sel = st.multiselect("Filtrar fabricante", fabricantes_disp, default=fabricantes_disp)
        with col_f2:
            abc_disp = sorted(df_estoque["abc"].dropna().astype(str).unique()) if "abc" in df_estoque.columns else []
            abc_sel  = st.multiselect("Curva ABC", abc_disp, default=abc_disp)
        with col_f3:
            mostrar_custo_zero = st.checkbox("Incluir itens com custo zero", value=True)

        df_est_filt = df_estoque[df_estoque["fabricante_nome"].isin(fab_sel)].copy()
        if abc_sel and "abc" in df_est_filt.columns:
            df_est_filt = df_est_filt[df_est_filt["abc"].astype(str).isin(abc_sel)]
        if not mostrar_custo_zero:
            df_est_filt = df_est_filt[~df_est_filt["flag_custo_zero"]]

        # KPIs
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("SKUs",            f"{df_est_filt['sku'].nunique():,}")
        k2.metric("Unidades totais", f"{df_est_filt['qtde_estoque'].sum():,.0f}")
        k3.metric("Valor de estoque",f"R$ {df_est_filt['custo_total'].sum():,.0f}")
        k4.metric("Itens custo zero",f"{df_est_filt['flag_custo_zero'].sum():,}")

        # Gráfico por fabricante
        resumo_fab = (
            df_est_filt.groupby("fabricante_nome")
            .agg(skus=("sku", "nunique"), unidades=("qtde_estoque", "sum"), valor=("custo_total", "sum"))
            .reset_index()
            .sort_values("valor", ascending=False)
        )

        fig_fab = px.bar(
            resumo_fab, x="fabricante_nome", y="valor",
            color="fabricante_nome",
            labels={"fabricante_nome": "Fabricante", "valor": "Valor (R$)"},
            title="Valor de estoque por fabricante",
            text_auto=".2s",
        )
        fig_fab.update_layout(showlegend=False)
        st.plotly_chart(fig_fab, use_container_width=True)

        # Tabela detalhada
        with st.expander("Ver tabela completa de estoque"):
            cols_show = [c for c in ["fabricante_nome", "sku", "descricao", "abc",
                                      "qtde_estoque", "custo_unitario", "custo_total", "flag_custo_zero"]
                         if c in df_est_filt.columns]
            st.dataframe(df_est_filt[cols_show].reset_index(drop=True), use_container_width=True)

        # Download
        st.download_button(
            "⬇️ Exportar estoque (CSV)",
            df_est_filt.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
            "estoque_base_app.csv",
            "text/csv",
        )

    # ════════════════════════════════════════════════════════
    # TAB 2 — VENDAS & DEMANDA
    # ════════════════════════════════════════════════════════
    with tab2:
        st.subheader("📈 Vendas & Demanda")

        # Filtros de período
        anos_disp = sorted(df_vendas["ano"].unique(), reverse=True)
        col_v1, col_v2, col_v3 = st.columns(3)

        with col_v1:
            ano_sel = st.selectbox("Ano", anos_disp, index=0)

        df_ano = df_vendas[df_vendas["ano"] == ano_sel]
        meses_ano    = sorted(df_ano["mes"].unique())
        meses_labels = [f"{m:02d}/{ano_sel}" for m in meses_ano]

        with col_v2:
            default_idx = meses_ano.index(3) if 3 in meses_ano else 0
            mes_label_sel = st.selectbox("Mês", meses_labels, index=default_idx)

        mes_sel = meses_ano[meses_labels.index(mes_label_sel)]

        with col_v3:
            marcas_disp = sorted(df_vendas["marca_norm"].unique())
            marcas_sel  = st.multiselect("Marcas", marcas_disp, default=marcas_disp)

        df_mes = df_ano[
            (df_ano["mes"] == mes_sel) &
            (df_ano["marca_norm"].isin(marcas_sel))
        ]

        # KPIs do mês
        k1, k2, k3 = st.columns(3)
        k1.metric("Faturamento do mês", f"R$ {df_mes['vl_total'].sum():,.0f}")
        k2.metric("Pedidos (linhas)",    f"{len(df_mes):,}")
        k3.metric("Qtde vendida",        f"{df_mes['qtde_venda'].sum():,.0f}")

        # Vendas por marca no mês
        venda_marca = (
            df_mes.groupby("marca_norm")["vl_total"]
            .sum()
            .reset_index()
            .sort_values("vl_total", ascending=False)
        )

        fig_marca = px.bar(
            venda_marca, x="marca_norm", y="vl_total",
            color="marca_norm",
            labels={"marca_norm": "Marca", "vl_total": "Faturamento (R$)"},
            title=f"Faturamento por marca — {mes_label_sel}",
            text_auto=".2s",
        )
        fig_marca.update_layout(showlegend=False)
        st.plotly_chart(fig_marca, use_container_width=True)

        # Evolução mensal do ano
        st.markdown("#### Evolução mensal do ano")
        evo_mensal = (
            df_ano[df_ano["marca_norm"].isin(marcas_sel)]
            .groupby(["mes", "marca_norm"])["vl_total"]
            .sum()
            .reset_index()
        )
        fig_evo = px.line(
            evo_mensal, x="mes", y="vl_total", color="marca_norm",
            labels={"mes": "Mês", "vl_total": "Faturamento (R$)", "marca_norm": "Marca"},
            title=f"Evolução mensal {ano_sel}",
            markers=True,
        )
        st.plotly_chart(fig_evo, use_container_width=True)

        # Tabela de SKUs mais vendidos no mês
        with st.expander("Ver SKUs mais vendidos no mês"):
            top_skus = (
                df_mes.groupby(["sku", "descricao", "marca_norm"])
                .agg(qtde=("qtde_venda", "sum"), valor=("vl_total", "sum"))
                .reset_index()
                .sort_values("valor", ascending=False)
                .head(50)
            )
            st.dataframe(top_skus.reset_index(drop=True), use_container_width=True)

        # Download
        st.download_button(
            "⬇️ Exportar vendas do mês (CSV)",
            df_mes.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
            f"vendas_{mes_label_sel.replace('/', '_')}.csv",
            "text/csv",
        )

    # ════════════════════════════════════════════════════════
    # TAB 3 — SUGESTÃO DE COMPRAS
    # ════════════════════════════════════════════════════════
    with tab3:
        st.subheader("🛒 Sugestão de Compras")

        # Parâmetros
        col_p1, col_p2, col_p3 = st.columns(3)
        with col_p1:
            meses_base = st.slider("Meses base para demanda média", 1, 12, 3)
        with col_p2:
            cobertura_meta = st.number_input("Cobertura desejada (dias)", value=COBERTURA_META_DIAS, step=5)
        with col_p3:
            lead_time = st.number_input("Lead time (dias)", value=LEAD_TIME_DIAS, step=5)

        # Demanda média mensal por SKU (últimos N meses disponíveis)
        datas_disp = df_vendas["ano_mes"].sort_values().unique()
        ultimos_meses = datas_disp[-meses_base:] if len(datas_disp) >= meses_base else datas_disp

        df_base = df_vendas[df_vendas["ano_mes"].isin(ultimos_meses)]
        demanda_sku = (
            df_base.groupby("sku")["qtde_venda"]
            .sum()
            .div(len(ultimos_meses))
            .reset_index()
            .rename(columns={"qtde_venda": "demanda_media_mensal"})
        )

        # Junta com estoque
        df_sug = df_estoque[["sku", "fabricante_nome", "descricao", "qtde_estoque", "custo_unitario", "custo_total", "flag_custo_zero"]].copy()
        df_sug = df_sug.merge(demanda_sku, on="sku", how="left")
        df_sug["demanda_media_mensal"] = df_sug["demanda_media_mensal"].fillna(0)

        # Demanda diária e cobertura atual
        df_sug["demanda_diaria"]     = df_sug["demanda_media_mensal"] / 30
        df_sug["cobertura_atual_dias"] = np.where(
            df_sug["demanda_diaria"] > 0,
            df_sug["qtde_estoque"] / df_sug["demanda_diaria"],
            np.inf,
        )

        # Estoque necessário para cobertura desejada + lead time
        df_sug["estoque_necessario"] = np.ceil(
            df_sug["demanda_diaria"] * (cobertura_meta + lead_time)
        )

        # Quantidade a comprar
        df_sug["qtde_comprar"] = np.maximum(
            0,
            df_sug["estoque_necessario"] - df_sug["qtde_estoque"]
        ).astype(int)

        # Valor estimado de compra
        df_sug["valor_estimado"] = df_sug["qtde_comprar"] * df_sug["custo_unitario"]

        # Filtros
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            fab_sug = st.multiselect(
                "Fabricante",
                sorted(df_sug["fabricante_nome"].unique()),
                default=sorted(df_sug["fabricante_nome"].unique()),
            )
        with col_s2:
            apenas_necessarios = st.checkbox("Mostrar apenas SKUs que precisam de compra", value=True)

        df_s = df_sug[df_sug["fabricante_nome"].isin(fab_sug)]
        if apenas_necessarios:
            df_s = df_s[df_s["qtde_comprar"] > 0]

        # KPIs
        k1, k2, k3 = st.columns(3)
        k1.metric("SKUs p/ comprar",      f"{(df_s['qtde_comprar'] > 0).sum():,}")
        k2.metric("Unidades p/ comprar",  f"{df_s['qtde_comprar'].sum():,.0f}")
        k3.metric("Valor est. compra",    f"R$ {df_s['valor_estimado'].sum():,.0f}")

        # Tabela
        cols_sug = [
            "fabricante_nome", "sku", "descricao",
            "qtde_estoque", "demanda_media_mensal",
            "cobertura_atual_dias", "estoque_necessario",
            "qtde_comprar", "custo_unitario", "valor_estimado",
            "flag_custo_zero",
        ]
        cols_sug = [c for c in cols_sug if c in df_s.columns]

        st.dataframe(
            df_s[cols_sug]
            .sort_values("valor_estimado", ascending=False)
            .reset_index(drop=True),
            use_container_width=True,
        )

        # Download
        st.download_button(
            "⬇️ Exportar sugestão de compras (CSV)",
            df_s[cols_sug].to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
            "sugestao_compras.csv",
            "text/csv",
        )


if __name__ == "__main__":
    main()
