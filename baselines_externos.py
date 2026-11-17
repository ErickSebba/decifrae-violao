"""
baselines_externos.py
=====================
Baselines externos da revisão do camera-ready: Chordino (NNLS Chroma, via
Sonic Annotator) e madmom (os .lab são produzidos por outro script).

Fluxo:
  1. `rodar_chordino` roda o Sonic Annotator com o transform congelado em
     `baselines/chordino_simplechord.n3` (parâmetros default do plugin) em
     cada faixa do manifest e guarda os segmentos, já em Harte, em
     `data/cache/baselines/chordino/<dataset>/<track_id>.lab`.
  2. `avaliar` lê esses .lab e gera linhas no MESMO formato de
     `runner.CSV_FIELDS`, escrevendo
     `data/results/baseline_<nome>_<ts>_ref<L>.csv` + `_meta.json`.

Uso (de dentro da pasta):
  python baselines_externos.py --baseline chordino --manifest \
      data/manifests/guitarset_comping.csv --splits val --ref-layer 0 \
      --post-review
  python baselines_externos.py --baseline madmom ... --post-review

O split `test` exige `--splits test` explícito, como no runner.py.

Vocabulário do Chordino (saída `simplechord`, `usehartesyntax = 0`, dicionário
embutido no plugin v5): tônica com os nomes de nota do plugin -- A, Bb, B, C,
C#, D, Eb, E, F, F#, G, Ab (mistura bemóis e sustenidos) -- seguida de um
sufixo de qualidade e, nas inversões, de '/<nota do baixo>' (nome ABSOLUTO da
nota, não grau). Sufixos do dicionário: '' (maior), 'm', 'dim', 'aug', '6',
'7', 'maj7', 'm7', 'm6', 'm7b5'; a tabela Harte que o plugin carrega (usada
quando `usehartesyntax = 1`) tem exatamente essas dez qualidades (':min',
':hdim7', ':maj6', ':7', ':maj7', ':min7', ':min6', ':dim', ':aug').
'N' = sem acorde. `parse_chordino` cobre também 'dim7' e algumas grafias
alternativas, por robustez a um chord.dict do usuário.
"""

import argparse
import csv
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "data" / "results"
CACHE_BASELINES = ROOT / "data" / "cache" / "baselines"
TRANSFORM_CHORDINO = ROOT / "baselines" / "chordino_simplechord.n3"
TRANSFORM_ID = "vamp:nnls-chroma:chordino:simplechord"
PLUGIN_DLL = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) \
    / "Vamp Plugins" / "nnls-chroma.dll"

BASELINES = {"chordino": "Chordino", "madmom": "madmom"}
SPLITS_PROTEGIDOS = {"test"}


# ==========================================================================
# 1. Rótulo do Chordino -> Harte
# ==========================================================================
_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

# Sufixo do Chordino -> qualidade Harte ('maj' explícito, como o madmom).
_QUALIDADE = {
    "":      "maj",
    "maj":   "maj",
    "M":     "maj",
    "m":     "min",
    "min":   "min",
    "dim":   "dim",
    "aug":   "aug",
    "+":     "aug",
    "6":     "maj6",
    "maj6":  "maj6",
    "7":     "7",
    "maj7":  "maj7",
    "M7":    "maj7",
    "m7":    "min7",
    "min7":  "min7",
    "m6":    "min6",
    "min6":  "min6",
    "dim7":  "dim7",
    "m7b5":  "hdim7",
    "hdim7": "hdim7",
    "sus2":  "sus2",
    "sus4":  "sus4",
}

# Grau do baixo por distância em semitons à tônica (grafia padrão).
_GRAU = {0: "1", 1: "b2", 2: "2", 3: "b3", 4: "3", 5: "4", 6: "b5", 7: "5",
         8: "b6", 9: "6", 10: "b7", 11: "7"}
# Grafia que respeita a nota do acorde, quando o baixo é uma delas (o
# mir_eval só olha o semitom, mas o rótulo fica legível).
_GRAU_POR_QUALIDADE = {
    "aug":   {8: "#5"},
    "dim7":  {9: "bb7"},
}

