# Hiperparâmetros — onde vivem, valores e efeito

Levantamento de **todos** os valores ajustáveis do pipeline, com o valor em cada
lugar onde aparecem. Não há um arquivo de configuração: os valores estão em
constantes de módulo, defaults de função e argumentos de chamada, em quatro
lugares. As células vazias significam "não é passado; cai no default da coluna
`pipeline.py`/`classifier.py`".

## 1. Tabela consolidada

| # | Parâmetro | `musicas.py` (topo) | `benchmark_musicas.py` (`run_atual` / `_cos`) | Default em `pipeline.py::analyze_track` / `classifier.py` | `Api/audio_processing_v2.py` (topo) | Efeito |
|---|---|---|---|---|---|---|
| 1 | `SR` | 22050 | 22050 | — (recebe `sr`) | 22050 | Taxa de amostragem do `librosa.load`. API comenta que 11025 é ~2× mais rápido e menos preciso. |
| 2 | `METHOD` | `"cqt"` | | `'cqt'` | `"cqt"` | Feature de chroma: `cqt` (36 bins/oitava) \| `cens` \| `stft`. |
| 3 | `SMOOTH` (median filter) | | | 21 (`beat_sync_chroma`) | 21 | Janela do filtro de mediana temporal no chroma (frames). 0/1 desliga. |
| 4 | `margin` (HPSS) | | | 3.0 (`beat_sync_chroma`) | 3.0 (literal) | Margem do HPSS. Maior = separação mais agressiva. |
| 5 | `bins_per_octave` | | | 36 (literal em `beat_sync_chroma` e `extract_chroma`) | 36 (literal) | Resolução do CQT (1/3 semitom). |
| 6 | `COMPLEXITY_PENALTY` | 0.06 | 0.06 | **0.0** (`CosineChordClassifier`) | 0.06 | Viés pró-tríade. Desconto máximo no cosseno de uma tétrade quando a nota de extensão está ausente. 0 = cosseno puro (default no bench). README sugere 0.02–0 para repertório com tétrades reais. |
| 7 | `EXT_SHARPNESS` | 4.0 | 4.0 | 4.0 (`CosineChordClassifier`) | 4.0 | Sensibilidade do viés adaptativo: `fator = max(0, 1 − ext_sharpness · energia_ext/energia_max)`. Maior = aceita a 7ª como real com menos energia. Só existe em `classifier.py` (não em `classifier_V2.py`). |
| 8 | `USE_VITERBI` | True | True | True | (sempre) | False = argmax por segmento com `confidence_gate`. |
| 9 | `CHANGE_PENALTY` | 2.0 | 2.0 | 2.0 | 2.0 | Custo (log) de trocar de acorde entre batidas vizinhas. Faixa sugerida no código: 1.5–4. Maior = timeline mais suave/grudenta. Fixo, não dividido por n_estados. |
| 10 | `TEMP` | 0.1 | | 0.1 | 0.1 | Temperatura do softmax das emissões. Faixa sugerida: 0.05–0.2. Menor = emissão mais decidida. |
| 11 | `N_LOGPROB` | −2.5 | | −2.5 | −2.5 | Log-prob base do estado N. Menos negativo = N aparece mais fácil; mais negativo = N só em silêncio real. |
| 12 | `REL_GATE` | 0.2 | 0.2 | 0.2 | 0.2 | Silêncio = RMS do segmento < 20 % da **mediana** do RMS dos segmentos (acima do piso). Relativo ao nível da gravação. |
| 13 | `ABS_FLOOR` | | | 5e-4 | 5e-4 | Piso absoluto de RMS: segmentos abaixo nunca entram na mediana e são silêncio digital. |
| 14 | `MIN_DUR` | 0.8 | 0.8 | 0.8 | **0.6** | Segmentos mais curtos que isso são absorvidos. **Único valor divergente entre bench e API.** (Além disso a API absorve sempre no anterior, sem iterar; o pipeline absorve no vizinho mais longo, iterando.) |
| 15 | `rms_gate` | 0.02 (passado ao CLF) | | 0.02 (`CosineChordClassifier`) | — | RMS mínimo do áudio em `classify_audio`. **Não é usado por `analyze_track`** (que usa REL_GATE/ABS_FLOOR). Só afeta o bench sintético e `pause_test`. |
| 16 | `confidence_gate` | | | 0.72 (`CosineChordClassifier`) | — | Cosseno mínimo em `classify_vector`; abaixo → N. **Ignorado quando `use_viterbi=True`.** Afeta só o bench sintético e o modo argmax. |
| 17 | Vocabulário | `MEDIUM` (60) | `MEDIUM` (60) | todos os 13 tipos (156) se `templates=None` | MEDIUM (hardcoded) | Conjunto de templates. Ver [TEMPLATES_ACORDES.md](TEMPLATES_ACORDES.md). |

