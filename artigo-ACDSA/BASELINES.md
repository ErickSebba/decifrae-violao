# Baselines V4 e V4b — descrição a partir do código

Documento escrito à mão por leitura de código (revisão camera-ready). Não há
nenhum número de resultado aqui: só a especificação dos dois baselines e as
diferenças em relação à família C–F. Toda afirmação traz `arquivo:linha` no
estado da branch `revisao-camera-ready` (HEAD `994c14a`).

Arquivos lidos: `legacy_v4.py` (intocável), `runner.py`, `pipeline.py`,
`config.py`, `classifier.py`, `viterbi.py`, `cache.py`, `chord_templates.py`,
`evaluate.py`.

---

## 1. Rota de execução no `runner.py`

| Variante | Motor | Chamada | Vocabulário declarado |
|---|---|---|---|
| `V4`  | `v4`  | `estimar_v4(y, sr)` (`runner.py:563-566`)  | `BASIC` (`runner.py:193`) |
| `V4b` | `v4b` | `estimar_v4b(y, sr)` (`runner.py:567-570`) | `BASIC` (`runner.py:194`) |
| C–F   | `cosseno` | `cache.get_features` + `estimar` → `pipeline.decode` (`runner.py:571-573`, `runner.py:336-345`) | `MEDIUM` (C, D, E) / `BASIC` (F) (`runner.py:197-200`) |

- O áudio dos baselines é carregado com `librosa.load(audio, sr=PRE_CHROMA.sr, mono=True)`
  (`runner.py:565`, `runner.py:569`), isto é, 22 050 Hz mono (`config.py:58`) —
  o mesmo carregamento da família C–F (`cache.py:169`).
- Os baselines **não usam cache** nem `PreChromaConfig`/`PostChromaConfig`:
  `Variante.pre` e `Variante.post` ficam `None` (`runner.py:165-166`,
  `runner.py:193-194`), e as colunas de configuração do CSV saem vazias
  (`runner.py:506-511`). O campo `vocab="BASIC"` dos baselines é só rótulo
  da linha do CSV (`runner.py:503`): o vocabulário efetivo é o literal do
  classificador (§3), que coincide com `BASIC = ['', 'm']`
  (`chord_templates.py:51`).
- `V4` chama o `legacy_v4.run_beat_tracking` intocado (`runner.py:351-354`).
  `V4b` usa uma **cópia** da segmentação (`_beat_sync_v4`, `runner.py:318-326`)
  e uma **cópia** do classificador sem os termos temporais
  (`classificar_segmento_v4b`, `runner.py:279-315`), porque `legacy_v4.py`
  não é editado (`runner.py:267-271`).

---

## 2. Segmentação (idêntica em V4 e V4b)

Linha a linha, `legacy_v4.run_beat_tracking` (`legacy_v4.py:85-97`) e
`runner._beat_sync_v4` (`runner.py:318-326`) fazem o mesmo:

1. **HPSS** com `margin=3.0`, literal no chamador: `runner.py:353` (V4) e
   `runner.py:361` (V4b). (O `legacy_v4.comparar_metodos` também usa 3,0,
   `legacy_v4.py:140`, mas não é chamado pelo runner.)
2. **Beat tracking** sobre o componente **percussivo**:
   `librosa.beat.beat_track(y=y_percussive, sr=sr)` com todos os demais
   argumentos no default do librosa (`legacy_v4.py:86`, `runner.py:321`).
3. **Chroma** `librosa.feature.chroma_cqt(y=y_harmonic, sr=sr, bins_per_octave=36)`
   sobre o componente **harmônico** (`legacy_v4.py:87`, `runner.py:322`).
   Demais argumentos no default (hop 512, `norm=inf` por quadro, `tuning`
   estimado; defaults conferidos na librosa 0.11.0 do `.venv`).
4. **Sem filtro de mediana temporal.** `scipy.ndimage` é importado em
   `legacy_v4.py:18`, mas não é usado em nenhum lugar do módulo.
