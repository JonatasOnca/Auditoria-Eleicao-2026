"""Carga das tabelas raw do TSE no BigQuery (`teconca-dev-data-solutions.auditoria_eleicao_2026_raw`).

Fonte: o espelho local `data/raw/` (tse.espelho), conferido por tamanho, CRC e SHA-512. O BigQuery não lê ZIP (e o log
da urna é ZIP dentro de ZIP), então cada arquivo é convertido para Parquet localmente, enviado para
`gs://teconca-dev-bronze-us-central1/tse/parquet/<tabela>/uf=<UF>/` e carregado com um job de load.

Regras das tabelas raw (o refinamento fica no Dataform):
- Todas as colunas dos CSVs como STRING, com o nome original do TSE e sem tratar `#NULO`, `-1` etc.
- Cada linha guarda `_arquivo_zip` e `_arquivo_interno`. URL, SHA-512 e hora do download de cada ZIP ficam na tabela
  `_arquivos`, que vem dos manifestos `manifests/espelho_*.csv`.
- `log_urna` e `log_gedai`: uma linha por linha do log, sem descartar nada. Linhas que não têm o número esperado de
  campos ficam inteiras em `linha_bruta`. O texto vai íntegro, inclusive os títulos de mesários (dataset restrito).
- Arquivos `_BR`/`_BRASIL` repetem a soma das UFs e não são carregados.
"""

from __future__ import annotations

import argparse
import os
import re
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from tse.urna_logs import logs_do_pacote

PROJETO = "teconca-dev-data-solutions"
DATASET_BQ = "auditoria_eleicao_2026_raw"
BUCKET = "teconca-dev-bronze-us-central1"
PREFIXO_GCS = "tse/parquet"
RAIZ = Path("data/raw")
TMP = Path("data/parquet_raw")
MANIFESTO = Path("manifests/bq_raw_carga.csv")

DS_URNA = "resultados-2026-arquivos-transmitidos-para-totalizacao"
DS_GEDAI = "resultados-2026-logs-do-sistema-de-preparacao-das-urnas-eletronicas-gedai-1-turno"

UFS = ["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR",
       "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO", "ZZ"]
UF_ID = {uf: i for i, uf in enumerate(UFS, 1)}  # partição por intervalo inteiro de log_urna

# Arquivo CSV (nome interno, minúsculo) -> tabela. Todo CSV do espelho tem de cair em uma tabela ou em IGNORAR.
TABELAS_CSV = {
    "boletim_urna": r"bweb_1t_",
    "votacao_secao": r"votacao_secao_2026_",
    "detalhe_votacao_secao": r"detalhe_votacao_secao_2026_",
    "votacao_candidato_munzona": r"votacao_candidato_munzona_2026_",
    "votacao_partido_munzona": r"votacao_partido_munzona_2026_",
    "detalhe_votacao_munzona": r"detalhe_votacao_munzona_2026_",
    "correspondencia_efetivada": r"ceft_1t_",
    "correspondencia_secao": r"csec_1t_",
    "correspondencia_contingencia": r"ccont_1t_",
    "modelo_urna": r"modelourna_numerointerno",
    "perfil_eleitor_secao": r"perfil_eleitor_secao_2026_",
    "perfil_eleitorado": r"perfil_eleitorado_2026_",
    "eleitorado_local_votacao": r"eleitorado_local_votacao_2026_",
    "perfil_eleitor_deficiencia": r"perfil_eleitor_deficiencia_2026_",
    "transferencia_temporaria": r"transferencia_temporaria_2026",
    "transferencia_temporaria_secao": r"transf_temporaria_secao_2026",
    "convocacao_mesarios": r"convocacao_mesarios_2026_",
    "convocacao_mesarios_funcoes_especiais": r"convocacao_mesarios_funcoes_especiais_2026_",
    "denuncia": r"denuncia_2026_",
    "municipio_tse_ibge": r"municipio_tse_ibge",
}
TABELAS_LOG = ["log_urna", "log_gedai"]
IGNORAR = re.compile(r"_(br|brasil)\.csv$", re.I)
RE_UF_CSV = re.compile(r"_([A-Z]{2})(?:_\d{12})?\.csv$")
RE_PACOTE = re.compile(r"o\d{5}([a-z]{2})(\d{5})(\d{4})(\d{4})-(log|logsa)\.jez$")
RE_UF_GEDAI = re.compile(r"log_gedai_1t_([A-Z]{2})_\d{12}\.zip$")

