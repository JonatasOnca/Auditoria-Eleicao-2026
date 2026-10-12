"""Catálogo do Portal de Dados Abertos do TSE (API CKAN).

A API CKAN só devolve metadados. Os dados em si são arquivos ZIP/CSV no CDN
(cdn.tse.jus.br) e são carregados para GCS/BigQuery na Fase 2.
"""

from __future__ import annotations

import httpx
import pandas as pd

from tse.resultados_api import USER_AGENT

CKAN = "https://dadosabertos.tse.jus.br/api/3/action"

DATASETS_2026 = [
    "resultados-2026",
    "resultados-2026-boletim-de-urna",
    "resultados-2026-correspondencias-esperadas-e-efetivadas-1-turno",
    "resultados-2026-arquivos-transmitidos-para-totalizacao",
    "resultados-2026-logs-do-sistema-de-preparacao-das-urnas-eletronicas-gedai-1-turno",
    "eleitorado-2026",
    "candidatos-2026",
]


def recursos(slug: str, client: httpx.Client | None = None) -> pd.DataFrame:
    """Lista os arquivos (recursos) de um dataset do portal."""
    http = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60)
    resp = http.get(f"{CKAN}/package_show", params={"id": slug})
    resp.raise_for_status()
    pacote = resp.json()["result"]
    return pd.DataFrame(
        [
            {
                "dataset": slug,
                "recurso": r.get("name"),
                "formato": (r.get("format") or "").upper(),
                "url": r.get("url"),
                "tamanho": r.get("size"),
                "modificado": r.get("last_modified") or r.get("metadata_modified"),
            }
            for r in pacote.get("resources", [])
        ]
    )


def catalogo(slugs: list[str] = DATASETS_2026) -> pd.DataFrame:
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60) as http:
        return pd.concat([recursos(s, http) for s in slugs], ignore_index=True)
