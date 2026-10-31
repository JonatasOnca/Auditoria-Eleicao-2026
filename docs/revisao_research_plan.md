# Revisão do RESEARCH_PLAN antes do registro prévio

> Revisão feita em **2026-10-31** por cinco papéis da equipe (`.claude/agents/`):
> estatística, engenharia de dados, operação da seção com segurança, direito
> eleitoral e revisão independente. O revisor independente leu o plano **sem** o
> checklist, para não ser guiado por ele. O objetivo é não repetir os erros do
> relatório de terceiros "Relatório Pericial Independente" (ver a avaliação em
> [avaliacao_relatorio_terceiros.md](avaliacao_relatorio_terceiros.md)).
>
> Esta é uma revisão feita por assistentes. Não substitui a revisão humana externa
> recomendada antes da divulgação.
>
> **Decisão de escopo do usuário:** a confirmação usa só 2026 (1º e 2º turnos), com
> declaração transparente do que já foi visto antes do congelamento do protocolo.

---

## 1. Checklist dos erros do Relatório Pericial

Status do plano **antes** das correções:

| # | Erro | Status | Onde | Correção (responsável) |
|---|---|---|---|---|
| E1 | Hora local lida como hora de Brasília | PARCIAL | §4; código `urna_logs.py:288-296` | Descrever no plano a regra de fuso ("Urna pronta" = 8h de Brasília, aceita nos primeiros 15 min; senão, horário nulo e contado). Aplicar o mesmo fuso a `DT_ABERTURA`/`DT_ENCERRAMENTO`. Testes para −2, −1, 0, +1 e indeterminado; hoje só o Acre é testado. Exterior (ZZ) analisado em separado (dados) |
| E2 | Encerramento lido como hora do voto | PARCIAL | §4, P6 leve | O código usa o horário do voto computado (correto). `closed_after_17` mede só o encerramento e não pode ser lido como voto. As variáveis das 19h estão no plano, mas **não existem no código** (dados) |
| E3 | Grandeza comparada com margem chamada de efeito | PARCIAL | P2, §8 | Medida de efeito com IC95% para cada RQ; efeito mínimo de interesse (SESOI) congelado; teste de equivalência (TOST); o teto de votos afetados com incerteza e sem atribuição a candidato (estatística) |
| E4 | Sem controles | PARCIAL | P2, P5, P6 | Lista única de covariáveis congelada: aptos, modelo de urna, % biometria cadastrada, idade, escolaridade, local de votação, efeito fixo de município. P3/P4 hoje sem controle. Antes × depois comparado com o mesmo contraste entre 16h–16h30 e 16h30–17h (estatística) |
| E5 | Sem linha de base nem placebo | PARCIAL | P7 | Placebos com janelas de mesma duração; placebos de 18h e 18h30 no regime das 19h; 1t × 2t comparado por estrato de cédula (número de cargos). O plano ainda trata 2022 como base principal (estatística) |
| E6 | Testes inadequados (gaussiana, Benford) | PARCIAL | P2, P4 | Wilcoxon sobre taxas não serve com 1 voto (mediana do 2t). Usar Mantel–Haenszel / logit condicional por seção (RQ1), permutação dentro da seção e proporção abaixo de T_min (RQ3), referência de Poisson calibrada antes das 17h (RQ2). Nada de Benford nem gaussiana (estatística) |
| E7 | Hipótese e limites depois de ver os dados | PARCIAL | §8, P7 | X, N, S sem valores e sem mecanismo. Congelar regras e o hash do script em tag git, com uma seção "já visto" (estatística, revisor) |
| E8 | Mecanismo mal descrito | PARCIAL | §1.1, §3.2, §4 | Ver §2 deste documento (operação/segurança) |
| E9 | Sem pacote de reprodução | PARCIAL | — | Ver §3 deste documento (dados) |
| E10 | Contexto político misturado | PARCIAL | §1.2, §9 | Regra explícita: o contexto fica na §1.2 e não entra em análise, figura ou conclusão. Ver a decisão pendente D1 (direito) |
| E11 | Retórica e acusação | PARCIAL | título, §9, P5 | Regra de linguagem com vocabulário fechado; título neutro; "votos fraudulentos aparecem" → "podem aparecer" (direito, revisor) |
| E12 | Muitos testes sem correção | **AUSENTE** | — | Família primária com Holm (α = 0,05); secundárias com BH-FDR (q = 0,05) rotuladas como exploratórias; sem p-valor por seção (estatística) |
| E13 | Falácia ecológica | PARCIAL | §1, §8, P5 | Toda conclusão no nível da seção; "votos afetados" é um teto, não atribuído a candidato (estatística) |