_RE_NOTA = re.compile(r"^([A-G])([#b]*)")


def _nota(texto):
    """'Eb...' -> ('Eb', classe de altura, resto do texto)."""
    m = _RE_NOTA.match(texto)
    if not m:
        raise ValueError(f"nota inválida: {texto!r}")
    letra, acid = m.groups()
    pc = (_PC[letra] + acid.count("#") - acid.count("b")) % 12
    return letra + acid, pc, texto[m.end():]


def parse_chordino(rotulo):
    """
    Converte um rótulo do Chordino ('Ebmaj7', 'Am7/G', 'N') para Harte
    ('Eb:maj7', 'A:min7/b7', 'N'). A grafia da tônica é preservada (o mir_eval
    entende bemóis e sustenidos). Rótulo desconhecido levanta ValueError --
    melhor parar do que pontuar um 'X' em silêncio.
    """
    r = rotulo.strip().strip('"').strip()
    if r in ("N", "", "X", "N/A"):
        return "N" if r != "X" else "X"
    if ":" in r:
        # já em Harte (usehartesyntax = 1): só valida com o mir_eval
        import mir_eval
        try:
            mir_eval.chord.encode(r)
        except Exception as exc:
            raise ValueError(f"rótulo Harte inválido: {rotulo!r}") from exc
        return r

    tonica, pc_tonica, resto = _nota(r)
    baixo = None
    if "/" in resto:
        resto, baixo = resto.split("/", 1)
    if resto not in _QUALIDADE:
        raise ValueError(f"qualidade desconhecida do Chordino: {rotulo!r}")
    qual = _QUALIDADE[resto]
    harte = f"{tonica}:{qual}"

    if baixo:
        if _RE_NOTA.match(baixo):
            nome_baixo, pc_baixo, sobra = _nota(baixo)
            if sobra:
                raise ValueError(f"baixo inválido: {rotulo!r}")
            semis = (pc_baixo - pc_tonica) % 12
            if semis:
                grau = _GRAU_POR_QUALIDADE.get(qual, {}).get(semis, _GRAU[semis])
                harte += f"/{grau}"
        else:
            # baixo já dado como grau (ex.: chord.dict do usuário)
            import mir_eval
            try:
                mir_eval.chord.scale_degree_to_semitone(baixo)
            except Exception as exc:
                raise ValueError(f"baixo inválido: {rotulo!r}") from exc
            if baixo != "1":
                harte += f"/{baixo}"
    return harte


# ==========================================================================
# 2. CSV do Sonic Annotator -> segmentos
# ==========================================================================
def ler_csv_sonic(caminho):
    """
    Lê o CSV do Sonic Annotator (`tempo,"rótulo"`, só os inícios; com vários
    arquivos a primeira coluna pode ser o nome do arquivo) e devolve
    [(início, rótulo bruto)], ordenado por tempo.
    """
    eventos = []
    with Path(caminho).open(encoding="utf-8", newline="") as fp:
        for campos in csv.reader(fp):
            campos = [c.strip() for c in campos if c.strip() != ""]
            if len(campos) < 2:
                continue
            tempo = None
            for c in campos[:-1]:
                try:
                    tempo = float(c)
                    break
                except ValueError:
                    continue
            if tempo is None:
                continue
            eventos.append((tempo, campos[-1]))
    eventos.sort(key=lambda e: e[0])
    return eventos


def eventos_para_segmentos(eventos, duracao):
    """
    Inícios -> segmentos (início, fim, rótulo Harte). O fim de cada segmento é
    o início do próximo; o do último é a duração do áudio. Segmentos de
    duração nula (dois eventos no mesmo instante) são descartados.
    """
    segmentos = []
    for i, (ini, rot) in enumerate(eventos):
        fim = eventos[i + 1][0] if i + 1 < len(eventos) else float(duracao)
        if fim <= ini:
            continue
        segmentos.append((float(ini), float(fim), parse_chordino(rot)))
    return segmentos


def escrever_lab(caminho, segmentos):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8", newline="\n") as fp:
        for ini, fim, rot in segmentos:
            fp.write(f"{ini:.9f}\t{fim:.9f}\t{rot}\n")


