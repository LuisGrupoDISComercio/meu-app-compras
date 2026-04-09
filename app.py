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
    "DAIKIN":         "Daikin",
    "LG":             "LG",
    "SAMSUNG":        "Samsung",
    "GREE":           "Gree",
    "TRANE":          "Trane",
    "TCL":            "TCL",
    "AGRATTO":        "Agratto",
    "DANIFICADO":     "DANIFICADOS",
    "DANIFICADOS":    "DANIFICADOS",
    "SEMI NOVOS":     "SEMI NOVOS",
    "SEMI":           "SEMI NOVOS",
    "ELGIN":          "ELGIN",
}

CONDICOES = {
    "LG":            {"limite": 3_500_000, "prazo": 28},
    "Samsung":       {"limite": 2_000_000, "prazo": 28},
    "Springer Midea":{"limite": 1_500_000, "prazo": 28},
    "Daikin":        {"limite": 5_000_000, "prazo": 35},
    "Agratto":       {"limite":   500_000, "prazo": 28},
    "Gree":          {"limite": 3_000_000, "prazo": 28},
    "Trane":         {"limite": 2_000_000, "prazo": 35},
    "TCL":           {"limite": 3_000_000, "prazo": 28},
}

MESES_PT = {
    1:"Jan", 2:"Fev", 3:"Mar", 4:"Abr", 5:"Mai", 6:"Jun",
    7:"Jul", 8:"Ago", 9:"Set", 10:"Out", 11:"Nov", 12:"Dez"
}

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def decode_bytes(raw: bytes) -> str:
    for enc in ("utf-8-sig", "latin-1", "cp1252", "iso-8859-1", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def normaliza_marca(valor: str) -> str:
    v = str(valor).strip().upper()
    for chave, nome in NORMALIZA_MARCA_VENDAS.items():
        if v == chave or v.startswith(chave):
            return nome
    return valor.strip().title()


def limpa_valor(s) -> float:
    """
    Converte qualquer formato monetário BR para float.
    """
    try:
        txt = str(s).strip()
        txt = re.sub(r"[R$\s]", "", txt)
        txt = txt.strip()
        if not txt:
            return 0.0

        tem_virgula = "," in txt
        tem_ponto   = "." in txt

        if tem_virgula and tem_ponto:
            txt = txt.replace(".", "").replace(",", ".")
        elif tem_virgula and not tem_ponto:
            txt = txt.replace(",", ".")
        elif tem_ponto and not tem_virgula:
            partes = txt.split(".")
            if len(partes) > 2:
                txt = txt.replace(".", "")
        return float(txt)
    except Exception:
        return 0.0


# ─────────────────────────────────────────────
# CARREGAMENTO DE DADOS
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def carregar_estoque(file_obj) -> pd.DataFrame:
    # 1) Ler algumas linhas sem cabeçalho para descobrir a linha certa
    preview = pd.read_excel(file_obj, header=None, nrows=10)
    header_row = None
    for i in range(len(preview)):
        linha = preview.iloc[i].astype(str).str.upper()
        if any("FABR" in x for x in linha) and any("PROD" in x for x in linha):
            header_row = i
            break

    if header_row is None:
        raise ValueError("Não encontrei linha de cabeçalho com 'Fabr' e 'Produto'.")

    # 2) Reposiciona o ponteiro do arquivo e lê de novo com o header correto
    file_obj.seek(0)
    df = pd.read_excel(file_obj, header=header_row)

    # 3) Normaliza nomes de colunas (remove espaços, deixa lower, sem acentos simples)
    col_original = df.columns.tolist()
    col_map = {}
    for c in df.columns:
        c_norm = str(c).strip()
        col_map[c] = c_norm

    df.rename(columns=col_map, inplace=True)

    # 4) Mapear colunas do Excel -> nomes internos
    # usamos substring para ser mais tolerante ('Custo Unit.' / 'Custo Unit')
    def achar_col(substrs):
        substrs = [s.upper() for s in substrs]
        for c in df.columns:
            c_up = str(c).upper()
            if any(s in c_up for s in substrs):
                return c
        return None

    col_fabr       = achar_col(["FABR"])
    col_prod       = achar_col(["PROD"])
    col_desc       = achar_col(["DESCRI"])
    col_classe     = achar_col(["CLASSE"])
    col_volume     = achar_col(["M³", "M3", "VOLUME"])
    col_qtde       = achar_col(["QTDE", "QUANT"])
    col_custo_unit = achar_col(["CUSTO UNIT", "CUSTO UNIT."])
    col_custo_tot  = achar_col(["CUSTO TOTAL", "CUSTO TOT"])

    required_pairs = {
        "fabricante_id": col_fabr,
        "produto_id": col_prod,
        "descricao": col_desc,
        "classe_abc": col_classe,
        "volume": col_volume,
        "qtde": col_qtde,
        "custo_unit": col_custo_unit,
        "custo_total": col_custo_tot,
    }

    faltando = [k for k, v in required_pairs.items() if v is None]
    if faltando:
        raise ValueError(f"Colunas não encontradas no Excel de estoque: {faltando}")

    df = df.rename(columns={
        col_fabr:       "fabricante_id",
        col_prod:       "produto_id",
        col_desc:       "descricao",
        col_classe:     "classe_abc",
        col_volume:     "volume",
        col_qtde:       "qtde",
        col_custo_unit: "custo_unit",
        col_custo_tot:  "custo_total",
    })

    # 5) Tipos e limpeza
    df = df.dropna(subset=["fabricante_id", "produto_id"])
    df["fabricante_id"] = pd.to_numeric(df["fabricante_id"], errors="coerce")
    df["produto_id"]    = pd.to_numeric(df["produto_id"], errors="coerce")
    df["qtde"]          = pd.to_numeric(df["qtde"], errors="coerce").fillna(0)
    df["volume"]        = pd.to_numeric(df["volume"], errors="coerce").fillna(0)

    df["custo_unit"]  = pd.to_numeric(df["custo_unit"], errors="coerce").fillna(0.0)
    df["custo_total"] = pd.to_numeric(df["custo_total"], errors="coerce").fillna(0.0)

    # 6) Filtra fabricantes descartados
    df = df[~df["fabricante_id"].isin(FABRICANTES_IGNORAR)].copy()

    # 7) Nome do fabricante
    df["fabricante_nome"] = df["fabricante_id"].map(MAPA_FABRICANTES_ESTOQUE)
    df["fabricante_nome"] = df["fabricante_nome"].fillna("Outros")

    return df


@st.cache_data(show_spinner=False)
def carregar_vendas(file_obj) -> pd.DataFrame:
    raw   = file_obj.read()
    texto = decode_bytes(raw)

    COLUNAS = ["data_emissao", "marca", "segmento", "potencia",
               "ciclo", "codigo", "descricao", "quantidade", "valor"]

    df = pd.read_csv(
        StringIO(texto),
        sep=";",
        header=None,
        names=COLUNAS,
        dtype=str,
        keep_default_na=False,
    )

    df = df[df["data_emissao"].str.match(r"^\d{2}/\d{2}/\d{4}$", na=False)].copy()
    df["data_emissao"] = pd.to_datetime(df["data_emissao"], format="%d/%m/%Y", errors="coerce")
    df = df.dropna(subset=["data_emissao"])

    df["marca"]       = df["marca"].apply(normaliza_marca)
    df["potencia"]    = pd.to_numeric(df["potencia"], errors="coerce")
    df["quantidade"]  = pd.to_numeric(df["quantidade"], errors="coerce").fillna(0)
    df["valor"]       = df["valor"].apply(limpa_valor)

    df["faturamento"] = df["quantidade"] * df["valor"]
    return df


# ─────────────────────────────────────────────
# ABAS (visuais) – aqui vou assumir que já existiam
# ─────────────────────────────────────────────
def aba_estoque(estoque_df: pd.DataFrame):
    st.header("📦 Estoque & ABC")
    st.dataframe(estoque_df, use_container_width=True)


def aba_vendas(vendas_df: pd.DataFrame):
    st.header("📈 Vendas & Demanda")
    st.dataframe(vendas_df, use_container_width=True)


def aba_cobertura(estoque_df, vendas_df):
    st.header("📊 Cobertura")
    st.write("Implementar lógica de cobertura aqui.")


def aba_sugestao(estoque_df, vendas_df):
    st.header("🛒 Sugestão de Compras")
    st.write("Implementar lógica de sugestão aqui.")


def aba_fornecedores(estoque_df):
    st.header("🏭 Fornecedores")

    dados_cond = [
        {
            "Fornecedor":  fab,
            "Limite (R$)": f"R$ {c['limite']:,.0f}" if c["limite"] > 0 else "—",
            "Prazo (dias)":c["prazo"] if c["prazo"] > 0 else "Antecipado",
        }
        for fab, c in CONDICOES.items()
    ]
    st.subheader("Condições Comerciais")
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
        except Exception as e:
            st.error(f"Erro ao carregar estoque: {e}")

    if file_vendas:
        try:
            vendas_df = carregar_vendas(file_vendas)
        except Exception as e:
            st.error(f"Erro ao carregar vendas: {e}")

    tabs = st.tabs([
        "📦 Estoque & ABC",
        "📈 Vendas & Demanda",
        "📊 Cobertura",
        "🛒 Sugestão de Compras",
        "🏭 Fornecedores"
    ])

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
