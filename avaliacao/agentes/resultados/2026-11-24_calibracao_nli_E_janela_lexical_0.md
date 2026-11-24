# Calibração do limiar do NLI — 24/11/2026

Modelo `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` · 105 pares de `avaliacao/pares_ouro/verificador_v1.jsonl` (68 sustenta, 24 contradiz, 13 nao_trata) · regra: menor limiar com precisão ≥ 0.9

**Limiar escolhido: 0.9** — precisão 0.915, recall 0.794 (antes, em 0,5: precisão 0.886, recall 0.912)

| limiar | precisão | recall | F1 | falsas liberadas | boas barradas |
|---|---|---|---|---|---|
| 0.05 | 0.846 | 0.971 | 0.904 | 12 | 2 |
| 0.1 | 0.857 | 0.971 | 0.91 | 11 | 2 |
| 0.15 | 0.865 | 0.941 | 0.901 | 10 | 4 |
| 0.2 | 0.877 | 0.941 | 0.908 | 9 | 4 |
| 0.25 | 0.877 | 0.941 | 0.908 | 9 | 4 |
| 0.3 | 0.877 | 0.941 | 0.908 | 9 | 4 |
| 0.35 | 0.875 | 0.926 | 0.9 | 9 | 5 |
| 0.4 | 0.886 | 0.912 | 0.899 | 8 | 6 |
| 0.45 | 0.886 | 0.912 | 0.899 | 8 | 6 |
| 0.5 | 0.886 | 0.912 | 0.899 | 8 | 6 |
| 0.55 | 0.899 | 0.912 | 0.905 | 7 | 6 |
| 0.6 | 0.899 | 0.912 | 0.905 | 7 | 6 |
| 0.65 | 0.897 | 0.897 | 0.897 | 7 | 7 |
| 0.7 | 0.897 | 0.897 | 0.897 | 7 | 7 |
| 0.75 | 0.894 | 0.868 | 0.881 | 7 | 9 |
| 0.8 | 0.892 | 0.853 | 0.872 | 7 | 10 |
| 0.85 | 0.889 | 0.824 | 0.855 | 7 | 12 |
| 0.9 | 0.915 | 0.794 | 0.85 | 5 | 14 |
| 0.95 | 0.914 | 0.779 | 0.841 | 5 | 15 |

Só o NLI, sem as regras: em 0,5 precisão 0.805 / recall 0.912; no limiar escolhido precisão 0.871 / recall 0.794.

## Pares barrados pelas regras antes do NLI

| id | rótulo | motivo |
|---|---|---|
| adv-00 | contradiz | número ou prazo que não está no trecho: 10% |
| adv-01 | contradiz | número ou prazo que não está no trecho: 60 minutos |
| adv-04 | contradiz | número ou prazo que não está no dispositivo que sustenta a frase: 8 dias |
| adv-05 | contradiz | número ou prazo que não está no dispositivo que sustenta a frase: 6 meses |
| adv-06 | contradiz | número ou prazo que não está no trecho: 120 dias |
| adv-10 | contradiz | número ou prazo que não está no trecho: 50% |
| adv-13 | contradiz | número ou prazo que não está no dispositivo que sustenta a frase: dois meses |
| adv-16 | contradiz | número ou prazo que não está no trecho: trinta dias |
| adv-22 | contradiz | número ou prazo que não está no trecho: 180 dias |
| adv-23 | nao_trata | número ou prazo que não está no trecho: 30 dias |
| adv-25 | nao_trata | número ou prazo que não está no trecho: dois salarios |
| adv-26 | nao_trata | número ou prazo que não está no trecho: 40% |
| adv-27 | nao_trata | número ou prazo que não está no trecho: 21 horas |

## Por origem dos pares

| origem | n | precisão / recall no escolhido | em 0,5 |
|---|---|---|---|
| adversarial (escrita a partir do texto da fonte) | 38 | 0.625 / 0.625 | 0.538 / 0.875 |
| bateria 17/11 (frase real do sistema) | 67 | 0.961 / 0.817 | 0.965 / 0.917 |

## Erros no limiar escolhido

