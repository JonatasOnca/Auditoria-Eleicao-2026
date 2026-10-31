# Modelo de ameaças do processo eleitoral brasileiro (visão de auditor)

> Exercício de auditoria de processos: percorrer a cadeia eleitoral, apontar onde
> poderia haver fraude ou sabotagem, quais controles existem e qual risco sobra.
> Cada vulnerabilidade aqui é uma **hipótese de auditoria**, não uma afirmação de
> que a fraude ocorreu. O texto fica no nível de processo e controle; não descreve
> como executar nenhum ataque.
>
> Ligado ao [RESEARCH_PLAN-pt-br.md](../RESEARCH_PLAN-pt-br.md) (§9). As análises
> citadas (RQ1–RQ5, P0–P9) estão definidas lá.

---

## 1. Cadeia eleitoral e superfícies de ataque

Formato de cada linha: **etapa → ameaça → controles existentes → risco residual →
o que os dados públicos do TSE conseguem detectar neste projeto.**

| # | Etapa | Ameaça (onde poderia haver fraude) | Controles existentes | Risco residual | Detecção com dados do TSE |
|---|---|---|---|---|---|
| 1 | Cadastro eleitoral | Transferência fraudulenta de domicílio eleitoral em municípios pequenos; eleitores falecidos ou duplicados não baixados | Biometria, revisões do eleitorado, cruzamento com registros de óbito, crime eleitoral (arts. 289–290 do Código Eleitoral) | **Médio** em municípios pequenos, onde poucos votos decidem a eleição municipal; **baixo** para Presidente | Crescimento de `QT_APTOS` por município entre eleições; perfil do eleitorado por seção |
| 2 | Desenvolvimento do software (TSE) | Ameaça interna: código alterado antes da assinatura; confiança na cadeia de compilação e no hardware do fornecedor | Inspeção do código-fonte aberta às entidades fiscalizadoras desde 12 meses antes, Teste Público de Segurança (TPS), cerimônia de assinatura digital e lacração, hashes publicados | **Baixo, mas estrutural**: a garantia depende de poucas pessoas e ferramentas, e o tempo e o acesso dos fiscalizadores são limitados | Nenhuma direta; só indício estatístico (P5–P7) |
| 3 | Preparação e carga das urnas (TRE/zona) | Ameaça interna na carga; urna carregada com mídia errada ou adulterada | A urna verifica a assinatura digital do software, cerimônia pública de carga, zerésima | **Baixo**; a presença de fiscais nessas cerimônias costuma ser baixa | Logs do sistema de preparação (GEDAI), `DT_CARGA_URNA_EFETIVADA`, correspondência esperada × efetivada |
| 4 | Dia da eleição: a mesa | Mesário votando por ausentes (hipótese em teste neste projeto); habilitação sem biometria; coação e voto de cabresto; compra de voto; controle territorial por milícia ou tráfico | Biometria; habilitação manual exige a digital do próprio mesário; fiscais de partido; log de eventos; celular proibido na cabine | **Médio/alto localmente**: concentra a maior parte dos casos reais julgados no Brasil. A presença ou ausência de fiscais não está nos dados abertos | RQ1–RQ5: `nh_rate_after`, `gap_before_17`, rajadas, fingerprint de Klimek |
| 5 | Falha de urna, contingência, cédula | Mais intervenção manual: troca de urna, recuperação de dados, votação em cédula | Procedimento registrado em ata e no log; arquivos de correspondência de urnas | **Médio**: é a etapa menos automatizada | `DS_TIPO_URNA`, CESP/CEFT, eventos de contingência e recuperação no log (P0) |
| 6 | Encerramento e BU | BU alterado entre a urna e a totalização | BU impresso em várias vias e afixado na porta, QR Code, assinatura digital, publicação por seção | **Baixo**, desde que os partidos colham os BUs. **É o controle mais forte do sistema** | Conferir o BU publicado com a imagem `imgbu.dat` e com BUs colhidos por terceiros |
| 7 | Transmissão e totalização (centralizada no TSE desde 2020) | Ataque de disponibilidade, atraso, vazamento; pausa na totalização que gera desconfiança | BU assinado digitalmente; qualquer parte pode retotalizar com os dados por seção | **Baixo para alterar o resultado; médio para gerar desconfiança** (atraso em 2020, pausa no recebimento de BUs no 2º turno de 2026) | `receipt_delay` (P8), histórico de totalização |
| 8 | **O voto dentro da urna: não há registro em papel conferível pelo eleitor** | Uma alteração no software da urna **antes** de gerar o BU não é detectável por recontagem, porque não existe outra cópia independente do voto | Teste de integridade (votação paralela em urnas sorteadas na véspera, filmada; em 2026 também na modalidade com biometria de eleitores voluntários), assinatura digital, TPS | **É o principal ponto estrutural** apontado pela literatura (ver Alemanha, 2009). A amostra é pequena e o teste só funciona se a urna não distinguir o teste da eleição real | Só indireta: consistência estatística entre seções e turnos (P5–P7) e os resultados publicados do teste de integridade |
| 9 | Governança institucional | O mesmo órgão (TSE) normatiza, administra e julga; mudança de regra no dia da eleição (prorrogação até as 19h no 2º turno de 2026, §1.2 do plano) | Revisão pelo STF, Ministério Público Eleitoral, publicidade dos atos | **Risco de legitimidade**, não de contagem | §1.2 do plano; variável `extended_regime` |
| 10 | Período pré-eleitoral | Abuso de poder econômico ou político, uso da máquina pública, falta de transporte, desinformação, violência política | Cassação de registro e diploma, AIJE, ADPF 1.013 (transporte gratuito), direito de resposta | **Alto**: é o tipo de fraude mais comum e mais punido no Brasil, e não passa pela urna | Fora do alcance dos dados de urna; denúncias do Pardal (P9) |

