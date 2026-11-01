"""Espelho local dos arquivos brutos do TSE (BU, RDV, log e assinaturas de cada seção).

Baixa para `data/raw/<dataset>/` os ZIPs oficiais do Portal de Dados Abertos, os mesmos arquivos
que o site de resultados serve seção a seção em "Dados de Urna" (comparados byte a byte em
2026-10-12). Os ZIPs ficam como estão, sem extrair (são ~2 milhões de arquivos).

Integridade de cada arquivo baixado:
- tamanho igual ao `content-length` do servidor;
- SHA-512 conferido contra o `.sha512` oficial, quando o TSE publica (o BU tem; os arquivos de urna não);
- CRC de todas as entradas do ZIP (`ZipFile.testzip`);
- SHA-512 calculado e registrado em `manifests/espelho_<dataset>.csv`.

O download usa várias conexões HTTP Range por arquivo e é retomável. Basta rodar de novo depois de uma interrupção.

Arquivos republicados: o TSE às vezes publica uma nova versão com o mesmo nome (em 2026-10-26, os arquivos de
`resultados-2026` passaram a trazer os dois turnos). Um arquivo já espelhado é baixado de novo quando o CDN informa
um `Last-Modified` posterior ao download ou um tamanho diferente. A versão anterior vai para
`<dataset>/_substituidos/<data do download>/` e a nova linha do manifesto guarda o SHA-512 dela em `substitui`.

Com `--enviar-bronze`, cada ZIP verificado é copiado para `gs://<bucket>/tse/zip/<dataset>/`. Um objeto já idêntico
no bucket não é reenviado; um objeto diferente é preservado em `<dataset>/_substituidos/` antes de ser substituído
(`enviar_bronze`), então o bronze nunca perde uma versão. Com
`--apagar-apos-envio`, a cópia local é apagada depois que o GCS confirma o tamanho (o upload já confere o crc32c);
o manifesto marca `local=False` e guarda o `gcs_uri`.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
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
CONEXOES = 8  # faixas HTTP Range simultâneas por arquivo (ver `baixar`)
ESPERA_FAIXA_S = 10
PARADO_S = 120  # sem nenhum byte por esse tempo, a conexão é dada como morta e o download é retomado em outra
PREFIXO_ZIP = "tse/zip"
RE_UF = r"_([A-Z]{2})(?:_\d{12})?\.zip$"


def baixar(http: httpx.Client, url: str, destino: Path, conexoes: int = CONEXOES) -> int:
    """Baixa `url` em `conexoes` faixas HTTP Range simultâneas.

    O CDN do TSE limita a vazão por conexão: em 2026-10-29 uma conexão dava ~2 MB/s e quatro juntas ~10 MB/s.
    O que falta depois do `.parcial` é dividido em faixas; cada faixa vai para `<arquivo>.parcial.<início>-<fim>` e
    é retomável pelo próprio tamanho. No fim as faixas são anexadas em ordem ao `.parcial`, que vira o arquivo.
    """
    tamanho = int(http.head(url).raise_for_status().headers["content-length"])
    parcial = destino.with_suffix(destino.suffix + ".parcial")
    if destino.exists() and destino.stat().st_size == tamanho:
        return tamanho
    feito = parcial.stat().st_size if parcial.exists() else 0
    faixas = sorted(
        (int(m[1]), int(m[2]), f)
        for f in parcial.parent.glob(parcial.name + ".*-*")
        if (m := re.search(r"\.(\d+)-(\d+)$", f.name))
    )
    faixas = completar_faixas(faixas, feito, tamanho, parcial)
    if faixas is None:
        passo = -(-(tamanho - feito) // conexoes)
        faixas = [(i, min(i + passo, tamanho), nome_faixa(parcial, i, min(i + passo, tamanho)))
                  for i in range(feito, tamanho, passo)]
    if faixas:
        with ThreadPoolExecutor(len(faixas)) as ex:
            list(ex.map(lambda fx: baixar_faixa(http, url, *fx), faixas))
        if any(a[1] != b[0] for a, b in zip(faixas, faixas[1:])) or faixas[0][0] != feito or faixas[-1][1] != tamanho:
            raise ValueError(f"faixas não contíguas para {url}")
        with parcial.open("ab") as saida:
            for _, _, f in faixas:
                with f.open("rb") as entrada:
                    shutil.copyfileobj(entrada, saida, BLOCO)
                f.unlink()
    feito = parcial.stat().st_size
    if feito != tamanho:
        raise ValueError(f"tamanho {feito} != {tamanho} para {url}")
    parcial.rename(destino)
    return tamanho


def nome_faixa(parcial: Path, inicio: int, fim: int) -> Path:
    return parcial.with_name(f"{parcial.name}.{inicio}-{fim}")


def completar_faixas(faixas: list, feito: int, tamanho: int, parcial: Path) -> list | None:
    """Faixas de uma execução anterior, com as lacunas preenchidas por faixas novas.

    Uma faixa cuja conexão caiu antes do primeiro byte não deixa arquivo; sem preencher a lacuna, a junção pularia
    esses bytes (aconteceu em 2026-10-29 com CE e foi barrado pela checagem de tamanho). Devolve None, apagando os
    arquivos, se não houver faixas ou se elas não couberem em [feito, tamanho) sem sobreposição.
    """
    completas, pos = [], feito
    for i, j, f in faixas:
        if i < pos or j > tamanho:
            completas = []
            break
        if i > pos:
            completas.append((pos, i, nome_faixa(parcial, pos, i)))
        completas.append((i, j, f))
        pos = j
    if not completas:
        for *_, f in faixas:
            f.unlink()
        return None
    if pos < tamanho:
        completas.append((pos, tamanho, nome_faixa(parcial, pos, tamanho)))
    return completas


def baixar_faixa(http: httpx.Client, url: str, inicio: int, fim: int, arquivo: Path) -> None:
    """Bytes [inicio, fim) de `url` em `arquivo`, retomando de onde parou."""
    feito = arquivo.stat().st_size if arquivo.exists() else 0
    while inicio + feito < fim:
        # Em 2026-10-28 uma queda de internet deixou a conexão aberta e muda por 50 min sem que o timeout de leitura
        # do httpx disparasse. O vigia fecha a resposta se nenhum byte chegar em PARADO_S, o que destrava a leitura.
        ultimo = [time.monotonic()]
        parar = threading.Event()
        try:
            with http.stream("GET", url, headers={"Range": f"bytes={inicio + feito}-{fim - 1}"}) as r:
                r.raise_for_status()
                if r.status_code != 206:
                    raise ValueError(f"o servidor ignorou o Range (HTTP {r.status_code}) para {url}")

                def vigiar():
                    while not parar.wait(10):
                        if time.monotonic() - ultimo[0] > PARADO_S:
                            print(f"   nenhum byte em {PARADO_S}s; fechando a conexão", flush=True)
                            r.close()
                            return

                threading.Thread(target=vigiar, daemon=True).start()
                with arquivo.open("ab") as f:
                    for bloco in r.iter_raw(1 << 20):
                        f.write(bloco)
                        feito += len(bloco)
                        ultimo[0] = time.monotonic()
        except (httpx.HTTPError, httpx.StreamError, OSError) as e:
            print(f"   conexão interrompida na faixa {inicio}-{fim} ({e!r}); retomando em {ESPERA_FAIXA_S}s", flush=True)
            time.sleep(ESPERA_FAIXA_S)
        finally:
            parar.set()
        # Se a conexão cai antes do primeiro byte (ex.: DNS fora do ar), o arquivo da faixa nem chega a existir.
        feito = arquivo.stat().st_size if arquivo.exists() else 0
    if inicio + feito != fim:
        raise ValueError(f"faixa {inicio}-{fim} com {feito} bytes para {url}")


def sha512(caminho: Path) -> str:
    h = hashlib.sha512()
    with caminho.open("rb") as f:
        while bloco := f.read(BLOCO):
            h.update(bloco)
    return h.hexdigest()


def do_turno(urls: pd.Series, turno: int | None) -> pd.Series:
    """Máscara dos arquivos de `turno`. Arquivos sem turno no nome (ex.: `votacao_secao_2026_AC.zip`) entram sempre."""
    if turno is None:
        return pd.Series(True, index=urls.index)
    marcado = urls.str.contains(r"_\dt_", case=False)
    return ~marcado | urls.str.contains(rf"_{turno}t_", case=False)


def manifesto_csv(slug: str) -> Path:
    return Path("manifests") / f"espelho_{slug}.csv"


def ler_manifesto(slug: str) -> pd.DataFrame:
    f = manifesto_csv(slug)
    return pd.read_csv(f, dtype=str) if f.exists() else pd.DataFrame()


def gravar_linha(slug: str, linha: dict) -> None:
    m = pd.concat([ler_manifesto(slug), pd.DataFrame([linha])], ignore_index=True)
    m.to_csv(manifesto_csv(slug), index=False)


def ultima_versao(manifesto: pd.DataFrame, nome: str) -> dict | None:
    if not len(manifesto):
        return None
    m = manifesto[manifesto["arquivo"] == nome]
    return m.iloc[-1].to_dict() if len(m) else None


def mudou_no_servidor(anterior: dict, tamanho: int, last_modified: str | None) -> bool:
    """O CDN tem uma versão diferente da que foi espelhada?"""
    if int(float(anterior["bytes"])) != tamanho:
        return True
    if last_modified:
        return parsedate_to_datetime(last_modified) > datetime.fromisoformat(anterior["baixado_em"])
    return False


def crc32c_b64(caminho: Path) -> str:
    """CRC32C do arquivo no formato que o GCS informa em `Blob.crc32c` (base64 dos 4 bytes, big-endian)."""
    import base64

    import google_crc32c

    c = google_crc32c.Checksum()
    with caminho.open("rb") as f:
        while bloco := f.read(BLOCO):
            c.update(bloco)
    return base64.b64encode(c.digest()).decode()


def enviar_bronze(bucket, local: Path, slug: str, substituido: str | None = None) -> str:
    """Copia o ZIP para o bucket bronze sem nunca perder a versão que já estava lá.

    - Objeto já existente e idêntico (tamanho e CRC32C): não reenvia.
    - Objeto existente e diferente: copia antes para `_substituidos/<marca>/`. A marca é `substituido` (data do
      download da versão anterior, vinda do manifesto) ou, sem ela, a data de atualização do objeto no bucket.
      Isso cobre objetos enviados por outro processo, que o manifesto não registrou.
    """
    nome = f"{PREFIXO_ZIP}/{slug}/{local.name}"
    blob = bucket.get_blob(nome)
    if blob is not None:
        if blob.size == local.stat().st_size and blob.crc32c == crc32c_b64(local):
            return f"gs://{bucket.name}/{nome}"
        marca = substituido or blob.updated.strftime("%Y%m%dT%H%M%S")
        bucket.copy_blob(blob, bucket, f"{PREFIXO_ZIP}/{slug}/_substituidos/{marca}/{local.name}")
    blob = bucket.blob(nome)
    from tse.bq_raw import retry_gcs

    blob.upload_from_filename(str(local), checksum="crc32c", timeout=3600, retry=retry_gcs())
    blob.reload()
    if blob.size != local.stat().st_size:
        raise ValueError(f"tamanho no GCS {blob.size} != local {local.stat().st_size} para {nome}")
    return f"gs://{bucket.name}/{nome}"


def atualizar_ultima(slug: str, nome: str, **campos) -> None:
    """Atualiza a linha mais recente de `nome` no manifesto (sem criar uma nova versão)."""
    m = ler_manifesto(slug)
    i = m.index[m["arquivo"] == nome][-1]
    for k, v in campos.items():
        if k not in m:
            m[k] = None
        m.at[i, k] = str(v)
    m.to_csv(manifesto_csv(slug), index=False)


def apagar_local(slug: str, destino: Path) -> None:
    """Apaga a cópia local de um ZIP que já está no bronze e marca isso no manifesto."""
    if not str(ultima_versao(ler_manifesto(slug), destino.name).get("gcs_uri")).startswith("gs://"):
        raise ValueError(f"{destino.name} não tem cópia no bronze; não apago")
    destino.unlink()
    atualizar_ultima(slug, destino.name, local=False)


def espelhar_zip(http: httpx.Client, slug: str, url: str, uf: str, pasta: Path, url_sha: str | None = None,
                 no_catalogo: bool = True, bucket=None, apagar: bool = False) -> Path | None:
    """Baixa e verifica um ZIP (ou confirma que a versão espelhada é a atual). Devolve o caminho local, ou None se
    o arquivo já está espelhado só no bronze."""
    cab = http.head(url).raise_for_status().headers
    tamanho_srv, last_modified, etag = int(cab["content-length"]), cab.get("last-modified"), cab.get("etag")
    destino = pasta / url.rsplit("/", 1)[1]
    anterior = ultima_versao(ler_manifesto(slug), destino.name)
    substitui = velho = None
    if anterior is not None:
        no_bronze = str(anterior.get("gcs_uri", "")).startswith("gs://")
        if not mudou_no_servidor(anterior, tamanho_srv, last_modified) and (destino.exists() or no_bronze):
            if bucket is not None and not no_bronze and destino.exists():
                atualizar_ultima(slug, destino.name, gcs_uri=enviar_bronze(bucket, destino, slug))
            print(f"[{uf}] {destino.name} já baixado e verificado", flush=True)
            return destino if destino.exists() else None
        if mudou_no_servidor(anterior, tamanho_srv, last_modified):
            substitui = anterior["sha512"]
            marca = re.sub(r"[^0-9T]", "", anterior["baixado_em"])[:15]
            if destino.exists():
                velho = pasta / "_substituidos" / marca / destino.name
                velho.parent.mkdir(parents=True, exist_ok=True)
                destino.rename(velho)
            print(f"[{uf}] {destino.name} foi republicado pelo TSE ({last_modified}); baixando a nova versão",
                  flush=True)

    inicio = datetime.now(timezone.utc)
    tamanho = baixar(http, url, destino)
    digest = sha512(destino)
    oficial = None
    if url_sha:
        oficial = http.get(url_sha).raise_for_status().text.split()[0].lower()
        if oficial != digest:
            destino.rename(destino.with_suffix(".zip.SHA_DIVERGENTE"))
            raise ValueError(f"SHA-512 não confere: {url}")
    with zipfile.ZipFile(destino) as z:
        corrompido = z.testzip()
        entradas = len(z.infolist())
    if corrompido:
        raise ValueError(f"CRC inválido em {corrompido} dentro de {destino}")
    if substitui == digest:  # só o Last-Modified mudou; o conteúdo é o mesmo
        print(f"[{uf}] {destino.name}: conteúdo idêntico ao já espelhado", flush=True)
        substitui = None
        if velho is not None:
            velho.unlink()
    uri = None
    if bucket is not None:
        uri = enviar_bronze(bucket, destino, slug, marca if substitui else None)
    gravar_linha(slug, {"dataset": slug, "uf": uf, "arquivo": destino.name, "url": url, "bytes": tamanho,
                        "entradas_zip": entradas, "sha512": digest, "sha512_oficial": oficial, "crc_ok": True,
                        "baixado_em": inicio.isoformat(), "last_modified": last_modified, "etag": etag,
                        "no_catalogo": no_catalogo, "substitui": substitui, "gcs_uri": uri, "local": True})
    print(f"[{uf}] {destino.name}: {tamanho / 1e9:.2f} GB, {entradas} entradas, CRC ok, "
          f"SHA-512 {'conferido com o oficial' if oficial else 'registrado (sem .sha512 oficial)'}"
          f"{'' if no_catalogo else ', fora do catálogo'}{', enviado ao bronze' if uri else ''}", flush=True)
    if apagar:
        apagar_local(slug, destino)
        return None
    return destino


def zips_do_dataset(http: httpx.Client, slug: str, turno: int | None, ufs: list[str] | None = None) -> pd.DataFrame:
    """ZIPs a espelhar (catálogo + fora do catálogo), com UF, `.sha512` oficial e tamanho, dos menores aos maiores."""
    rec = ckan.recursos_turno(slug, turno, http) if turno else ckan.recursos(slug, http)
    urls = set(rec["url"])
    zips = rec[rec["url"].str.endswith(".zip") & do_turno(rec["url"], turno)].copy()
    zips["uf"] = zips["url"].str.extract(RE_UF)[0]
    if ufs:
        zips = zips[zips["uf"].isin([u.upper() for u in ufs])]
    zips["url_sha"] = [u + ".sha512" if u + ".sha512" in urls else None for u in zips["url"]]
    zips["bytes"] = [int(http.head(u).headers["content-length"]) for u in zips["url"]]
    return zips.sort_values("bytes")


def main() -> None:
    p = argparse.ArgumentParser(description="Espelho local dos arquivos brutos do TSE (2026)")
    p.add_argument("--dataset", action="append", help="slug CKAN (padrão: BU e arquivos de urna)")
    p.add_argument("--turno", type=int, choices=[1, 2],
                   help="só arquivos deste turno (os sem turno no nome entram sempre); procura também fora do catálogo")
    p.add_argument("--uf", action="append")
    p.add_argument("--raiz", default="data/raw")
    p.add_argument("--enviar-bronze", action="store_true", help="copia cada ZIP verificado para o bucket bronze")
    p.add_argument("--apagar-apos-envio", action="store_true", help="apaga o ZIP local depois do envio ao bronze")
    a = p.parse_args()
    if a.apagar_apos_envio and not a.enviar_bronze:
        p.error("--apagar-apos-envio exige --enviar-bronze")

    bucket = None
    if a.enviar_bronze:
        from tse.bq_raw import clientes

        bucket, _ = clientes()
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=httpx.Timeout(60, read=300),
                      follow_redirects=False) as http:
        for slug in a.dataset or DATASETS:
            zips = zips_do_dataset(http, slug, a.turno, a.uf)
            pasta = Path(a.raiz) / slug
            pasta.mkdir(parents=True, exist_ok=True)
            print(f"== {slug}: {len(zips)} arquivos, {zips['bytes'].sum() / 1e9:.1f} GB", flush=True)
            for r in zips.itertuples():
                espelhar_zip(http, slug, r.url, r.uf, pasta, r.url_sha, r.no_catalogo, bucket, a.apagar_apos_envio)


if __name__ == "__main__":
    main()
