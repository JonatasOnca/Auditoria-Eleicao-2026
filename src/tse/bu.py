"""Boletins de Urna (BU) em CSV, por UF (RESEARCH_PLAN.md §5.1, camada leve).

Fonte: dataset CKAN `resultados-2026-boletim-de-urna` (`bweb_1t_{UF}_*.zip` + `.sha512`).
Cada ZIP é baixado em memória, conferido contra o `.sha512` oficial e reduzido a duas tabelas:

- `bu_secoes`: uma linha por seção. Inclui aptos, comparecimento, eleitores com biometria não
  reconhecida, abertura/encerramento (hora LOCAL da urna), tipo de urna, seções agregadas,
  recebimento e identificação da urna.
- `bu_votos_presidente`: votos por seção × votável para Presidente (nominais, brancos, nulos).

Em 2026 algumas colunas mudaram de nome em relação a 2022:
`QT_ELEI_BIOM_SEM_HABILITACAO` (antes `QT_ELEITORES_BIOMETRIA_NH`) e `DS_SECOES_AGREGADAS`
(antes `DS_AGREGADAS`).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import zipfile
from pathlib import Path

import httpx
import pandas as pd

from tse import ckan
from tse.resultados_api import USER_AGENT

DATASET = "resultados-2026-boletim-de-urna"

COLS_SECAO = [
    "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO", "NR_LOCAL_VOTACAO",
    "QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES", "QT_ELEI_BIOM_SEM_HABILITACAO",
    "DT_ABERTURA", "DT_ENCERRAMENTO", "DT_BU_RECEBIDO", "DT_EMISSAO_BU",
    "CD_TIPO_URNA", "DS_TIPO_URNA", "NR_URNA_EFETIVADA", "DS_SECOES_AGREGADAS",
    "NR_JUNTA_APURADORA", "NR_TURMA_APURADORA",
]
INTEIROS = ["QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES", "QT_ELEI_BIOM_SEM_HABILITACAO"]
DATAS = ["DT_ABERTURA", "DT_ENCERRAMENTO", "DT_BU_RECEBIDO", "DT_EMISSAO_BU"]


def _chaves(df: pd.DataFrame) -> pd.DataFrame:
    return df.assign(
        uf=df["SG_UF"],
        cd_municipio=df["CD_MUNICIPIO"].str.zfill(5),
        nr_zona=df["NR_ZONA"].str.zfill(4),
        nr_secao=df["NR_SECAO"].str.zfill(4),
    )


def processar_uf(http: httpx.Client, url: str, url_sha: str | None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    conteudo = http.get(url).raise_for_status().content
    sha = hashlib.sha512(conteudo).hexdigest()
    oficial = None
    if url_sha:
        oficial = http.get(url_sha).raise_for_status().text.split()[0].lower()
        if oficial != sha:
            raise ValueError(f"SHA-512 não confere para {url}: {sha} != {oficial}")
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        csv = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        bu = pd.read_csv(z.open(csv), sep=";", encoding="latin-1", dtype=str, keep_default_na=False)

    pres = bu[bu["DS_CARGO_PERGUNTA"].str.upper() == "PRESIDENTE"]
    secoes = _chaves(pres.drop_duplicates(["CD_MUNICIPIO", "NR_ZONA", "NR_SECAO"])[COLS_SECAO])
    secoes[INTEIROS] = secoes[INTEIROS].apply(pd.to_numeric, errors="coerce").astype("Int64")
    for c in DATAS:
        secoes[c] = pd.to_datetime(secoes[c], errors="coerce")
    secoes["DS_SECOES_AGREGADAS"] = secoes["DS_SECOES_AGREGADAS"].replace("#NULO#", None)
    secoes["_fonte"] = url
    secoes["_sha512"] = sha

    votos = _chaves(pres)[["uf", "cd_municipio", "nr_zona", "nr_secao", "CD_TIPO_VOTAVEL",
                           "DS_TIPO_VOTAVEL", "NR_VOTAVEL", "NM_VOTAVEL", "QT_VOTOS"]].copy()
    votos["QT_VOTOS"] = votos["QT_VOTOS"].astype(int)
    info = {"url": url, "csv": csv, "sha512": sha, "sha512_oficial": oficial, "linhas_csv": len(bu),
            "secoes": len(secoes)}
    return secoes, votos, info


def main() -> None:
    p = argparse.ArgumentParser(description="BU 2026 1º turno: seções e votos para Presidente")
    p.add_argument("--uf", action="append")
    p.add_argument("--saida", default="data/bu_2026_1t")
    a = p.parse_args()
    saida = Path(a.saida)
    saida.mkdir(parents=True, exist_ok=True)

    rec = ckan.recursos(DATASET)
    zips = rec[rec["url"].str.contains("/bweb_1t_") & rec["url"].str.endswith(".zip")].copy()
    zips["uf"] = zips["url"].str.extract(r"bweb_1t_([A-Z]{2})_")[0]
    # se o TSE republicou, fica o arquivo mais recente de cada UF (timestamp DDMMAAAAHHMM no nome)
    zips["ts"] = pd.to_datetime(zips["url"].str.extract(r"_(\d{12})\.zip$")[0], format="%d%m%Y%H%M")
    zips = zips.sort_values("ts").drop_duplicates("uf", keep="last")
    if a.uf:
        zips = zips[zips["uf"].isin([u.upper() for u in a.uf])]
    shas = set(rec["url"])

    todas_secoes, todos_votos, manifesto = [], [], []
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=300) as http:
        for r in zips.itertuples():
            s, v, info = processar_uf(http, r.url, r.url + ".sha512" if r.url + ".sha512" in shas else None)
            todas_secoes.append(s)
            todos_votos.append(v)
            manifesto.append({"uf": r.uf, **info})
            print(f"[{r.uf}] {info['secoes']} seções, SHA-512 {'conferido' if info['sha512_oficial'] else 'sem .sha512 oficial'}",
                  flush=True)

    pd.concat(todas_secoes).to_parquet(saida / "bu_secoes.parquet", index=False)
    pd.concat(todos_votos).to_parquet(saida / "bu_votos_presidente.parquet", index=False)
    pd.DataFrame(manifesto).to_csv("manifests/bu_2026_1t_manifesto.csv", index=False)
    print("OK:", sum(len(s) for s in todas_secoes), "seções")


if __name__ == "__main__":
    main()
