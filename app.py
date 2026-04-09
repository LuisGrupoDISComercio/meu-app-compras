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
    "LG":             {"limite": 3_500_000, "prazo": 28},
    "Samsung":        {"limite": 2_000_000, "prazo": 28},
    "Springer Midea": {"limite": 1_500_000, "prazo": 28},
    "Daikin":         {"limite": 5_000_000, "prazo": 35},
    "Agratto":        {"limite":   500_000, "prazo": 28},
    "Gree":           {"limite": 3_000_000, "prazo": 28},
    "Trane":          {"limite": 2_000_000, "prazo": 35},
    "TCL":            {"limite": 3_000_000, "prazo": 28},
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
    Exemplos:
      'R$ 4.317'         -> 4317.0
      'R$ 6.265.053,00'  -> 6265053.0
      '1067,50'          -> 1067.5
      '1067.50'          -> 1067.5
    """
    try:
        txt = str(s).strip()
        txt = re.sub(r"[R$\s]", "", txt).strip()
        if not txt:
            return 0.0

        tem_virgula = "," in txt
        tem_ponto   = "." in txt

        if tem_virgula and tem_ponto:
            # Formato BR: 6.265.053,00 → remove pontos, troca vírgula
            txt = txt.replace(".", "").replace(",", ".")
        elif tem_virgula and not tem_ponto:
            # Só vírgula: decimal BR
            txt = txt.replace(",", ".")
        elif tem_ponto and not tem_virgula:
            partes = txt.split(".")
            if len(partes) > 2:
                # Múltiplos pontos = separador de milhar: 1.234.567
                txt = txt.replace(".", "")
            elif len(partes) == 2 and len(partes[1]) == 3:
                # Um ponto com 3 dígitos depois = milhar: 4.317
                txt = txt.replace(".", "")
            # else: decimal normal: 1067.50
        return float(txt)
    except Exception:
        return 0.0


# ─────────────────────────────────────────────
# CARREGAMENTO DE DADOS
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def carregar_vendas(file_obj):
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

    # Remove colunas duplicadas caso existam
    df = df.loc[:, ~df.columns.duplicated()]

    # Descarta linhas onde data_emissao não é uma data válida dd/mm/aaaa
    df = df[df["data_emissao"].str.match(r"^\d{2}/\d{2}/\d{4}$", na=False)].copy()

    # Converte data via apply (evita bug de duplicate keys do pandas moderno

