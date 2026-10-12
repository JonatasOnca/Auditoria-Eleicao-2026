"""Extração de variáveis por seção a partir dos logs das urnas (RESEARCH_PLAN.md §4, camada completa).

Fonte: dataset CKAN `resultados-2026-arquivos-transmitidos-para-totalizacao`, um ZIP por UF
(`bu_imgbu_logjez_rdv_vscmr_2026_1t_{UF}.zip`). Cada seção tem um `...-log.jez`, que em 2026
é um ZIP (não 7z, apesar do leiame do TSE) contendo `logd.dat`. O `logd.dat` é texto em latin-1
separado por tab: data, hora, nível, id da urna, aplicação, mensagem, hash.

Os ZIPs não são baixados inteiros: o índice é lido por HTTP Range, e cada log é buscado com uma
única requisição de intervalo e descomprimido em memória. Nada é gravado em disco além do resultado.

Decisões de método (sondagem de 2026-10-12, 3 seções do AC):
- O log usa a hora LOCAL da urna. A urna libera a votação às 8h de Brasília, registrando
  "Urna pronta para receber votos" (06:00:01 no Acre). O fuso de cada seção é inferido SÓ por
  esse evento (projeto usa apenas dados do TSE, sem tabela externa de fusos). Se não houver
  "Urna pronta" nos primeiros 15 min de uma hora até as 9h locais, a seção fica com
  `fuso_determinado = False` e todas as variáveis de horário vazias. As contagens que não dependem
  da hora continuam preenchidas.
- Classificação de cada voto pelo caminho de habilitação:
    biometrica: "Tipo de habilitação do eleitor [biométrica]"
    manual_com_biometria: houve tentativas de digital e depois "habilitação manual" (mesário liberou)
    sem_biometria: nenhuma tentativa de digital (por exemplo, confirmação do ano de nascimento)
- Urna substituída durante o dia: o log da urna original vem aninhado dentro do .jez
  (por exemplo `...ME.jez`, também um ZIP com logd.dat). Todos os logs do pacote são lidos e os votos
  são somados. No AC isso fecha a contagem com o BU nas 6 seções que divergiam.
- Os títulos de eleitor dos mesários que aparecem no log NÃO são guardados. Só contamos quantos
  mesários distintos liberaram eleitores manualmente.
"""

from __future__ import annotations

import argparse
import io
import re
import struct
import sys
import time
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd

from tse import ckan
from tse.resultados_api import USER_AGENT

DATASET = "resultados-2026-arquivos-transmitidos-para-totalizacao"
DIA_ELEICAO = "04/10/2026"

# Variáveis que dependem da conversão para a hora de Brasília. Ficam vazias sem fuso determinado.
COLS_HORARIO = [
    "primeiro_voto_brt", "ultimo_voto_brt", "encerramento_brt", "votos_antes_17", "votos_apos_17",
    "gap_antes_17_min", "votos_ultimos_10min_antes_17", "intervalo_apos_17_mediana_s",
    "intervalo_apos_17_min_s", "intervalo_antes_17_mediana_s", "mesarios_distintos_manual_apos_17",
    "n_biometrica_antes_17", "n_biometrica_apos_17", "n_manual_com_biometria_antes_17",
    "n_manual_com_biometria_apos_17", "n_sem_biometria_antes_17", "n_sem_biometria_apos_17",
]

# o03220 ac 01015 0002 0088 -log.jez  ->  pleito, uf, município, zona, seção
RE_ARQUIVO = re.compile(r"o(\d{5})([a-z]{2})(\d{5})(\d{4})(\d{4})-log\.jez$")
RE_MESARIO_HAB = re.compile(r"Mesário (\d+) habilitou o eleitor")


# --------------------------------------------------------------------------- rede


