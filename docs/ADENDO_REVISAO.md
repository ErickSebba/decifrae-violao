# Adendo da revisão (camera-ready)

> Registro das configurações novas pedidas pelos revisores do ACDSA 2027.
> Não altera `docs/CONGELAMENTO.md` nem `docs/ADENDO_CONGELAMENTO.md`. Todos os
> valores abaixo foram escolhidos **só no split de validação** e este arquivo é
> commitado **antes** de qualquer execução das variantes novas no teste.
> Todas as análises desta fase são **pós-especificadas** (`post_review=true`
> no meta.json de cada CSV).

- Escrito em: 2026-11-16
- Branch: `revisao-camera-ready`
- Fonte de todos os números: `data/results/calibracao_revisao_20261116_231220.csv`
  (+ `_meta.json`), gerado por `calibracao_revisao.py`, split `val` (120 faixas,
  executantes 00–03), médias ponderadas pela duração da referência.
- Desempate fixado antes de rodar: menor |valor − default de `config.py`|,
  depois o menor valor. Não foi necessário em nenhuma das quatro escolhas.

## 1. Variantes fatoriais (sem escolha de valor)

Completam o fatorial 2×2×2 decodificador × abstenção própria × gate relativo.

| variante | definição em `runner.py` |
|---|---|
| `Crg` | C com `rel_gate = 0` (mantém `confidence_gate = 0,72`) |
| `Drg` | D com `rel_gate = 0` (mantém `n_logprob = −2,5`) |

As outras seis células (`C`, `C0`, `C0rg`, `D`, `D0`, `D0rg`) já existiam.

## 2. Cobertura igualada

Cobertura = 1 − fração do tempo estimada como `N` (independe da camada).
Na validação: cobertura de **C = 60,46 %**, de **D = 87,87 %**.

| variante | parâmetro varrido | grade | critério | valor escolhido | cobertura obtida | alvo |
|---|---|---|---|---|---|---|
| `Cmatch` | `confidence_gate` de C | 0,50…0,90, passo 0,01 | argmin \|cob(C,θ) − cob(D)\| | **θ\* = 0,65** | 88,45 % | 87,87 % |
| `Dmatch` | `n_logprob` de D | −1…−8, passo 0,25 | argmin \|cob(D,β) − cob(C)\| | **β\* = −2,25** | 66,42 % | 60,46 % |

Limitação registrada: a cobertura de D cai de forma íngreme entre β = −2,5
(87,87 %) e β = −2,0 (41,34 %); na grade pedida, o ponto mais próximo
(−2,25) fica 5,96 pontos acima do alvo. O casamento de C (0,58 ponto) é bem
mais fino que o de D. A grade **não** foi refinada depois de ver isso.

## 3. Penalidade de transição calibrada

`change_penalty` ∈ {0,5; 1; 1,5; 2; 2,5; 3; 4; 6}, critério: maior `root` na
faixa toda, camada chord[0] (a curva em chord[1] é idêntica no nível `root`
e escolheria o mesmo valor).

| cp | 0,5 | 1,0 | 1,5 | 2,0 | 2,5 | 3,0 | 4,0 | 6,0 |
|---|---|---|---|---|---|---|---|---|
| `D0rg` (60) root % | 66,40 | 66,59 | **66,78** | 65,80 | 64,69 | 63,43 | 60,66 | 53,93 |
| `F0rg` (24) root % | 70,47 | **70,52** | 70,25 | 69,15 | 68,27 | 67,02 | 63,98 | 56,75 |

| variante | definição | valor escolhido |
|---|---|---|
| `D0rg_cal` | D0rg com `change_penalty` calibrado | **1,5** |
| `F0rg_cal` | F0rg com `change_penalty` calibrado | **1,0** |

O default congelado (2,0) não era o ótimo em nenhum dos dois vocabulários; o
ganho na validação é de +0,98 (D0rg) e +1,37 (F0rg) ponto, e é ganho **dentro
da amostra** de calibração — só o teste o mede.

## 4. Execução prevista no teste (uma vez)

`runner.py --splits test --post-review` com `Crg, Drg, C0, D0, Cmatch, Dmatch,
D0rg_cal, F0rg_cal`, nas camadas chord[0] e chord[1], um commit entre as duas.
As mesmas seis variantes novas rodam também no val, nas duas camadas, antes do
teste. Nenhum valor deste adendo é revisto depois da leitura do teste.