ESQUEMA_LOG_URNA = pa.schema([
    ("uf", pa.string()), ("uf_id", pa.int64()), ("cd_municipio", pa.string()), ("nr_zona", pa.string()),
    ("nr_secao", pa.string()), ("tipo_log", pa.string()), ("arquivo_logd", pa.string()), ("nr_linha", pa.int64()),
    ("data_hora", pa.string()), ("nivel", pa.string()), ("id_urna", pa.string()), ("aplicacao", pa.string()),
    ("mensagem", pa.string()), ("hash_log", pa.string()), ("linha_bruta", pa.string()),
])
CAMPOS_URNA = ["data_hora", "nivel", "id_urna", "aplicacao", "mensagem", "hash_log"]
ESQUEMA_LOG_GEDAI = pa.schema([
    ("uf", pa.string()), ("_arquivo_zip", pa.string()), ("arquivo_jez", pa.string()), ("arquivo_log", pa.string()),
    ("nr_linha", pa.int64()), ("data_hora", pa.string()), ("nivel", pa.string()), ("mensagem", pa.string()),
    ("hash_log", pa.string()), ("linha_bruta", pa.string()),
])
CAMPOS_GEDAI = ["data_hora", "nivel", "mensagem", "hash_log"]
LINHAS_POR_GRUPO = 1_000_000


# ------------------------------------------------------------------------- manifesto


def registrar(**linha) -> None:
    linha["quando"] = datetime.now(timezone.utc).isoformat()
    df = pd.DataFrame([linha])
    df.to_csv(MANIFESTO, mode="a", header=not MANIFESTO.exists(), index=False)


def ja_carregado(tabela: str, uf: str) -> bool:
    if not MANIFESTO.exists():
        return False
    m = pd.read_csv(MANIFESTO, dtype=str)
    return ((m["etapa"] == "carga") & (m["tabela"] == tabela) & (m["uf"] == uf)).any()


# ------------------------------------------------------------------------------ CSV


def arquivos_csv(ufs: set[str] | None) -> list[tuple[str, Path, str, str]]:
    """(tabela, zip, entrada, uf) de todo CSV do espelho, exceto logs. Para se algum CSV não tiver tabela."""
    saida, sem_tabela = [], []
    for z in sorted(RAIZ.glob("*/*.zip")):
        if z.parent.name in (DS_URNA, DS_GEDAI) or z.name.startswith("Relatorio_Resultado_Totalizacao"):
            continue
        for entrada in zipfile.ZipFile(z).namelist():
            if not entrada.lower().endswith(".csv") or IGNORAR.search(entrada):
                continue
            tabela = next((t for t, p in TABELAS_CSV.items() if re.match(p, entrada.lower())), None)
            if tabela is None:
                sem_tabela.append(f"{z.name}/{entrada}")
                continue
            m = RE_UF_CSV.search(entrada)
            uf = m.group(1) if m else "BR"
            if ufs and uf != "BR" and uf not in ufs:
                continue
            saida.append((tabela, z, entrada, uf))
    if sem_tabela:
        raise ValueError(f"CSVs sem tabela definida: {sem_tabela}")
    return saida


def converter_csv(z: Path, entrada: str, destino: Path) -> int:
    """CSV do TSE -> Parquet, tudo como texto. Tenta UTF-8 e, se houver byte inválido, relê como Latin-1."""
    for encoding in ("utf8", "latin1"):
        try:
            with zipfile.ZipFile(z) as zf:
                with zf.open(entrada) as f:
                    cabecalho = f.readline().decode("utf-8" if encoding == "utf8" else "latin-1")
                colunas = [c.strip().strip('"') for c in cabecalho.rstrip("\r\n").split(";")]
                with zf.open(entrada) as f:
                    leitor = pacsv.open_csv(
                        f,
                        read_options=pacsv.ReadOptions(encoding=encoding, block_size=64 << 20),
                        parse_options=pacsv.ParseOptions(delimiter=";", quote_char='"'),
                        convert_options=pacsv.ConvertOptions(
                            column_types={c: pa.string() for c in colunas},
                            strings_can_be_null=False, quoted_strings_can_be_null=False),
                    )
                    if leitor.schema.names != colunas:
                        raise ValueError(f"cabeçalho inesperado em {entrada}: {leitor.schema.names}")
                    extra = {"_arquivo_zip": z.name, "_arquivo_interno": entrada}
                    esquema = leitor.schema
                    for k in extra:
                        esquema = esquema.append(pa.field(k, pa.string()))
                    linhas = 0
                    with pq.ParquetWriter(destino, esquema, compression="zstd") as w:
                        for lote in leitor:
                            n = lote.num_rows
                            cols = lote.columns + [pa.array([v] * n, pa.string()) for v in extra.values()]
                            w.write_batch(pa.RecordBatch.from_arrays(cols, schema=esquema))
                            linhas += n
            return linhas
        except pa.ArrowInvalid as e:
            if encoding == "utf8" and "UTF8" in str(e).upper():
                continue
            raise
    raise AssertionError("inalcançável")


