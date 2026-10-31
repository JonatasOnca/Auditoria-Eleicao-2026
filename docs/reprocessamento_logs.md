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

## Estado (2026-10-31 14:20, horário do Mac)

| Turno | Situação |
|---|---|
| 2º | **Concluído e consolidado** com a regra corrigida: 28 UFs, 3 seções divergentes (BA 35653/0235 −13, MA 08893/0609 −36, RS 89060/0191 −2, todas com urna de contingência sem o log da urna original) |
| 1º | Em andamento com a regra corrigida. AC AP RO RR SE TO ZZ prontas e corrigidas; MS refeito do zero (a pausa anterior o pegou entre a gravação dos dois arquivos) |

Ritmo observado: ~40–50 seções/s; o 1º turno inteiro tem ~499 mil seções (~3h).

Para conferir o estado atual a qualquer momento:
```
ls data/logs_2026_1t/secoes_??.parquet | wc -l   # UFs prontas do 1º turno (28 = completo)
```

## Como retomar
Na raiz do projeto, um comando só (refaz apenas as UFs do 1º turno que faltam; roda em segundo plano e não
para se o terminal ou o editor fechar):
```
nohup caffeinate -i zsh -c 'uv run python -m tse.reprocessar_logs --turno 1 >> data/reprocessar_1t.log 2>&1' >/dev/null 2>&1 &
```
Acompanhar: `tail -f data/reprocessar_1t.log`. Cada UF pronta aparece como
`[UF] OK: N seções, 0 erros, …`; as que já estavam prontas aparecem como `[UF] já processado, pulando`. O fim de cada
turno é a linha `FIM`.

Para pausar de novo: `pkill -f tse.reprocessar_logs` (perde só a UF em andamento).

## Quando terminar
1. `uv run python -m tse.consolidar --turno 1` (o 2º turno já foi consolidado).
2. Comparar a conciliação nova com a anterior (`_metodo_anterior/` e `manifests/conciliacao_logs_bu_2026_{t}t.csv`
   no git): seções divergentes, votos interrompidos, logs de outra seção.
3. Commitar os manifests de conciliação e atualizar este arquivo para "concluído".

**Enquanto não terminar, não rodar `tse.consolidar --turno 1`:** a pasta do 1º turno ainda não tem todas as UFs.
`secoes_{UF}.parquet` é gravado por último, depois de `votos_tardios_{UF}.parquet`, e marca a UF como pronta.