### Conclusão do auditor

- **Mais risco real e documentado:** etapas 4, 1 e 10. Todas são locais e dependem
  de intervenção humana.
- **Mais risco estrutural:** etapa 8, porque o eleitor não tem um registro em papel
  que permita conferir a contagem de forma independente.
- **Controle mais forte:** etapa 6. O BU é impresso, afixado e publicado por seção,
  e qualquer partido pode refazer a soma.
- **Escala:** uma fraude nacional teria de passar pelas etapas 2, 3 e 8 sem ser
  pega na inspeção de código, no TPS e no teste de integridade, o que exige um
  conluio interno grande. Uma fraude local (etapa 4) custa pouco, mas tem alcance
  limitado e deixa rastro no log da urna, que é o que este projeto mede.

---

## 2. Escândalos de outros países: poderiam ocorrer aqui?

| Caso | O que aconteceu | Análogo no Brasil | Avaliação |
|---|---|---|---|
| **Dieselgate (Volkswagen, 2015)** | O software dos motores detectava quando estava em teste e se comportava de outro jeito | Teste de integridade da urna (etapa 8) | **Possível em tese.** Mitigado pelo sorteio na véspera, pela simulação realista e pela biometria de eleitores reais. É o argumento mais forte a favor de um registro em papel |
| **Holanda, 2006 (urnas Nedap)** | Grupo cívico, com o Chaos Computer Club, mostrou que as urnas podiam ser reprogramadas; o governo suspendeu o voto eletrônico | TPS brasileiro | **Já ocorreu em parte:** no TPS de 2012, uma equipe da UnB (Diego Aranha) recuperou a ordem dos votos no RDV de uma urna (474 de 475), o que ameaçava o sigilo; o TSE corrigiu o embaralhamento. Em 2017, outra equipe achou a chave de cifra do sistema de arquivos. Mostra que o TPS encontra falhas e que elas existiram |
| **Alemanha, 03/03/2009 (Tribunal Constitucional)** | O uso das urnas Nedap em 2005 foi declarado inconstitucional: as etapas essenciais da eleição devem poder ser verificadas por cidadãos sem conhecimento técnico. O resultado de 2005 foi mantido, por falta de prova de manipulação | Etapa 8 | **Aplicável como princípio**: é a crítica de verificabilidade pública ao modelo brasileiro |
| **Índia (urnas EVM)** | Acusações de adulteração; o país passou a usar comprovante em papel (VVPAT) | Etapa 8 | Mostra a solução que o Brasil discutiu e não adotou: o STF declarou inconstitucional o voto impresso em 14/09/2020 (ADI 5.889), alegando risco ao sigilo e à liberdade do voto |
| **Rússia (carrossel, enchimento de urna)** | Votos em nome de ausentes; picos de comparecimento detectados estatisticamente (Klimek et al., 2012) | Etapa 4: é exatamente a hipótese em teste | **Possível localmente.** A biometria encarece, mas a habilitação manual continua possível. Detectável pelo fingerprint e pelo log (P2–P5) |
| **EUA, Carolina do Norte, 9º distrito (2018)** | Coleta fraudulenta de votos pelo correio; nova eleição convocada pelo conselho eleitoral | Não há voto pelo correio no Brasil | **Mecanismo diferente.** O risco equivalente aqui é a coação local (etapas 4 e 10) |
| **Venezuela, 2024** | A oposição reuniu as atas das mesas e mostrou divergência com o resultado anunciado pelo CNE, que não publicou o resultado por mesa | BU na porta e publicação por seção | **O controle brasileiro é justamente esse**: qualquer parte pode refazer a totalização com os BUs. O risco aqui seria deixar de publicar os BUs, o que não ocorreu |
| **Bolívia, 2019** | A contagem rápida (TREP) foi interrompida na noite da eleição e retomada com mudança de tendência; a auditoria da OEA apontou "manipulação intencional". **Caso contestado:** o CEPR e outros questionaram a análise da OEA | Pausa no recebimento de BUs no 2º turno de 2026 | **Risco de narrativa.** Dá para auditar com o histórico de totalização e o `receipt_delay` (P8) |
| **Quênia, 2017** | A Suprema Corte anulou a eleição presidencial de 08/08/2017 por irregularidades na condução e na transmissão dos resultados | Etapa 7 | **Baixo**: o BU é assinado digitalmente e pode ser conferido com o impresso |
| **EUA, 2020 / Brasil, 2022** | Alegações de fraude sem dados que as sustentassem (urnas Dominion; relatório do PL sobre os logs) | — | **Lição de método**: toda alegação precisa virar uma hipótese testável, como neste projeto |