def ler_lab(caminho):
    segmentos = []
    with Path(caminho).open(encoding="utf-8") as fp:
        for linha in fp:
            partes = linha.split()
            if len(partes) >= 3 and not linha.startswith("#"):
                segmentos.append((float(partes[0]), float(partes[1]),
                                  partes[2]))
    return segmentos


# ==========================================================================
# 3. Execução do Chordino
# ==========================================================================
def _sonic_annotator():
    candidatos = [
        os.environ.get("SONIC_ANNOTATOR"),
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs"
            / "sonic-annotator" / "sonic-annotator-win64"
            / "sonic-annotator.exe"),
        shutil.which("sonic-annotator"),
    ]
    for c in candidatos:
        if c and Path(c).is_file():
            return c
    raise SystemExit("sonic-annotator não encontrado (defina SONIC_ANNOTATOR)")


def _duracao_audio(caminho):
    import soundfile as sf
    return float(sf.info(str(caminho)).duration)


def _linhas(manifest, splits):
    with Path(manifest).open(encoding="utf-8", newline="") as fp:
        linhas = [r for r in csv.DictReader(fp)
                  if (r.get("excluded") or "false").strip().lower() != "true"]
    return [r for r in linhas if r.get("split") in splits]


def dir_baseline(baseline, dataset):
    return CACHE_BASELINES / baseline / dataset


def rodar_chordino(manifest, splits, verbose=True):
    """
    Roda o Chordino em cada faixa (não excluída) do manifest nos splits dados.
    Pula faixa já em cache. Devolve a lista de falhas [(track_id, erro)].
    """
    exe = _sonic_annotator()
    linhas = _linhas(manifest, splits)
    falhas = []
    for i, row in enumerate(linhas, start=1):
        tid = row["track_id"]
        destino = dir_baseline("chordino", row["dataset"]) / f"{tid}.lab"
        if destino.exists():
            continue
        audio = ROOT / row["audio_path"]
        try:
            # O Sonic Annotator não abre caminhos não-ASCII no Windows (a
            # pasta do projeto tem 'ã'): transform e áudio são copiados para
            # um diretório temporário e passados por caminho relativo.
            with tempfile.TemporaryDirectory() as tmp:
                shutil.copyfile(TRANSFORM_CHORDINO, Path(tmp) / "t.n3")
                shutil.copyfile(audio, Path(tmp) / f"audio{audio.suffix}")
                (Path(tmp) / "out").mkdir()
                proc = subprocess.run(
                    [exe, "-t", "t.n3", "-w", "csv", "--csv-basedir", "out",
                     "--csv-force", f"audio{audio.suffix}"],
                    cwd=tmp, capture_output=True, text=True, timeout=600)
                saidas = list((Path(tmp) / "out").glob("*.csv"))
                if proc.returncode != 0 or len(saidas) != 1:
                    raise RuntimeError(
                        f"sonic-annotator rc={proc.returncode}, "
                        f"{len(saidas)} CSV; stderr: {proc.stderr[-300:]}")
                bruto = destino.parent / "csv" / f"{tid}.csv"
                bruto.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(saidas[0], bruto)
            segmentos = eventos_para_segmentos(ler_csv_sonic(bruto),
                                               _duracao_audio(audio))
            escrever_lab(destino, segmentos)
        except Exception as exc:
            falhas.append((tid, f"{type(exc).__name__}: {exc}"))
        if verbose:
            sys.stdout.write(f"\r  chordino: {i}/{len(linhas)}")
            sys.stdout.flush()
    if verbose and linhas:
        print()
    return falhas


# ==========================================================================
# 4. Avaliação no formato do runner
# ==========================================================================
@contextmanager
def _estimado_em_harte():
    """
    O `evaluate._to_arrays` traduz SEMPRE o estimado pelo vocabulário do
    projeto ('Am' -> 'A:min'); um rótulo já em Harte ('A:min', 'C:maj/3')
    viraria 'X'. Enquanto este contexto está ativo, rótulo com ':' ou '/'
    passa direto (o resto -- 'N' -- segue pela tradução original). Vale para
    `score_segments` e para o diagnóstico do runner, que usam a mesma função.
    """
    import evaluate
    original = evaluate._to_mireval

    def _passa_harte(label):
        if isinstance(label, str) and (":" in label or "/" in label):
            return label
        return original(label)

    evaluate._to_mireval = _passa_harte
    try:
        yield
    finally:
        evaluate._to_mireval = original


