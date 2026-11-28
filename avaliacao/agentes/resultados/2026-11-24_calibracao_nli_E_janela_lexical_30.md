# Calibração do limiar do NLI — 24/11/2026

Modelo `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` · 105 pares de `avaliacao/pares_ouro/verificador_v1.jsonl` (68 sustenta, 24 contradiz, 13 nao_trata) · regra: menor limiar com precisão ≥ 0.9

**Limiar escolhido: 0.4** — precisão 0.905, recall 0.838 (antes, em 0,5: precisão 0.905, recall 0.838)

| limiar | precisão | recall | F1 | falsas liberadas | boas barradas |
|---|---|---|---|---|---|
| 0.05 | 0.871 | 0.897 | 0.884 | 9 | 7 |
| 0.1 | 0.871 | 0.897 | 0.884 | 9 | 7 |
| 0.15 | 0.881 | 0.868 | 0.874 | 8 | 9 |
| 0.2 | 0.894 | 0.868 | 0.881 | 7 | 9 |
| 0.25 | 0.894 | 0.868 | 0.881 | 7 | 9 |
| 0.3 | 0.894 | 0.868 | 0.881 | 7 | 9 |
| 0.35 | 0.892 | 0.853 | 0.872 | 7 | 10 |
| 0.4 | 0.905 | 0.838 | 0.87 | 6 | 11 |
| 0.45 | 0.905 | 0.838 | 0.87 | 6 | 11 |
| 0.5 | 0.905 | 0.838 | 0.87 | 6 | 11 |
| 0.55 | 0.919 | 0.838 | 0.877 | 5 | 11 |
| 0.6 | 0.919 | 0.838 | 0.877 | 5 | 11 |
| 0.65 | 0.918 | 0.824 | 0.868 | 5 | 12 |
| 0.7 | 0.918 | 0.824 | 0.868 | 5 | 12 |
| 0.75 | 0.915 | 0.794 | 0.85 | 5 | 14 |
| 0.8 | 0.914 | 0.779 | 0.841 | 5 | 15 |
| 0.85 | 0.911 | 0.75 | 0.823 | 5 | 17 |
| 0.9 | 0.942 | 0.721 | 0.817 | 3 | 19 |
| 0.95 | 0.942 | 0.721 | 0.817 | 3 | 19 |

Só o NLI, sem as regras: em 0,5 precisão 0.805 / recall 0.912; no limiar escolhido precisão 0.805 / recall 0.912.

## Pares barrados pelas regras antes do NLI

| id | rótulo | motivo |
|---|---|---|
| bat17-01 | sustenta | a frase usa pouco do texto do trecho (sobreposição 0.27 < 0.30) |
| bat17-03 | sustenta | a frase usa pouco do texto do trecho (sobreposição 0.25 < 0.30) |
| bat17-07 | sustenta | a frase usa pouco do texto do trecho (sobreposição 0.23 < 0.30) |
| bat17-20 | contradiz | a frase usa pouco do texto do trecho (sobreposição 0.19 < 0.30) |
| bat17-23 | sustenta | a frase usa pouco do texto do trecho (sobreposição 0.26 < 0.30) |
| bat17-24 | nao_trata | a frase usa pouco do texto do trecho (sobreposição 0.23 < 0.30) |
| bat17-29 | sustenta | a frase usa pouco do texto do trecho (sobreposição 0.27 < 0.30) |
| bat17-56 | nao_trata | a frase usa pouco do texto do trecho (sobreposição 0.22 < 0.30) |
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
| adv-24 | nao_trata | a frase usa pouco do texto do trecho (sobreposição 0.14 < 0.30) |
| adv-25 | nao_trata | número ou prazo que não está no trecho: dois salarios |
| adv-26 | nao_trata | número ou prazo que não está no trecho: 40% |
| adv-27 | nao_trata | número ou prazo que não está no trecho: 21 horas |
| adv-28 | nao_trata | a frase usa pouco do texto do trecho (sobreposição 0.17 < 0.30) |
| adv-29 | nao_trata | a frase usa pouco do texto do trecho (sobreposição 0.14 < 0.30) |

## Por origem dos pares

