# Reprocessamento dos logs com o método corrigido — estado e retomada

## Por que
Em 2026-10-30 a contagem de votos nos logs das urnas foi corrigida (commit 875b6b7, `src/tse/urna_logs.py`):
- log de outra seção dentro do pacote não entra mais na contagem (`n_logs_outra_secao`);
- voto confirmado e interrompido por queda de energia passa a contar (`n_votos_interrompidos`).

**Correção da correção (2026-10-31).** Contar todo voto interrompido estava errado: no 2º turno as seções
divergentes foram de 7 para 53. Pelo log, o voto interrompido só foi gravado quando, ao religar, a urna responde
"O eleitor identificado já votou" à próxima identificação (3 seções); quando responde "Eleitor foi habilitado", o voto
se perdeu e o eleitor votou de novo (51 seções, inclusive os 36 desligamentos pela chave). A regra foi corrigida em
`src/tse/urna_logs.py` (nova coluna `n_votos_descartados`). Como os eventos que disparam a interrupção são os mesmos,
só as seções com `n_votos_interrompidos > 0` mudam: `tse.corrigir_interrompidos` recalcula só essas, relendo os logs
do CDN, nas UFs que já estavam prontas. Conferido no 2º turno: as outras 499.123 seções ficaram idênticas.

Por isso as variáveis por seção dos dois turnos (`data/logs_2026_{1,2}t/secoes_{UF}.parquet` e
`votos_tardios_{UF}.parquet`) estão sendo recalculadas com `tse.reprocessar_logs`, que lê os ZIPs do CDN do TSE.
Os resultados do método anterior estão guardados em `data/logs_2026_{1,2}t/_metodo_anterior/`.

Nada disso altera a cópia dos dados do TSE: bronze e tabelas do BigQuery ficam como estão.

## Estado: CONCLUÍDO em 2026-10-31 17:14 (horário do Mac)

Os dois turnos foram reprocessados com a regra corrigida e consolidados (`manifests/conciliacao_logs_bu_2026_{1,2}t.csv`).

| | 1º turno | 2º turno |
|---|---|---|
| Seções no log / no BU | 499.176 / 499.206 | 499.177 / 499.205 |
| Só no BU | 30 (28 ZZ, 2 MG) | 28 (27 ZZ, 1 SP) |
| Seções com votos log ≠ BU | **5** (método anterior: 9) | **3** (método anterior: 7) |
| Logs de outra seção no pacote | 17 | 9 |
| Votos interrompidos: gravados / perdidos | 4 / 150 | 3 / 54 |
| Erros de leitura | 0 | 0 |

Seções divergentes que restam:
- 1º turno: BA 39934/0183/0175 (−36) e SP 71072/0002/0035 (−15), ambas com 2 logs (troca de urna); RJ 58971/0087/0184
  (−2); RS 89036/0083/0044 (−1, 3 logs); SP 63614/0227/0305 (−1, a exceção da regra do voto interrompido, ver
  docstring de `tse.urna_logs`).
- 2º turno: BA 35653/0173/0235 (−13), MA 08893/0047/0609 (−36) e RS 89060/0017/0191 (−2), todas com urna de
  contingência sem o log da urna original no período de votação.

Saídas consolidadas do método anterior: `data/logs_2026_{1,2}t/_metodo_anterior/consolidado/`.

## Como foi feito (para refazer)
Reprocessamento de um turno inteiro a partir do CDN (pula as UFs com `secoes_{UF}.parquet`; roda em segundo plano):
```
nohup caffeinate -i zsh -c 'uv run python -m tse.reprocessar_logs --turno 1 >> data/reprocessar_1t.log 2>&1' >/dev/null 2>&1 &
```
Cada UF pronta aparece como `[UF] OK: N seções, 0 erros, …`; o fim é a linha `FIM`. Para pausar:
`pkill -f tse.reprocessar_logs` (perde só a UF em andamento). `secoes_{UF}.parquet` é gravado por último, depois de
`votos_tardios_{UF}.parquet`, e marca a UF como pronta. Depois: `uv run python -m tse.consolidar --turno 1`.