5. **Sincronização por batida**: `fix_frames(beats, x_max=chroma.shape[1])`
   (default `pad=True`, acrescenta as bordas 0 e `x_max`) e
   `util.sync(chroma, beats, aggregate=np.median)` (`legacy_v4.py:88-89`,
   `runner.py:323-324`). Bordas em segundos por `frames_to_time`
   (`legacy_v4.py:90`, `runner.py:325`).
6. **Um segmento por intervalo entre batidas**, `start=tempos[i]`,
   `end=tempos[i+1]` (`legacy_v4.py:95`, `runner.py:366`).
7. **Nenhuma fusão de segmentos.** O runner devolve a lista por batida tal
   como sai (`runner.py:355`, `runner.py:363-368`). A fusão de vizinhos
   iguais que existe em `legacy_v4.py:169-178` está dentro de
   `comparar_metodos` (só para o gráfico) e não é executada pelo runner.
   Nenhuma absorção de segmentos curtos.

Consequência para as métricas: os níveis de acurácia e `overseg`/`underseg`/`seg`
não dependem da fusão — o `mir_eval.chord.evaluate` (0.8.2) funde
intervalos de rótulo igual (`merge_chord_intervals`) antes de medir a
segmentação, e é ele que `evaluate.py:110` chama. Já a coluna de diagnóstico
`n_segmentos_est = len(est)` (`runner.py:516`) conta **batidas** nos
baselines e **segmentos fundidos** em C–F: não é comparável entre as duas
famílias.

---

## 3. Classificador e equação do escore

Código: `legacy_v4.classificar_segmento_v4` (`legacy_v4.py:27-79`); a cópia
`runner.classificar_segmento_v4b` (`runner.py:279-315`) com as constantes em
`runner.py:272-276`.

**Normalização.** O vetor `c` (chroma do segmento, 12 dimensões, já
mediana-sincronizado) é dividido pelo seu máximo:
`ĉ = c / (max(c) + 1e-6)` (`legacy_v4.py:30`, `runner.py:283`).

**Vocabulário.** 12 tônicas (`legacy_v4.py:32`, `runner.py:272`) × 2 tipos
ativos (`legacy_v4.py:35-41`, `runner.py:273-276`):

| sufixo | intervalos | `bias` | `required` |
|---|---|---|---|
| `''` (maior) | {0, 4, 7} | 0,15 | `None` |
| `'m'` (menor) | {0, 3, 7} | 0,15 | `None` |

`sus2`, `sus4` e `7` estão comentados (`legacy_v4.py:38-40`) e não existem em
V4b. Total: 24 rótulos, só sustenidos. Não há um estado `N` competindo no
argmax (ver §5).

**Escore** (`legacy_v4.py:61-73`; V4b `runner.py:302-307`), para a tônica
`r`, o tipo `q`, o conjunto de classes de altura `T = T(r,q)` e o rótulo
anterior `a` (string emitida no segmento anterior):

```
s(r,q) = Σ_{k∈T} ĉ_k − 0,6 · Σ_{k∉T} ĉ_k + 0,15
         + 0,5 · 1[nome(r,q) = a]                     (só V4)
         − 0,1 · 1[a ≠ "" ∧ len(a) < len(nome(r,q))]  (só V4)
```

Decisão: `argmax` com comparação estrita `score > melhor_score`
(`legacy_v4.py:75-77`, `runner.py:311-313`), varrendo as tônicas de C a B e,
dentro de cada uma, `''` antes de `'m'` (`legacy_v4.py:46-47`). Em empate
exato vence o **primeiro** na ordem C, Cm, C#, C#m, …, B, Bm. Determinístico.

**Constantes** (todas literais, nenhuma configurável):

