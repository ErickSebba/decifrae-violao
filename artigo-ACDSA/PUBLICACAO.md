# Exportação pública: o que entra e o que não entra

> Lista para uma eventual exportação pública do material do artigo. **Nada foi
> publicado.** Levantado em 2026-11-17 na branch `revisao-camera-ready`, a
> partir de `git ls-files` (195 arquivos rastreados) e do `.gitignore`.

## ⚠ Bloqueio antes de qualquer exportação

Os cinco áudios de `Musicas/` **estão rastreados no Git**, apesar de o
`CLAUDE.md` mandar não commitá-los (são gravações comerciais):

```
Musicas/Boate azul (Am) 2.mp3
Musicas/Re_2.mp3
Musicas/Sol_1.mp3
Musicas/Tempo_Perdido.mp3
Musicas/TrocaDeAcordes(C-G-A-F).mp3
```

Eles entraram nos commits `e426941` e `515ff45` e estão no **histórico**.
Consequência: o repositório **não pode ser publicado como está** (nem por push
para um remoto público, nem por cópia do `.git`). Há duas saídas, e as duas
são decisão do autor:

1. exportar só uma árvore limpa (cópia dos arquivos listados abaixo, sem
   `.git`, ou `git archive` com os caminhos permitidos), **ou**
2. reescrever o histórico para remover `Musicas/` antes de publicar.

Nenhuma das duas foi feita.

## Entra (código, configs, manifests, resultados, artigo)

| grupo | caminhos | observação |
|---|---|---|
| núcleo do pipeline | `chord_templates.py`, `classifier.py`, `viterbi.py`, `pipeline.py`, `evaluate.py`, `config.py`, `cache.py`, `dataset_io.py`, `legacy_v4.py` | `legacy_v4.py` é o baseline V4 |
| experimentos | `runner.py`, `stats.py`, `curvas.py`, `mascara_comum.py`, `coverage_report.py`, `congelar.py`, `calibracao_revisao.py`, `curvas_teste_revisao.py`, `analise_executantes.py`, `analise_fatorial.py`, `analise_decomposicao.py`, `analise_vocabulario.py` | |
| figuras e tabelas | `figuras_artigo.py`, `figura_curvas.py`, `tabelas_artigo.py` | |
| bench | `benchmark_musicas.py`, `musicas.py`, `run_bench.py`, `bench.py`, `synth.py`, `noise.py` | `benchmark_musicas.py` e `musicas.py` leem `Musicas/` — publicáveis como código, mas não rodam sem os áudios |
| testes | `tests/*.py` | |
| dependências | `requirements.txt`, `requirements-dev.txt` | |
| manifests | `data/manifests/guitarset_comping.csv`, `data/manifests/idmt_smt_chords.csv` | só caminhos, splits e exclusões; nenhum áudio |
| resultados | `data/results/*.csv`, `data/results/*_meta.json` | métricas agregadas e por faixa; nenhum áudio nem rótulo de referência bruto |
| documentação | `README.md`, `CLAUDE.md`, `docs/*.md` | `docs/GROUND_TRUTH.md` traz as anotações do projeto para `Musicas/` (são do projeto e podem ir; os áudios não) |
| artigo | `artigo-ACDSA/METODOLOGIA.md`, `RESULTADOS.md`, `REVISAO.md`, `ESPECIFICACAO.md`, `BASELINES.md`, `PUBLICACAO.md`, `artigo-ACDSA/figuras/*`, `artigo-ACDSA/tabelas/*`, `artigo-ACDSA/splits/*.txt` | |
| oráculo e logs | `out/musicas_bench/metrics.json`, `out/logs/*.txt` | o oráculo é só métricas |

Nota: a menção a `classifier_V2.py` no mapa de módulos do `CLAUDE.md` foi
removida (o arquivo não existe).

## Decisão do autor (não listado como "entra" nem como "não entra")

| caminho | por quê |
|---|---|
| `out/musicas/*_timeline.png`, `out/musicas_bench/comparativo.png`, `out/*.png` | figuras derivadas das gravações comerciais (chromagramas e linhas do tempo); não são o áudio, mas derivam dele |
| `Api/` | cópia standalone fora do escopo do artigo (`CLAUDE.md`) |
| `artigo-ACDSA/slides-ACDSA/`, `artigo-ACDSA/slides-ACDSA.zip` | não rastreados; material de apresentação do autor |

## Não entra

| caminho | motivo |
|---|---|
| `Musicas/` (todos os `.mp3`) | gravações comerciais; não redistribuir (`CLAUDE.md`) — **hoje rastreados, ver bloqueio acima** |
| `data/raw/` | downloads originais do GuitarSet e do IDMT (3,3 GB); redistribuição fora do escopo, o leitor baixa da fonte (`docs/DATASETS.md`) |
| `data/extracted/` | áudio e JAMS extraídos (2,9 GB); mesmo motivo |
| `data/cache/` | features `.npz` derivadas do áudio; regeneráveis com `cache.py` |
| `data/raw/guitar-techs/` (Guitar-TECHS, CC BY 4.0) | não usado nesta versão; o leitor baixa da fonte (`docs/DATASETS.md` §6) |
| `.venv/`, `__pycache__/`, `.pytest_cache/`, `.claude/` | ambiente local |

## Licenças a citar numa exportação

- GuitarSet: CC BY 4.0, citação obrigatória (`METODOLOGIA.md` §1.4).
- IDMT-SMT-Chords: conferir a licença da distribuição original antes de
  publicar qualquer manifest que aponte para ele (`docs/DATASETS.md`).

## Cópia limpa exportada (2026-11-17)

Gerada em `..\Decifra-Violao-publico` por `git archive` do commit `e525f0d`
(só arquivos rastreados), mais `README_REPRODUCAO.md` (cópia de
`docs/REPRODUCAO.md`). **Nenhum repositório remoto foi criado; nada foi
publicado.**

- Fora da cópia: `.git`, `Musicas/`, `data/raw/`, `data/extracted/`,
  `data/cache/` (os três últimos nem são rastreados), e, por precaução, os
  itens de "decisão do autor": `Api/`, `out/musicas/*_timeline.png` e
  `out/musicas_bench/comparativo.png`.
- Verificado: 265 arquivos, 12 MB, **nenhum** `.wav`, `.mp3`, `.flac` (nem
  outro formato de áudio); tipos presentes: csv, json, py, md, tex, png, pdf,
  txt, n3.
- Na cópia, `pytest`: 223 passam e 27 são pulados (precisam dos dados).
- O bloqueio do histórico continua valendo para o repositório: a cópia não
  tem `.git`, então não carrega os `.mp3` dos commits `e426941` e `515ff45`.
