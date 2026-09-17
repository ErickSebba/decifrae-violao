# Changelog — progressão do módulo de acordes

Histórico reconstruído em 17/09/2026 a partir das datas de modificação dos
arquivos e do conteúdo de cada versão. Cada entrada corresponde a um commit
(datado com a data original) e a uma tag `vX.Y`. O código não foi alterado em
nenhum ponto; só o versionamento e a documentação são de 17/09.

## v0.1 — Baseline V4 (27/06/2026)

`legacy_v4.py` (então em `V1/`): o classificador original do decifrae,
preservado intacto para servir de referência.

- `classificar_segmento_v4`: chroma normalizado pelo máximo; score =
  Σ energia das notas do acorde − 0,6 · Σ energia das outras + bias 0,15;
  +0,5 se for o acorde anterior (inércia); −0,1 se o nome for mais longo que
  o anterior. Só maior/menor (sus2/sus4/7 comentados).
- `run_beat_tracking` / `run_onset_detection` / `run_agglomerative` +
  `comparar_metodos`: os três esquemas de segmentação comparados na época.

## v0.2 — Bench sintético v1 (27–28/06/2026, pasta `V1/`)

Primeira bancada modular, imports `from V1.x`. Removida do diretório em v1.0
(continua em `git show v0.2:V1/…`).

- `chord_templates.py`: 13 tipos de acorde, templates binários, subconjuntos.
- `classifier.py`: `CosineChordClassifier` com `confidence_gate=0.72`,
  `rms_gate=0.02` e **`complexity_penalty` linear** — `penalty · (n_notas − 3)`
  descontado do cosseno (o gate de confiança usava o cosseno cru).
- `synth.py`: série harmônica com `n_harmonics`, `decay`, `spread_octaves`, detune.
- `noise.py`: branco, rosa, detune, percussivo, reverb; `DEFAULT_CONDITIONS`.
- `bench.py` / `run_bench.py`: matriz de confusão por condição e por tipo,
  teste de pausa, varredura de harmônicos; cosseno vs V4.

## v0.3 — Layout flat, Viterbi, prior fixo (28/06/2026 18:28)

- Módulos copiados de `V1/` para a raiz com imports diretos.
- **`viterbi.py` novo**: decodificação HMM em log-espaço; softmax com
  temperatura nas emissões; estado N com log-prob base; transição
  `0` (manter) / `−change_penalty` (trocar), fixa; `force_n` para silêncio.
- **`classifier_V2.py`**: adiciona `emission()` (vetor de cosseno sem gate,
  usado como matriz de emissão) e troca a penalidade linear por um **prior
  fixo** `−complexity_penalty` para templates com ≥ 4 notas.
- `README.md`: documenta o bench e os 4 achados (cosseno escala p/ tétrades;
  ambiguidades são teóricas; gate N funciona; robusto a harmônicos).

## v0.4 — Pipeline beat-sync + viés adaptativo (28/06/2026 18:52)

- **`pipeline.py` novo**: `beat_sync_chroma` (HPSS uma vez → beat track no
  percussivo → CQT 36 bins no harmônico → median 21 → sync por batida) e
  `analyze_track` (RMS por segmento → gate relativo → emissões → Viterbi →
  merge → `_absorb_short`). Corrige o HPSS duplicado e os segmentos de 22 ms
  do `musicas.py` v1.
- **`classifier.py` (raiz)**: viés pró-tríade **adaptativo** — para cada
  tétrade guarda o índice da nota de extensão (maior intervalo ≥ 8); a
  penalidade é `complexity_penalty · max(0, 1 − ext_sharpness · energia_ext)`.
  Sétimas reais passam; flicker maj7 de corda solta é suprimido.
  A partir daqui há duas versões da classe: `classifier.py` (atual) e
  `classifier_V2.py` (anterior). `musicas.py` usa a atual; `pipeline.py`,
  `bench.py` e `run_bench.py` continuam importando `classifier_V2`.
- **`musicas.py` v2**: vocabulário MEDIUM, `complexity_penalty=0.06`,
  parâmetros no topo, timelines em `out/musicas/`.
- `bench.py`, `run_bench.py`: versões flat.
- `Musicas/`: Re_2, Sol_1, Tempo_Perdido, TrocaDeAcordes(C-G-A-F).
- Resultados qualitativos no README: Tempo_Perdido deixa de ser 100 % N.

## v0.5 — Port para a API (28/06/2026 20:50–21:00)

Pasta `Api/` = cópia do backend FastAPI:

- `audio_processing.py`: versão antiga em produção (V4 sem comentários).
- `audio_processing (1).py`: pipeline novo **standalone** (templates MEDIUM,
  cosseno adaptativo, Viterbi, gate relativo, `refinar_beat_tracking`),
  hiperparâmetros centralizados no topo, mesmo contrato `{chords, timestamps}`,
  omite N. `MIN_DUR=0.6` (bench usa 0.8).
- `main.py`: `/process-audio`, `/process-bass`, `/health`, `/_warmup`.
- `audio_processing_baixo.py`: módulo de baixo, dependência do `main.py`.

## v0.6 — Benchmark em áudio real com mir_eval (29/06/2026)

- **`evaluate.py` novo**: `score_segments` — tradução do vocabulário para
  mir_eval e acurácia ponderada por tempo em `root/majmin/sevenths/mirex`.
- **`benchmark_musicas.py` novo**: GT de Tempo Perdido (13 segmentos) e
  Boate Azul (76 segmentos), V4 vs atual, `comparativo.png` + `metrics.json`.
- `Musicas/Boate azul (Am) 2.mp3`.
- Resultado: Tempo Perdido root 78,8 → 98,2 %; Boate Azul root 84,7 → 94,1 %,
  majmin 63,0 → 90,6 %, sevenths 50,3 → 78,6 %.

## v1.0 — Versionamento e documentação (17/09/2026)

Sem alteração de código.

- Repositório git com os commits acima nas datas originais; tags `v0.1`–`v1.0`.
- Removidos do diretório (movidos para `../_removidos_de_DecifraViolao/`):
  `Baixo.rar` (módulo de baixo), `Controlador.ino` (PID de motor, outro
  projeto), `Musicas/Boate azul (Am).mp3` (versão antiga, não usada pelo
  benchmark) e sua timeline `out/musicas/Boate azul (Am)_timeline.png`.
- `V1/` removida do HEAD (preservada em v0.2).
- Bench sintético re-executado: gerados `out/{confusao_cosseno, confusao_v4,
  acuracia_cosseno, varredura_harmonicos}.png` e `out/logs/`.
- Benchmark de áudio real re-executado: `metrics.json` idêntico ao de 29/06.
- `docs/`: DOSSIE_TECNICO, TEMPLATES_ACORDES, HIPERPARAMETROS, GROUND_TRUTH,
  BENCHMARK, CHANGELOG. `README.md` reescrito como "como se roda hoje".
- `requirements.txt` e `.gitignore`.
