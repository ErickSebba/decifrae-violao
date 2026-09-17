# Benchmarks — scripts, saídas brutas e uso como teste de regressão

Há dois benchmarks independentes. O de **áudio real** é o que protege uma
refatoração (tem ground truth e é determinístico); o **sintético** mede
propriedades do classificador isolado.

## 1. Benchmark em áudio real (`benchmark_musicas.py`)

### O que faz

Para cada faixa em `GROUND_TRUTH` (Tempo Perdido, Boate Azul):

1. `librosa.load(sr=22050, mono)`.
2. `run_v4`: HPSS → `legacy_v4.run_beat_tracking` → segmentos do V4 (`''`/`N/A` → `N`).
3. `run_atual`: `pipeline.analyze_track(y, sr, _cos, use_viterbi=True, change_penalty=2.0, rel_gate=0.2, min_dur=0.8)` com `_cos = CosineChordClassifier(MEDIUM, complexity_penalty=0.06, ext_sharpness=4.0)`.
4. `evaluate.score_segments` em 4 níveis mir_eval: `root`, `majmin`, `sevenths`, `mirex`.
5. Tabela no terminal, `out/musicas_bench/comparativo.png`, `out/musicas_bench/metrics.json`.

### Como rodar

```bash
python benchmark_musicas.py     # ~1–2 min; precisa de mir_eval
```

### Saída bruta atual (`out/musicas_bench/metrics.json`, gerado 29/06/2026)

```json
{
  "Tempo_Perdido": {
    "v4":    {"root": 0.787935731037597,  "majmin": 0.787935731037597,  "sevenths": 0.787935731037597,  "mirex": 0.787935731037597},
    "atual": {"root": 0.9821876502206878, "majmin": 0.9821876502206878, "sevenths": 0.9821876502206878, "mirex": 0.9821876502206878}
  },
  "Boate_azul__Am__2": {
    "v4":    {"root": 0.8468119927372086, "majmin": 0.6300469318686006, "sevenths": 0.5029588500345934, "mirex": 0.6300469318686006},
    "atual": {"root": 0.9407682122926609, "majmin": 0.905995315007779,  "sevenths": 0.7856858386100956, "mirex": 0.905995315007779}
  }
}
```

**Reprodutibilidade verificada em 17/09/2026**: re-executado no mesmo ambiente
(Python 3.14.6, librosa 0.11.0), `metrics.json` e `comparativo.png` saíram
**byte a byte idênticos** aos de 29/06 (`git diff` vazio). Log em
`out/logs/benchmark_musicas_2026-09-17.txt`.

### Uso como teste de regressão

Enquanto o pipeline não muda de comportamento, o `metrics.json` commitado é o
oráculo. Procedimento após qualquer refatoração:

```bash
python benchmark_musicas.py
git diff --exit-code out/musicas_bench/metrics.json   # 0 = sem regressão
```

Regras:

- Comparação exata funciona porque o pipeline é determinístico (sem seed
  aleatória; beat tracking, CQT e Viterbi são determinísticos). Se uma
  mudança de versão do librosa alterar o beat tracking, os números mudam sem
  ser regressão — nesse caso, regenerar o oráculo e registrar a versão.
- Uma refatoração "pura" (mover módulos, unificar `classifier`/`classifier_V2`,
  centralizar hiperparâmetros) **deve** dar diff vazio.
- Uma mudança de hiperparâmetro ou de algoritmo deve ser justificada por
  melhora em pelo menos um nível sem piorar os outros; atualizar o
  `metrics.json` no mesmo commit.
- Só há 2 faixas anotadas. Ver [GROUND_TRUTH.md](GROUND_TRUTH.md) §5 para
  adicionar mais.

Uma versão em `pytest` seria: carregar `metrics.json`, rodar `run_atual` nas
duas faixas e afirmar igualdade com tolerância 1e-9 por nível. Não existe
ainda (sem `tests/` no projeto).

## 2. Bench sintético (`run_bench.py`)

### O que faz

Compara `CosineChordClassifier` (de `classifier_V2.py`, `complexity_penalty=0`,
vocabulário = todos os 13 tipos) com `classificar_segmento_v4` em três
baterias, usando acordes gerados por `synth.py`:

