# Especificação de reprodutibilidade do pipeline

Documento da revisão camera-ready (ACDSA 2027). Descreve o que o código faz,
sem experimento novo: cada afirmação aponta a linha que a sustenta. As
referências `arquivo:linha` sem prefixo são da raiz do repositório no branch
`revisao-camera-ready`. As que começam com `librosa/` ou `scipy/` são do código
instalado em `.venv/Lib/site-packages/` (librosa 0.11.0, scipy 1.18.0; ver
item 1).

Rota avaliada no artigo: `runner.rodar` → `cache.get_features` →
`pipeline.extract_features` → `runner.estimar` → `pipeline.decode`
(runner.py:572-573, cache.py:169-170, runner.py:343-344).

---

## 1. Versões

Fonte: os `_meta.json` em `data/results/` das execuções no split de teste.

| Meta (data/results/) | python | numpy | scipy | librosa | mir_eval |
|---|---|---|---|---|---|
| `ablation_20260927_014253_ref0_meta.json` (splits `["test"]`) | 3.14.6 (CPython) | 2.4.6 | — | 0.11.0 | 0.8.2 |
| `ablation_20260927_014445_ref1_meta.json` (splits `["test"]`) | 3.14.6 (CPython) | 2.4.6 | — | 0.11.0 | 0.8.2 |
| `ablation_20260927_201422_ref0_meta.json` (splits `["test"]`) | 3.14.6 (CPython) | 2.4.6 | — | 0.11.0 | 0.8.2 |
| `ablation_20260927_201649_ref1_meta.json` (splits `["test"]`) | 3.14.6 (CPython) | 2.4.6 | — | 0.11.0 | 0.8.2 |
| `ablation_20261116_231650_ref0_meta.json` (splits `["test"]`) | 3.14.6 (CPython) | 2.4.6 | — | 0.11.0 | 0.8.2 |
| `ablation_20261116_231706_ref1_meta.json` (splits `["test"]`) | 3.14.6 (CPython) | 2.4.6 | — | 0.11.0 | 0.8.2 |
| `stats_test_ref0_20260927_020514_meta.json` | 3.14.6 | 2.4.6 | 1.18.0 | — | — |
| `stats_test_ref0_20260927_202140_meta.json` | 3.14.6 | 2.4.6 | 1.18.0 | — | — |
| `stats_test_ref1_20260927_020516_meta.json` | 3.14.6 | 2.4.6 | 1.18.0 | — | — |
| `stats_test_ref1_20260927_202219_meta.json` | 3.14.6 | 2.4.6 | 1.18.0 | — | — |

- **Não há divergência** entre as metas: todas as que registram um pacote
  registram a mesma versão.
- **librosa e mir_eval** vêm só das metas de ablação: `runner._meta` grava
  python, implementação, numpy, librosa e mir_eval, mas **não grava scipy**
  (runner.py:615-621).
- **scipy** vem só das metas `stats_test_*`: `stats.py` grava python, numpy e
  scipy (stats.py:514-517), não librosa nem mir_eval. Fora dessas, scipy
  1.18.0 aparece também em `mascara_comum_20260927_202401_meta.json`
  (splits `["val","test"]`; mascara_comum.py:297-299), igual.
- As metas de teste pós-revisão `curvas_teste_20261117_004111_meta.json` e
  `cobertura_igualada_teste_20261117_004111_meta.json` repetem python 3.14.6,
  numpy 2.4.6, librosa 0.11.0 e mir_eval 0.8.2 (curvas_teste_revisao.py:259-261).
- Conferência na `.venv` atual (só leitura, `importlib`/`__version__`):
  python 3.14.6, numpy 2.4.6, scipy 1.18.0, librosa 0.11.0, mir_eval 0.8.2 —
  idênticas às metas. Dependências que **nenhuma meta registra** e que
  influem no resultado (ver seção final): numba 0.65.1, llvmlite 0.47.0,
  soxr 1.1.0, soundfile 0.14.0, audioread 3.1.0 (valores da `.venv` hoje, não
  das execuções). `requirements.txt` não fixa versões.
- Estado da árvore registrado: as quatro ablações de teste de 2026-09-27 têm
  `arvore_suja=false`; as duas de 2026-11-16 (`231650`, `231706`) têm
  `arvore_suja=true`.

