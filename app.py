import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="Motor de Compras — Ar Condicionado",
    page_icon="❄️",
    layout="wide",
)

FABRICANTES_IGNORAR = {900, 995, 998, 999}

# ----------------- Utilitários -----------------
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

# ----------------- Carga do estoque -----------------
def carregar_estoque(file):
    # o seu arquivo tem o cabeçalho na SEGUNDA linha (linha 1, pois começa em 0)
    df = pd.read_excel(file, header=1)

    # garantimos nomes padrão
    df = df.rename(
        columns={
            "Fabr": "fabr",
            "Produto": "produto",
            "Descrição": "descricao",
            "ABC": "abc_sistema",
            "Cubagem (Un)": "cubagem",
            "Qtde": "qtde",
            "Custo Entrada Unitário Médio": "vl_unit",
            "Custo Entrada Total": "vl_total",
        }
    )

    # remove linha TOTAL (produto e fabr vazios/NaN)
    df = df.dropna(subset=["fabr", "produto"], how="all")

    # remove fabricantes de serviço/danificado
    df["fabr"] = pd.to_numeric(df["fabr"], errors="coerce")
    df = df[~df["fabr"].isin(FABRICANTES_IGNORAR)]

    # garante tipos numéricos
    df["qtde"] = pd.to_numeric(df["qtde"], errors="coerce").fillna(0)
    df["vl_total"] = pd.to_numeric(df["vl_total"], errors="coerce").fillna(0)

    # tira linhas totalmente zeradas
    df = df[df["qtde"].ne(0) | df["vl_total"].ne(0)]

    return df

# ----------------- Aba Estoque & ABC -----------------
def aba_estoque(estoque_df: pd.DataFrame):
    st.header("📦 Estoque & ABC")

    if estoque_df.empty:
        st.warning("Carregue o arquivo de estoque na barra lateral.")
        return

    df = estoque_df.copy()

    # métricas principais
    skus = df["produto"].nunique()
    qtde_total = df["qtde"].sum()
    vl_total = df["vl_total"].sum()

    col1, col2, col3 = st.columns(3)
    col1.metric("SKUs em estoque", fmt_qtde(skus))
    col2.metric("Qtd total em estoque", fmt_qtde(qtde_total))
    col3.metric("Valor total em estoque", fmt_brl(vl_total))

    st.markdown("### Detalhe do Estoque")
    st.dataframe(
        df[["fabr", "produto", "descricao", "abc_sistema", "qtde", "vl_total"]],
        use_container_width=True,
        height=500,
    )

# ----------------- Main -----------------
def main():
    st.title("🧊 Motor de Compras — Ar Condicionado")

    st.sidebar.header("📂 Arquivos")
    est_file = st.sidebar.file_uploader("Estoque (.xlsx)", type=["xlsx"], key="up_est")

    estoque_df = pd.DataFrame()
    if est_file is not None:
        try:
            estoque_df = carregar_estoque(est_file)
            if not estoque_df.empty:
                st.sidebar.success(f"Estoque: {fmt_qtde(len(estoque_df))} produtos")
            else:
                st.sidebar.error("Estoque: 0 produtos")
        except Exception as e:
            st.sidebar.error(f"Erro ao carregar estoque: {e}")
            estoque_df = pd.DataFrame()

    aba_estoque(estoque_df)

if __name__ == "__main__":
    main()
