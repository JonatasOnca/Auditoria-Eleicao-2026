# Auditoria Eleição 2026

O projeto analisa o comportamento eleitoral nas Eleições Gerais de 2026 e faz uma auditoria estatística dos resultados, usando **apenas dados oficiais do TSE**.

> **Ressalva metodológica:** uma anomalia estatística (desvio de Benford, comparecimento atípico, urnas substituídas etc.) é um **sinal para investigação**, não uma prova de fraude. Todo achado precisa ser rastreável até o arquivo oficial do TSE (URL e hash) e confrontado com explicações operacionais conhecidas antes de qualquer conclusão.

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