def _referencia(row, ref_camada):
    import dataset_io as ds
    if hasattr(ds, "load_reference"):
        return ds.load_reference(row, index=ref_camada)
    caminho = ROOT / row["annotation_path"]
    if caminho.suffix.lower() == ".lab":
        return ds.load_idmt_lab(caminho)
    return ds.load_guitarset(caminho, index=ref_camada)


def avaliar(nome, dir_lab, manifest, splits, ref_camada, verbose=True):
    """
    Pontua os .lab de `dir_lab/<dataset>/<track_id>.lab` contra a referência.
    Devolve (linhas no formato runner.CSV_FIELDS, falhas).
    """
    import runner
    variante = runner.Variante(nome, motor=nome.lower(), vocab=nome)
    linhas = _linhas(manifest, splits)
    if not linhas:
        raise SystemExit(f"nenhuma faixa em {manifest} com split em "
                         f"{sorted(splits)}")
    resultados, falhas = [], []
    with _estimado_em_harte():
        for i, row in enumerate(linhas, start=1):
            tid = row["track_id"]
            try:
                ref = _referencia(row, ref_camada)
                lab = Path(dir_lab) / row["dataset"] / f"{tid}.lab"
                if not lab.exists():
                    raise FileNotFoundError(f"sem .lab: {lab}")
                est = ler_lab(lab)
                resultados.append(runner._linha_csv(
                    variante, row, ref, est, runner._duracao(ref), ref_camada))
            except Exception as exc:
                falhas.append((tid, f"{type(exc).__name__}: {exc}"))
            if verbose:
                sys.stdout.write(f"\r  {nome}: {i}/{len(linhas)}")
                sys.stdout.flush()
    if verbose:
        print()
    return resultados, falhas


def _sha256(caminho):
    try:
        return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()
    except OSError:
        return None


def _info_chordino():
    info = {"transform_id": TRANSFORM_ID,
            "transform_arquivo": TRANSFORM_CHORDINO.relative_to(ROOT).as_posix(),
            "transform_sha256": _sha256(TRANSFORM_CHORDINO),
            "plugin_dll_sha256": _sha256(PLUGIN_DLL)}
    try:
        texto = TRANSFORM_CHORDINO.read_text(encoding="utf-8")
        m = re.search(r'vamp:plugin_version\s+"""(.*?)"""', texto)
        info["plugin_version"] = m.group(1) if m else None
        info["parametros"] = dict(re.findall(
            r'vamp:identifier\s+"(\w+)"\s*\]\s*;\s*vamp:value\s+"([^"]+)"',
            texto))
        for chave in ("step_size", "block_size"):
            m = re.search(rf'vamp:{chave}\s+"(\d+)"', texto)
            info[chave] = int(m.group(1)) if m else None
    except OSError as exc:
        info["erro"] = str(exc)
    try:
        info["sonic_annotator_version"] = subprocess.run(
            [_sonic_annotator(), "-v"], capture_output=True, text=True,
            timeout=30).stdout.strip()
    except (Exception, SystemExit) as exc:
        info["sonic_annotator_version"] = None
        info["erro_sonic"] = str(exc)
    return info


def _info_madmom():
    try:
        from importlib.metadata import version
        return {"madmom_version": version("madmom")}
    except Exception:
        return {"madmom_version": None,
                "nota": "rótulos produzidos fora deste script"}


