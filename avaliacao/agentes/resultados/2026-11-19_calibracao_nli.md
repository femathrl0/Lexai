# Calibração do limiar do NLI — 19/11/2026

Modelo `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` · 105 pares de `avaliacao/pares_ouro/verificador_v1.jsonl` (68 sustenta, 24 contradiz, 13 nao_trata) · regra: menor limiar com precisão ≥ 0.9

**Limiar escolhido: 0.75** — precisão 0.875, recall 0.618 (antes, em 0,5: precisão 0.83, recall 0.647) — **nenhum limiar atingiu o portão; usado o de maior precisão**

| limiar | precisão | recall | F1 | falsas liberadas | boas barradas |
|---|---|---|---|---|---|
| 0.05 | 0.803 | 0.838 | 0.82 | 14 | 11 |
| 0.1 | 0.812 | 0.824 | 0.818 | 13 | 12 |
| 0.15 | 0.828 | 0.779 | 0.803 | 11 | 15 |
| 0.2 | 0.839 | 0.765 | 0.8 | 10 | 16 |
| 0.25 | 0.836 | 0.75 | 0.791 | 10 | 17 |
| 0.3 | 0.836 | 0.75 | 0.791 | 10 | 17 |
| 0.35 | 0.845 | 0.721 | 0.778 | 9 | 19 |
| 0.4 | 0.833 | 0.662 | 0.738 | 9 | 23 |
| 0.45 | 0.833 | 0.662 | 0.738 | 9 | 23 |
| 0.5 | 0.83 | 0.647 | 0.727 | 9 | 24 |
| 0.55 | 0.843 | 0.632 | 0.723 | 8 | 25 |
| 0.6 | 0.843 | 0.632 | 0.723 | 8 | 25 |
| 0.65 | 0.843 | 0.632 | 0.723 | 8 | 25 |
| 0.7 | 0.857 | 0.618 | 0.718 | 7 | 26 |
| 0.75 | 0.875 | 0.618 | 0.724 | 6 | 26 |
| 0.8 | 0.87 | 0.588 | 0.702 | 6 | 28 |
| 0.85 | 0.86 | 0.544 | 0.667 | 6 | 31 |
| 0.9 | 0.875 | 0.515 | 0.648 | 5 | 33 |
| 0.95 | 0.865 | 0.471 | 0.61 | 5 | 36 |

Só o NLI, sem as regras: em 0,5 precisão 0.772 / recall 0.647; no limiar escolhido precisão 0.84 / recall 0.618.

## Pares barrados pelas regras antes do NLI

| id | rótulo | motivo |
|---|---|---|
| adv-00 | contradiz | número ou prazo que não está no trecho: 10% |
| adv-01 | contradiz | número ou prazo que não está no trecho: 60 minutos |
| adv-06 | contradiz | número ou prazo que não está no trecho: 120 dias |
| adv-10 | contradiz | número ou prazo que não está no trecho: 50% |
| adv-16 | contradiz | número ou prazo que não está no trecho: trinta dias |
| adv-22 | contradiz | número ou prazo que não está no trecho: 180 dias |
| adv-23 | nao_trata | número ou prazo que não está no trecho: 30 dias |
| adv-25 | nao_trata | número ou prazo que não está no trecho: dois salarios |
| adv-26 | nao_trata | número ou prazo que não está no trecho: 40% |
| adv-27 | nao_trata | número ou prazo que não está no trecho: 21 horas |

## Por origem dos pares

| origem | n | precisão / recall no escolhido | em 0,5 |
|---|---|---|---|
| adversarial (escrita a partir do texto da fonte) | 38 | 0.6 / 0.75 | 0.462 / 0.75 |
| bateria 17/11 (frase real do sistema) | 67 | 0.947 / 0.6 | 0.95 / 0.633 |

## Erros no limiar escolhido