1. **Bench principal**: (raízes × 13 tipos × condições de ruído). Com
   `QUICK=True`: raízes C, D#, F#, A e 7 condições (sem detune) = 364 casos
   por classificador. Reporta acurácia por condição, por tipo, top confusões,
   matrizes de confusão por tipo.
2. **Teste de pausa**: 30 pausas com ruído em 4 amplitudes; mede % rotulada
   como acorde (ideal 0 %).
3. **Varredura de harmônicos**: acurácia em maj/m/7/maj7 com 1 a 12
   harmônicos por nota, sem ruído.

### Como rodar

```bash
python run_bench.py     # ~2 min com QUICK=True; saídas em out/
```

Gera `out/confusao_cosseno.png`, `out/confusao_v4.png`,
`out/acuracia_cosseno.png`, `out/varredura_harmonicos.png`.

### Saída bruta atual (`out/logs/run_bench_2026-09-17.txt`)

Estes PNGs e o log **não existiam no disco** quando o repositório foi criado
(só os do bench de áudio real). Foram gerados em 17/09/2026 e commitados como
linha de base.

Acurácia por condição (QUICK, 364 casos):

| Condição | Cosseno | V4 |
|---|---:|---:|
| clean, white_30dB, white_15dB, white_5dB, pink_15dB, percussive, reverb | 67,3 % | 15,4 % |

(igual em todas as condições — o ruído sintético não muda o resultado;
o que limita o cosseno são as ambiguidades teóricas, e o V4 só conhece maj/m.)

Acurácia por tipo:

| Tipo | Cosseno | V4 | Explicação |
|---|---:|---:|---|
| maj, m | 100 % | 100 % | |
| 7, maj7, m7, m6, dim, sus2 | 100 % | 0 % | V4 não tem esses tipos |
| aug | 50 % | 0 % | simetria (3 raízes) |
| dim7 | 25 % | 0 % | simetria (4 raízes) |
| 6 | 0 % | 0 % | `X6` = `(X+9)m7`, o m7 vence o empate |
| sus4 | 0 % | 0 % | `Xsus4` = `(X+5)sus2` |
| m7b5 | 0 % | 0 % | `Xm7b5` = `(X+3)m6` |

Top confusões (7× cada = 1 raiz × 7 condições): `Csus4→Fsus2`, `C6→Am7`,
`Cm7b5→D#m6`, `D#sus4→G#sus2`, `D#6→Cm7`, `D#dim7→Cdim7`, `D#m7b5→F#m6`,
`F#aug→Daug`, `F#sus4→Bsus2`, `F#6→D#m7`. Todas são pares de templates
idênticos (ver [TEMPLATES_ACORDES.md](TEMPLATES_ACORDES.md) §3), não erros.

Teste de pausa (% rotulada como acorde):

| Ruído | Cosseno | V4 |
|---|---:|---:|
| 0.005 | 0 % | 0 % |
| 0.010 | 0 % | 0 % |
| 0.020 | 0 % | 36,7 % |
| 0.050 | 0 % | 100 % |

Varredura de harmônicos (1–12): cosseno 100 % em todos; V4 50 % em todos
(acerta maj/m, erra 7/maj7).

### Como usar

O bench sintético é útil para validar uma mudança em `chord_templates.py` ou
no classificador (ex.: novo tipo de acorde, mudança no viés pró-tríade),
não para regressão do pipeline completo (não passa por beat-sync nem Viterbi).
A comparação de regressão é o log: mesmas tabelas ⇒ mesmo comportamento.
Nota: o script imprime em cp1252 no console do Windows; o log arquivado foi
convertido para UTF-8.

## 3. Outros pontos de entrada com auto-teste

| Comando | Verifica |
|---|---|
| `python chord_templates.py` | 24 templates BASIC, vetores de C, C7, Cmaj7 |
| `python classifier.py` | C, Cm, C7, Cmaj7, Cm7 sintéticos → OK; pausa → N |
| `python viterbi.py` | flicker C/Cmaj7 colapsa em C com Viterbi |
| `python pipeline.py` | faixa sintética C(2s) G(2s) Am(2s) → 3 segmentos |
| `python evaluate.py` | GT vs GT = 100 %; trocar E7 por E derruba só `sevenths` |
| `python musicas.py` | timelines de todas as faixas de `Musicas/` (sem GT; inspeção visual) |
