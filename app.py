import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import re
from itertools import combinations
from collections import Counter

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

LOGOS = {
    "LG":      "images/LG_logo_2014svg.png",
    "Samsung": "images/Samsung_Logo.png",
    "Midea":   "images/Midea_Logo.jpg",
    "Daikin":  "images/daikin_logo.png",
    "Agratto": "images/aGRATTO_LOGO.jpg",
    "Gree":    "images/gree_LOGO.png",
    "Trane":   "images/pngtransparenttraneredhorizontallogo.png",
    "TCL":     "images/pngtransparenttclhdlogo.png",
    "Grupo":   "images/DIS_NEW.jpg",
}

# Paleta de cores ABC IA
COR_ABC = {
    "A+": {"bg": "#8B6914", "fg": "#FFFFFF"},  # ouro escuro, texto branco
    "A":  {"bg": "#FFD700", "fg": "#1a1a1a"},  # ouro claro, texto quase preto
    "B":  {"bg": "#FFA500", "fg": "#1a1a1a"},  # laranja, texto quase preto
    "C":  {"bg": "#FFE033", "fg": "#1a1a1a"},  # amarelo, texto quase preto
    "X":  {"bg": "#C0C0C0", "fg": "#1a1a1a"},  # cinza, texto quase preto
}

# ─────────────────────────────────────────────
# FUNÇÕES AUXILIARES DE FORMATAÇÃO
# ─────────────────────────────────────────────
def fmt_brl(valor: float) -> str:
    """Formata número como moeda brasileira: R$ 1.234.567,89"""
    try:
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"

def fmt_qtde(valor: float) -> str:
    """Formata quantidade sem casas decimais com separador de milhar"""
    try:
        return f"{valor:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "0"

# ─────────────────────────────────────────────
# CLASSIFICAÇÃO ABC IA
# ─────────────────────────────────────────────
def classificar_abc_ia(df_vendas: pd.DataFrame, col_produto: str,
                       col_valor: str, col_qtde: str) -> pd.DataFrame:
    """
    Retorna DataFrame com colunas:
      produto, classe_abc_IA_unid, classe_abc_IA_$
    Faixas:
      A+  → top 5% acumulado
      A   → até 20%
      B   → até 70%
      C   → até 95%
      X   → restante (sem venda ou abaixo de 95%)
    """
    if df_vendas.empty:
        return pd.DataFrame(columns=[col_produto, "classe_abc_IA_unid", "classe_abc_IA_$"])

    limites = {"A+": 0.05, "A": 0.20, "B": 0.70, "C": 0.95, "X": 1.01}

    def _abc_por(col_metrica):
        resumo = (
            df_vendas.groupby(col_produto, as_index=False)[col_metrica]
            .sum()
            .sort_values(col_metrica, ascending=False)
        )
        total = resumo[col_metrica].sum()
        if total == 0:
            resumo["classe"] = "X"
            return resumo[[col_produto, "classe"]]
        resumo["acum"] = resumo[col_metrica].cumsum() / total
        resumo["acum_anterior"] = resumo["acum"].shift(1, fill_value=0)

        def classifica(row):
            if row["acum_anterior"] < limites["A+"]:
                return "A+"
            elif row["acum_anterior"] < limites["A"]:
                return "A"
            elif row["acum_anterior"] < limites["B"]:
                return "B"
            elif row["acum_anterior"] < limites["C"]:
                return "C"
            else:
                return "X"

        resumo["classe"] = resumo.apply(classifica, axis=1)
        return resumo[[col_produto, "classe"]]

    por_unid = _abc_por(col_qtde).rename(columns={"classe": "classe_abc_IA_unid"})
    por_valor = _abc_por(col_valor).rename(columns={"classe": "classe_abc_IA_$"})

    resultado = por_unid.merge(por_valor, on=col_produto, how="outer")
    resultado["classe_abc_IA_unid"] = resultado["classe_abc_IA_unid"].fillna("X")
    resultado["classe_abc_IA_$"]    = resultado["classe_abc_IA_$"].fillna("X")

    return resultado

