# Definição dos templates de acordes

Fonte: `chord_templates.py`. Tudo abaixo é gerado a partir de `CHORD_TYPES`,
`NOTE_NAMES` e `build_templates()`; nada é definido à mão fora do código.

## 1. Como um template é construído

- `NOTE_NAMES = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']` — índice 0 = C. Só sustenidos (não há `Db`, `Eb`…).
- Um **tipo** de acorde é uma lista de intervalos em semitons a partir da tônica (`CHORD_TYPES[sufixo]`).
- `template_vector(root_pc, sufixo)` = vetor de 12 posições com `1.0` em `(root_pc + intervalo) % 12` para cada intervalo, `0.0` no resto.
- O nome é `NOTE_NAMES[root_pc] + sufixo` (`chord_name`). Sufixo vazio = maior (`'C'`), igual ao V4.
- `build_templates(sufixos)` gera `{nome: vetor}` para as 12 tônicas de cada sufixo. `None` = todos os 13 tipos (156 templates).
- No classificador (`CosineChordClassifier.__init__`) cada linha é normalizada para norma L2 = 1 (tríade ÷ √3, tétrade ÷ √4). A classificação é `argmax(M @ chroma/‖chroma‖)`.

## 2. Os 13 tipos disponíveis (`CHORD_TYPES`)

| Sufixo | Intervalos | Nome | Grupo |
|---|---|---|---|
| `''` | 0 4 7 | maior | TRIADS, BASIC, MEDIUM |
| `m` | 0 3 7 | menor | TRIADS, BASIC, MEDIUM |
| `dim` | 0 3 6 | diminuto | TRIADS |
| `aug` | 0 4 8 | aumentado | TRIADS |
| `sus2` | 0 2 7 | suspenso 2 | TRIADS |
| `sus4` | 0 5 7 | suspenso 4 | TRIADS |
| `7` | 0 4 7 10 | dominante com 7 | TETRADS, MEDIUM |
| `maj7` | 0 4 7 11 | maior com 7M | TETRADS, MEDIUM |
| `m7` | 0 3 7 10 | menor com 7 | TETRADS, MEDIUM |
| `6` | 0 4 7 9 | maior com 6 | TETRADS |
| `m6` | 0 3 7 9 | menor com 6 | TETRADS |
| `dim7` | 0 3 6 9 | diminuto com 7 dim | TETRADS |
| `m7b5` | 0 3 6 10 | meio-diminuto | TETRADS |

Subconjuntos prontos:

| Nome | Sufixos | Templates | Usado por |
|---|---|---|---|
| `BASIC` | `''`, `m` | 24 | Referência do que o V4 cobre |
| `MEDIUM` | `''`, `m`, `7`, `maj7`, `m7` | **60** | `musicas.py`, `benchmark_musicas.py`, `pipeline.py` (smoke test), API |
| `TRIADS` | 6 tríades | 72 | `run_bench.py` (junto com TETRADS) |
| `TETRADS` | 7 tétrades | 84 | `run_bench.py` |
| todos | 13 tipos | 156 | `CosineChordClassifier()` sem argumento |

## 3. Ambiguidades (templates idênticos)

Dentro de **MEDIUM não há nenhum par de templates iguais** — os 60 vetores são
distintos. Fora dele, os seguintes acordes têm exatamente o mesmo conjunto de
pitch-classes e são indistinguíveis por chroma (o chroma dobra oitavas e descarta
o baixo); o bench os reporta como "erros" que na verdade são empates:

| Par | Notas | Motivo |
|---|---|---|
| `Xsus2` = `(X+7)sus4` | ex.: Csus2 = Gsus4 = {C, D, G} | rotação |
| `Xm7` = `(X+3)6` | ex.: Cm7 = D#6 = {C, D#, G, A#}; Am7 = C6 | rotação |
| `Xm7b5` = `(X+3)m6` | ex.: Cm7b5 = D#m6 | rotação |
| `Xaug` = `(X+4)aug` = `(X+8)aug` | ex.: Caug = Eaug = G#aug | simetria (3 raízes → ~33 % de acerto) |
| `Xdim7` = 4 raízes | ex.: Cdim7 = D#dim7 = F#dim7 = Adim7 | simetria (4 raízes → ~25 %) |

Solução apontada no README: detecção de baixo/raiz (PYIN) para desempatar.

## 4. Como adicionar um tipo

Uma linha em `CHORD_TYPES` (ex.: `'add9': [0, 2, 4, 7]`), opcionalmente
incluí-lo em um subconjunto. Nada mais precisa ser re-tunado — é a razão de
usar cosseno. Atenção:

