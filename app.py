import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

st.set_page_config(
    page_title="Motor de Compras — Ar Condicionado",
    page_icon="❄️",
    layout="wide",
)

# ================ UTILITÁRIOS =================
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
    cores = {
        "A+": ("#8B6914", "#FFFFFF"),
        "A": ("#FFD700", "#1a1a1a"),
        "B": ("#FFA500", "#1a1a1a"),
        "C": ("#FFFF99", "#1a1a1a"),
        "X": ("#D3D3D3", "#1a1a1a"),
    }
    if pd.isna(classe):
        return ""
    bg, fg = cores.get(str(classe).strip().upper(), cores["X"])
    return f"background-color: {bg}; color: {fg}; font-weight:bold; text-align:center;"

# ================ CARREGAMENTO DE ESTOQUE =================
@st.cache_data
def carregar_estoque(file_obj):
    # NÃO forçar dtype=str: deixa o pandas ler tipos numéricos normal
    df = pd.read_excel(file_obj, sheet_name=0, header=0)
    df.columns = df.columns.astype(str).str.strip()

    # mapeia colunas específicas do seu layout
    rename = {}
    for col in df.columns:
        lo = col.lower()
        if lo == "produto":
            rename[col] = "produto"
        elif "descri" in lo:
            rename[col] = "descricao"
        elif lo == "abc":
            rename[col] = "curva_sistema"
        elif lo == "qtde":
            rename[col] = "qtde"
        elif "custo entrada unit" in lo:
            rename[col] = "vl_custo"
        elif "custo entrada total" in lo:
            rename[col] = "vl_total"
        elif lo == "fabr":
            rename[col] = "marca"

    df = df.rename(columns=rename)

    # garante tipos corretos
    if "qtde" in df.columns:
        df["qtde"] = pd.to_numeric(df["qtde"], errors="coerce").fillna(0)

    if "vl_total" in df.columns:
        # aqui é a chave: usar diretamente o float já vindo do Excel
        df["vl_total"] = pd.to_numeric(df["vl_total"], errors="coerce").fillna(0.0)

    if "vl_custo" in df.columns:
        df["vl_custo"] = pd.to_numeric(df["vl_custo"], errors="coerce").fillna(0.0)

    if "produto" in df.columns:
        df["produto"] = df["produto"].astype(str).str.strip()
    if "descricao" in df.columns:
        df["descricao"] = df["descricao"].astype(str).str.strip()
    if "curva_sistema" in df.columns:
        df["curva_sistema"] = df["curva_sistema"].astype(str).str.strip()
    if "marca" in df.columns:
        df["marca"] = df["marca"].astype(str).str.strip()

    # NÃO recalcula vl_total se já veio da planilha
    return df

# ================ CARREGAMENTO DE VENDAS (igual você já tinha) =================
@st.cache_data
def carregar_vendas(file_obj):
    df = pd.read_csv(file_obj, sep=";", decimal=",", encoding="latin1")
    df.columns = df.columns.astype(str).str.strip()
    # ajustes mínimos (se precisar, mantemos depois)
    return df

# ================ ABC =================
def calcular_abc(df, col_qtde="qtde", col_valor="vl_total"):
    base = df.copy()

    if col_qtde in base.columns:
        base[col_qtde] = pd.to_numeric(base[col_qtde], errors="coerce").fillna(0)
    if col_valor and col_valor in base.columns:
        base[col_valor] = pd.to_numeric(base[col_valor], errors="coerce").fillna(0)

    # ABC por unidade
    grp_qtde = (
        base.groupby("produto", as_index=False)[col_qtde]
        .sum()
        .rename(columns={col_qtde: "qtde_total"})
    )
    grp_qtde["perc"] = grp_qtde["qtde_total"] / grp_qtde["qtde_total"].sum()
    grp_qtde = grp_qtde.sort_values("perc", ascending=False)
    grp_qtde["perc_acum"] = grp_qtde["perc"].cumsum()

    def classificar(p):
        if p <= 0.80:
            return "A"
        elif p <= 0.95:
            return "B"
        else:
            return "C"

    grp_qtde["classe_unid"] = grp_qtde["perc_acum"].apply(classificar)

    # ABC por valor
    if col_valor and col_valor in base.columns:
        grp_val = (
            base.groupby("produto", as_index=False)[col_valor]
            .sum()
            .rename(columns={col_valor: "valor_total"})
        )
        grp_val["perc_v"] = grp_val["valor_total"] / grp_val["valor_total"].sum()
        grp_val = grp_val.sort_values("perc_v", ascending=False)
        grp_val["perc_acum_v"] = grp_val["perc_v"].cumsum()
        grp_val["classe_valor"] = grp_val["perc_acum_v"].apply(classificar)
    else:
        grp_val = pd.DataFrame(columns=["produto", "valor_total", "classe_valor"])

    res = base.merge(grp_qtde[["produto", "classe_unid"]], on="produto", how="left")
    res = res.merge(grp_val[["produto", "classe_valor"]], on="produto", how="left")
    return res