# ─────────────────────────────────────────────
# ANÁLISE DE KITS MSP
# ─────────────────────────────────────────────
def analisar_kits_msp(df_vendas: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    """
    Analisa os conjuntos (kits) mais vendidos de MSP agrupando por Pedido.
    Retorna DataFrame com: kit (frozenset → str), frequência, marcas.
    """
    msp = df_vendas[df_vendas["grupo"].str.upper() == "MSP"].copy()
    if msp.empty or "pedido" not in msp.columns:
        return pd.DataFrame()

    msp = msp[msp["pedido"].notna() & (msp["pedido"].astype(str).str.strip() != "")]

    kits = Counter()
    for pedido_id, grupo in msp.groupby("pedido"):
        produtos = tuple(sorted(grupo["produto_id"].dropna().astype(int).unique()))
        if len(produtos) >= 2:
            kits[produtos] += 1

    if not kits:
        return pd.DataFrame()

    rows = []
    for kit, freq in kits.most_common(top_n):
        # Pega descrições dos produtos do kit
        descricoes = (
            df_vendas[df_vendas["produto_id"].isin(kit)][["produto_id", "descricao"]]
            .drop_duplicates("produto_id")
            .set_index("produto_id")["descricao"]
            .to_dict()
        )
        desc_str = " | ".join([descricoes.get(p, str(p)) for p in kit])
        marca = ", ".join(
            df_vendas[df_vendas["produto_id"].isin(kit)]["marca"].unique()
        )
        rows.append({
            "Frequência": freq,
            "Qtde Produtos no Kit": len(kit),
            "Marca(s)": marca,
            "Produtos do Kit": desc_str,
        })

    return pd.DataFrame(rows)

# ─────────────────────────────────────────────
# CARGA DE ESTOQUE
# ─────────────────────────────────────────────
@st.cache_data
def carregar_estoque(file) -> pd.DataFrame:
    try:
        file.seek(0)
        df = pd.read_excel(file, header=0)

        # Remove coluna Unnamed: 0 (índice exportado pelo Excel)
        if "Unnamed: 0" in df.columns:
            df = df.drop(columns=["Unnamed: 0"])

        # Pega as 8 primeiras colunas por posição
        df = df.iloc[:, :8]
        df.columns = [
            "fabr",
            "produto",
            "descricao",
            "classe_abc",
            "cubagem",
            "qtde",
            "custo_unit",
            "custo_total",
        ]

        # Remove linhas totalmente vazias e linha TOTAL
        df = df.dropna(how="all")
        df = df[~df["descricao"].astype(str).str.upper().eq("TOTAL")]

        # Converte numéricos
        df["fabr"]      = pd.to_numeric(df["fabr"],      errors="coerce")
        df["produto"]   = pd.to_numeric(df["produto"],   errors="coerce")
        df["qtde"]      = pd.to_numeric(df["qtde"],      errors="coerce").fillna(0)
        df["cubagem"]   = pd.to_numeric(df["cubagem"],   errors="coerce").fillna(0)
        df["custo_unit"]= pd.to_numeric(df["custo_unit"],errors="coerce").fillna(0)
        df["custo_total"]= pd.to_numeric(df["custo_total"],errors="coerce").fillna(0)

        # Remove fabricantes ignorados
        df = df.dropna(subset=["fabr"])
        df["fabr"] = df["fabr"].astype(int)
        df = df[~df["fabr"].isin(FABRICANTES_IGNORAR)]

        # Converte produto para inteiro
        df = df.dropna(subset=["produto"])
        df["produto"] = df["produto"].astype(int)

        # Mapeia fabricante
        df["fabricante"] = df["fabr"].map(MAPA_FABRICANTES_ESTOQUE).fillna("Outros")

        return df.reset_index(drop=True)

    except Exception as e:
        st.sidebar.error(f"Erro ao carregar estoque: {e}")
        return pd.DataFrame()

# ─────────────────────────────────────────────
# CARGA DE VENDAS
# ─────────────────────────────────────────────
@st.cache_data
def carregar_vendas(file) -> pd.DataFrame:
    """
    Cabeçalho esperado (separador ;):
    Emissao NF ; Marca ; Grupo ; BTU ; Ciclo ; Produto ; Descricao ;
    Qtde ; VL Custo (Últ Entrada) ; VL Total

    OBS: a coluna Pedido pode aparecer ou não — o código detecta
    automaticamente pela presença do cabeçalho.
    """
    try:
        file.seek(0)
        conteudo = file.read()

        for enc in ["utf-8-sig", "latin-1", "cp1252"]:
            try:
                texto = conteudo.decode(enc)
                break
            except Exception:
                continue
        else:
            texto = conteudo.decode("latin-1", errors="replace")

        linhas = [l for l in texto.splitlines() if l.strip()]
        if not linhas:
            st.sidebar.error("Vendas: arquivo vazio.")
            return pd.DataFrame()

        # Detecta cabeçalho e posição das colunas
        cabecalho = [c.strip().lower() for c in linhas[0].split(";")]

        # Mapeamento flexível de posições
        pos = {}
        for i, c in enumerate(cabecalho):
            if re.search(r"emis|data", c):        pos["data"]     = i
            elif re.search(r"pedido|order", c):   pos["pedido"]   = i
            elif re.search(r"marca|brand", c):    pos["marca"]    = i
            elif re.search(r"grupo|group", c):    pos["grupo"]    = i
            elif re.search(r"btu", c):            pos["btu"]      = i
            elif re.search(r"ciclo", c):          pos["ciclo"]    = i
            elif re.search(r"^produto|^cod", c):  pos["produto"]  = i
            elif re.search(r"desc", c):           pos["descricao"]= i
            elif re.search(r"qtde|qty|quant", c): pos["qtde"]     = i
            elif re.search(r"custo|cust", c):     pos["custo"]    = i
            elif re.search(r"total|vl total", c): pos["valor"]    = i

        # Fallback: se não detectou cabeçalho, assume posições fixas sem pedido
        if "data" not in pos:
            pos = {
                "data": 0, "marca": 1, "grupo": 2, "btu": 3,
                "ciclo": 4, "produto": 5, "descricao": 6,
                "qtde": 7, "custo": 8, "valor": 9
            }
            inicio = 0
        else:
            inicio = 1  # pula o cabeçalho

        def extrair(partes, chave):
            i = pos.get(chave)
            if i is None or i >= len(partes):
                return ""
            return partes[i].strip()

        def limpar_valor(v):
            v = re.sub(r"[R$\s\u00a0]", "", str(v))
            v = v.replace(".", "").replace(",", ".")
            try:
                return float(v)
            except Exception:
                return 0.0

        registros = []
        padrao_data = re.compile(r"^\d{2}/\d{2}/\d{4}")

        for linha in linhas[inicio:]:
            partes = linha.split(";")
            data_str = extrair(partes, "data")
            if not padrao_data.match(data_str):
                continue
            try:
                data = pd.to_datetime(data_str, format="%d/%m/%Y", errors="coerce")
                if pd.isna(data):
                    continue

                pedido_raw = extrair(partes, "pedido")
                pedido     = pedido_raw if pedido_raw else None

                produto_raw = extrair(partes, "produto")
                produto_id  = int(float(produto_raw)) if produto_raw else None

                qtde_raw = extrair(partes, "qtde")
                qtde     = float(qtde_raw.replace(",", ".")) if qtde_raw else 0.0

                custo = limpar_valor(extrair(partes, "custo"))
                valor = limpar_valor(extrair(partes, "valor"))
                # Se não tem coluna de VL Total separada, usa custo como valor
                if valor == 0.0 and custo > 0:
                    valor = custo * qtde

                registros.append({
                    "data_emissao": data,
                    "pedido":       pedido,
                    "marca":        extrair(partes, "marca"),
                    "grupo":        extrair(partes, "grupo"),
                    "btu":          extrair(partes, "btu"),
                    "ciclo":        extrair(partes, "ciclo"),
                    "produto_id":   produto_id,
                    "descricao":    extrair(partes, "descricao"),
                    "qtde":         qtde,
                    "custo_unit":   custo,
                    "valor_total":  valor,
                })
            except Exception:
                continue

        if not registros:
            st.sidebar.error("Vendas: nenhum registro válido.")
            return pd.DataFrame()

        df = pd.DataFrame(registros)
        df["produto_id"] = pd.to_numeric(df["produto_id"], errors="coerce")
        df = df.dropna(subset=["produto_id"])
        df["produto_id"] = df["produto_id"].astype(int)

        return df.reset_index(drop=True)

    except Exception as e:
        st.sidebar.error(f"Erro ao carregar vendas: {e}")
        return pd.DataFrame()

# ─────────────────────────────────────────────
# ABA: ESTOQUE & ABC
# ─────────────────────────────────────────────
def aba_estoque(estoque_df: pd.DataFrame, vendas_df: pd.DataFrame):
    st.header("📦 Estoque & ABC")

    if estoque_df.empty:
        st.warning("Carregue o arquivo de estoque para ver esta aba.")
        return

    # ── Filtro de período para ABC IA ─────────────────────────────────
    st.subheader("⚙️ Parâmetros de Análise")

    col_f1, col_f2, col_f3 = st.columns([2, 2, 2])

    if not vendas_df.empty:
        data_min = vendas_df["data_emissao"].min().date()
        data_max = vendas_df["data_emissao"].max().date()
    else:
        data_min = pd.Timestamp("2025-01-01").date()
        data_max = pd.Timestamp.today().date()

    with col_f1:
        dt_inicio = st.date_input("De", value=data_min, min_value=data_min, max_value=data_max, key="abc_dt_ini")
    with col_f2:
        dt_fim    = st.date_input("Até", value=data_max, min_value=data_min, max_value=data_max, key="abc_dt_fim")
    with col_f3:
        fab_opcoes = ["Todos"] + sorted(estoque_df["fabricante"].unique().tolist())
        fab_sel    = st.selectbox("Fabricante", fab_opcoes, key="abc_fab")

    # ── KPIs ──────────────────────────────────────────────────────────
    st.divider()
    df_view = estoque_df.copy()
    if fab_sel != "Todos":
        df_view = df_view[df_view["fabricante"] == fab_sel]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("SKUs no Estoque",      fmt_qtde(len(df_view)))
    c2.metric("Total de Unidades",    fmt_qtde(df_view["qtde"].sum()))
    c3.metric("Valor Total (Custo)",  fmt_brl(df_view["custo_total"].sum()))
    c4.metric("Fabricantes Ativos",   str(df_view["fabricante"].nunique()))

    # ── Calcula ABC IA ─────────────────────────────────────────────────
    abc_ia = pd.DataFrame(columns=["produto_id", "classe_abc_IA_unid", "classe_abc_IA_$"])

    if not vendas_df.empty:
        vendas_periodo = vendas_df[
            (vendas_df["data_emissao"].dt.date >= dt_inicio) &
            (vendas_df["data_emissao"].dt.date <= dt_fim)
        ].copy()
        abc_ia = classificar_abc_ia(
            vendas_periodo,
            col_produto="produto_id",
            col_valor="valor_total",
            col_qtde="qtde"
        )

    # Junta ABC IA no estoque
    df_view = df_view.merge(
        abc_ia, left_on="produto", right_on="produto_id", how="left"
    )
    df_view["classe_abc_IA_unid"] = df_view["classe_abc_IA_unid"].fillna("X")
    df_view["classe_abc_IA_$"]    = df_view["classe_abc_IA_$"].fillna("X")

    # ── Tabela principal com cores ─────────────────────────────────────
    st.divider()
    st.subheader("📋 Tabela de Estoque")

    # Colunas a exibir (reordena)
    colunas_exib = [
        "fabricante", "produto", "descricao",
        "classe_abc",
        "classe_abc_IA_unid",
        "classe_abc_IA_$",
        "qtde", "custo_unit", "custo_total",
    ]
    tabela = df_view[colunas_exib].copy()

    # Formatação financeira
    tabela["custo_unit"]  = tabela["custo_unit"].apply(fmt_brl)
    tabela["custo_total"] = tabela["custo_total"].apply(fmt_brl)
    tabela["qtde"]        = tabela["qtde"].apply(fmt_qtde)

    # Renomeia para exibição
    tabela = tabela.rename(columns={
        "fabricante":        "Fabricante",
        "produto":           "Código",
        "descricao":         "Descrição",
        "classe_abc":        "ABC (Sistema)",
        "classe_abc_IA_unid":"ABC IA (Unid)",
        "classe_abc_IA_$":   "ABC IA (R$)",
        "qtde":              "Qtde",
        "custo_unit":        "Custo Unit.",
        "custo_total":       "Custo Total",
    })

    def colorir_abc(val):
        info = COR_ABC.get(str(val), {"bg": "transparent", "fg": "#000000"})
        return f"background-color:{info['bg']};color:{info['fg']};font-weight:600;text-align:center;"

    styled = (
        tabela.style
        .applymap(colorir_abc, subset=["ABC IA (Unid)", "ABC IA (R$)"])
    )

    st.dataframe(styled, use_container_width=True, height=500)

    # ── Distribuição das curvas ────────────────────────────────────────
    st.divider()
    st.subheader("📊 Distribuição das Curvas ABC IA")

    col_g1, col_g2 = st.columns(2)

    with col_g1:
        dist_unid = (
            df_view.groupby("classe_abc_IA_unid", as_index=False)
            .agg(SKUs=("produto", "count"), Unidades=("qtde", "sum"))
            .sort_values("SKUs", ascending=False)
        )
        ordem_abc = ["A+", "A", "B", "C", "X"]
        cores_abc = [COR_ABC.get(c, {"bg": "#999"})["bg"] for c in ordem_abc]
        dist_unid["classe_abc_IA_unid"] = pd.Categorical(
            dist_unid["classe_abc_IA_unid"], categories=ordem_abc, ordered=True
        )
        dist_unid = dist_unid.sort_values("classe_abc_IA_unid")

        fig_unid = px.bar(
            dist_unid, x="classe_abc_IA_unid", y="SKUs",
            title="Por Volume de Unidades Vendidas",
            color="classe_abc_IA_unid",
            color_discrete_sequence=cores_abc,
            text="SKUs",
        )
        fig_unid.update_layout(showlegend=False)
        st.plotly_chart(fig_unid, use_container_width=True)

    with col_g2:
        dist_valor = (
            df_view.groupby("classe_abc_IA_$", as_index=False)
            .agg(SKUs=("produto", "count"))
            .sort_values("SKUs", ascending=False)
        )
        dist_valor["classe_abc_IA_$"] = pd.Categorical(
            dist_valor["classe_abc_IA_$"], categories=ordem_abc, ordered=True
        )
        dist_valor = dist_valor.sort_values("classe_abc_IA_$")

        fig_valor = px.bar(
            dist_valor, x="classe_abc_IA_$", y="SKUs",
            title="Por Valor Vendido (R$)",
            color="classe_abc_IA_$",
            color_discrete_sequence=cores_abc,
            text="SKUs",
        )
        fig_valor.update_layout(showlegend=False)
        st.plotly_chart(fig_valor, use_container_width=True)

    # ── Kits MSP ──────────────────────────────────────────────────────
    if not vendas_df.empty:
        st.divider()
        st.subheader("🔧 Kits MSP mais Vendidos (por Pedido)")

        kits_df = analisar_kits_msp(
            vendas_df[
                (vendas_df["data_emissao"].dt.date >= dt_inicio) &
                (vendas_df["data_emissao"].dt.date <= dt_fim)
            ],
            top_n=20
        )

        if kits_df.empty:
            if "pedido" not in vendas_df.columns or vendas_df["pedido"].isna().all():
                st.info("Coluna 'Pedido' não encontrada no CSV de vendas — adicione-a para habilitar a análise de kits MSP.")
            else:
                st.info("Nenhum kit MSP identificado no período selecionado.")
        else:
            st.dataframe(kits_df, use_container_width=True, height=400)


# ─────────────────────────────────────────────
# ABA: VENDAS & DEMANDA
# ─────────────────────────────────────────────
def aba_vendas(df: pd.DataFrame):
    st.header("📈 Vendas & Demanda")

    if df.empty:
        st.warning("Carregue o arquivo de vendas.")
        return

    col1, col2, col3 = st.columns(3)
    col1.metric("Registros", fmt_qtde(len(df)))
    col2.metric("Unidades Vendidas", fmt_qtde(df["qtde"].sum()))
    col3.metric("Faturamento Total", fmt_brl(df["valor_total"].sum()))

    st.divider()

    # Vendas por marca
    st.subheader("Vendas por Marca")
    por_marca = (
        df.groupby("marca", as_index=False)
        .agg(Unidades=("qtde", "sum"), Faturamento=("valor_total", "sum"))
        .sort_values("Faturamento", ascending=False)
    )
    fig = px.bar(por_marca, x="marca", y="Faturamento",
                 title="Faturamento por Marca (R$)", text_auto=".2s")
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Evolução mensal
    st.subheader("Evolução Mensal")
    df_m = df.copy()
    df_m["mes"] = df_m["data_emissao"].dt.to_period("M").astype(str)
    mensal = (
        df_m.groupby("mes", as_index=False)
        .agg(Unidades=("qtde", "sum"), Faturamento=("valor_total", "sum"))
        .sort_values("mes")
    )
    fig2 = px.line(mensal, x="mes", y="Faturamento",
                   title="Faturamento Mensal (R$)", markers=True)
    st.plotly_chart(fig2, use_container_width=True)

    st.divider()

    marcas_disp = ["Todas"] + sorted(df["marca"].dropna().unique().tolist())
    marca_sel = st.selectbox("Filtrar por marca", marcas_disp, key="vendas_marca")
    df_view = df if marca_sel == "Todas" else df[df["marca"] == marca_sel]
    st.dataframe(
        df_view[["data_emissao", "marca", "grupo", "produto_id",
                 "descricao", "qtde", "valor_total"]]
        .sort_values("data_emissao", ascending=False),
        use_container_width=True,
    )


# ─────────────────────────────────────────────
# ABA: COBERTURA
# ─────────────────────────────────────────────
def aba_cobertura(estoque_df: pd.DataFrame, vendas_df: pd.DataFrame):
    st.header("📊 Cobertura de Estoque")

    if estoque_df.empty or vendas_df.empty:
        st.warning("Carregue estoque e vendas para ver a cobertura.")
        return

    dias = max(
        (vendas_df["data_emissao"].max() - vendas_df["data_emissao"].min()).days, 1
    )
    demanda = (
        vendas_df.groupby("produto_id", as_index=False)
        .agg(total_vendido=("qtde", "sum"))
    )
    demanda["demanda_diaria"] = demanda["total_vendido"] / dias

    cobertura = estoque_df.merge(
        demanda, left_on="produto", right_on="produto_id", how="left"
    )
    cobertura["demanda_diaria"] = cobertura["demanda_diaria"].fillna(0)
    cobertura["cobertura_dias"] = np.where(
        cobertura["demanda_diaria"] > 0,
        cobertura["qtde"] / cobertura["demanda_diaria"],
        np.inf
    )

    alvo = st.slider("Dias de cobertura alvo", 30, 180, 90, key="cob_slider")

    critico = cobertura[cobertura["cobertura_dias"] < alvo].sort_values("cobertura_dias")
    st.metric("Produtos abaixo da cobertura alvo", len(critico))

    st.dataframe(
        critico[["fabricante", "produto", "descricao",
                 "qtde", "demanda_diaria", "cobertura_dias"]]
        .rename(columns={
            "fabricante":    "Fabricante",
            "produto":       "Código",
            "descricao":     "Descrição",
            "qtde":          "Estoque Atual",
            "demanda_diaria":"Demanda/Dia",
            "cobertura_dias":"Cobertura (dias)",
        }),
        use_container_width=True,
    )


# ─────────────────────────────────────────────
# ABA: SUGESTÃO DE COMPRA
# ─────────────────────────────────────────────
def aba_sugestao(estoque_df: pd.DataFrame, vendas_df: pd.DataFrame):
    st.header("🛒 Sugestão de Compra")

    if estoque_df.empty or vendas_df.empty:
        st.warning("Carregue estoque e vendas para gerar sugestões.")
        return

    dias_alvo = st.slider("Dias de cobertura desejada", 30, 180, 90, key="sug_slider")

    dias = max(
        (vendas_df["data_emissao"].max() - vendas_df["data_emissao"].min()).days, 1
    )
    demanda = (
        vendas_df.groupby("produto_id", as_index=False)
        .agg(total_vendido=("qtde", "sum"))
    )
    demanda["demanda_diaria"] = demanda["total_vendido"] / dias

    sug = estoque_df.merge(
        demanda, left_on="produto", right_on="produto_id", how="left"
    )
    sug["demanda_diaria"]   = sug["demanda_diaria"].fillna(0)
    sug["estoque_alvo"]     = sug["demanda_diaria"] * dias_alvo
    sug["sugestao_compra"]  = (sug["estoque_alvo"] - sug["qtde"]).clip(lower=0).round(0)
    sug["valor_sugestao"]   = sug["sugestao_compra"] * sug["custo_unit"]

    sug_view = sug[sug["sugestao_compra"] > 0].sort_values("valor_sugestao", ascending=False)

    col1, col2 = st.columns(2)
    col1.metric("Produtos a Comprar", fmt_qtde(len(sug_view)))
    col2.metric("Investimento Total Estimado", fmt_brl(sug_view["valor_sugestao"].sum()))

    fabs = ["Todos"] + sorted(sug_view["fabricante"].unique().tolist())
    fab_sel = st.selectbox("Filtrar por fabricante", fabs, key="sug_fab")
    if fab_sel != "Todos":
        sug_view = sug_view[sug_view["fabricante"] == fab_sel]

    sug_view_fmt = sug_view[[
        "fabricante", "produto", "descricao", "classe_abc",
        "qtde", "demanda_diaria", "estoque_alvo", "sugestao_compra",
        "custo_unit", "valor_sugestao"
    ]].copy()

    sug_view_fmt["custo_unit"]    = sug_view_fmt["custo_unit"].apply(fmt_brl)
    sug_view_fmt["valor_sugestao"]= sug_view_fmt["valor_sugestao"].apply(fmt_brl)
    sug_view_fmt["qtde"]          = sug_view_fmt["qtde"].apply(fmt_qtde)

    st.dataframe(sug_view_fmt.rename(columns={
        "fabricante":     "Fabricante",
        "produto":        "Código",
        "descricao":      "Descrição",
        "classe_abc":     "ABC",
        "qtde":           "Estoque Atual",
        "demanda_diaria": "Demanda/Dia",
        "estoque_alvo":   "Estoque Alvo",
        "sugestao_compra":"Qtde Sugerida",
        "custo_unit":     "Custo Unit.",
        "valor_sugestao": "Valor Sugerido",
    }), use_container_width=True)

    csv = sug_view.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")
    st.download_button("📥 Baixar Sugestão (.csv)", data=csv,
                       file_name="sugestao_compra.csv", mime="text/csv")


# ─────────────────────────────────────────────
# ABA: FORNECEDORES
# ─────────────────────────────────────────────
def aba_fornecedores(estoque_df: pd.DataFrame):
    st.header("🏭 Fornecedores")

    if estoque_df.empty:
        st.warning("Carregue o arquivo de estoque.")
        return

    fabricantes = sorted(estoque_df["fabricante"].unique().tolist())

    for fab in fabricantes:
        with st.expander(fab, expanded=False):
            col_logo, col_info = st.columns([1, 5])

            with col_logo:
                logo = LOGOS.get(fab)
                if logo:
                    try:
                        st.image(logo, width=130)
                    except Exception:
                        st.caption(fab)

            with col_info:
                df_fab = estoque_df[estoque_df["fabricante"] == fab]
                c1, c2, c3 = st.columns(3)
                c1.metric("SKUs",          fmt_qtde(len(df_fab)))
                c2.metric("Unidades",      fmt_qtde(df_fab["qtde"].sum()))
                c3.metric("Valor Estoque", fmt_brl(df_fab["custo_total"].sum()))

                df_fab_fmt = df_fab[["produto", "descricao", "classe_abc",
                                     "qtde", "custo_unit", "custo_total"]].copy()
                df_fab_fmt["custo_unit"]  = df_fab_fmt["custo_unit"].apply(fmt_brl)
                df_fab_fmt["custo_total"] = df_fab_fmt["custo_total"].apply(fmt_brl)
                df_fab_fmt["qtde"]        = df_fab_fmt["qtde"].apply(fmt_qtde)

                st.dataframe(df_fab_fmt.rename(columns={
                    "produto":    "Código",
                    "descricao":  "Descrição",
                    "classe_abc": "ABC",
                    "qtde":       "Qtde",
                    "custo_unit": "Custo Unit.",
                    "custo_total":"Custo Total",
                }).sort_values("Custo Total", ascending=False),
                use_container_width=True)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    try:
        st.sidebar.image(LOGOS["Grupo"], use_container_width=True)
    except Exception:
        st.sidebar.title("Motor de Compras ❄️")

    st.sidebar.markdown("### 📂 Arquivos de Dados")

    estoque_file = st.sidebar.file_uploader("Estoque (.xlsx)", type=["xlsx"])
    vendas_file  = st.sidebar.file_uploader("Vendas (.csv)",  type=["csv"])

    estoque_df = pd.DataFrame()
    vendas_df  = pd.DataFrame()

    if estoque_file is not None:
        estoque_df = carregar_estoque(estoque_file)
        if not estoque_df.empty:
            st.sidebar.success(f"✅ Estoque: {len(estoque_df)} produtos carregados")
        else:
            st.sidebar.error("❌ Estoque: 0 produtos — verifique o arquivo")

    if vendas_file is not None:
        vendas_df = carregar_vendas(vendas_file)
        if not vendas_df.empty:
            st.sidebar.success(f"✅ Vendas: {fmt_qtde(len(vendas_df))} registros carregados")
        else:
            st.sidebar.error("❌ Vendas: 0 registros — verifique o arquivo")

    tabs = st.tabs([
        "📦 Estoque & ABC",
        "📈 Vendas & Demanda",
        "📊 Cobertura",
        "🛒 Sugestão de Compra",
        "🏭 Fornecedores",
    ])

    with tabs[0]: aba_estoque(estoque_df, vendas_df)
    with tabs[1]: aba_vendas(vendas_df)
    with tabs[2]: aba_cobertura(estoque_df, vendas_df)
    with tabs[3]: aba_sugestao(estoque_df, vendas_df)
    with tabs[4]: aba_fornecedores(estoque_df)


if __name__ == "__main__":
    main()
