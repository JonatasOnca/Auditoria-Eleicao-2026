# API de Resultados do TSE: endpoints (ciclo 2026)

Fonte oficial: o app e o site <https://resultados.tse.jus.br>. Os endpoints foram extraídos do bundle JavaScript do app em 2026-10-12. Os padrões usados em 2022 (`dados-simplificados/...-r.json`) **não existem mais** em 2026.

Base: `https://resultados.tse.jus.br/oficial/{ciclo}/`, com `ciclo = ele2026`. Não há autenticação, e todos os números vêm como **string** com vírgula decimal.

## Códigos (de `/oficial/comum/config/ele-c.json`)
| Eleição | 1º turno | 2º turno | Cargos |
|---|---|---|---|
| Federal | 6257 | 6258 | 1 Presidente |
| Estadual | 6259 | 6260 | 3 Governador, 5 Senador, 6 Dep. Federal, 7 Dep. Estadual, 8 Dep. Distrital |

O pleito é 1219 (04/10/2026).

## Endpoints
| Recurso | Caminho |
|---|---|
| Lista de eleições (todos os ciclos) | `/oficial/comum/config/ele-c.json` |
| UFs, municípios (código TSE e IBGE) e zonas | `{ele}/config/mun-e{ele:06}-cm.json` |
| Resultado "unificado" de um cargo | `{ele}/dados/{uf}/{uf}{mun:05?}{-z{zona:04}?}-c{cargo:04}-e{ele:06}-u.json` |
| Candidatos eleitos | `{ele}/dados/{uf}/{uf}-c{cargo:04}-e{ele:06}-e.json` |
| Acompanhamento da totalização (BR/UF) | `{ele}/dados/{uf}/{uf}-e{ele:06}-ab.json` |
| Configuração dos arquivos de urna por UF | `arquivo-urna/{pleito}/config/{uf}/{uf}-p{pleito:06}-cs.json` |
| Arquivos de uma seção (BU, RDV, log) | `arquivo-urna/{pleito}/dados/{uf}/{mun:05}/{zona:04}/{secao:04}/p{pleito:06}-{uf}-m{mun:05}-z{zona:04}-s{secao:04}-aux.json` |

Exemplos:
- `ele2026/6257/dados/br/br-c0001-e006257-u.json`: Presidente, Brasil
- `ele2026/6259/dados/sp/sp71072-c0003-e006259-u.json`: Governador, município de São Paulo
- `uf = zz` é o exterior (só vota para presidente)

O endpoint `arquivo-urna/...` (configuração dos arquivos de urna) retornou 404 em 2026-10-12 quando chamado como `.json`. Ainda não foi testado na forma `.jws` nem com outros códigos de pleito. Os arquivos por seção serão obtidos pelo Portal de Dados Abertos na Fase 2.

## Assinatura digital (JWS)
Em produção, o app oficial (v26.10.9, flag `assinaturaJwsAtiva = true`) não lê o `.json`. Ele troca a extensão para **`.jws`**, no mesmo caminho, e só exibe os dados depois de verificar a assinatura:

- Formato: JWS compacto `base64url(header).base64url(payload).base64url(assinatura)`, com header `{"kid": "sNbt9Q_fLS65zE1_ZLNV-XRRwPY", "typ": "JOSE", "alg": "EdDSA"}`.
- Chave pública Ed25519 (ambiente `prod`): `x = kWlpNHjuws1csyQZwzn3Fhzbi3RD435RbpThtSr4hMc`. Ela está embutida no app e publicada em `/oficial/app/assets/assinatura-jws/prod.jwk.json`.
- O payload é exatamente o JSON do `.json` correspondente; isso foi verificado em 2026-10-12 em 5 arquivos.
- O app anexa `?nocache=<epoch ms>` a cada requisição.

`tse.resultados_api.ResultadosTSE` faz o mesmo: lê o `.jws`, verifica a assinatura e rejeita o arquivo com `AssinaturaInvalida` se ela não conferir. Também confere se a chave publicada mudou (rotação de chave). Com `snapshot_dir`, grava os tokens `.jws` originais, que qualquer pessoa pode verificar com a chave pública acima.

## Campos principais do `-u.json`
- `dg`/`hg`: data e hora de geração. `s`: seções (`ts` total, `st` totalizadas, `pstn` em %).
- `e`: eleitorado (`te`), comparecimento (`c`), abstenção (`a`).
- `v`: votos totais (`tv`), válidos (`vv`), nominais (`vnom`), legenda (`van`), brancos (`vb`), nulos (`tvn`), nulos técnicos (`vnt`).
- `carg[].agr[]` (coligações) contém `par[]` (partidos), que contém `cand[]` (candidatos). Cada candidato tem número `n`, nome de urna `nmu`, votos `vap`, % de válidos `pvapn`, situação `st` e flag de eleito `e`.

## Observação
O eleitorado de uma UF é ligeiramente maior para Presidente do que para os cargos estaduais. Em AC são 613.742 contra 613.316. A diferença corresponde a eleitores em trânsito vindos de outras UFs, que só podem votar para Presidente.
