"""
dataset_io.py
=============
Adaptadores de anotação dos datasets externos e gerador dos manifests.

As decisões (qual sinal, qual camada de acorde, quais faixas excluídas, quais
splits) estão em `docs/DATASETS.md`; aqui só a implementação delas.

Duas regras que valem para os dois adaptadores:

1. Os rótulos saem **em notação Harte, como estão no arquivo** -- nada de
   traduzir para o vocabulário do projeto ('Am', 'E7'). Quem pontua precisa
   chamar `evaluate.score_segments(..., ref_is_harte=True)`, senão a referência
   passa por `_QUALITY_MAP`, vira 'X' e o mir_eval a ignora.
2. A saída é uma lista contígua e ordenada de `(start, end, label)`: lacunas
   entre observações viram 'N', inclusive uma lacuna inicial antes da primeira
   observação.

Rodar `python dataset_io.py` imprime uma amostra das anotações para conferência
manual contra o áudio, e `build_manifests()` (re)escreve os dois CSVs.
"""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

GUITARSET_AUDIO = ROOT / "data" / "extracted" / "guitarset" / "audio_mono-mic"
GUITARSET_ANNOT = ROOT / "data" / "extracted" / "guitarset" / "annotation"
IDMT_ROOT = ROOT / "data" / "extracted" / "idmt-smt-chords" / "IDMT-SMT-CHORDS"
MANIFESTS = ROOT / "data" / "manifests"

NO_CHORD = 'N'

# Tolerância para tratar duas bordas como a mesma. As anotações do GuitarSet
# têm tempos como 7.441860465116279; a diferença entre o fim de uma observação
# e o início da seguinte fica na ordem de 1e-15 quando não há lacuna real.
EPS = 1e-9

# Índice da anotação de acorde a usar. docs/DATASETS.md §2: chord[1] é a
# camada performed/inferred (transcrição semi-automática verificada à mão);
# chord[0] é o lead sheet instruído.
CHORD_ANNOTATION_INDEX = 1

# docs/DATASETS.md §2: as duas anotações com tempo deslocado (issue #5 do
# GuitarSet). Ficam no manifest com excluded=true, não são omitidas.
GUITARSET_EXCLUDED = {
    "04_BN3-154-E_comp": "timing incorreto (+0,409 s), issue #5 do GuitarSet",
    "04_Jazz1-200-B_comp": "timing incorreto (+0,309 s), issue #5 do GuitarSet",
}

# docs/DATASETS.md §4: busca e ajuste só no split de validação.
GUITARSET_VAL_PLAYERS = {"00", "01", "02", "03"}
GUITARSET_TEST_PLAYERS = {"04", "05"}

MANIFEST_FIELDS = ["dataset", "track_id", "audio_path", "annotation_path",
                   "player_id", "split", "excluded", "exclude_reason"]


# ==========================================================================
# Utilidades comuns
# ==========================================================================
def _fill_gaps(observations, total_duration=None):
    """
    (start, end, label) ordenados -> lista contígua, com 'N' nas lacunas.

    observations   : iterável de (start, end, label), em qualquer ordem.
    total_duration : se dado e maior que o fim da última observação, fecha a
                     cauda com um 'N' até lá.
    """
    obs = sorted(observations, key=lambda o: (o[0], o[1]))
    segments = []
    cursor = 0.0
    for start, end, label in obs:
        if end - start <= EPS:
            continue                      # observação degenerada: ignora
        if start - cursor > EPS:
            segments.append((cursor, start, NO_CHORD))
        segments.append((start, end, label))
        cursor = end
    if total_duration is not None and total_duration - cursor > EPS:
        segments.append((cursor, float(total_duration), NO_CHORD))
    return segments


# ==========================================================================
# 1. GuitarSet (JAMS)
# ==========================================================================
def load_guitarset(jams_path, index=CHORD_ANNOTATION_INDEX):
    """
    Lê um JAMS do GuitarSet e devolve [(start, end, label_harte), ...].

    Por default usa a SEGUNDA anotação do namespace `chord` (chord[1]), a
    camada performed/inferred -- é a referência do benchmark. `index=0` lê o
    lead sheet instruído, útil só para comparar as duas camadas
    (ver `coverage_report.py`). O JAMS é lido como JSON puro -- o pacote `jams` não é
    dependência do projeto e o formato é JSON.
    """
    jams_path = Path(jams_path)
    with jams_path.open(encoding="utf-8") as fp:
        doc = json.load(fp)

    chord_anns = [a for a in doc.get("annotations", [])
                  if a.get("namespace") == "chord"]
    if len(chord_anns) <= index:
        raise ValueError(
            f"{jams_path.name}: esperava ao menos {index + 1} anotações no "
            f"namespace 'chord', encontrei {len(chord_anns)}"
        )

    observations = [
        (float(o["time"]), float(o["time"]) + float(o["duration"]), o["value"])
        for o in chord_anns[index]["data"]
    ]
    duration = doc.get("file_metadata", {}).get("duration")
    return _fill_gaps(observations, total_duration=duration)


