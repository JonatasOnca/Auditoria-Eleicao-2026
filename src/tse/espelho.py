"""Espelho local dos arquivos brutos do TSE (BU, RDV, log e assinaturas de cada seção).

Baixa para `data/raw/<dataset>/` os ZIPs oficiais do Portal de Dados Abertos, os mesmos arquivos
que o site de resultados serve seção a seção em "Dados de Urna" (comparados byte a byte em
2026-10-12). Os ZIPs ficam como estão, sem extrair (são ~2 milhões de arquivos).

Integridade de cada arquivo baixado:
- tamanho igual ao `content-length` do servidor;
- SHA-512 conferido contra o `.sha512` oficial, quando o TSE publica (o BU tem; os arquivos de urna não);
- CRC de todas as entradas do ZIP (`ZipFile.testzip`);
- SHA-512 calculado e registrado em `manifests/espelho_<dataset>.csv`.

O download é retomável (HTTP Range). Basta rodar de novo depois de uma interrupção.
"""

from __future__ import annotations

import argparse
import hashlib
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd

from tse import ckan
from tse.resultados_api import USER_AGENT

DATASETS = [
    "resultados-2026-boletim-de-urna",
    "resultados-2026-arquivos-transmitidos-para-totalizacao",
]
BLOCO = 8 * 1024 * 1024


def baixar(http: httpx.Client, url: str, destino: Path) -> int:
    tamanho = int(http.head(url).raise_for_status().headers["content-length"])
    parcial = destino.with_suffix(destino.suffix + ".parcial")
    if destino.exists() and destino.stat().st_size == tamanho:
        return tamanho
    feito = parcial.stat().st_size if parcial.exists() else 0
    while feito < tamanho:
        try:
            with http.stream("GET", url, headers={"Range": f"bytes={feito}-"}) as r:
                r.raise_for_status()
                with parcial.open("ab") as f:
                    for bloco in r.iter_bytes(BLOCO):
                        f.write(bloco)
                        feito += len(bloco)
        except httpx.HTTPError as e:
            print(f"   conexão interrompida em {feito / 1e9:.2f} GB ({e!r}); retomando", flush=True)
            feito = parcial.stat().st_size
    if feito != tamanho:
        raise ValueError(f"tamanho {feito} != {tamanho} para {url}")
    parcial.rename(destino)
    return tamanho


def sha512(caminho: Path) -> str:
    h = hashlib.sha512()
    with caminho.open("rb") as f:
        while bloco := f.read(BLOCO):
            h.update(bloco)
    return h.hexdigest()


def main() -> None:
    p = argparse.ArgumentParser(description="Espelho local dos arquivos brutos do TSE (2026, 1º turno)")
    p.add_argument("--dataset", action="append", help="slug CKAN (padrão: BU e arquivos de urna)")
    p.add_argument("--uf", action="append")
    p.add_argument("--raiz", default="data/raw")
    a = p.parse_args()

    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=httpx.Timeout(60, read=300),
                      follow_redirects=False) as http:
        for slug in a.dataset or DATASETS:
            rec = ckan.recursos(slug, http)
            urls = set(rec["url"])
            zips = rec[rec["url"].str.endswith(".zip")].copy()
            zips["uf"] = zips["url"].str.extract(r"_([A-Z]{2})(?:_\d{12})?\.zip$")[0]
            if a.uf:
                zips = zips[zips["uf"].isin([u.upper() for u in a.uf])]
            zips["bytes"] = [int(http.head(u).headers["content-length"]) for u in zips["url"]]
            zips = zips.sort_values("bytes")
            pasta = Path(a.raiz) / slug
            pasta.mkdir(parents=True, exist_ok=True)
            manifesto_csv = Path("manifests") / f"espelho_{slug}.csv"
            manifesto = pd.read_csv(manifesto_csv) if manifesto_csv.exists() else pd.DataFrame()
            print(f"== {slug}: {len(zips)} arquivos, {zips['bytes'].sum() / 1e9:.1f} GB", flush=True)

            for r in zips.itertuples():
                destino = pasta / r.url.rsplit("/", 1)[1]
                if len(manifesto) and (manifesto["arquivo"] == destino.name).any() and destino.exists():
                    print(f"[{r.uf}] já baixado e verificado", flush=True)
                    continue
                inicio = datetime.now(timezone.utc)
                tamanho = baixar(http, r.url, destino)
                digest = sha512(destino)
                oficial = None
                if r.url + ".sha512" in urls:
                    oficial = http.get(r.url + ".sha512").raise_for_status().text.split()[0].lower()
                    if oficial != digest:
                        destino.rename(destino.with_suffix(".zip.SHA_DIVERGENTE"))
                        raise ValueError(f"SHA-512 não confere: {r.url}")
                with zipfile.ZipFile(destino) as z:
                    corrompido = z.testzip()
                    entradas = len(z.infolist())
                if corrompido:
                    raise ValueError(f"CRC inválido em {corrompido} dentro de {destino}")
                linha = {"dataset": slug, "uf": r.uf, "arquivo": destino.name, "url": r.url, "bytes": tamanho,
                         "entradas_zip": entradas, "sha512": digest, "sha512_oficial": oficial,
                         "crc_ok": True, "baixado_em": inicio.isoformat()}
                manifesto = pd.concat([manifesto, pd.DataFrame([linha])], ignore_index=True)
                manifesto.to_csv(manifesto_csv, index=False)
                print(f"[{r.uf}] {tamanho / 1e9:.2f} GB, {entradas} entradas, CRC ok, "
                      f"SHA-512 {'conferido com o oficial' if oficial else 'registrado (sem .sha512 oficial)'}",
                      flush=True)


if __name__ == "__main__":
    main()
