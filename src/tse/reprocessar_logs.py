"""Reprocessa as variáveis dos logs (tse.urna_logs) de um turno inteiro, lendo os ZIPs do CDN do TSE.

Usado depois da correção do método de contagem (log de outra seção e voto interrompido, 2026-10-30), quando os ZIPs
de urna já não estavam no disco. As URLs vêm do manifesto do espelho; em 2026-10-30 as versões no CDN foram
conferidas com o manifesto (no 1º turno o TSE só acrescentou `imgbu.dat`; logs idênticos em tamanho e CRC).

Retomável por UF: `urna_logs.processar_uf` pula a UF cujo `secoes_{UF}.parquet` já existe, e esse arquivo só é
gravado quando a UF termina. Estado e comando de retomada: docs/reprocessamento_logs.md.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from tse import espelho, urna_logs


def main() -> None:
    p = argparse.ArgumentParser(description="Reprocessa os logs de um turno a partir do CDN do TSE")
    p.add_argument("--turno", type=int, choices=[1, 2], required=True)
    p.add_argument("--conexoes", type=int, default=32)
    a = p.parse_args()

    m = espelho.ler_manifesto(urna_logs.DATASET).drop_duplicates("arquivo", keep="last")
    m = m[m["arquivo"].str.contains(f"_{a.turno}t_")].assign(b=lambda d: d["bytes"].astype(int)).sort_values("b")
    saida = Path(f"data/logs_2026_{a.turno}t")
    saida.mkdir(parents=True, exist_ok=True)
    for r in m.itertuples():  # das menores para as maiores (SP por último)
        urna_logs.processar_uf(r.url, r.uf, saida, a.conexoes, None, a.turno)
    print("FIM", flush=True)


if __name__ == "__main__":
    main()
