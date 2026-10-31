# Research Plan — Voting After 17:00 in Brazilian Presidential Elections: A Statistical Test of a Claim About Votes Cast for Absent Voters

> **Portuguese version: [RESEARCH_PLAN-pt-br.md](RESEARCH_PLAN-pt-br.md).** Both files carry the same content and
> must be updated together.

> Self-contained hand-off document: the claim, the questions, the verified data
> sources, the variables, every analysis step, and the checks.

> **Nature of this work:** an independent statistical study with public TSE data. It is
> not an official audit nor a forensic report (*perícia*).

**Scope decisions**
- **Geography:** all 27 states (Brasil inteiro); sections abroad (ZZ) analysed separately.
- **Elections:** 2026 President only. The **1st round is the primary confirmatory dataset**; the **2nd round is a separate stratum** (different ballot and the court-ordered 19:00 regime, §1.2). Part of the 2026 data was seen before the protocol was frozen; this is declared in `docs/registro_previo.md`, and those analyses count as exploratory. 2022 is an optional future replication, not part of this study.
- **Unit of analysis:** polling section × round.

---

## 1. Claim under test

A report attributed to voters alleges a common practice: after the
polls close at 17:00, poll workers (*mesários*) already know which registered
voters did not show up and cast ballots in their names. The test is national;
the Northeast is a pre-specified subgroup.

The goal is to **test** the claim with public data, not to prove it. If the
practice exists at scale, it should leave measurable traces in the voting-machine
logs and section results. If those traces are absent, that is also a valid
finding, limited to the form of the practice described here (§8).

**Key constraint (vote secrecy):** no public file links an individual vote's
timestamp to the candidate chosen. The machine log has timestamps but no
candidate; the RDV has candidates but is shuffled. All candidate-level analysis
is therefore **ecological** (section level), never vote level.

### 1.1 How a polling section works, and what each step leaves in the data

The claim is about what happens inside a polling section, so the analysis has to
follow the section's own procedure. Each step below lists the **data trail** it
leaves. Log messages are quoted exactly as they appear in the 2026 `logd.dat`
files (application `VOTA` unless noted). Rules marked *(confirm)* come from
general knowledge of the procedure and still need to be checked against the TSE
resolution for 2026.

**Who is in the section**

| Role | What they do | Trace in public data |
|---|---|---|
| Presiding officer (*presidente da mesa*) | Opens and closes the voting, decides on incidents, signs the minutes | Operator actions in the log ("Operador selecionou: Encerrar votação") |
| Poll workers (*mesários*, *secretários*) | Identify voters, type the voter id into the poll-worker terminal, enable voters manually when the fingerprint fails, collect signatures on the voter list | Summons in `convocacao_mesarios` (aggregate only); in the log, "Mesário N habilitou o eleitor" and the poll-worker registration events (their voter ids are **not** stored by this project) |
| Party inspectors (*fiscais*) and delegates (*delegados*) | Watch opening, voting and closing; may file complaints in the minutes and ask for a printed copy of the BU | **None.** Their presence and the section minutes (*ata*) are not in the open data, so claims about "sections without inspectors" cannot be tested here |
| Electoral judge and technicians | Machine replacement (contingency), data recovery, ballot counting by the board when paper is used | Contingency and recovery events in the log; `DS_TIPO_URNA`, correspondence files (CESP/CEFT) |

**Flow of the day**

```mermaid
flowchart TD
    A["Before 8:00: machine switched on<br/>zero report printed (zerésima)"] --> B["8:00 Brasília: voting released"]
    B --> C["Poll worker types voter id<br/>(título or CPF)"]
    C --> D{"Fingerprint<br/>registered?"}
    D -- yes --> E{"Fingerprint<br/>recognised?"}
    E -- yes --> H["Voter enabled<br/>(biometric)"]
    E -- "no, after up to 4 attempts" --> F["Biographic enabling<br/>year of birth checked,<br/>then the Presiding officer's fingerprint"]
    D -- no --> G["Enabled without biometrics<br/>year of birth + signature<br/>(no poll-worker fingerprint)"]
    F --> I["Voter enabled<br/>(biographic: BU field<br/>QT_ELEI_BIOM_SEM_HABILITACAO)"]
    G --> J["Voter enabled<br/>(no fingerprint attempt)"]
    H --> K["Voter votes for each office<br/>last one: President"]
    I --> K
    J --> K
    K --> L["Vote stored<br/>voter signs the paper list"]
    L --> C
    L --> M{"17:00 Brasília"}
    M -- "people still in line<br/>(they get a number)" --> C
    M -- "line empty" --> N["Presiding officer closes voting"]
    M -. "2026 2nd round only: section still open<br/>at the court order (~17:03)" .-> X["Voting continues until 19:00<br/>(STF, Rcl 101.673/BA, see 1.2)"]
    X -.-> C
    X -. "19:00 or line empty" .-> N
    N --> O["BU printed in several copies<br/>one posted at the door,<br/>copies to inspectors"]
    O --> P["Result media sent for transmission<br/>BU, RDV, log published later by TSE"]
    B -. "machine fails" .-> Q["Restart the same machine<br/>or replace it (contingency):<br/>the memory card carries<br/>the votes already cast"]
    Q -. "last resort" .-> R["Paper ballots<br/>(DS_TIPO_URNA not Apurada)"]
    Q -.-> C
```

**Data trail of each step**

