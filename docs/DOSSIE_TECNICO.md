# Dossiê técnico — módulo de reconhecimento de acordes (DecifraViolão)

> Referência central do módulo. Escrito a partir do código como ele está em
> 17/09/2026 (commit `docs`), sem alterar nenhuma linha de código. Onde o
> código tem inconsistências, elas estão registradas aqui em vez de corrigidas.

Documentos complementares em `docs/`:

| Arquivo | Conteúdo |
|---|---|
| [TEMPLATES_ACORDES.md](TEMPLATES_ACORDES.md) | Os 13 tipos de acorde, o vocabulário MEDIUM (60 templates) e as ambiguidades harmônicas |
| [HIPERPARAMETROS.md](HIPERPARAMETROS.md) | Todos os hiperparâmetros, onde cada um vive, valor em cada lugar, efeito |
| [GROUND_TRUTH.md](GROUND_TRUTH.md) | Anotações de Tempo Perdido e Boate Azul, formato, como anotar novas faixas |
| [BENCHMARK.md](BENCHMARK.md) | Os dois benchmarks, como rodar, saídas brutas atuais, uso como regressão |
| [CHANGELOG.md](CHANGELOG.md) | Progressão do código (V4 → cosseno → Viterbi → beat-sync → API → mir_eval) |

---

## 1. O que o módulo faz

Recebe um arquivo de áudio de violão (mono, 22 050 Hz) e devolve uma sequência
de segmentos `{start, end, label}` onde `label` é um nome de acorde
(`C`, `Am`, `E7`, `Bmaj7`, `Dm7`…) ou `N` (sem acorde / silêncio).

Fluxo (função `analyze_track` em `pipeline.py`):

```
áudio y (22050 Hz, mono)
  │
  ├─ librosa.effects.hpss(margin=3.0) ──► y_harmonic, y_percussive
  │
  ├─ beat_track(y_percussive) ──────────► batidas (bordas dos segmentos)
  │
  ├─ chroma_cqt(y_harmonic, bins_per_octave=36) ──► chroma 12×T
  ├─ median_filter temporal (janela 21)
  ├─ sync por batida (agregação = mediana) ─────► chroma 12×n_beats
  │
  ├─ RMS por segmento ──► gate RELATIVO: silêncio = RMS < rel_gate·mediana
  │                        (piso absoluto abs_floor) ──► force_n[i]
  │
  ├─ classifier.emission(chroma[:, i]) ──► cosseno vs 60 templates
  │       (+ viés pró-tríade adaptativo)      = matriz de emissão n_beats×60
  │
  ├─ viterbi.decode(emissions, force_n) ──► rótulo por batida (61 estados: 60 + N)
  │
  ├─ _merge: funde vizinhos iguais
  └─ _absorb_short: segmentos < min_dur herdam o rótulo do vizinho mais longo
```

O mesmo fluxo existe em **duas implementações** (ver §4):

1. **Módulos do bench** (`pipeline.py` + `classifier.py` + `viterbi.py` +
   `chord_templates.py`) — usados por `musicas.py` e `benchmark_musicas.py`.
2. **Cópia standalone para a API** (`Api/audio_processing (1).py`) — tudo em
   um arquivo, sem depender dos módulos acima, com o contrato de saída da
   produção (`{"chords": [...], "timestamps": [{start, end, chord}]}`).

---

## 2. Módulos e responsabilidades

### 2.1 Núcleo (importável)

| Módulo | Expõe | Depende de |
|---|---|---|
| `chord_templates.py` | `NOTE_NAMES`, `CHORD_TYPES` (13 tipos), `TRIADS`, `TETRADS`, `BASIC`, `MEDIUM`, `build_templates(suffixes)`, `template_vector`, `chord_pitch_classes`, `chord_name` | numpy |
| `classifier.py` | `CosineChordClassifier` (`emission`, `classify_vector`, `classify_audio`), `extract_chroma`, `chroma_vector`, `NO_CHORD` | chord_templates, librosa, scipy |
| `classifier_V2.py` | Mesma API, **versão anterior** (prior fixo, sem `ext_sharpness`) — ver §4.1 | chord_templates, librosa, scipy |
| `viterbi.py` | `decode(emissions, names, change_penalty, temp, n_logprob, force_n)`, `NO_CHORD` | numpy |
| `pipeline.py` | `beat_sync_chroma`, `analyze_track`, `_merge`, `_absorb_short` | classifier_V2 (só `NO_CHORD`), viterbi, librosa, scipy |
| `evaluate.py` | `score_segments(est, ref, levels)` → dict de acurácias mir_eval | mir_eval |

