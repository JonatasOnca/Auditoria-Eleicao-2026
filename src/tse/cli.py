"""Linha de comando: `uv run tse <comando>`."""

from __future__ import annotations

import argparse
from datetime import date

import pandas as pd

from tse import ckan
from tse.resultados_api import CARGOS, ResultadosTSE


def _salvar(df: pd.DataFrame, saida: str | None) -> None:
    if saida:
        (df.to_parquet if saida.endswith(".parquet") else df.to_csv)(saida, index=False)
        print(f"-> {saida} ({len(df)} linhas)")
    else:
        with pd.option_context("display.max_rows", 60, "display.width", 200):
            print(df)


def main() -> None:
    p = argparse.ArgumentParser(prog="tse", description="Dados oficiais do TSE - Eleições 2026")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("catalogo", help="Lista arquivos do Portal de Dados Abertos (CKAN)")
    c.add_argument("--dataset", action="append", help="slug CKAN (padrão: datasets de 2026)")
    c.add_argument("-o", "--saida")

    for nome, ajuda in [("totais", "Totais (comparecimento, brancos, nulos)"),
                        ("candidatos", "Votação por candidato")]:
        s = sub.add_parser(nome, help=ajuda)
        s.add_argument("--cargo", type=int, default=1, choices=CARGOS)
        s.add_argument("--nivel", choices=["br", "uf", "municipio"], default="br")
        s.add_argument("--uf", action="append", help="filtra UFs (nível uf/municipio)")
        s.add_argument("-o", "--saida")
        s.add_argument("--snapshot-dir", help="grava os JSONs originais neste diretório")

    a = p.parse_args()

    if a.cmd == "catalogo":
        df = ckan.catalogo(a.dataset or ckan.DATASETS_2026)
        _salvar(df, a.saida or f"manifests/catalogo_{date.today().isoformat()}.csv")
        return

    with ResultadosTSE(snapshot_dir=a.snapshot_dir) as api:
        if a.nivel == "br":
            ufs = ["br"] if a.cargo == 1 else sorted(set(api.municipios(6259)["uf"]) - {"ZZ"})
        if a.cmd == "totais":
            if a.nivel == "br" and a.cargo == 1:
                df = pd.DataFrame([api.totais(1)])
            elif a.nivel in ("br", "uf"):
                df = api.totais_ufs(a.cargo)
                if a.uf:
                    df = df[df["uf"].isin([u.upper() for u in a.uf])]
            else:
                df = api.totais_municipios(a.cargo, a.uf)
        else:
            if a.nivel == "municipio":
                df = api.candidatos_municipios(a.cargo, a.uf)
            else:
                alvo = a.uf or ufs
                df = pd.concat([api.candidatos(a.cargo, u) for u in alvo], ignore_index=True)
        _salvar(df, a.saida)
        reg = api.registro_df()
        print(f"[{len(reg)} leituras da API; {int(reg['assinatura_ok'].sum())}/{len(reg)} assinaturas "
              f"válidas do TSE; gerado pelo TSE em {reg['gerado_tse'].dropna().max()}]")


if __name__ == "__main__":
    main()
