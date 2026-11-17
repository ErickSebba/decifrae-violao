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
| `D0rg` (60) root % | 66,39 | 66,59 | **66,78** | 65,80 | 64,69 | 63,43 | 60,66 | 53,93 |
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

## 5. Curvas de acerto × cobertura no teste (protocolo, 2026-11-17)

Registrado e commitado **antes** de rodar. Análise pós-especificada
(`post_review=true`), sem escolha de nenhum valor: não há calibração no teste.

- Script: `curvas_teste_revisao.py`; split `test` (58 faixas), camada chord[0],
  nível `root`.
- Curva C: variante C com `confidence_gate` ∈ {0} ∪ {0,50; 0,51; …; 0,90}.
- Curva D: variante D com `n_logprob` ∈ {−1; −1,25; …; −8} ∪ {−1e9}.
- Demais campos como em `runner.VARIANTES["C"]`/`["D"]` (inclusive
  `rel_gate = 0,2`).
- Por ponto e faixa: cobertura (1 − `frac_n_est`), `root_rotulado` e `root`
  na faixa toda. Agregação por ponto: média ponderada pela duração da faixa
  (`root_rotulado` exclui as faixas em que a cobertura é zero).
- Comparação na mesma cobertura: para cada curva, interpolação linear da
  métrica agregada em função da cobertura agregada (pontos ordenados por
  cobertura), nos alvos **60 %, 70 %, 77 % e 90 %**. Δ = D − C.
- IC 95 %: bootstrap pareado por faixa (10 000 reamostragens, seed 0); em
  cada reamostragem as duas curvas são reagregadas com os mesmos pesos e
  reinterpoladas. Alvo fora do intervalo de cobertura de uma curva numa
  reamostragem → reamostragem descartada para aquele alvo, e o número de
  reamostragens válidas é reportado.
- Saídas: `data/results/curvas_teste_<ts>.csv` (uma linha por curva, ponto e
  faixa), `data/results/cobertura_igualada_teste_<ts>.csv` (resumo),
  `artigo-ACDSA/tabelas/tab_cobertura_igualada.tex`,
  `artigo-ACDSA/figuras/fig_cobertura_teste.pdf/.png` (3,5 pol, fonte 8 pt).

## 6. Procedência das ablações de teste `20261116_231650` e `_231706` (2026-11-17)

As duas execuções únicas do teste pós-revisão gravaram `arvore_suja: true`.
Verificado depois, a partir do Git:

- `_231650_ref0` registra o commit `a380774`; `_231706_ref1`, o `b5065ef`. Entre
  os dois commits a única diferença é o próprio CSV/meta do chord[0]
  (`git diff --stat a380774 b5065ef`).
- Nenhum arquivo `.py` rastreado diferia do commit gravado: entre `a380774` e
  `bc001a8` os únicos `.py` que mudam são os quatro `analise_*.py`, **criados**
  depois das execuções e não importados por `runner.py`.
- O que sujava a árvore: (i) arquivos **não rastreados** do usuário
  (`artigo-ACDSA/slides-ACDSA/`, `artigo-ACDSA/slides-ACDSA.zip` e zips em
  `data/`), e (ii) uma alteração **rastreada e não commitada** do usuário em
  `artigo-ACDSA/RESULTADOS.md` (legendas de figuras), commitada só em
  `bc001a8`. Nenhum dos dois é lido pelo pipeline.

Conclusão: o código que produziu as duas ablações é exatamente o dos commits
gravados no meta. Os CSVs não foram regenerados, porque isso seria uma segunda
leitura do teste.