| Constante | Valor | Onde |
|---|---|---|
| gate de soma do chroma | 0,1 | `legacy_v4.py:29`, `runner.py:281` |
| epsilon da normalização | 1e-6 | `legacy_v4.py:30`, `runner.py:283` |
| peso da energia fora do template | 0,6 | `legacy_v4.py:66`, `runner.py:307` |
| `bias` (maior e menor) | 0,15 | `legacy_v4.py:36-37`, `runner.py:274-275` |
| limiar da nota obrigatória | 0,25 | `legacy_v4.py:58`, `runner.py:299` |
| bônus de inércia (só V4) | +0,5 | `legacy_v4.py:69-70` |
| penalidade de nome longo (só V4) | −0,1 | `legacy_v4.py:72-73` |
| HPSS `margin` | 3,0 | `runner.py:353`, `runner.py:361` |
| CQT `bins_per_octave` | 36 | `legacy_v4.py:87`, `runner.py:322` |

**Observações que decorrem do código** (não são escolhas declaradas):

- **O `bias` não tem efeito.** Os dois tipos ativos têm o mesmo `bias` 0,15;
  como é somado a todos os candidatos, não altera o `argmax`.
- **O limiar 0,25 é código morto.** Os dois tipos ativos têm
  `required: None`, então o bloco de `legacy_v4.py:56-59` (`runner.py:297-300`)
  nunca executa.
- **Forma equivalente.** Como `Σ_{k∉T} ĉ_k = S − Σ_{k∈T} ĉ_k`, com
  `S = Σ_k ĉ_k` independente do candidato,
  `s = 1,6 · Σ_{k∈T} ĉ_k − 0,6 · S + 0,15 (+ termos temporais)`.
  Sem os termos temporais (V4b), o classificador escolhe a tríade com a
  **maior soma de energia normalizada-pelo-máximo nas suas três classes de
  altura**.
- **`"N/A"` é inalcançável na prática.** O vencedor inicial é `"N/A"`
  (`legacy_v4.py:44`), mas qualquer escore finito supera `−inf`. Só
  sobreviveria se `ĉ` contivesse `NaN` (todas as comparações falsas). Em
  todo caso, `_normaliza_v4` o mapeia para `N` (`runner.py:329-330`).

---

## 4. Os dois termos temporais gulosos (só V4)

Ambos dependem apenas de `acorde_anterior`, que é o **rótulo emitido** no
segmento anterior (já com o efeito da inércia), passado em
`legacy_v4.py:92-96`. O primeiro segmento recebe `""`.

1. **Inércia, +0,5** (`legacy_v4.py:69-70`): somado ao candidato cujo nome é
   igual ao rótulo anterior. Na forma equivalente acima, o acorde anterior só
   é trocado se outra tríade tiver `Σ_{k∈T} ĉ_k` maior por mais de
   0,5/1,6 = 0,3125 (ou 0,6/1,6 = 0,375 se o rival também levar a
   penalidade do item 2), em unidades de chroma normalizado pelo máximo.
2. **Penalidade de nome longo, −0,1** (`legacy_v4.py:72-73`): subtraída de
   todo candidato cujo **nome tem mais caracteres** que o rótulo anterior,
   desde que este não seja vazio. Depende da **grafia**, não da qualidade
   do acorde: com `len("C")=1`, `len("Cm")=len("C#")=2`, `len("C#m")=3`,
   - anterior maior natural (`C`): penaliza todos os menores e todos os
     maiores com sustenido;
   - anterior menor natural (`Cm`) ou maior com sustenido (`C#`): penaliza só
     os menores com sustenido;
   - anterior menor com sustenido (`C#m`): não penaliza nada.

   O candidato igual ao anterior nunca é penalizado (mesmo comprimento).
   O comentário da docstring do runner ("−0.1 no nome mais longo",
   `runner.py:12`) descreve o código fielmente; a leitura "viés pró-maior"
   só vale parcialmente, por causa do efeito dos sustenidos.

