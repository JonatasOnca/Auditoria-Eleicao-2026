# Research Plan — Post-17:00 Voting and Ballot-Stuffing Signals in Brazilian Elections

> Self-contained hand-off document: the claim, the questions, the verified data
> sources, the variables, every analysis step, and the checks. Nothing has been
> implemented yet.

**Scope decisions**
- **Geography:** all 27 states (Brasil inteiro).
- **Elections:** 2022 President, 1st and 2nd round (main dataset), and 2026 1st round (replication; already published). Add the 2026 2nd round (Oct 25, 2026) when TSE publishes it.
- **Unit of analysis:** polling section × round.

---

## 1. Claim under test

A report from voters in Brazil's Northeast alleges a common practice: after the
polls close at 17:00, poll workers (*mesários*) already know which registered
voters did not show up and cast ballots in their names.

The goal is to **test** the claim with public data, not to prove it. If the
practice exists at scale, it should leave measurable traces in the voting-machine
logs and section results. If those traces are absent, that is also a valid
finding.

**Key constraint (vote secrecy):** no public file links an individual vote's
timestamp to the candidate chosen. The machine log has timestamps but no
candidate; the RDV has candidates but is shuffled. All candidate-level analysis
is therefore **ecological** (section level), never vote level.

---

## 2. Research questions and hypotheses

**Main RQ:** In the Brazilian presidential election, do polling sections show
signs consistent with poll workers voting on behalf of absent voters after
17:00, and are those signs associated with turnout and candidate vote share?

| # | Sub-question | H₀ (null) |
|---|---|---|
| RQ1 | Is the share of voters enabled **without biometrics** higher after 17:00 than before, within the same section? | The no-biometric rate after 17:00 is not higher than before 17:00. |
| RQ2 | Do sections show post-17:00 voting **without a queue** at 17:00 (no activity in the last minutes before closing)? | Post-17:00 votes occur only in sections with continuous activity up to 17:00. |
| RQ3 | Do post-17:00 votes come in **bursts** (short, regular intervals between votes)? | Inter-vote intervals after 17:00 follow the same distribution as before 17:00 in the same section. |
| RQ4 | Are sections with high RQ1–RQ3 signals associated with **abnormally high turnout**? | Signal intensity is not associated with turnout, after municipal fixed effects. |
| RQ5 | Is post-17:00 activity associated with **candidate vote share**? | Post-17:00 share is not associated with candidate share, after municipal fixed effects. |

RQ1–RQ3 test the **mechanism**; RQ4–RQ5 test the **consequence**. A credible
signal needs both. An association in RQ5 alone is not evidence of fraud.

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
| `resultados-2022-correspondencias-esperadas-e-efetivadas-{1,2}-turno`, `resultados-2026-correspondencias-esperadas-e-efetivadas-1-turno` | Expected vs. actual machine per section (machine replacements, contingency) | `eleicoes/eleicoes{Y}/correspesp/CESP_{t}_{UF}_*.zip` | Small |
| `comparecimento-e-abstencao-2022` | Turnout/abstention by voter profile | `odsele/perfil_comparecimento_abstencao/…` | Medium |
| `denuncias-eleitorais-2022`, `denuncias-eleitorais` (2026) | Complaints filed in the *Pardal* app: municipality, office, irregularity type, PJe case link | `odsele/denuncia/denuncia_{Y}.zip` | 1 MB |
| `mesarios-2022`, `mesarias-mesarios-e-funcoes-especiais-2026` | Poll-worker summons (aggregate use only) | `odsele/convocacao_mesarios/…` | Small |
| `correspondencia-entre-numero-interno-e-modelo-da-urna-1` | Voting-machine model per internal number | `odsele/modelo_urna/modelourna_numerointerno.zip` | Small |
| `resultados-2026-logs-do-sistema-de-preparacao-das-urnas-eletronicas-gedai-1-turno` | Logs of the machine-preparation system (context only) | — | — |

### 3.2 BU CSV columns (verified header, `bweb_1t_AC_*.csv`, `;`-separated, Latin-1)