class ArquivoRemoto(io.RawIOBase):
    """Arquivo somente leitura via HTTP Range, suficiente para o zipfile ler o índice."""

    def __init__(self, url: str, http: httpx.Client):
        self.url, self.http, self.pos = url, http, 0
        self.tamanho = int(http.head(url).raise_for_status().headers["content-length"])

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = {0: off, 1: self.pos + off, 2: self.tamanho + off}[whence]
        return self.pos

    def read(self, n=-1):
        if n < 0:
            n = self.tamanho - self.pos
        if n == 0 or self.pos >= self.tamanho:
            return b""
        fim = min(self.pos + n, self.tamanho) - 1
        r = self.http.get(self.url, headers={"Range": f"bytes={self.pos}-{fim}"}).raise_for_status()
        self.pos += len(r.content)
        return r.content

    def readinto(self, b):
        d = self.read(len(b))
        b[: len(d)] = d
        return len(d)


def ler_entrada(http: httpx.Client, url: str, info: zipfile.ZipInfo) -> bytes:
    """Lê uma entrada do ZIP remoto com uma só requisição (cabeçalho local + dados)."""
    folga = 30 + len(info.filename.encode()) + 512
    ini = info.header_offset
    for tentativa in range(4):
        try:
            r = http.get(url, headers={"Range": f"bytes={ini}-{ini + folga + info.compress_size}"})
            r.raise_for_status()
            break
        except httpx.HTTPError:
            if tentativa == 3:
                raise
            time.sleep(2**tentativa)
    b = r.content
    if b[:4] != b"PK\x03\x04":
        raise ValueError(f"cabeçalho local inválido em {info.filename}")
    n_nome, n_extra = struct.unpack("<HH", b[26:30])
    dados = b[30 + n_nome + n_extra : 30 + n_nome + n_extra + info.compress_size]
    if info.compress_type == zipfile.ZIP_STORED:
        return dados
    return zlib.decompress(dados, -15)


# ------------------------------------------------------------------------- parsing


def _ts(data_hora: str) -> datetime:
    return datetime.strptime(data_hora, "%d/%m/%Y %H:%M:%S")


def votos_do_log(logd: str) -> tuple[list[tuple[datetime, str, str | None]], dict]:
    """Devolve [(hora_local, tipo_habilitação, mesário_que_habilitou)] e eventos do dia."""
    votos, cur = [], []
    extras = {"encerramento": None, "pronta": None, "eventos_dia": 0, "digital_de_mesario": 0}
    for linha in logd.splitlines():
        p = linha.split("\t")
        if len(p) < 6 or not p[0].startswith(DIA_ELEICAO):
            continue
        extras["eventos_dia"] += 1
        msg = p[4]
        if p[3] != "VOTA":
            continue
        if msg.startswith("Aguardando digitação do identificador"):
            cur = []
        cur.append(msg)
        if msg.startswith("Digital coletada bate com uma digital gravada após o registro inicial de mesário"):
            extras["digital_de_mesario"] += 1
        elif msg == "Urna pronta para receber votos" and extras["pronta"] is None:
            extras["pronta"] = _ts(p[0])
        elif msg == "Operador selecionou: Encerrar votação" and extras["encerramento"] is None:
            extras["encerramento"] = _ts(p[0])
        elif msg == "O voto do eleitor foi computado":
            if any("[biométrica]" in m for m in cur):
                tipo = "biometrica"
            elif any(m.startswith("Capturada a digital. Tentativa") for m in cur):
                tipo = "manual_com_biometria"
            else:
                tipo = "sem_biometria"
            mesario = next((m2.group(1) for m in cur if (m2 := RE_MESARIO_HAB.match(m))), None)
            votos.append((_ts(p[0]), tipo, mesario))
            cur = []
    return votos, extras


def logs_do_pacote(conteudo: bytes, profundidade: int = 0) -> list[str]:
    """Todos os logd.dat de um pacote .jez, incluindo pacotes de urnas substituídas aninhados."""
    textos = []
    with zipfile.ZipFile(io.BytesIO(conteudo)) as jz:
        for nome in jz.namelist():
            if nome.endswith("logd.dat"):
                textos.append(jz.read(nome).decode("latin-1"))
            elif nome.lower().endswith(".jez") and profundidade < 3:
                textos.extend(logs_do_pacote(jz.read(nome), profundidade + 1))
    return textos