**Resultado:** nenhuma proteção estava completa. Uma estava ausente (E12).

---

## 2. Definições operacionais (E8) — achados de operação e segurança

Fontes: log 2026, `src/tse/urna_logs.py`, BU 2026 e o Manual do Mesário 2026 (TSE,
pp. 7, 9, 15, 18–21, 24–25).

1. **Nome errado da coluna no plano.** Em 2026 a coluna é `QT_ELEI_BIOM_SEM_HABILITACAO`.
   `QT_ELEITORES_BIOMETRIA_NH` e `DS_AGREGADAS` são nomes de 2022, mas a §3.2 os dá
   como "cabeçalho verificado".
2. **Há três vias de habilitação, não duas.**

   | Via | O que acontece | Marcador no log |
   |---|---|---|
   | Biométrica | Digital do eleitor reconhecida | "Tipo de habilitação do eleitor [biométrica]" |
   | **Biográfica** | Depois de 4 tentativas, ano de nascimento + **digital do Presidente da Mesa** | "Solicitação de dado pessoal…", "Dado digitado confere" |
   | **Sem biometria** | Eleitor sem digital cadastrada; ano de nascimento e assinatura, **sem digital de mesário** | "Ano de nascimento digitado é igual ao do cadastro", sem pedido de dado pessoal |

   O campo do BU mede a via **biográfica**: correlação de 0,996 por seção com
   `n_manual_com_biometria` nos dois turnos e −0,05 a −0,07 com `n_sem_biometria`. O BU
   soma 172 mil (1t) e 212 mil (2t) a mais que o log; a origem desse excedente não foi
   verificada. A §1.1 está errada ao dizer que a via sem biometria deixa rastro de
   mesário.
3. **Cerca de 1/3 das habilitações biográficas não tem mesário identificado no log.**
   Nos votos a partir das 16h, só 66% (2t) e 60% (1t) têm "Mesário N habilitou o
   eleitor". Há dois padrões ("digital não é de mesário registrado" e "não é possível
   associar a habilitação a um mesário"). A explicação provável, com confiança média, é
   um presidente ou substituto não registrado na urna.
4. **Regra do código a revisar.** A via biográfica é decidida por "Capturada a
   digital. Tentativa". Um voto com digital solicitada e nunca capturada cai em
   `sem_biometria`.

**Regras da §1.1:**

| Regra | Situação |
|---|---|
| Até 4 tentativas de digital | **Confirmada** (Manual pp. 18 e 21) |
| Dados da habilitação biográfica | **Confirmada**: documento com foto, ano de nascimento, digital do Presidente, assinatura no caderno |
| Senhas às 17h | **Confirmada**: encerramento só a partir das 17h de Brasília; senhas da última à primeira pessoa da fila (pp. 7 e 24) |
| Quem podia votar entre 17h e 19h no 2t | **Não confirmada**: o texto do Ofício-Circular 354/2026 não foi encontrado |
| Vias do BU | **Confirmada**: 5 obrigatórias + até 5 adicionais (p. 25) |
| Teste de integridade 2026 | **Não confirmada**: não há resultado consolidado publicado pelo TSE |

**Correções propostas:**
- `nh_rate_bio` = `QT_ELEI_BIOM_SEM_HABILITACAO / QT_COMPARECIMENTO` (via biográfica).
- No log, separar `bio_rate_*` e `semdig_rate_*` antes e depois do corte.
- Nova variável `manual_sem_mesario_id`.
- Fluxograma corrigido ("Presidente da Mesa", três vias).

---

## 3. Reprodutibilidade (E9) — achados de engenharia de dados

**O que existe:**
- comandos por etapa (`tse.espelho`, `tse.bu`, `tse.pipeline_urna`,
  `tse.reprocessar_logs`, `tse.consolidar`, `tse.bq_raw`, `tse.auditoria_carga`);
- 17 manifestos com sha512, e o `bu.py` confere cada ZIP com o `.sha512` oficial;
- `uv.lock`;
- 12 testes, que passam.

**Lacunas:**
1. Não há documento com a ordem dos comandos do zero, nem com o tempo e o disco de
   cada etapa (~134 GB no 2t).
2. `bq_raw.py` fixa projeto e bucket GCP privados; não há modo só local nem variável
   de ambiente.
3. O Dataform está em repositório separado, ignorado pelo git e vazio no checkout:
   as camadas acima da raw não são reproduzíveis a partir deste repositório.