### 2.2 Baseline

| Módulo | Expõe |
|---|---|
| `legacy_v4.py` | `classificar_segmento_v4(chroma, acorde_anterior)` (energia útil − 0,6·ruído + bias 0,15 + inércia +0,5; só maior/menor), `run_beat_tracking`, `run_onset_detection`, `run_agglomerative`, `comparar_metodos`. **Intocado por decisão de projeto** — é o baseline de todos os benchmarks. |

### 2.3 Bench sintético

| Módulo | Expõe |
|---|---|
| `synth.py` | `synth_chord(root_pc, suffix, sr, dur, base_octave, n_harmonics, decay, spread_octaves, detune_cents, normalize)`, `synth_pause`, `midi_to_freq`, `pc_to_midi`. Síntese por série harmônica (não senóide pura — o 7º harmônico é o que confunde maj com 7). |
| `noise.py` | `add_white_noise`, `add_pink_noise`, `detune`, `add_percussive`, `reverb_tail`, `apply_condition`, `DEFAULT_CONDITIONS` (9 condições). |
| `bench.py` | `run_bench(classify_fn, …)`, `accuracy_table`, `top_confusions`, `confusion_by_type`, `pause_test`, `harmonic_sweep`, `plot_*`. Agnóstico ao classificador. |
| `run_bench.py` | Entry point: cosseno vs V4 nas 3 baterias. `QUICK=True` (4 raízes, sem detune). |

### 2.4 Scripts sobre áudio real

| Script | Faz |
|---|---|
| `musicas.py` | Roda `analyze_track` em todos os áudios de `Musicas/`, imprime segmentos e salva `out/musicas/<faixa>_timeline.png`. |
| `benchmark_musicas.py` | Ground truth de Tempo Perdido e Boate Azul embutido; roda V4 e pipeline atual; pontua com `evaluate.score_segments`; salva `out/musicas_bench/{comparativo.png, metrics.json}`. |

### 2.5 API (cópia do backend)

| Arquivo | Estado |
|---|---|
| `Api/main.py` | FastAPI: `POST /process-audio` → `detectar_acordes`; `POST /process-bass` → `pipeline_completo`; `/health`; `/_warmup`. Importa `app.audio_processing` e `app.audio_processing_baixo` (pacote `app/` do backend, não desta pasta). |
| `Api/audio_processing.py` | Versão **antiga** em produção: `classificar_segmento` (o V4 sem os comentários), `refinar_beat_tracking`, `detectar_acordes`. |
| `Api/audio_processing (1).py` | Versão **nova**, standalone: templates MEDIUM, `_CosineClassifier` com viés adaptativo, `_viterbi_decode`, gate relativo. Substitui a antiga mantendo `detectar_acordes` e `refinar_beat_tracking` com o mesmo contrato. **É o arquivo a copiar para `app/audio_processing.py` no backend.** |
| `Api/audio_processing_baixo.py` | Módulo de baixo (pYIN + DP + tablatura). Fora do escopo de acordes; está aqui porque `main.py` importa. |

---

## 3. Decisões técnicas e por quê

