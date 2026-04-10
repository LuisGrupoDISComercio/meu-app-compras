import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import io
import re
from pathlib import Path

st.set_page_config(
    page_title="Motor de Compras — Ar Condicionado",
    page_icon="❄️",
    layout="wide"
)

# ─────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────

# Mapa de fornecedores: coluna Fabr (002, 003, etc.)
MAPA_FABRICANTES_ESTOQUE = {
    "002": "LG",
    "003": "Samsung",
    "004": "Midea",
    "005": "Daikin",
    "006": "Agratto",
    "007": "Gree",
    "010": "Trane",
    "011": "TCL",
}
FABRICANTES_IGNORAR_INTERVALO = range(900, 1000)  # 900–999 = Outros

# Caminhos de logos (ajuste nomes conforme seus arquivos na pasta images/)
LOGOS_FORNECEDOR = {
    "LG": "images/lg.png",
    "Samsung": "images/samsung.png",
    "Midea": "images/midea.png",
    "Daikin": "images/daikin.png",
    "Agratto": "images/agratto.png",
    "Gree": "images/gree.png",
    "Trane": "images/trane.png",
    "TCL": "images/tcl.png",
}
LOGO_EMPRESA = "images/DIS_NEW.png"

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def limpa_valor(s) -> float:
    try:
        txt = str(s).strip()
        if not txt:
            return 0.0
        # remove símbolos comuns
        txt = re.sub(r"[R$\s]", "", txt)
        # BR: ponto milhar, vírgula decimal
        if "," in txt and "." in txt:
            txt = txt.replace(".", "").replace(",", ".")
        elif "," in txt:
            txt = txt.replace(",", ".")
        return float(txt)
    except Exception:
        return 0.0


def carrega_logo(path_str: str):
    """Tenta carregar uma imagem, devolve None se não existir."""
    if not path_str:
        return None
    p = Path(path_str)
    if p.is_file():
        return str(p)
    return None

# ─────────────────────────────────────────────
# CARREGAMENTO DE DADOS
# ─────────────────────────────────────────────
def carregar_estoque(file) -> pd.DataFrame:
    """
    Lê o Estoque.xlsx com estrutura:
    Fabr | Produto | Descrição | ABC | Cubagem (Un) | Qtde |
    Custo Entrada Unitário Médio | Custo Entrada Total
    """
    file.seek(0)
    df = pd.read_excel(file, header=0)

    # Garante as colunas esperadas pelo nome original
    colmap_esperado = {
        "Fabr": "fabricante_raw",
        "Produto": "produto_id",
        "Descrição": "descricao",
        "ABC": "classe_abc",
        "Cubagem (Un)": "volume",
        "Qtde": "qtde",
        "Custo Entrada Unitário Médio": "custo_unit",
        "Custo Entrada Total": "custo_total",
    }
    faltando = [c for c in colmap_esperado.keys() if c not in df.columns]
    if faltando:
        raise ValueError(f"Colunas não encontradas no Excel de estoque: {faltando}")

    df = df[list(colmap_esperado.keys())].rename(columns=colmap_esperado)

    # Remove linhas totalmente vazias
    df = df.dropna(how="all")

    # Converte fabricante para string de 3 dígitos (002, 003, etc.)
    def normaliza_fabr(x):
        try:
            if pd.isna(x):
                return None
            v_float = float(x)
            v_int = int(v_float)
            return f"{v_int:03d}"
        except Exception:
            s = str(x).strip()
            # se já vier como "002", "3", etc.
            s = re.sub(r"\D", "", s)
            if not s:
                return None
            return f"{int(s):03d}"

    df["fabricante_codigo"] = df["fabricante_raw"].apply(normaliza_fabr)

    # Classifica 900–999 como "Outros"
    def mapeia_fabricante(cod: str) -> str:
        if cod is None:
            return "Outros"
        if cod in MAPA_FABRICANTES_ESTOQUE:
            return MAPA_FABRICANTES_ESTOQUE[cod]
        try:
            n = int(cod)
            if n in FABRICANTES_IGNORAR_INTERVALO:
                return "Outros"
        except Exception:
            pass
        return "Outros"

    df["fabricante_nome"] = df["fabricante_codigo"].apply(mapeia_fabricante)

    # Conversões numéricas
    df["qtde"] = pd.to_numeric(df["qtde"], errors="coerce").fillna(0).astype(float)
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)
    df["custo_unit"] = pd.to_numeric(df["custo_unit"], errors="coerce").fillna(0.0)
    df["custo_total"] = pd.to_numeric(df["custo_total"], errors="coerce").fillna(
        df["qtde"] * df["custo_unit"]
    )

    # Limpa descrição e classe
    df["descricao"] = df["descricao"].astype(str).str.strip()
    df["classe_abc"] = df["classe_abc"].astype(str).str.strip()

    # Remove produtos sem código / sem qtde
    df = df[df["produto_id"].notna()]
    df["produto_id"] = df["produto_id"].astype(str).str.strip()

    # Reordena colunas principais
    cols = [
        "fabricante_codigo",
        "fabricante_nome",
        "produto_id",
        "descricao",
        "classe_abc",
        "volume",
        "qtde",
        "custo_unit",
        "custo_total",
    ]
    df = df[cols].reset_index(drop=True)
    return df