def variaveis_secao(nome: str, logds: list[str], uf: str) -> tuple[dict, list[dict]]:
    m = RE_ARQUIVO.search(nome)
    chave = {"uf": uf, "cd_municipio": m.group(3), "nr_zona": m.group(4), "nr_secao": m.group(5)}
    votos, extras = [], {"encerramento": None, "pronta": None, "eventos_dia": 0, "digital_de_mesario": 0}
    for logd in logds:
        v, e = votos_do_log(logd)
        votos.extend(v)
        extras["eventos_dia"] += e["eventos_dia"]
        extras["digital_de_mesario"] += e["digital_de_mesario"]
        if e["pronta"] and (extras["pronta"] is None or e["pronta"] < extras["pronta"]):
            extras["pronta"] = e["pronta"]
        if e["encerramento"] and (extras["encerramento"] is None or e["encerramento"] > extras["encerramento"]):
            extras["encerramento"] = e["encerramento"]
    votos.sort(key=lambda v: v[0])
    linha = {**chave, "arquivo": nome, "n_logs": len(logds), "n_votos": len(votos),
             "eventos_dia": extras["eventos_dia"], "digital_de_mesario": extras["digital_de_mesario"]}
    if not votos:
        return linha, []

    # Fuso (hora local - hora de Brasília): "Urna pronta" às 06:00 local → -2.
    pronta = extras["pronta"]
    fuso = pronta.hour - 8 if pronta and pronta.minute < 15 and pronta.hour <= 9 else None
    if fuso not in (-2, -1, 0, 1):
        fuso = None
    determinado = fuso is not None
    fuso = fuso if determinado else 0  # só para o cálculo; os campos de horário são anulados abaixo
    para_brt = lambda t: t - timedelta(hours=fuso)  # noqa: E731
    corte = datetime(2026, 10, 4, 17, 0, 0)

    brt = [(para_brt(t), tipo, mes) for t, tipo, mes in votos]
    antes = [v for v in brt if v[0] < corte]
    depois = [v for v in brt if v[0] >= corte]
    tipos = ("biometrica", "manual_com_biometria", "sem_biometria")
    intervalos = [(b[0] - a[0]).total_seconds() for a, b in zip(depois, depois[1:])]
    if antes and depois:
        intervalos.insert(0, (depois[0][0] - antes[-1][0]).total_seconds())

    linha.update(
        fuso_determinado=determinado,
        fuso_inferido=fuso if determinado else None,
        urna_pronta_local=pronta,
        primeiro_voto_brt=brt[0][0],
        ultimo_voto_brt=brt[-1][0],
        encerramento_brt=para_brt(extras["encerramento"]) if extras["encerramento"] else None,
        votos_antes_17=len(antes),
        votos_apos_17=len(depois),
        gap_antes_17_min=(corte - antes[-1][0]).total_seconds() / 60 if antes else None,
        votos_ultimos_10min_antes_17=sum(v[0] >= corte - timedelta(minutes=10) for v in antes),
        intervalo_apos_17_mediana_s=pd.Series(intervalos).median() if intervalos else None,
        intervalo_apos_17_min_s=min(intervalos) if intervalos else None,
        intervalo_antes_17_mediana_s=pd.Series(
            [(b[0] - a[0]).total_seconds() for a, b in zip(antes, antes[1:])]).median() if len(antes) > 1 else None,
        mesarios_distintos_manual=len({v[2] for v in brt if v[2]}),
        mesarios_distintos_manual_apos_17=len({v[2] for v in depois if v[2]}),
    )
    for t in tipos:
        linha[f"n_{t}"] = sum(v[1] == t for v in brt)
        linha[f"n_{t}_antes_17"] = sum(v[1] == t for v in antes)
        linha[f"n_{t}_apos_17"] = sum(v[1] == t for v in depois)

    if not determinado:
        linha.update(dict.fromkeys(COLS_HORARIO))
        return linha, []

    # Votos a partir das 16h de Brasília, um por linha (para RQ3 e placebos), sem identificar mesários.
    tardios = [{**chave, "hora_brt": t, "tipo": tipo, "liberado_por_mesario": mes is not None}
               for t, tipo, mes in brt if t >= datetime(2026, 10, 4, 16, 0, 0)]
    return linha, tardios