4. O notebook não tem comando de execução documentado e depende de `data/` (ignorado
   pelo git).
5. **Há código sem commit** (`urna_logs.py`, `consolidar.py`, `tests/test_turnos.py`,
   `manifests/conciliacao_logs_bu_2026_2t.csv`) e um script fora do git
   (`corrigir_interrompidos.py`). O commit que gerou cada manifesto não fica registrado.
6. Não há hash das saídas finais nem uma tabela "número do relatório → consulta".
7. `uv run pytest` falha porque o `.venv` aponta para a pasta antiga do projeto. Com
   o ambiente recriado, passam 12 testes.
8. Os manifestos de conciliação e de carga não têm hash.

---

## 4. Problemas de desenho apontados pelo revisor independente

Em ordem de gravidade:
1. **Não há critério agregado de refutação.** A §8 define a seção anômala, mas não
   quantas sustentam ou refutam a afirmação, nem a taxa de falsos positivos esperada
   sem fraude.
2. **Limites livres.** X, N e S não estão fixados, e a P4 deixa escolher entre KS e
   Mann–Whitney (forking paths).
3. **Enquadramento enviesado.** A H₀ da RQ2 cai com uma única seção; o título fala em
   "voto fraudulento"; a P5 afirma que fraude "aparece como aglomerado" (Klimek não
   está calibrado para voto obrigatório e seções pequenas); a §1.2 biográfica não tem
   papel analítico.
4. **Fuso, relógio e exterior.** Faltam a conversão, UFs com mais de um fuso,
   Fernando de Noronha, a deriva de relógio e o exterior (ZZ). A checagem de total
   nacional inclui o exterior.
5. **Seleção na RQ1.** Só entram seções com votos depois das 17h, com denominadores
   minúsculos, e o conceito "sem biometria" mistura vias (ver §2).
6. **O regime das 19h é endógeno.** Ficar aberta depende de haver fila. O horário vem
   da imprensa. Ler 17h como 19h esconde o que ocorreu entre 17h e 19h. A §5.3 e a §11
   não incluem o 2t.
7. **Turnos com cédulas diferentes.** São 5–7 cargos no 1t e 1–2 no 2t. Δ`cand_share`
   entre turnos não está definido.
8. **RQ4/RQ5.** A associação com comparecimento é quase mecânica; falta direção e
   desfecho primário; com ~470 mil seções, tudo sai "significativo".
9. **O desenho detecta só uma forma de agir.** Votar por ausentes antes das 17h, em
   momentos ociosos, não deixa as três assinaturas. Um resultado nulo deve ser limitado
   a "não há rastro da forma descrita depois das 17h".
10. **Conciliação e versões.** Não há regra de inclusão para seções que não conciliam;
    o dicionário de eventos não tem versão; o piloto é descrito com 2022 AC.

---

## 5. Poder estatístico e números de referência (estatística)

Números da base atual. Só se olhou a quantidade de votos e dados de antes das 17h,
nenhum desfecho:

| | 1º turno | 2º turno |
|---|---|---|
| Seções com voto depois das 17h | 220.471 | 30.037 |
| Votos depois das 17h | 3,68 mi | 34.494 (mediana de 1 por seção) |
| Seções com ≥ 3 / ≥ 5 votos depois das 17h | 146.061 / 128.921 | 642 / 68 |

O total de 34.494 votos depois das 17h no 2º turno (log, método corrigido, 28 UFs)
bate com os ~34,4 mil divulgados pelo TSE à imprensa. É uma checagem cruzada
independente.

- **RQ1:**
  - 2º turno: efeito mínimo detectável de ~0,6–0,8 pp, cerca de 150–300 votos no país.
  - 1º turno: ~0,04 pp. Quase tudo sai significativo, por isso o SESOI é obrigatório.
- **RQ3 no 2º turno:** o teste dentro da seção é inviável; rajadas com N ≥ 5 só
  ocorrem em 68 seções.
- **RQ4/RQ5 no 2º turno:** só detectariam fraude que atingisse a maioria dos votos
  tardios e fosse para um único lado.
- **Teto do 2º turno:** 34.494 votos depois das 17h, incluindo os votos autorizados
  entre 17h e 19h.

**Desenho recomendado dentro de 2026:**
- **1º turno como base confirmatória principal.**
- **2º turno como estrato separado.** Confirmatórios só:
  - a checagem de integridade (P0);
  - a RQ2 às 19h;
  - os placebos em 18h e 18h30.

  A RQ1 e a RQ3 entre 17h e 19h ficam exploratórias.

