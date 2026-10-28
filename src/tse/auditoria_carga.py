"""Auditoria da carga: confere, sem alterar nada, que nenhum dado se perdeu ou duplicou entre o TSE e o BigQuery.

Verificações (cada uma vira uma linha em `manifests/auditoria_carga.csv`, com `ok` True/False):
1. Espelho: para a versão mais recente de cada ZIP no manifesto, o arquivo local existe com o tamanho registrado
   e/ou a cópia no bronze existe com o mesmo tamanho. ZIP apagado localmente sem cópia no bronze é falha.
2. `log_urna[_2t]`: por UF, as linhas da partição no BigQuery são exatamente as linhas convertidas na última carga
   (detecta Parquet repetido ou faltando no GCS) e as seções distintas batem com os pacotes lidos.
3. Variáveis dos logs: nenhuma seção com erro de leitura em `data/logs_2026_{t}t/secoes_*.parquet`.
4. Tabelas CSV: as linhas no BigQuery são a soma das linhas convertidas da versão atual de cada CSV.
5. 1º turno: as tabelas raw do 1º turno que não foram recarregadas têm as mesmas linhas da linha de base
   (`manifests/bq_linha_de_base_1t.csv`, contagens lidas no BigQuery em 2026-10-28 antes da carga do 2º turno).

Uso: `uv run python -m tse.auditoria_carga [--turno 2]`. Sai com código 1 se alguma verificação falhar.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from tse import bq_raw, espelho
from tse.ckan import UFS

LINHA_DE_BASE = Path("manifests/bq_linha_de_base_1t.csv")
SAIDA = Path("manifests/auditoria_carga.csv")
# Recarregadas de propósito com a republicação do TSE (dois turnos e Presidente): não entram na comparação com a base.
RECARREGADAS = {"votacao_secao", "detalhe_votacao_secao", "detalhe_votacao_munzona", "votacao_candidato_munzona",
                "votacao_partido_munzona", "_arquivos"}


def checar_espelho(bucket) -> list[dict]:
    saida = []
    for f in sorted(Path("manifests").glob("espelho_*.csv")):
        slug = f.stem.removeprefix("espelho_")
        m = pd.read_csv(f, dtype=str)
        for nome, v in m.groupby("arquivo", sort=False):
            r = v.iloc[-1]
            bytes_ = int(float(r["bytes"]))
            local = Path("data/raw") / slug / nome
            tem_local = local.exists() and local.stat().st_size == bytes_
            uri = str(r.get("gcs_uri", ""))
            tem_bronze = None
            if uri.startswith("gs://"):
                blob = bucket.get_blob(uri.split(f"gs://{bucket.name}/", 1)[1])
                tem_bronze = blob is not None and blob.size == bytes_
            ok = tem_local or bool(tem_bronze)
            if uri.startswith("gs://"):
                ok = ok and bool(tem_bronze)  # se prometemos uma cópia no bronze, ela tem de existir
            saida.append({"verificacao": "espelho", "alvo": f"{slug}/{nome}", "ok": ok,
                          "detalhe": f"local={tem_local} bronze={tem_bronze} bytes={bytes_}"})
    return saida


def checar_log_urna(bq, turno: int) -> list[dict]:
    tabela = "log_urna" if turno == 1 else f"log_urna_{turno}t"
    m = pd.read_csv(bq_raw.MANIFESTO, dtype=str)
    cargas = m[(m["etapa"] == "carga") & (m["tabela"] == tabela)].groupby("uf").last()
    contagem = {r["uf_id"]: (r["linhas"], r["secoes"]) for r in bq.query(f"""
        SELECT uf_id, COUNT(*) linhas, COUNT(DISTINCT CONCAT(cd_municipio, nr_zona, nr_secao, tipo_log)) secoes
        FROM `{bq_raw.PROJETO}.{bq_raw.DATASET_BQ}.{tabela}` GROUP BY 1""").result()}
    saida = []
    for uf in UFS:
        uid = bq_raw.UF_ID[uf]
        if uf not in cargas.index:
            ok = uid not in contagem  # UF ainda não carregada não pode ter linhas soltas
            saida.append({"verificacao": tabela, "alvo": uf, "ok": ok,
                          "detalhe": "ainda não carregada" + ("" if ok else f"; mas há {contagem[uid][0]} linhas")})
            continue
        esperado = int(cargas.at[uf, "linhas"])
        pacotes = int(cargas.at[uf, "arquivo"].split()[0])
        linhas, secoes = contagem.get(uid, (0, 0))
        saida.append({"verificacao": tabela, "alvo": uf, "ok": linhas == esperado and secoes == pacotes,
                      "detalhe": f"BQ {linhas} linhas / convertidas {esperado}; seções BQ {secoes} / pacotes {pacotes}"})
    return saida


def checar_variaveis(turno: int) -> list[dict]:
    saida = []
    for f in sorted(Path(f"data/logs_2026_{turno}t").glob("secoes_*.parquet")):
        s = pd.read_parquet(f)
        erros = int(s["erro"].notna().sum()) if "erro" in s else 0
        saida.append({"verificacao": f"variaveis_logs_{turno}t", "alvo": f.stem.split("_")[1], "ok": erros == 0,
                      "detalhe": f"{len(s)} seções, {erros} com erro de leitura"})
    return saida


def checar_csv(bq) -> list[dict]:
    m = pd.read_csv(bq_raw.MANIFESTO, dtype=str)
    arq = m[m["etapa"] == "arquivo"]
    saida = []
    for tabela in bq_raw.TABELAS_CSV:
        v = arq[arq["tabela"] == tabela]
        if v.empty:
            continue
        esperado = int(v.groupby("arquivo")["linhas"].last().astype(int).sum())
        real = bq.get_table(f"{bq_raw.PROJETO}.{bq_raw.DATASET_BQ}.{tabela}").num_rows
        saida.append({"verificacao": "tabela_csv", "alvo": tabela, "ok": real == esperado,
                      "detalhe": f"BQ {real} / convertidas {esperado}"})
    return saida


def checar_linha_de_base(bq) -> list[dict]:
    base = pd.read_csv(LINHA_DE_BASE)
    saida = []
    for r in base.itertuples():
        if r.tabela in RECARREGADAS:
            continue
        real = bq.get_table(f"{bq_raw.PROJETO}.{bq_raw.DATASET_BQ}.{r.tabela}").num_rows
        saida.append({"verificacao": "linha_de_base_1t", "alvo": r.tabela, "ok": real == r.linhas,
                      "detalhe": f"BQ {real} / base {r.linhas}"})
    # nas recarregadas, as linhas do 1º turno sem Presidente têm de continuar as mesmas (votacao_secao/detalhe_secao)
    for tabela in ("votacao_secao", "detalhe_votacao_secao"):
        b = int(base.loc[base["tabela"] == tabela, "linhas"].iloc[0])
        real = next(iter(bq.query(f"""SELECT COUNT(*) n FROM `{bq_raw.PROJETO}.{bq_raw.DATASET_BQ}.{tabela}`
            WHERE NR_TURNO = '1' AND CD_CARGO != '1'""").result()))["n"]
        saida.append({"verificacao": "linha_de_base_1t", "alvo": f"{tabela} (1º turno sem Presidente)",
                      "ok": real == b, "detalhe": f"BQ {real} / base {b}"})
    return saida


def main() -> None:
    p = argparse.ArgumentParser(description="Auditoria da carga (somente leitura)")
    p.add_argument("--turno", type=int, choices=[1, 2], default=2)
    t = p.parse_args().turno

    bucket, bq = bq_raw.clientes()
    linhas = (checar_espelho(bucket) + checar_log_urna(bq, t) + checar_variaveis(t) + checar_csv(bq)
              + checar_linha_de_base(bq))
    df = pd.DataFrame(linhas).assign(quando=datetime.now(timezone.utc).isoformat())
    df.to_csv(SAIDA, index=False)
    resumo = df.groupby("verificacao")["ok"].agg(ok="sum", total="size")
    print(resumo.to_string())
    falhas = df[~df["ok"]]
    if len(falhas):
        print(f"\n{len(falhas)} FALHAS:")
        with pd.option_context("display.width", 250, "display.max_colwidth", 120, "display.max_rows", 200):
            print(falhas[["verificacao", "alvo", "detalhe"]].to_string(index=False))
        sys.exit(1)
    print("\nnenhuma falha")


if __name__ == "__main__":
    main()
