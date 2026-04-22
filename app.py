import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

st.set_page_config(
    page_title="Motor de Compras — Ar Condicionado",
    page_icon="❄️",
    layout="wide",
)

# =========================================================
# CONSTANTES
# =========================================================
FABRICANTES_IGNORAR = {900, 995, 998, 999}

MAPA_FABRICANTES = {
    2: "LG",
    3: "Samsung",
    4: "Midea",
    5: "Daikin",
    6: "Agratto",
    7: "Gree",
    10: "Trane",
    11: "TCL",
}

# =========================================================
# UTILITÁRIOS
# =========================================================
def fmt_brl(valor):
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return "R$ 0,00"
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_qtde(valor):
    try:
        v = int(round(float(valor)))
    except (TypeError, ValueError):
        return "0"
    return f"{v:,}".replace(",", ".")


def colorir_curva(val):
    if pd.isna(val):
        return "background-color: #444; color: #fff;"
    v = str(val).upper()
    if v.startswith("A"):
        return "background-color: #22c55e; color: black;"  # verde
    if v.startswith("B"):
        return "background-color: #eab308; color: black;"  # amarelo
    if v.startswith("C"):
        return "background-color: #f97316; color: black;"  # laranja
    return "background-color: #6b7280; color: white;"      # cinza