**Regras para congelar** (calibradas só com dados de antes das 17h):

| Limite | Regra |
|---|---|
| T_min | Percentil 0,5 dos intervalos antes das 17h, por turno e estrato de cédula |
| S | Percentil 5 desses intervalos |
| N | 3, com sensibilidade em 5 |
| X | O maior entre 10 min e o p99,9 dos intervalos das 8h às 10h; "atividade" conta a identificação do eleitor |
| Condição 2 da §8 | ≥ 3 votos depois do corte e teste binomial contra a taxa da seção antes do corte; com 1–2 votos, a seção é "indeterminada" |
| Taxa de falso positivo | A regra aplicada às janelas de 16h00 a 16h30 |

**Regra de decisão do estudo:**
- **Apoia:** RQ1 e (RQ2 ou RQ3) significativas depois de Holm e acima do SESOI, com
  placebos abaixo de metade do efeito, mais seções anômalas que a referência calibrada
  e RQ4/RQ5 na mesma direção. Mesmo assim, é indício, não prova.
- **Refuta, em escala:** o teste de equivalência fica abaixo do SESOI em RQ1–RQ3, ou
  o teto superior do IC95% de votos afetados fica abaixo da margem.
- **Inconclusivo:** os demais casos.

---

## 6. Linguagem e riscos (direito)

**Regra de linguagem:**
- Termos permitidos: "anomalia estatística", "indício", "sinal compatível com",
  "desvio em relação à linha de base", "não explicado pelos controles".
- Termos proibidos nas conclusões: "fraude", "fraudulento", "irregularidade" (só ao
  citar uma decisão), "perícia", "laudo", "comprova", "manipulação". "Testar" é
  permitido; "provar" não.
- Publicar só agregados. Grupos com menos de 10 seções são suprimidos.
- Se surgir indício forte: não identificar a seção. Documentar com hash e código,
  mandar para revisão independente e encaminhar de forma reservada ao MP Eleitoral ou
  à Corregedoria do TRE.

**Riscos e mitigações:**
- **LGPD:** dados de mesários com base em estudo e pesquisa, minimização, nada
  abaixo do nível da seção.
- **CE art. 323 e Res. 23.610 art. 9-C:** título neutro, ressalva em cada saída,
  resultado nulo publicado com o mesmo destaque.
- **Crimes contra a honra:** só agregados.
- **Direito autoral do relatório de terceiros:** citar só o necessário para a crítica.

**Outros pontos:**
- Título sugerido: "Votação após as 17h nas eleições presidenciais: teste
  estatístico de uma afirmação sobre votos por ausentes".
- O README deve dizer que é um estudo estatístico independente, não auditoria oficial
  nem perícia.
- "Relato de eleitores do Nordeste" → "relato atribuído a eleitores"; o teste é
  nacional.
- §1.2: trocar "era legal" por "estava autorizado pela ordem judicial então vigente";
  corrigir o resumo do link da Metrópoles (a matéria fala em concordância de Nunes
  Marques).

---

## 7. Decisões pendentes do usuário

| # | Decisão | Recomendação dos revisores |
|---|---|---|
| D1 | O parágrafo da §1.2 sobre a relação de Zanin com Lula, incluído a pedido do usuário | Direito e revisor recomendam deixar como registro de contexto sem efeito na análise, ou em nota ou anexo, citando que impedimento e suspeição são decididos pelo STF (CPC arts. 144–145) |
| D2 | Título do plano ("Sinais de Voto Fraudulento") | Título neutro (§6) |
| D3 | Pasta do relatório de terceiros na raiz do repositório | Mover para `referencias/terceiros/` e levar a avaliação para `docs/` |
| D4 | O código sem commit e `corrigir_interrompidos.py` | Revisar e versionar **antes** do congelamento: o protocolo precisa apontar para um commit que gerou os dados |
| D5 | 1º turno como base confirmatória principal e 2º como estrato | Recomendado pela estatística; compatível com a decisão de usar só 2026 |

---

## 8. Próximos passos

1. O usuário decide D1–D5.
2. Corrigir o RESEARCH_PLAN (EN e PT-BR) com as seções 1 a 6 deste documento.
3. Escrever `docs/registro_previo.md` e `docs/reproducao.md`.
4. Pré-requisitos do congelamento:
   - código versionado (D4);
   - reprocessamento do 1º turno concluído;
   - variáveis das 19h e das três vias implementadas e testadas;
   - `.venv` recriado.
5. Congelar o protocolo com tag git e só então rodar as análises confirmatórias.
