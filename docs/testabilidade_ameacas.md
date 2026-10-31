# Testabilidade das ameaças com os dados disponíveis

> Para cada etapa do [modelo de ameaças](modelo_de_ameacas.md), o que dá para testar
> com os dados oficiais do TSE que o projeto **já tem**, o que precisa de trabalho
> extra e o que não é testável com dados abertos.
>
> Situação em **2026-10-31**. Os números das §3 e §4 são **preliminares**: o
> reprocessamento dos logs com o método corrigido ([reprocessamento_logs.md](reprocessamento_logs.md))
> ainda está rodando.

---

## 1. Resumo

| # | Etapa / ameaça | Testável? | Prioridade |
|---|---|---|---|
| 4 | Mesa: mesário votando por ausentes, habilitação sem biometria | **Sim, já** | 1 |
| 5 | Contingência, troca de urna, cédula | **Sim, já** | 2 |
| 3 | Carga das urnas | **Sim, em boa parte** | 2 |
| 7 | Transmissão e totalização | **Em parte** | 3 |
| 6 | BU alterado entre a urna e a totalização | **Sim, com trabalho extra** | 3 |
| 9 | Governança (prorrogação até as 19h) | **O efeito, sim**; a decisão, não | 1 (junto com a 4) |
| 1 | Cadastro eleitoral | **Fraco** (falta base de outras eleições) | 4 |
| 10 | Pré-eleitoral | **Só contexto** | 4 |
| 2 | Software do TSE | **Não** | — |
| 8 | Voto dentro da urna (sem registro em papel) | **Não diretamente** | — |

---

## 2. Base disponível

Só **2026, 1º e 2º turnos**. Não há nada de 2022 no projeto, embora o
RESEARCH_PLAN conte com 2022 como base principal.

| Fonte | Onde | Conteúdo útil |
|---|---|---|
| Boletim de urna (CSV) | BigQuery `boletim_urna`, `boletim_urna_2t`; local `data/bu_2026_{1,2}t/` | 499.206 seções (1º) e 499.205 (2º); aptos, comparecimento, `QT_ELEI_BIOM_SEM_HABILITACAO`, `DT_ABERTURA`, `DT_ENCERRAMENTO`, `DT_EMISSAO_BU`, `DT_BU_RECEBIDO`, `DS_TIPO_URNA`, `NR_URNA_EFETIVADA` |
| Logs das urnas | BigQuery `log_urna`, `log_urna_2t`; variáveis por seção em `data/logs_2026_{1,2}t/` | Votos antes/depois das 17h, intervalos, tipo de habilitação, mesários distintos na habilitação manual, logs de outra seção, votos interrompidos |
| Logs de preparação (GEDAI) | BigQuery `log_gedai`, `log_gedai_2t` | Carga das urnas |
| Correspondências | `correspondencia_secao`, `correspondencia_efetivada`, `correspondencia_contingencia` (e `_2t`) | Urna esperada × efetivada; contingência |
| Pacotes das urnas | ZIPs `bu_imgbu_logjez_rdv_vscmr_2026_{1t,2t}_{UF}` no bronze | BU, imagem do BU, RDV e assinaturas de cada seção. **Hoje só o log é extraído** |
| Eleitorado 2026 | `perfil_eleitorado`, `perfil_eleitor_secao`, `transferencia_temporaria(_secao)`, `eleitorado_local_votacao` | Perfil por seção; transferência temporária |
| Mesários | `convocacao_mesarios`, `convocacao_mesarios_funcoes_especiais` | Agregado |
| Denúncias (Pardal) | `denuncia` | Tipo e município |
| Totalização | `data/raw/resultados-2026/Relatorio_Resultado_Totalizacao_2026_*.zip` | Resultado por UF |

**O que falta:** eleitorado, BUs e logs de 2022 (ou 2024); histórico da
totalização de 2026 ao longo da noite; resultados do teste de integridade de 2026.

---

## 3. Por etapa

### Etapa 4 — Mesa (núcleo do projeto) — **testável já**
- **Variáveis prontas no log:** `votos_apos_17`, `gap_antes_17_min`,
  `votos_ultimos_10min_antes_17`, `intervalo_apos_17_mediana_s`,
  `intervalo_apos_17_min_s`, `n_sem_biometria_apos_17`,
  `n_manual_com_biometria_apos_17`, `mesarios_distintos_manual_apos_17`.
- **Com o BU:** comparecimento e votos para Presidente por seção; isso cobre RQ1–RQ5
  e o fingerprint de Klimek (P5).
- **Comparação natural entre turnos:** no 2º turno, votar entre 17h e 19h numa seção
  ainda aberta era legal; no 1º, não.
- **Falta:** criar as variáveis do regime das 19h (`extended_regime`,
  `closed_before_decision`, `votes_17_19`, `votes_after_19`, `gap_before_19`).
  O horário de corte (~17h03) precisa ser confirmado com a íntegra da Rcl 101.673/BA.

### Etapa 9 — Efeito da prorrogação — **testável junto com a 4**
Números preliminares do 2º turno, só com as 27 UFs já reprocessadas pelo método
corrigido (**sem SP**; 395.522 seções):

| Encerramento (log, hora de Brasília) | Seções |
|---|---|
| Até 17h03 | 348.635 |
| Entre 17h03 e 19h | 43.801 |
| Depois das 19h | 2.290 |
| Sem horário de encerramento no log | 796 |