# =========================================================
# CARREGAMENTO DE ESTOQUE
# =========================================================
def carregar_estoque(file):
    try:
        df = pd.read_excel(file)
    except Exception as e:
        st.error(f"Erro ao ler Excel de estoque: {e}")
        return pd.DataFrame()

    # Padronizar colunas
    df.columns = [str(c).strip() for c in df.columns]

    # Renomear para padrão interno
    rename_map = {
        "Fabr": "fabr",
        "Produto": "produto",
        "Descrição": "descricao",
        "ABC": "curva_sistema",
        "Cubagem (Un)": "cubagem",
        "Qtde": "qtde",
        "Custo Entrada Unitário Médio": "custo_unit_medio",
        "Custo Entrada Total": "vl_total",
    }
    df = df.rename(columns=rename_map)

    # Remover linha TOTAL (onde fabr e produto são NaN)
    if "fabr" in df.columns and "produto" in df.columns:
        df = df.dropna(subset=["fabr", "produto"], how="all")

    # Remover fabricantes ignorados
    if "fabr" in df.columns:
        df = df[~df["fabr"].isin(FABRICANTES_IGNORAR)]

    # Tipos
    for col in ["fabr", "produto"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    if "qtde" in df.columns:
        df["qtde"] = pd.to_numeric(df["qtde"], errors="coerce").fillna(0).astype(float)

    if "vl_total" in df.columns:
        df["vl_total"] = pd.to_numeric(df["vl_total"], errors="coerce").fillna(0.0)

    # Garantir textos
    for col in ["descricao", "curva_sistema"]:
        if col in df.columns:
            df[col] = df[col].astype(str)

    return df


# =========================================================
# CARREGAMENTO DE VENDAS
# =========================================================
def tentar_ler_csv(file, encoding):
    # Tenta detectar separador com base na primeira linha
    file.seek(0)
    primeira_linha = file.readline().decode(encoding, errors="ignore")
    sep = ";" if primeira_linha.count(";") > primeira_linha.count(",") else ","
    file.seek(0)
    return pd.read_csv(file, sep=sep, encoding=encoding)


def carregar_vendas(file):
    if file is None:
        return pd.DataFrame()

    # Tenta UTF-8; se falhar, tenta latin1
    try:
        df = tentar_ler_csv(file, "utf-8")
    except Exception:
        try:
            df = tentar_ler_csv(file, "latin1")
        except Exception as e2:
            st.error(f"Erro ao carregar vendas: {e2}")
            return pd.DataFrame()

    # Padronizar nomes de colunas
    df.columns = [str(c).strip().lower() for c in df.columns]

    # Tenta mapear colunas essenciais
    col_produto = None
    for c in df.columns:
        if "produto" in c or "codprod" in c or "sku" in c:
            col_produto = c
            break

    col_data = None
    for c in df.columns:
        if "data" in c or "dt_venda" in c or "emissao" in c:
            col_data = c
            break

    col_qtde = None
    for c in df.columns:
        if "qtde" in c or "quant" in c or "qtd" in c:
            col_qtde = c
            break

    if col_produto is None or col_data is None or col_qtde is None:
        st.error(
            "Não encontrei as colunas de produto, data e quantidade no CSV de vendas. "
            "Confira se o arquivo possui essas informações."
        )
        return pd.DataFrame()

    vendas = df[[col_produto, col_data, col_qtde]].copy()
    vendas = vendas.rename(
        columns={
            col_produto: "produto",
            col_data: "data",
            col_qtde: "qtde",
        }
    )

    vendas["produto"] = pd.to_numeric(vendas["produto"], errors="coerce").astype("Int64")
    vendas["qtde"] = pd.to_numeric(vendas["qtde"], errors="coerce").fillna(0.0)
    vendas["data"] = pd.to_datetime(vendas["data"], errors="coerce")

    vendas = vendas.dropna(subset=["produto", "data"])
    vendas = vendas[vendas["qtde"] > 0]

    return vendas


# =========================================================
# COBERTURA E DEMANDA
# =========================================================
def calcular_demanda_media_diaria(vendas_df):
    if vendas_df.empty:
        return pd.DataFrame(columns=["produto", "media_diaria"])

    # janela = do primeiro ao último dia de venda
    inicio = vendas_df["data"].min()
    fim = vendas_df["data"].max()
    dias = max((fim - inicio).days + 1, 1)

    demanda = (
        vendas_df.groupby("produto")["qtde"]
        .sum()
        .reset_index()
        .rename(columns={"qtde": "qtde_total"})
    )
    demanda["media_diaria"] = demanda["qtde_total"] / dias
    return demanda[["produto", "media_diaria"]]


def calcular_cobertura(estoque_df, vendas_df):
    if estoque_df.empty:
        return pd.DataFrame()

    demanda = calcular_demanda_media_diaria(vendas_df) if not vendas_df.empty else pd.DataFrame(columns=["produto", "media_diaria"])

    base = estoque_df.copy()
    base = base.merge(demanda, on="produto", how="left")

    base["media_diaria"] = base["media_diaria"].fillna(0.0)
    base["cobertura_dias"] = np.where(
        base["media_diaria"] > 0,
        base["qtde"] / base["media_diaria"],
        np.inf,
    )

    return base


# =========================================================
# ABAS
# =========================================================
def aba_estoque(estoque_df, vendas_df):
    st.subheader("Estoque & ABC")

    if estoque_df.empty:
        st.warning("Nenhum estoque carregado.")
        return

    skus = estoque_df["produto"].nunique()
    qtde_total = estoque_df["qtde"].sum()
    vl_total = estoque_df["vl_total"].sum()

    c1, c2, c3 = st.columns(3)
    c1.metric("SKUs em estoque", fmt_qtde(skus))
    c2.metric("Qtd total em estoque", fmt_qtde(qtde_total))
    c3.metric("Valor total em estoque", fmt_brl(vl_total))

    st.markdown("### Detalhe por produto")

    fabrs_disponiveis = sorted(estoque_df["fabr"].dropna().unique().tolist())
    fabrs_sel = st.multiselect(
        "Filtrar por fabricante (código):",
        fabrs_disponiveis,
        default=fabrs_disponiveis,
        key="filtro_fabr_estoque",
    )

    curvas_disponiveis = sorted(
        estoque_df["curva_sistema"].dropna().astype(str).unique().tolist()
    )
    curvas_sel = st.multiselect(
        "Filtrar por Curva Sistema:",
        curvas_disponiveis,
        default=curvas_disponiveis,
        key="filtro_curva_sistema",
    )

    df = estoque_df.copy()
    if fabrs_sel:
        df = df[df["fabr"].isin(fabrs_sel)]
    if curvas_sel:
        df = df[df["curva_sistema"].isin(curvas_sel)]

    df_exibir = df[
        [
            "fabr",
            "produto",
            "descricao",
            "curva_sistema",
            "qtde",
            "vl_total",
        ]
    ].copy()
    df_exibir = df_exibir.rename(
        columns={
            "descricao": "Descrição",
            "curva_sistema": "Curva Sistema",
            "qtde": "Qtde",
            "vl_total": "Custo Entrada Total",
        }
    )

    df_exibir["Custo Entrada Total"] = df_exibir["Custo Entrada Total"].apply(fmt_brl)

    st.dataframe(
        df_exibir.style.applymap(colorir_curva, subset=["Curva Sistema"]),
        use_container_width=True,
        height=600,
    )


def aba_vendas(vendas_df):
    st.subheader("Vendas & Demanda")

    if vendas_df.empty:
        st.info("Nenhum arquivo de vendas carregado ainda.")
        return

    st.write(f"Total de registros de vendas: **{fmt_qtde(len(vendas_df))}**")

    vendas_df["ano_mes"] = vendas_df["data"].dt.to_period("M").astype(str)
    mensal = (
        vendas_df.groupby("ano_mes")["qtde"]
        .sum()
        .reset_index()
        .rename(columns={"ano_mes": "Mês", "qtde": "Qtde Vendida"})
    )

    fig = px.bar(mensal, x="Mês", y="Qtde Vendida", title="Vendas Mensais (Qtde)")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Top 20 produtos mais vendidos")
    top = (
        vendas_df.groupby("produto")["qtde"]
        .sum()
        .reset_index()
        .rename(columns={"qtde": "Qtde Vendida"})
        .sort_values("Qtde Vendida", ascending=False)
        .head(20)
    )
    st.dataframe(top, use_container_width=True)


def aba_cobertura(estoque_df, vendas_df):
    st.subheader("Cobertura de Estoque (em dias)")

    if estoque_df.empty:
        st.warning("Carregue o estoque para ver a cobertura.")
        return

    base = calcular_cobertura(estoque_df, vendas_df)

    st.write(
        "Cobertura em dias = `Qtde em estoque / Média de vendas diárias`. "
        "Quando não há venda histórica, a cobertura aparece como ∞."
    )

    df = base[["fabr", "produto", "descricao", "curva_sistema", "qtde", "media_diaria", "cobertura_dias"]].copy()
    df = df.rename(
        columns={
            "descricao": "Descrição",
            "curva_sistema": "Curva Sistema",
            "qtde": "Qtde Estoque",
            "media_diaria": "Média Diária",
            "cobertura_dias": "Cobertura (dias)",
        }
    )
    st.dataframe(df, use_container_width=True)


def aba_sugestao(estoque_df, vendas_df):
    st.subheader("Sugestão de Compra")

    if estoque_df.empty:
        st.warning("Carregue o estoque para calcular sugestão de compra.")
        return

    if vendas_df.empty:
        st.info("Carregue o CSV de vendas para gerar sugestão baseada em demanda.")
        return

    dias_alvo = st.slider("Estoque alvo (dias)", min_value=7, max_value=120, value=30, step=1)

    base = calcular_cobertura(estoque_df, vendas_df)
    base["estoque_alvo_qtde"] = base["media_diaria"] * dias_alvo
    base["sugestao_qtde"] = np.maximum(base["estoque_alvo_qtde"] - base["qtde"], 0)
    base["sugestao_qtde"] = base["sugestao_qtde"].round(0)

    sug = base[base["sugestao_qtde"] > 0].copy()

    sug = sug.sort_values(
        by=["curva_sistema", "sugestao_qtde"],
        ascending=[True, False],
    )

    df = sug[
        [
            "fabr",
            "produto",
            "descricao",
            "curva_sistema",
            "qtde",
            "media_diaria",
            "cobertura_dias",
            "estoque_alvo_qtde",
            "sugestao_qtde",
        ]
    ].copy()

    df = df.rename(
        columns={
            "descricao": "Descrição",
            "curva_sistema": "Curva Sistema",
            "qtde": "Qtde Estoque",
            "media_diaria": "Média Diária",
            "cobertura_dias": "Cobertura (dias)",
            "estoque_alvo_qtde": f"Estoque alvo ({dias_alvo} dias)",
            "sugestao_qtde": "Sugestão de compra (Qtde)",
        }
    )

    st.dataframe(df, use_container_width=True)


def aba_fornecedores(estoque_df):
    st.subheader("Fornecedores")

    if estoque_df.empty:
        st.warning("Carregue o estoque para visualizar os fornecedores.")
        return

    df = estoque_df.copy()
    resumo = (
        df.groupby("fabr")
        .agg(
            skus=("produto", "nunique"),
            qtde_total=("qtde", "sum"),
            vl_total=("vl_total", "sum"),
        )
        .reset_index()
        .rename(columns={"fabr": "Fabricante"})
    )

    resumo["Fabricante Nome"] = resumo["Fabricante"].map(MAPA_FABRICANTES).fillna("Outros")
    resumo["Valor em Estoque"] = resumo["vl_total"].apply(fmt_brl)

    st.dataframe(
        resumo[["Fabricante", "Fabricante Nome", "skus", "qtde_total", "Valor em Estoque"]],
        use_container_width=True,
    )


# =========================================================
# APP
# =========================================================
def main():
    st.title("Motor de Compras — Ar Condicionado")

    st.sidebar.header("Arquivos")
    est_file = st.sidebar.file_uploader("Estoque (.xlsx)", type=["xlsx"], key="estoque")
    vnd_file = st.sidebar.file_uploader("Vendas (.csv)", type=["csv"], key="vendas")

    estoque_df = carregar_estoque(est_file) if est_file else pd.DataFrame()
    vendas_df = carregar_vendas(vnd_file) if vnd_file else pd.DataFrame()

    if not estoque_df.empty:
        st.sidebar.success(f"Estoque: {fmt_qtde(len(estoque_df))} produtos")
    else:
        st.sidebar.error("Estoque: 0 produtos")

    if not vendas_df.empty:
        st.sidebar.success(f"Vendas: {fmt_qtde(len(vendas_df))} registros")
    else:
        st.sidebar.error("Vendas: 0 registros")

    tabs = st.tabs(
        [
            "📦 Estoque & ABC",
            "📈 Vendas & Demanda",
            "📊 Cobertura",
            "🛒 Sugestão de Compra",
            "🏭 Fornecedores",
        ]
    )

    with tabs[0]:
        aba_estoque(estoque_df, vendas_df)
    with tabs[1]:
        aba_vendas(vendas_df)
    with tabs[2]:
        aba_cobertura(estoque_df, vendas_df)
    with tabs[3]:
        aba_sugestao(estoque_df, vendas_df)
    with tabs[4]:
        aba_fornecedores(estoque_df)


if __name__ == "__main__":
    main()