| Step | Log messages (2026) | Other files |
|---|---|---|
| Zero report and opening | "Gerando relatório [ZERÉSIMA] [INÍCIO]", "Urna pronta para receber votos" (local machine time: 06:00:01 in Acre is 8:00 in Brasília) | `DT_ABERTURA` in the BU (also local time) |
| Voter identification | "Aguardando digitação do identificador do eleitor", "Identificador do eleitor digitado pelo mesário", "Identificador digitado pelo mesário foi: (Título de eleitor)" or "(CPF)" | — |
| Biometric enabling | "Solicita digital. Tentativa [N] de [4]", "Capturada a digital. Tentativa [N] de [4]", "Tipo de habilitação do eleitor [biométrica]" | — |
| Biographic enabling (after 4 failed fingerprints) | Fingerprint attempts, then "Solicitação de dado pessoal do eleitor para habilitação manual", "Dado digitado confere", "Solicita digital do mesário" (the machine requires the poll worker's own fingerprint), "Mesário N habilitou o eleitor". The fingerprint is the Presiding officer's (Manual do Mesário 2026, p. 21). Only ~60–66% of these votes carry "Mesário N habilitou o eleitor"; the rest show "Biometria coletada não é do mesário…" or "Não é possível associar a habilitação a um mesário" (officer not registered on the machine) | `QT_ELEI_BIOM_SEM_HABILITACAO` in the BU (day total, not split by hour); correlation 0.996 per section with this log path |
| Enabling without biometrics (no fingerprint on file) | "Ano de nascimento digitado é igual ao do cadastro" (or "… é diferente do cadastro") without prior "Capturada a digital" or "Solicitação de dado pessoal…". No poll-worker fingerprint | Not in the BU field |
| Vote | "Eleitor foi habilitado", "Voto confirmado para [Governador]" (where there is a runoff), "Voto confirmado para [Presidente]", "O voto do eleitor foi computado" | RDV (shuffled votes), BU totals |
| Closing | "Operador selecionou: Encerrar votação", "Todas as pessoas presentes já votaram? SIM", "Gerando relatório [BU] [INÍCIO]", "Gerando arquivo de resultado [bu.dat] + [Início]" | `DT_ENCERRAMENTO` (local time), printed BU image (`imgbu.dat`) |
| Power loss / restart | Application `LOGD`: "Início das operações do logd", "Urna ligada em …"; the vote in progress may lack "computado" (see `tse.urna_logs`) | — |
| Contingency machine | "Modo de carga da UE - Urna de contingência", "Início do procedimento de contingência", "Término do processo de contingência", then the section's own "Município / Zona Eleitoral / Seção Eleitoral" | The original machine's log may be nested in the package (`…-01.jez`, `…ME.jez`); correspondence files |
| Data recovery | "Iniciando aplicação RECUPERADOR DE DADOS" (application `GAP`), then events of application `RED` | The package may carry the log of another section's machine (filtered by `tse.urna_logs.secoes_do_log`) |

**Procedural rules (checked against the Manual do Mesário 2026, TSE)**
- **Confirmed:** up to 4 fingerprint attempts before biographic enabling (Manual pp. 18, 21; logs show "Tentativa [4] de [4]").
- **Confirmed:** biographic enabling requires a photo ID (p. 9), the year of birth and the Presiding officer's fingerprint (p. 21); the voter then signs the list.
- **Confirmed:** voting can only be closed from 17:00 Brasília; numbered tickets go to everyone in line, from last to first (pp. 7, 24).
- **Not confirmed (Ofício text not found):** 2026 2nd round: who could vote between 17:00 and 19:00 in sections still open (any voter arriving, or numbered tickets only), per Ofício-Circular GAB-PRES nº 354/2026 (see §1.2).
- **Confirmed:** 5 mandatory BU copies plus up to 5 extra, for the Board, the door, the Presiding officer, the last two voters, inspectors, prosecutors or press on request (p. 25).
- **Not confirmed:** integrity-test sample and consolidated 2026 results (only regional news, about 20–35 machines per state).

**Where the claim under test sits in this flow.** A poll worker who knows from
the paper list which voters did not show up would have to type their voter id
after 17:00 and enable them biographically (which requires the Presiding
officer's fingerprint and is usually logged as "Mesário N habilitou o eleitor")
or, for voters with no fingerprint on file, by year of birth only (no poll-worker
fingerprint at all). That path leaves:
votes after 17:00 (`votes_after_17`), biographic or no-biometric enabling
(`bio_rate_after`, `semdig_rate_after`), no voting activity just before 17:00 (`gap_before_17`), and
votes closer together than a real voter can manage (`interval_after_17`). Those
are exactly the variables of RQ1–RQ3.

### 1.2 Exception in the 2026 2nd round: voting extended to 19:00

The flow above is the normal day. On the 2nd round of **25 October 2026** the
closing time was changed **during election day** by a court order, so in that
round a vote cast between 17:00 and 19:00 in a section that was still open was
**authorised by the court order then in force** (exact scope pending the Ofício, §1.1)
and does not require a queue at 17:00. Every 17:00 cutoff in this plan
has to be read with that exception for 2026 2t (see §4, §6, §8).

**Who decided and how**

| Item | Fact |
|---|---|
| Decision | Preliminary injunction (*liminar*), single-judge (*monocrática*), extending the closing of vote reception "by two hours, until 19:00, Brasília time" |
| Judge | Minister **Cristiano Zanin**, Supreme Federal Court (**STF**) |
| Case | **Reclamação nº 101.673/BA** |
| Requested by | Coalition "Brasil Pronto Pra Mais" (Lula, PT). The campaign of Flávio Bolsonaro (PL) had also asked the TSE for an extension in municipalities of SP, PR, MG, RS and SC, citing rain and flooding |
| Legal ground | Alleged non-compliance by Salvador, Feira de Santana and Lauro de Freitas (BA) with **ADPF 1.013**, the STF ruling that requires free public transport, at weekday frequency, on election days |
| Scope | The complaint named 3 municipalities in Bahia; the order was extended to the whole country. Zanin later clarified it applied **only where machines had not yet been closed**; votes of machines already closed were totalised as usual. Closed machines were not reopened |
| Execution | The TSE president, Minister Kassio Nunes Marques, complied through Ofício-Circular GAB-PRES nº 354/2026: sections still open stayed open until 19:00. The TSE temporarily blocked the reception of BUs |
| Positions | The Electoral Public Prosecutor (MP Eleitoral) opposed the extension. Nunes Marques said the injunction, issued after closing time, "created difficulties for the electoral process" and that "never in the history of the TSE has there been any extension" |

**Timeline of the day (Brasília time, as reported by the press)**

| Time | Event |
|---|---|
| 13:22 and 15:42 | Lula's coalition files extension requests with the **TSE** |
| 16:22 | The coalition files the Reclamação with the **STF**, asking for nationwide effect |
| 16:33 | Case assigned to Minister Zanin |
| 17:00 | Legal closing time |
| ~17:03 | Zanin's decision is published |
| Later | Zanin clarifies: only machines not yet closed; TSE issues Ofício-Circular 354/2026 |
| 19:00 | New closing time for sections still open |

**Competence: STF × TSE.** Elections are run by the Electoral Justice, headed by
the **Superior Electoral Court (TSE)**. The order came from the **STF**, not from
the TSE. Both readings are recorded here, each with its source; this plan does not
decide between them:
- *Criticism:* the order "ran over the TSE", which was the body that should have
  decided the campaigns' requests (Poder360); the TSE president criticised the
  injunction and the MP Eleitoral opposed it.
- *Counter-argument:* a *reclamação* is the instrument to enforce the STF's own
  rulings, and the request was framed as non-compliance with ADPF 1.013, an STF
  ruling (Migalhas).

**About the judge.** Context record with no effect on the analysis: see Annex A.

**Challenges after the round (reported, not assessed here):** a request to the
Electoral Prosecutor General (PGE) to annul the 2nd round, a request for Zanin's
impeachment, and Flávio Bolsonaro's statement that he does not recognise the result.

**What this changes in the data.** Sections fall into two regimes in 2026 2t:
(a) closed before the decision (~17:03), where the normal 17:00 rule applies;
(b) still open at the decision, where voting could legally continue until 19:00.
The regime is inferred from the log (closing events) and `DT_ENCERRAMENTO`, not
from press reports (variables `extended_regime`, `closed_before_decision`,
`votes_17_19`, `votes_after_19` in §4). The 1st round keeps the 17:00
rule. Because staying open depended on having a queue, the regime is not random: the
2nd round is a separate stratum, and comparisons with the 1st round are exploratory (§6, P7).

**Sources (press, used only as legal context; no analytical input comes from them).**
Poder360, 25/10/2026: https://www.poder360.com.br/poder-eleicoes-2026/zanin-prorroga-votacao-do-2o-turno-ate-19h/ ·
CNN Brasil, 25/10/2026: https://www.cnnbrasil.com.br/eleicoes/zanin-prorroga-eleicao-ate-as-19h-deste-domingo-em-todo-o-pais/ ·
Exame, 25/10/2026: https://exame.com/brasil/por-que-o-tse-decidiu-prorrogar-o-horario-de-votacao-ate-as-19h/ ·
Migalhas: https://www.migalhas.com.br/quentes/467195/zanin-prorroga-votacao-ate-as-19h-apos-reclamacao-sobre-transporte ·
Metrópoles (Nunes Marques agrees to comply with the order): https://www.metropoles.com/brasil/nunes-marques-concorda-com-zanin-sobre-prorrogacao-da-votacao-ate-as-19h ·
CartaCapital: https://www.cartacapital.com.br/politica/em-pronunciamento-nunes-marques-critica-decisao-de-zanin-que-alterou-horario-de-votacao/ ·
Poder360, 01/06/2023: https://www.poder360.com.br/justica/lula-indica-seu-advogado-cristiano-zanin-ao-stf/ ·
Money Times, 21/06/2023: https://www.moneytimes.com.br/senado-aprova-indicacao-de-cristiano-zanin-ex-advogado-de-lula-para-o-stf/

*Pending:* attach the full text of the decision in Rcl 101.673/BA (STF portal) and
Ofício-Circular GAB-PRES nº 354/2026 (TSE). Where they contradict a time above,
the official documents prevail.

---

## 2. Research questions and hypotheses

**Main RQ:** In the Brazilian presidential election, do polling sections show
signs consistent with poll workers voting on behalf of absent voters after
17:00, and are those signs associated with turnout and candidate vote share?

| # | Sub-question | H₀ (null) | Test and primary measure |
|---|---|---|---|
| RQ1 | Is the share of **biographic** enablements (and, separately, of enablements **without biometrics**) higher after the cutoff than before, within the same section? | Within-section odds of biographic (no-biometric) enablement after the cutoff are not higher than before. | One-sided; conditional logit / Mantel–Haenszel stratified by section; odds ratio with 95% CI |
| RQ2 | Do **more sections than expected** vote after the cutoff **without a queue** (no voter identification in the X minutes before)? | The number of such sections is not higher than expected under a Poisson reference calibrated on 16:00–16:50. | One-sided; observed − expected sections, 95% CI |
| RQ3 | Are post-cutoff votes **closer together than physically plausible**? | The share of post-cutoff intervals below T_min is not higher than before the cutoff. | One-sided; within-section permutation; difference in shares, 95% CI |
| RQ4 | Are RQ1–RQ3 signals associated with **higher turnout**? | No association after controls and municipal fixed effects. | One-sided (+); β with 95% CI, errors clustered by municipality |
| RQ5 | Is post-cutoff activity associated with **candidate vote share**? | No association after controls and municipal fixed effects. | Two-sided (no candidate is pre-specified as beneficiary); β with 95% CI |

The **cutoff** is 17:00 in the 1st round; in the 2nd round it is 17:00 for sections closed
before the court order and 19:00 for sections in the extended regime (§1.2, §8). Thresholds,
controls, multiple-testing correction and the decision rule are in §8 and frozen in
`docs/registro_previo.md`.

RQ1–RQ3 test the **mechanism**; RQ4–RQ5 test the **consequence**. A credible
signal needs both. An association in RQ5 alone is not evidence of the practice.

---

## 3. Data sources (verified on dadosabertos.tse.jus.br, Oct 2026)

All datasets can be listed through the portal's CKAN API, so no URL needs to be
hard-coded:

```
https://dadosabertos.tse.jus.br/api/3/action/package_search?q=2022
https://dadosabertos.tse.jus.br/api/3/action/package_show?id=<dataset-id>
```

### 3.1 Datasets

| Dataset id (CKAN) | Content | File pattern (cdn.tse.jus.br/estatistica/sead/…) | Size |
|---|---|---|---|
| `resultados-2022-boletim-de-urna`, `resultados-2026-boletim-de-urna` | Ballot report (BU) as CSV: one row per section × office × candidate | `eleicoes/eleicoes{Y}/buweb/bweb_{1t,2t}_{UF}_{timestamp}.zip` (+ `.sha512`) | Small (AC 1t 2022: 6 MB) |
| `resultados-2022-arquivos-transmitidos-para-totalizacao`, `resultados-2026-arquivos-transmitidos-para-totalizacao` | Raw machine files per section: `.bu`, `.imgbu`, **`.logjez`** (machine log, 7z-compressed), `.rdv`, `.vscmr` | `eleicoes/eleicoes{Y}/arqurnatot/bu_imgbu_logjez_rdv_vscmr_{Y}_{1t,2t}_{UF}.zip` | **Large:** 2022 2nd round AC 367 MB, PI 1.7 GB, SP 20 GB |
| `eleitorado-2022`, `eleitorado-2026` | Voter profile **per section** (age, education, etc.) | `odsele/perfil_eleitor_secao/perfil_eleitor_secao_{Y}_{UF}.zip` | Medium |
| `resultados-2022`, `resultados-2026` | Votes per section (`votacao_secao_{Y}_BR.zip`, 271 MB), turnout detail per section (`detalhe_votacao_secao_{Y}.zip`, 244 MB), **totalization timeline** (`Historico_Totalizacao_Presidente_BR_{1T,2T}_2022.zip`) | `odsele/votacao_secao/…`, `odsele/detalhe_votacao_secao/…`, `eleicoes/eleicoes2022/Historico_Totalizacao_…` | Medium |
| `resultados-2022-correspondencias-esperadas-e-efetivadas-{1,2}-turno`, `resultados-2026-correspondencias-esperadas-e-efetivadas-{1,2}-turno` | Expected vs. actual machine per section (machine replacements, contingency) | `eleicoes/eleicoes{Y}/correspesp/CESP_{t}_{UF}_*.zip` | Small |
| `comparecimento-e-abstencao-2022` | Turnout/abstention by voter profile | `odsele/perfil_comparecimento_abstencao/…` | Medium |
| `denuncias-eleitorais-2022`, `denuncias-eleitorais` (2026) | Complaints filed in the *Pardal* app: municipality, office, irregularity type, PJe case link | `odsele/denuncia/denuncia_{Y}.zip` | 1 MB |
| `mesarios-2022`, `mesarias-mesarios-e-funcoes-especiais-2026` | Poll-worker summons (aggregate use only) | `odsele/convocacao_mesarios/…` | Small |
| `correspondencia-entre-numero-interno-e-modelo-da-urna-1` | Voting-machine model per internal number | `odsele/modelo_urna/modelourna_numerointerno.zip` | Small |
| `resultados-2026-logs-do-sistema-de-preparacao-das-urnas-eletronicas-gedai-{1,2}-turno` | Logs of the machine-preparation system (context only) | — | — |

### 3.2 BU CSV columns (2026 header, verified on `bweb_2t_AC_*.csv`, `;`-separated, Latin-1)

```
DT_GERACAO; HH_GERACAO; ANO_ELEICAO; CD_TIPO_ELEICAO; NM_TIPO_ELEICAO; CD_PLEITO; DT_PLEITO;
NR_TURNO; CD_ELEICAO; DS_ELEICAO; SG_UF; CD_MUNICIPIO; NM_MUNICIPIO; NR_ZONA; NR_SECAO;
NR_LOCAL_VOTACAO; CD_CARGO_PERGUNTA; DS_CARGO_PERGUNTA; NR_PARTIDO; SG_PARTIDO; NM_PARTIDO;
DT_BU_RECEBIDO; QT_APTOS; QT_COMPARECIMENTO; QT_ABSTENCOES; CD_TIPO_URNA; DS_TIPO_URNA;
CD_TIPO_VOTAVEL; DS_TIPO_VOTAVEL; NR_VOTAVEL; NM_VOTAVEL; QT_VOTOS; NR_URNA_EFETIVADA;
CD_CARGA_1_URNA_EFETIVADA; CD_CARGA_2_URNA_EFETIVADA; CD_FLASHCARD_URNA_EFETIVADA;
DT_CARGA_URNA_EFETIVADA; DS_CARGO_PERGUNTA_SECAO; DS_SECOES_AGREGADAS; DT_ABERTURA; DT_ENCERRAMENTO;
QT_ELEI_BIOM_SEM_HABILITACAO; DT_EMISSAO_BU; NR_JUNTA_APURADORA; NR_TURMA_APURADORA
```

Columns that matter most:

| Column | Use |
|---|---|
| `DT_ABERTURA`, `DT_ENCERRAMENTO` | Machine opening/closing time in **local machine time** (convert with `tz_offset`, §4). Closing time is not voting time: use the log for vote times |
| `QT_ELEI_BIOM_SEM_HABILITACAO` | Voters with a fingerprint on file enabled **biographically** (year of birth + Presiding officer's fingerprint); day total. Validated against the log (correlation 0.996 per section). Does **not** include voters without a fingerprint on file |
| `DT_BU_RECEBIDO` | When TSE received the BU, used for transmission delay (P8) |
| `QT_APTOS`, `QT_COMPARECIMENTO`, `QT_ABSTENCOES` | Registered voters, turnout, abstention |
| `DS_TIPO_URNA` | APURADA / replaced machine / etc. |
| `NR_URNA_EFETIVADA` | Machine id, mapped to model via `modelourna_numerointerno` |
| `DS_SECOES_AGREGADAS` | Aggregated sections, which need special handling |
| `NR_VOTAVEL`, `QT_VOTOS` (with `DS_CARGO_PERGUNTA = Presidente`) | Candidate votes per section |

### 3.3 Two analysis tiers

| Tier | Data | What it answers | Cost |
|---|---|---|---|
| **Light** | BU CSV + voter profile, all of Brazil | Which sections closed after 17:00; overall no-biometric rate; turnout; candidate share; receipt delay (RQ4, RQ5, P8, partially RQ1) | Hundreds of MB, minutes |
| **Full** | Machine logs (`.logjez`), all of Brazil | Votes before/after 17:00, no-biometric **before vs. after** 17:00, queue gap, inter-vote intervals (RQ1–RQ3) | **Hundreds of GB** across 3 rounds, hours |

Do the light tier first: it is cheap and already answers part of the question.

### 3.4 Log format (resolved with the 2026 logs)

The event dictionary was built empirically from the 2026 logs (table in §1.1, `src/tse/urna_logs.py`).
There is no official TSE documentation of the messages, so the dictionary is versioned with the code
and every frozen run records the commit that produced it.

---

## 4. Variables (section × round)

| Variable | Definition | Source | Tier |
|---|---|---|---|
| `uf`, `cd_municipio`, `nr_zona`, `nr_secao`, `nr_local_votacao` | Keys | BU | Light |
| `registered` | `QT_APTOS` | BU | Light |
| `turnout` | `QT_COMPARECIMENTO / QT_APTOS` | BU | Light |
| `tz_offset` | Section time zone: hour of "Urna pronta para receber votos" − 8 (= 8:00 Brasília), accepted only within the first 15 min of the hour and in {−2, −1, 0, +1}; otherwise null and counted (`secoes_sem_fuso`) | Log | Full |
| `close_time` | `DT_ENCERRAMENTO` converted from local machine time to Brasília time with `tz_offset` | BU + log | Light |
| `closed_after_17` | `close_time > 17:00:00` (Brasília time). Measures closing only; **never read as voting after 17:00** | Derived | Light |
| `minutes_after_17` | Minutes between 17:00 and `close_time` | Derived | Light |
| `nh_rate_bio` | `QT_ELEI_BIOM_SEM_HABILITACAO / QT_COMPARECIMENTO` (biographic enablement, §1.1) | BU | Light |
| `cand_share_{x}` | Presidential vote share of each candidate (valid votes) | BU | Light |
| `receipt_delay` | `DT_BU_RECEBIDO − DT_ENCERRAMENTO` | BU | Light |
| `machine_model` | From `NR_URNA_EFETIVADA` | BU + model table | Light |
| `replaced_machine` | `DS_TIPO_URNA` ≠ APURADA, or the correspondence file shows a change | BU / CESP | Light |
| Age, education, biometric-registration share | Section voter profile | Profile | Light |
| `votes_before_17`, `votes_after_17` | Votes computed before/after 17:00:00 | Log | Full |
| `share_after_17` | `votes_after_17 / votes_total` | Derived | Full |
| `bio_rate_before`, `bio_rate_after` | Biographic enablement rate before/after the cutoff (marker "Solicitação de dado pessoal…") | Log | Full |
| `semdig_rate_before`, `semdig_rate_after` | Rate of enablement without biometrics before/after the cutoff ("Ano de nascimento digitado…" without that request) | Log | Full |
| `manual_sem_mesario_id` | Biographic enablements with no "Mesário N habilitou o eleitor" line | Log | Full |
| `gap_before_17` | Minutes between the last vote before 17:00 and 17:00 | Log | Full |
| `interval_after_17` (median, p10) | Seconds between consecutive votes after 17:00 | Log | Full |
| `burst_count` | Runs of ≥ N consecutive non-biometric (biographic or without biometrics) votes with interval < S seconds | Log | Full |
| `last_vote_time` | Time of the last vote computed | Log | Full |
| `closed_before_decision` | 2026 2t only: section closed before the court order (~17:03 Brasília; exact time to be fixed from the official decision) | Log + BU | Full |
| `extended_regime` | 2026 2t only: section still open at the court order, so voting could legally continue until 19:00 (§1.2) | Log + BU | Full |
| `votes_17_19`, `votes_after_19` | 2026 2t only: votes computed between 17:00 and 19:00, and after 19:00 | Log | Full |
| `gap_before_19` | 2026 2t, `extended_regime` only: minutes between the last vote before 19:00 and 19:00 | Log | Full |
| `n_votos_interrompidos`, `n_votos_descartados`, `n_logs_outra_secao` | Counting-method flags: interrupted vote recorded / lost, log of another section in the package (`src/tse/urna_logs.py`) | Log | Full |

---

## 5. What has to be done (step by step)

### 5.1 Light tier: BU for all of Brazil
- [ ] List resources via the CKAN API for `resultados-2026-boletim-de-urna` (28 files per round: 27 UFs + ZZ) and `eleitorado-2026` (section profile).
- [ ] Download and verify against `.sha512` where published.
- [ ] Filter `DS_CARGO_PERGUNTA = Presidente`; collapse to **one row per section** with the variables in §4.
- [ ] Handle aggregated sections (`DS_SECOES_AGREGADAS`) and replaced machines (`DS_TIPO_URNA`, CESP files).
- [ ] **Check:** national totals for each 2026 round must match the official TSE result (2nd round: Lula 64,256,232; Flávio Bolsonaro 59,826,041; also validated against the signed Results API). Section counts per UF must match `detalhe_votacao_secao`.

### 5.2 Log pilot (one small state)
- [x] Pilot done on 2026 AC (probe of 2026-10-12, documented in `src/tse/urna_logs.py`).
- [ ] Open a few `.logjez` files (7z) and read the raw `logd.dat`.
- [ ] Build the **event dictionary** (§3.4): message string → category.
- [ ] Extract the per-section log features from §4.
- [ ] **Reconcile:** votes computed in the log must equal `QT_COMPARECIMENTO` in the BU. Target ≥ 99% match; list unmatched sections instead of dropping them. The confirmatory analysis is run with and without them.
- [ ] Review the dictionary and the match rate **before** scaling up.

### 5.3 Logs for all of Brazil
- [ ] Process **one state at a time** (download zip → read only `.logjez` → write per-section features → delete zip), so disk use stays near the size of the largest zip (SP ≈ 20 GB).
- [ ] Order: smallest states first, SP last; keep a progress/state file so the run can resume.
- [ ] Run for 2026 1t and 2026 2t (`tse.reprocessar_logs`; status in `docs/reprocessamento_logs.md`). The ZIPs can be deleted after processing because the manifests keep URL and sha512 for re-download and re-verification.

### 5.4 Build the panel
- [ ] Join BU + log features + voter profile on (`uf`, `cd_municipio`, `nr_zona`, `nr_secao`, round).
- [ ] Link 2026 1t ↔ 2t on the section keys and report the sections that do not match.

---

## 6. Analysis points

### P0 — Data quality
- [ ] Log vs. BU reconciliation table (per UF and round).
- [ ] Flag and report: replaced machines, contingency votes, aggregated sections, transit voting, clock anomalies (events before opening or after closing).
- [ ] 2026 2t: flag any vote after 19:00, and any vote after 17:00 in a section with `closed_before_decision` (a closed machine could not be reopened).

### P1 — Descriptive picture (light tier)
- [ ] Distribution of `close_time` by UF/region; % of sections closing after 17:00, and how late.
- [ ] 2026 2t: split sections into `closed_before_decision` vs. `extended_regime`; distribution of `close_time` between 17:00 and 19:00 by UF/region.
- [ ] `nh_rate_bio` by UF, region, age profile and machine model (the legitimate baseline).
- [ ] Turnout and candidate share by region.

### P2 — Mechanism: no-biometric enablement (RQ1, full tier)
- [ ] Within-section comparison of biographic and no-biometric enablement before vs. after the cutoff, on vote counts: conditional logit / Mantel–Haenszel stratified by section (not Wilcoxon on rates, which fails with 1–2 post-cutoff votes). Odds ratio with 95% CI. Benchmark: the same contrast between 16:00–16:30 and 16:30–17:00.
- [ ] Repeat by region; test whether the Northeast differs **after controlling for** age, education and biometric registration.

### P3 — Mechanism: voting without a queue (RQ2, full tier)
Legitimate post-17:00 voting requires people already in line at 17:00, so there
should be continuous activity right before closing.
- [ ] Count sections with `votes_after_17 > 0` **and** `gap_before_17` > X minutes, and compare with the expected count under a Poisson reference, Σ exp(−λᵢX), with λᵢ estimated from voter identifications between 16:00 and 16:50.
- [ ] Describe those sections: number of post-17:00 votes, how they were enabled, intervals.
- [ ] 2026 2t: in `extended_regime` sections, votes between 17:00 and 19:00 do not need a queue at 17:00; apply the queue test at 19:00 (`votes_after_19 > 0` and `gap_before_19` > X). Sections with `closed_before_decision` keep the 17:00 test.

### P4 — Mechanism: bursts (RQ3, full tier)
- [ ] Compare the share of post-cutoff intervals below T_min with the pre-cutoff share, by within-section permutation. This is the single pre-specified test (intervals are integer seconds with ties, so no KS).
- [ ] Physical minimum time per vote: T_min = 0.5th percentile of pre-17:00 intervals, per round and ballot stratum (number of offices); flag intervals below it.
- [ ] Count runs of consecutive no-biometric votes (`burst_count`).

### P5 — Consequence: turnout (RQ4)
- [ ] **Election fingerprint** (Klimek et al., 2012): 2D histogram of turnout × candidate share per section, by region and round. Ballot stuffing **can** show up as a cluster near 100% turnout with high share for one candidate. The method is not calibrated for compulsory voting and small sections, so it is descriptive only.
- [ ] Regression `turnout ~ signal + controls + municipality FE`, with errors clustered by municipality. `signal` is the RQ1–RQ3 indicators, not the count of late votes (legitimate late voting raises turnout mechanically).

### P6 — Consequence: vote share (RQ5)
- [ ] Light tier: `cand_share ~ closed_after_17 + minutes_after_17 + nh_rate_bio + controls + municipality FE`.
- [ ] Full tier: `cand_share ~ share_after_17 + bio_rate_after + controls + municipality FE`.
- [ ] *(Exploratory)* **Within-section change between rounds (2026):** Δ`share_after_17` vs. Δ in the share of the two 2nd-round candidates. Ballots differ between rounds, so this is not confirmatory.

### P7 — Robustness and placebos
- [ ] **Placebo cutoffs:** repeat P2–P6 with 16:00 and 16:30 as the "closing" time (windows of the same length as the real one) and, in 2nd-round `extended_regime` sections, with 18:00 and 18:30. If the effect also appears there, it is not about closing.
- [ ] **2026 2nd round as a separate stratum**, same code and rules. Confirmatory only for the P0 integrity checks, RQ2 at 19:00 and the 18:00/18:30 placebos; RQ1/RQ3 in the 17:00–19:00 window are exploratory (late arrivals may differ).
- [ ] *(Exploratory)* Compare post-17:00 patterns in 2nd-round `extended_regime` sections (17:00–19:00 voting authorised) with the 1st round (post-17:00 voting required a queue), stratified by ballot.
- [ ] Threshold sensitivity (X minutes, N votes, S seconds), with values fixed **before** looking at results.
- [ ] Optional future replication on 2022 or 2018 (in 2018 closing was 17:00 *local* time, so the cutoff differs per state).

### P8 — Transmission delay (separate claim: "some states take too long to send results")
- [ ] `receipt_delay` by UF and municipality (light tier).
- [ ] Is the delay explained by remoteness (rural, Amazon region, satellite transmission) or associated with P2–P4 signals?
- [ ] Use the 2026 totalization timeline, if TSE publishes it, to show how the national count evolved over the night.

### P9 — Formal complaints (context)
- [ ] From the Pardal complaints (`denuncia_2022`, `denuncia_2026`): count complaints by irregularity type and municipality, and check whether this practice was formally reported, and where.
- [ ] Compare complaint municipalities with flagged vs. non-flagged sections (aggregate only).

---

## 7. Alternative explanations to rule out

| Observed pattern | Innocent explanation | How to control |
|---|---|---|
| Many votes after 17:00 | Queue at closing time | `gap_before_17` (P3) |
| Votes between 17:00 and 19:00 in 2026 2t | Court-ordered extension (Rcl 101.673/BA, §1.2) | `extended_regime`, `votes_17_19` |
| Higher non-biometric rate late in the day | Late voters differ (elderly, manual workers) | 16:00–16:30 vs 16:30–17:00 benchmark; voter profile |
| Biographic enabling with no identified poll worker | Presiding officer not registered on the machine | `manual_sem_mesario_id`, descriptive |
| Sections open until 19:00 with no votes | The court order kept machines open | Vote times from the log, not closing time |
| More no-biometric enablement | Worn fingerprints (manual workers), elderly voters, faulty readers | Age/education profile, machine model, biometric-registration share |
| Regional pattern correlated with a candidate | Northeast has a different political preference **and** different demographics | Municipal fixed effects, within-section changes |
| Very early "closing" in the West | Unified Brasília time (closes 15:00 local time in Acre) | Use Brasília time consistently |
| Late results | Logistics (remote areas, satellite) | P8 |
| Odd log timestamps | Machine clock errors, replaced machines | P0 flags |

---

## 8. Interpretation and decision rule (frozen in `docs/registro_previo.md`)

**Cutoff.** 17:00 in the 2026 1st round and, in the 2nd round, for `closed_before_decision`
sections; 19:00 for 2nd-round `extended_regime` sections (§1.2).

**Section level.** A section counts as **anomalous** only if it meets all three conditions:
1. post-cutoff votes with no voter identification in the X minutes before the cutoff;
2. at least 3 post-cutoff votes and a non-biometric share (biographic or without biometrics)
   significantly above the section's own pre-cutoff rate (one-sided binomial test).
   Sections with 1–2 post-cutoff votes are "indeterminate", not anomalous;
3. post-cutoff intervals below T_min, or a run of ≥ N non-biometric votes with intervals < S.

**Thresholds** are set by rules computed only on pre-17:00 data, which are not outcomes:

| Threshold | Rule | Sensitivity |
|---|---|---|
| T_min | 0.5th percentile of pre-17:00 inter-vote intervals, per round and ballot stratum (number of offices) | — |
| S | 5th percentile of the same intervals | — |
| N | 3 | 5 |
| X | max(10 min, 99.9th percentile of intervals between 8:00 and 10:00) | 5, 15, 20, 30 min |

The false-positive rate is estimated by applying the same rule to the 16:00–16:30 window.

**Study level.**
- **Supports the claim (indication, not proof):** RQ1 and (RQ2 or RQ3) significant after
  Holm and above the smallest effect size of interest (SESOI); placebos below half of the
  effect; more anomalous sections than the calibrated reference; RQ4/RQ5 in the same
  direction.
- **Refutes it at scale:** equivalence tests (TOST) below the SESOI for RQ1–RQ3, or the
  upper 95% bound of affected votes below the national margin.
- **Inconclusive:** everything else, including CIs that cover both 0 and the SESOI, and
  positive placebos.

**Multiple testing.** Primary family RQ1–RQ5 × 2 rounds with Holm (α = 0.05). Everything
else (placebos, regions, sensitivity) with BH-FDR (q = 0.05), labelled exploratory. No
p-values per section.

**Report:** number and % of anomalous sections against the calibrated reference, their
geographic distribution (aggregates only), and the **ceiling** of votes that could be
affected (all post-cutoff votes in anomalous sections, not attributed to any candidate),
with its confidence interval, compared with the national margin.

A null result only means there is no trace of the practice **in the form described, after
the cutoff**. It does not rule out other forms (for example, votes cast at idle moments
before 17:00).

---

## 9. Limitations and ethics

- Ecological inference: section-level associations do not reveal individual votes.
- An anomaly is an **indication**, not proof; only an audit or investigation can confirm it.
- Log clock and event-format issues may create false signals (P0).
- Do not name poll workers or accuse specific sections publicly; report aggregates.
- Data is public; use nothing beyond what TSE publishes.
- Threat model of the whole electoral chain (where fraud could happen, existing controls, residual risk, what TSE data can detect, and international cases): [docs/modelo_de_ameacas.md](docs/modelo_de_ameacas.md) (Portuguese).
- **Language rule.** Permitted terms: "statistical anomaly", "indication", "signal
  consistent with", "deviation from the baseline", "not explained by the controls". Not used
  in conclusions: "fraud", "fraudulent", "irregularity" (a legal qualification, only when
  quoting a decision), "forensic report" or *perícia*/*laudo*, "proves", "manipulation".
  "Test" is used; "prove" is not.
- Only aggregates are published (UF, region, size band); groups with fewer than 10 sections
  are suppressed. A strong indication is not published with the section identified: it is
  documented with hash and code, sent to independent review and referred confidentially to
  the Electoral Prosecutor (MP Eleitoral) or the TRE's internal affairs office.
- Political and legal context stays in §1.2 and Annex A and does not enter any analysis,
  figure or conclusion.
- Null results are published with the same prominence as positive ones.

---

## 10. Prior work to read

- Klimek, P., Yegorov, Y., Hanel, R., & Thurner, S. (2012). Statistical detection of systematic election irregularities. *PNAS, 109*(41), 16469–16473.
- Mebane, W. R. — *Election Forensics* (turnout- and digit-based tests, and their limits).
- Partido Liberal / Instituto Voto Legal (2022). *Relatório Técnico — Logs Inválidos das Urnas Eletrônicas* (v0.7, 15/11/2022), plus the TSE response.
- Independent analysis by USP/UFSCar/UFPA and other researchers of the log issue (Poder360, Dec 2022): https://static.poder360.com.br/2022/12/Analise-Bug04030201_USPUFSCarUFPAoutros.pdf
- Virgolino, V. A. C. (2023). *UrnaLogs* — undergraduate thesis, UFCG (collection and organization of the 2022 logs by section): https://bdtd.ufcg.edu.br/jspui/bitstream/riufcg/30487/1/VICTOR%20ARRUDA%20C%c3%82MARA%20VIRGOLINO%20-%20TCC%20ARTIGO%20CI%c3%8aNCIA%20DA%20COMPUTA%c3%87%c3%83O%20CEEI%202023.pdf
- Fact-checks on "votes after 17:00" and on the logs (Comprova/Metrópoles, O Popular, 2022). List every argument they raise and make sure the analysis addresses it.
- TSE IT glossary (biometric verification vs. identification): https://www.tse.jus.br/institucional/catalogo-de-publicacoes/arquivos/glossario-ti
- STF, Reclamação nº 101.673/BA (Min. Cristiano Zanin, 25/10/2026), STF ADPF 1.013 (free transport on election day) and TSE Ofício-Circular GAB-PRES nº 354/2026: official texts to attach. Press coverage used for §1.2 is listed there.

---

## 11. Expected deliverables

1. Section-level panel (2026 1st and 2nd round, all UFs + ZZ) with the §4 variables and the hashes of its inputs.
2. Versioned log event dictionary and reconciliation report (P0).
3. Pre-registration (`docs/registro_previo.md`), frozen with a git tag before any confirmatory run.
4. Descriptive report and figures (P1).
5. Confirmatory tests RQ1–RQ5 with effect sizes, CIs, Holm correction and placebos; 2nd round as a separate stratum.
6. Anomaly table (aggregate), with the ceiling of affected votes and its CI compared to the margin.
7. Reproduction package (`docs/reproducao.md`): commands, environment, manifests, and a table "number in the report → code/query".
8. Written conclusion under the §8 decision rule and the §9 language rule, with its limitations.

---

## 12. Rigor and reproducibility

- **Review of this plan** by the team roles, against the errors of the third-party report:
  [docs/revisao_research_plan.md](docs/revisao_research_plan.md).
- **Pre-registration:** [docs/registro_previo.md](docs/registro_previo.md). Frozen with a git
  tag before any confirmatory run. Any later change is logged as a deviation; analyses not in
  it are exploratory. It also declares what had already been seen of the 2026 data.
- **Reproduction:** [docs/reproducao.md](docs/reproducao.md).
- **Stage gates.** No stage starts before the previous one passes its check, and each check
  is recorded:
  1. data mirrored and verified against the official `.sha512`;
  2. logs reprocessed; log × BU reconciliation ≥ 99%, with unmatched sections listed;
  3. tests pass and the code that produced the data is committed;
  4. pre-registration frozen (tag);
  5. confirmatory run, once, from the tagged commit;
  6. independent review: agent `revisor-independente` and, before publication, external
     human reviewers (statistician and security specialist).
- **Every number in the final report is produced by versioned code** and stored with the
  hashes of its inputs. None is typed by hand.

---

## Annex A. Context about the judge (no effect on the analysis)

Cristiano Zanin was Luiz Inácio Lula da Silva's personal defence lawyer in the Lava Jato
criminal cases from 2013, and obtained the annulment of Lula's convictions. Lula nominated
him to the STF on 01/06/2023 (seat of Ricardo Lewandowski); the Senate approved him on
21/06/2023 by 58 votes to 18. The decision of 25/10/2026 granted a request from the
coalition of Lula, then a candidate for re-election. At his Senate hearing Zanin said he
would not judge cases in which he had acted as a lawyer.

Impediment and suspicion of a judge are decided by the STF itself (CPC, arts. 144–145;
STF internal rules). This project does not assess that question, and no variable depends
on it. Sources: listed in §1.2.