## 2. Split

Fonte: `data/manifests/guitarset_comping.csv` (colunas `split`, `excluded`,
`exclude_reason`), gerado por `dataset_io.guitarset_rows`
(dataset_io.py:157-189).

- Regra: músicos 00-03 → `val`, 04-05 → `test` (dataset_io.py:54-55,
  163-168). Exclusões fixas em `GUITARSET_EXCLUDED` (dataset_io.py:48-51); as
  excluídas ficam no manifest com `excluded=true` (dataset_io.py:177-178).
- O runner descarta `excluded=true` antes de filtrar por split
  (runner.py:482-486).
- Arquivos gravados (um `track_id` por linha, na ordem do manifest, que é a
  ordem alfabética dos WAV, dataset_io.py:160):
  - `artigo-ACDSA/splits/val.txt` — **120** faixas;
  - `artigo-ACDSA/splits/test.txt` — **58** faixas;
  - `artigo-ACDSA/splits/excluidas.txt` — **2** faixas (ambas do teste,
    músico 04), `track_id<TAB>motivo`:
    `04_BN3-154-E_comp` (timing incorreto, +0,409 s) e
    `04_Jazz1-200-B_comp` (timing incorreto, +0,309 s), issue #5 do GuitarSet.
- Total 180 = 120 + 58 + 2, o que `guitarset_rows` exige (dataset_io.py:180-181).

## 3. Áudio, HPSS, beat tracking e CQT

### 3.1 Carga do áudio
`librosa.load(audio, sr=22050, mono=True)` (cache.py:169; `sr` de
config.py:58). Defaults herdados (librosa 0.11.0, assinatura de
`librosa.load`): `res_type='soxr_hq'`, `dtype=float32`, `offset=0`,
`duration=None`. O GuitarSet `audio_mono-mic` (dataset_io.py:29) é
reamostrado para 22 050 Hz pelo soxr.

### 3.2 HPSS
Chamada: `librosa.effects.hpss(y, margin=3.0)` (pipeline.py:97;
config.py:61). Só `margin` é passado. Parâmetros efetivos (defaults herdados
de librosa 0.11.0, `librosa/effects.py:66` e corpo em 129-160):

| Parâmetro | Valor efetivo | Origem |
|---|---|---|
| `margin` | 3.0 (harmônico e percussivo) | código |
| `kernel_size` | 31 (mediana de 31 quadros e 31 bins) | default |
| `power` | 2.0 | default |
| `mask` | False (máscaras suaves aplicadas ao STFT) | default |
| `n_fft` | 2048 | default |
| `hop_length` | None → `win_length // 4` = 512 (`librosa/core/spectrum.py:233-234`) | default |
| `win_length` | None → `n_fft` = 2048 | default |
| `window` | `'hann'` | default |
| `center`, `pad_mode` | True, `'constant'` | default |
| saída | ISTFT com `length=len(y)` (`librosa/effects.py:151,160`) | librosa |

Com `margin > 1` há resíduo descartado: `y_harm + y_perc ≠ y`.

### 3.3 Beat tracking
Chamada: `librosa.beat.beat_track(y=y_perc, sr=sr)` (pipeline.py:99), sobre o
componente **percussivo**. Nenhum parâmetro além de `y` e `sr` é passado; o
`tempo` devolvido é ignorado. Efetivos (defaults de librosa 0.11.0,
`librosa/beat.py:36`):

| Parâmetro | Valor efetivo |
|---|---|
| `hop_length` | 512 |
| `start_bpm` | 120.0 |
| `tightness` | 100 |
| `trim` | True (descarta batidas fracas no início e no fim) |
| `bpm`, `prior` | None (tempo estimado por `_tempo`, `librosa/beat.py:235-242`) |
| `units` | `'frames'` |
| `sparse` | True |
| envelope de onset | `onset.onset_strength(y, sr, hop_length=512, aggregate=np.median)` — `aggregate=np.median` é fixo dentro do librosa (`librosa/beat.py:217-219`); os demais parâmetros do onset são os defaults de `onset_strength` (`librosa/onset.py:216`: `lag=1`, `max_size=1`, `detrend=False`, `center=True`, feature mel) |
| envelope nulo | devolve `beats = []` (`librosa/beat.py:227-230`) |

