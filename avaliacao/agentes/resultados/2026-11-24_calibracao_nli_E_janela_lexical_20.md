# Calibração do limiar do NLI — 24/11/2026

Modelo `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` · 105 pares de `avaliacao/pares_ouro/verificador_v1.jsonl` (68 sustenta, 24 contradiz, 13 nao_trata) · regra: menor limiar com precisão ≥ 0.9

**Limiar escolhido: 0.55** — precisão 0.912, recall 0.912 (antes, em 0,5: precisão 0.899, recall 0.912)

| limiar | precisão | recall | F1 | falsas liberadas | boas barradas |
|---|---|---|---|---|---|
| 0.05 | 0.868 | 0.971 | 0.917 | 10 | 2 |
| 0.1 | 0.868 | 0.971 | 0.917 | 10 | 2 |
| 0.15 | 0.877 | 0.941 | 0.908 | 9 | 4 |
| 0.2 | 0.889 | 0.941 | 0.914 | 8 | 4 |
| 0.25 | 0.889 | 0.941 | 0.914 | 8 | 4 |
| 0.3 | 0.889 | 0.941 | 0.914 | 8 | 4 |
| 0.35 | 0.887 | 0.926 | 0.906 | 8 | 5 |
| 0.4 | 0.899 | 0.912 | 0.905 | 7 | 6 |
| 0.45 | 0.899 | 0.912 | 0.905 | 7 | 6 |
| 0.5 | 0.899 | 0.912 | 0.905 | 7 | 6 |
| 0.55 | 0.912 | 0.912 | 0.912 | 6 | 6 |
| 0.6 | 0.912 | 0.912 | 0.912 | 6 | 6 |
| 0.65 | 0.91 | 0.897 | 0.904 | 6 | 7 |
| 0.7 | 0.91 | 0.897 | 0.904 | 6 | 7 |
| 0.75 | 0.908 | 0.868 | 0.887 | 6 | 9 |
| 0.8 | 0.906 | 0.853 | 0.879 | 6 | 10 |
| 0.85 | 0.903 | 0.824 | 0.862 | 6 | 12 |
| 0.9 | 0.931 | 0.794 | 0.857 | 4 | 14 |
| 0.95 | 0.93 | 0.779 | 0.848 | 4 | 15 |

Só o NLI, sem as regras: em 0,5 precisão 0.805 / recall 0.912; no limiar escolhido precisão 0.816 / recall 0.912.

## Pares barrados pelas regras antes do NLI

| id | rótulo | motivo |
|---|---|---|
| bat17-20 | contradiz | a frase usa pouco do texto do trecho (sobreposição 0.19 < 0.20) |
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
| adv-24 | nao_trata | a frase usa pouco do texto do trecho (sobreposição 0.14 < 0.20) |
| adv-25 | nao_trata | número ou prazo que não está no trecho: dois salarios |
| adv-26 | nao_trata | número ou prazo que não está no trecho: 40% |
| adv-27 | nao_trata | número ou prazo que não está no trecho: 21 horas |
| adv-28 | nao_trata | a frase usa pouco do texto do trecho (sobreposição 0.17 < 0.20) |
| adv-29 | nao_trata | a frase usa pouco do texto do trecho (sobreposição 0.14 < 0.20) |

## Por origem dos pares

| origem | n | precisão / recall no escolhido | em 0,5 |
|---|---|---|---|
| adversarial (escrita a partir do texto da fonte) | 38 | 0.583 / 0.875 | 0.538 / 0.875 |
| bateria 17/11 (frase real do sistema) | 67 | 0.982 / 0.917 | 0.982 / 0.917 |

## Erros no limiar escolhido

| id | rótulo | p(sustenta) | frase | fonte |
|---|---|---|---|---|
| bat17-10 | sustenta | 0.336 | A remuneração do trabalho noturno urbano é maior em 20% do que a do diurno, conforme o CLT, Art. 73. | CLT, Art. 73 |
| bat17-12 | sustenta | 0.001 | O acréscimo de 20% é calculado sobre a hora diurna, conforme a LC 150/2015, Art. 14, § 2º. | LC 150/2015 (doméstico), Art. 14 |
| bat17-14 | sustenta | 0.369 | O trabalho noturno urbano é considerado aquele executado entre as 22 horas de um dia e as 5 horas do dia seguinte, conforme o CLT, Art. 73, § 2º. | CLT, Art. 73 |
| bat17-56 | nao_trata | 0.984 | A mulher grávida pode parar de trabalhar se o emprego prejudicar a gravidez, conforme o Art. 394 da CLT. | CLT, Art. 394 |
| bat17-61 | sustenta | 0.024 | A notificação do empregador relativa aos débitos com o FGTS interrompe o prazo prescricional, conforme o art. 23-A, § 1º, da Lei 8.036/1990. | Lei 8.036/1990 (FGTS), Art. 23-A |
| bat17-62 | sustenta | 0.125 | Os resultados financeiros da Caixa Econômica Federal no período entre o repasse dos bancos e o depósito nas contas vinculadas destinar-se-ão à cobertura das despesas de administração do FGTS, conforme o art. 4º da Lei 8.036/1990. | Lei 8.036/1990 (FGTS), Art. 12 |
| adv-03 | contradiz | 0.999 | O empregado pode faltar até 5 dias consecutivos por causa do casamento sem perder o salário. | CLT, Art. 473 |
| adv-07 | contradiz | 0.874 | São acrescidos 5 dias de aviso prévio por ano de serviço na mesma empresa. | Lei 12.506/2011 (aviso prévio), Art. 1º |
| adv-15 | contradiz | 0.997 | Na dispensa sem justa causa, o empregador deposita no FGTS uma multa de 20% sobre os depósitos do contrato. | Lei 8.036/1990 (FGTS), Art. 18 |
| adv-17 | contradiz | 0.963 | Na primeira solicitação do seguro-desemprego, basta ter recebido salários em 6 dos últimos 12 meses. | Lei 7.998/1990 (seguro-desemprego), Art. 3º |
| adv-20 | contradiz | 0.874 | As gorjetas não fazem parte da remuneração do empregado. | CLT, Art. 457 |
| adv-35 | sustenta | 0.104 | A multa do art. 477 é devida mesmo quando o vínculo de emprego só foi reconhecido na Justiça. | Súmula 462 do TST |
