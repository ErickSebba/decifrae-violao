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
# 4. IDMT-SMT-Guitar V2, subconjunto 4 (CSV por batida)
# ==========================================================================
# Acrescentado na revisão camera-ready. Nada acima foi alterado.
#
# Formato (descrição oficial, SMT_GUITAR_dataset_description.pdf §2.2.2):
#
#     tempo_s,compasso.batida[:acorde[/baixo]]     <- uma linha por batida
#     ...
#     compasso_ini,batida_ini      <- início da 1ª ocorrência da sequência repetida
#     compasso_fim,batida_fim      <- fim dessa mesma sequência
#     numerador,denominador        <- fórmula de compasso (sempre 4,4 aqui)
#
# As três linhas finais (só inteiros, sem ponto: '1,1', '8,4', '4,4') são o
# rodapé de repetição/compasso e NÃO são batidas: são ignoradas.
#
# Seis arquivos de acoustic_pickup têm uma linha de batida com o número da
# batida truncado ('10.005034013,5.', '13.787505668,5.3d',
# '10.000725623,3.:Gbmin'). O tempo está íntegro, então a linha conta como
# batida (o rótulo, quando existe, é mantido).
#
# Convenção do fim: o rótulo de uma linha vale até a próxima linha COM rótulo;
# o último acorde vai até o último tempo de batida + 1 intervalo mediano entre
# batidas (a anotação marca o início de cada batida, não o fim da última). A
# referência começa no PRIMEIRO tempo de batida, não em 0: antes dele há um
# compasso de silêncio e dois compassos de sinal de controle (notas abafadas),
# que não são anotados. O mir_eval recorta o estimado ao intervalo da
# referência, então o pré-roll não entra na pontuação.

IDMT_GUITAR_ROOT = (ROOT / "data" / "extracted" / "idmt-smt-guitar"
                    / "IDMT-SMT-GUITAR_V2" / "dataset4")

IDMT_GUITAR_FIELDS = MANIFEST_FIELDS + ["guitarra", "velocidade", "estilo",
                                        "andamento_bpm"]

# Sufixo IDMT -> qualidade Harte. A notação do IDMT é aditiva: '7' explícito
# quando há sétima menor ('713' = 7 + 13, '79' = 7 + 9), e os números soltos
# são notas acrescentadas à tríade maior ('13', '11', '9', '913', '1113').
# Por isso '13' sozinho é maj(13) (add13 = sexta), e NÃO o 13 dominante do
# jazz: o próprio dataset distingue '13' de '713', e em 3 das 8 formas com
# baixo ('E13/Db', 'A13/Gb', 'B13/Ab') o baixo é justamente a 6ª, o que
# só faz sentido num acorde de sexta. As extensões ficam literais, entre
# parênteses; o mir_eval ignora graus acima da oitava (9, 11, 13) ao
# codificar, então maj(13), maj(9), maj(11) contam como 'maj' e 7(9), 7(b9),
# 7(13) como '7' -- é a convenção do avaliador, a mesma para os três datasets.
IDMT_GUITAR_QUALITY = {
    "":         "maj",
    "min":      "min",
    "7":        "7",
    "maj7":     "maj7",
    "min7":     "min7",
    "dim":      "dim",
    "dim7":     "dim7",
    "sus4":     "sus4",
    "sus9":     "sus2",          # 1-5-9: a 9 substitui a 3ª -> sus2
    "5":        "5",             # power chord (1-5)
    "min75b":   "hdim7",         # m7(b5) = meio-diminuto
    "75b":      "7(*5,b5)",      # 7 com a 5ª abaixada (b5 substitui a 5)
    "79":       "7(9)",          # = '9' (dominante com nona)
    "79b":      "7(b9)",
    "713":      "7(13)",
    "713b":     "7(b13)",
    "7913":     "7(9,13)",
    "913":      "maj(9,13)",     # 6/9 sem 7ª
    "9":        "maj(9)",        # add9
    "11":       "maj(11)",       # add11
    "1113":     "maj(11,13)",
    "13":       "maj(13)",       # add13 (= sexta); ver comentário acima
    "min13":    "min(13)",       # m add13 (= m6)
    "min79":    "min7(9)",       # = min9
    "minmaj79": "minmaj7(9)",
    "maj79":    "maj7(9)",       # = maj9
}

# Semitons do baixo acima da raiz -> grau Harte. A grafia (b5 e não #4,
# b6 e não #5) não importa para o mir_eval, que só usa o semitom.
_IDMT_GUITAR_BASS_DEGREE = ["1", "b2", "2", "b3", "3", "4", "b5", "5", "b6",
                            "6", "b7", "7"]
_PITCH = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

