# Anotações de ground truth (áudio real)

As anotações vivem **hardcoded** em `benchmark_musicas.py` (`GT_TEMPO`,
`GT_BOATE`, `GROUND_TRUTH`, `AUDIO_FILES`). Este documento as reproduz para
consulta e descreve o formato, para que novas faixas sejam anotadas do mesmo
jeito e sirvam de caso-teste no harness.

## 1. Formato

Lista de tuplas `(start_s, end_s, label)`:

- tempos em segundos (float), contíguos, começando em 0.0;
- `label` no vocabulário do projeto: tônica em `NOTE_NAMES` (só sustenidos: `A#`, não `Bb`) + sufixo de `CHORD_TYPES` (`''` maior, `m`, `7`, `maj7`, `m7`…);
- `'N'` para trechos sem acorde (intro instrumental, silêncio, fala);
- `evaluate.py` traduz para mir_eval (`Am` → `A:min`, `E7` → `E:7`) e o próprio mir_eval reamostra estimativa e referência numa grade comum — lacunas viram `N`.

`GROUND_TRUTH = {chave: lista}`; o áudio é `Musicas/<chave>.mp3`, salvo se a
chave estiver em `AUDIO_FILES` (mapeia para o nome real com espaços/parênteses).

## 2. Tempo Perdido (`Musicas/Tempo_Perdido.mp3`, 46,7 s anotados)

Cifra conhecida: **C Am Bm Em** em loop. Intro instrumental = N. Só tríades —
por isso os 4 níveis do mir_eval dão o mesmo número nessa faixa.

| Início | Fim | Acorde | | Início | Fim | Acorde |
|---:|---:|---|---|---:|---:|---|
| 0.0 | 6.0 | N | | 23.7 | 26.3 | Am |
| 6.0 | 10.5 | C | | 26.3 | 30.0 | Bm |
| 10.5 | 13.1 | Am | | 30.0 | 33.2 | Em |
| 13.1 | 16.5 | Bm | | 33.2 | 37.4 | C |
| 16.5 | 19.9 | Em | | 37.4 | 39.9 | Am |
| 19.9 | 23.7 | C | | 39.9 | 43.6 | Bm |
| | | | | 43.6 | 46.7 | Em |

Nota do código: gravação com RMS ≈ 0,01. Com gate absoluto a faixa saía 100 % N;
foi o caso que motivou o gate relativo (`REL_GATE`).

## 3. Boate Azul (`Musicas/Boate azul (Am) 2.mp3`, chave `Boate_azul__Am__2`, 193,7 s anotados)

Cifra em Am. Verso: Am G F E7 Dm Am E7 Am A7 (com variações); refrão modula
para Lá maior: E D A. **Timing aproximado**, anotado sobre a estrutura da faixa
(comentário do próprio arquivo). Contém tétrades reais (E7, A7), o que faz o
nível `sevenths` ser informativo aqui.

### Intro

| Início | Fim | Acorde |
|---:|---:|---|
| 0.0 | 9.4 | N |

### Verso 1

| Início | Fim | Acorde | | Início | Fim | Acorde |
|---:|---:|---|---|---:|---:|---|
| 9.4 | 11.5 | G | | 45.3 | 49.3 | E7 |
| 11.5 | 13.1 | C | | 49.3 | 52.7 | Dm |
| 13.1 | 15.3 | Am | | 52.7 | 56.1 | Am |
| 15.3 | 16.4 | Dm | | 56.1 | 58.9 | E7 |
| 16.4 | 18.2 | E7 | | 58.9 | 61.2 | Am |
| 18.2 | 20.4 | Am | | 61.2 | 62.3 | A7 |
| 20.4 | 21.5 | A7 | | 62.3 | 66.3 | Dm |
| 21.5 | 23.3 | Dm | | 66.3 | 69.1 | Am |
| 23.3 | 24.9 | G | | 69.1 | 72.5 | E7 |
| 24.9 | 26.6 | C | | 72.5 | 74.7 | Am |
| 26.6 | 28.9 | Am | | 74.7 | 75.9 | A7 |
| 28.9 | 30.0 | Dm | | 75.9 | 79.9 | Dm |
| 30.0 | 31.7 | E7 | | 79.9 | 82.7 | Am |
| 31.7 | 38.5 | Am | | 82.7 | 84.4 | F |
| 38.5 | 41.9 | G | | 84.4 | 86.0 | E7 |
| 41.9 | 45.3 | F | | | | |

