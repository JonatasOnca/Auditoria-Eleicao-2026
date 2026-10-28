"""Catálogo do Portal de Dados Abertos do TSE (API CKAN).

A API CKAN só devolve metadados. Os dados em si são arquivos ZIP/CSV no CDN
(cdn.tse.jus.br) e são carregados para GCS/BigQuery na Fase 2.

Em 2026-10-28, `package_show` devolvia uma versão antiga dos datasets (o BU sem nenhum arquivo do 2º turno),
enquanto `package_search` já trazia a versão atual. Por isso a leitura usa `package_search` com o nome exato.

O catálogo também não lista todos os arquivos publicados no CDN: em 2026-10-28 faltavam o BU do 2º turno de RR e
todos os arquivos de urna do 2º turno. `fora_do_catalogo` encontra esses arquivos pelo padrão de nome dos arquivos
do próprio dataset e só os aceita se o CDN do TSE responder 200.
"""

from __future__ import annotations

import re

import httpx
import pandas as pd

from tse.resultados_api import USER_AGENT

CKAN = "https://dadosabertos.tse.jus.br/api/3/action"

UFS = ["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR",
       "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO", "ZZ"]

DATASETS_2026 = [
    "resultados-2026",
    "resultados-2026-boletim-de-urna",
    "resultados-2026-correspondencias-esperadas-e-efetivadas-1-turno",
    "resultados-2026-correspondencias-esperadas-e-efetivadas-2-turno",
    "resultados-2026-arquivos-transmitidos-para-totalizacao",
    "resultados-2026-logs-do-sistema-de-preparacao-das-urnas-eletronicas-gedai-1-turno",
    "resultados-2026-logs-do-sistema-de-preparacao-das-urnas-eletronicas-gedai-2-turno",
    "eleitorado-2026",
    "candidatos-2026",
]


def recursos(slug: str, client: httpx.Client | None = None) -> pd.DataFrame:
    """Lista os arquivos (recursos) de um dataset do portal."""
    http = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60)
    resp = http.get(f"{CKAN}/package_search", params={"fq": f"name:{slug}", "rows": 5})
    resp.raise_for_status()
    pacote = next((p for p in resp.json()["result"]["results"] if p["name"] == slug), None)
    if pacote is None:
        raise ValueError(f"dataset não encontrado no portal: {slug}")
    return pd.DataFrame(
        [
            {
                "dataset": slug,
                "recurso": r.get("name"),
                "formato": (r.get("format") or "").upper(),
                "url": r.get("url"),
                "tamanho": r.get("size"),
                "modificado": r.get("last_modified") or r.get("metadata_modified"),
                "no_catalogo": True,
            }
            for r in pacote.get("resources", [])
        ]
    )


def fora_do_catalogo(rec: pd.DataFrame, turno: int, http: httpx.Client) -> pd.DataFrame:
    """ZIPs de `turno` que estão no CDN do TSE mas não no catálogo, um por UF ausente.

    O modelo de URL vem dos ZIPs do mesmo turno no dataset (trocando só a UF) ou, se não houver nenhum, dos ZIPs
    do 1º turno (trocando `_1t_` por `_{turno}t_`). Uma URL candidata só entra se o HEAD responder 200. O `.sha512`
    oficial correspondente entra junto quando existe."""
    zips = rec[rec["url"].str.endswith(".zip")]
    padrao = re.compile(rf"_{turno}t_([A-Z]{{2}})(?=[_.])")
    modelos = [u for u in zips["url"] if padrao.search(u)]
    if not modelos and turno != 1:
        modelos = [re.sub(r"_1t_", f"_{turno}t_", u) for u in zips["url"] if re.search(r"_1t_[A-Z]{2}(?=[_.])", u)]
    presentes = {padrao.search(u).group(1) for u in zips["url"] if padrao.search(u)}
    ausentes = [uf for uf in UFS if uf not in presentes]
    if not modelos or not ausentes:
        return rec.iloc[0:0]
    novos = []
    for uf in ausentes:
        candidatas = dict.fromkeys(padrao.sub(f"_{turno}t_{uf}", u, count=1) for u in modelos)
        for url in candidatas:
            if http.head(url).status_code != 200:
                continue
            novos.append({"dataset": rec["dataset"].iloc[0], "recurso": f"{uf} (fora do catálogo)", "formato": "ZIP",
                          "url": url, "tamanho": None, "modificado": None, "no_catalogo": False})
            if http.head(url + ".sha512").status_code == 200:
                novos.append({**novos[-1], "formato": "SHA512", "url": url + ".sha512"})
            break
    return pd.DataFrame(novos, columns=rec.columns)


def recursos_turno(slug: str, turno: int, http: httpx.Client) -> pd.DataFrame:
    """Recursos do catálogo mais os arquivos do turno que só existem no CDN."""
    rec = recursos(slug, http)
    return pd.concat([rec, fora_do_catalogo(rec, turno, http)], ignore_index=True)


def catalogo(slugs: list[str] = DATASETS_2026) -> pd.DataFrame:
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60) as http:
        return pd.concat([recursos(s, http) for s in slugs], ignore_index=True)