def _meta(baseline, nome, manifest, splits, ref_camada, dir_lab, n_linhas,
          falhas, segundos, projeto):
    import mir_eval
    import numpy as np
    meta = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "post_review": True,
        "baseline": baseline,
        "variante": nome,
        "manifest": str(manifest),
        "splits": sorted(splits),
        "ref_camada": f"chord[{ref_camada}]",
        "ref_is_harte": True,
        "est_is_harte": True,
        "dir_lab": Path(dir_lab).relative_to(ROOT).as_posix(),
        "n_linhas": n_linhas,
        "falhas": [{"onde": o, "erro": e} for o, e in falhas],
        "segundos": round(segundos, 1),
        "versoes": {
            "python": sys.version.split()[0],
            "implementacao": platform.python_implementation(),
            "numpy": np.__version__,
            "mir_eval": mir_eval.__version__,
        },
        "projeto": projeto,
    }
    meta.update(_info_chordino() if baseline == "chordino" else _info_madmom())
    return meta


def escrever(resultados, meta, baseline, timestamp, ref_camada):
    import runner
    RESULTS.mkdir(parents=True, exist_ok=True)
    base = f"baseline_{baseline}_{timestamp}_ref{ref_camada}"
    csv_path = RESULTS / f"{base}.csv"
    meta_path = RESULTS / f"{base}_meta.json"
    if csv_path.exists() or meta_path.exists():
        raise SystemExit(f"{csv_path.name} já existe -- CSV nunca é sobrescrito")
    with csv_path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=runner.CSV_FIELDS)
        writer.writeheader()
        writer.writerows(resultados)
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False),
                         encoding="utf-8")
    return csv_path, meta_path


def main(argv=None):
    ap = argparse.ArgumentParser(description="Baselines externos (Chordino, "
                                             "madmom) no formato do runner.")
    ap.add_argument("--baseline", required=True, choices=sorted(BASELINES))
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--splits", default="val",
                    help="lista separada por vírgula (default: val). "
                         "'test' precisa ser pedido explicitamente.")
    ap.add_argument("--ref-layer", type=int, default=0, choices=(0, 1))
    ap.add_argument("--post-review", action="store_true",
                    help="obrigatório: baselines externos são da revisão")
    ap.add_argument("--so-avaliar", action="store_true",
                    help="não roda o Chordino; só avalia os .lab em cache")
    args = ap.parse_args(argv)

    if not args.post_review:
        raise SystemExit("baselines externos exigem --post-review")
    splits = {s.strip() for s in args.splits.split(",") if s.strip()}
    protegidos = splits & SPLITS_PROTEGIDOS
    if protegidos and "--splits" not in (argv if argv is not None else sys.argv):
        raise SystemExit(f"split protegido {sorted(protegidos)} exige --splits "
                         f"explícito")

    import runner
    # commit lido ANTES de qualquer saída (cache ou resultados)
    projeto = runner._commit()

    nome = BASELINES[args.baseline]
    dir_lab = CACHE_BASELINES / args.baseline
    print(f"baseline {nome} | manifest {args.manifest} | splits "
          f"{sorted(splits)} | referência chord[{args.ref_layer}]")
    if protegidos:
        print(f"  ATENÇÃO: split(s) {sorted(protegidos)} -- o conjunto de teste "
              f"deve ser lido uma única vez.")

    t0 = time.perf_counter()
    falhas = []
    if args.baseline == "chordino" and not args.so_avaliar:
        falhas += [(f"chordino/{t}", e)
                   for t, e in rodar_chordino(args.manifest, splits)]
    resultados, falhas_av = avaliar(nome, dir_lab, args.manifest, splits,
                                    args.ref_layer)
    falhas += [(f"{nome}/{t}", e) for t, e in falhas_av]
    segundos = time.perf_counter() - t0

    if resultados:
        runner.resumir(resultados, [nome], args.ref_layer)
    meta = _meta(args.baseline, nome, args.manifest, splits, args.ref_layer,
                 dir_lab, len(resultados), falhas, segundos, projeto)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path, meta_path = escrever(resultados, meta, args.baseline, timestamp,
                                   args.ref_layer)
    print(f"\nfalhas: {len(falhas)}")
    for onde, erro in falhas[:10]:
        print(f"  {onde}: {erro}")
    print(f"escrito {csv_path.relative_to(ROOT).as_posix()} "
          f"({len(resultados)} linhas)")
    print(f"escrito {meta_path.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    main()