Os "12 hiperparâmetros" citados nas conversas de planejamento correspondem às
linhas **1–3, 6, 7, 9–14** (as 11 constantes do topo de
`Api/audio_processing_v2.py`) mais `margin` (4). `bins_per_octave` (5),
`rms_gate` (15) e `confidence_gate` (16) estão listados por completude — os dois
últimos são inertes no pipeline com Viterbi.

## 2. Parâmetros do bench sintético (não afetam o pipeline)

| Parâmetro | Onde | Valor | Efeito |
|---|---|---|---|
| `QUICK` | `run_bench.py` | True | True = 4 raízes (C, D#, F#, A) e sem condições `detune_*`. False = 12 raízes e 9 condições. |
| `dur` | `bench.run_bench` | 1.5 s | Duração de cada acorde sintético. |
| `n_harmonics` | `bench.run_bench` / `synth_chord` | 6 | Harmônicos por nota na síntese. O 7º é o que aproxima maj de 7. |
| `decay` | idem | 0.6 | Decaimento de amplitude por harmônico. |
| `base_octave` | idem | 3 | Oitava da tônica. `spread_octaves=True` espalha as notas. |
| `seed` | `bench.run_bench` | 0 | Semente dos ruídos. |
| `noise_levels` | `bench.pause_test` | (0.005, 0.01, 0.02, 0.05) | Amplitude do ruído nas pausas. |
| `harmonics_range` | `bench.harmonic_sweep` | 1..12 | Varredura. |
| `DEFAULT_CONDITIONS` | `noise.py` | clean, white_30dB, white_15dB, white_5dB, pink_15dB, detune_25c, detune_50c, percussive (5 hits, amp 0.4), reverb (decay 0.35) | Bateria de degradações. |

## 3. Ordem de precedência hoje

Para o **pipeline real** (o que o usuário vê): `musicas.py` → passa tudo
explicitamente → `analyze_track` → `viterbi.decode`. Os defaults de
`analyze_track` coincidem com `musicas.py` exceto que `musicas.py` também
constrói o classificador com `complexity_penalty=0.06` (default da classe é 0).

Para o **benchmark de regressão**: `benchmark_musicas.py::run_atual` passa só
`use_viterbi, change_penalty, rel_gate, min_dur`; `temp`, `n_logprob`,
`abs_floor`, `method` caem nos defaults de `analyze_track` (que são iguais aos
de `musicas.py`). Resultado: benchmark e `musicas.py` rodam com os mesmos
valores, mas por caminhos diferentes — alterar um default em `pipeline.py` muda
o benchmark sem mudar `musicas.py`, e vice-versa.

Para a **API**: só as constantes do topo de `Api/audio_processing_v2.py`.

## 4. Espaço de busca sugerido (a partir dos comentários do código)

| Parâmetro | Faixa que o código sugere |
|---|---|
| `CHANGE_PENALTY` | 1.5 – 4.0 |
| `TEMP` | 0.05 – 0.2 |
| `N_LOGPROB` | ~ −1.5 – −4.0 (menos negativo = mais N) |
| `REL_GATE` | 0.1 – 0.3 |
| `MIN_DUR` | 0.6 – 1.0 |
| `COMPLEXITY_PENALTY` | 0 – 0.06 (0.02 para repertório com tétrades reais) |
| `EXT_SHARPNESS` | 2 – 6 |
| `SMOOTH` | 11 – 31 (ímpar) |

Qualquer busca deve usar `benchmark_musicas.py` como função objetivo — hoje é
o único harness com ground truth em áudio real.
