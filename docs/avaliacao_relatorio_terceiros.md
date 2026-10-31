# Avaliação do relatório de terceiros "Relatório Pericial Independente — Eleições 2026"

> Documento de terceiros (28/10/2026), **não produzido por este projeto**. A transcrição integral e as imagens
> originais estão em [referencias/terceiros/relatorio-28-10-2026/](../referencias/terceiros/relatorio-28-10-2026/).
> Este arquivo reúne só a conferência feita pelo projeto Auditoria-Eleicao-2026, com dados oficiais do TSE.

## 1. Notas de verificação

Conferência feita em 29/10/2026 com o Boletim de Urna do 2º turno (`bweb_2t_*`, 28 UFs, SHA-512 conferido com o
`.sha512` oficial) já validado contra a API de Resultados assinada do TSE. Somente dados oficiais do TSE.

**Números que se reproduzem exatamente**

| Afirmação do documento | Valor nos dados oficiais |
|---|---|
| 499.205 seções; 128.236.074 votos | 499.205 seções; comparecimento 128.236.074 |
| 8.632.488 eleitores sem biometria (6,73%) | soma de `QT_ELEI_BIOM_SEM_HABILITACAO` = 8.632.488 (6,73%) |
| Margem de 4.430.191 votos | Lula 64.256.232 − Flávio 59.826.041 = 4.430.191 |
| 17h01–17h15: 339.593 seções, 88.071.750 eleitores, 53,46% Lula | idêntico |
| 17h16–18h59: 2.472 seções, 674.799 eleitores, 57,16% Lula | idêntico |
| Até 17h00: Flávio 52,39%, vantagem ~1,8 mi | Flávio 52,39%, vantagem 1.747.639 |
| Após 17h00: vantagem de Lula > 6,1 mi | 6.177.738 |
| Após 19h00: 6.333 seções, 1.856.306 eleitores | 6.342 seções, 1.858.274 (diferença no corte do minuto 19h00) |

**Ressalva de método que muda a leitura do Capítulo 1.** `DT_ENCERRAMENTO` (e `DT_ABERTURA`) estão na **hora local
da urna**, não na de Brasília: o menor encerramento é 15:00:13, e 32.033 urnas abriram às 6h ou 7h locais (8h de
Brasília em AC, AM, MS, MT, RO e RR). As janelas do documento usam a hora local, então as seções desses estados, que
encerraram às 17h de Brasília (15h ou 16h locais), caem em "até 17h00". Refeito com a hora de Brasília (fuso de cada
seção inferido da própria hora de abertura; 1.324 seções do exterior ou com abertura fora do padrão ficam de fora):

| Janela (hora de Brasília) | Seções | Comparecimento | % Lula (válidos Lula+Flávio) | Vantagem de Lula |
|---|---|---|---|---|
| até 17h00 | 125.673 | 31.612.267 | 49,01% | −604.845 |
| 17h01–17h15 | 363.364 | 93.703.651 | 52,61% | +4.726.581 |
| 17h16–18h59 | 2.493 | 675.172 | 57,15% | +93.226 |
| 19h00 ou mais | 6.351 | 1.860.955 | 55,18% | +185.676 |

A diferença entre janelas continua existindo, mas a vantagem de Flávio nas seções "até 17h00" cai de ~1,75 milhão
para ~605 mil. Diferenças entre janelas de encerramento também refletem o perfil das seções (tamanho, fila, região),
então são associação ecológica, não causa.

**Outras observações**

- *Data de liberação (Introdução e Conclusão):* os arquivos `bweb_2t_*` têm no nome o carimbo 26/10/2026 07:42 e
  apareceram no catálogo do Portal de Dados Abertos em 27/10; o documento fala em liberação na manhã de 28/10.
- *`QT_ELEI_BIOM_SEM_HABILITACAO`:* o número total confere, mas o campo conta eleitores cuja digital não foi
  reconhecida e que foram habilitados de outra forma. Ele não indica, por si só, voto irregular; a comparação com a
  margem de vitória é uma comparação de grandezas, não uma medida de efeito. Os logs das urnas (`log_urna_2t`)
  permitem separar habilitação biométrica, manual após tentativas de digital e sem biometria, por horário.
- *Capítulos 4 e 5 (percentuais extremos e Benford):* conferidos em 31/10/2026; ver a avaliação abaixo.
- *Capítulo 6 (contexto institucional):* afirmações sobre pessoas e fatos políticos que não vêm de dados do TSE; fora
  do escopo analítico deste projeto. Checagem de contexto, com fontes de imprensa, na avaliação abaixo.

## 2. Avaliação de método (31/10/2026)

Revisão feita com os papéis de estatística, operação da seção e segurança, direito eleitoral e revisão independente
(`.claude/agents/`). Dados: `data/bu_2026_{1,2}t/` (BU, todas as UFs) e `data/logs_2026_2t/` (logs pelo método corrigido,
27 UFs e 395.522 seções; **sem SP**, cujo reprocessamento não tinha terminado). É uma revisão técnica de assistentes,
não um laudo nem um parecer jurídico.

**Veredito.** Os números do documento vêm de campos oficiais e, em geral, conferem. As conclusões não têm base
científica: não há hipótese fixada antes dos dados, comparação com o 1º turno, controles, testes nem medida de
incerteza, e não há código ou tabela por seção publicados. Em vários pontos, os próprios dados do TSE contradizem a
conclusão.

