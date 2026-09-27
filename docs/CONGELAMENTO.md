# Congelamento das configurações para o conjunto de teste

> **Gerado por `python congelar.py`. Não editar à mão.** Rodar o
> script de novo e obter um diff significa que uma configuração mudou
> depois de congelada — nesse caso o congelamento é que está errado,
> não o script.

- Gerado em: 2026-09-27T01:36:51
- Commit que define estas configurações: `b68033d50796683143ae8c914af5732b56c2da52`
- Árvore suja na geração: **sim**

O conjunto de teste (60 excertos dos músicos 04 e 05) **não foi lido**
até este ponto. Toda a busca e todo o ajuste rodaram no split `val`
(120 excertos, músicos 00–03), como manda o `CLAUDE.md`. Este
documento existe para fixar o que vai ser medido **antes** de medir:
sem ele, qualquer escolha feita depois de ver o teste é ajuste
disfarçado de resultado.

## 1. As configurações

| Configuração | Motor | Vocabulário | Por que entra |
|---|---|---|---|
| `V4` | v4 | BASIC | baseline do projeto, intocado (`legacy_v4.py`). |
| `C` | cosseno | MEDIUM | melhor acerto no tempo rotulado (74,7 % em root), ao custo de abster-se em 39,5 % do tempo. |
| `D` | cosseno | MEDIUM | o pipeline com Viterbi sem absorção de segmentos curtos; melhor que E em todos os níveis na validação. |
| `E` | cosseno | MEDIUM | a configuração atual do sistema em produção. Entra para que o artigo reporte o que o Decifraê faz hoje, não só o melhor achado. |
| `F0rg` | cosseno | BASIC | melhor acerto sobre a faixa toda em root e sevenths (vocabulário BASIC, sem nenhuma fonte de N). |
| `D0rg` | cosseno | MEDIUM | melhor acerto sobre a faixa toda em majmin e mirex na camada chord[1] (vocabulário MEDIUM, sem nenhuma fonte de N). |

## 2. Campos pré-chroma

Etapa cara (HPSS, beat track, CQT). O `V4` não usa esta configuração:
tem o caminho próprio dele, com `margin=3.0` e `bins_per_octave=36`
literais dentro de `legacy_v4.run_beat_tracking`.

| Campo | `V4` | `C` | `D` | `E` | `F0rg` | `D0rg` |
|---|---|---|---|---|---|---|
| `sr` | — | 22050 | 22050 | 22050 | 22050 | 22050 |
| `method` | — | cqt | cqt | cqt | cqt | cqt |
| `smooth` | — | 21 | 21 | 21 | 21 | 21 |
| `hpss_margin` | — | 3.0 | 3.0 | 3.0 | 3.0 | 3.0 |
| `bins_per_octave` | — | 36 | 36 | 36 | 36 | 36 |

## 3. Campos pós-chroma

Etapa barata (gate de silêncio, emissão, Viterbi, merge, absorção).
Três destes campos configuram o **classificador**, não o `decode`:
`complexity_penalty`, `ext_sharpness` e `confidence_gate`.

| Campo | `V4` | `C` | `D` | `E` | `F0rg` | `D0rg` |
|---|---|---|---|---|---|---|
| `complexity_penalty` | — | 0.06 | 0.06 | 0.06 | 0.06 | 0.06 |
| `ext_sharpness` | — | 4.0 | 4.0 | 4.0 | 4.0 | 4.0 |
| `confidence_gate` | — | 0.72 | 0.72 | 0.72 | 0.72 | 0.72 |
| `use_viterbi` | — | False | True | True | True | True |
| `change_penalty` | — | 2.0 | 2.0 | 2.0 | 2.0 | 2.0 |
| `temp` | — | 0.1 | 0.1 | 0.1 | 0.1 | 0.1 |
| `n_logprob` | — | -2.5 | -2.5 | -2.5 | −1e9 | −1e9 |
| `rel_gate` | — | 0.2 | 0.2 | 0.2 | 0.0 | 0.0 |
| `abs_floor` | — | 0.0005 | 0.0005 | 0.0005 | 0.0005 | 0.0005 |
| `min_dur` | — | 0.0 | 0.0 | 0.8 | 0.0 | 0.0 |

## 4. O que NÃO foi ablacionado

Registrado para que a ausência seja uma decisão declarada e não um
esquecimento que um revisor descubra:

