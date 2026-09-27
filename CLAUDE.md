# CLAUDE.md — DecifraViolão (módulo de reconhecimento de acordes)

Contrato de trabalho neste repositório. Leia antes de qualquer alteração.

## Contexto

Módulo de reconhecimento de acordes da plataforma Decifraê. Recebe áudio de
violão (mono, 22 050 Hz) e devolve segmentos `{start, end, label}`, onde
`label` é um acorde do vocabulário MEDIUM (60 nomes) ou `N` (sem acorde).

O objetivo **atual** do repositório é dar suporte a um artigo científico: um
estudo de ablação das etapas do pipeline e uma calibração automática dos
hiperparâmetros, avaliados no GuitarSet e no IDMT-SMT-Chords. O prazo é curto.
Isso muda as prioridades: **estabilidade de comportamento vale mais que
elegância de código**.

Documentação de referência em `docs/`: `DOSSIE_TECNICO.md` (arquitetura e
decisões), `TEMPLATES_ACORDES.md` (os 60 templates), `HIPERPARAMETROS.md`
(todos os valores e onde vivem), `GROUND_TRUTH.md` (anotações), `BENCHMARK.md`
(os dois benchmarks), `CHANGELOG.md` (histórico).

## Regra de ouro: o oráculo de regressão

O pipeline é determinístico. `out/musicas_bench/metrics.json` está commitado e
é o oráculo: enquanto o comportamento não muda de propósito, ele tem de sair
idêntico.

```bash
python benchmark_musicas.py
git diff --exit-code out/musicas_bench/metrics.json   # 0 = sem regressão
```

- **Toda refatoração desta fase é neutra em comportamento.** Mover módulos,
  unificar classes duplicadas, centralizar constantes, separar funções:
  o diff tem de ser vazio. Diff não vazio = a mudança está errada. Não é
  arredondamento, não é "provavelmente tudo bem".
- Se o diff aparecer, **reverta e investigue**; não ajuste o oráculo para
  fechar a conta.
- O oráculo só é regenerado quando uma mudança de hiperparâmetro ou de
  algoritmo é intencional, e no mesmo commit que a introduz.
- Um commit por tarefa, com o oráculo verificado antes de commitar.

## Mapa dos módulos

Núcleo (importável, layout plano na raiz, sem pacote):

| Módulo | Papel |
|---|---|
| `chord_templates.py` | 13 tipos de acorde, `build_templates`, subconjuntos (`BASIC`, `MEDIUM`, `TRIADS`, `TETRADS`) |
| `classifier.py` | `CosineChordClassifier` — versão **atual**, com viés pró-tríade adaptativo (`ext_sharpness`) |
| `classifier_V2.py` | Mesma classe, versão **anterior** (prior fixo). O nome está invertido; ver `DOSSIE_TECNICO.md` §4.1 |
| `viterbi.py` | Decodificação HMM em log-espaço, 61 estados (60 acordes + N) |
| `pipeline.py` | `beat_sync_chroma` (HPSS → beat track → CQT → mediana → sync) e `analyze_track` |
| `evaluate.py` | `score_segments` — tradução para mir_eval e acurácia ponderada por tempo |
| `legacy_v4.py` | Baseline V4. **Não editar, por decisão de projeto.** |

Entry points: `musicas.py`, `benchmark_musicas.py`, `run_bench.py`.
Bench sintético: `synth.py`, `noise.py`, `bench.py`.

Todos os scripts rodam **de dentro da pasta** (imports absolutos por nome de
arquivo, sem `__init__.py`).

## Hiperparâmetros: pré-chroma e pós-chroma

Distinção central para os experimentos. Ver `docs/HIPERPARAMETROS.md` para
valores, faixas e efeitos.

- **Pré-chroma (caros — exigem recalcular HPSS, beat track e CQT):**
  `SR`, `METHOD`, `SMOOTH`, `margin` do HPSS, `bins_per_octave`.
- **Pós-chroma (baratos — operam sobre o chroma já sincronizado):**
  `COMPLEXITY_PENALTY`, `EXT_SHARPNESS`, `CHANGE_PENALTY`, `TEMP`,
  `N_LOGPROB`, `REL_GATE`, `MIN_DUR`.

Sete dos oito parâmetros do espaço de busca são pós-chroma. Por isso o
pipeline será separado em extração (cacheável) e decisão (barata), e a busca
roda sobre o cache.

Hoje os mesmos valores aparecem em quatro lugares (`musicas.py`,
`benchmark_musicas.py`, defaults de `pipeline.py`/`classifier.py`, e a cópia da
API). Centralizar isso é tarefa explícita, não iniciativa própria.

## Vocabulário

`MEDIUM` = 60 templates: maior, menor, `7`, `maj7`, `m7` × 12 tônicas.
Nomes só com sustenidos (`A#`, nunca `Bb`). Sufixo vazio = maior.
A ordem de `build_templates(MEDIUM)` é a ordem das colunas da matriz de
emissão; a coluna 60 é o estado `N`, adicionado por `viterbi.decode`.

Ao mexer em `chord_templates.py`, `evaluate.py::_QUALITY_MAP` precisa da
tradução do novo sufixo, senão o rótulo vira `'X'` e o mir_eval o ignora.

## Fora de escopo nesta fase

Não trabalhe nestes itens sem pedido explícito:

- `Api/` — a cópia standalone não entra no artigo. Não sincronizar, não
  refatorar, não importar.
- `legacy_v4.py` — baseline intocável.
- Transformar o projeto em pacote Python (`pyproject.toml`, `__init__.py`,
  ajuste de imports em massa).
- Bench sintético como resultado principal — as "confusões" que ele reporta
  são empates teóricos entre templates idênticos, não erros.
- Áudio de `Musicas/` — são gravações comerciais; não commitar, não
  redistribuir. As anotações de ground truth são do projeto e ficam.

## Convenções dos experimentos

- Um CSV por experimento, em `out/experiments/`, **nunca sobrescrito**.
  Uma linha por faixa, com as colunas de configuração repetidas na linha.
- Nenhum número do artigo é digitado à mão: tabelas e figuras saem de script
  lendo os CSVs.
- Seeds fixas e registradas em qualquer processo estocástico.
- Busca e ajuste rodam **apenas** no split de validação. O conjunto de teste é
  lido uma única vez, no fim. Um script de busca que abre faixa de teste é bug.
- Faixas, splits e exclusões vivem em `docs/DATASETS.md` — não hardcodar
  listas de faixas em script.

## Sub-agentes

- Use sub-agentes **em paralelo** quando as tarefas forem independentes.
- Só a sessão principal executa `runner.py` e faz commits. Sub-agentes escrevem
  apenas nos arquivos que lhes forem atribuídos e **não commitam**.
- Nenhum sub-agente lê o split `test` antes de o CSV do teste estar commitado
  pela sessão principal.

## Entregáveis do artigo

- Resultados validados são commitados em `artigo-ACDSA/` assim que ficam
  prontos, com as figuras e dois arquivos: `METODOLOGIA.md` e `RESULTADOS.md`.
- Todo número em `artigo-ACDSA/` sai de um CSV em `data/results/`, com a origem
  indicada.

## Estilo

- Português nos comentários e na documentação, como o resto do repositório.
- Mudanças mínimas: não reformatar arquivo inteiro, não renomear o que não foi
  pedido, não "melhorar de passagem".
- Se uma tarefa parecer exigir mudar comportamento, **pare e pergunte** antes
  de escrever código.