| Afirmação do documento | O que os dados mostram |
|---|---|
| "Após as 19h00": 6.333 seções, 1,86 mi de eleitores | 6.344 seções encerraram às 19h ou depois (hora de Brasília), mas os logs registram **6 votos** dados a partir das 19h (RJ 4, BA 2). Mediana de 124 min entre o último voto e o encerramento: urnas abertas pela prorrogação, sem eleitores. O documento confunde eleitores da seção com votos fora do horário |
| Percentuais "avassaladores" nas seções após 19h | Acompanham a % Lula do próprio município: SP 57,46% observado × 55,14% esperado (94% dessas seções são da capital); BA 72,31% × 72,70%; PE 65,79% × 67,21%. MA tem só 3 seções nesse grupo |
| 8,63 mi sem biometria, "quase o dobro da margem" | Comparação de grandezas, não medida de efeito. Correlação por seção entre taxa sem biometria e % Lula: 0,068 (2t) e 0,063 (1t); com efeito fixo de município, 0,012. Regressão dentro do município: +0,028 pp por ponto de taxa (IC95% −0,041 a +0,097), efeito nulo. "< 0,1%" não é forma de expressar correlação |
| Liberação "mediante a simples digitação do ano de nascimento" | O campo acompanha o caminho manual que exige dado pessoal e a **digital do mesário** ("Solicita digital do mesário", "Mesário N habilitou o eleitor"): correlação de 0,996 por seção com `n_manual_com_biometria` do log, e −0,06 com o caminho do ano de nascimento |
| "Escala inédita no segundo turno" | Taxa nacional 6,66% (1t) e 6,73% (2t); distribuição por seção quase idêntica; correlação de 0,82 da mesma seção entre turnos |
| "Sob a proteção da escuridão de uma prorrogação" | Das ~13,4 mi habilitações não biométricas no log, 4.586 (0,03%) ocorreram após as 17h e 1 após as 19h |
| Cap. 4: percentuais deveriam ser "gaussianos" | Premissa falsa (assimetria 0,28, curtose −0,55; reflete a geografia). As contagens 6.899 e 384 correspondem a ≥90%, não a ">90%" (6.816 e 378). A razão ~20:1 já existia no 1º turno (3.639 × 184) |
| Cap. 5: Benford | Inaplicável a contagens limitadas pelo tamanho da seção (p10 = 185, p90 = 320 eleitores). A "anomalia" aparece igual para os dois candidatos nos dois turnos. O documento não publica o resultado |
| Corte das 17h (Cap. 1) | `DT_ENCERRAMENTO` está em hora local (ver ressalva acima); a prorrogação até 19h no 2º turno (RESEARCH_PLAN §1.2) torna legal o voto entre 17h e 19h nas seções abertas, o que o documento ignora |

**Capítulo 6 (checagem de contexto, fontes de imprensa; nenhuma afirmação tem fonte no documento).**
- **Passaportes "7 minutos" após a proclamação: parcial e distorcida.** O pedido foi da PF; Moraes determinou a
  entrega dos passaportes num inquérito sigiloso.
  ([Conjur](https://conjur.com.br/2026-out-27/moraes-manda-flavio-entregar-passaporte-e-o-proibe-de-deixar-o-pais/))
- **"PF articulou prisão" e "proteção diplomática dos EUA": contradita.** O pedido de prisão foi de deputados, e a PF
  declarou que Flávio não é foragido.
  ([Gazeta do Povo](https://www.gazetadopovo.com.br/gazeta-agora/gazeta-agora-pf-afirma-que-flavio-bolsonaro-nao-e-foragido-e-descarta-decretar-prisao/))
- **"US$ 40 mi à família de magistrados": não encontrada.** Existem outras alegações, com outros valores.
- **Trump: confirmado.** Disse que a eleição "pareceu fraudada", sem provas.
  ([Gazeta do Povo](https://www.gazetadopovo.com.br/mundo/trump-diz-que-eleicao-no-brasil-pareceu-fraudada-mas-afirma-ter-boa-relacao-com-lula/))
- **Argentina: parcial.**
- **China "admitiu": contradita.** Pequim parabenizou Lula.
  ([Brasil de Fato](https://www.brasildefato.com.br/2026/10/26/china-parabeniza-reeleicao-de-lula-e-diz-que-respeita-a-decisao-do-povo-brasileiro/))

**Título.** "Pericial" é impróprio: perícia é feita por perito nomeado num processo (CPC, arts. 156 e 464–480), e o
próprio rodapé diz que o texto "não constitui laudo judicial". O termo adequado é estudo estatístico independente.

**Indícios de produção com IA (não comprováveis só pelo texto).**
- **Confiança:** moderada a alta de que a versão final foi reescrita com um modelo de linguagem; baixa sobre a origem
  da análise e dos números.
- **Indícios a favor:**
  - referências a uma "análise original" e a "análises independentes posteriores";
  - a nota sobre gráficos "que dependiam de imagens anexas à análise original";
  - autorreferência à edição ("Ressalvas metodológicas… foram incorporadas neste documento");
  - ressalvas técnicas convivendo com retórica oposta;
  - parágrafo repetido no Cap. 3 e no Anexo;
  - tríades, construções "não é X, é Y", títulos dramáticos e fechos de efeito.
- **Indícios contra:**
  - acusações nominais sem fonte, atípicas de modelos comerciais;
  - vocabulário comum do jornalismo político;
  - erros de conta compatíveis com edição humana.

**Pendências.**
- Refazer os votos após 17h e após 19h com SP, quando o reprocessamento terminar.
- Conferir por que 98 mil habilitações manuais não têm a linha "Mesário N habilitou o eleitor" no log.
- Confirmar na resolução do TSE de 2026 os dados exigidos na habilitação manual.