# ------------------------------------------------------------------------------ logs


def _linhas_para_colunas(texto: str, campos: list[str], cols: dict[str, list]) -> int:
    n = 0
    for i, linha in enumerate(texto.splitlines(), 1):
        p = linha.split("\t")
        ok = len(p) == len(campos)
        for k, c in enumerate(campos):
            cols[c].append(p[k] if ok else None)
        cols["linha_bruta"].append(None if ok else linha)
        cols["nr_linha"].append(i)
        n += 1
    return n


def _converter_lote_urna(args: tuple[str, list[str], str, str]) -> tuple[int, int]:
    """Processo filho: converte um lote de pacotes .jez de uma UF em um arquivo Parquet."""
    zip_path, entradas, destino, uf = args
    total, pacotes = 0, 0
    with zipfile.ZipFile(zip_path) as zf, pq.ParquetWriter(destino, ESQUEMA_LOG_URNA, compression="zstd") as w:
        cols = {c: [] for c in ESQUEMA_LOG_URNA.names}

        def descarregar():
            if cols["nr_linha"]:
                w.write_table(pa.Table.from_pydict(cols, schema=ESQUEMA_LOG_URNA))
                for v in cols.values():
                    v.clear()

        for entrada in entradas:
            m = RE_PACOTE.search(entrada)
            for caminho, texto in logs_do_pacote(zf.read(entrada), com_caminho=True):
                n = _linhas_para_colunas(texto, CAMPOS_URNA, cols)
                fixos = {"uf": uf, "uf_id": UF_ID[uf], "cd_municipio": m.group(2), "nr_zona": m.group(3),
                         "nr_secao": m.group(4), "tipo_log": m.group(5), "arquivo_logd": caminho}
                for c, v in fixos.items():
                    cols[c].extend([v] * n)
                total += n
            pacotes += 1
            if len(cols["nr_linha"]) >= LINHAS_POR_GRUPO:
                descarregar()
        descarregar()
    return total, pacotes