### 3.4 Chroma CQT
Chamada: `librosa.feature.chroma_cqt(y=y_harmonic, sr=sr, bins_per_octave=36)`
(pipeline.py:106-107; `method='cqt'`, config.py:59; 36, config.py:62).
Efetivos (librosa 0.11.0, `librosa/feature/spectral.py:1289` e 1371-1414):

| Grandeza | Valor efetivo | Origem |
|---|---|---|
| hop | 512 amostras = 23,22 ms a 22 050 Hz | default `hop_length=512` |
| transformada | `cqt` (modo `'full'`), módulo `np.abs` | default `cqt_mode='full'`, spectral.py:1371,1386-1396 |
| `fmin` | None → C1 = 32,70 Hz (`librosa/core/constantq.py:923-925`) | default |
| afinação | `tuning=None` → estimada por faixa com `estimate_tuning(y=y_harmonic, sr, bins_per_octave=36)`, e `fmin ← fmin·2^(tuning/36)` (`constantq.py:927-934`) | default |
| nº de oitavas | 7 | default `n_octaves=7` |
| nº de bins | 7 × 36 = 252 (de ~32,7 Hz a ~4,1 kHz, antes da correção de afinação) | spectral.py:1393 |
| bins por oitava | 36 (1/3 de semitom) | código |
| filtros | `filter_scale=1`, `norm=1`, `sparsity=0.01`, `window='hann'`, `scale=True`, `pad_mode='constant'`, `res_type='soxr_hq'` (`constantq.py:28-43`) | default |
| CQT → chroma | `cq_to_chroma` com `fmin=None` (C1 **sem** correção de afinação), `base_c=True`, `window=None`: cada classe soma 3 bins adjacentes (o central ±1), pesos 1 (`librosa/filters.py:1071-1114`) | default |
| `threshold` | 0.0 (não zera nada: módulos ≥ 0) | default, spectral.py:1410-1411 |
| normalização | `norm=np.inf` por quadro: cada coluna dividida pelo seu máximo; coluna com máximo abaixo de `tiny` fica **sem** normalizar (`fill=None`, `librosa/util/utils.py:955,1002-1004`) | default, spectral.py:1414 |
| dtype | float32 | conferido em snippet |

**Alinhamento de quadro.** O quadro `t` está centrado na amostra `512·t`
(STFT com `center=True` dentro da CQT, `constantq.py:1120-1127`); o número de
quadros é `1 + ⌊N/512⌋` para N amostras (conferido: 2 s → 87 quadros). A
conversão quadro→tempo é `librosa.frames_to_time(beats, sr=sr)` com
`hop_length=512` e `n_fft=None`, i.e. `t = 512·k / 22050`, sem deslocamento
de meia janela (pipeline.py:113).

**Pós-processamento do chroma no projeto.**
1. Filtro de mediana temporal `scipy.ndimage.median_filter(chroma,
   size=(1, 21))` (pipeline.py:108-109; `smooth=21`, config.py:60), aplicado
   **depois** da normalização ∞; por isso as colunas deixam de ter máximo 1.
   Borda herdada do scipy: `mode='reflect'` (default de
   `scipy/ndimage/_filters.py:2078`).
2. Agregação por batida (item 4).
3. Normalização L2 do vetor de cada batida só no classificador
   (classifier.py:123-126). Vetor com norma < 1e-9 → emissão toda zero
   (classifier.py:124-125).

## 4. Agregação batida → chroma

Código (pipeline.py:111-113):

```
beats = librosa.util.fix_frames(beats, x_max=chroma.shape[1])
chroma_sync = librosa.util.sync(chroma, beats, aggregate=np.median)
beat_times = librosa.frames_to_time(beats, sr=sr)
```

- `fix_frames` com `x_min=0` (default), `x_max=T` (nº de quadros) e
  `pad=True` (default): recorta as batidas em `[0, T]`, **acrescenta 0 e T**,
  filtra e devolve `np.unique` (ordenado, sem repetidos)
  (`librosa/util/utils.py:580, 649, 657, 660-666`).
- `sync` com `aggregate=np.median`: segmento `k` = mediana, por classe, dos
  quadros `[b_k, b_{k+1})` (`librosa/util/utils.py:1654, 1673`;
  `index_to_slice` em 1542-1545). Com nº par de quadros, `np.median` é a média
  dos dois centrais.