```
DT_GERACAO; HH_GERACAO; ANO_ELEICAO; CD_TIPO_ELEICAO; NM_TIPO_ELEICAO; CD_PLEITO; DT_PLEITO;
NR_TURNO; CD_ELEICAO; DS_ELEICAO; SG_UF; CD_MUNICIPIO; NM_MUNICIPIO; NR_ZONA; NR_SECAO;
NR_LOCAL_VOTACAO; CD_CARGO_PERGUNTA; DS_CARGO_PERGUNTA; NR_PARTIDO; SG_PARTIDO; NM_PARTIDO;
DT_BU_RECEBIDO; QT_APTOS; QT_COMPARECIMENTO; QT_ABSTENCOES; CD_TIPO_URNA; DS_TIPO_URNA;
CD_TIPO_VOTAVEL; DS_TIPO_VOTAVEL; NR_VOTAVEL; NM_VOTAVEL; QT_VOTOS; NR_URNA_EFETIVADA;
CD_CARGA_1_URNA_EFETIVADA; CD_CARGA_2_URNA_EFETIVADA; CD_FLASHCARD_URNA_EFETIVADA;
DT_CARGA_URNA_EFETIVADA; DS_CARGO_PERGUNTA_SECAO; DS_AGREGADAS; DT_ABERTURA; DT_ENCERRAMENTO;
QT_ELEITORES_BIOMETRIA_NH; DT_EMISSAO_BU; NR_JUNTA_APURADORA; NR_TURMA_APURADORA
```

Columns that matter most:

| Column | Use |
|---|---|
| `DT_ABERTURA`, `DT_ENCERRAMENTO` | Machine opening/closing time; closing after 17:00 means voting continued after 17:00 |
| `QT_ELEITORES_BIOMETRIA_NH` | Voters **not enabled by biometrics** in the section (total for the day, not split by time) |
| `DT_BU_RECEBIDO` | When TSE received the BU, used for transmission delay (P8) |
| `QT_APTOS`, `QT_COMPARECIMENTO`, `QT_ABSTENCOES` | Registered voters, turnout, abstention |
| `DS_TIPO_URNA` | APURADA / replaced machine / etc. |
| `NR_URNA_EFETIVADA` | Machine id, mapped to model via `modelourna_numerointerno` |
| `DS_AGREGADAS` | Aggregated sections, which need special handling |
| `NR_VOTAVEL`, `QT_VOTOS` (with `DS_CARGO_PERGUNTA = Presidente`) | Candidate votes per section |

### 3.3 Two analysis tiers

| Tier | Data | What it answers | Cost |
|---|---|---|---|
| **Light** | BU CSV + voter profile, all of Brazil | Which sections closed after 17:00; overall no-biometric rate; turnout; candidate share; receipt delay (RQ4, RQ5, P8, partially RQ1) | Hundreds of MB, minutes |
| **Full** | Machine logs (`.logjez`), all of Brazil | Votes before/after 17:00, no-biometric **before vs. after** 17:00, queue gap, inter-vote intervals (RQ1–RQ3) | **Hundreds of GB** across 3 rounds, hours |

Do the light tier first: it is cheap and already answers part of the question.

### 3.4 Still unknown (resolve in the pilot, step 5.2)

- Exact log line format inside `.logjez` (expected: 7z archive containing `logd.dat`, one event per line with timestamp, level, machine id, application, message, hash).
- Exact log **message strings** for:
  - voter enabled by biometrics;
  - biometric failure, then enabled by the poll worker (typed voter ID / document);
  - vote computed;
  - machine closing.
- No official TSE documentation for the log messages was found. Build the event dictionary empirically from a small state, and cross-check against the 2022 analyses listed in §10.

---

## 4. Variables (section × round)

| Variable | Definition | Source | Tier |
|---|---|---|---|
| `uf`, `cd_municipio`, `nr_zona`, `nr_secao`, `nr_local_votacao` | Keys | BU | Light |
| `registered` | `QT_APTOS` | BU | Light |
| `turnout` | `QT_COMPARECIMENTO / QT_APTOS` | BU | Light |
| `close_time` | `DT_ENCERRAMENTO` | BU | Light |
| `closed_after_17` | `close_time > 17:00:00` (Brasília time) | Derived | Light |
| `minutes_after_17` | Minutes between 17:00 and `close_time` | Derived | Light |
| `nh_rate` | `QT_ELEITORES_BIOMETRIA_NH / QT_COMPARECIMENTO` | BU | Light |
| `cand_share_{x}` | Presidential vote share of each candidate (valid votes) | BU | Light |
| `receipt_delay` | `DT_BU_RECEBIDO − DT_ENCERRAMENTO` | BU | Light |
| `machine_model` | From `NR_URNA_EFETIVADA` | BU + model table | Light |
| `replaced_machine` | `DS_TIPO_URNA` ≠ APURADA, or the correspondence file shows a change | BU / CESP | Light |
| Age, education, biometric-registration share | Section voter profile | Profile | Light |
| `votes_before_17`, `votes_after_17` | Votes computed before/after 17:00:00 | Log | Full |
| `share_after_17` | `votes_after_17 / votes_total` | Derived | Full |
| `nh_rate_before`, `nh_rate_after` | No-biometric enablement rate before/after 17:00 | Log | Full |
| `gap_before_17` | Minutes between the last vote before 17:00 and 17:00 | Log | Full |
| `interval_after_17` (median, p10) | Seconds between consecutive votes after 17:00 | Log | Full |
| `burst_count` | Runs of ≥ N consecutive no-biometric votes with interval < S seconds | Log | Full |
| `last_vote_time` | Time of the last vote computed | Log | Full |