def converter_log_urna(uf: str, pasta: Path, workers: int) -> tuple[list[Path], int, int]:
    z = next((RAIZ / DS_URNA).glob(f"bu_imgbu_logjez_rdv_vscmr_2026_1t_{uf}.zip"))
    entradas = [n for n in zipfile.ZipFile(z).namelist() if RE_PACOTE.search(n)]
    tamanho = max(500, len(entradas) // (workers * 4) + 1)
    lotes = [entradas[i:i + tamanho] for i in range(0, len(entradas), tamanho)]
    destinos = [pasta / f"{uf}_{k:04d}.parquet" for k in range(len(lotes))]
    linhas = pacotes = 0
    with ProcessPoolExecutor(workers) as pool:
        for n, p in pool.map(_converter_lote_urna, [(str(z), l, str(d), uf) for l, d in zip(lotes, destinos)]):
            linhas += n
            pacotes += p
    return destinos, linhas, pacotes


def converter_log_gedai(z: Path, destino: Path) -> int:
    uf = RE_UF_GEDAI.search(z.name).group(1)
    cols = {c: [] for c in ESQUEMA_LOG_GEDAI.names}
    total = 0
    with zipfile.ZipFile(z) as zf:
        for entrada in zf.namelist():
            if not entrada.lower().endswith(".jez"):
                continue
            for caminho, texto in logs_do_pacote(zf.read(entrada), com_caminho=True, finais=(".log",)):
                n = _linhas_para_colunas(texto, CAMPOS_GEDAI, cols)
                for c, v in {"uf": uf, "_arquivo_zip": z.name, "arquivo_jez": entrada, "arquivo_log": caminho}.items():
                    cols[c].extend([v] * n)
                total += n
    pq.write_table(pa.Table.from_pydict(cols, schema=ESQUEMA_LOG_GEDAI), destino, compression="zstd")
    return total


# ------------------------------------------------------------------------- GCS e BQ


def clientes():
    from google.cloud import bigquery, storage

    return storage.Client(project=PROJETO).bucket(BUCKET), bigquery.Client(project=PROJETO, location="US")


def subir(bucket, local: Path, tabela: str, uf: str) -> str:
    nome = f"{PREFIXO_GCS}/{tabela}/uf={uf}/{local.name}"
    bucket.blob(nome).upload_from_filename(str(local), checksum="crc32c", timeout=3600)
    return f"gs://{BUCKET}/{nome}"


def criar_log_urna(bq) -> None:
    bq.query(f"""
        CREATE TABLE IF NOT EXISTS `{PROJETO}.{DATASET_BQ}.log_urna` (
          uf STRING, uf_id INT64, cd_municipio STRING, nr_zona STRING, nr_secao STRING, tipo_log STRING,
          arquivo_logd STRING, nr_linha INT64, data_hora STRING, nivel STRING, id_urna STRING, aplicacao STRING,
          mensagem STRING, hash_log STRING, linha_bruta STRING)
        PARTITION BY RANGE_BUCKET(uf_id, GENERATE_ARRAY(1, {len(UFS) + 1}, 1))
        CLUSTER BY cd_municipio, nr_zona, nr_secao, aplicacao
        OPTIONS(description="Linhas do logd.dat de cada urna (dataset resultados-2026-arquivos-transmitidos-para-totalizacao), sem transformação. Contém títulos de mesários.")
    """).result()


def carregar(bq, tabela: str, uri: str, truncar: bool = True, particao: int | None = None) -> str:
    from google.cloud import bigquery

    destino = f"{PROJETO}.{DATASET_BQ}.{tabela}" + (f"${particao}" if particao else "")
    cfg = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition="WRITE_TRUNCATE" if truncar else "WRITE_APPEND",
    )
    job = bq.load_table_from_uri(uri, destino, job_config=cfg)
    job.result()
    return job.job_id


def carregar_arquivos(bq) -> None:
    """Tabela `_arquivos`: uma linha por ZIP do espelho, com URL, SHA-512 e hora do download."""
    m = pd.concat([pd.read_csv(f, dtype=str) for f in sorted(Path("manifests").glob("espelho_*.csv"))])
    m = m.rename(columns={"arquivo": "_arquivo_zip"})
    TMP.mkdir(parents=True, exist_ok=True)
    local = TMP / "_arquivos.parquet"
    pq.write_table(pa.Table.from_pandas(m.astype(str).where(m.notna(), None), preserve_index=False), local)
    from google.cloud import bigquery

    cfg = bigquery.LoadJobConfig(source_format=bigquery.SourceFormat.PARQUET, write_disposition="WRITE_TRUNCATE")
    with local.open("rb") as f:
        bq.load_table_from_file(f, f"{PROJETO}.{DATASET_BQ}._arquivos", job_config=cfg).result()
    local.unlink()
    print(f"[_arquivos] {len(m)} ZIPs", flush=True)


# --------------------------------------------------------------------------- driver


def processar_csv(tabela: str, arquivos: list, bucket, bq, manter: bool) -> None:
    pasta = TMP / tabela
    pasta.mkdir(parents=True, exist_ok=True)
    total = 0
    for _, z, entrada, uf in arquivos:
        t0 = time.time()
        local = pasta / (Path(entrada).stem + ".parquet")
        linhas = converter_csv(z, entrada, local)
        uri = subir(bucket, local, tabela, uf)
        registrar(etapa="arquivo", tabela=tabela, uf=uf, arquivo=entrada, linhas=linhas,
                  bytes=local.stat().st_size, uri=uri, job_id="")
        print(f"[{tabela}] {entrada}: {linhas} linhas, {local.stat().st_size / 1e6:.0f} MB, {time.time() - t0:.0f}s",
              flush=True)
        total += linhas
        if not manter:
            local.unlink()
    job = carregar(bq, tabela, f"gs://{BUCKET}/{PREFIXO_GCS}/{tabela}/*")
    registrar(etapa="carga", tabela=tabela, uf="*", arquivo="", linhas=total, bytes="", uri="", job_id=job)
    print(f"[{tabela}] carregada ({total} linhas convertidas nesta execução), job {job}", flush=True)


