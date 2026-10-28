"""Compara uma versão republicada de `votacao_candidato_munzona` com a versão anterior, para um turno.

Em 2026-10-26/27 o TSE republicou os arquivos de `resultados-2026` com o 2º turno, e as linhas do 1º turno também
mudaram. O espelho (tse.espelho) guarda a versão anterior em `data/raw/resultados-2026/_substituidos/<data>/`.
Este módulo junta as duas versões por município × zona × cargo × candidato e registra o que mudou:

- `manifests/republicacao_votacao_candidato_munzona_{t}t.csv`: uma linha por chave com diferença (`so_antiga`,
  `so_nova` ou `alterada`), com votos, situação da candidatura, destinação dos votos e situação de totalização nas
  duas versões;
- `manifests/republicacao_votacao_candidato_munzona_{t}t_resumo.csv`: totais por UF × cargo.

As duas versões são identificadas pelo SHA-512 do manifesto do espelho. Uma diferença é um fato a explicar
(por exemplo, retotalização depois de decisão sobre candidatura), não uma conclusão.
"""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

import pandas as pd

from tse import espelho

DATASET = "resultados-2026"
ARQUIVO = "votacao_candidato_munzona_2026.zip"
CHAVE = ["SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "CD_CARGO", "DS_CARGO", "SQ_CANDIDATO", "NR_CANDIDATO",
         "NM_URNA_CANDIDATO", "ST_VOTO_EM_TRANSITO"]
VALORES = ["QT_VOTOS_NOMINAIS", "QT_VOTOS_NOMINAIS_VALIDOS", "DS_SITUACAO_CANDIDATURA", "DS_DETALHE_SITUACAO_CAND",
           "NM_TIPO_DESTINACAO_VOTOS", "DS_SIT_TOT_TURNO"]
NUMEROS = ["QT_VOTOS_NOMINAIS", "QT_VOTOS_NOMINAIS_VALIDOS"]


def ler(z: Path, turno: int) -> tuple[pd.DataFrame, str]:
    """Linhas do turno em todos os CSVs por UF e no `_BR` (Presidente); o `_BRASIL` repete a soma e fica de fora."""
    partes, geracao = [], set()
    with zipfile.ZipFile(z) as zf:
        for n in zf.namelist():
            if not n.lower().endswith(".csv") or n.lower().endswith("_brasil.csv"):
                continue
            df = pd.read_csv(zf.open(n), sep=";", encoding="latin-1", dtype=str, keep_default_na=False,
                             usecols=CHAVE + VALORES + ["NR_TURNO", "DT_GERACAO", "HH_GERACAO"])
            df = df[df["NR_TURNO"] == str(turno)]
            geracao.update(df["DT_GERACAO"] + " " + df["HH_GERACAO"])
            partes.append(df.drop(columns=["NR_TURNO", "DT_GERACAO", "HH_GERACAO"]))
    df = pd.concat(partes, ignore_index=True)
    df[NUMEROS] = df[NUMEROS].astype("int64")
    if df.duplicated(CHAVE).any():
        raise ValueError(f"chave duplicada em {z}")
    return df, ", ".join(sorted(geracao))


def main() -> None:
    p = argparse.ArgumentParser(description="Diferenças entre versões de votacao_candidato_munzona")
    p.add_argument("--turno", type=int, choices=[1, 2], default=1)
    t = p.parse_args().turno

    raiz = Path("data/raw") / DATASET
    m = espelho.ler_manifesto(DATASET)
    versoes = m[m["arquivo"] == ARQUIVO]
    nova, antiga = versoes.iloc[-1], versoes.iloc[-2]
    marca = "".join(c for c in antiga["baixado_em"] if c.isdigit() or c == "T")[:15]
    arq_antigo = raiz / "_substituidos" / marca / ARQUIVO
    if nova["substitui"] != antiga["sha512"] or espelho.sha512(arq_antigo) != antiga["sha512"]:
        raise ValueError("versão anterior no disco não confere com o manifesto")

    a, ger_a = ler(arq_antigo, t)
    b, ger_b = ler(raiz / ARQUIVO, t)
    j = a.merge(b, on=CHAVE, how="outer", suffixes=("_antiga", "_nova"), indicator=True)
    j["tipo"] = j["_merge"].map({"left_only": "so_antiga", "right_only": "so_nova", "both": "alterada"})
    for c in NUMEROS:
        j[f"{c}_dif"] = j[f"{c}_nova"].fillna(0).astype("int64") - j[f"{c}_antiga"].fillna(0).astype("int64")
    mudou = j["_merge"] != "both"
    for c in VALORES:
        mudou |= j[f"{c}_antiga"].astype(str) != j[f"{c}_nova"].astype(str)
    dif = j[mudou].drop(columns="_merge")
    dif.insert(0, "sha512_antiga", antiga["sha512"])
    dif.insert(1, "sha512_nova", nova["sha512"])

    resumo = dif.groupby(["SG_UF", "DS_CARGO", "tipo"]).agg(
        linhas=("tipo", "size"),
        votos_nominais_dif=("QT_VOTOS_NOMINAIS_dif", "sum"),
        votos_validos_dif=("QT_VOTOS_NOMINAIS_VALIDOS_dif", "sum"),
        candidatos=("SQ_CANDIDATO", "nunique"),
    ).reset_index()

    base = Path("manifests") / f"republicacao_votacao_candidato_munzona_{t}t"
    dif.to_csv(f"{base}.csv", index=False)
    resumo.to_csv(f"{base}_resumo.csv", index=False)
    print(f"versão antiga: gerada {ger_a}, baixada {antiga['baixado_em']}")
    print(f"versão nova:   gerada {ger_b}, baixada {nova['baixado_em']}")
    print(f"{len(a)} -> {len(b)} linhas do {t}º turno; {len(dif)} com diferença")
    with pd.option_context("display.width", 250, "display.max_rows", 80):
        print(resumo.to_string(index=False))


if __name__ == "__main__":
    main()