- **Antes da primeira batida:** vira um segmento próprio, `[0, b_1)`, porque o
  0 é inserido. Se a primeira batida já for o quadro 0, o `unique` elimina o
  repetido e não há segmento vazio.
- **Depois da última batida:** segmento `[b_K, T)`, com borda final
  `T·512/22050 s`, que pode passar da duração do áudio em até um hop
  (~23 ms; conferido: 3,0 s de silêncio → borda 3,0186 s).
- **Menos de 2 batidas:** 0 batidas (inclusive envelope de onset nulo) →
  bordas `[0, T]`, **um único segmento** cobrindo a faixa inteira (conferido
  com 3 s de silêncio: `n_seg=1`). 1 batida em `0 < b < T` → 2 segmentos.
  Nenhum caso levanta erro; `decode` só devolve `[]` se `n_seg == 0`
  (pipeline.py:225-226), o que exigiria `T = 0`.
- `beat_times` tem sempre `n_seg + 1` bordas, logo o ramo
  `else t0` de pipeline.py:144 e pipeline.py:256 nunca é executado.
- RMS por segmento: no áudio **original** (não no harmônico), amostras
  `y[int(t0·sr) : int(t1·sr)]` (truncamento), `sqrt(mean(x²) + 1e-12)`;
  fatia vazia → 0.0 (pipeline.py:139-155).

## 5. Templates

- Intervalos (semitons a partir da tônica), chord_templates.py:31-46. Os usados
  no artigo: maior `''` = {0,4,7}; `m` = {0,3,7}; `7` = {0,4,7,10};
  `maj7` = {0,4,7,11}; `m7` = {0,3,7,10}.
- Vetor binário de 12 posições, 1.0 nas classes `(raiz + intervalo) mod 12`,
  índice 0 = C (chord_templates.py:22, 65-73).
- Normalização L2 por linha no classificador: `M / (‖M‖₂ + 1e-9)`
  (classifier.py:96-98). Tríade → entradas 1/√3; tétrade → 1/2.
- Ordem das colunas: `build_templates` percorre os sufixos na ordem da lista
  e, dentro de cada um, as raízes 0..11 (chord_templates.py:94-98); a ordem é
  a de inserção no `dict`, preservada por `list(templates.keys())`
  (classifier.py:94).
  - `BASIC = ['', 'm']` (chord_templates.py:51) → 24 colunas:
    0-11 = C, C#, …, B; 12-23 = Cm, …, Bm.
  - `MEDIUM = ['', 'm', '7', 'maj7', 'm7']` (chord_templates.py:52) → 60:
    0-11 maiores, 12-23 menores, 24-35 `7`, 36-47 `maj7`, 48-59 `m7`.
  - O estado N é a coluna seguinte (24 ou 60), anexada só no Viterbi
    (viterbi.py:68-70).
- Viés pró-tríade (só tétrades): nota de extensão = `(raiz + maior intervalo
  ≥ 8) mod 12` (classifier.py:107-115). Na emissão,
  `s_k ← cos_k − cp·max(0, 1 − es·ĉ[ext_k])`, com `ĉ = c / (max c + 1e-9)`
  (classifier.py:128-137); produção `cp=0.06`, `es=4.0` (config.py:81-82).
  No BASIC não há tétrade e o termo não atua.
- Vocabulário por variante: `runner.classificador_de` monta o classificador
  com `build_templates(VOCABULARIOS[vocab])` (runner.py:144, 246-260).

## 6. Desempates e limiares

