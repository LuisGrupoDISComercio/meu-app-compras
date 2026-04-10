import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import io
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

MAPA_FABRICANTES_ESTOQUE = {
    2:  "LG",
    3:  "Samsung",
    4:  "Midea",
    5:  "Daikin",
    6:  "Agratto",
    7:  "Gree",
    10: "Trane",
    11: "TCL",
}

# ─────────────────────────────────────────────
# CARREGAR ESTOQUE
# ─────────────────────────────────────────────
def carregar_estoque(file_estoque) -> pd.DataFrame:
    file_estoque.seek(0)
    df = pd.read_excel(file_estoque, header=0)
    df = df.iloc[:, :8].copy()
    df.columns = [
        "fabr", "produto_id", "descricao", "classe_abc",
        "cubagem_un", "qtde", "custo_unit", "custo_total",
    ]

    df = df[~df["classe_abc"].astype(str).str.contains("TOTAL", na=False)]
    df = df[~df["descricao"].astype(str).str.contains("TOTAL", na=False)]

    for col in ["fabr", "produto_id", "qtde"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ["cubagem_un", "custo_unit", "custo_total"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["fabr", "produto_id", "qtde", "custo_total"])
    df["fabr"] = df["fabr"].astype(int)
    df = df[~df["fabr"].isin(FABRICANTES_IGNORAR)]
    df["fabricante"] = df["fabr"].map(MAPA_FABRICANTES_ESTOQUE).fillna("Outros")
    df = df.sort_values(["fabricante", "produto_id"])
    return df


# ─────────────────────────────────────────────
# CARREGAR VENDAS
# ─────────────────────────────────────────────
def carregar_vendas(file_vendas) -> pd.DataFrame:
    """
    Lê o Vendas.csv com estrutura real:
    Col 0: Emissao NF   → data_emissao  (dd/mm/aaaa)
    Col 1: Marca        → marca
    Col 2: Grupo        → grupo
    Col 3: BTU          → btu
    Col 4: Ciclo        → ciclo
    Col 5: Produto      → produto_id
    Col 6: Descricao    → descricao
    Col 7: Qtde         → qtde
    Col 8: VL Total     → vl_total
    """
    file_vendas.seek(0)
    raw = file_vendas.read()

    # Detecta encoding
    for enc in ("utf-8-sig", "latin-1", "cp1252", "utf-8"):
        try:
            texto = raw.decode(enc)
            break
        except Exception:
            continue
    else:
        texto = raw.decode("utf-8", errors="replace")

    buf = io.StringIO(texto)

    # Lê com separador ;, tudo como string, ignora linhas em branco
    df = pd.read_csv(
        buf,
        sep=";",
        dtype=str,
        skip_blank_lines=True,
        header=0,
    )

    # Remove colunas completamente vazias (colunas extras do CSV)
    df = df.dropna(axis=1, how="all")
    df.columns = [str(c).strip() for c in df.columns]

    # Valida que tem pelo menos 9 colunas
    if df.shape[1] < 9:
        raise ValueError(
            f"CSV tem apenas {df.shape[1]} colunas. "
            "Esperado: Emissao NF; Marca; Grupo; BTU; Ciclo; Produto; Descricao; Qtde; VL Total"
        )

    # Mapeia por POSIÇÃO — ignora nome real da coluna
    col_names = list(df.columns)
    df = df.rename(columns={
        col_names[0]: "data_emissao_raw",
        col_names[1]: "marca",
        col_names[2]: "grupo",
        col_names[3]: "btu",
        col_names[4]: "ciclo",
        col_names[5]: "produto_id",
        col_names[6]: "descricao",
        col_names[7]: "qtde",
        col_names[8]: "vl_total_raw",
    })

    # Mantém só as colunas que nos interessam
    df = df[[
        "data_emissao_raw", "marca", "grupo", "btu",
        "ciclo", "produto_id", "descricao", "qtde", "vl_total_raw"
    ]].copy()

    # ── Data ────────────────────────────────────────────────────────────
    # Filtra apenas linhas com data no formato dd/mm/aaaa
    df = df[
        df["data_emissao_raw"].astype(str).str.strip()
        .str.match(r"^\d{2}/\d{2}/\d{4}$", na=False)
    ].copy()

    df["data_emissao"] = pd.to_datetime(
        df["data_emissao_raw"].str.strip(),
        format="%d/%m/%Y",
        errors="coerce",
    )
    df = df.dropna(subset=["data_emissao"])

    # ── Quantidade ───────────────────────────────────────────────────────
    df["qtde"] = (
        df["qtde"]
        .astype(str)
        .str.strip()
        .str.replace(r"\s", "", regex=True)
        .pipe(lambda s: pd.to_numeric(s, errors="coerce"))
        .fillna(0.0)
    )

    # ── Valor total (R$ 10.862,00 ou 10862,00 ou 10.862) ────────────────
    def parse_valor(s):
        s = str(s).strip()
        s = re.sub(r"[R$\s]", "", s)       # remove R$, espaços
        s = s.replace(".", "").replace(",", ".")  # 10.862,00 → 10862.00
        try:
            return float(s)
        except Exception:
            return 0.0

    df["vl_total"] = df["vl_total_raw"].apply(parse_valor)

    # ── Produto ID ───────────────────────────────────────────────────────
    df["produto_id"] = (
        df["produto_id"]
        .astype(str)
        .str.strip()
        .str.extract(r"(\d+)", expand=False)
    )
    df["produto_id"] = pd.to_numeric(df["produto_id"], errors="coerce")

    # ── Marca (normaliza para maiúsculo) ─────────────────────────────────
    df["marca"] = df["marca"].astype(str).str.strip().str.upper()

    # ── Campos auxiliares ─────────────────────────────────────────────────
    df["grupo"]    = df["grupo"].astype(str).str.strip()
    df["btu"]      = pd.to_numeric(df["btu"], errors="coerce").fillna(0).astype(int)
    df["ciclo"]    = df["ciclo"].astype(str).str.strip()
    df["descricao"]= df["descricao"].astype(str).str.strip()

    # ── Resultado final ──────────────────────────────────────────────────
    df = df[[
        "data_emissao", "marca", "grupo", "btu",
        "ciclo", "produto_id", "descricao", "qtde", "vl_total"
    ]].sort_values("data_emissao").reset_index(drop=True)

    if df.empty:
        raise ValueError("Nenhuma linha válida encontrada no CSV de vendas após o tratamento.")

    return df


# ─────────────────────────────────────────────
# ABAS
# ─────────────────────────────────────────────
def aba_estoque(estoque_df: pd.DataFrame):
    st.header("📦 Estoque")
    st.write(f"Linhas carregadas: **{len(estoque_df):,}**")

    resumo = (
        estoque_df.groupby("fabricante", as_index=False)
        .agg(qtde_total=("qtde", "sum"), valor_total=("custo_total", "sum"))
        .sort_values("valor_total", ascending=False)
    )
    resumo["Valor (R$)"] = resumo["valor_total"].apply(lambda v: f"R$ {v:,.0f}")

    st.subheader("Resumo por fabricante")
    st.dataframe(
        resumo[["fabricante", "qtde_total", "Valor (R$)"]],
        use_container_width=True,
        hide_index=True,
    )

    fig = px.pie(
        resumo, names="fabricante", values="valor_total",
        title="Participação por valor em estoque", hole=0.4
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Detalhe completo")
    st.dataframe(estoque_df, use_container_width=True, height=500)


def aba_vendas(vendas_df: pd.DataFrame):
    st.header("📈 Vendas & Demanda")

    if vendas_df.empty:
        st.info("Carregue o arquivo de vendas.")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Registros", f"{len(vendas_df):,}")
    c2.metric(
        "Período",
        f"{vendas_df['data_emissao'].min().strftime('%d/%m/%Y')} → "
        f"{vendas_df['data_emissao'].max().strftime('%d/%m/%Y')}"
    )
    c3.metric("Valor total", f"R$ {vendas_df['vl_total'].sum():,.0f}")

    st.divider()

    # Vendas por marca
    por_marca = (
        vendas_df.groupby("marca", as_index=False)
        .agg(receita=("vl_total", "sum"), pecas=("qtde", "sum"))
        .sort_values("receita", ascending=False)
    )
    fig_m = px.bar(
        por_marca, x="marca", y="receita",
        title="Receita por marca", text_auto=".2s",
        labels={"marca": "Marca", "receita": "Receita (R$)"}
    )
    st.plotly_chart(fig_m, use_container_width=True)

    # Evolução mensal
    vendas_df2 = vendas_df.copy()
    vendas_df2["mes"] = vendas_df2["data_emissao"].dt.to_period("M").astype(str)
    mensal = (
        vendas_df2.groupby("mes", as_index=False)
        .agg(receita=("vl_total", "sum"))
    )
    fig_mes = px.line(
        mensal, x="mes", y="receita",
        markers=True, title="Evolução mensal de vendas",
        labels={"mes": "Mês", "receita": "Receita (R$)"}
    )
    st.plotly_chart(fig_mes, use_container_width=True)

    st.subheader("Detalhe de vendas")
    st.dataframe(vendas_df, use_container_width=True, height=400)


def aba_cobertura(estoque_df: pd.DataFrame, vendas_df: pd.DataFrame):
    st.header("📊 Cobertura de Estoque")

    if estoque_df.empty or vendas_df.empty:
        st.info("Carregue os dois arquivos para calcular a cobertura.")
        return

    # Demanda total por produto no período
    dias_periodo = max(
        (vendas_df["data_emissao"].max() - vendas_df["data_emissao"].min()).days, 1
    )
    demanda = (
        vendas_df.groupby("produto_id", as_index=False)["qtde"].sum()
        .rename(columns={"qtde": "qtde_vendida"})
    )
    demanda["demanda_dia"] = demanda["qtde_vendida"] / dias_periodo

    estoque_df2 = estoque_df.copy()
    estoque_df2["produto_id_num"] = pd.to_numeric(estoque_df2["produto_id"], errors="coerce")

    cob = estoque_df2.merge(
        demanda.rename(columns={"produto_id": "produto_id_num"}),
        on="produto_id_num", how="left"
    )
    cob["demanda_dia"]   = cob["demanda_dia"].fillna(0)
    cob["qtde_vendida"]  = cob["qtde_vendida"].fillna(0)
    cob["cobertura_dias"] = np.where(
        cob["demanda_dia"] > 0,
        cob["qtde"] / cob["demanda_dia"],
        np.inf
    )

    def status(d):
        if d == np.inf:  return "Sem giro"
        if d < 30:       return "🔴 Crítico"
        if d < 60:       return "🟡 Atenção"
        return "🟢 OK"

    cob["status"] = cob["cobertura_dias"].apply(status)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🔴 Crítico",  (cob["status"] == "🔴 Crítico").sum())
    c2.metric("🟡 Atenção",  (cob["status"] == "🟡 Atenção").sum())
    c3.metric("🟢 OK",       (cob["status"] == "🟢 OK").sum())
    c4.metric("⚪ Sem giro", (cob["status"] == "Sem giro").sum())

    st.divider()

    sel = st.multiselect(
        "Filtrar status",
        ["🔴 Crítico", "🟡 Atenção", "🟢 OK", "Sem giro"],
        default=["🔴 Crítico", "🟡 Atenção"]
    )
    cob_show = cob[cob["status"].isin(sel)].copy() if sel else cob.copy()
    cob_show["cobertura_fmt"] = cob_show["cobertura_dias"].apply(
        lambda x: "∞" if x == np.inf else f"{x:.0f} dias"
    )
    st.dataframe(
        cob_show[[
            "fabricante", "produto_id", "descricao",
            "qtde", "demanda_dia", "cobertura_fmt", "status"
        ]].sort_values("cobertura_dias"),
        use_container_width=True, height=450, hide_index=True
    )


def aba_sugestao(estoque_df: pd.DataFrame, vendas_df: pd.DataFrame):
    st.header("🛒 Sugestão de Compras")

    if estoque_df.empty or vendas_df.empty:
        st.info("Carregue os dois arquivos para gerar sugestões.")
        return

    dias_alvo = st.slider("Dias de cobertura alvo", 30, 180, 90)

    dias_periodo = max(
        (vendas_df["data_emissao"].max() - vendas_df["data_emissao"].min()).days, 1
    )
    demanda = (
        vendas_df.groupby("produto_id", as_index=False)["qtde"].sum()
        .rename(columns={"qtde": "qtde_vendida"})
    )
    demanda["demanda_dia"] = demanda["qtde_vendida"] / dias_periodo

    estoque_df2 = estoque_df.copy()
    estoque_df2["produto_id_num"] = pd.to_numeric(estoque_df2["produto_id"], errors="coerce")

    sug = estoque_df2.merge(
        demanda.rename(columns={"produto_id": "produto_id_num"}),
        on="produto_id_num", how="left"
    )
    sug["demanda_dia"]      = sug["demanda_dia"].fillna(0)
    sug["estoque_alvo"]     = sug["demanda_dia"] * dias_alvo
    sug["sugestao_compra"]  = (sug["estoque_alvo"] - sug["qtde"]).clip(lower=0).round(0)
    sug["valor_compra"]     = sug["sugestao_compra"] * sug["custo_unit"]

    sug = sug[sug["sugestao_compra"] > 0].sort_values("valor_compra", ascending=False)

    c1, c2 = st.columns(2)
    c1.metric("SKUs para comprar",    f"{len(sug):,}")
    c2.metric("Valor total sugerido", f"R$ {sug['valor_compra'].sum():,.0f}")

    st.dataframe(
        sug[[
            "fabricante", "produto_id", "descricao",
            "qtde", "demanda_dia", "estoque_alvo", "sugestao_compra", "valor_compra"
        ]].rename(columns={
            "fabricante":     "Fabricante",
            "produto_id":     "Produto",
            "descricao":      "Descrição",
            "qtde":           "Qtde Atual",
            "demanda_dia":    "Dem./dia",
            "estoque_alvo":   "Alvo",
            "sugestao_compra":"Sugestão",
            "valor_compra":   "Valor (R$)",
        }),
        use_container_width=True, height=450, hide_index=True
    )

    por_fab = (
        sug.groupby("fabricante", as_index=False)["valor_compra"].sum()
        .sort_values("valor_compra", ascending=False)
    )
    fig = px.bar(
        por_fab, x="fabricante", y="valor_compra",
        title="Sugestão de compras por fabricante",
        text_auto=".2s",
        labels={"fabricante": "Fabricante", "valor_compra": "Valor (R$)"}
    )
    st.plotly_chart(fig, use_container_width=True)


def aba_fornecedores(estoque_df: pd.DataFrame):
    st.header("🏭 Fornecedores")

    if estoque_df.empty:
        st.info("Carregue o arquivo de estoque.")
        return

    resumo = (
        estoque_df.groupby("fabricante", as_index=False)
        .agg(
            SKUs=("produto_id", "nunique"),
            Pecas=("qtde", "sum"),
            Valor=("custo_total", "sum"),
        )
        .sort_values("Valor", ascending=False)
    )
    resumo["Valor (R$)"] = resumo["Valor"].apply(lambda v: f"R$ {v:,.0f}")

    st.dataframe(
        resumo[["fabricante", "SKUs", "Pecas", "Valor (R$)"]],
        use_container_width=True, hide_index=True
    )

    fig = px.bar(
        resumo, x="fabricante", y="Valor",
        title="Valor em estoque por fabricante",
        text_auto=".2s",
        labels={"fabricante": "Fabricante", "Valor": "Valor (R$)"}
    )
    st.plotly_chart(fig, use_container_width=True)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    st.title("❄️ Motor de Compras — Ar Condicionado")

    with st.sidebar:
        st.header("📂 Arquivos")
        file_estoque = st.file_uploader("Estoque (.xlsx)", type=["xlsx"])
        file_vendas  = st.file_uploader("Vendas (.csv)",  type=["csv"])

    estoque_df = pd.DataFrame()
    vendas_df  = pd.DataFrame()

    if file_estoque:
        try:
            estoque_df = carregar_estoque(file_estoque)
            st.sidebar.success(f"Estoque: {len(estoque_df):,} linhas carregadas")
        except Exception as e:
            st.sidebar.error(f"Erro ao carregar estoque: {e}")

    if file_vendas:
        try:
            file_vendas.seek(0)
            vendas_df = carregar_vendas(file_vendas)
            st.sidebar.success(f"Vendas: {len(vendas_df):,} registros carregados")
        except Exception as e:
            st.sidebar.error(f"Erro ao carregar vendas: {e}")

    tabs = st.tabs([
        "📦 Estoque & ABC",
        "📈 Vendas & Demanda",
        "📊 Cobertura",
        "🛒 Sugestão de Compras",
        "🏭 Fornecedores",
    ])

    with tabs[0]:
        if not estoque_df.empty:
            aba_estoque(estoque_df)
        else:
            st.info("Carregue o arquivo de estoque.")

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