# ==========================================================================
# 2. IDMT-SMT-Chords (.lab)
# ==========================================================================
def load_idmt_lab(lab_path):
    """
    Lê um .lab (início, fim, rótulo Harte) e devolve a mesma estrutura.

    O arquivo `guitar_annotation.lab` é único e vale para os 6 WAVs de
    `guitar/` -- são a mesma sequência de acordes renderizada com timbres
    diferentes. Sem duração declarada: a cobertura vai até o fim da última
    linha (que, nos 6 arquivos, é exatamente a duração do áudio).
    """
    lab_path = Path(lab_path)
    observations = []
    with lab_path.open(encoding="utf-8") as fp:
        for n, line in enumerate(fp, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 3:
                raise ValueError(
                    f"{lab_path.name}:{n}: esperava 'início fim rótulo', "
                    f"li {line!r}"
                )
            observations.append((float(parts[0]), float(parts[1]), parts[2]))
    return _fill_gaps(observations)


# ==========================================================================
# 3. Manifests
# ==========================================================================
def _relative(path):
    """Caminho relativo à raiz do projeto, com barras normais."""
    return Path(path).resolve().relative_to(ROOT).as_posix()


def guitarset_rows():
    """Uma linha por excerto de comping (180), incluindo os excluídos."""
    rows = []
    for audio in sorted(GUITARSET_AUDIO.glob("*_comp_mic.wav")):
        track_id = audio.stem[:-len("_mic")]
        player_id = track_id.split("_", 1)[0]
        if player_id in GUITARSET_VAL_PLAYERS:
            split = "val"
        elif player_id in GUITARSET_TEST_PLAYERS:
            split = "test"
        else:
            raise ValueError(f"{track_id}: músico inesperado {player_id!r}")
        reason = GUITARSET_EXCLUDED.get(track_id, "")
        rows.append({
            "dataset": "guitarset",
            "track_id": track_id,
            "audio_path": _relative(audio),
            "annotation_path": _relative(GUITARSET_ANNOT / f"{track_id}.jams"),
            "player_id": player_id,
            "split": split,
            "excluded": "true" if reason else "false",
            "exclude_reason": reason,
        })
    if len(rows) != 180:
        raise RuntimeError(f"esperava 180 excertos de comping, achei {len(rows)}")
    marcados = sum(1 for r in rows if r["excluded"] == "true")
    if marcados != len(GUITARSET_EXCLUDED):
        raise RuntimeError(
            f"esperava {len(GUITARSET_EXCLUDED)} faixas excluídas no manifest, "
            f"marquei {marcados} -- os nomes em GUITARSET_EXCLUDED não batem "
            f"com os arquivos em disco"
        )
    return rows


def idmt_rows():
    """Uma linha por WAV de guitar/ (6). Split 'eval': nunca usado em ajuste."""
    audio_root = IDMT_ROOT / "guitar"
    annotation = audio_root / "guitar_annotation.lab"
    rows = []
    for audio in sorted(audio_root.glob("*.wav")):
        rows.append({
            "dataset": "idmt-smt-chords",
            "track_id": audio.stem,
            "audio_path": _relative(audio),
            "annotation_path": _relative(annotation),
            "player_id": "",            # o dataset não tem músico identificado
            "split": "eval",
            "excluded": "false",
            "exclude_reason": "",
        })
    if len(rows) != 6:
        raise RuntimeError(f"esperava 6 WAVs de guitar/, achei {len(rows)}")
    return rows


def _write_manifest(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def build_manifests():
    """Escreve os dois CSVs em data/manifests/ e devolve os caminhos."""
    gs = _write_manifest(MANIFESTS / "guitarset_comping.csv", guitarset_rows())
    idmt = _write_manifest(MANIFESTS / "idmt_smt_chords.csv", idmt_rows())
    return [gs, idmt]


# ==========================================================================
if __name__ == "__main__":
    # Amostra para conferência manual contra o áudio.
    amostras = [
        ("GuitarSet", GUITARSET_ANNOT / "00_BN1-129-Eb_comp.jams", load_guitarset),
        ("GuitarSet", GUITARSET_ANNOT / "03_Rock1-130-A_comp.jams", load_guitarset),
        ("IDMT", IDMT_ROOT / "guitar" / "guitar_annotation.lab", load_idmt_lab),
    ]
    for rotulo, caminho, loader in amostras:
        print("=" * 68)
        print(f"{rotulo}: {caminho.name}")
        print("=" * 68)
        if not caminho.exists():
            print("  (arquivo ausente)")
            continue
        segs = loader(caminho)
        print(f"  {len(segs)} segmentos, cobertura "
              f"{segs[0][0]:.3f}s -> {segs[-1][1]:.3f}s")
        for start, end, label in segs[:10]:
            print(f"  {start:8.3f} -> {end:8.3f}  {label}")

    print("=" * 68)
    for caminho in build_manifests():
        n = sum(1 for _ in caminho.open(encoding="utf-8")) - 1
        print(f"escrito {_relative(caminho)} ({n} linhas)")