| Ponto | Regra no código | Desempate / borda |
|---|---|---|
| argmax sem Viterbi | `best = int(np.argmax(sims))` (classifier.py:149) | empate → **menor índice de coluna** (primeira ocorrência do `np.argmax`): ordem do item 5, raiz C antes de C#, maior antes de menor antes de `7`… |
| gate de confiança | `if best_score < confidence_gate: N` (classifier.py:152) | **estrito**: escore igual ao limiar rotula. Inerte com Viterbi (só `classify_vector` o lê; config.py:75-78) |
| chroma nulo (sem Viterbi) | `np.sum(chroma_vec) < 1e-6` → N (classifier.py:145-146) | estrito |
| gate de RMS (mediana) | mediana de `seg_rms[seg_rms > abs_floor]`, 0.0 se vazio (pipeline.py:230) | segmento com RMS **igual** ao piso fica fora da mediana |
| gate de RMS (limiar) | `gate = max(abs_floor, rel_gate·mediana)` (pipeline.py:231); `force_n` se `seg_rms < gate` (pipeline.py:238-239) | **estrito**: RMS igual ao gate não é silêncio. Com `rel_gate=0` (variantes `rg`) o piso absoluto 5e-4 continua ativo |
| `rms_gate` do classificador | 0.02 em `classify_audio` (classifier.py:158-163) | **não é usado** no pipeline do artigo |
| Viterbi: emissão | `log(softmax(s/temp) + 1e-12)` para acordes; N = `n_logprob` constante, fora do softmax (viterbi.py:73-77); `temp` limitado a ≥ 1e-6 (viterbi.py:37) | quadro forçado: acordes −50, N = 0 (viterbi.py:78-80) |
| Viterbi: transição | 0 para permanecer, `−change_penalty` para qualquer troca, inclusive de/para N; matriz não normalizada (viterbi.py:83-84) | — |
| Viterbi: inicialização | `delta[0] = log_em[0]`, **sem prior inicial** (equivale a prior uniforme não normalizado) (viterbi.py:89) | — |
| Viterbi: recursão | `psi[t,j] = argmax(delta[t−1] + log_T[:,j])` (viterbi.py:92-94) | empate → **estado anterior de menor índice**, não necessariamente o próprio `j` |
| Viterbi: estado final | `argmax(delta[-1])` (viterbi.py:97) | empate → menor índice; N (último) perde empates para qualquer acorde |
| "N proibido" (`*0*`) | `n_logprob = −1e9` (runner.py:191) | quadros com `force_n` ainda recebem N = 0, logo N continua possível pelo gate de RMS |

## 7. Filtro de duração (`pipeline._absorb_short`, pipeline.py:170-197)

Entrada: segmentos já mesclados (`_merge`, pipeline.py:259). `_merge` descarta
segmentos com `end <= start` e funde vizinhos de mesmo rótulo
(pipeline.py:158-167). Produção: `min_dur = 0.8 s` (config.py:90); variantes
sem o estágio (A-D, F e derivadas) usam 0 (runner.py:182-186).

- `min_dur <= 0` → devolve a lista recebida, sem cópia (pipeline.py:176-177).
- Trabalha sobre cópias dos dicts (pipeline.py:178).
- **Ordem de varredura:** não há varredura sequencial. A cada iteração toma o
  segmento de **menor duração da faixa inteira** (pipeline.py:182-184);
  empate de duração → o de **menor índice** (o `min` do Python devolve o
  primeiro mínimo).
- **Critério de curto:** `dur < min_dur` (estrito): se o mais curto tem
  `dur >= min_dur`, para (pipeline.py:185-186).
- **Vizinho doador:** com os dois vizinhos, o **mais longo**; empate de
  duração → **esquerda** (`>=`, pipeline.py:190-191). Não considera rótulo,
  escore nem se o vizinho é N.
- **Bordas da faixa:** o primeiro segmento só tem o vizinho da direita e o
  último só o da esquerda; esse único vizinho é o doador, qualquer que seja a
  duração dele (pipeline.py:188-189, 192-193).
- **Mesmo rótulo dos dois lados:** após relabelar, `_merge` funde os três
  (pipeline.py:194-195).
- **Reatribuição repetida:** depois de cada relabel + merge as durações são
  recalculadas; um segmento que cresceu ao absorver outro pode continuar curto
  e ser absorvido depois, levando junto o trecho absorvido (cadeia).
- **Parada:** o laço exige `len(segs) > 1` (pipeline.py:180), e cada iteração
  reduz o nº de segmentos em ≥ 1 (o rótulo copiado é de um vizinho, então o
  merge sempre funde). Termina em no máximo `n − 1` iterações. A flag
  `changed` é sempre True dentro do laço; a saída real é o `break`
  (pipeline.py:186) ou restar um segmento. Um único segmento curto
  sobrevive.