def detectar_delimitador(texto: str) -> str:
    # conta ; e , e escolhe o mais frequente (simples e robusto)
    sc = texto.count(";")
    cc = texto.count(",")
    return ";" if sc >= cc else ","


def carregar_vendas(file) -> pd.DataFrame:
    """
    Lê Vendas.csv com delimitador automático.
    Espera, no mínimo, colunas:
    - data_emissao
    - produto_id
    - qtde
    - valor_total (ou similar)
    """
    raw = file.read()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="ignore")
    texto = str(raw)

    delim = detectar_delimitador(texto)
    buf = io.StringIO(texto)

    df = pd.read_csv(buf, sep=delim, dtype=str, keep_default_na=False)

    # Tentativa de mapear nomes padrões
    col_data = None
    for c in df.columns:
        if c.lower().startswith("data"):
            col_data = c
            break

    col_prod = None
    for c in df.columns:
        if "prod" in c.lower():
            col_prod = c
            break

    col_qtde = None
    for c in df.columns:
        if "qtde" in c.lower() or "quant" in c.lower():
            col_qtde = c
            break

    col_valor = None
    for c in df.columns:
        if "valor" in c.lower() or "total" in c.lower():
            col_valor = c
            break

    obrig = {
        "data_emissao": col_data,
        "produto_id": col_prod,
        "qtde": col_qtde,
        "valor_total": col_valor,
    }
    faltando = [k for k, v in obrig.items() if v is None]
    if faltando:
        raise ValueError(f"Não consegui identificar colunas obrigatórias em Vendas: {faltando}")

    df = df.rename(
        columns={
            obrig["data_emissao"]: "data_emissao",
            obrig["produto_id"]: "produto_id",
            obrig["qtde"]: "qtde",
            obrig["valor_total"]: "valor_total",
        }
    )

    # converte tipos
    df["produto_id"] = df["produto_id"].astype(str).str.strip()
    df["qtde"] = pd.to_numeric(df["qtde"], errors="coerce").fillna(0.0)
    df["valor_total"] = df["valor_total"].apply(limpa_valor)

    # datas (dd/mm/aaaa ou yyyy-mm-dd etc.)
    df["data_emissao"] = pd.to_datetime(df["data_emissao"], errors="coerce", dayfirst=True)
    df = df[df["data_emissao"].notna()].reset_index(drop=True)
    return df