### Refrão 1 (Lá maior)

| Início | Fim | Acorde | | Início | Fim | Acorde |
|---:|---:|---|---|---:|---:|---|
| 86.0 | 89.8 | A | | 103.2 | 104.8 | E |
| 89.8 | 91.5 | E | | 104.8 | 107.0 | D |
| 91.5 | 93.2 | D | | 107.0 | 109.8 | A |
| 93.2 | 96.6 | A | | 109.8 | 111.5 | E |
| 96.6 | 100.0 | E | | 111.5 | 113.2 | D |
| 100.0 | 103.2 | A | | 113.2 | 118.4 | A |

### Verso 2

| Início | Fim | Acorde | | Início | Fim | Acorde |
|---:|---:|---|---|---:|---:|---|
| 118.4 | 120.1 | G | | 137.0 | 140.4 | E7 |
| 120.1 | 121.8 | C | | 140.4 | 142.7 | Am |
| 121.8 | 124.1 | Am | | 142.7 | 144.4 | A7 |
| 124.1 | 125.2 | Dm | | 144.4 | 147.8 | Dm |
| 125.2 | 126.9 | E7 | | 147.8 | 151.1 | Am |
| 126.9 | 129.7 | Am | | 151.1 | 152.3 | F |
| 129.7 | 134.1 | Dm | | 152.3 | 154.4 | E7 |
| 134.1 | 137.0 | Am | | | | |

### Refrão 2 + final

| Início | Fim | Acorde | | Início | Fim | Acorde |
|---:|---:|---|---|---:|---:|---|
| 154.4 | 157.7 | A | | 171.3 | 172.9 | E |
| 157.7 | 158.8 | E | | 172.9 | 174.6 | D |
| 158.8 | 161.7 | D | | 174.6 | 178.1 | A |
| 161.7 | 164.5 | A | | 178.1 | 181.5 | E |
| 164.5 | 166.1 | E | | 181.5 | 193.7 | A |
| 166.1 | 167.9 | D | | | | |
| 167.9 | 171.3 | A | | | | |

## 4. Faixas em `Musicas/` sem ground truth formal

Estas têm só a descrição qualitativa do README (28/06) e a timeline em
`out/musicas/`; não entram em `benchmark_musicas.py`:

| Arquivo | Conteúdo esperado | Observação do README |
|---|---|---|
| `Sol_1.mp3` | G | "N (intro) + G limpo, sem flicker" |
| `Re_2.mp3` | D (pelo nome) | sem observação registrada |
| `TrocaDeAcordes(C-G-A-F).mp3` | C G A F | "na ordem, resíduos de transição ~0,9 s nas bordas" |

O README já sugeria anotar `TrocaDeAcordes` para um número publicável — é a
candidata mais fácil (4 acordes, trocas claras).

## 5. Como anotar uma faixa nova

1. Colocar o áudio em `Musicas/`.
2. Escrever a lista `(start, end, label)` como acima. Para timing, uma
   referência prática é rodar `python musicas.py` e ajustar as bordas da
   timeline gerada contra a escuta — mas **não** copiar os rótulos do pipeline
   (senão o GT mede o pipeline contra ele mesmo).
3. Registrar em `GROUND_TRUTH` (e em `AUDIO_FILES` se o nome tiver espaços).
4. Rodar `python benchmark_musicas.py`; os novos números entram em
   `out/musicas_bench/metrics.json` e no `comparativo.png`.
5. Copiar a tabela para este documento.
