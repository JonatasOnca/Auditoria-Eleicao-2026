"""Inventário do bronze `gs://<bucket>/tse/zip/`: o que o TSE publica × o que está no bucket × o que está local.

Somente leitura (salvo `--corrigir-manifesto`). Para cada arquivo:
- **TSE**: a última versão registrada em `manifests/espelho_<dataset>.csv` e o tamanho atual no CDN (HEAD). Os
  datasets de 2026 do catálogo CKAN que nunca foram espelhados entram também, com os ZIPs listados no catálogo;
- **bucket**: o objeto `tse/zip/<dataset>/<arquivo>` (tamanho, CRC32C, data); `_substituidos/` não conta;
- **local**: `data/raw/<dataset>/<arquivo>`, se existir (CRC32C calculado).

Situações:
- `ok`: o objeto do bucket tem o tamanho do CDN e, havendo cópia local do mesmo tamanho, o mesmo CRC32C;
- `falta_no_bucket`: não está no bucket, mas a versão atual está local (basta enviar);
- `so_no_cdn`: não está no bucket nem local (precisa baixar);
- `desatualizado_no_bucket`: o bucket tem um tamanho diferente do CDN (o TSE republicou);
- `divergente`: bucket e cópia local têm o mesmo tamanho e CRC32C diferente.

Sem cópia local, a igualdade bucket × CDN é só por tamanho (o CDN não informa hash dos arquivos de urna).

Com `--corrigir-manifesto`, as linhas `ok` cujo manifesto não tem `gcs_uri` (envios feitos por outro processo)
passam a registrá-lo.

Uso: `uv run --extra gcp python -m tse.bronze_inventario [--dataset SLUG ...] [--corrigir-manifesto]`
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import httpx
import pandas as pd

from tse import espelho
from tse.resultados_api import USER_AGENT

CKAN = "https://dadosabertos.tse.jus.br/api/3/action"


def datasets_2026(http: httpx.Client) -> dict[str, list[str]]:
    """Datasets de 2026 do catálogo CKAN e as URLs dos ZIPs de cada um."""
    r = http.get(f"{CKAN}/package_search", params={"q": "2026", "rows": 500}).raise_for_status().json()
    return {p["name"]: [x["url"] for x in p["resources"] if x["url"].endswith(".zip")]
            for p in r["result"]["results"]}


def tamanho_cdn(http: httpx.Client, url: str) -> int | None:
    try:
        return int(http.head(url).raise_for_status().headers["content-length"])
    except (httpx.HTTPError, KeyError, ValueError):
        return None


def situacao(cdn: int | None, obj, local: Path) -> str:
    if obj is None:
        return "falta_no_bucket" if local.exists() and local.stat().st_size == cdn else "so_no_cdn"
    if cdn is not None and obj.size != cdn:
        return "desatualizado_no_bucket"
    if local.exists() and local.stat().st_size == obj.size and espelho.crc32c_b64(local) != obj.crc32c:
        return "divergente"
    return "ok"


def inventario(bucket, http: httpx.Client, slugs: list[str], catalogo: dict[str, list[str]], raiz: Path):
    linhas = []
    for slug in slugs:
        prefixo = f"{espelho.PREFIXO_ZIP}/{slug}/"
        objetos = {b.name[len(prefixo):]: b for b in bucket.client.list_blobs(bucket, prefix=prefixo)
                   if "/_substituidos/" not in b.name}
        m = espelho.ler_manifesto(slug).drop_duplicates("arquivo", keep="last")
        arquivos = {r.arquivo: r.url for r in m.itertuples()}
        for url in catalogo.get(slug, []):
            arquivos.setdefault(url.rsplit("/", 1)[1], url)
        with ThreadPoolExecutor(8) as ex:
            cdn = dict(zip(arquivos, ex.map(lambda u: tamanho_cdn(http, u), arquivos.values())))
        reg = m.set_index("arquivo") if len(m) else None
        for arq, url in sorted(arquivos.items()):
            obj, local = objetos.get(arq), raiz / slug / arq
            no_manifesto = reg is not None and arq in reg.index
            linhas.append({
                "dataset": slug, "arquivo": arq, "url": url, "no_manifesto": no_manifesto,
                "bytes_manifesto": int(reg.at[arq, "bytes"]) if no_manifesto else None,
                "bytes_cdn": cdn[arq], "bytes_bucket": obj.size if obj else None,
                "crc32c_bucket": obj.crc32c if obj else None,
                "atualizado_bucket": obj.updated.isoformat() if obj else None,
                "local": local.exists(),
                "gcs_uri_manifesto": str(reg.at[arq, "gcs_uri"]) if no_manifesto and "gcs_uri" in reg else None,
                "situacao": situacao(cdn[arq], obj, local),
            })
        print(f"[{slug}] {len(arquivos)} arquivos", flush=True)
    return pd.DataFrame(linhas)


def main() -> None:
    p = argparse.ArgumentParser(description="Inventário do bronze tse/zip (somente leitura)")
    p.add_argument("--dataset", action="append", help="limita aos datasets (padrão: manifestos + catálogo 2026)")
    p.add_argument("--raiz", default="data/raw")
    p.add_argument("--corrigir-manifesto", action="store_true",
                   help="registra o gcs_uri das linhas ok que o manifesto não tem")
    a = p.parse_args()

    from tse.bq_raw import clientes

    bucket, _ = clientes()
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60) as http:
        catalogo = datasets_2026(http)
        slugs = a.dataset or sorted({f.stem.removeprefix("espelho_") for f in Path("manifests").glob("espelho_*.csv")}
                                    | set(catalogo))
        df = inventario(bucket, http, slugs, catalogo, Path(a.raiz))

    saida = Path("manifests") / f"inventario_bronze_{date.today().isoformat()}.csv"
    df.to_csv(saida, index=False)
    print(df.groupby(["dataset", "situacao"]).size().unstack(fill_value=0).to_string())
    print(f"\nTotal: {df['situacao'].value_counts().to_dict()}  ->  {saida}")

    if a.corrigir_manifesto:
        alvo = df[(df["situacao"] == "ok") & df["no_manifesto"]
                  & ~df["gcs_uri_manifesto"].fillna("").str.startswith("gs://")]
        for r in alvo.itertuples():
            espelho.atualizar_ultima(r.dataset, r.arquivo,
                                     gcs_uri=f"gs://{bucket.name}/{espelho.PREFIXO_ZIP}/{r.dataset}/{r.arquivo}")
        print(f"gcs_uri registrado em {len(alvo)} linhas de manifesto")


if __name__ == "__main__":
    main()