| Decisão | Motivo (do código/README) |
|---|---|
| **Cosseno em vez de soma de energia** | O cosseno é auto-normalizado pela norma do template (√3 vs √4): uma tétrade só vence se houver energia real na 4ª nota. Elimina o viés que fazia Cmaj virar C7 e dispensa bias manual por tipo. Escala para qualquer tipo em `CHORD_TYPES` sem re-tunar. |
| **Templates binários** | Cada tipo é uma lista de intervalos; o template é o vetor 12-dim com 1 nas pitch-classes. Adicionar um acorde = uma linha em `CHORD_TYPES`. |
| **Vocabulário MEDIUM (60)** | maior, menor, 7, maj7, m7 × 12 tônicas. "Bom equilíbrio p/ violão". Sem ambiguidades internas (nenhum par de templates iguais). |
| **Beat-sync** | Chroma extraído uma vez no áudio inteiro e agregado por batida (mediana). Segmentos estáveis (~0,85 s). Corrigiu os segmentos de ~22 ms e os avisos `n_fft too large` do `musicas.py` v1. Mesmo esquema do V4. |
| **HPSS antes do chroma** | Chroma do componente harmônico; beat tracking do percussivo. `margin=3.0`. Um único HPSS por faixa (o v1 fazia dois). |
| **CQT com 36 bins/oitava + median filter 21** | Resolução de 1/3 de semitom, suaviza flicker frame-a-frame. |
| **Viterbi com penalidade de troca FIXA** | Custo de trocar de estado é `-change_penalty` (log), não dividido por n_estados. Com matriz estocástica normalizada, o acorde ficava "preso" ao crescer o vocabulário. Independe de 24 ou 156 acordes. |
| **Estado N como coluna extra com log-prob base** | `n_logprob = -2.5`. N vence quando nenhum acorde casa bem, sem depender do gate fixo de 0,72 (que marcava Tempo Perdido 100 % N). |
| **Gate de silêncio RELATIVO** | `RMS < rel_gate · mediana(RMS dos segmentos)`. Gravações baixas (Tempo Perdido, RMS ≈ 0,01) não viram silêncio. `abs_floor = 5e-4` pega silêncio digital. |
| **Viés pró-tríade adaptativo** | `complexity_penalty = 0.06` desconta do cosseno das tétrades **apenas** quando a nota de extensão (6ª/7ª) está fraca no chroma: `fator = max(0, 1 − ext_sharpness · energia_ext)`. Suprime o flicker maj7/7 de cordas soltas ressoando, mas deixa passar E7/A7 reais da Boate Azul. |
| **Absorção de segmentos curtos** | `min_dur = 0.8 s`: um segmento curto herda o rótulo do vizinho mais longo, iterando até estabilizar. Remove blips de transição. |
| **V4 preservado intacto** | Baseline em todos os benchmarks. Não editar. |

---

## 4. Estado atual: inconsistências e pontos abertos

Nada abaixo foi alterado — está registrado para orientar a refatoração.

### 4.1 `classifier.py` vs `classifier_V2.py` (naming invertido)

- `classifier_V2.py` (28/06 18:28) é a versão **anterior**: prior fixo
  `-complexity_penalty` para todo template com ≥ 4 notas.
- `classifier.py` (28/06 18:51) é a versão **atual**: viés adaptativo com
  `ext_idx`/`ext_sharpness`.
- Quem importa o quê:

| Importa `classifier` (atual) | Importa `classifier_V2` (anterior) |
|---|---|
| `musicas.py`, `benchmark_musicas.py` | `pipeline.py` (só `NO_CHORD`), `bench.py` (só `NO_CHORD`), `run_bench.py` (`CosineChordClassifier`, `chroma_vector`, `NO_CHORD`) |

Consequência prática: o **bench sintético mede `classifier_V2`** com
`complexity_penalty=0` (default) — ou seja, cosseno puro; as duas versões são
idênticas nesse regime. O **pipeline real mede `classifier`** com
`complexity_penalty=0.06`. Não há divergência de resultado hoje, mas há dois
arquivos com a mesma classe.

### 4.2 Pacote importável ou script?

**Importável, mas sem pacote.** Os módulos são planos na raiz, sem
`__init__.py`, sem `setup.py`/`pyproject.toml`, e os imports são absolutos por
nome de arquivo (`from classifier import …`). Funciona só com a raiz no
`sys.path` (rodar de dentro da pasta). Os entry points (`musicas.py`,
`run_bench.py`, `benchmark_musicas.py`) são scripts com constantes no topo.

A cópia da API (`Api/audio_processing (1).py`) é 100 % standalone e **duplica**
`chord_templates` (só MEDIUM), a classe do classificador, o softmax, o Viterbi
e o merge — ~230 linhas que precisariam ser mantidas em sincronia com os
módulos do bench.

Tamanho da refatoração para virar pacote: mover os 6 módulos do núcleo para
`decifra_acordes/` com `__init__.py`, ajustar ~12 linhas de import nos scripts,
e fazer a API importar o pacote em vez da cópia. Mover os `.py` sem ajustar os
imports quebra tudo — por isso este trabalho de organização deixou o layout
flat.

### 4.3 Hiperparâmetros espalhados

Os mesmos valores aparecem em 4 lugares (detalhe em
[HIPERPARAMETROS.md](HIPERPARAMETROS.md)):

1. Constantes no topo de `musicas.py` (fonte "oficial" hoje).
2. Chamada em `benchmark_musicas.py::run_atual` (subconjunto, restante cai nos defaults).
3. Defaults de `analyze_track` em `pipeline.py` e de `CosineChordClassifier.__init__`.
4. Constantes no topo de `Api/audio_processing (1).py`.