- `evaluate.py::_QUALITY_MAP` precisa da tradução para a notação mir_eval do novo sufixo, senão o label vira `'X'` e é ignorado na pontuação.
- `classifier.py` procura a "nota de extensão" como o maior intervalo ≥ 8 do tipo (para o viés adaptativo). Um tipo sem intervalo ≥ 8 não recebe penalidade.
- A cópia standalone da API (`Api/audio_processing_v2.py`) tem seu **próprio** `CHORD_TYPES` (só MEDIUM) e precisa ser atualizada separadamente.

## 5. Os 60 templates do vocabulário MEDIUM

Ordem = ordem de `build_templates(MEDIUM)`, que é a ordem das colunas na
matriz de emissão do Viterbi (`classifier.names`). Coluna 60 (não listada)
é o estado `N` adicionado por `viterbi.decode`.

### maior (`''`, intervalos [0, 4, 7])

| # | Nome | Notas | Vetor (C C# D D# E F F# G G# A A# B) |
|---|---|---|---|
| 0 | C | C E G | `1 0 0 0 1 0 0 1 0 0 0 0` |
| 1 | C# | C# F G# | `0 1 0 0 0 1 0 0 1 0 0 0` |
| 2 | D | D F# A | `0 0 1 0 0 0 1 0 0 1 0 0` |
| 3 | D# | D# G A# | `0 0 0 1 0 0 0 1 0 0 1 0` |
| 4 | E | E G# B | `0 0 0 0 1 0 0 0 1 0 0 1` |
| 5 | F | F A C | `1 0 0 0 0 1 0 0 0 1 0 0` |
| 6 | F# | F# A# C# | `0 1 0 0 0 0 1 0 0 0 1 0` |
| 7 | G | G B D | `0 0 1 0 0 0 0 1 0 0 0 1` |
| 8 | G# | G# C D# | `1 0 0 1 0 0 0 0 1 0 0 0` |
| 9 | A | A C# E | `0 1 0 0 1 0 0 0 0 1 0 0` |
| 10 | A# | A# D F | `0 0 1 0 0 1 0 0 0 0 1 0` |
| 11 | B | B D# F# | `0 0 0 1 0 0 1 0 0 0 0 1` |

### menor (`'m'`, intervalos [0, 3, 7])

| # | Nome | Notas | Vetor (C C# D D# E F F# G G# A A# B) |
|---|---|---|---|
| 12 | Cm | C D# G | `1 0 0 1 0 0 0 1 0 0 0 0` |
| 13 | C#m | C# E G# | `0 1 0 0 1 0 0 0 1 0 0 0` |
| 14 | Dm | D F A | `0 0 1 0 0 1 0 0 0 1 0 0` |
| 15 | D#m | D# F# A# | `0 0 0 1 0 0 1 0 0 0 1 0` |
| 16 | Em | E G B | `0 0 0 0 1 0 0 1 0 0 0 1` |
| 17 | Fm | F G# C | `1 0 0 0 0 1 0 0 1 0 0 0` |
| 18 | F#m | F# A C# | `0 1 0 0 0 0 1 0 0 1 0 0` |
| 19 | Gm | G A# D | `0 0 1 0 0 0 0 1 0 0 1 0` |
| 20 | G#m | G# B D# | `0 0 0 1 0 0 0 0 1 0 0 1` |
| 21 | Am | A C E | `1 0 0 0 1 0 0 0 0 1 0 0` |
| 22 | A#m | A# C# F | `0 1 0 0 0 1 0 0 0 0 1 0` |
| 23 | Bm | B D F# | `0 0 1 0 0 0 1 0 0 0 0 1` |

### dominante 7 (`'7'`, intervalos [0, 4, 7, 10])

| # | Nome | Notas | Vetor (C C# D D# E F F# G G# A A# B) |
|---|---|---|---|
| 24 | C7 | C E G A# | `1 0 0 0 1 0 0 1 0 0 1 0` |
| 25 | C#7 | C# F G# B | `0 1 0 0 0 1 0 0 1 0 0 1` |
| 26 | D7 | D F# A C | `1 0 1 0 0 0 1 0 0 1 0 0` |
| 27 | D#7 | D# G A# C# | `0 1 0 1 0 0 0 1 0 0 1 0` |
| 28 | E7 | E G# B D | `0 0 1 0 1 0 0 0 1 0 0 1` |
| 29 | F7 | F A C D# | `1 0 0 1 0 1 0 0 0 1 0 0` |
| 30 | F#7 | F# A# C# E | `0 1 0 0 1 0 1 0 0 0 1 0` |
| 31 | G7 | G B D F | `0 0 1 0 0 1 0 1 0 0 0 1` |
| 32 | G#7 | G# C D# F# | `1 0 0 1 0 0 1 0 1 0 0 0` |
| 33 | A7 | A C# E G | `0 1 0 0 1 0 0 1 0 1 0 0` |
| 34 | A#7 | A# D F G# | `0 0 1 0 0 1 0 0 1 0 1 0` |
| 35 | B7 | B D# F# A | `0 0 0 1 0 0 1 0 0 1 0 1` |

