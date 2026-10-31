"""Recalcula só as seções com voto interrompido depois da correção da regra (2026-10-31).

A regra de 2026-10-30 contava todo voto confirmado para [Presidente] e interrompido antes de "computado". A regra
corrigida (tse.urna_logs, docstring do módulo) só conta quando a urna responde "O eleitor identificado já votou" na
identificação seguinte. Os eventos que disparam a interrupção são os mesmos nas duas regras, então só mudam as seções
com `n_votos_interrompidos > 0` na saída antiga; em todas as outras a saída é idêntica e só ganha
`n_votos_descartados = 0`.

Para cada `secoes_{UF}.parquet` ainda sem a coluna `n_votos_descartados`, relê do CDN do TSE os logs das seções
afetadas, recalcula com `urna_logs.variaveis_secao` e substitui as linhas delas em `secoes_{UF}.parquet` e
`votos_tardios_{UF}.parquet`. Idempotente: UF que já tem a coluna é pulada.
"""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

import httpx
import pandas as pd

from tse import espelho, urna_logs

CHAVE = ["uf", "cd_municipio", "nr_zona", "nr_secao"]


def corrigir_uf(url: str, uf: str, pasta: Path, turno: int, http: httpx.Client) -> None:
    secoes_pq, tardios_pq = pasta / f"secoes_{uf}.parquet", pasta / f"votos_tardios_{uf}.parquet"
    s = pd.read_parquet(secoes_pq)
    if "n_votos_descartados" in s:
        print(f"[{uf}] já corrigido, pulando", flush=True)
        return
    t = pd.read_parquet(tardios_pq)
    afetadas = s[s["n_votos_interrompidos"].fillna(0) > 0]
    novas, novos_tardios = [], []
    if len(afetadas):
        z = zipfile.ZipFile(urna_logs.ArquivoRemoto(url, http))
        infos = {i.filename: i for i in z.infolist()}
        for r in afetadas.itertuples():
            linha, tard = urna_logs.variaveis_secao(
                r.arquivo, urna_logs.logs_do_pacote(urna_logs.ler_entrada(http, url, infos[r.arquivo])), uf, turno)
            novas.append(linha)
            novos_tardios.extend(tard)
            print(f"[{uf}] {r.cd_municipio}/{r.nr_zona}/{r.nr_secao}: n_votos {r.n_votos} → {linha['n_votos']} "
                  f"(interrompidos {r.n_votos_interrompidos} → {linha['n_votos_interrompidos']}, "
                  f"descartados {linha['n_votos_descartados']})", flush=True)
    chaves = set(map(tuple, afetadas[CHAVE].astype(str).values))
    fora = lambda d: ~d[CHAVE].astype(str).apply(tuple, axis=1).isin(chaves)  # noqa: E731
    s = s[fora(s)].assign(n_votos_descartados=0)
    s = pd.concat([s, pd.DataFrame(novas)], ignore_index=True)
    cols = list(s.columns.drop("n_votos_descartados"))
    cols.insert(cols.index("n_votos_interrompidos") + 1, "n_votos_descartados")
    s = s[cols].sort_values(CHAVE, kind="stable", ignore_index=True)
    t = pd.concat([t[fora(t)] if len(t) else t, pd.DataFrame(novos_tardios, columns=t.columns)], ignore_index=True)
    s.to_parquet(secoes_pq, index=False)
    t.to_parquet(tardios_pq, index=False)
    print(f"[{uf}] OK: {len(afetadas)} seções recalculadas", flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description="Recalcula as seções com voto interrompido (regra corrigida)")
    p.add_argument("--turno", type=int, choices=[1, 2], required=True)
    turno = p.parse_args().turno
    pasta = Path(f"data/logs_2026_{turno}t")
    m = espelho.ler_manifesto(urna_logs.DATASET).drop_duplicates("arquivo", keep="last")
    m = m[m["arquivo"].str.contains(f"_{turno}t_")].set_index("uf")
    with httpx.Client(headers={"User-Agent": urna_logs.USER_AGENT}, timeout=120) as http:
        for f in sorted(pasta.glob("secoes_*.parquet")):
            uf = f.stem.split("_")[1]
            corrigir_uf(m.loc[uf, "url"], uf, pasta, turno, http)
    print("FIM", flush=True)


if __name__ == "__main__":
    main()