# Rótulo sem tradução segura -> 'X' (o mir_eval ignora na ponderação).
# Ocorrências conhecidas no subconjunto 4:
#   'GB5'   (3 arquivos, rock_1_100BPM slow): provável 'Gb5' (a sequência é a
#           mesma das outras guitarras), mas não é grafia válida -> X.
#   'D/7Gb' (8 arquivos, classical_1): provável 'D7/Gb' (a 2ª volta repete a
#           1ª, onde está 'D7/Gb'), mas o baixo '7Gb' não é nota -> X.
IDMT_GUITAR_UNKNOWN = 'X'

_IDMT_NOTE_RE = None
_IDMT_BEAT_RE = None
_IDMT_FOOTER_RE = None


def _idmt_regex():
    """Compila as expressões regulares uma vez (import de `re` tardio)."""
    global _IDMT_NOTE_RE, _IDMT_BEAT_RE, _IDMT_FOOTER_RE
    if _IDMT_NOTE_RE is None:
        import re
        _IDMT_NOTE_RE = re.compile(r"^([A-G])([b#]?)$")
        # tempo com ponto decimal, compasso, '.', número da batida (pode vir
        # truncado ou sujo, ver acima) e rótulo opcional depois de ':'
        _IDMT_BEAT_RE = re.compile(
            r"^(\d+\.\d+),(\d+)\.([^:]*)(?::(.*))?$")
        _IDMT_FOOTER_RE = re.compile(r"^\d+,\d+$")
    return _IDMT_NOTE_RE, _IDMT_BEAT_RE, _IDMT_FOOTER_RE


def _idmt_pitch(nota):
    """'Gb' -> 6; None se não for uma nota válida."""
    note_re, _, _ = _idmt_regex()
    m = note_re.match(nota)
    if not m:
        return None
    acidente = {"": 0, "b": -1, "#": 1}[m.group(2)]
    return (_PITCH[m.group(1)] + acidente) % 12


def idmt_guitar_to_harte(label):
    """
    Rótulo do IDMT-SMT-Guitar -> Harte.

    'NC' -> 'N'; 'D7/C' -> 'D:7/b7'; 'Gbmin75b/C' -> 'Gb:hdim7/b5'.
    A raiz fica como está (bemóis são válidos no mir_eval); o baixo vira grau
    relativo à raiz. Sufixo desconhecido ou nota inválida -> 'X'.
    """
    label = label.strip()
    if label == "NC":
        return NO_CHORD
    acorde, _, baixo = label.partition("/")
    if len(acorde) >= 2 and acorde[1] in "b#":
        raiz, sufixo = acorde[:2], acorde[2:]
    else:
        raiz, sufixo = acorde[:1], acorde[1:]
    p_raiz = _idmt_pitch(raiz)
    qualidade = IDMT_GUITAR_QUALITY.get(sufixo)
    if p_raiz is None or qualidade is None:
        return IDMT_GUITAR_UNKNOWN
    harte = f"{raiz}:{qualidade}"
    if baixo:
        p_baixo = _idmt_pitch(baixo)
        if p_baixo is None:
            return IDMT_GUITAR_UNKNOWN
        harte += "/" + _IDMT_GUITAR_BASS_DEGREE[(p_baixo - p_raiz) % 12]
    return harte


def _parse_idmt_guitar(csv_path):
    """
    Lê o CSV e devolve (batidas, rotulos, rodape):
      batidas : [tempo_s, ...] de todas as linhas de batida, em ordem
      rotulos : [(indice_da_batida, rótulo_original), ...] das linhas com ':'
      rodape  : as linhas só com inteiros, na ordem do arquivo
    """
    csv_path = Path(csv_path)
    _, beat_re, footer_re = _idmt_regex()
    batidas, rotulos, rodape = [], [], []
    with csv_path.open(encoding="utf-8", newline="") as fp:
        for n, line in enumerate(fp, start=1):
            line = line.strip()
            if not line:
                continue
            if footer_re.match(line):
                rodape.append(line)
                continue
            if rodape:
                raise ValueError(f"{csv_path.name}:{n}: batida depois do "
                                 f"rodapé: {line!r}")
            m = beat_re.match(line)
            if not m:
                raise ValueError(f"{csv_path.name}:{n}: linha ilegível "
                                 f"{line!r}")
            if m.group(4) is not None:
                rotulos.append((len(batidas), m.group(4)))
            batidas.append(float(m.group(1)))
    return batidas, rotulos, rodape


