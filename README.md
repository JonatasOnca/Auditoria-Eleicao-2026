# Auditoria Eleição 2026

O projeto analisa o comportamento eleitoral nas Eleições Gerais de 2026 com **apenas dados oficiais do TSE**. É um **estudo estatístico independente**: não é auditoria oficial nem perícia.

- Plano de pesquisa: [RESEARCH_PLAN-pt-br.md](RESEARCH_PLAN-pt-br.md) ([EN](RESEARCH_PLAN.md))
- Registro prévio (protocolo congelado antes das análises confirmatórias): [docs/registro_previo.md](docs/registro_previo.md)
- Como reproduzir: [docs/reproducao.md](docs/reproducao.md)
- Revisão do plano pelos papéis da equipe: [docs/revisao_research_plan.md](docs/revisao_research_plan.md)

> **Ressalva metodológica:** uma anomalia estatística (comparecimento atípico, urnas substituídas etc.) é um **sinal para investigação**, não uma prova de fraude. Todo achado precisa ser rastreável até o arquivo oficial do TSE (URL e hash) e confrontado com explicações operacionais conhecidas antes de qualquer conclusão.

## Fontes
| Fonte | Uso | Acesso |
|---|---|---|
| API de Resultados (`resultados.tse.jus.br`) | Agregados nos níveis Brasil, UF, município e zona | Leitura direta em memória (Fase 1) |
| Portal de Dados Abertos (`dadosabertos.tse.jus.br`, CKAN) | Votação por seção, BU, correspondências, logs, RDV, eleitorado e candidatos | CDN do TSE para GCS e BigQuery (Fase 2) |

Toda leitura da API de Resultados é feita na versão **assinada digitalmente pelo TSE** (`.jws`, Ed25519), a mesma que o app oficial verifica. Um arquivo com assinatura inválida é rejeitado. Detalhes dos endpoints e da assinatura: [docs/api_resultados.md](docs/api_resultados.md).

## Uso
```bash
uv sync --extra dev
uv run pytest tests                              # testes da assinatura (requer rede)
uv run tse totais --cargo 1                       # Presidente, Brasil
uv run tse candidatos --cargo 1 --nivel uf        # Presidente por UF
uv run tse totais --cargo 3 --nivel municipio --uf MG -o mg_gov.parquet
uv run tse catalogo                               # arquivos do portal (salva em manifests/)
```

Em Python:
```python
from tse.resultados_api import ResultadosTSE
with ResultadosTSE() as api:
    br = api.totais(cargo=1)
    mun = api.totais_municipios(cargo=1)       # ~5.570 requisições, 4 conexões em paralelo
    api.registro_df()                          # URL, SHA-256 e data de geração de cada leitura
```

Cargos: 1 Presidente, 3 Governador, 5 Senador, 6 Dep. Federal, 7 Dep. Estadual, 8 Dep. Distrital.

## Turnos
O 1º turno foi em 04/10/2026 e o 2º em 25/10/2026 (Presidente e Governador em AC, AM, DF, ES, RN e TO). Os comandos
aceitam `--turno {1,2}`:

```bash
uv run tse candidatos --cargo 1 --turno 2                        # API de Resultados, eleição 6258
uv run python -m tse.espelho --turno 2 --dataset resultados-2026-boletim-de-urna
uv run python -m tse.bu --turno 2                                # data/bu_2026_2t/
uv run python -m tse.pipeline_urna --turno 2                     # logs das urnas UF por UF -> log_urna_2t
uv run python -m tse.consolidar --turno 2                        # conciliação log × BU
uv run python -m tse.bq_raw --tabela boletim_urna_2t             # carga raw no BigQuery
```

Tabelas raw no BigQuery (`teconca-dev-data-solutions.auditoria_eleicao_2026_raw`):
- **Separadas por turno** (o TSE publica um arquivo por turno): `boletim_urna`, `correspondencia_*`, `log_gedai` e
  `log_urna` para o 1º turno; as mesmas com sufixo `_2t` para o 2º.
- **Com os dois turnos** (o TSE republicou o mesmo arquivo com `NR_TURNO` 1 e 2 em 26/10/2026): `votacao_secao`,
  `detalhe_votacao_secao`, `detalhe_votacao_munzona`, `votacao_candidato_munzona`, `votacao_partido_munzona`.

Cuidados:
- O log da urna do 2º turno (`log_urna_2t`) também traz os eventos do 1º turno, porque a urna é a mesma e o
  `logd.dat` é cumulativo. As análises filtram por `data_hora` (o `tse.urna_logs` já usa só o dia do turno).
- O catálogo CKAN não lista todos os arquivos: o BU do 2º turno de RR e os arquivos de urna do 2º turno estão só no
  CDN. Eles entram pelo padrão de nome e só se o CDN do TSE responder 200; o manifesto marca `no_catalogo=False`.
- Arquivos republicados com o mesmo nome são baixados de novo; a versão anterior fica em
  `data/raw/<dataset>/_substituidos/` e o manifesto registra o SHA-512 substituído.

## Agentes da auditoria

Subagentes do Claude Code em `.claude/agents/`, um para cada papel da equipe. Eles
preparam, revisam e questionam o trabalho, mas **não substituem os profissionais**
nem dão valor institucional ou jurídico ao resultado.

| Agente | Papel | Edita arquivos? |
|---|---|---|
| `estatistico-eleitoral` | Desenho e interpretação estatística (RQ1–RQ5, fingerprint, placebos) | Não |
| `engenheiro-dados` | Código em `src/tse`, BigQuery, Dataform, conciliação log × BU | Sim |
| `seguranca-urna` | Logs, BU, RDV, assinaturas, TPS e teste de integridade | Não |
| `advogado-eleitoral` | Legalidade dos procedimentos, competência, linguagem das conclusões | Não |
| `auditor-processos` | Modelo de ameaças, controles e risco residual | Não |
| `operacao-secao` | Eventos do log como ações reais na seção; regras de procedimento | Não |
| `revisor-independente` | Segunda leitura cética, sem receber a conclusão | Não |

### Como usar os agentes em cada etapa

O fluxo segue as portas de etapa do plano (§12) e o registro prévio. Nenhuma etapa pula a anterior.

| Momento | Quem | O que faz |
|---|---|---|
| Antes de começar uma fase | `estatistico-eleitoral` + `revisor-independente` | Conferem se a fase segue o registro prévio e se nada foi decidido depois de ver os dados |
| Ao escrever código | `engenheiro-dados` implementa; `revisor-independente` revisa o diff | Testes passando e código commitado antes de gerar dados |
| Ao interpretar um evento do log ou um procedimento | `operacao-secao` + `seguranca-urna` | Definição operacional validada contra o log e o Manual do Mesário |
| Antes de congelar o registro prévio | todos; `revisor-independente` por último, sem receber a conclusão | Nenhum campo em aberto; tag `registro-previo-v1` |
| Antes de divulgar qualquer número ou texto | `advogado-eleitoral` (linguagem) + `revisor-independente` (leitura cética) | Regra de linguagem da §9; todo número rastreável a `resultados.json` |
| Antes da publicação | revisores **humanos** externos (estatístico e segurança) | Os agentes não substituem essa revisão |

Exemplo de pedido: *"use o revisor-independente para revisar o diff de `src/tse/analise.py` contra o `docs/registro_previo.md`, sem dizer qual resultado esperamos"*.