---

## 5. What has to be done (step by step)

### 5.1 Light tier: BU for all of Brazil
- [ ] List resources via the CKAN API for `resultados-{2022,2026}-boletim-de-urna` (27 UFs × 3 rounds = 81 files) and `eleitorado-{2022,2026}` (section profile).
- [ ] Download and verify against `.sha512` where published.
- [ ] Filter `DS_CARGO_PERGUNTA = Presidente`; collapse to **one row per section** with the variables in §4.
- [ ] Handle aggregated sections (`DS_AGREGADAS`) and replaced machines (`DS_TIPO_URNA`, CESP files).
- [ ] **Check:** national totals for the 2022 2nd round must match the official result (Lula 60,345,999; Bolsonaro 58,206,354). Section counts per UF must match `detalhe_votacao_secao`.

### 5.2 Log pilot (one small state)
- [ ] Download `bu_imgbu_logjez_rdv_vscmr_2022_2t_AC.zip` (367 MB).
- [ ] Open a few `.logjez` files (7z) and read the raw `logd.dat`.
- [ ] Build the **event dictionary** (§3.4): message string → category.
- [ ] Extract the per-section log features from §4.
- [ ] **Reconcile:** votes computed in the log must equal `QT_COMPARECIMENTO` in the BU. Target ≥ 99% match; list unmatched sections instead of dropping them.
- [ ] Review the dictionary and the match rate **before** scaling up.

### 5.3 Logs for all of Brazil
- [ ] Process **one state at a time** (download zip → read only `.logjez` → write per-section features → delete zip), so disk use stays near the size of the largest zip (SP ≈ 20 GB).
- [ ] Order: smallest states first, SP last; keep a progress/state file so the run can resume.
- [ ] Repeat for 2022 1t, 2022 2t and 2026 1t.

### 5.4 Build the panel
- [ ] Join BU + log features + voter profile on (`uf`, `cd_municipio`, `nr_zona`, `nr_secao`, round).
- [ ] Link 2022 1t ↔ 2t (same sections) and 2022 ↔ 2026, where section keys are stable.

---

## 6. Analysis points

### P0 — Data quality
- [ ] Log vs. BU reconciliation table (per UF and round).
- [ ] Flag and report: replaced machines, contingency votes, aggregated sections, transit voting, clock anomalies (events before opening or after closing).

### P1 — Descriptive picture (light tier)
- [ ] Distribution of `close_time` by UF/region; % of sections closing after 17:00, and how late.
- [ ] `nh_rate` by UF, region, age profile and machine model (the legitimate baseline).
- [ ] Turnout and candidate share by region.

### P2 — Mechanism: no-biometric enablement (RQ1, full tier)
- [ ] Paired comparison `nh_rate_after` vs `nh_rate_before` within each section (Wilcoxon signed-rank; effect size *r*).
- [ ] Repeat by region; test whether the Northeast differs **after controlling for** age, education and biometric registration.

### P3 — Mechanism: voting without a queue (RQ2, full tier)
Legitimate post-17:00 voting requires people already in line at 17:00, so there
should be continuous activity right before closing.
- [ ] Count sections with `votes_after_17 > 0` **and** `gap_before_17` > X minutes.
- [ ] Describe those sections: number of post-17:00 votes, how they were enabled, intervals.

### P4 — Mechanism: bursts (RQ3, full tier)
- [ ] Compare the interval distribution before vs. after 17:00 within each section (Kolmogorov–Smirnov or Mann–Whitney).
- [ ] Estimate the physical minimum time per vote (enable + all offices + confirm) from pre-17:00 data; flag intervals below it.
- [ ] Count runs of consecutive no-biometric votes (`burst_count`).

### P5 — Consequence: turnout (RQ4)
- [ ] **Election fingerprint** (Klimek et al., 2012): 2D histogram of turnout × candidate share per section, by region and round. Ballot stuffing shows up as a cluster near 100% turnout with high share for one candidate.
- [ ] Regression `turnout ~ signal + controls + municipality FE`, with errors clustered by municipality.

### P6 — Consequence: vote share (RQ5)
- [ ] Light tier: `cand_share ~ closed_after_17 + minutes_after_17 + nh_rate + controls + municipality FE`.
- [ ] Full tier: `cand_share ~ share_after_17 + nh_rate_after + controls + municipality FE`.
- [ ] **Within-section change between rounds (2022):** Δ`share_after_17` vs Δ`cand_share`; each section serves as its own control.

