# Registro prévio do estudo

> **Status: RASCUNHO, ainda não congelado.** Este documento só vale como registro prévio
> depois de congelado com a tag git `registro-previo-v1` (§9). Até lá, qualquer item pode
> mudar. Depois do congelamento, toda mudança vai para a tabela de desvios (§10).
>
> Base: `RESEARCH_PLAN-pt-br.md` §2, §4, §6 e §8, e a revisão em
> [revisao_research_plan.md](revisao_research_plan.md). Em caso de conflito, prevalece
> este documento congelado.
>
> Os valores marcados com **[revisão humana]** devem ser revistos por um estatístico
> humano antes do congelamento.

---

## 1. Pergunta e escopo

**Afirmação em teste.** Depois das 17h, mesários votariam no lugar de eleitores ausentes.

**Pergunta.** As seções eleitorais mostram, depois do corte, os rastros que essa prática
deixaria no log da urna?
- habilitação não biométrica acima da própria linha de base;
- votos sem fila;
- intervalos curtos demais para um eleitor real.

**Escopo.**
- Eleição: Presidente 2026.
- **Base confirmatória principal: 1º turno.** O 2º turno é um estrato separado (§5).
- Unidade de análise: seção × turno.
- Seções do exterior (ZZ) analisadas em separado.
- Só dados oficiais do TSE.

**O que um resultado nulo significa.** Que não há rastro da prática **na forma descrita,
depois do corte**. Votos dados em momentos ociosos antes das 17h não deixariam esses
rastros e ficam fora do alcance deste desenho.

---

## 2. O que já foi visto antes do congelamento (transparência)

O usuário decidiu usar só 2026, sabendo que parte dos dados já foi examinada. Tudo o
que está abaixo foi visto **antes** deste protocolo e conta só como **exploratório**:

| O que foi visto | Onde | Turno |
|---|---|---|
| Distribuição dos horários de encerramento (até 17h03, 17h03–19h, depois das 19h) | `docs/testabilidade_ameacas.md` §3 | 2t |
| Total de votos depois das 17h (34.494) e depois das 19h; seções com voto depois das 17h | idem; `docs/revisao_research_plan.md` §5 | 2t |
| Habilitações por tipo, total e depois das 17h | `docs/avaliacao_relatorio_terceiros.md` | 2t |
| Correlação por seção entre taxa biográfica e % de um candidato (com e sem efeito fixo de UF/município) | idem | 1t e 2t |
| Regressão dentro do município de % candidato sobre taxa biográfica | idem | 2t |
| Votos depois das 17h pelo método antigo (3,57 mi) | `docs/testabilidade_ameacas.md` §4 | 1t |
| Reprodução dos capítulos do relatório de terceiros (percentuais extremos, Benford, janelas de encerramento) | `docs/avaliacao_relatorio_terceiros.md` | 1t e 2t |
| Quantidade de votos depois das 17h e percentis dos intervalos **antes** das 17h (para o cálculo de poder) | `docs/revisao_research_plan.md` §5 | 1t e 2t |

**Consequências:**
- **RQ5 e o contraste 1t × 2t não contam como confirmatórios.** São relatados, mas
  rotulados como exploratórios.
- Na RQ1–RQ3 do 1º turno, até agora só se viram quantidades de votos e dados de antes
  das 17h, que servem de calibração e não de desfecho. **Essas RQs continuam
  confirmatórias.**
- Os desfechos da RQ1–RQ4 do 1º turno (taxas depois do corte, seções sem fila,
  intervalos depois do corte) **não podem ser calculados antes do congelamento.**

---

## 3. Dados e versões

- **Insumos:** BU (`bweb_{1t,2t}_*.csv`), pacotes de urna
  (`bu_imgbu_logjez_rdv_vscmr_2026_{1t,2t}_*.zip`), perfil do eleitorado por seção,
  correspondências e modelo de urna. URL, data e sha512 de cada um estão em `manifests/`.