| id | rótulo | p(sustenta) | frase | fonte |
|---|---|---|---|---|
| bat17-06 | sustenta | 0.893 | O art. 462 também proíbe que as empresas restringam a liberdade dos funcionários de usar o seu salário como quiserem. | CLT, Art. 462 |
| bat17-09 | sustenta | 0.733 | O art. 462 também proíbe que as empresas obriguem os funcionários a usar o seu salário de uma forma específica. | CLT, Art. 462 |
| bat17-10 | sustenta | 0.336 | A remuneração do trabalho noturno urbano é maior em 20% do que a do diurno, conforme o CLT, Art. 73. | CLT, Art. 73 |
| bat17-11 | sustenta | 0.735 | A hora de trabalho noturno urbano é contada como 52 minutos e 30 segundos, conforme o CLT, Art. 73, § 1º. | CLT, Art. 73 |
| bat17-12 | sustenta | 0.001 | O acréscimo de 20% é calculado sobre a hora diurna, conforme a LC 150/2015, Art. 14, § 2º. | LC 150/2015 (doméstico), Art. 14 |
| bat17-14 | sustenta | 0.369 | O trabalho noturno urbano é considerado aquele executado entre as 22 horas de um dia e as 5 horas do dia seguinte, conforme o CLT, Art. 73, § 2º. | CLT, Art. 73 |
| bat17-20 | contradiz | 0.999 | O tempo que passa além da jornada normal, mesmo que seja um pouco mais, não é considerado hora extra, a menos que haja uma regra específica. | CLT, Art. 4º |
| bat17-49 | sustenta | 0.822 | O trabalhador demitido sem justa causa (falta grave que permite encerrar o contrato sem algumas verbas) tem direito à remuneração das férias não gozadas, se o contrato acaba antes de 12 meses de trabalho, conforme o Art. 147 da CLT. | CLT, Art. 147 |
| bat17-51 | sustenta | 0.644 | O seguro-desemprego para empregados domésticos demitidos sem justa causa tem valor de 1 salário-mínimo, por até 3 meses, conforme o Art. 26 da LC 150/2015. | LC 150/2015 (doméstico), Art. 26 |
| bat17-56 | nao_trata | 0.984 | A mulher grávida pode parar de trabalhar se o emprego prejudicar a gravidez, conforme o Art. 394 da CLT. | CLT, Art. 394 |
| bat17-61 | sustenta | 0.024 | A notificação do empregador relativa aos débitos com o FGTS interrompe o prazo prescricional, conforme o art. 23-A, § 1º, da Lei 8.036/1990. | Lei 8.036/1990 (FGTS), Art. 23-A |
| bat17-62 | sustenta | 0.125 | Os resultados financeiros da Caixa Econômica Federal no período entre o repasse dos bancos e o depósito nas contas vinculadas destinar-se-ão à cobertura das despesas de administração do FGTS, conforme o art. 4º da Lei 8.036/1990. | Lei 8.036/1990 (FGTS), Art. 12 |
| bat17-63 | sustenta | 0.873 | A Caixa Econômica Federal passa a gerenciar as contas do FGTS (Fundo de Garantia do Tempo de Serviço) dentro de um ano, a partir da promulgação da Lei 8.036/1990, conforme o art. 12, caput, da mesma lei. | Lei 8.036/1990 (FGTS), Art. 12 |
| adv-03 | contradiz | 0.999 | O empregado pode faltar até 5 dias consecutivos por causa do casamento sem perder o salário. | CLT, Art. 473 |
| adv-15 | contradiz | 0.997 | Na dispensa sem justa causa, o empregador deposita no FGTS uma multa de 20% sobre os depósitos do contrato. | Lei 8.036/1990 (FGTS), Art. 18 |
| adv-17 | contradiz | 0.963 | Na primeira solicitação do seguro-desemprego, basta ter recebido salários em 6 dos últimos 12 meses. | Lei 7.998/1990 (seguro-desemprego), Art. 3º |
| adv-33 | sustenta | 0.751 | Se a reintegração não acontece dentro do período de estabilidade, a gestante tem direito aos salários desse período. | Súmula 244 do TST |
| adv-34 | sustenta | 0.843 | A empregada gestante não pode ser dispensada sem justa causa desde a confirmação da gravidez até cinco meses após o parto. | ADCT, Art. 10 |
| adv-35 | sustenta | 0.104 | A multa do art. 477 é devida mesmo quando o vínculo de emprego só foi reconhecido na Justiça. | Súmula 462 do TST |
