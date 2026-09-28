# Adendo ao congelamento

> Este documento **corrige o registro** de `docs/CONGELAMENTO.md` sem alterá-lo.
> O congelamento foi commitado antes da leitura do conjunto de teste, e é essa
> anterioridade que lhe dá valor; editá-lo depois a destruiria. As três
> correções abaixo ficam aqui, datadas e commitadas antes da execução que
> autorizam.

- Escrito em: 2026-09-27
- Congelamento corrigido: `docs/CONGELAMENTO.md`, commit `c4b4be2`
- Commit que define as configurações congeladas: `b68033d`

## 1. `C0rg` e `V4b` foram omitidas da §1 por erro

A §5 do congelamento pré-registrou seis pares de comparação. Os pares **2** e
**4** são:

| # | par | métricas | o que isola |
|---|---|---|---|
| 2 | `C0rg` vs `D0rg` | `root`, `majmin` | o Viterbi com cobertura igualada |
| 4 | `V4b` vs `V4` | `root`, `overseg` | a inércia temporal do baseline |

Eles exigem oito variantes, mas a §1 congelou seis: **`C0rg` e `V4b` ficaram
fora da lista**. A omissão é um erro de transcrição entre as duas seções do
mesmo documento, não uma decisão: nenhuma passagem do congelamento, nem do
`docs/DATASETS.md`, nem do `CLAUDE.md` justifica excluir do teste duas
variantes cujos pares estão pré-registrados.

Consequência da omissão na primeira execução do teste: 4 das 15 comparações
pré-registradas não foram avaliadas, e a família de Holm do teste ficou com 11
em vez de 15 — tornando os p ajustados do teste incomparáveis com os da
validação.

**Correção.** As duas variantes vão ao conjunto de teste, nas duas camadas, com
as configurações **inalteradas** desde `b68033d`. Verificado linha a linha
contra `git show b68033d:runner.py`:

```text
"C0rg": Variante("C0rg", PRE_CHROMA, replace(sem_gate, rel_gate=0.0))
"V4b":  Variante("V4b", motor="v4b", vocab="BASIC")
sem_gate = replace(com_bias, confidence_gate=0.0)
```

| campo | `C0rg` | `V4b` |
|---|---|---|
| motor | cosseno | v4b (cópia do V4 sem os dois termos temporais) |
| vocabulário | MEDIUM | BASIC |
| `complexity_penalty` | 0.06 | — |
| `ext_sharpness` | 4.0 | — |
| `confidence_gate` | **0.0** | — |
| `use_viterbi` | False | — |
| `change_penalty` | 2.0 | — |
| `temp` | 0.1 | — |
| `n_logprob` | −2.5 | — |
| `rel_gate` | **0.0** | — |
| `abs_floor` | 5e-4 | — |
| `min_dur` | 0.0 | — |
| pré-chroma | `sr` 22050, `cqt`, `smooth` 21, `hpss_margin` 3.0, `bins_per_octave` 36 | idem, via o caminho próprio do V4 |

Nenhum parâmetro foi escolhido, ajustado ou revisto após a leitura do teste.
Esta execução completa uma matriz pré-especificada; não acrescenta comparação
nova. As 15 comparações e suas métricas continuam exatamente as da §5.

## 2. A árvore estava suja na geração, e o commit veio 90 s depois

O congelamento registra "Árvore suja na geração: **sim**", o que enfraquece o
vínculo entre o commit citado e o conteúdo do documento. A cronologia, lida do
git:

| horário | evento |
|---|---|
| 01:30:18 | `b68033d` — commit que define as configurações |
| 01:36:51 | `congelar.py` gera o documento; a árvore continha as mudanças de `congelar.py` e `stats.py` ainda não commitadas |
| 01:38:13 | `c4b4be2` — o documento e essas mudanças são commitados juntos |
| 01:42:53 | primeira leitura do conjunto de teste (`ablation_20260927_014253_ref0`) |

A sujeira era o próprio código que gerou o documento, commitado **82 segundos
depois** da geração e **4min40s antes** da primeira leitura do teste. A
anterioridade do pré-registro está preservada, e é auditável pela ordem dos
commits: `c4b4be2` é ancestral de `f0b3d38` e `2c31006`.

## 3. O `N` residual de 0,25 % vem do `rel_gate`, não do `abs_floor`

A §4 do congelamento atribui ao piso absoluto de RMS (`abs_floor = 5e-4`) os
0,25 % de tempo rotulado como `N` que restam nas variantes sem outras fontes de
`N`. **A atribuição está errada.** Na validação:

| variante | `rel_gate` | `min_dur` | `N est` | faixas com `N > 0` |
|---|---:|---:|---:|---:|
| `C0`, `D0`, `F0` | 0,2 | 0,0 | 0,2458 % | 10 de 120 |
| `E0` | 0,2 | 0,8 | 0,0832 % | — |
| `C0rg`, `D0rg`, `E0rg`, `F0rg` | **0,0** | — | **0,0000 %** | **0 de 120** |
| `V4` | — | — | 0,0000 % | 0 de 120 |

As variantes com `rel_gate = 0` têm `frac_n_est` exatamente zero em todas as 120
faixas. Se a causa fosse o `abs_floor`, elas também exibiriam o resíduo, porque
nenhuma delas o altera. O responsável é o **gate relativo** de silêncio.

O `abs_floor` tem efeito, mas apenas no conjunto de teste e em **1 excerto de
58** (`frac_n_est` = 0,0154 % nessa faixa, 0 nas outras 57).

Esta correção não muda nenhuma configuração congelada nem nenhuma comparação:
afeta só a explicação do mecanismo. Ela está também registrada na §0 de
`artigo-ACDSA/RESULTADOS.md`.
