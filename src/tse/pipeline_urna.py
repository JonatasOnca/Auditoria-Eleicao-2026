"""Arquivos de urna de um turno, UF por UF, sem manter o espelho inteiro em disco.

Os ZIPs de arquivos de urna do 2º turno somam ~134 GB, mais do que o espaço livre. Para cada UF, das menores para
as maiores:
1. espelha o ZIP (tse.espelho: tamanho, CRC, SHA-512 no manifesto) e o copia para o bucket bronze;
2. extrai as variáveis por seção dos logs (tse.urna_logs, lendo do disco);
3. converte os logs para Parquet e substitui a partição da UF em `log_urna[_2t]` (tse.bq_raw);
4. apaga o ZIP local (a cópia verificada fica no bronze e o hash no manifesto).

Cada etapa é pulada se já foi feita, então basta rodar de novo depois de uma interrupção. Se o ZIP local já tiver
sido apagado e faltar alguma etapa, ele é baixado de volta do bronze e conferido contra o SHA-512 do manifesto.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import httpx

from tse import bq_raw, espelho, urna_logs
from tse.resultados_api import USER_AGENT


def recuperar_do_bronze(bucket, slug: str, destino: Path) -> None:
    linha = espelho.ultima_versao(espelho.ler_manifesto(slug), destino.name)
    nome = linha["gcs_uri"].split(f"gs://{bucket.name}/", 1)[1]
    print(f"[{linha['uf']}] baixando {destino.name} de volta do bronze", flush=True)
    bucket.blob(nome).download_to_filename(str(destino), checksum="crc32c", timeout=3600)
    if espelho.sha512(destino) != linha["sha512"]:
        destino.unlink()
        raise ValueError(f"SHA-512 da cópia no bronze não confere com o manifesto: {nome}")


def main() -> None:
    p = argparse.ArgumentParser(description="Arquivos de urna UF por UF: espelho, bronze, variáveis dos logs e BigQuery")
    p.add_argument("--turno", type=int, choices=[1, 2], default=2)
    p.add_argument("--uf", action="append")
    p.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    p.add_argument("--conexoes", type=int, default=12)
    p.add_argument("--manter-zip", action="store_true", help="não apaga o ZIP local no fim de cada UF")
    a = p.parse_args()

    t = a.turno
    slug = bq_raw.DS_URNA
    tabela = "log_urna" if t == 1 else f"log_urna_{t}t"
    saida_logs = Path(f"data/logs_2026_{t}t")
    saida_logs.mkdir(parents=True, exist_ok=True)
    pasta = bq_raw.RAIZ / slug
    pasta.mkdir(parents=True, exist_ok=True)

    bucket, bq = bq_raw.clientes()
    bq_raw.criar_log_urna(bq, tabela)
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=httpx.Timeout(60, read=300)) as http:
        zips = espelho.zips_do_dataset(http, slug, t, a.uf)
        zips = zips[zips["url"].str.contains(rf"_{t}t_[A-Z]{{2}}\.zip$")]
        print(f"== {slug}, {t}º turno: {len(zips)} UFs, {zips['bytes'].sum() / 1e9:.1f} GB", flush=True)
        for r in zips.itertuples():
            destino = pasta / r.url.rsplit("/", 1)[1]
            falta_logs = not (saida_logs / f"secoes_{r.uf}.parquet").exists()
            falta_bq = not bq_raw.ja_carregado(tabela, r.uf)
            if not (falta_logs or falta_bq):
                print(f"[{r.uf}] completo", flush=True)
                continue
            local = espelho.espelhar_zip(http, slug, r.url, r.uf, pasta, r.url_sha, r.no_catalogo, bucket)
            if local is None:
                recuperar_do_bronze(bucket, slug, destino)
            if falta_logs:
                urna_logs.processar_uf(r.url, r.uf, saida_logs, a.conexoes, bq_raw.RAIZ, t)
            if falta_bq:
                bq_raw.carregar_log_urna_uf(r.uf, t, bucket, bq, a.workers, manter=False)
            if not a.manter_zip:
                espelho.apagar_local(slug, destino)
                print(f"[{r.uf}] ZIP local apagado (cópia no bronze)", flush=True)


if __name__ == "__main__":
    main()
