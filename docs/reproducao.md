# Como reproduzir o estudo

> Objetivo: permitir que outra equipe refaça cada etapa a partir dos arquivos públicos do
> TSE e chegue aos mesmos números. Os itens marcados **[FALTA]** ainda não existem; eles
> estão no caminho crítico do congelamento (`docs/registro_previo.md` §9).

---

## 0. Requisitos

- **Python:** ≥ 3.12 e [uv](https://docs.astral.sh/uv/).
- **Ambiente travado** por `uv.lock`:
  ```bash
  uv sync --extra dev            # análise e testes
  uv sync --extra dev --extra gcp   # só se for usar GCS/BigQuery
  ```
- **Disco:**
  - ZIPs de urna: ~134 GB por turno, se baixados todos de uma vez;
  - processando UF por UF, o pico fica perto do maior ZIP (SP, ~20 GB);
  - variáveis por seção: alguns GB.
- **Tempo** (MacBook, ~50 seções/s): ~2h45 por turno para os logs. **[FALTA]** medir e
  registrar por etapa.
- **Testes:**
  ```bash
  uv run pytest -q
  ```
  Se aparecer `Failed to spawn: pytest`, o `.venv` foi criado em outra pasta. Recrie com
  `uv sync --extra dev --reinstall`, ou rode
  `env -u VIRTUAL_ENV uv run --extra dev python -m pytest -q`. Em 2026-10-31: 12 testes
  passando.

---

## 1. Dados: baixar e conferir

Toda URL, data, tamanho e sha512 está em `manifests/`. Os arquivos principais são:
- `espelho_*.csv`
- `bu_2026_{1t,2t}_manifesto.csv`
- `catalogo_2026-10-12.csv`

```bash
uv run tse catalogo                                   # lista o portal; comparar com manifests/catalogo_*.csv
uv run python -m tse.espelho --turno 1 --dataset resultados-2026-boletim-de-urna
uv run python -m tse.espelho --turno 2 --dataset resultados-2026-boletim-de-urna
```

O espelho baixa cada arquivo do CDN do TSE e confere com o `.sha512` oficial.

**Pacotes de urna (logs).** O passo 3 lê os ZIPs direto do CDN, pelas URLs do manifesto
`manifests/espelho_resultados-2026-arquivos-transmitidos-para-totalizacao.csv`. Esse manifesto
já está versionado, então não é preciso espelhar os pacotes de urna (cerca de 134 GB por turno).
Para regenerá-lo do zero:
`uv run python -m tse.espelho --turno 2 --dataset resultados-2026-arquivos-transmitidos-para-totalizacao`
(baixa os ZIPs; use `--uf` para limitar). Um arquivo
que o TSE republicar com o mesmo nome é baixado de novo, e a versão anterior fica
guardada. Para reproduzir exatamente, compare o sha512 do seu download com o do
manifesto: se diferir, o TSE republicou o arquivo. O TSE não mantém versões antigas no CDN.
Nesse caso, registre a diferença e compare os resultados entre as duas versões. **[FALTA]** guardar
uma cópia dos arquivos usados num repositório público de dados.

---

## 2. Boletim de urna (seções e votos para Presidente)

O `tse.bu` baixa os ZIPs do BU em memória direto do CDN, confere com o `.sha512` e grava só o resumo
por seção. Ele não depende do passo 1.

```bash
uv run python -m tse.bu --turno 1      # data/bu_2026_1t/
uv run python -m tse.bu --turno 2      # data/bu_2026_2t/
```

**Checagem:**
- os totais nacionais devem bater com o resultado oficial;
- no 2º turno: 499.205 seções, comparecimento de 128.236.074, Lula 64.256.232 e Flávio
  Bolsonaro 59.826.041.

---

## 3. Logs das urnas (variáveis por seção)

```bash
uv run python -m tse.reprocessar_logs --turno 2 >> data/reprocessar_2t.log 2>&1
uv run python -m tse.reprocessar_logs --turno 1 >> data/reprocessar_1t.log 2>&1
```

- **Como lê:** os ZIPs são lidos direto do CDN do TSE, pelas URLs do manifesto do
  espelho.
- **Retomada:** é possível retomar; a UF pronta é pulada.
- **Saída:** `data/logs_2026_{1,2}t/secoes_{UF}.parquet` e `votos_tardios_{UF}.parquet`.
- **Método de contagem:** está documentado no docstring de `src/tse/urna_logs.py`. Cobre
  log de outra seção, voto interrompido gravado ou perdido e fuso.
- Detalhes de estado e retomada: [reprocessamento_logs.md](reprocessamento_logs.md).

Um reprocessamento novo já usa a regra corrigida de voto interrompido, e nesse caso o passo abaixo é
desnecessário. Ele só serve para saídas geradas antes de 2026-10-31, que não têm a coluna
`n_votos_descartados`: `uv run python -m tse.corrigir_interrompidos --turno {1,2}`. O comando é
idempotente: pula a UF que já tem a coluna.

**Alternativa com GCS e BigQuery** (exige projeto e bucket do GCP):
```bash
uv run python -m tse.pipeline_urna --turno 2
```
**[FALTA]** projeto e bucket estão fixos em `src/tse/bq_raw.py`. É preciso torná-los
configuráveis por variável de ambiente para outra equipe usar o próprio GCP. As etapas 1 a 4 e
6 não dependem de GCP; só a etapa 5 depende.

---

## 4. Conciliação log × BU

```bash
uv run python -m tse.consolidar --turno 1
uv run python -m tse.consolidar --turno 2
```

**Saída:** `manifests/conciliacao_logs_bu_2026_{1t,2t}.csv`.

**Checagem:**
- ≥ 99% das seções com votos do log iguais ao `QT_COMPARECIMENTO` (mínimo aceitável, não meta);
- as seções que não conferem ficam listadas em `data/logs_2026_*t/secoes_votos_divergentes.csv`.

**Referência do 2º turno** (2026-10-31, regra corrigida):
- log: 128.234.924 votos;
- BU: 128.236.074 votos;
- votos depois das 17h: 34.494, que bate com os ~34,4 mil divulgados pelo TSE.

Como obter esses números a partir das variáveis por seção:
```bash
uv run python -c "import pandas as pd,glob; d=pd.concat(map(pd.read_parquet,glob.glob('data/logs_2026_2t/secoes_*.parquet'))); print(len(d), int(d.n_votos.sum()), int(d.votos_apos_17.sum()))"
```
- `n_votos`: votos computados no log, pela regra corrigida.
- `votos_apos_17`: votos computados depois das 17h00 de **Brasília**. O horário local da urna é
  convertido pelo fuso da seção (`fuso_determinado`; regra no docstring de `urna_logs.py`).
- O corte é sempre 17h. A separação da janela de 17h a 19h do 2º turno vem das variáveis do regime
  das 19h (§4 do plano), que são **[FALTA]**.

---

## 5. Carga no BigQuery (opcional)

```bash
uv run python -m tse.bq_raw --tabela boletim_urna_2t
uv run python -m tse.auditoria_carga --turno 2        # confere linhas e hashes da carga
uv run python -m tse.validacao_conteudo --turno 2     # confere contra fontes independentes do TSE
```

**[FALTA]** as camadas acima da raw estão no repositório Dataform separado (`dataform/`,
fora deste git). Para reproduzir, é preciso publicar esse repositório ou trazer as
consultas para cá. As análises confirmatórias **não devem depender dele**: devem rodar a
partir dos parquets das etapas 2 a 4.

---

## 6. Análises confirmatórias **[FALTA]**

- **Script:** `src/tse/analise.py`, a escrever.
- **Comando:**
  ```bash
  uv run python -m tse.analise --turno {1,2}
  ```
- **O que o script faz:**
  1. lê só os parquets das etapas 2 a 4;
  2. calcula os limites da §6 do registro prévio com dados de antes das 17h;
  3. grava os limites antes de qualquer desfecho;
  4. roda RQ1–RQ4, placebos e sensibilidades;
  5. aplica Holm e BH-FDR;
  6. aplica a regra de decisão.
- **Saída:** `resultados/{turno}/` com:
  - uma tabela por RQ;
  - um `resultados.json` com cada número do relatório;
  - o sha256 de cada insumo e o commit do código.
- **Semente fixa:** 20261031.
- **Testes:** o script é testado com dados simulados (`tests/test_analise.py`) **antes**
  de rodar nos dados reais.

---

## 7. Do resultado ao relatório **[FALTA]**

- Todo número do relatório final é lido de `resultados/*/resultados.json`. Nenhum é
  digitado à mão.
- O relatório traz uma tabela "número → chave em `resultados.json` → função que o
  calcula".
- O notebook `notebooks/01_panorama_1turno.ipynb` é exploratório e roda com:
  ```bash
  uv run --extra notebook jupyter nbconvert --to notebook --execute notebooks/01_panorama_1turno.ipynb
  ```

---

## 8. Checklist de reprodução

| Passo | Comando | Verificação | Situação |
|---|---|---|---|
| Ambiente | `uv sync --extra dev` | `uv run pytest -q` passa | Pronto (recriar `.venv` se necessário) |
| Dados | `tse.espelho` | sha512 = manifesto | Pronto |
| BU | `tse.bu` | totais oficiais | Pronto |
| Logs | `tse.reprocessar_logs` | 28 UFs por turno, 0 erros | 2t pronto; 1t em andamento |
| Conciliação | `tse.consolidar` | ≥ 99% | 2t pronto |
| Registro prévio | tag `registro-previo-v1` | tabela da §9 preenchida | Rascunho |
| Análises | `tse.analise` | `resultados.json` + hashes | [FALTA] |
| Relatório | — | todo número rastreável | [FALTA] |
