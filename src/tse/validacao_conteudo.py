"""Validação de conteúdo do que já está no BigQuery: o dado é o mesmo que o TSE publicou?

A auditoria da carga (tse.auditoria_carga) confere contagens e tamanhos. Aqui o conteúdo é comparado com fontes
independentes do pipeline:

1. `log_urna[_2t]` × ZIP original: para uma amostra de pacotes de cada UF carregada, o `.jez` é lido direto do ZIP no
   bronze (o mesmo arquivo baixado do TSE; o SHA-512 da cópia é conferido nas UFs pequenas), descompactado com
   código próprio e comparado linha a linha, byte a byte, com as linhas do BigQuery.
2. Resultados × API assinada: votos por UF × cargo × votável em `boletim_urna[_2t]` e em `votacao_secao` contra a API
   de Resultados (JWS Ed25519 verificado), para Presidente, Governador e Senador, nos dois turnos.
3. Log × BU: por seção, votos computados no dia da eleição (variáveis de tse.urna_logs) contra o comparecimento do BU.

Saída: `manifests/validacao_conteudo_{t}t.csv`, uma linha por verificação. Somente leitura.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import random
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from tse import bq_raw, espelho
from tse.resultados_api import ResultadosTSE, eleicao_do_cargo

AMOSTRA_POR_UF = 12
SHA_COMPLETO_ATE = 600_000_000  # recalcula o SHA-512 da cópia no bronze para ZIPs até este tamanho
RE_PACOTE = re.compile(r"o\d{5}([a-z]{2})(\d{5})(\d{4})(\d{4})-(log|logsa)\.jez$")
CARGOS = {1: "Presidente", 3: "Governador", 5: "Senador"}


class BlobRemoto(io.RawIOBase):
    """Leitura aleatória de um objeto do GCS por intervalos, para o zipfile ler só o índice e as entradas pedidas."""

    def __init__(self, blob):
        self.blob, self.pos = blob, 0
        blob.reload()
        self.tamanho = blob.size

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = {0: off, 1: self.pos + off, 2: self.tamanho + off}[whence]
        return self.pos

    def readinto(self, b):
        if self.pos >= self.tamanho:
            return 0
        fim = min(self.pos + len(b), self.tamanho) - 1
        dados = self.blob.download_as_bytes(start=self.pos, end=fim, retry=bq_raw.retry_gcs())
        b[: len(dados)] = dados
        self.pos += len(dados)
        return len(dados)


def logs_independente(conteudo: bytes, prefixo: str = "", prof: int = 0) -> dict[str, str]:
    """Todos os `logd.dat` de um pacote `.jez` (ZIP), inclusive pacotes aninhados de urna substituída."""
    saida = {}
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        for nome in z.namelist():
            if nome.endswith("logd.dat"):
                saida[prefixo + nome] = z.read(nome).decode("latin-1")
            elif nome.lower().endswith(".jez") and prof < 3:
                saida.update(logs_independente(z.read(nome), f"{prefixo}{nome}/", prof + 1))
    return saida


def validar_log_urna(bucket, bq, turno: int) -> list[dict]:
    tabela = "log_urna" if turno == 1 else f"log_urna_{turno}t"
    m = pd.read_csv(bq_raw.MANIFESTO, dtype=str)
    carregadas = sorted(set(m[(m["etapa"] == "carga") & (m["tabela"] == tabela)]["uf"]))
    esp = espelho.ler_manifesto(bq_raw.DS_URNA)
    saida = []
    for uf in carregadas:
        nome = f"bu_imgbu_logjez_rdv_vscmr_2026_{turno}t_{uf}.zip"
        reg = espelho.ultima_versao(esp, nome)
        blob = bucket.blob(reg["gcs_uri"].split(f"gs://{bucket.name}/", 1)[1])
        if int(float(reg["bytes"])) <= SHA_COMPLETO_ATE:
            h = hashlib.sha512()
            blob.reload()
            with blob.open("rb") as f:
                while bloco := f.read(8 << 20):
                    h.update(bloco)
            saida.append({"verificacao": "bronze_sha512", "alvo": nome, "ok": h.hexdigest() == reg["sha512"],
                          "detalhe": "SHA-512 da cópia no bronze recalculado e comparado com o do download"})
        z = zipfile.ZipFile(io.BufferedReader(BlobRemoto(blob), buffer_size=1 << 20))
        pacotes = [i for i in z.infolist() if RE_PACOTE.search(i.filename)]
        amostra = random.Random(f"{turno}{uf}").sample(pacotes, min(AMOSTRA_POR_UF, len(pacotes)))
        fonte, chaves = {}, []
        for info in amostra:
            _, mun, zona, secao, tipo = RE_PACOTE.search(info.filename).groups()
            for caminho, texto in logs_independente(z.read(info)).items():
                for i, linha in enumerate(texto.splitlines(), 1):
                    fonte[(mun, zona, secao, tipo, caminho, i)] = linha
            chaves.append((mun, zona, secao, tipo))
        filtro = " OR ".join(f"(cd_municipio='{a}' AND nr_zona='{b}' AND nr_secao='{c}' AND tipo_log='{d}')"
                             for a, b, c, d in chaves)
        sql = f"""SELECT cd_municipio, nr_zona, nr_secao, tipo_log, arquivo_logd, nr_linha,
                         {', '.join(bq_raw.CAMPOS_URNA)}, linha_bruta
                  FROM `{bq_raw.PROJETO}.{bq_raw.DATASET_BQ}.{tabela}` WHERE uf_id = {bq_raw.UF_ID[uf]} AND ({filtro})"""
        bq_linhas = {}
        for r in bq.query(sql).result():
            linha = r["linha_bruta"] if r["linha_bruta"] is not None else "\t".join(r[c] for c in bq_raw.CAMPOS_URNA)
            bq_linhas[(r["cd_municipio"], r["nr_zona"], r["nr_secao"], r["tipo_log"], r["arquivo_logd"],
                       r["nr_linha"])] = linha
        faltando = set(fonte) - set(bq_linhas)
        sobrando = set(bq_linhas) - set(fonte)
        diferentes = sum(fonte[k] != bq_linhas[k] for k in set(fonte) & set(bq_linhas))
        saida.append({"verificacao": f"{tabela}_conteudo", "alvo": uf,
                      "ok": not faltando and not sobrando and diferentes == 0,
                      "detalhe": f"{len(amostra)} pacotes, {len(fonte)} linhas no ZIP; faltando no BQ {len(faltando)}, "
                                 f"sobrando no BQ {len(sobrando)}, diferentes {diferentes}"})
        print(f"[{tabela}] {uf}: {saida[-1]['detalhe']}", flush=True)
    return saida


def votos_api(api: ResultadosTSE, cargo: int, turno: int, uf: str) -> dict[str, int]:
    ele = eleicao_do_cargo(cargo, turno)
    c = api.candidatos(cargo, uf, eleicao=ele)
    t = api.totais(cargo, uf, eleicao=ele)
    votos = {str(r.numero): r.votos for r in c.itertuples()}
    votos["95"] = t["brancos"]
    votos["96"] = t["nulos"]  # inclui os nulos técnicos (votos em candidato com registro anulado)
    return votos


def validar_resultados(bq, turno: int) -> list[dict]:
    d = f"{bq_raw.PROJETO}.{bq_raw.DATASET_BQ}"
    bu = "boletim_urna" if turno == 1 else f"boletim_urna_{turno}t"
    consultas = {
        bu: f"""SELECT SG_UF uf, CAST(CD_CARGO_PERGUNTA AS INT64) cargo, NR_VOTAVEL n, SUM(CAST(QT_VOTOS AS INT64)) v
                FROM `{d}.{bu}` WHERE CD_CARGO_PERGUNTA IN ('1','3','5') GROUP BY 1,2,3""",
        "votacao_secao": f"""SELECT SG_UF uf, CAST(CD_CARGO AS INT64) cargo, NR_VOTAVEL n, SUM(CAST(QT_VOTOS AS INT64)) v
                FROM `{d}.votacao_secao` WHERE NR_TURNO = '{turno}' AND CD_CARGO IN ('1','3','5') GROUP BY 1,2,3""",
    }
    bqv = {t: pd.DataFrame([dict(r) for r in bq.query(q).result()]) for t, q in consultas.items()}
    saida = []
    with ResultadosTSE() as api:
        for cargo, nome in CARGOS.items():
            ufs = sorted(set(bqv[bu].loc[bqv[bu]["cargo"] == cargo, "uf"]))
            for uf in ufs:
                oficial = votos_api(api, cargo, turno, uf)
                for tabela, df in bqv.items():
                    x = df[(df["uf"] == uf) & (df["cargo"] == cargo)]
                    meus = dict(zip(x["n"], x["v"]))
                    # votos em número sem candidato na API (ex.: registro anulado) entram como nulos técnicos
                    extra = sum(v for n, v in meus.items() if n not in oficial)
                    meus = {n: v for n, v in meus.items() if n in oficial}
                    meus["96"] = meus.get("96", 0) + extra
                    dif = {n: (meus.get(n, 0), v) for n, v in oficial.items() if meus.get(n, 0) != v}
                    saida.append({"verificacao": f"api_{tabela}", "alvo": f"{uf} {nome}", "ok": not dif,
                                  "detalhe": "idêntico à API assinada" if not dif else f"diferenças (BQ, API): {dif}"})
    return saida


def validar_log_bu(turno: int) -> list[dict]:
    pasta = Path(f"data/logs_2026_{turno}t")
    bu = pd.read_parquet(f"data/bu_2026_{turno}t/bu_secoes.parquet")
    chave = ["uf", "cd_municipio", "nr_zona", "nr_secao"]
    saida = []
    for f in sorted(pasta.glob("secoes_*.parquet")):
        uf = f.stem.split("_")[1]
        s = pd.read_parquet(f)
        m = bu[bu["uf"] == uf][chave + ["QT_COMPARECIMENTO"]].merge(s[chave + ["n_votos"]], on=chave, how="inner")
        div = int((m["n_votos"] != m["QT_COMPARECIMENTO"]).sum())
        saida.append({"verificacao": "log_x_bu", "alvo": uf, "ok": div == 0,
                      "detalhe": f"{len(m)} seções pareadas; {div} com votos no log diferentes do comparecimento do BU; "
                                 f"votos log {int(m['n_votos'].sum())} / BU {int(m['QT_COMPARECIMENTO'].sum())}"})
    return saida


def main() -> None:
    p = argparse.ArgumentParser(description="Validação de conteúdo contra fontes independentes (somente leitura)")
    p.add_argument("--turno", type=int, choices=[1, 2], default=2)
    t = p.parse_args().turno

    bucket, bq = bq_raw.clientes()
    linhas = validar_log_urna(bucket, bq, t) + validar_resultados(bq, t) + validar_log_bu(t)
    df = pd.DataFrame(linhas).assign(quando=datetime.now(timezone.utc).isoformat())
    df.to_csv(f"manifests/validacao_conteudo_{t}t.csv", index=False)
    print(df.groupby("verificacao")["ok"].agg(ok="sum", total="size").to_string())
    falhas = df[~df["ok"]]
    if len(falhas):
        with pd.option_context("display.width", 250, "display.max_colwidth", 160, "display.max_rows", 200):
            print(f"\n{len(falhas)} com diferença:\n" + falhas[["verificacao", "alvo", "detalhe"]].to_string(index=False))
        sys.exit(1)
    print("\nnenhuma diferença")


if __name__ == "__main__":
    main()