**Guloso.** A decisão no segmento `i` é tomada uma vez, sem olhar adiante, e
o resultado realimenta o segmento `i+1`: é uma cadeia de primeira ordem
decidida localmente, não uma decodificação ótima (contraste com o Viterbi de
D–F, `viterbi.py:82-94`).

**Interação com o silêncio.** Se o segmento anterior caiu no gate (§5),
`acorde_anterior = ""`: nenhum candidato tem nome vazio (sem bônus) e a
penalidade exige `acorde_anterior` não vazio — os dois termos ficam
desligados no segmento seguinte.

---

## 5. Silêncio e `N`

- **Única fonte de N nos baselines:** `np.sum(chroma_segmento) < 0.1` →
  devolve `""` (`legacy_v4.py:29`, `runner.py:281-282`), convertido em `N`
  por `_normaliza_v4` (`runner.py:329-330`, aplicado em `runner.py:355` e
  `runner.py:367`). O teste é sobre o **chroma sincronizado não normalizado**
  (a soma é feita antes da divisão pelo máximo).
- **Não há gate de RMS** nem limiar de confiança: não se mede energia do
  áudio em nenhum ponto de V4/V4b.
- **Ressalva (inferência, não verificada empiricamente aqui):** como o
  `chroma_cqt` normaliza cada quadro pelo máximo (`norm=inf`), um quadro com
  qualquer energia tem máximo 1, e a mediana por batida tende a ter soma bem
  acima de 0,1. O gate deve disparar praticamente só em trechos de chroma
  (quase) nulo, isto é, silêncio digital. A fração de N efetiva dos
  baselines deve ser lida dos CSVs (`frac_n_est`), não deduzida daqui.

---

## 6. O que V4b remove e o que mantém

**Remove exatamente duas linhas de escore** (`runner.py:267-269`,
substituídas pelo comentário de `runner.py:309`):

- `score += 0.5` quando `nome_atual == acorde_anterior` (`legacy_v4.py:69-70`);
- `score -= 0.1` quando `acorde_anterior` não vazio e mais curto que
  `nome_atual` (`legacy_v4.py:72-73`).

Como esses eram os únicos usos de `acorde_anterior`, o parâmetro sai da
assinatura e V4b é **sem estado** (`runner.py:270-271`, `runner.py:279`):
cada batida é classificada isoladamente (`runner.py:364-365`).

**Mantém, literalmente igual:** HPSS 3,0; beat tracking no percussivo;
`chroma_cqt` com 36 bins/oitava; `fix_frames` + sync por mediana; ausência
de filtro de mediana temporal; normalização pelo máximo; os 24 templates;
o peso 0,6; o `bias` 0,15; o limiar morto 0,25; o gate de soma 0,1; a ordem
de varredura e o desempate; a saída por batida sem fusão; o mapeamento
`""`/`"N/A"` → `N`.

Diferença de implementação que **não** muda a saída: V4 chama
`legacy_v4.run_beat_tracking` e V4b chama a cópia `_beat_sync_v4`; os dois
corpos são idênticos linha a linha (`legacy_v4.py:86-90` vs.
`runner.py:321-325`). V4b converte as bordas para `float` Python
(`runner.py:366`); V4 as repassa como `np.float64` (`runner.py:355`) —
mesmo valor.

---

## 7. Diferenças de front-end e de decisão em relação à família C–F

Família C–F: `pipeline._beat_sync_chroma` (`pipeline.py:82-114`) com
`PRE_CHROMA` (`config.py:58-62`, todas as variantes C–F usam `PRE_CHROMA`,
`runner.py:197-200`), seguido de `pipeline.decode` (`pipeline.py:200-259`).