### maior 7M (`'maj7'`, intervalos [0, 4, 7, 11])

| # | Nome | Notas | Vetor (C C# D D# E F F# G G# A A# B) |
|---|---|---|---|
| 36 | Cmaj7 | C E G B | `1 0 0 0 1 0 0 1 0 0 0 1` |
| 37 | C#maj7 | C# F G# C | `1 1 0 0 0 1 0 0 1 0 0 0` |
| 38 | Dmaj7 | D F# A C# | `0 1 1 0 0 0 1 0 0 1 0 0` |
| 39 | D#maj7 | D# G A# D | `0 0 1 1 0 0 0 1 0 0 1 0` |
| 40 | Emaj7 | E G# B D# | `0 0 0 1 1 0 0 0 1 0 0 1` |
| 41 | Fmaj7 | F A C E | `1 0 0 0 1 1 0 0 0 1 0 0` |
| 42 | F#maj7 | F# A# C# F | `0 1 0 0 0 1 1 0 0 0 1 0` |
| 43 | Gmaj7 | G B D F# | `0 0 1 0 0 0 1 1 0 0 0 1` |
| 44 | G#maj7 | G# C D# G | `1 0 0 1 0 0 0 1 1 0 0 0` |
| 45 | Amaj7 | A C# E G# | `0 1 0 0 1 0 0 0 1 1 0 0` |
| 46 | A#maj7 | A# D F A | `0 0 1 0 0 1 0 0 0 1 1 0` |
| 47 | Bmaj7 | B D# F# A# | `0 0 0 1 0 0 1 0 0 0 1 1` |

### menor 7 (`'m7'`, intervalos [0, 3, 7, 10])

| # | Nome | Notas | Vetor (C C# D D# E F F# G G# A A# B) |
|---|---|---|---|
| 48 | Cm7 | C D# G A# | `1 0 0 1 0 0 0 1 0 0 1 0` |
| 49 | C#m7 | C# E G# B | `0 1 0 0 1 0 0 0 1 0 0 1` |
| 50 | Dm7 | D F A C | `1 0 1 0 0 1 0 0 0 1 0 0` |
| 51 | D#m7 | D# F# A# C# | `0 1 0 1 0 0 1 0 0 0 1 0` |
| 52 | Em7 | E G B D | `0 0 1 0 1 0 0 1 0 0 0 1` |
| 53 | Fm7 | F G# C D# | `1 0 0 1 0 1 0 0 1 0 0 0` |
| 54 | F#m7 | F# A C# E | `0 1 0 0 1 0 1 0 0 1 0 0` |
| 55 | Gm7 | G A# D F | `0 0 1 0 0 1 0 1 0 0 1 0` |
| 56 | G#m7 | G# B D# F# | `0 0 0 1 0 0 1 0 1 0 0 1` |
| 57 | Am7 | A C E G | `1 0 0 0 1 0 0 1 0 1 0 0` |
| 58 | A#m7 | A# C# F G# | `0 1 0 0 0 1 0 0 1 0 1 0` |
| 59 | Bm7 | B D F# A | `0 0 1 0 0 0 1 0 0 1 0 1` |

## 6. Mapeamento para mir_eval (`evaluate.py::_QUALITY_MAP`)

| Projeto | mir_eval | | Projeto | mir_eval |
|---|---|---|---|---|
| `''` | `X` (tônica nua = maj) | | `7` | `X:7` |
| `m` | `X:min` | | `maj7` | `X:maj7` |
| `dim` | `X:dim` | | `m7` | `X:min7` |
| `aug` | `X:aug` | | `6` | `X:maj6` |
| `sus2` | `X:sus2` | | `m6` | `X:min6` |
| `sus4` | `X:sus4` | | `dim7` | `X:dim7` |
| `N`, `''`, `N/A`, `None` | `N` | | `m7b5` | `X:hdim7` |

Sufixo desconhecido → `'X'` (mir_eval ignora na ponderação).
