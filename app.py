import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import re

st.set_page_config(
    page_title="Motor de Compras — Ar Condicionado",
    page_icon="❄️",
    layout="wide"
)

# ─────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────
FABRICANTES_IGNORAR = {900, 995, 998, 999}

MAPA_FABRICANTES = {
    2:  "LG",
    3:  "Samsung",
    4:  "Midea",
    5:  "Daikin",
    6:  "Agratto",
    7:  "Gree",
    10: "Trane",
    11: "TCL",
}

LOGOS = {
    "LG":      "images/LG_logo_2014svg.png",
    "Samsung": "images/Samsung_Logo.png",
    "Midea":   "images/Midea_Logo.jpg",
    "Daikin":  "images/daikin_logo.png",
    "Agratto": "images/aGRATTO_LOGO.jpg",
    "Gree":    "images/gree_LOGO.png",
    "Trane":   "images/pngtransparenttraneredhorizontallogo.png",
    "TCL":     "images/pngtransparenttclhdlogo.png",
}

# ─────────────────────────────────────────────
# CARREGAR ESTOQUE
# ─────────────────────────────────────────────
def carregar_estoque(file) -> pd.DataFrame:
    try:
        file.seek(0)
        df = pd.read_excel(file, header=0)

        # Pega só as 8 primeiras colunas por posição
        df = df.iloc[:, :8]
        df.columns = [
            "fabr", "produto", "descricao", "abc",
            "cubagem", "qtde", "custo_unit", "custo_total"
        ]

        # Remove linha TOTAL e linhas sem fabricante
        df = df[df["descricao"].astype(str).str.upper() != "TOTAL"]
        df = df.dropna(subset=["fabr"])

        # Converte fabricante para inteiro
        df["fabr"] = pd.to_numeric(df["fabr"], errors="coerce")
        df = df.dropna(subset=["fabr"])
        df["fabr"] = df["fabr"].astype(int)

        # Remove fabricantes ignorados (900, 995, 998, 999)
        df = df[~df["fabr"].isin(FABRICANTES_IGNORAR)]

        # Mapeia para nome do fornecedor
        df["fornecedor"] = df["fabr"].map(MAPA_FABRICANTES).fillna("Outros")

        # Converte numéricos
        df["produto"]     = pd.to_numeric(df["produto"],    errors="coerce")
        df["qtde"]        = pd.to_numeric(df["qtde"],       errors="coerce").fillna(0)
        df["custo_unit"]  = pd.to_numeric(df["custo_unit"], errors="coerce").fillna(0)
        df["custo_total"] = pd.to_numeric(df["custo_total"],errors="coerce").fillna(0)

        df = df.reset_index(drop=True)
        return df

    except Exception as e:
        st.sidebar.error(f"Erro ao carregar estoque: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────
# CARREGAR VENDAS
# ─────────────────────────────────────────────
def carregar_vendas(file) -> pd.DataFrame:
    try:
        file.seek(0)
        raw = file.read()

        # Detecta encoding
        for enc in ["utf-8-sig", "latin-1", "cp1252"]:
            try:
                texto = raw.decode(enc)
                break
            except Exception:
                continue

        linhas = texto.splitlines()

        # Filtra só linhas que começam com data dd/mm/aaaa
        padrao_data = re.compile(r"^\d{2}/\d{2}/\d{4}")
        linhas_dados = [l for l in linhas if padrao_data.match(l.strip())]

        if not linhas_dados:
            st.sidebar.error("Vendas: nenhuma linha com data encontrada.")
            return pd.DataFrame()

        registros = []
        for linha in linhas_dados:
            partes = linha.split(";")
            if len(partes) < 8:
                continue
            data_str  = partes[0].strip()
            marca     = partes[1].strip()
            grupo     = partes[2].strip()
            btu_str   = partes[3].strip()
            ciclo     = partes[4].strip()
            prod_str  = partes[5].strip()
            descricao = partes[6].strip()
            qtde_str  = partes[7].strip()
            valor_str = partes[8].strip() if len(partes) > 8 else "0"

            # Parse data
            try:
                data = pd.to_datetime(data_str, format="%d/%m/%Y")
            except Exception:
                continue

            # Parse numéricos
            try:
                produto_id = int(float(prod_str))
            except Exception:
                produto_id = None

            try:
                btu = int(float(btu_str))
            except Exception:
                btu = None

            try:
                qtde = float(qtde_str.replace(",", "."))
            except Exception:
                qtde = 0.0

            # Limpa valor: remove R$, pontos de milhar, troca vírgula por ponto
            valor_limpo = re.sub(r"[R$\s]", "", valor_str)
            valor_limpo = valor_limpo.replace(".", "").replace(",", ".")
            try:
                valor = float(valor_limpo)
            except Exception:
                valor = 0.0

            registros.append({
                "data_emissao": data,
                "marca":        marca,
                "grupo":        grupo,
                "btu":          btu,
                "ciclo":        ciclo,
                "produto_id":   produto_id,
                "descricao":    descricao,
                "qtde":         qtde,
                "valor":        valor,
            })

        df = pd.DataFrame(registros)
        return df

    except Exception as e:
        st.sidebar.error(f"Erro ao carregar vendas: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────
# ABA: ESTOQUE & ABC
# ─────────────────────────────────────────────
def aba_estoque(df: pd.DataFrame):
    st.header("📦 Estoque & ABC")

    if df.empty:
        st.info("Carregue o arquivo de estoque.")
        return

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total SKUs", f"{len(df):,}")
    col2.metric("Total Unidades", f"{df['qtde'].sum():,.0f}")
    col3.metric("Valor Total (R$)", f"R$ {df['custo_total'].sum():,.2f}")
    col4.metric("Fornecedores", df["fornecedor"].nunique())

    st.divider()

    # Tabela por fornecedor
    st.subheader("Estoque por Fornecedor")
    resumo = (
        df.groupby("fornecedor", as_index=False)
        .agg(
            SKUs=("produto", "count"),
            Unidades=("qtde", "sum"),
            Valor_Total=("custo_total", "sum"),
        )
        .sort_values("Valor_Total", ascending=False)
    )
    resumo["Valor_Total"] = resumo["Valor_Total"].apply(lambda x: f"R$ {x:,.2f}")
    st.dataframe(resumo, use_container_width=True)

    # Gráfico pizza
    fig = px.pie(
        df.groupby("fornecedor", as_index=False)["custo_total"].sum(),
        names="fornecedor",
        values="custo_total",
        title="Participação por Valor de Estoque",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Curva ABC
    st.subheader("Curva ABC")
    abc = (
        df.groupby("abc", as_index=False)["custo_total"]
        .sum()
        .sort_values("custo_total", ascending=False)
    )
    st.dataframe(abc, use_container_width=True)

    st.divider()
    st.subheader("Dados Completos")
    st.dataframe(df, use_container_width=True)


# ─────────────────────────────────────────────
# ABA: VENDAS & DEMANDA
# ─────────────────────────────────────────────
def aba_vendas(df: pd.DataFrame):
    st.header("📈 Vendas & Demanda")

    if df.empty:
        st.info("Carregue o arquivo de vendas.")
        return

    col1, col2, col3 = st.columns(3)
    col1.metric("Registros", f"{len(df):,}")
    col2.metric("Unidades Vendidas", f"{df['qtde'].sum():,.0f}")
    col3.metric("Receita Total (R$)", f"R$ {df['valor'].sum():,.2f}")

    st.divider()

    # Vendas por marca
    st.subheader("Vendas por Marca")
    por_marca = (
        df.groupby("marca", as_index=False)
        .agg(Unidades=("qtde", "sum"), Receita=("valor", "sum"))
        .sort_values("Receita", ascending=False)
    )
    st.dataframe(por_marca, use_container_width=True)

    fig = px.bar(por_marca, x="marca", y="Receita", title="Receita por Marca")
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Evolução mensal
    st.subheader("Evolução Mensal de Vendas")
    df["mes"] = df["data_emissao"].dt.to_period("M").astype(str)
    mensal = (
        df.groupby("mes", as_index=False)
        .agg(Unidades=("qtde", "sum"), Receita=("valor", "sum"))
    )
    fig2 = px.line(mensal, x="mes", y="Receita", title="Receita Mensal", markers=True)
    st.plotly_chart(fig2, use_container_width=True)


# ─────────────────────────────────────────────
# ABA: COBERTURA
# ─────────────────────────────────────────────
def aba_cobertura(estoque_df: pd.DataFrame, vendas_df: pd.DataFrame):
    st.header("🗓️ Cobertura de Estoque")

    if estoque_df.empty or vendas_df.empty:
        st.info("Carregue os dois arquivos para ver a cobertura.")
        return

    dias_cobertura_alvo = st.slider("Dias de cobertura alvo", 30, 180, 90)

    dias_periodo = max(
        (vendas_df["data_emissao"].max() - vendas_df["data_emissao"].min()).days, 1
    )

    demanda = (
        vendas_df.groupby("produto_id", as_index=False)
        .agg(total_vendido=("qtde", "sum"))
    )
    demanda["demanda_dia"] = demanda["total_vendido"] / dias_periodo

    cobertura = estoque_df.merge(
        demanda, left_on="produto_id" if "produto_id" in estoque_df.columns else "produto",
        right_on="produto_id", how="left"
    )

    # Ajuste: estoque usa coluna "produto"
    cobertura = estoque_df.copy()
    cobertura = cobertura.merge(demanda, left_on="produto", right_on="produto_id", how="left")
    cobertura["demanda_dia"] = cobertura["demanda_dia"].fillna(0)
    cobertura["cobertura_dias"] = cobertura.apply(
        lambda r: r["qtde"] / r["demanda_dia"] if r["demanda_dia"] > 0 else 9999, axis=1
    )
    cobertura["status"] = cobertura["cobertura_dias"].apply(
        lambda x: "🔴 Crítico" if x < 30
        else ("🟡 Atenção" if x < dias_cobertura_alvo else "🟢 OK")
    )

    st.dataframe(
        cobertura[["fornecedor", "produto", "descricao", "qtde",
                   "demanda_dia", "cobertura_dias", "status"]].sort_values("cobertura_dias"),
        use_container_width=True
    )

    criticos = cobertura[cobertura["status"] == "🔴 Crítico"]
    st.metric("Itens Críticos (< 30 dias)", len(criticos))


# ─────────────────────────────────────────────
# ABA: SUGESTÃO DE COMPRA
# ─────────────────────────────────────────────
def aba_sugestao(estoque_df: pd.DataFrame, vendas_df: pd.DataFrame):
    st.header("🛒 Sugestão de Compra")

    if estoque_df.empty or vendas_df.empty:
        st.info("Carregue os dois arquivos para gerar sugestões.")
        return

    dias_alvo = st.slider("Dias de cobertura desejada", 30, 180, 90, key="sugestao_slider")

    dias_periodo = max(
        (vendas_df["data_emissao"].max() - vendas_df["data_emissao"].min()).days, 1
    )

    demanda = (
        vendas_df.groupby("produto_id", as_index=False)
        .agg(total_vendido=("qtde", "sum"))
    )
    demanda["demanda_dia"] = demanda["total_vendido"] / dias_periodo

    sugestao = estoque_df.merge(demanda, left_on="produto", right_on="produto_id", how="left")
    sugestao["demanda_dia"] = sugestao["demanda_dia"].fillna(0)
    sugestao["estoque_alvo"] = sugestao["demanda_dia"] * dias_alvo
    sugestao["comprar"] = (sugestao["estoque_alvo"] - sugestao["qtde"]).clip(lower=0).round()
    sugestao["valor_compra"] = sugestao["comprar"] * sugestao["custo_unit"]

    sugestao_filtrada = sugestao[sugestao["comprar"] > 0].sort_values("valor_compra", ascending=False)

    st.metric("Itens a Comprar", len(sugestao_filtrada))
    st.metric(
        "Investimento Total Estimado",
        f"R$ {sugestao_filtrada['valor_compra'].sum():,.2f}"
    )

    st.dataframe(
        sugestao_filtrada[[
            "fornecedor", "produto", "descricao", "abc",
            "qtde", "demanda_dia", "estoque_alvo", "comprar", "valor_compra"
        ]],
        use_container_width=True
    )

    # Download
    csv = sugestao_filtrada.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")
    st.download_button(
        "📥 Baixar Sugestão de Compra (.csv)",
        data=csv,
        file_name="sugestao_compra.csv",
        mime="text/csv"
    )


# ─────────────────────────────────────────────
# ABA: FORNECEDORES
# ─────────────────────────────────────────────
def aba_fornecedores(estoque_df: pd.DataFrame):
    st.header("🏭 Fornecedores")

    if estoque_df.empty:
        st.info("Carregue o arquivo de estoque.")
        return

    fornecedores = sorted(estoque_df["fornecedor"].unique())

    for nome in fornecedores:
        with st.expander(f"📌 {nome}", expanded=False):
            col_logo, col_info = st.columns([1, 4])

            with col_logo:
                logo_path = LOGOS.get(nome)
                if logo_path:
                    try:
                        st.image(logo_path, width=120)
                    except Exception:
                        st.write(nome)

            with col_info:
                subset = estoque_df[estoque_df["fornecedor"] == nome]
                c1, c2, c3 = st.columns(3)
                c1.metric("SKUs", len(subset))
                c2.metric("Unidades", f"{subset['qtde'].sum():,.0f}")
                c3.metric("Valor", f"R$ {subset['custo_total'].sum():,.2f}")
                st.dataframe(
                    subset[["produto", "descricao", "abc", "qtde", "custo_unit", "custo_total"]],
                    use_container_width=True
                )


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    # Logo do grupo
    try:
        st.sidebar.image("images/DIS_NEW.jpg", use_container_width=True)
    except Exception:
        pass

    st.sidebar.title("Motor de Compras ❄️")
    st.sidebar.markdown("---")

    file_estoque = st.sidebar.file_uploader("📂 Estoque (.xlsx)", type=["xlsx"])
    file_vendas  = st.sidebar.file_uploader("📂 Vendas (.csv)",  type=["csv"])

    estoque_df = pd.DataFrame()
    vendas_df  = pd.DataFrame()

    if file_estoque:
        estoque_df = carregar_estoque(file_estoque)
        if not estoque_df.empty:
            st.sidebar.success(f"✅ Estoque: {len(estoque_df)} produtos carregados")
        else:
            st.sidebar.error("❌ Estoque: 0 produtos — verifique o arquivo")

    if file_vendas:
        vendas_df = carregar_vendas(file_vendas)
        if not vendas_df.empty:
            st.sidebar.success(f"✅ Vendas: {len(vendas_df):,} registros carregados")
        else:
            st.sidebar.error("❌ Vendas: 0 registros — verifique o arquivo")

    tabs = st.tabs([
        "📦 Estoque & ABC",
        "📈 Vendas & Demanda",
        "🗓️ Cobertura",
        "🛒 Sugestão de Compra",
        "🏭 Fornecedores",
    ])

    with tabs[0]:
        aba_estoque(estoque_df)
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