### P7 — Robustness and placebos
- [ ] **Placebo cutoffs:** repeat P2–P6 with 16:00 and 16:30 as the "closing" time. If the effect also appears there, it is not about closing.
- [ ] **2026 1st-round replication** with the same code and thresholds.
- [ ] Threshold sensitivity (X minutes, N votes, S seconds), with values fixed **before** looking at results.
- [ ] Optional 2018 baseline (closing was 17:00 *local* time, so the cutoff differs per state).

### P8 — Transmission delay (separate claim: "some states take too long to send results")
- [ ] `receipt_delay` by UF and municipality (light tier).
- [ ] Is the delay explained by remoteness (rural, Amazon region, satellite transmission) or associated with P2–P4 signals?
- [ ] Use `Historico_Totalizacao_Presidente_BR_{1T,2T}_2022` to show how the national count evolved over the night.

### P9 — Formal complaints (context)
- [ ] From the Pardal complaints (`denuncia_2022`, `denuncia_2026`): count complaints by irregularity type and municipality, and check whether this practice was formally reported, and where.
- [ ] Compare complaint municipalities with flagged vs. non-flagged sections (aggregate only).

---

## 7. Alternative explanations to rule out

| Observed pattern | Innocent explanation | How to control |
|---|---|---|
| Many votes after 17:00 | Queue at closing time | `gap_before_17` (P3) |
| More no-biometric enablement | Worn fingerprints (manual workers), elderly voters, faulty readers | Age/education profile, machine model, biometric-registration share |
| Regional pattern correlated with a candidate | Northeast has a different political preference **and** different demographics | Municipal fixed effects, within-section changes |
| Very early "closing" in the West | Unified Brasília time (closes 15:00 local time in Acre) | Use Brasília time consistently |
| Late results | Logistics (remote areas, satellite) | P8 |
| Odd log timestamps | Machine clock errors, replaced machines | P0 flags |

---

## 8. Interpretation rule (fix before running)

A section counts as an **anomaly** only if it meets all three conditions:
1. post-17:00 votes with no activity in the X minutes before 17:00;
2. post-17:00 votes mostly enabled without biometrics;
3. intervals below the physical minimum, or in bursts.

Report: number and % of anomalous sections, their geographic distribution, their
turnout and vote share compared with other sections in the same municipality, and
**the maximum number of votes that could have been affected**. Compare that number
with the national margin of victory.

Write down X, N and S (and the reasoning) **before** computing the anomaly table.

---

## 9. Limitations and ethics

- Ecological inference: section-level associations do not reveal individual votes.
- An anomaly is an **indication**, not proof; only an audit or investigation can confirm it.
- Log clock and event-format issues may create false signals (P0).
- Do not name poll workers or accuse specific sections publicly; report aggregates.
- Data is public; use nothing beyond what TSE publishes.

---

## 10. Prior work to read

- Klimek, P., Yegorov, Y., Hanel, R., & Thurner, S. (2012). Statistical detection of systematic election irregularities. *PNAS, 109*(41), 16469–16473.
- Mebane, W. R. — *Election Forensics* (turnout- and digit-based tests, and their limits).
- Partido Liberal / Instituto Voto Legal (2022). *Relatório Técnico — Logs Inválidos das Urnas Eletrônicas* (v0.7, 15/11/2022), plus the TSE response.
- Independent analysis by USP/UFSCar/UFPA and other researchers of the log issue (Poder360, Dec 2022): https://static.poder360.com.br/2022/12/Analise-Bug04030201_USPUFSCarUFPAoutros.pdf
- Virgolino, V. A. C. (2023). *UrnaLogs* — undergraduate thesis, UFCG (collection and organization of the 2022 logs by section): https://bdtd.ufcg.edu.br/jspui/bitstream/riufcg/30487/1/VICTOR%20ARRUDA%20C%c3%82MARA%20VIRGOLINO%20-%20TCC%20ARTIGO%20CI%c3%8aNCIA%20DA%20COMPUTA%c3%87%c3%83O%20CEEI%202023.pdf
- Fact-checks on "votes after 17:00" and on the logs (Comprova/Metrópoles, O Popular, 2022). List every argument they raise and make sure the analysis addresses it.
- TSE IT glossary (biometric verification vs. identification): https://www.tse.jus.br/institucional/catalogo-de-publicacoes/arquivos/glossario-ti

---

## 11. Expected deliverables

1. Section-level panel (2022 1t, 2022 2t, 2026 1t, all UFs) with the §4 variables.
2. Log event dictionary and reconciliation report (P0).
3. Descriptive report and figures (P1, fingerprints, close-time maps).
4. Hypothesis tests RQ1–RQ5 with effect sizes, placebo results and the 2026 replication.
5. Anomaly table (aggregate), with the maximum affected votes compared to the margin.
6. Written conclusion: whether the evidence supports the claim, and its limitations.