| Eixo | V4 / V4b | C–F | Igual? |
|---|---|---|---|
| Carregamento | 22 050 Hz mono (`runner.py:565`) | 22 050 Hz mono (`cache.py:169`) | sim |
| Margem do HPSS | 3,0 literal (`runner.py:353`, `:361`) | `hpss_margin=3.0` (`config.py:61`, `pipeline.py:97`) | sim (fontes distintas) |
| Sinal do beat tracking | percussivo, defaults (`legacy_v4.py:86`) | percussivo, defaults (`pipeline.py:99`) | sim |
| Chroma | `chroma_cqt`, harmônico (`legacy_v4.py:87`) | `method="cqt"` → `chroma_cqt`, harmônico (`config.py:59`, `pipeline.py:105-107`) | sim |
| Bins do CQT | 36 literal (`legacy_v4.py:87`) | `bins_per_octave=36` (`config.py:62`) | sim |
| Suavização temporal | **nenhuma** | **mediana de 21 quadros** por classe de altura (`config.py:60`, `pipeline.py:108-109`); ≈ 0,49 s com hop 512 a 22 050 Hz | **não** |
| Agregação por batida | `fix_frames` + mediana (`legacy_v4.py:88-89`) | idem (`pipeline.py:111-112`) | sim |
| Normalização na decisão | divisão pelo **máximo** (`legacy_v4.py:30`) | norma **L2** do vetor e dos templates, cosseno (`classifier.py:96-98`, `:123-127`); o máximo só entra no viés pró-tríade (`classifier.py:130`) | **não** |
| Escore | soma de energia, 0,6 fora, `bias` 0,15 | cosseno − `complexity_penalty`·fator da extensão (0,06; `ext_sharpness` 4,0) (`classifier.py:127-137`, `config.py:81-82`) | **não** |
| Vocabulário | 24 (maior/menor) literal | 60 `MEDIUM` (C, D, E) / 24 `BASIC` (F) (`runner.py:197-200`, `chord_templates.py:51-52`) | só F coincide |
| Gate de silêncio | soma do chroma < 0,1 (`legacy_v4.py:29`) | **RMS do áudio original** por segmento (`pipeline.py:139-145`, `:150-155`), `gate = max(abs_floor=5e-4, rel_gate=0,2 · mediana)` (`pipeline.py:229-231`, `config.py:88-89`) | **não** |
| Outras fontes de N | nenhuma | `confidence_gate=0,72` em C (`classifier.py:152-153`); estado N com `n_logprob=−2,5` em D–F (`viterbi.py:77`); `force_n` sobrepõe ambos (`viterbi.py:78-80`, `pipeline.py:247-249`) | **não** |
| Modelo temporal | V4: guloso (+0,5 / −0,1); V4b: nenhum | C: nenhum (argmax por batida, `pipeline.py:245-251`); D–F: Viterbi, softmax `temp=0,1`, troca custa `change_penalty=2,0` (`viterbi.py:75`, `:83-84`) | **não** |
| Fusão de segmentos | **nenhuma** (`runner.py:355`, `:363-368`) | `_merge` de vizinhos iguais (`pipeline.py:158-167`, `:259`) | **não** |
| Absorção de curtos | nenhuma | `min_dur`: 0 em C, D, F; 0,8 s em E (`runner.py:183-186`, `pipeline.py:170-197`) | só C, D, F coincidem |
| Configuração | literais, fora de `config.py` | `PreChromaConfig`/`PostChromaConfig` | **não** |

Nota: a variante `A` (`runner.py:195`, `smooth=0`) tem front-end idêntico ao
de V4/V4b (HPSS 3,0, beat no percussivo, CQT 36, sem mediana, sync por
mediana). A diferença entre V4b e A está, portanto, inteiramente na decisão
(normalização, escore, vocabulário, gates de N, fusão), e não na extração.

---

## 8. Ambiguidades e determinismo

- **Determinismo.** Nenhum passo é estocástico: HPSS, `beat_track`,
  `chroma_cqt` (com estimativa de afinação) e o laço do classificador são
  determinísticos dado o áudio. O resultado depende das versões de
  librosa/numpy/scipy (o `.venv` tem librosa 0.11.0 e mir_eval 0.8.2); os
  defaults implícitos de `beat_track` e `chroma_cqt` não estão fixados no
  código dos baselines.
