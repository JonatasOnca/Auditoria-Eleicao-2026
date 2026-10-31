# Reprocessamento dos logs com o método corrigido — estado e retomada

## Por que
Em 2026-10-30 a contagem de votos nos logs das urnas foi corrigida (commit 875b6b7, `src/tse/urna_logs.py`):
- log de outra seção dentro do pacote não entra mais na contagem (`n_logs_outra_secao`);
- voto confirmado e interrompido por queda de energia passa a contar (`n_votos_interrompidos`).

Por isso as variáveis por seção dos dois turnos (`data/logs_2026_{1,2}t/secoes_{UF}.parquet` e
`votos_tardios_{UF}.parquet`) estão sendo recalculadas com `tse.reprocessar_logs`, que lê os ZIPs do CDN do TSE.
Os resultados do método anterior estão guardados em `data/logs_2026_{1,2}t/_metodo_anterior/`.

Nada disso altera a cópia dos dados do TSE: bronze e tabelas do BigQuery ficam como estão.

## Estado (PAUSADO em 2026-10-31 00:14, horário do Mac)

| Turno | Prontas | Faltam |
|---|---|---|
| 2º | 20 de 28: AC AL AM AP DF ES GO MA MS MT PA PB PI RN RO RR SC SE TO ZZ | 8: PE CE PR RS BA RJ MG SP (~329 mil seções) |
| 1º | 0 de 28 | todas (~499 mil seções) |

PE estava em andamento na pausa e recomeça do zero (o progresso de uma UF só é salvo quando ela termina).
Ritmo observado: ~50 seções/s, ou seja ~2 h para o que falta do 2º turno e ~2h45 para o 1º.

Para conferir o estado atual a qualquer momento:
```
ls data/logs_2026_2t/secoes_*.parquet | wc -l   # UFs prontas do 2º turno (28 = completo)
ls data/logs_2026_1t/secoes_*.parquet | wc -l   # UFs prontas do 1º turno
```

## Como retomar
Na raiz do projeto, um comando só (refaz apenas o que falta: 2º turno, depois 1º; roda em segundo plano e não
para se o terminal ou o editor fechar):
```
nohup caffeinate -i zsh -c 'uv run python -m tse.reprocessar_logs --turno 2 >> data/reprocessar_2t.log 2>&1 && uv run python -m tse.reprocessar_logs --turno 1 >> data/reprocessar_1t.log 2>&1' >/dev/null 2>&1 &
```
Acompanhar: `tail -f data/reprocessar_2t.log` (depois `data/reprocessar_1t.log`). Cada UF pronta aparece como
`[UF] OK: N seções, 0 erros, …`; as que já estavam prontas aparecem como `[UF] já processado, pulando`. O fim de cada
turno é a linha `FIM`.

Para pausar de novo: `pkill -f tse.reprocessar_logs` (perde só a UF em andamento).

## Quando terminar
1. `uv run python -m tse.consolidar --turno 2` e `uv run python -m tse.consolidar --turno 1`.
2. Comparar a conciliação nova com a anterior (`_metodo_anterior/` e `manifests/conciliacao_logs_bu_2026_{t}t.csv`
   no git): seções divergentes, votos interrompidos, logs de outra seção.
3. Commitar os manifests de conciliação e atualizar este arquivo para "concluído".

**Enquanto não terminar, não rodar `tse.consolidar --turno 1`:** os `secoes_*.parquet` do 1º turno foram movidos
para `_metodo_anterior/` e a pasta está vazia.