# ================ ABAS =================
def aba_estoque(estoque_df, vendas_df):
    st.header("📦 Estoque & ABC IA")

    if estoque_df.empty:
        st.warning("Carregue o arquivo de estoque.")
        return

    df = estoque_df.copy()
    df_abc = calcular_abc(df, col_qtde="qtde", col_valor="vl_total")

    skus = df_abc["produto"].nunique()
    qtde_total = df_abc["qtde"].sum() if "qtde" in df_abc.columns else 0
    vl_total_sum = df_abc["vl_total"].sum() if "vl_total" in df_abc.columns else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("SKUs em estoque", fmt_qtde(skus))
    col2.metric("Qtd total em estoque", fmt_qtde(qtde_total))
    col3.metric("Valor total em estoque", fmt_brl(vl_total_sum))

    # resumo curva sistema se existir
    if "curva_sistema" in df_abc.columns:
        cont = df_abc["curva_sistema"].value_counts().sort_index()
        resumo = ", ".join([f"{k}: {v}" for k, v in cont.items()])
        st.text(f"Curva Sistema (SKUs): {resumo}")

    st.markdown("### Detalhe por produto (ABC IA x Curva Sistema)")

    cols = ["produto", "descricao", "qtde"]
    if "curva_sistema" in df_abc.columns:
        cols.append("curva_sistema")
    cols += ["classe_unid", "classe_valor"]
    cols = [c for c in cols if c in df_abc.columns]

    df_view = df_abc[cols].copy()
    if "qtde" in df_view.columns:
        df_view["qtde"] = df_view["qtde"].apply(fmt_qtde)

    styler = df_view.style
    if "classe_unid" in df_view.columns:
        styler = styler.map(colorir_abc, subset=["classe_unid"])
    if "classe_valor" in df_view.columns:
        styler = styler.map(colorir_abc, subset=["classe_valor"])

    st.dataframe(styler, use_container_width=True)

def aba_vendas(vendas_df):
    st.header("📈 Vendas & Demanda")
    if vendas_df.empty:
        st.warning("Carregue o arquivo de vendas.")
        return
    st.dataframe(vendas_df.head(100))

def aba_cobertura(estoque_df, vendas_df):
    st.header("📊 Cobertura")
    st.info("Cobertura será implementada na próxima etapa.")

def aba_sugestao(estoque_df, vendas_df):
    st.header("🛒 Sugestão de Compra")
    st.info("Sugestão de compra será implementada na próxima etapa.")

def aba_fornecedores(estoque_df):
    st.header("🏭 Fornecedores")
    if estoque_df.empty:
        st.warning("Carregue o arquivo de estoque.")
        return
    if "marca" not in estoque_df.columns:
        st.info("Coluna de fabricante/marca não encontrada no estoque.")
        return
    df = estoque_df
    agg = {"SKUs": ("produto", "nunique"), "Unidades": ("qtde", "sum")}
    if "vl_total" in df.columns:
        agg["Valor"] = ("vl_total", "sum")
    resumo = df.groupby("marca", as_index=False).agg(**agg)
    resumo["Unidades"] = resumo["Unidades"].apply(fmt_qtde)
    if "Valor" in resumo.columns:
        resumo["Valor_fmt"] = resumo["Valor"].apply(fmt_brl)
        cols = ["marca", "SKUs", "Unidades", "Valor_fmt"]
        ren = {"marca": "Fabricante", "Valor_fmt": "Valor (R$)"}
    else:
        cols = ["marca", "SKUs", "Unidades"]
        ren = {"marca": "Fabricante"}
    st.dataframe(resumo[cols].rename(columns=ren), use_container_width=True)

# ================ MAIN =================
def main():
    st.sidebar.markdown("### 📂 Dados")
    est_file = st.sidebar.file_uploader("Estoque (.xlsx)", type=["xlsx"], key="up_est")
    vnd_file = st.sidebar.file_uploader("Vendas (.csv)", type=["csv"], key="up_vnd")

    estoque_df = pd.DataFrame()
    vendas_df = pd.DataFrame()

    if est_file is not None:
        estoque_df = carregar_estoque(est_file)
        if not estoque_df.empty:
            st.sidebar.success(f"Estoque: {fmt_qtde(len(estoque_df))} produtos")
        else:
            st.sidebar.error("Estoque: 0 produtos")

    if vnd_file is not None:
        vendas_df = carregar_vendas(vnd_file)
        if not vendas_df.empty:
            st.sidebar.success(f"Vendas: {fmt_qtde(len(vendas_df))} registros")
        else:
            st.sidebar.error("Vendas: 0 registros")

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