- **Empates.** Resolvidos pela ordem de varredura (comparação estrita), não
  por critério musical (§3).
- **Penalidade de "nome longo".** O nome descreve o código, mas o efeito é
  dependente da grafia em sustenidos (§4), o que deve ser dito se o artigo
  a apresentar como "viés pró-tríade maior".
- **`bias` e `required`.** Presentes no código, sem efeito no vocabulário
  ativo (§3).
- **`n_segmentos_est`.** Não comparável entre baselines (por batida) e C–F
  (fundido) (§2).
- **Gate de 0,1.** Escala do limiar depende da normalização interna do
  `chroma_cqt`; o comportamento descrito em §5 é inferência.

## 9. Baselines de terceiros: Chordino e madmom (pós-revisão)

Rodam como estão distribuídos, **sem nenhum parâmetro ajustado**, no
GuitarSet (validação e teste) e nas duas bases externas
(`baselines_externos.py`, `baselines/madmom_acordes.py`).

| | Chordino | madmom |
|---|---|---|
| versão | NNLS Chroma / Chordino, plugin versão 5 (Vamp Plugin Pack 2.0), via Sonic Annotator 1.7 | madmom 0.17.dev0, commit `27f032e` do GitHub (o 0.16.1 do PyPI não compila no Python 3.10) |
| componente | transform `vamp:nnls-chroma:chordino:simplechord` (`baselines/chordino_simplechord.n3`) | `CNNChordFeatureProcessor` + `CRFChordRecognitionProcessor`, modelos `models/chords/2016/chords_cnnfeat.pkl` e `chords_cnncrf.pkl` |
| parâmetros | defaults: step 2048, block 16384, `useNNLS` 1, `rollon` 0, `tuningmode` 0 (global), `whitening` 1, `s` 0,7, `boostn` 0,1 | defaults do processador (100 fps na entrada da CNN, 10 fps na saída) |
| vocabulário de saída | maior, menor, `dim`, `aug`, `6`, `m6`, `7`, `maj7`, `m7`, `m7b5`, com baixo; `N` | 24 (maior, menor) + `N` |
| ambiente | binário Windows | venv separado: Python 3.10.20, numpy 1.26.4, scipy 1.15.3 (`data/cache/baselines/madmom/versoes.json`) |
| treino | sem treino (templates fixos sobre o NNLS chroma) | ver abaixo |

**Corpora de treino do madmom.** A documentação oficial do madmom
(docstrings de `CNNChordFeatureProcessor` e `CRFChordRecognitionProcessor`)
remete a Korzeniowski e Widmer, *A Fully Convolutional Deep Auditory Model
for Musical Chord Recognition*, MLSP 2016 (arXiv:1612.05082). O artigo, §4,
usa um conjunto composto: **Isophonics** (180 faixas dos Beatles, 19 do
Queen, 18 do Zweieck; 10 h 21 min), **RWC Popular** (100 faixas; 6 h 46 min)
e **Robbie Williams** (65 faixas; 4 h 30 min), em validação cruzada de 8
partes. **Não inclui GuitarSet** (publicado em 2018, depois do modelo) **nem
IDMT-SMT-Guitar ou IDMT-SMT-Chords.** Ressalva: nem a documentação nem o
artigo dizem se o modelo distribuído foi treinado no conjunto inteiro ou numa
das 8 partes; em qualquer caso, os corpora são esses. Os modelos do madmom
são CC BY-NC-SA 4.0 (`madmom/models/README.rst`).

**Avaliação.** Os rótulos dos dois já saem em Harte e passam pelo mesmo
mir_eval, com as mesmas referências e colunas do runner (`est_is_harte:
true` no meta). Segmentos estimados inteiramente fora do intervalo da
referência são descartados antes (o mir_eval já os corta; ver
`docs/ADENDO_REVISAO.md` §8, desvio registrado).