def aplicar_regra_fuso(secoes: pd.DataFrame, tardios: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aplica a regra de fuso a arquivos gerados pela versão anterior, que usava uma tabela de
    fusos por UF quando o log não permitia inferir o fuso. O resultado é idêntico ao de reprocessar."""
    if "fuso_usado" not in secoes:
        return secoes, tardios
    sem = ~secoes["fuso_inferido"].isin([-2, -1, 0, 1]) & secoes["n_votos"].gt(0)
    secoes = secoes.copy()
    secoes.loc[sem, COLS_HORARIO] = None
    secoes.insert(secoes.columns.get_loc("fuso_inferido"), "fuso_determinado", ~sem & secoes["n_votos"].gt(0))
    secoes = secoes.drop(columns=["fuso_usado", "fuso_confere_uf"])
    if len(tardios):
        chave = ["cd_municipio", "nr_zona", "nr_secao"]
        excluir = secoes.loc[sem, chave].assign(_x=1)
        tardios = tardios.merge(excluir, on=chave, how="left")
        tardios = tardios[tardios["_x"].isna()].drop(columns="_x")
    return secoes, tardios


# --------------------------------------------------------------------------- driver


def processar_uf(url: str, uf: str, saida: Path, conexoes: int) -> None:
    secoes_pq, tardios_pq = saida / f"secoes_{uf}.parquet", saida / f"votos_tardios_{uf}.parquet"
    if secoes_pq.exists():
        print(f"[{uf}] já processado, pulando", flush=True)
        return
    limites = httpx.Limits(max_connections=conexoes, max_keepalive_connections=conexoes)
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=120, limits=limites) as http:
        z = zipfile.ZipFile(ArquivoRemoto(url, http))
        logs = [i for i in z.infolist() if RE_ARQUIVO.search(i.filename)]
        t0, linhas, tardios, erros = time.time(), [], [], []

        def tarefa(info):
            try:
                return variaveis_secao(info.filename, logs_do_pacote(ler_entrada(http, url, info)), uf)
            except Exception as e:  # noqa: BLE001 — registramos e seguimos; nunca descartar em silêncio
                return {"uf": uf, "arquivo": info.filename, "erro": repr(e)[:300]}, []

        with ThreadPoolExecutor(conexoes) as pool:
            for k, (linha, tard) in enumerate(pool.map(tarefa, logs), 1):
                (erros if "erro" in linha else linhas).append(linha)
                tardios.extend(tard)
                if k % 2000 == 0:
                    print(f"[{uf}] {k}/{len(logs)} seções, {time.time() - t0:.0f}s", flush=True)

    df = pd.DataFrame(linhas + erros)
    df.to_parquet(secoes_pq, index=False)
    pd.DataFrame(tardios).to_parquet(tardios_pq, index=False)
    print(f"[{uf}] OK: {len(linhas)} seções, {len(erros)} erros, "
          f"{int(df.get('votos_apos_17', pd.Series(dtype=int)).fillna(0).sum())} votos após 17h, "
          f"{time.time() - t0:.0f}s", flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description="Variáveis por seção a partir dos logs das urnas (2026, 1º turno)")
    p.add_argument("--uf", action="append", help="UFs a processar (padrão: todas, das menores para as maiores)")
    p.add_argument("--saida", default="data/logs_2026_1t")
    p.add_argument("--conexoes", type=int, default=12)
    a = p.parse_args()

    saida = Path(a.saida)
    saida.mkdir(parents=True, exist_ok=True)
    rec = ckan.recursos(DATASET)
    rec = rec[rec["url"].str.endswith(".zip")].copy()
    rec["uf"] = rec["url"].str.extract(r"_([A-Z]{2})\.zip$")[0]
    if a.uf:
        rec = rec[rec["uf"].isin([u.upper() for u in a.uf])]
    # das menores para as maiores (SP por último)
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60) as http:
        rec["bytes"] = [int(http.head(u).headers["content-length"]) for u in rec["url"]]
    rec = rec.sort_values("bytes")
    for r in rec.itertuples():
        try:
            processar_uf(r.url, r.uf, saida, a.conexoes)
        except Exception as e:  # noqa: BLE001
            print(f"[{r.uf}] FALHOU: {e!r}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