- **Método de contagem do log:** `src/tse/urna_logs.py` no commit do congelamento.
  Inclui as regras de log de outra seção, voto interrompido gravado ou perdido e fuso.
- **Fuso da seção:** hora de "Urna pronta para receber votos" − 8. A regra só é aceita
  nos primeiros 15 min da hora e com resultado em {−2, −1, 0, +1}. Fora disso o horário
  fica nulo e a seção sai das análises de horário, com contagem relatada.
- **Horários de voto:** "O voto do eleitor foi computado" no log. `DT_ENCERRAMENTO`
  nunca é usado como horário de voto.

---

## 4. Variáveis e definições

As definições estão na §4 do plano. Para este protocolo:

**Corte:**
- 17h00 de Brasília no 1º turno.
- No 2º turno:
  - 17h00 nas seções `closed_before_decision`;
  - 19h00 nas seções `extended_regime`.
- O horário da decisão vem do documento oficial. Se ele não estiver disponível no
  congelamento, usa-se 17h03, com sensibilidade de ±30 min.

**Vias de habilitação:**
- **biográfica:** "Solicitação de dado pessoal…";
- **sem biometria:** "Ano de nascimento digitado…" sem esse pedido;
- **biométrica:** "[biométrica]".
- "Não biométrica" = biográfica + sem biometria.

**Estrato de cédula:** número de cargos votados no turno da UF. Exemplo: 2º turno com e
sem Governador.

**Covariáveis (lista fechada):**
- log(aptos);
- modelo de urna;
- % do eleitorado com biometria cadastrada, se o perfil de 2026 trouxer;
- % de 60 anos ou mais;
- % com até ensino fundamental;
- efeito fixo de município.

---

## 5. Hipóteses confirmatórias

| # | H₁ (direção) | Teste | Medida de efeito | SESOI **[revisão humana]** |
|---|---|---|---|---|
| RQ1a | Chance de habilitação **biográfica** maior depois do corte que antes, dentro da seção | Mantel–Haenszel / logit condicional por seção, unilateral | Razão de chances (OR), IC95% | OR = máx(1,25; 2 × OR do contraste de referência 16h–16h30 × 16h30–17h) |
| RQ1b | Idem para habilitação **sem biometria** | idem | idem | idem |
| RQ2 | Mais seções com voto depois do corte e sem identificação de eleitor nos X min anteriores do que o esperado | Observado × esperado por Poisson (Σ exp(−λᵢX), λᵢ estimado entre 16h00 e 16h50), unilateral; IC por bootstrap de seções | Excesso de seções e razão observado/esperado | Razão ≥ 1,5 |
| RQ3 | Proporção de intervalos depois do corte abaixo de T_min maior que antes do corte | Permutação dentro da seção (10.000 permutações, semente 20261031), unilateral | Diferença de proporções, IC95% | +1 ponto percentual |
| RQ4 | Indicadores RQ1–RQ3 associados a comparecimento mais alto | Regressão linear com covariáveis e efeito fixo de município, erro agrupado por município, unilateral | β por desvio-padrão do indicador | +0,5 pp de comparecimento |

**No 2º turno** (estrato separado), são confirmatórios só:
- **P0, integridade:**
  - voto computado depois do encerramento da urna;
  - voto depois das 19h;
  - voto depois das 17h em seção `closed_before_decision`.
- **RQ2 às 19h** nas seções `extended_regime`.
- **Placebos de 18h e 18h30.**

A RQ1 e a RQ3 na janela de 17h a 19h ficam exploratórias.

**Exploratórias, em qualquer turno:**
- RQ5 (votação dos candidatos);
- contraste 1t × 2t;
- fingerprint de Klimek;
- análises por UF e região;
- o subgrupo Nordeste, que é definido de antemão mas fica fora da família primária.

---

## 6. Limites (regras calculadas só com dados de antes das 17h)

