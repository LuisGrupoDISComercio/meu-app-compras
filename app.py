import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

st.set_page_config(
    page_title="Motor de Compras — Ar Condicionado",
    page_icon="❄️",
    layout="wide",
)

# ─────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────
FABRICANTES_IGNORAR = {900, 995, 998, 999}

MAPA_FABRICANTES_ESTOQUE = {
    2: "LG",
    3: "Samsung",
    4: "Midea",
    5: "Daikin",
    6: "Agratto",
    7: "Gree",
    10: "Trane",
    11: "TCL",
}

LOGOS = {
    "LG": "images/LG_logo_2014svg.png",
    "Samsung": "images/Samsung_Logo.png",
    "Midea": "images/Midea_Logo.jpg",
    "Daikin": "images/daikin_logo.png",
    "Agratto": "images/aGRATTO_LOGO.jpg",
    "Gree": "images/gree_LOGO.png",
    "Trane": "images/pngtransparenttraneredhorizontallogo.png",
    "TCL": "images/TCL_logo.png",
    "Grupo": "images/DIS_NEW.jpg",
}

COR_ABC = {
    "A+": {"bg": "#8B6914", "fg": "#FFFFFF"},
    "A":  {"bg": "#FFD700", "fg": "#1a1a1a"},
    "B":  {"bg": "#FFA500", "fg": "#1a1a1a"},
    "C":  {"bg": "#FFFF99", "fg": "#1a1a1a"},
    "X":  {"bg": "#D3D3D3", "fg": "#1a1a1a"},
}


# ─────────────────────────────────────────────
# UTILITÁRIOS
# ─────────────────────────────────────────────
def fmt_brl(valor):
    try:
        v = float(valor)
        inteiro = int(v)
        decimal = round((v - inteiro) * 100)
        inteiro_fmt = f"{inteiro:,}".replace(",", ".")
        return f"R$ {inteiro_fmt},{decimal:02d}"
    except Exception:
        return str(valor)


def fmt_qtde(valor):
    try:
        return f"{int(float(valor)):,}".replace(",", ".")
    except Exception:
        return str(valor)


def colorir_abc(classe):
    if pd.isna(classe):
        return ""
    info = COR_ABC.get(str(classe).strip(), COR_ABC["X"])
    return (
        f"background-color: {info['bg']}; "
        f"color: {info['fg']}; "
        f"font-weight: bold; "
        f"text-align: center;"
    )