| Parâmetro | Valor fixo | Situação |
|---|---|---|
| `change_penalty` | 2.0 | **Nunca variado.** Nenhuma execução usou outro valor, nem na ablação nem nas curvas. Vem da calibração manual em `Musicas/` e entra no teste como constante, não como escolha justificada por dado. |
| `temp` | 0.1 | Nunca variado. |
| `ext_sharpness` | 4.0 | Nunca variado. Só tem efeito quando `complexity_penalty > 0`. |
| `abs_floor` | 5e-4 | Nunca variado. Responde pelos 0,25 % de tempo em N que sobram nas variantes `rg`. |
| `bins_per_octave` | 36 | Nunca variado. Ligado à configuração no T5, mas não varrido. |
| `hpss_margin` | 3.0 | Idem. |

## 5. Comparações pré-registradas

Os pares abaixo, e as métricas de cada um, foram fixados **antes** de
ler o conjunto de teste. Cada par isola uma etapa; a diferença
reportada é sempre `b − a`, positivo quando `b` é melhor. São os
mesmos pares que `stats.py` roda na validação — a lista vive em
`stats.PARES` e é importada por este script, para que o documento não
possa divergir do código.

Cada comparação traz: diferença média ponderada por duração, IC 95 %
por bootstrap pareado (10 000 reamostragens de faixas, semente 0),
Wilcoxon pareado e a contagem de faixas em que `b` ganha, perde ou
empata.

### 5.1 Critério de decisão

Declarado antes de ler o teste, para que a leitura não possa escolher
o critério que favorece a conclusão:

**(a) O critério PRINCIPAL é o IC 95 % do bootstrap pareado sobre a
média ponderada por duração.** O Wilcoxon pareado é SECUNDÁRIO: ele
complementa dizendo se a diferença é consistente faixa a faixa, e
nunca decide sozinho. Os dois medem coisas diferentes e podem
discordar — a média ponderada é dominada por faixas longas, o teste
de ranks conta faixas. Quando discordarem, ambos são reportados.

**(b) Os p-valores são corrigidos por Holm-Bonferroni sobre as
15 comparações desta tabela**, em duas famílias
separadas (uma para o bootstrap, uma para o Wilcoxon), com
α = 0.05. O p do bootstrap é o nível de significância
atingido: duas vezes a menor cauda da distribuição bootstrap em
relação a zero, com piso em 1/10 000.

**(c) Classificação de cada efeito:**

| Classe | Regra |
|---|---|
| `confirmado` | o IC 95 % exclui zero **e** o p de Holm do bootstrap < 0.05 |
| `empate` | o IC 95 % cruza zero — não há efeito distinguível de ruído |
| `fragil` | o IC 95 % exclui zero mas Holm não rejeita |

Um efeito `empate` **não** é descrito como ganho em nenhum texto do
artigo. Um efeito `fragil` é reportado com a ressalva explícita. A
classificação é calculada por `stats.classificar`, não atribuída à
mão.

| # | Par | Métricas | O que isola |
|---|---|---|---|
| 1 | `C` vs `D` | `root`, `root_rotulado` | o Viterbi na métrica usual |
| 2 | `C0rg` vs `D0rg` | `root`, `majmin` | o Viterbi com cobertura igualada (nenhuma fonte de N) |
| 3 | `D` vs `E` | `root`, `seg`, `overseg` | o trade-off do min_dur: acurácia contra segmentação |
| 4 | `V4b` vs `V4` | `root`, `overseg` | a inércia temporal do baseline |
| 5 | `V4` vs `F0rg` | `root`, `majmin`, `seg` | baseline contra a melhor variante |
| 6 | `D0rg` vs `F0rg` | `root`, `majmin`, `sevenths` | o vocabulário (MEDIUM vs BASIC) com cobertura igualada |

Nenhum par novo entra depois de o teste ser lido. Um par acrescentado
depois é análise exploratória e precisa ser reportado como tal.

## 6. Protocolo do teste

1. O split `test` é lido **uma única vez**, com
   `python runner.py --manifest data/manifests/guitarset_comping.csv`
   `--splits test --variants V4,C,D,E,F0rg,D0rg`.
2. As duas camadas de anotação (`--ref-layer 0` e `--ref-layer 1`) são
   reportadas. A camada principal é a `chord[1]`, conforme
   `docs/DATASETS.md` §2.
3. As duas faixas com timing incorreto seguem excluídas pelo manifest
   (`excluded=true`), então o teste tem 58 excertos pontuados de 60.
4. Nada é ajustado depois. Se o resultado do teste sugerir outra
   configuração, isso é trabalho para outro conjunto de dados, não
   uma revisão deste número.