| Limite | Regra | Sensibilidade |
|---|---|---|
| T_min | Percentil 0,5 dos intervalos entre votos consecutivos antes das 17h, por turno e estrato de cédula | Percentil 1 |
| S | Percentil 5 dos mesmos intervalos | Percentil 10 |
| N | 3 votos não biométricos consecutivos | 5 |
| X | máx(10 min; percentil 99,9 dos intervalos entre identificações de eleitor das 8h às 10h) | 5, 15, 20, 30 min |
| Mínimo de votos depois do corte para a condição 2 | 3 (com 1–2 votos a seção é "indeterminada") | — |

Os valores numéricos resultantes são calculados pelo script de análise no commit
congelado e gravados no arquivo de resultados antes de qualquer desfecho.

---

## 7. Critérios de inclusão e exclusão (decididos antes)

| Situação | Tratamento |
|---|---|
| Fuso indeterminado | Fora das análises de horário; contagem relatada |
| Log × BU não concilia (votos do log ≠ `QT_COMPARECIMENTO`) | Incluída na análise principal, com marcação. Sensibilidade sem essas seções |
| Seção agregada (`DS_SECOES_AGREGADAS`) | Incluída; sensibilidade sem elas |
| Urna substituída / contingência / log de outra seção | Incluída; sensibilidade sem elas |
| Exterior (ZZ) | Análise separada, fora da família primária |
| Seção sem nenhum voto depois do corte | Entra em RQ2 (denominador) e RQ4; não entra em RQ1/RQ3 |

Toda exclusão é relatada com contagem por UF.

---

## 8. Regra de decisão

**Múltiplos testes:**
- Família primária: RQ1a, RQ1b, RQ2, RQ3 e RQ4 no 1º turno, mais os confirmatórios do
  2º turno (§5). Correção de Holm, α = 0,05.
- Demais análises: BH-FDR, q = 0,05, rotuladas como exploratórias.
- Nenhum p-valor por seção.

**Conclusão do estudo:**
- **Apoia (indício, não prova):**
  - RQ1 (a ou b) e (RQ2 ou RQ3) significativas depois de Holm e acima do SESOI;
  - placebos abaixo de metade do efeito;
  - número de seções anômalas acima da referência calibrada (regra aplicada às 16h00–16h30);
  - RQ4 na mesma direção.
- **Refuta em escala:** TOST abaixo do SESOI em RQ1–RQ3, ou o limite superior do IC95% do
  teto de votos afetados abaixo da margem nacional do turno.
- **Inconclusivo:** os demais casos.

**Relato obrigatório**, com o mesmo destaque para resultado positivo ou nulo:
- todas as RQs primárias, com efeito, IC e p ajustado;
- os placebos;
- as sensibilidades;
- o teto de votos afetados (sem atribuição a candidato) comparado com a margem.

**Linguagem:** a regra da §9 do plano.

---

## 9. Procedimento de congelamento

**Pré-requisitos** (todos registrados antes da tag):
1. reprocessamento dos logs concluído nos dois turnos;
2. código que gerou os dados commitado;
3. testes passando;
4. variáveis `tz_offset`, `bio_rate_*`, `semdig_rate_*`, `manual_sem_mesario_id` e
   regime das 19h implementadas e testadas;
5. script de análise escrito e testado **com dados simulados**, nunca com os desfechos
   reais;
6. revisão deste documento pelo `revisor-independente` e, se possível, por um
   estatístico humano.

**Congelamento:**
1. Preencher a tabela abaixo.
2. Commitar.
3. Criar a tag `registro-previo-v1` (assinada, se possível).
4. Fazer o push da tag.

| Campo | Valor |
|---|---|
| Data do congelamento | — |
| Commit | — |
| Hash (sha256) do script de análise | — |
| Manifestos dos insumos (arquivo e sha512) | — |

**Rodada confirmatória:**
- uma única vez, a partir do commit com a tag;
- a saída vai para `resultados/` com o hash dos insumos;
- qualquer rodada adicional é exploratória ou registrada como desvio.

---

## 10. Desvios

| Data | Item | Mudança | Motivo | Efeito esperado |
|---|---|---|---|---|
| — | — | — | — | — |