| id | rótulo | p(sustenta) | frase | fonte |
|---|---|---|---|---|
| bat17-00 | sustenta | 0.003 | O art. 60 da CLT diz que, para aumentar o horário de trabalho em atividades insalubres, é preciso pedir autorização antes das autoridades competentes. | CLT, Art. 60 |
| bat17-01 | sustenta | 0.006 | A exceção é que, quando a jornada é de 12 horas de trabalho e 36 horas de descanso seguidas, não é preciso pedir autorização antes. | CLT, Art. 60 |
| bat17-02 | sustenta | 0.002 | O art. 60 da CLT diz que, para aumentar o tempo de trabalho em atividades insalubres, é preciso pedir autorização das autoridades responsáveis por saúde no trabalho. | CLT, Art. 60 |
| bat17-06 | sustenta | 0.003 | O art. 462 também proíbe que as empresas restringam a liberdade dos funcionários de usar o seu salário como quiserem. | CLT, Art. 462 |
| bat17-09 | sustenta | 0.006 | O art. 462 também proíbe que as empresas obriguem os funcionários a usar o seu salário de uma forma específica. | CLT, Art. 462 |
| bat17-10 | sustenta | 0.333 | A remuneração do trabalho noturno urbano é maior em 20% do que a do diurno, conforme o CLT, Art. 73. | CLT, Art. 73 |
| bat17-12 | sustenta | 0.002 | O acréscimo de 20% é calculado sobre a hora diurna, conforme a LC 150/2015, Art. 14, § 2º. | LC 150/2015 (doméstico), Art. 14 |
| bat17-14 | sustenta | 0.396 | O trabalho noturno urbano é considerado aquele executado entre as 22 horas de um dia e as 5 horas do dia seguinte, conforme o CLT, Art. 73, § 2º. | CLT, Art. 73 |
| bat17-19 | sustenta | 0.192 | O tempo de serviço efetivo também conta quando o trabalhador estiver fora do trabalho por motivo de serviço militar ou acidente do trabalho. | CLT, Art. 4º |
| bat17-20 | contradiz | 0.996 | O tempo que passa além da jornada normal, mesmo que seja um pouco mais, não é considerado hora extra, a menos que haja uma regra específica. | CLT, Art. 4º |
| bat17-22 | sustenta | 0.455 | O tempo de serviço efetivo também conta quando o trabalhador estiver afastado por serviço militar ou acidente do trabalho. | CLT, Art. 4º |
| bat17-35 | sustenta | 0.007 | O empregado pode ficar ausente nos dias em que tiver que fazer provas do vestibular para entrar em faculdade. | CLT, Art. 473 |
| bat17-36 | sustenta | 0.355 | O empregado pode ficar ausente pelo tempo necessário se estiver participando de reunião oficial de órgão internacional em que o Brasil participe, na qualidade de representante de sindicato. | CLT, Art. 473 |
| bat17-37 | sustenta | 0.538 | O empregado pode ficar ausente pelo tempo necessário para acompanhar a esposa ou companheira em até 6 consultas médicas ou exames durante a gravidez. | CLT, Art. 473 |
| bat17-45 | sustenta | 0.005 | O empregado pode ficar ausente nos dias em que estiver fazendo provas do vestibular para entrar em faculdade. | CLT, Art. 473 |
| bat17-46 | sustenta | 0.137 | O empregado pode ficar ausente pelo tempo que precisar, se estiver participando de reunião oficial de organismo internacional em que o Brasil participe, na qualidade de representante de sindicato. | CLT, Art. 473 |
| bat17-47 | sustenta | 0.376 | O empregado pode ficar ausente para acompanhar sua esposa ou companheira em até 6 consultas médicas ou exames durante a gravidez. | CLT, Art. 473 |
| bat17-48 | sustenta | 0.362 | O empregado pode ficar ausente pelo tempo necessário para acompanhar sua esposa ou companheira em até 6 consultas médicas ou em exames complementares durante o período de gravidez. | CLT, Art. 473 |
| bat17-51 | sustenta | 0.656 | O seguro-desemprego para empregados domésticos demitidos sem justa causa tem valor de 1 salário-mínimo, por até 3 meses, conforme o Art. 26 da LC 150/2015. | LC 150/2015 (doméstico), Art. 26 |
| bat17-54 | sustenta | 0.001 | A falta de aviso prévio por parte do empregador dá ao empregado o direito aos salários correspondentes ao prazo do aviso. | LC 150/2015 (doméstico), Art. 23 |
| bat17-55 | sustenta | 0.002 | A falta de aviso prévio por parte do empregador dá ao empregado o direito aos salários correspondentes ao prazo do aviso, garantida sempre a integração desse período ao seu tempo de serviço. | LC 150/2015 (doméstico), Art. 23 |
| bat17-56 | nao_trata | 0.984 | A mulher grávida pode parar de trabalhar se o emprego prejudicar a gravidez, conforme o Art. 394 da CLT. | CLT, Art. 394 |
| bat17-61 | sustenta | 0.004 | A notificação do empregador relativa aos débitos com o FGTS interrompe o prazo prescricional, conforme o art. 23-A, § 1º, da Lei 8.036/1990. | Lei 8.036/1990 (FGTS), Art. 23-A |
| bat17-62 | sustenta | 0.132 | Os resultados financeiros da Caixa Econômica Federal no período entre o repasse dos bancos e o depósito nas contas vinculadas destinar-se-ão à cobertura das despesas de administração do FGTS, conforme o art. 4º da Lei 8.036/1990. | Lei 8.036/1990 (FGTS), Art. 12 |
| bat17-63 | sustenta | 0.246 | A Caixa Econômica Federal passa a gerenciar as contas do FGTS (Fundo de Garantia do Tempo de Serviço) dentro de um ano, a partir da promulgação da Lei 8.036/1990, conforme o art. 12, caput, da mesma lei. | Lei 8.036/1990 (FGTS), Art. 12 |
| bat17-65 | sustenta | 0.303 | A conta vinculada será transferida para o banco escolhido pelo novo empregador, até que a centralização prevista no art. 12 seja concluída. | Lei 8.036/1990 (FGTS), Art. 12 |
| adv-03 | contradiz | 0.999 | O empregado pode faltar até 5 dias consecutivos por causa do casamento sem perder o salário. | CLT, Art. 473 |
| adv-05 | contradiz | 0.997 | O empregado pode faltar um dia a cada 6 meses para doar sangue. | CLT, Art. 473 |
| adv-07 | contradiz | 0.875 | São acrescidos 5 dias de aviso prévio por ano de serviço na mesma empresa. | Lei 12.506/2011 (aviso prévio), Art. 1º |
| adv-17 | contradiz | 0.962 | Na primeira solicitação do seguro-desemprego, basta ter recebido salários em 6 dos últimos 12 meses. | Lei 7.998/1990 (seguro-desemprego), Art. 3º |
| adv-30 | sustenta | 0.056 | Na dispensa sem justa causa, o empregador deposita no FGTS 40% de todos os depósitos feitos durante o contrato. | Lei 8.036/1990 (FGTS), Art. 18 |
| adv-35 | sustenta | 0.111 | A multa do art. 477 é devida mesmo quando o vínculo de emprego só foi reconhecido na Justiça. | Súmula 462 do TST |