| origem | n | precisão / recall no escolhido | em 0,5 |
|---|---|---|---|
| adversarial (escrita a partir do texto da fonte) | 38 | 0.538 / 0.875 | 0.538 / 0.875 |
| bateria 17/11 (frase real do sistema) | 67 | 1.0 / 0.833 | 1.0 / 0.833 |

## Erros no limiar escolhido

| id | rótulo | p(sustenta) | frase | fonte |
|---|---|---|---|---|
| bat17-01 | sustenta | 0.0 | A exceção é que, quando a jornada é de 12 horas de trabalho e 36 horas de descanso seguidas, não é preciso pedir autorização antes. | CLT, Art. 60 |
| bat17-03 | sustenta | 0.0 | A exceção é que trabalhar 12 horas por dia, com 36 horas seguidas de folga, não precisa de autorização prévia. | CLT, Art. 60 |
| bat17-07 | sustenta | 0.0 | O art. 462 da CLT permite que o empregador desconte parte do salário do funcionário se ele causar algum dano, mas só se houver acordo ou intenção maliciosa do funcionário. | CLT, Art. 462 |
| bat17-10 | sustenta | 0.336 | A remuneração do trabalho noturno urbano é maior em 20% do que a do diurno, conforme o CLT, Art. 73. | CLT, Art. 73 |
| bat17-12 | sustenta | 0.001 | O acréscimo de 20% é calculado sobre a hora diurna, conforme a LC 150/2015, Art. 14, § 2º. | LC 150/2015 (doméstico), Art. 14 |
| bat17-14 | sustenta | 0.369 | O trabalho noturno urbano é considerado aquele executado entre as 22 horas de um dia e as 5 horas do dia seguinte, conforme o CLT, Art. 73, § 2º. | CLT, Art. 73 |
| bat17-23 | sustenta | 0.0 | Se o trabalhador trabalhar mais do que o horário normal, mesmo que por pouco tempo, não é hora extra se ele fizer isso por vontade própria, como proteger-se ou usar instalações da empresa. | CLT, Art. 4º |
| bat17-29 | sustenta | 0.0 | O art. 473 da CLT permite que o empregado fique em casa sem perder o salário por até 2 dias seguidos se um familiar próximo morrer. | CLT, Art. 473 |
| bat17-61 | sustenta | 0.024 | A notificação do empregador relativa aos débitos com o FGTS interrompe o prazo prescricional, conforme o art. 23-A, § 1º, da Lei 8.036/1990. | Lei 8.036/1990 (FGTS), Art. 23-A |
| bat17-62 | sustenta | 0.125 | Os resultados financeiros da Caixa Econômica Federal no período entre o repasse dos bancos e o depósito nas contas vinculadas destinar-se-ão à cobertura das despesas de administração do FGTS, conforme o art. 4º da Lei 8.036/1990. | Lei 8.036/1990 (FGTS), Art. 12 |
| adv-03 | contradiz | 0.999 | O empregado pode faltar até 5 dias consecutivos por causa do casamento sem perder o salário. | CLT, Art. 473 |
| adv-07 | contradiz | 0.874 | São acrescidos 5 dias de aviso prévio por ano de serviço na mesma empresa. | Lei 12.506/2011 (aviso prévio), Art. 1º |
| adv-08 | contradiz | 0.511 | O desconto no salário por dano causado pelo empregado é sempre proibido. | CLT, Art. 462 |
| adv-15 | contradiz | 0.997 | Na dispensa sem justa causa, o empregador deposita no FGTS uma multa de 20% sobre os depósitos do contrato. | Lei 8.036/1990 (FGTS), Art. 18 |
| adv-17 | contradiz | 0.963 | Na primeira solicitação do seguro-desemprego, basta ter recebido salários em 6 dos últimos 12 meses. | Lei 7.998/1990 (seguro-desemprego), Art. 3º |
| adv-20 | contradiz | 0.874 | As gorjetas não fazem parte da remuneração do empregado. | CLT, Art. 457 |
| adv-35 | sustenta | 0.104 | A multa do art. 477 é devida mesmo quando o vínculo de emprego só foi reconhecido na Justiça. | Súmula 462 do TST |