def load_idmt_guitar(csv_path):
    """
    Lê um CSV de acordes do IDMT-SMT-Guitar (subconjunto 4) e devolve
    [(start, end, label_harte), ...], contígua, do primeiro tempo de batida
    até o último tempo + 1 intervalo mediano entre batidas.

    Cada linha com rótulo abre um segmento que vai até a próxima linha com
    rótulo. Se a primeira batida não tiver rótulo (não ocorre no subconjunto
    4), o trecho inicial vira 'N'. O rodapé de 3 linhas é ignorado.
    """
    import numpy as np                  # import tardio, como no resto do módulo

    csv_path = Path(csv_path)
    batidas, rotulos, _ = _parse_idmt_guitar(csv_path)
    if len(batidas) < 2:
        raise ValueError(f"{csv_path.name}: menos de duas batidas")
    if any(b <= a for a, b in zip(batidas, batidas[1:])):
        raise ValueError(f"{csv_path.name}: tempos de batida não crescentes")

    fim = batidas[-1] + float(np.median(np.diff(batidas)))
    inicios = [(batidas[i], idmt_guitar_to_harte(r)) for i, r in rotulos]
    if not inicios or inicios[0][0] > batidas[0]:
        inicios.insert(0, (batidas[0], NO_CHORD))

    segments = []
    for k, (t0, label) in enumerate(inicios):
        t1 = inicios[k + 1][0] if k + 1 < len(inicios) else fim
        segments.append((t0, t1, label))
    return segments


def idmt_guitar_rows():
    """
    Uma linha por WAV do subconjunto 4 (507), incluindo o par que não casa.

    O CSV de um WAV é `annotation/chords/<mesmo nome>.csv`. Quando ele não
    existe, procura-se um CSV da mesma peça (mesmo '<estilo>_<n>_') na pasta;
    se houver, a linha aponta para ele mas fica excluded=true -- o nome
    diverge no andamento e não se supõe que casem. Sem candidato, é erro.
    """
    import re

    rows = []
    for audio in sorted(IDMT_GUITAR_ROOT.glob("*/*/*/audio/*.wav")):
        estilo_dir = audio.parent.parent
        velocidade = estilo_dir.parent.name
        guitarra = estilo_dir.parent.parent.name
        m = re.match(r"^(.+_\d+)_(\d+)BPM$", audio.stem)
        if not m:
            raise ValueError(f"{audio.name}: nome sem andamento")
        chords_dir = estilo_dir / "annotation" / "chords"
        annotation = chords_dir / f"{audio.stem}.csv"
        reason = ""
        if not annotation.exists():
            candidatos = sorted(chords_dir.glob(f"{m.group(1)}_*BPM.csv"))
            if len(candidatos) != 1:
                raise RuntimeError(f"{_relative(audio)}: sem anotação e "
                                   f"{len(candidatos)} candidatos")
            annotation = candidatos[0]
            reason = (f"anotação não casa com o áudio: {audio.name} vs "
                      f"{annotation.name} (andamento divergente no nome)")
        slug = guitarra.lower().replace(" ", "-")
        rows.append({
            "dataset": "idmt-smt-guitar",
            "track_id": f"{slug}_{velocidade}_{audio.stem}",
            "audio_path": _relative(audio),
            "annotation_path": _relative(annotation),
            "player_id": "",
            "split": "external",
            "excluded": "true" if reason else "false",
            "exclude_reason": reason,
            "guitarra": guitarra,
            "velocidade": velocidade,
            "estilo": estilo_dir.name,
            "andamento_bpm": m.group(2),
        })
    if len(rows) != 507:
        raise RuntimeError(f"esperava 507 WAVs no subconjunto 4, achei {len(rows)}")
    if len({r["track_id"] for r in rows}) != len(rows):
        raise RuntimeError("track_id repetido no IDMT-SMT-Guitar")
    return rows


def build_manifest_idmt_guitar():
    """Escreve data/manifests/idmt_smt_guitar.csv e devolve o caminho."""
    path = MANIFESTS / "idmt_smt_guitar.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=IDMT_GUITAR_FIELDS)
        writer.writeheader()
        writer.writerows(idmt_guitar_rows())
    return path


# ==========================================================================
# 5. Despachante de referência
# ==========================================================================
def load_reference(row, index=CHORD_ANNOTATION_INDEX):
    """
    Referência de uma linha de manifest, pelo `row["dataset"]`.

    guitarset       -> load_guitarset(ROOT/annotation_path, index=index),
                       exatamente a chamada de `runner.rodar`
    idmt-smt-chords -> load_idmt_lab(ROOT/annotation_path)
    idmt-smt-guitar -> load_idmt_guitar(ROOT/annotation_path)

    `index` só vale para o GuitarSet (camada chord[index]).
    """
    dataset = row["dataset"]
    caminho = ROOT / row["annotation_path"]
    if dataset == "guitarset":
        return load_guitarset(caminho, index=index)
    if dataset == "idmt-smt-chords":
        return load_idmt_lab(caminho)
    if dataset == "idmt-smt-guitar":
        return load_idmt_guitar(caminho)
    raise ValueError(f"dataset desconhecido: {dataset!r}")


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