# ─────────────────────────────────────────────
# CARREGAMENTO DE ESTOQUE
# ─────────────────────────────────────────────
@st.cache_data
def carregar_estoque(file_obj):
    try:
        xls = pd.ExcelFile(file_obj)
        aba = xls.sheet_names[0]
        df_raw = xls.parse(aba, header=None)

        # Localiza linha de cabeçalho
        header_row = None
        for i, row in df_raw.iterrows():
            vals = row.astype(str).str.lower().tolist()
            if any("produto" in v for v in vals):
                header_row = i
                break

        if header_row is None:
            st.error("Estoque: coluna 'Produto' não encontrada.")
            return pd.DataFrame()

        df = xls.parse(aba, header=header_row)
        df.columns = df.columns.astype(str).str.strip()
        df = df.dropna(axis=1, how="all")
        df = df.dropna(subset=[df.columns[0]])

        # Mapeia colunas
        rename_map = {}
        for col in df.columns:
            lo = col.lower().strip()
            if lo == "produto":
                rename_map[col] = "produto"
            elif "descr" in lo:
                rename_map[col] = "descricao"
            elif lo == "grupo":
                rename_map[col] = "grupo"
            elif lo == "btu":
                rename_map[col] = "btu"
            elif lo == "ciclo":
                rename_map[col] = "ciclo"
            elif lo in ("qtde", "qtd", "quantidade"):
                rename_map[col] = "qtde"
            elif "vl custo" in lo or ("custo" in lo and "ult" in lo):
                rename_map[col] = "vl_custo"
            elif "vl total" in lo or "valor total" in lo:
                rename_map[col] = "vl_total"
            elif "marca" in lo or "fabricante" in lo:
                rename_map[col] = "marca"

        df = df.rename(columns=rename_map)

        # Numéricos
        for c in ["qtde", "vl_custo", "vl_total"]:
            if c in df.columns:
                df[c] = (
                    df[c]
                    .astype(str)
                    .str.replace(r"\.", "", regex=True)
                    .str.replace(",", ".", regex=False)
                )
                df[c] = pd.to_numeric(df[c], errors="coerce")

        if "produto" not in df.columns or "qtde" not in df.columns:
            st.error("Estoque: colunas obrigatórias não encontradas após mapeamento.")
            return pd.DataFrame()

        df["produto"] = df["produto"].astype(str).str.strip()
        df["descricao"] = df.get("descricao", pd.Series([""] * len(df))).astype(str).str.strip()

        # Calcula vl_total se não existir
        if "vl_total" not in df.columns and "vl_custo" in df.columns:
            df["vl_total"] = df["qtde"].fillna(0) * df["vl_custo"].fillna(0)

        df = df[df["qtde"].fillna(0) > 0].reset_index(drop=True)
        return df

    except Exception as e:
        st.error(f"Erro ao carregar estoque: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────
# CARREGAMENTO DE VENDAS
# ─────────────────────────────────────────────
@st.cache_data
def carregar_vendas(file_obj):
    """
    Aceita CSV com 9 colunas (sem Pedido) ou 10 colunas (com Pedido).
    Separador: ;
    Decimal: , (vírgula)
    """
    try:
        # Lê sem inferir tipos para ter controle total
        df = pd.read_csv(
            file_obj,
            sep=";",
            encoding="latin-1",
            dtype=str,
            skip_blank_lines=True,
        )
        df.columns = df.columns.str.strip()

        # Remove linhas totalmente vazias
        df = df.dropna(how="all")

        # Mapeia colunas
        rename_map = {}
        for col in df.columns:
            lo = col.lower().strip()
            if "emiss" in lo or lo in ("data", "dt"):
                rename_map[col] = "data"
            elif lo == "pedido":
                rename_map[col] = "pedido"
            elif "marca" in lo:
                rename_map[col] = "marca"
            elif "grupo" in lo:
                rename_map[col] = "grupo"
            elif "btu" in lo:
                rename_map[col] = "btu"
            elif "ciclo" in lo:
                rename_map[col] = "ciclo"
            elif lo == "produto":
                rename_map[col] = "produto"
            elif "descr" in lo:
                rename_map[col] = "descricao"
            elif lo in ("qtde", "qtd", "quantidade"):
                rename_map[col] = "qtde"
            elif "custo" in lo and "total" not in lo:
                rename_map[col] = "vl_custo"
            elif "total" in lo:
                rename_map[col] = "vl_total"

        df = df.rename(columns=rename_map)

        # Data
        if "data" in df.columns:
            df["data"] = pd.to_datetime(
                df["data"].str.strip(), format="%d/%m/%Y", errors="coerce"
            )

        # Converte numéricos: remove ponto de milhar, troca vírgula por ponto
        def _num(serie):
            return (
                pd.to_numeric(
                    serie.astype(str)
                    .str.strip()
                    .str.replace(r"\.", "", regex=True)
                    .str.replace(",", ".", regex=False),
                    errors="coerce",
                )
                .fillna(0.0)
                .astype(float)
            )

        for c in ["qtde", "vl_custo", "vl_total"]:
            if c in df.columns:
                df[c] = _num(df[c])

        # Quando vl_total está ausente ou zero, calcula como custo × qtde
        if "vl_total" not in df.columns:
            df["vl_total"] = 0.0
        if "vl_custo" in df.columns and "qtde" in df.columns:
            mask_sem_total = df["vl_total"].isna() | (df["vl_total"] == 0)
            df.loc[mask_sem_total, "vl_total"] = (
                df.loc[mask_sem_total, "vl_custo"] * df.loc[mask_sem_total, "qtde"]
            )

        # Garante string nas categóricas
        for c in ["marca", "grupo", "btu", "ciclo", "produto", "descricao"]:
            if c in df.columns:
                df[c] = df[c].astype(str).str.strip()

        return df.reset_index(drop=True)

    except Exception as e:
        st.error(f"Erro ao carregar vendas: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────
# CLASSIFICAÇÃO ABC IA
# ─────────────────────────────────────────────
def classificar_abc_ia(df_vendas):
    """
    Recebe df_vendas já filtrado pelo período.
    Retorna DataFrame com produto, classe_unid, classe_valor.
    """
    if df_vendas.empty or "produto" not in df_vendas.columns:
        return pd.DataFrame(columns=["produto", "classe_unid", "classe_valor"])

    agg = (
        df_vendas.groupby("produto", as_index=False)
        .agg(qtde_total=("qtde", "sum"), valor_total=("vl_total", "sum"))
    )

    def _curva(serie, col_out):
        total = serie.sum()
        if total == 0:
            return pd.Series(["X"] * len(serie), index=serie.index)
        s = serie.sort_values(ascending=False)
        acum = s.cumsum() / total
        classes = pd.cut(
            acum,
            bins=[-0.001, 0.50, 0.80, 0.95, 0.99, 1.001],
            labels=["A+", "A", "B", "C", "X"],
        )
        return classes

    agg = agg.sort_values("qtde_total", ascending=False).reset_index(drop=True)
    agg["classe_unid"] = _curva(agg["qtde_total"], "classe_unid").values

    agg = agg.sort_values("valor_total", ascending=False).reset_index(drop=True)
    agg["classe_valor"] = _curva(agg["valor_total"], "classe_valor").values

    return agg[["produto", "qtde_total", "valor_total", "classe_unid", "classe_valor"]]


# ─────────────────────────────────────────────
# ABA ESTOQUE & ABC
# ─────────────────────────────────────────────
def aba_estoque(estoque_df, vendas_df):
    st.header("📦 Estoque & ABC IA")

    if estoque_df.empty:
        st.warning("Carregue o arquivo de estoque para ver esta aba.")
        return

    # ── Parâmetros ──────────────────────────────────────────────────
    st.subheader("⚙️ Parâmetros")
    c1, c2, c3 = st.columns(3)

    data_ini_default = pd.Timestamp("2025-01-01").date()
    data_fim_default = pd.Timestamp.today().date()

    if not vendas_df.empty and "data" in vendas_df.columns:
        datas = vendas_df["data"].dropna()
        if not datas.empty:
            data_ini_default = datas.min().date()
            data_fim_default = datas.max().date()

    with c1:
        data_ini = st.date_input("De", value=data_ini_default, key="est_ini")
    with c2:
        data_fim = st.date_input("Até", value=data_fim_default, key="est_fim")
    with c3:
        if "marca" in estoque_df.columns:
            marcas = ["Todas"] + sorted(estoque_df["marca"].dropna().unique().tolist())
        else:
            marcas = ["Todas"]
        marca_sel = st.selectbox("Fabricante", marcas, key="est_marca")

    # ── Filtro de estoque ────────────────────────────────────────────
    df_est = estoque_df.copy()
    if marca_sel != "Todas" and "marca" in df_est.columns:
        df_est = df_est[df_est["marca"] == marca_sel]

    # ── KPIs ─────────────────────────────────────────────────────────
    st.divider()
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("SKUs", fmt_qtde(len(df_est)))
    k2.metric("Total Unidades", fmt_qtde(df_est["qtde"].sum() if "qtde" in df_est.columns else 0))
    k3.metric("Valor Total (Custo)", fmt_brl(df_est["vl_total"].sum() if "vl_total" in df_est.columns else 0))
    k4.metric("Fabricantes", str(df_est["marca"].nunique()) if "marca" in df_est.columns else "—")

    # ── ABC IA ────────────────────────────────────────────────────────
    abc_df = pd.DataFrame(columns=["produto", "qtde_total", "valor_total", "classe_unid", "classe_valor"])
    if not vendas_df.empty and "data" in vendas_df.columns:
        v_filtrado = vendas_df[
            (vendas_df["data"].dt.date >= data_ini) &
            (vendas_df["data"].dt.date <= data_fim)
        ]
        abc_df = classificar_abc_ia(v_filtrado)

    # Junta ABC no estoque
    df_est["produto"] = df_est["produto"].astype(str).str.strip()
    if not abc_df.empty:
        abc_df["produto"] = abc_df["produto"].astype(str).str.strip()
        df_est = df_est.merge(
            abc_df[["produto", "qtde_total", "valor_total", "classe_unid", "classe_valor"]],
            on="produto",
            how="left",
        )
    else:
        df_est["qtde_total"] = 0.0
        df_est["valor_total"] = 0.0
        df_est["classe_unid"] = "X"
        df_est["classe_valor"] = "X"

    df_est["classe_unid"] = df_est["classe_unid"].fillna("X").astype(str)
    df_est["classe_valor"] = df_est["classe_valor"].fillna("X").astype(str)

    # ── Tabela ────────────────────────────────────────────────────────
    st.divider()
    st.subheader("📋 Tabela de Estoque")

    colunas_ord = [
        ("marca",        "Fabricante"),
        ("grupo",        "Grupo"),
        ("btu",          "BTU"),
        ("ciclo",        "Ciclo"),
        ("produto",      "Produto"),
        ("descricao",    "Descrição"),
        ("qtde",         "Qtde Estoque"),
        ("vl_custo",     "Custo Unit."),
        ("vl_total",     "Custo Total"),
        ("qtde_total",   "Vendas (Unid)"),
        ("valor_total",  "Vendas (R$)"),
        ("classe_unid",  "ABC IA (Unid)"),
        ("classe_valor", "ABC IA (R$)"),
    ]

    cols_presentes = [(c, label) for c, label in colunas_ord if c in df_est.columns]
    df_view = df_est[[c for c, _ in cols_presentes]].copy()
    df_view.columns = [label for _, label in cols_presentes]

    # Formatação
    for col in ["Custo Unit.", "Custo Total", "Vendas (R$)"]:
        if col in df_view.columns:
            df_view[col] = df_view[col].apply(fmt_brl)
    for col in ["Qtde Estoque", "Vendas (Unid)"]:
        if col in df_view.columns:
            df_view[col] = df_view[col].apply(fmt_qtde)

    # Cor nas colunas ABC IA
    cols_abc = [c for c in ["ABC IA (Unid)", "ABC IA (R$)"] if c in df_view.columns]
    if cols_abc:
        styled = df_view.style.map(colorir_abc, subset=cols_abc)
    else:
        styled = df_view.style

    st.dataframe(styled, use_container_width=True, height=520)

    # ── Gráfico de distribuição ───────────────────────────────────────
    if "classe_unid" in df_est.columns:
        st.divider()
        st.subheader("📊 Distribuição ABC IA")

        gc1, gc2 = st.columns(2)
        ordem = ["A+", "A", "B", "C", "X"]

        with gc1:
            cnt_unid = (
                df_est["classe_unid"]
                .value_counts()
                .reindex(ordem, fill_value=0)
                .reset_index()
            )
            cnt_unid.columns = ["Classe", "SKUs"]
            cnt_unid["Classe"] = cnt_unid["Classe"].astype(str)
            cores = [COR_ABC.get(c, {"bg": "#999"})["bg"] for c in cnt_unid["Classe"]]
            fig1 = px.bar(
                cnt_unid, x="Classe", y="SKUs",
                title="Por Unidades Vendidas",
                color="Classe",
                color_discrete_sequence=cores,
                text="SKUs",
            )
            fig1.update_traces(textposition="outside")
            fig1.update_layout(showlegend=False, plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig1, use_container_width=True)

        with gc2:
            cnt_valor = (
                df_est["classe_valor"]
                .value_counts()
                .reindex(ordem, fill_value=0)
                .reset_index()
            )
            cnt_valor.columns = ["Classe", "SKUs"]
            cnt_valor["Classe"] = cnt_valor["Classe"].astype(str)
            cores2 = [COR_ABC.get(c, {"bg": "#999"})["bg"] for c in cnt_valor["Classe"]]
            fig2 = px.bar(
                cnt_valor, x="Classe", y="SKUs",
                title="Por Valor Vendido (R$)",
                color="Classe",
                color_discrete_sequence=cores2,
                text="SKUs",
            )
            fig2.update_traces(textposition="outside")
            fig2.update_layout(showlegend=False, plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig2, use_container_width=True)


# ─────────────────────────────────────────────
# ABA VENDAS & DEMANDA
# ─────────────────────────────────────────────
def aba_vendas(vendas_df):
    st.header("📈 Vendas & Demanda")

    if vendas_df.empty:
        st.warning("Carregue o arquivo de vendas para ver esta aba.")
        return

    # Filtros
    fc1, fc2 = st.columns(2)
    marcas_disp = ["Todas"] + sorted(vendas_df["marca"].dropna().unique().tolist()) if "marca" in vendas_df.columns else ["Todas"]
    grupos_disp = ["Todos"] + sorted(vendas_df["grupo"].dropna().unique().tolist()) if "grupo" in vendas_df.columns else ["Todos"]

    with fc1:
        marca_sel = st.selectbox("Marca", marcas_disp, key="vnd_marca")
    with fc2:
        grupo_sel = st.selectbox("Grupo", grupos_disp, key="vnd_grupo")

    df = vendas_df.copy()
    if marca_sel != "Todas" and "marca" in df.columns:
        df = df[df["marca"] == marca_sel]
    if grupo_sel != "Todos" and "grupo" in df.columns:
        df = df[df["grupo"] == grupo_sel]

    # KPIs
    st.divider()
    k1, k2, k3 = st.columns(3)
    k1.metric("Registros", fmt_qtde(len(df)))
    if "qtde" in df.columns:
        k2.metric("Unidades Vendidas", fmt_qtde(df["qtde"].sum()))
    if "vl_total" in df.columns:
        k3.metric("Valor Total (R$)", fmt_brl(df["vl_total"].sum()))

    # Gráfico mensal — garantir tipos serializáveis para o Plotly
    if "data" in df.columns and "vl_total" in df.columns:
        st.divider()
        df_mes = df.copy()
        df_mes["mes"] = df_mes["data"].dt.to_period("M").astype(str)
        mensal = (
            df_mes.groupby("mes", as_index=False)
            .agg(vl_total=("vl_total", "sum"), qtde=("qtde", "sum"))
        )
        # Garantir float nativo (evita TypeError do Plotly com numpy types)
        mensal["vl_total"] = mensal["vl_total"].astype(float)
        mensal["qtde"] = mensal["qtde"].astype(float)

        fig = px.bar(
            mensal,
            x="mes",
            y="vl_total",
            title="Vendas Mensais (R$)",
            labels={"mes": "Mês", "vl_total": "R$"},
            text_auto=True,
        )
        fig.update_traces(marker_color="#1565C0")
        fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

    # Gráfico por marca
    if "marca" in df.columns and "vl_total" in df.columns:
        por_marca = (
            df.groupby("marca", as_index=False)["vl_total"]
            .sum()
            .sort_values("vl_total", ascending=False)
        )
        por_marca["vl_total"] = por_marca["vl_total"].astype(float)
        fig2 = px.bar(
            por_marca,
            x="marca",
            y="vl_total",
            title="Vendas por Marca (R$)",
            labels={"marca": "Marca", "vl_total": "R$"},
            text_auto=True,
        )
        fig2.update_layout(plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig2, use_container_width=True)

    # Tabela
    st.divider()
    st.subheader("📋 Detalhes")
    df_show = df.copy()
    if "vl_custo" in df_show.columns:
        df_show["vl_custo"] = df_show["vl_custo"].apply(fmt_brl)
    if "vl_total" in df_show.columns:
        df_show["vl_total"] = df_show["vl_total"].apply(fmt_brl)
    st.dataframe(df_show, use_container_width=True, height=400)


# ─────────────────────────────────────────────
# ABA COBERTURA
# ─────────────────────────────────────────────
def aba_cobertura(estoque_df, vendas_df):
    st.header("📊 Cobertura de Estoque")

    if estoque_df.empty or vendas_df.empty:
        st.warning("Carregue estoque e vendas para ver a cobertura.")
        return

    if "data" not in vendas_df.columns or "produto" not in vendas_df.columns:
        st.warning("Dados de vendas incompletos.")
        return

    dias_total = max((vendas_df["data"].max() - vendas_df["data"].min()).days, 1)

    media = (
        vendas_df.groupby("produto", as_index=False)["qtde"]
        .sum()
        .rename(columns={"qtde": "total_vendido"})
    )
    media["media_diaria"] = (media["total_vendido"] / dias_total).astype(float)

    df = estoque_df.copy()
    df["produto"] = df["produto"].astype(str).str.strip()
    media["produto"] = media["produto"].astype(str).str.strip()
    df = df.merge(media, on="produto", how="left")
    df["media_diaria"] = df["media_diaria"].fillna(0.0)
    df["cobertura_dias"] = df.apply(
        lambda r: round(float(r["qtde"]) / float(r["media_diaria"]), 1)
        if r["media_diaria"] > 0 else None,
        axis=1,
    )

    alvo = st.slider("Cobertura alvo (dias)", 15, 180, 60, key="cob_alvo")
    criticos = df[df["cobertura_dias"].notna() & (df["cobertura_dias"] < alvo)]

    c1, c2 = st.columns(2)
    c1.metric("Produtos abaixo do alvo", fmt_qtde(len(criticos)))
    c2.metric("Alvo definido", f"{alvo} dias")

    cols_exib = [c for c in ["marca", "produto", "descricao", "qtde", "media_diaria", "cobertura_dias"] if c in df.columns]
    labels = {"marca": "Fabricante", "produto": "Produto", "descricao": "Descrição",
              "qtde": "Estoque", "media_diaria": "Média/Dia", "cobertura_dias": "Cobertura (dias)"}
    st.dataframe(
        criticos[cols_exib].rename(columns=labels).sort_values("Cobertura (dias)"),
        use_container_width=True,
        height=450,
    )


# ─────────────────────────────────────────────
# ABA SUGESTÃO DE COMPRA
# ─────────────────────────────────────────────
def aba_sugestao(estoque_df, vendas_df):
    st.header("🛒 Sugestão de Compra")

    if estoque_df.empty or vendas_df.empty:
        st.warning("Carregue estoque e vendas para gerar sugestões.")
        return

    dias_alvo = st.slider("Cobertura desejada (dias)", 15, 180, 90, key="sug_alvo")

    dias_total = max((vendas_df["data"].max() - vendas_df["data"].min()).days, 1)
    media = (
        vendas_df.groupby("produto", as_index=False)["qtde"]
        .sum()
        .rename(columns={"qtde": "total_vendido"})
    )
    media["media_diaria"] = (media["total_vendido"] / dias_total).astype(float)

    df = estoque_df.copy()
    df["produto"] = df["produto"].astype(str).str.strip()
    media["produto"] = media["produto"].astype(str).str.strip()
    df = df.merge(media, on="produto", how="left")
    df["media_diaria"] = df["media_diaria"].fillna(0.0)
    df["estoque_alvo"] = (df["media_diaria"] * dias_alvo).astype(float)
    df["sugestao"] = (df["estoque_alvo"] - df["qtde"].fillna(0)).clip(lower=0).round(0)

    if "vl_custo" in df.columns:
        df["valor_sugestao"] = (df["sugestao"] * df["vl_custo"].fillna(0)).astype(float)
    else:
        df["valor_sugestao"] = 0.0

    df_sug = df[df["sugestao"] > 0].sort_values("valor_sugestao", ascending=False)

    c1, c2 = st.columns(2)
    c1.metric("SKUs a comprar", fmt_qtde(len(df_sug)))
    c2.metric("Investimento estimado", fmt_brl(df_sug["valor_sugestao"].sum()))

    cols_exib = [c for c in ["marca", "produto", "descricao", "qtde", "media_diaria", "sugestao", "vl_custo", "valor_sugestao"] if c in df_sug.columns]
    labels = {
        "marca": "Fabricante", "produto": "Produto", "descricao": "Descrição",
        "qtde": "Estoque Atual", "media_diaria": "Média/Dia",
        "sugestao": "Sugestão (Unid)", "vl_custo": "Custo Unit.",
        "valor_sugestao": "Valor Total Sugerido",
    }
    df_show = df_sug[cols_exib].rename(columns=labels).copy()
    if "Custo Unit." in df_show.columns:
        df_show["Custo Unit."] = df_show["Custo Unit."].apply(fmt_brl)
    if "Valor Total Sugerido" in df_show.columns:
        df_show["Valor Total Sugerido"] = df_show["Valor Total Sugerido"].apply(fmt_brl)

    st.dataframe(df_show, use_container_width=True, height=500)

    csv = df_sug.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")
    st.download_button("📥 Exportar Sugestão (.csv)", data=csv,
                       file_name="sugestao_compra.csv", mime="text/csv")


# ─────────────────────────────────────────────
# ABA FORNECEDORES
# ─────────────────────────────────────────────
def aba_fornecedores(estoque_df):
    st.header("🏭 Fornecedores")

    if estoque_df.empty:
        st.warning("Carregue o arquivo de estoque.")
        return

    col_marca = "marca" if "marca" in estoque_df.columns else None
    if col_marca is None:
        st.info("Coluna de fabricante não encontrada no estoque.")
        return

    resumo = (
        estoque_df.groupby(col_marca, as_index=False)
        .agg(
            SKUs=("produto", "nunique"),
            Unidades=("qtde", "sum"),
            Valor_Total=("vl_total", "sum"),
        )
        .sort_values("Valor_Total", ascending=False)
    )

    resumo["Unidades"] = resumo["Unidades"].apply(fmt_qtde)
    resumo["Valor_Total_fmt"] = resumo["Valor_Total"].apply(fmt_brl)

    st.dataframe(
        resumo[[col_marca, "SKUs", "Unidades", "Valor_Total_fmt"]]
        .rename(columns={col_marca: "Fabricante", "Valor_Total_fmt": "Valor Total (R$)"}),
        use_container_width=True,
    )

    st.divider()
    for fab in resumo[col_marca].tolist():
        logo_path = LOGOS.get(fab)
        df_fab = estoque_df[estoque_df[col_marca] == fab]
        with st.expander(f"{fab}  —  {len(df_fab)} SKUs"):
            if logo_path:
                try:
                    st.image(logo_path, width=120)
                except Exception:
                    pass
            df_fab_show = df_fab.copy()
            if "vl_custo" in df_fab_show.columns:
                df_fab_show["vl_custo"] = df_fab_show["vl_custo"].apply(fmt_brl)
            if "vl_total" in df_fab_show.columns:
                df_fab_show["vl_total"] = df_fab_show["vl_total"].apply(fmt_brl)
            st.dataframe(df_fab_show, use_container_width=True)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    # Logo
    try:
        st.sidebar.image(LOGOS["Grupo"], use_container_width=True)
    except Exception:
        st.sidebar.title("Motor de Compras ❄️")

    st.sidebar.markdown("### 📂 Dados")

    est_file = st.sidebar.file_uploader("Estoque (.xlsx)", type=["xlsx"], key="up_est")
    vnd_file = st.sidebar.file_uploader("Vendas (.csv)", type=["csv"], key="up_vnd")

    estoque_df = pd.DataFrame()
    vendas_df = pd.DataFrame()

    if est_file is not None:
        estoque_df = carregar_estoque(est_file)
        if not estoque_df.empty:
            st.sidebar.success(f"✅ Estoque: {fmt_qtde(len(estoque_df))} produtos")
        else:
            st.sidebar.error("❌ Estoque: 0 produtos")

    if vnd_file is not None:
        vendas_df = carregar_vendas(vnd_file)
        if not vendas_df.empty:
            st.sidebar.success(f"✅ Vendas: {fmt_qtde(len(vendas_df))} registros")
        else:
            st.sidebar.error("❌ Vendas: 0 registros")

    tabs = st.tabs([
        "📦 Estoque & ABC",
        "📈 Vendas & Demanda",
        "📊 Cobertura",
        "🛒 Sugestão de Compra",
        "🏭 Fornecedores",
    ])

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