- O mesmo vale para segmentos N: são absorvidos e doam rótulo como qualquer
  acorde.
- Testes que fixam esses casos: `tests/test_filtro_duracao.py` (borda,
  vizinhos iguais, cadeia).

Pseudocódigo: `artigo-ACDSA/tabelas/alg_pipeline.tex` e
`artigo-ACDSA/tabelas/alg_duracao.tex`.

---

## Comportamentos não determinísticos ou não especificados

O pipeline não usa números aleatórios; para a mesma máquina e as mesmas
bibliotecas o resultado é reprodutível (o oráculo
`out/musicas_bench/metrics.json` depende disso). Os pontos abaixo são os que o
código **não fixa** por si:

1. **Defaults de biblioteca.** Todos os parâmetros listados como "default" no
   item 3 (HPSS, beat tracking, onset, CQT, afinação, `cq_to_chroma`,
   normalização ∞, `mode='reflect'` do filtro de mediana, `res_type` do load)
   não estão no código do projeto: valem os da librosa 0.11.0 / scipy 1.18.0.
   Outra versão pode mudar o resultado sem alterar uma linha do repositório.
2. **Versões não registradas.** As metas de ablação não gravam scipy
   (runner.py:615-621); nenhuma meta grava numba/llvmlite (beat tracker e
   utilitários do librosa são `numba.guvectorize`, `librosa/beat.py:517-686`),
   soxr (reamostragem 44,1 → 22,05 kHz), soundfile/libsndfile (decodificação)
   nem a biblioteca BLAS/FFT do numpy. As versões citadas no item 1 para esses
   pacotes são as da `.venv` hoje, não as das execuções.
3. **Cache sem versão.** A chave do cache de features é só (caminho do áudio,
   `PreChromaConfig`) (cache.py:80-91, 109-135): não inclui versões de
   biblioteca nem hash do conteúdo do áudio. As versões numa meta são as do
   processo que **leu** o cache, não necessariamente as do que **calculou** o
   chroma.
4. **Ponto flutuante.** `M @ v` (classifier.py:127), FFTs da CQT/STFT e a
   reamostragem podem diferir no último bit entre CPU/BLAS/SIMD. Isso só muda
   rótulos onde há comparação exata: empates de argmax (item 6), limiares
   estritos (`<` do gate de confiança e do gate de RMS) e empates de duração
   no filtro (item 7). As durações são `end − start` de tempos `512·k/22050`
   em float64: dois segmentos com o mesmo nº de quadros podem não ter
   durações bit a bit iguais, e então o "empate → esquerda/primeiro" pode não
   se aplicar como se esperaria contando quadros.
5. **Desempates por índice.** `np.argmax` e `min` resolvem empates pela
   primeira ocorrência; isso é determinístico, mas a preferência resultante
   (raiz C, qualidade maior, vizinho esquerdo, estado anterior de menor
   índice no Viterbi em vez de "permanecer") é efeito colateral da ordem das
   colunas, não uma decisão de projeto documentada.
6. **Ordem do dicionário de templates.** Depende da ordem de inserção do
   `dict` (garantida em Python ≥ 3.7) e da ordem das listas `BASIC`/`MEDIUM`;
   determinística, mas qualquer reordenação muda os desempates do item 5.
7. **Borda final além do áudio.** A última borda é `T·512/sr`, que pode
   exceder a duração do arquivo em até ~23 ms (item 4). O tratamento desse
   excesso fica a cargo da avaliação (`mir_eval.chord.evaluate` em evaluate.py:110, que ajusta os
   intervalos estimados aos da referência; idem runner.py:384), não do pipeline.
8. **Afinação por faixa.** `estimate_tuning` desloca o `fmin` da CQT, mas o
   mapa `cq_to_chroma` usa C1 sem correção (item 3.4). É o comportamento da
   librosa 0.11.0; o código do projeto não o especifica.
9. **Faixas sem batida.** Viram um único segmento de faixa inteira (item 4);
   o código não trata esse caso explicitamente, ele decorre do `pad=True` do
   `fix_frames`.
10. **Árvore suja.** As ablações de teste pós-revisão
    (`ablation_20261116_231650_ref0`, `..._231706_ref1`) registram
    `arvore_suja=true`; a meta não diz quais arquivos estavam modificados.