def processar_log_urna(ufs: list[str], bucket, bq, workers: int, manter: bool) -> None:
    criar_log_urna(bq)
    tamanhos = {uf: next((RAIZ / DS_URNA).glob(f"*_{uf}.zip")).stat().st_size for uf in ufs}
    for uf in sorted(ufs, key=tamanhos.get):
        if ja_carregado("log_urna", uf):
            print(f"[log_urna] {uf} já carregado, pulando", flush=True)
            continue
        t0 = time.time()
        pasta = TMP / "log_urna" / uf
        pasta.mkdir(parents=True, exist_ok=True)
        destinos, linhas, pacotes = converter_log_urna(uf, pasta, workers)
        mb = sum(d.stat().st_size for d in destinos) / 1e6
        print(f"[log_urna] {uf}: {pacotes} pacotes, {linhas} linhas, {mb:.0f} MB, {time.time() - t0:.0f}s", flush=True)
        for d in destinos:
            subir(bucket, d, "log_urna", uf)
        job = carregar(bq, "log_urna", f"gs://{BUCKET}/{PREFIXO_GCS}/log_urna/uf={uf}/*", particao=UF_ID[uf])
        registrar(etapa="carga", tabela="log_urna", uf=uf, arquivo=f"{pacotes} pacotes", linhas=linhas,
                  bytes=int(mb * 1e6), uri=f"gs://{BUCKET}/{PREFIXO_GCS}/log_urna/uf={uf}/", job_id=job)
        print(f"[log_urna] {uf} carregado, job {job}, total {time.time() - t0:.0f}s", flush=True)
        if not manter:
            for d in destinos:
                d.unlink()


def processar_log_gedai(ufs: set[str] | None, bucket, bq, manter: bool) -> None:
    pasta = TMP / "log_gedai"
    pasta.mkdir(parents=True, exist_ok=True)
    total = 0
    for z in sorted((RAIZ / DS_GEDAI).glob("log_gedai_1t_*.zip")):
        uf = RE_UF_GEDAI.search(z.name).group(1)
        if ufs and uf not in ufs:
            continue
        local = pasta / (z.stem + ".parquet")
        linhas = converter_log_gedai(z, local)
        uri = subir(bucket, local, "log_gedai", uf)
        registrar(etapa="arquivo", tabela="log_gedai", uf=uf, arquivo=z.name, linhas=linhas,
                  bytes=local.stat().st_size, uri=uri, job_id="")
        total += linhas
        if not manter:
            local.unlink()
    job = carregar(bq, "log_gedai", f"gs://{BUCKET}/{PREFIXO_GCS}/log_gedai/*")
    registrar(etapa="carga", tabela="log_gedai", uf="*", arquivo="", linhas=total, bytes="", uri="", job_id=job)
    print(f"[log_gedai] carregada ({total} linhas), job {job}", flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description="Carga das tabelas raw do TSE no BigQuery")
    p.add_argument("--tabela", action="append", help="tabelas (padrão: todas)")
    p.add_argument("--uf", action="append", help="limita às UFs (arquivos nacionais entram sempre)")
    p.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    p.add_argument("--manter-parquet", action="store_true", help="não apaga o Parquet local depois do envio")
    a = p.parse_args()

    ufs = {u.upper() for u in a.uf} if a.uf else None
    todas = list(TABELAS_CSV) + TABELAS_LOG + ["_arquivos"]
    tabelas = a.tabela or todas
    desconhecidas = set(tabelas) - set(todas)
    if desconhecidas:
        raise SystemExit(f"tabelas desconhecidas: {desconhecidas}")

    bucket, bq = clientes()
    csvs = arquivos_csv(ufs)
    for tabela in tabelas:
        if tabela == "_arquivos":
            carregar_arquivos(bq)
        elif tabela == "log_urna":
            processar_log_urna(sorted(ufs) if ufs else UFS, bucket, bq, a.workers, a.manter_parquet)
        elif tabela == "log_gedai":
            processar_log_gedai(ufs, bucket, bq, a.manter_parquet)
        else:
            processar_csv(tabela, [c for c in csvs if c[0] == tabela], bucket, bq, a.manter_parquet)


if __name__ == "__main__":
    main()
