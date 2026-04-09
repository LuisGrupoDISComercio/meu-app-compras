def carregar_estoque(file_obj) -> pd.DataFrame:
    """
    Lê o Estoque.xlsx mapeando colunas por POSIÇÃO, não por nome.
    Ordem esperada no Excel:
      0: Fabr       → fabricante_id
      1: Produto    → produto_id
      2: Descrição  → descricao
      3: Classe     → classe_abc
      4: M³         → volume
      5: Qtde       → qtde
      6: Custo Unit → custo_unit
      7: Custo Total→ custo_total
    """

    # ── 1. descobre em qual linha está o cabeçalho ──────────────────────
    preview = pd.read_excel(file_obj, header=None, nrows=10, dtype=str)
    file_obj.seek(0)

    header_row = 0
    for i, row in preview.iterrows():
        vals = row.astype(str).str.strip().str.lower().tolist()
        # procura a linha que tem algo parecido com "fabr" e "produto"
        tem_fabr    = any("fabr" in v for v in vals)
        tem_produto = any("prod" in v for v in vals)
        if tem_fabr and tem_produto:
            header_row = i
            break

    # ── 2. lê com o cabeçalho correto ───────────────────────────────────
    df = pd.read_excel(file_obj, header=header_row, dtype=str)
    file_obj.seek(0)

    # ── 3. limpa nomes de colunas ────────────────────────────────────────
    df.columns = [str(c).strip() for c in df.columns]

    # ── 4. renomeia por POSIÇÃO (ignora nome exato) ──────────────────────
    NOMES_INTERNOS = [
        "fabricante_id",  # col 0
        "produto_id",     # col 1
        "descricao",      # col 2
        "classe_abc",     # col 3
        "volume",         # col 4
        "qtde",           # col 5
        "custo_unit",     # col 6
        "custo_total",    # col 7
    ]

    if df.shape[1] < len(NOMES_INTERNOS):
        raise ValueError(
            f"Excel tem só {df.shape[1]} colunas; esperava ao menos {len(NOMES_INTERNOS)}."
        )

    rename_map = {df.columns[i]: NOMES_INTERNOS[i] for i in range(len(NOMES_INTERNOS))}
    df = df.rename(columns=rename_map)

    # ── 5. descarta linhas sem fabricante ou produto ─────────────────────
    df = df.dropna(subset=["fabricante_id", "produto_id"])
    df = df[df["fabricante_id"].str.strip() != ""]
    df = df[df["produto_id"].str.strip()    != ""]

    # ── 6. converte tipos ────────────────────────────────────────────────
    df["fabricante_id"] = pd.to_numeric(df["fabricante_id"], errors="coerce")
    df["produto_id"]    = pd.to_numeric(df["produto_id"],    errors="coerce")
    df["qtde"]          = pd.to_numeric(df["qtde"],          errors="coerce").fillna(0)
    df["volume"]        = pd.to_numeric(df["volume"],        errors="coerce").fillna(0)
    df["custo_unit"]    = df["custo_unit"].apply(limpa_valor)
    df["custo_total"]   = df["custo_total"].apply(limpa_valor)

    # ── 7. descarta fabricantes ignorados e sem mapeamento ───────────────
    df = df.dropna(subset=["fabricante_id", "produto_id"])
    df["fabricante_id"] = df["fabricante_id"].astype(int)
    df["produto_id"]    = df["produto_id"].astype(int)

    df = df[~df["fabricante_id"].isin(FABRICANTES_IGNORAR)]

    # ── 8. adiciona nome do fabricante ───────────────────────────────────
    df["fabricante_nome"] = df["fabricante_id"].map(MAPA_FABRICANTES_ESTOQUE).fillna("Outros")

    return df
