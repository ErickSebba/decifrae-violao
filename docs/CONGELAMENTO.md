# Congelamento das configurações para o conjunto de teste

> **Gerado por `python congelar.py`. Não editar à mão.** Rodar o
> script de novo e obter um diff significa que uma configuração mudou
> depois de congelada — nesse caso o congelamento é que está errado,
> não o script.

- Gerado em: 2026-09-26T01:52:28
- Commit que define estas configurações: `159993387b9a0c17a3830eaf9ce3b5e1885ec91c`
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

## 4. Protocolo do teste

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