# ─────────────────────────────────────────────
# ABAS
# ─────────────────────────────────────────────
def aba_estoque(estoque_df: pd.DataFrame):
    st.header("📦 Estoque & ABC")

    c1, c2, c3, c4 = st.columns(4)
    total_itens = len(estoque_df)
    total_sku = estoque_df["produto_id"].nunique()
    valor_total = estoque_df["custo_total"].sum()
    volume_total = estoque_df["volume"].sum()

    c1.metric("Linhas de estoque", f"{total_itens:,}".replace(",", "."))
    c2.metric("SKUs distintos", f"{total_sku:,}".replace(",", "."))
    c3.metric("Valor total em estoque", f"R$ {valor_total:,.0f}".replace(",", "."))
    c4.metric("Volume total (m³)", f"{volume_total:,.1f}".replace(",", "."))

    st.subheader("Tabela de estoque (amostra)")
    st.dataframe(
        estoque_df.head(200),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Estoque por fabricante (R$)")
    fab_group = (
        estoque_df.groupby("fabricante_nome", as_index=False)["custo_total"]
        .sum()
        .rename(columns={"custo_total": "Valor"})
        .sort_values("Valor", ascending=False)
    )
    st.dataframe(fab_group, use_container_width=True, hide_index=True)

    fig = px.pie(
        fab_group,
        names="fabricante_nome",
        values="Valor",
        title="Participação por valor em estoque",
        hole=0.4,
    )
    st.plotly_chart(fig, use_container_width=True)


def aba_vendas(vendas_df: pd.DataFrame):
    st.header("📈 Vendas & Demanda")

    c1, c2, c3 = st.columns(3)
    c1.metric("Registros de venda", f"{len(vendas_df):,}".replace(",", "."))
    c2.metric(
        "Período",
        f"{vendas_df['data_emissao'].min().date()} → {vendas_df['data_emissao'].max().date()}",
    )
    c3.metric("Valor total", f"R$ {vendas_df['valor_total'].sum():,.0f}".replace(",", "."))

    st.subheader("Tabela de vendas (amostra)")
    st.dataframe(
        vendas_df.head(500),
        use_container_width=True,
        hide_index=True,
    )


def aba_cobertura(estoque_df: pd.DataFrame, vendas_df: pd.DataFrame):
    st.header("📊 Cobertura")
    st.info("Ainda não implementado nesta versão simplificada.")


def aba_sugestao(estoque_df: pd.DataFrame, vendas_df: pd.DataFrame):
    st.header("🛒 Sugestão de Compras")
    st.info("Ainda não implementado nesta versão simplificada.")


def aba_fornecedores(estoque_df: pd.DataFrame):
    st.header("🏭 Fornecedores")

    if estoque_df.empty:
        st.info("Carregue o arquivo de estoque para ver os fornecedores.")
        return

    fab_group = (
        estoque_df.groupby("fabricante_nome", as_index=False)["custo_total"]
        .sum()
        .rename(columns={"custo_total": "Valor"})
        .sort_values("Valor", ascending=False)
    )

    st.subheader("Resumo por fornecedor")
    st.dataframe(fab_group, use_container_width=True, hide_index=True)

    st.subheader("Identidade visual")
    cols = st.columns(4)
    for i, (_, row) in enumerate(fab_group.iterrows()):
        nome = row["fabricante_nome"]
        col = cols[i % 4]
        with col:
            st.markdown(f"**{nome}**")
            logo_path = carrega_logo(LOGOS_FORNECEDOR.get(nome, ""))
            if logo_path:
                st.image(logo_path, use_container_width=True)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    # Logo da empresa no topo da sidebar (se existir)
    with st.sidebar:
        logo_path = carrega_logo(LOGO_EMPRESA)
        if logo_path:
            st.image(logo_path, use_container_width=True)
        st.title("Motor de Compras")
        st.caption("Grupo DIS Comércio — UNIS / Bonshop")

        st.header("📂 Arquivos")
        file_estoque = st.file_uploader("Estoque (.xlsx)", type=["xlsx"])
        file_vendas = st.file_uploader("Vendas (.csv)", type=["csv"])

    estoque_df = pd.DataFrame()
    vendas_df = pd.DataFrame()

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

    st.title("❄️ Motor de Compras — Ar Condicionado")

    tabs = st.tabs(
        [
            "📦 Estoque & ABC",
            "📈 Vendas & Demanda",
            "📊 Cobertura",
            "🛒 Sugestão de Compras",
            "🏭 Fornecedores",
        ]
    )

    with tabs[0]:
        if not estoque_df.empty:
            aba_estoque(estoque_df)
        else:
            st.info("Carregue o arquivo de estoque.")

    with tabs[1]:
        if not vendas_df.empty:
            aba_vendas(vendas_df)
        else:
            st.info("Carregue o arquivo de vendas.")

    with tabs[2]:
        aba_cobertura(estoque_df, vendas_df)

    with tabs[3]:
        aba_sugestao(estoque_df, vendas_df)

    with tabs[4]:
        aba_fornecedores(estoque_df)


if __name__ == "__main__":
    main()
