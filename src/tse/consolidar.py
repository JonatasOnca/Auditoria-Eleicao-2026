"""Consolida as variáveis dos logs de todas as UFs e concilia com o BU, seção a seção (RESEARCH_PLAN.md P0).

Entradas: `data/logs_2026_1t/secoes_{UF}.parquet` e `votos_tardios_{UF}.parquet` (tse.urna_logs),
`data/bu_2026_1t/bu_secoes.parquet` (tse.bu).
Saídas: `data/logs_2026_1t/logs_secoes.parquet`, `data/logs_2026_1t/logs_votos_tardios.parquet` e
`manifests/conciliacao_logs_bu_2026_1t.csv` (resumo por UF).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from tse.urna_logs import aplicar_regra_fuso

CHAVE = ["uf", "cd_municipio", "nr_zona", "nr_secao"]


def main() -> None:
    pasta = Path("data/logs_2026_1t")
    secoes, tardios = [], []
    for f in sorted(pasta.glob("secoes_*.parquet")):
        uf = f.stem.split("_")[1]
        s, t = aplicar_regra_fuso(pd.read_parquet(f), pd.read_parquet(pasta / f"votos_tardios_{uf}.parquet"))
        secoes.append(s)
        tardios.append(t)
    s = pd.concat(secoes, ignore_index=True)
    t = pd.concat(tardios, ignore_index=True)
    erros = s[s["erro"].notna()] if "erro" in s else s.iloc[0:0]
    s = s[s["erro"].isna()].drop(columns="erro") if "erro" in s else s

    bu = pd.read_parquet("data/bu_2026_1t/bu_secoes.parquet")
    m = bu[CHAVE + ["QT_COMPARECIMENTO", "QT_ELEI_BIOM_SEM_HABILITACAO", "DS_SECOES_AGREGADAS"]].merge(
        s[CHAVE + ["n_votos", "n_logs", "fuso_determinado", "n_manual_com_biometria"]],
        on=CHAVE, how="outer", indicator=True)
    m["diff_votos"] = m["n_votos"] - m["QT_COMPARECIMENTO"]
    m["diff_biometria"] = m["n_manual_com_biometria"] - m["QT_ELEI_BIOM_SEM_HABILITACAO"]

    resumo = m.groupby("uf").agg(
        secoes_bu=("QT_COMPARECIMENTO", "count"),
        secoes_log=("n_votos", "count"),
        so_no_bu=("_merge", lambda x: (x == "left_only").sum()),
        so_no_log=("_merge", lambda x: (x == "right_only").sum()),
        comparecimento_bu=("QT_COMPARECIMENTO", "sum"),
        votos_log=("n_votos", "sum"),
        secoes_votos_divergentes=("diff_votos", lambda x: (x.fillna(0) != 0).sum()),
        secoes_biometria_igual=("diff_biometria", lambda x: (x == 0).sum()),
        secoes_sem_fuso=("fuso_determinado", lambda x: (x == False).sum()),  # noqa: E712
        secoes_urna_substituida=("n_logs", lambda x: (x > 1).sum()),
    ).reset_index()
    resumo["erros_leitura"] = resumo["uf"].map(erros.groupby("uf").size()).fillna(0).astype(int)
    total = resumo.drop(columns="uf").sum().to_frame().T.assign(uf="TOTAL")
    resumo = pd.concat([resumo, total], ignore_index=True)

    s.to_parquet(pasta / "logs_secoes.parquet", index=False)
    t.to_parquet(pasta / "logs_votos_tardios.parquet", index=False)
    m[m["_merge"] != "both"].to_csv(pasta / "secoes_nao_pareadas.csv", index=False)
    m[(m["_merge"] == "both") & (m["diff_votos"] != 0)].to_csv(pasta / "secoes_votos_divergentes.csv", index=False)
    resumo.to_csv("manifests/conciliacao_logs_bu_2026_1t.csv", index=False)
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print(resumo.to_string(index=False))


if __name__ == "__main__":
    main()