- 22.474 seções tiveram ao menos um voto depois das 17h, somando 25.671 votos.
  Desses votos, 21.085 foram por biometria, 2.095 por habilitação manual com
  biometria e 2.491 sem biometria.
- Só **6 seções** têm o último voto às 19h ou depois.
- Há 43.801 seções encerradas entre 17h03 e 19h, mas só 22.474 com voto depois
  das 17h. Isso sugere que muitas seções ficaram abertas sem receber votos. Precisa
  conferir.
- Também precisam ser conferidas as 2.290 seções encerradas depois das 19h
  (procedimento de encerramento demorado ou outra causa).

### Etapa 5 — Contingência — **testável já**
- No CSV do BU, as 499.206 / 499.205 seções aparecem como `Apurada` nos dois turnos.
  Não há seção com votação por cédula.
- A troca de urna se mede pelas tabelas `correspondencia_*` e
  `correspondencia_contingencia`, por `NR_URNA_EFETIVADA` e pelos eventos de
  contingência no log. O 2º turno registrou só 7 seções com log de outra seção no
  pacote e 49 votos interrompidos por queda de energia (27 UFs).
- **A fazer:** taxa de contingência por UF e município, e se as seções com troca de
  urna concentram os sinais da etapa 4.

### Etapa 3 — Carga das urnas — **testável em boa parte**
- `log_gedai(_2t)` × `correspondencia_efetivada(_2t)`: a urna que votou é a que foi
  preparada para a seção? O horário de carga é coerente com o calendário?
- `urna_pronta_local` no log: horário de abertura por seção.
- **A fazer:** fazer o pareamento GEDAI × correspondência × BU e listar as
  divergências.

### Etapa 7 — Transmissão — **testável em parte**
- `DT_BU_RECEBIDO − DT_ENCERRAMENTO` por seção e UF (P8). `DT_ENCERRAMENTO` está em
  hora local; é preciso converter com o fuso da seção, já determinado no log
  (`fuso_determinado`).
- No 2º turno, a pausa no recebimento de BUs aparece como um vazio em
  `DT_BU_RECEBIDO`.
- **Não dá:** reconstruir a evolução da apuração nacional de 2026 sem o histórico de
  totalização.

### Etapa 6 — BU entre a urna e a totalização — **testável com trabalho extra**
- Os ZIPs no bronze já têm `bu`, `imgbu` e `rdv` de cada seção.
- **Teste proposto:**
  1. Decodificar o BU assinado.
  2. Comparar com a imagem do BU impresso e com o CSV publicado.
  3. Recontar o RDV e comparar com o BU.
  4. Conferir as assinaturas.
- É o teste mais forte disponível contra fraude **depois** da urna. Custa pouco em
  processamento porque reaproveita a leitura dos ZIPs feita pelo `tse.reprocessar_logs`.

### Etapa 1 — Cadastro — **fraco**
- Dá para olhar a proporção de transferências temporárias e o perfil por seção em
  2026.
- O teste principal (crescimento de aptos por município entre eleições) exige o
  eleitorado de 2022/2024, que não foi baixado.
- Pela regra do projeto, não se usam dados externos (IBGE, óbitos).

### Etapa 10 — Pré-eleitoral — **só contexto**
- `denuncia`: contagem por tipo e município e comparação com as seções marcadas
  (P9). Não é prova.

### Etapas 2 e 8 — **não testáveis diretamente**
- Os dados abertos não trazem nada sobre o desenvolvimento do software.
- Sobre o voto dentro da urna, sobram a consistência estatística entre seções e
  turnos e, com a etapa 6, a coerência RDV × BU. Isso não detecta uma alteração
  feita antes de o voto chegar ao RDV.
- Os resultados do teste de integridade de 2026 não estão nos datasets espelhados.
  Seriam a única evidência direta.

---

## 4. Ponto a verificar antes de qualquer conclusão

No 1º turno, com o método **anterior** e sem SP (395.520 seções), o log mostra
192.423 seções com voto depois das 17h, somando 3.566.945 votos (242.276 sem
biometria e 184.023 com habilitação manual). No 2º turno são 25.671 votos.

A diferença pode ter explicação legítima: o 1º turno tem mais cargos, o que alonga
cada voto e forma fila. Mas também pode vir do método antigo ou da conversão de
fuso. **Não tirar conclusão** até:
1. o reprocessamento do 1º turno terminar com o método corrigido;
2. conferir a conversão de fuso nas UFs fora do horário de Brasília;
3. comparar com `DT_ENCERRAMENTO` do BU.

---

## 5. Próximos passos

1. Terminar o reprocessamento (2º turno: falta SP; depois o 1º turno inteiro).
2. Etapas 4 e 9: implementar as variáveis do regime das 19h e rodar RQ1–RQ5 nos dois
   turnos.
3. Etapas 5 e 3: pareamento GEDAI × correspondência × BU; taxa de contingência.
4. Etapa 6: extrair BU, imagem do BU e RDV dos ZIPs e fazer a conferência cruzada.
5. Ampliar a base: eleitorado e BUs de 2022 (ou 2024), para a etapa 1 e para a linha
   de base do plano.
6. Pedir ou localizar os resultados do teste de integridade de 2026 (TSE/TREs).
