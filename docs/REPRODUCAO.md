# Reprodução dos resultados do artigo

Cópia de exportação do repositório DecifraViolão (módulo de reconhecimento de
acordes). Contém código, manifests, CSVs de resultado e o material do artigo.
**Não contém áudio, datasets nem caches**: baixe as bases da fonte original.

## 1. Ambiente

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt -r requirements-dev.txt   # Windows
# .venv/bin/python -m pip install ...                                            # Linux/macOS
python -m pytest -q          # sanidade: a suíte não precisa de áudio
```

Todos os scripts rodam **de dentro da pasta raiz** (imports por nome de
arquivo, sem pacote). No Windows, use `PYTHONIOENCODING=utf-8`.

## 2. Dados

Baixe e descompacte conforme `docs/DATASETS.md`, mantendo os caminhos
relativos dos manifests:

| base | onde | manifest |
|---|---|---|
| GuitarSet (CC BY 4.0) | `data/raw/guitarset/` → `data/extracted/guitarset/` | `data/manifests/guitarset_comping.csv` |
| IDMT-SMT-Chords (CC BY-NC-ND 4.0) | `data/raw/idmt-smt-chords/` → `data/extracted/idmt-smt-chords/` | `data/manifests/idmt_smt_chords.csv` |
| IDMT-SMT-Guitar V2, subconjunto 4 | `data/raw/idmt-smt-guitar/` → `data/extracted/idmt-smt-guitar/IDMT-SMT-GUITAR_V2/` | `data/manifests/idmt_smt_guitar.csv` |

Splits e exclusões estão nos manifests e em `artigo-ACDSA/splits/`.

## 3. Pipeline

```bash
# features (HPSS, beat tracking, CQT) em cache; a etapa cara
python cache.py --manifest data/manifests/guitarset_comping.csv

# variantes congeladas (val; o teste é pedido explicitamente)
python runner.py --manifest data/manifests/guitarset_comping.csv --splits val --ref-layer 1
python runner.py --manifest data/manifests/guitarset_comping.csv --splits test --ref-layer 1

# estatística dos 15 contrastes sobre um CSV de ablação
python stats.py --csv data/results/ablation_<ts>_ref1.csv
```

Análises pós-revisão (`--post-review` marca o meta.json):

```bash
python runner.py --manifest data/manifests/idmt_smt_guitar.csv --splits external --ref-layer 0 --post-review
python runner.py --manifest data/manifests/idmt_smt_chords.csv --splits eval --ref-layer 0 --post-review
python analise_externo.py        # tab_externo, tab_transferencia, fig_transferencia
python diagnostico_n.py          # fig_diagnostico_n
python beat_tracking_idmt.py
python tabelas_curtas.py         # tab_principal, tab_transferencia_curta
```

Baselines de terceiros: Chordino via Sonic Annotator e madmom num ambiente
separado; versões e comandos em `artigo-ACDSA/BASELINES.md` §9 e
`baselines_externos.py --help`.

## 4. Onde está cada número

- Protocolo e congelamento: `docs/CONGELAMENTO.md`, `docs/ADENDO_REVISAO.md`.
- Método e resultados: `artigo-ACDSA/METODOLOGIA.md`, `RESULTADOS.md`; cada
  número cita o CSV de `data/results/` de onde sai, e cada CSV tem um
  `_meta.json` com commit, configuração e seeds.
- Tabelas e figuras: `artigo-ACDSA/tabelas/`, `artigo-ACDSA/figuras/`.

O pipeline é determinístico; com as mesmas versões de bibliotecas, as
rodadas reproduzem os CSVs. `benchmark_musicas.py` (oráculo de regressão
interno) depende de gravações comerciais que **não** são distribuídas e não
roda nesta cópia.