---

## 3. O que isso muda no projeto

| Etapa | Situação |
|---|---|
| 1 Cadastro | Testável em parte (crescimento de aptos por município); fora do escopo atual |
| 3 Carga | Testável com logs GEDAI e correspondência (P0) |
| 4 Mesa | **Núcleo do projeto** (RQ1–RQ5) |
| 5 Contingência | P0 |
| 6 BU | Testável: conferência BU × `imgbu.dat` |
| 7 Totalização | P8 |
| 2, 8, 9, 10 | Não testáveis diretamente com dados abertos; só indícios estatísticos ou contexto (P9) |

**Pendência:** obter os resultados publicados do teste de integridade de 2026
(TSE e TREs, 1º e 2º turnos). São a única evidência direta disponível sobre a
etapa 8.

---

## Fontes

- TPS 2012 (UnB, ordem dos votos): https://www.baguete.com.br/noticias/unb-quebra-sigilo-da-urna-eletronica ·
  relatório técnico: https://www.lasca.ic.unicamp.br/media/publications/relatorio-urna.pdf ·
  TPS 2017: https://www.welivesecurity.com/br/2018/10/17/diego-aranha-os-testes-de-seguranca-nas-urnas-eletronicas/
- Alemanha, BVerfG 2 BvC 3/07, 03/03/2009: https://www.wahlrecht.de/wahlpruefung/20090303.htm ·
  Holanda e Alemanha: https://edri.org/our-work/edri-gramnumber7-5no-evoting-germany/
- STF, ADI 5.889 (voto impresso): https://www.conjur.com.br/2020-set-16/supremo-confirma-liminar-impede-volta-voto-impresso/
- Teste de integridade 2026 (TSE): https://www.tse.jus.br/comunicacao/noticias/2026/Outubro/teste-de-integridade-no-tse-confirma-correspondencia-entre-cedulas-e-votos-registrados-nas-urnas
- Quênia 2017: https://www.aljazeera.com/news/2017/9/4/kenya-to-hold-fresh-presidential-election-on-october-17
- Carolina do Norte 2018: https://www.jurist.org/news/2019/02/north-carolina-elections-board-votes-to-hold-new-congressional-election/
- Bolívia 2019 (crítica à OEA): https://cepr.net/report/observing-the-observers-the-oas-in-the-2019-bolivian-elections/
- Klimek, P. et al. (2012). Statistical detection of systematic election irregularities. *PNAS, 109*(41).
- *Fontes a anexar:* Venezuela 2024 (atas da oposição e posição do CNE); Índia (adoção do VVPAT); Dieselgate (EPA, 2015).