Divergências conhecidas: `MIN_DUR` = 0,8 (musicas/benchmark/pipeline) vs
**0,6** (API); `rms_gate=0.02` passado em `musicas.py` mas não usado por
`analyze_track` (só `classify_audio` usa); `confidence_gate=0.72` é ignorado
pelo pipeline com Viterbi (só `classify_vector` usa).

### 4.4 Saída do pipeline vs contrato da API

- `analyze_track` devolve `[{'start','end','label'}]` **incluindo** segmentos `N`.
- `detectar_acordes` (API) devolve `{"chords", "timestamps":[{start,end,chord}]}` **omitindo** `N`, com `round(…, 2)`, e usa `refinar_beat_tracking` (absorve o curto **no anterior**, sem iterar) em vez de `_absorb_short` (absorve no vizinho **mais longo**, iterando). Os dois podem divergir em bordas de transição.

### 4.5 `Musicas/` e `out/`

- `musicas.py` processa toda a pasta; `benchmark_musicas.py` só as duas faixas com GT.
- `out/musicas/*.png` foram gerados em 28/06 (antes da versão final do GT). Não são entrada de nada.
- Os `.png` do bench sintético (`out/confusao_*.png`, `acuracia_cosseno.png`, `harmonicos.png`) não estavam no disco quando o repositório foi criado — foram regenerados em 17/09 (ver [BENCHMARK.md](BENCHMARK.md)).

### 4.6 Dependências não declaradas

Não havia `requirements.txt`; o README listava `librosa numpy scipy scikit-learn matplotlib soundfile` e `evaluate.py` adicionou `mir_eval`. `scikit-learn` e `soundfile` não são importados por nenhum módulo (soundfile é backend implícito do librosa). Criado `requirements.txt` na raiz com o que é realmente importado.

---

## 5. Resultados registrados

### 5.1 Áudio real (`out/musicas_bench/metrics.json`, 29/06/2026)

| Faixa | Nível | V4 | Atual | Δ |
|---|---|---:|---:|---:|
| Tempo_Perdido | root / majmin / sevenths / mirex | 78,8 % | 98,2 % | +19,4 |
| Boate_azul (Am) 2 | root | 84,7 % | 94,1 % | +9,4 |
| | majmin | 63,0 % | 90,6 % | +27,6 |
| | sevenths | 50,3 % | 78,6 % | +28,3 |
| | mirex | 63,0 % | 90,6 % | +27,6 |

Tempo Perdido tem os 4 níveis iguais porque o GT só contém tríades.

### 5.2 Bench sintético (do README, 28/06)

1. Cosseno acerta 7, maj7, m7, m6, dim, sus2 a 100 % sem bias; V4 devolve tríade em qualquer tétrade.
2. Ambiguidades são teóricas, não bugs: `Csus4 = Fsus2`, `C6 = Am7`, `Cm7b5 = Ebm6`; `aug` ~33 %, `dim7` ~25 % (fator de simetria). Nenhuma dentro de MEDIUM.
3. Gate N: 0 % de falso-positivo em pausas com ruído; V4 alucina a partir de ruído 0,02 (~37 %) e 100 % em 0,05.
4. Varredura de 1 a 12 harmônicos: cosseno mantém 100 % em maj/m/7/maj7.

### 5.3 Observações qualitativas (README)

- Tempo_Perdido: N (intro) + três ciclos limpos de C Am Bm Em (antes: 100 % N).
- Sol_1: N + G limpo. TrocaDeAcordes: C G A F na ordem, resíduos ~0,9 s nas trocas.

---

## 6. Como rodar hoje

```bash
pip install -r requirements.txt
python musicas.py             # Musicas/ -> out/musicas/*.png + segmentos no terminal
python benchmark_musicas.py   # V4 vs atual em Tempo Perdido e Boate Azul -> out/musicas_bench/
python run_bench.py           # bench sintético cosseno vs V4 -> out/*.png
python evaluate.py            # sanity check do mir_eval
python pipeline.py            # smoke test com faixa sintética C-G-Am
```

Todos devem ser executados **de dentro da pasta** (imports absolutos por nome de arquivo).

---

## 7. Próximos passos que o próprio código já aponta

- Detecção de raiz/baixo (PYIN) para quebrar as ambiguidades de rotação/simetria (só relevante fora de MEDIUM).
- Unificar `classifier.py`/`classifier_V2.py` e centralizar os hiperparâmetros (P1 da refatoração).
- Fazer a API importar o núcleo em vez da cópia standalone.
- Anotar mais faixas com GT (formato em [GROUND_TRUTH.md](GROUND_TRUTH.md)) para um número publicável.
