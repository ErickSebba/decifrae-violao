"""
runner.py
=========
Matriz de ablação: roda as variantes do pipeline sobre um manifest e escreve
um CSV por experimento em `data/results/`.

As variantes são INCREMENTAIS -- cada uma acrescenta uma etapa à anterior, para
que a diferença entre duas linhas vizinhas seja atribuível a uma etapa só.
Todas usam o vocabulário MEDIUM.

    V4   baseline legacy_v4 (caminho próprio: precisa do waveform, não usa
         config nem o cache de Features)
    A    smooth=0,  complexity_penalty=0,    use_viterbi=False, min_dur=0
    B    smooth=21, complexity_penalty=0,    use_viterbi=False, min_dur=0
    C    smooth=21, complexity_penalty=0.06, use_viterbi=False, min_dur=0
    D    smooth=21, complexity_penalty=0.06, use_viterbi=True,  min_dur=0
    E    smooth=21, complexity_penalty=0.06, use_viterbi=True,  min_dur=0.8

E é a configuração atual do sistema: confere com os defaults de `config.py`
nos quatro campos ablacionados e nos demais (change_penalty 2.0, temp 0.1,
n_logprob -2.5, rel_gate 0.2, abs_floor 5e-4, ext_sharpness 4.0), que ficam
fixos em todas as variantes.

DOIS PARÂMETROS QUE NÃO ESTÃO NO DECODE
---------------------------------------
`complexity_penalty` e `ext_sharpness` configuram o CLASSIFICADOR, não o
`pipeline.decode` -- que os ignora de propósito (ver o docstring dele). Um
runner que montasse um classificador só e variasse esses campos no `post`
estaria varrendo dois parâmetros sem efeito nenhum, e a ablação concluiria que
o viés pró-tríade não importa. Aqui cada par (complexity_penalty,
ext_sharpness) tem o seu próprio `CosineChordClassifier`, memoizado em
`classificador_de`.

`smooth` é PRÉ-chroma, então A e B usam extrações diferentes -- o cache
resolve isso sozinho, porque a chave dele inclui todos os campos de
PreChromaConfig.

Referência: GuitarSet chord[0] (lead sheet instruído), com `ref_is_harte=True`.
Atenção: `docs/DATASETS.md` §2 declara chord[1] como referência principal do
benchmark. Esta ablação usa chord[0] por decisão explícita da tarefa; o valor
vai registrado na coluna `ref_camada` e no meta.json para que nenhum número
fique órfão da sua referência.

CLI:

    python runner.py --manifest data/manifests/guitarset_comping.csv
    python runner.py --manifest ... --variants A,B,C
    python runner.py --manifest ... --splits test     # explícito, ver abaixo

O split `test` NUNCA entra por default (CLAUDE.md: busca e ajuste só na
validação; o teste é lido uma vez, no fim).
"""

import argparse
import csv
import json
import platform
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path

import numpy as np

import cache
import dataset_io as ds
from chord_templates import MEDIUM, build_templates
from classifier import CosineChordClassifier
from config import PRE_CHROMA, POST_CHROMA, PreChromaConfig, PostChromaConfig
from evaluate import score_segments
from pipeline import decode

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "data" / "results"

LEVELS = ['root', 'majmin', 'sevenths', 'mirex']

# Camada de anotação usada como referência (0 = lead sheet instruído).
REF_CAMADA = 0

# Splits que exigem menção explícita na linha de comando.
SPLITS_PROTEGIDOS = {"test"}


@dataclass(frozen=True)
class Variante:
    nome: str
    pre: PreChromaConfig = None
    post: PostChromaConfig = None
    v4: bool = False


def _variantes():
    """A matriz, montada por diferença sobre os defaults de config.py."""
    pre_sem_smooth = replace(PRE_CHROMA, smooth=0)
    sem_bias = replace(POST_CHROMA, complexity_penalty=0.0,
                       use_viterbi=False, min_dur=0.0)
    com_bias = replace(sem_bias, complexity_penalty=0.06)
    com_viterbi = replace(com_bias, use_viterbi=True)
    atual = replace(com_viterbi, min_dur=0.8)
    return {
        "V4": Variante("V4", v4=True),
        "A": Variante("A", pre_sem_smooth, sem_bias),
        "B": Variante("B", PRE_CHROMA, sem_bias),
        "C": Variante("C", PRE_CHROMA, com_bias),
        "D": Variante("D", PRE_CHROMA, com_viterbi),
        "E": Variante("E", PRE_CHROMA, atual),
    }


VARIANTES = _variantes()

# ==========================================================================
# Classificadores: um por (complexity_penalty, ext_sharpness)
# ==========================================================================
_CLASSIFICADORES = {}


def classificador_de(post):
    """
    O CosineChordClassifier correspondente a `post`, memoizado pelos DOIS
    campos que o `decode` não consegue aplicar. Duas variantes com o mesmo par
    compartilham a instância; um par novo constrói outra.
    """
    chave = (post.complexity_penalty, post.ext_sharpness)
    if chave not in _CLASSIFICADORES:
        _CLASSIFICADORES[chave] = CosineChordClassifier(
            templates=build_templates(MEDIUM),
            complexity_penalty=post.complexity_penalty,
            ext_sharpness=post.ext_sharpness)
    return _CLASSIFICADORES[chave]


# ==========================================================================
# Estimativa
# ==========================================================================
def estimar(variante, features):
    """
    Segmentos estimados por uma variante do pipeline atual, já no formato
    (start, end, label) que o `evaluate.score_segments` consome -- o `decode`
    devolve dicts, e passar os dicts adiante faz o scorer desempacotar as
    CHAVES ('start', 'end', 'label') em vez dos valores.
    """
    segs = decode(features, classificador_de(variante.post), variante.post)
    return [(s['start'], s['end'], s['label']) for s in segs]


def estimar_v4(y, sr):
    """
    Caminho próprio do baseline: HPSS + beat tracking do legacy_v4. Mesma
    normalização de rótulo que `benchmark_musicas.run_v4` faz.
    """
    import librosa
    from legacy_v4 import run_beat_tracking

    y_h, y_p = librosa.effects.hpss(y, margin=3.0)
    segs, _ = run_beat_tracking(y, sr, y_h, y_p)
    return [(s['start'], s['end'],
             s['label'] if s['label'] not in ('', 'N/A') else 'N')
            for s in segs]


# ==========================================================================
# Execução
# ==========================================================================
def _linhas(manifest, splits):
    with Path(manifest).open(encoding="utf-8", newline="") as fp:
        linhas = [r for r in csv.DictReader(fp)
                  if (r.get("excluded") or "false").strip().lower() != "true"]
    return [r for r in linhas if r.get("split") in splits]


def _duracao(segmentos):
    return float(segmentos[-1][1] - segmentos[0][0]) if segmentos else 0.0


def _linha_csv(variante, row, ref, est, dur_ref):
    scores = score_segments(est, ref, levels=LEVELS, ref_is_harte=True)
    saida = {
        "variante": variante.nome,
        "track_id": row.get("track_id", ""),
        "split": row.get("split", ""),
        "ref_camada": f"chord[{REF_CAMADA}]",
        "duracao_s": round(dur_ref, 3),
        "n_segmentos_est": len(est),
    }
    campos_pre = asdict(variante.pre) if variante.pre else {}
    campos_post = asdict(variante.post) if variante.post else {}
    for nome in PreChromaConfig.__dataclass_fields__:
        saida[nome] = campos_pre.get(nome, "")
    for nome in PostChromaConfig.__dataclass_fields__:
        saida[nome] = campos_post.get(nome, "")
    for nivel in LEVELS:
        saida[nivel] = round(scores[nivel], 9)
    return saida


CSV_FIELDS = (["variante", "track_id", "split", "ref_camada", "duracao_s",
               "n_segmentos_est"]
              + list(PreChromaConfig.__dataclass_fields__)
              + list(PostChromaConfig.__dataclass_fields__)
              + LEVELS)


def rodar(manifest, splits, nomes_variantes, verbose=True):
    """
    Roda a matriz. Devolve (linhas, falhas). Uma faixa que quebra é registrada
    e o lote segue.
    """
    linhas_manifest = _linhas(manifest, splits)
    if not linhas_manifest:
        raise SystemExit(f"nenhuma faixa em {manifest} com split em {sorted(splits)}")

    resultados, falhas = [], []
    total = len(linhas_manifest)

    # Referências: lidas uma vez por faixa, reusadas por todas as variantes.
    refs, duracoes = {}, {}
    for row in linhas_manifest:
        tid = row["track_id"]
        try:
            refs[tid] = ds.load_guitarset(ROOT / row["annotation_path"],
                                          index=REF_CAMADA)
            duracoes[tid] = _duracao(refs[tid])
        except Exception as exc:
            falhas.append((f"ref/{tid}", f"{type(exc).__name__}: {exc}"))

    for nome in nomes_variantes:
        variante = VARIANTES[nome]
        t0 = time.perf_counter()
        for i, row in enumerate(linhas_manifest, start=1):
            tid = row["track_id"]
            if tid not in refs:
                continue
            try:
                audio = ROOT / row["audio_path"]
                if variante.v4:
                    import librosa
                    y, sr = librosa.load(audio, sr=PRE_CHROMA.sr, mono=True)
                    est = estimar_v4(y, sr)
                else:
                    features = cache.get_features(audio, variante.pre)
                    est = estimar(variante, features)
                resultados.append(
                    _linha_csv(variante, row, refs[tid], est, duracoes[tid]))
            except Exception as exc:
                falhas.append((f"{nome}/{tid}", f"{type(exc).__name__}: {exc}"))
            if verbose:
                sys.stdout.write(f"\r  {nome}: {i}/{total}")
                sys.stdout.flush()
        if verbose:
            print(f"   ({time.perf_counter() - t0:.0f}s)")

    return resultados, falhas


# ==========================================================================
# Saída
# ==========================================================================
def _commit():
    """Commit atual e se a árvore está suja -- sem isso o CSV não é rastreável."""
    def git(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                              text=True, timeout=30).stdout.strip()
    try:
        return {"commit": git("rev-parse", "HEAD"),
                "arvore_suja": bool(git("status", "--porcelain"))}
    except Exception as exc:
        return {"commit": None, "arvore_suja": None, "erro": str(exc)}


def _meta(manifest, splits, nomes, n_linhas, falhas, segundos):
    import librosa
    import mir_eval
    return {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "manifest": str(manifest),
        "splits": sorted(splits),
        "variantes": list(nomes),
        "ref_camada": f"chord[{REF_CAMADA}]",
        "ref_is_harte": True,
        "vocabulario": "MEDIUM",
        "n_linhas": n_linhas,
        "falhas": [{"onde": o, "erro": e} for o, e in falhas],
        "segundos": round(segundos, 1),
        "versoes": {
            "python": sys.version.split()[0],
            "implementacao": platform.python_implementation(),
            "numpy": np.__version__,
            "librosa": librosa.__version__,
            "mir_eval": mir_eval.__version__,
        },
        "projeto": _commit(),
        "config_base": {"pre": asdict(PRE_CHROMA), "post": asdict(POST_CHROMA)},
    }


def escrever(resultados, meta, timestamp):
    RESULTS.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS / f"ablation_{timestamp}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(resultados)
    meta_path = RESULTS / f"ablation_{timestamp}_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False),
                         encoding="utf-8")
    return csv_path, meta_path


def resumir(resultados, nomes):
    """Média ponderada por duração, por variante e nível."""
    print("\n" + "=" * 62)
    print("Média ponderada por duração (%)")
    print("=" * 62)
    print(f"{'variante':<9} | " + " | ".join(f"{n:>9}" for n in LEVELS)
          + f" | {'faixas':>7}")
    print("-" * 62)
    tabela = {}
    for nome in nomes:
        linhas = [l for l in resultados if l["variante"] == nome]
        if not linhas:
            continue
        peso = sum(l["duracao_s"] for l in linhas)
        medias = {n: (sum(l[n] * l["duracao_s"] for l in linhas) / peso
                      if peso else 0.0) for n in LEVELS}
        tabela[nome] = medias
        print(f"{nome:<9} | "
              + " | ".join(f"{medias[n]*100:8.2f}%" for n in LEVELS)
              + f" | {len(linhas):7d}")
    return tabela


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Roda a matriz de ablação sobre um manifest.")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--splits", default="val",
                    help="lista separada por vírgula (default: val). "
                         "'test' precisa ser pedido explicitamente.")
    ap.add_argument("--variants", default=",".join(VARIANTES),
                    help=f"default: todas ({','.join(VARIANTES)})")
    args = ap.parse_args(argv)

    splits = {s.strip() for s in args.splits.split(",") if s.strip()}
    nomes = [n.strip() for n in args.variants.split(",") if n.strip()]

    desconhecidas = [n for n in nomes if n not in VARIANTES]
    if desconhecidas:
        raise SystemExit(f"variante desconhecida: {desconhecidas} "
                         f"(conhecidas: {list(VARIANTES)})")

    protegidos = splits & SPLITS_PROTEGIDOS
    if protegidos and "--splits" not in (argv if argv is not None else sys.argv):
        raise SystemExit(f"split protegido {sorted(protegidos)} exige --splits "
                         f"explícito")

    print(f"manifest {args.manifest} | splits {sorted(splits)} | "
          f"variantes {nomes} | referência chord[{REF_CAMADA}]")
    if protegidos:
        print(f"  ATENÇÃO: rodando split(s) {sorted(protegidos)} -- "
              f"o conjunto de teste deve ser lido uma única vez.")

    t0 = time.perf_counter()
    resultados, falhas = rodar(args.manifest, splits, nomes)
    segundos = time.perf_counter() - t0

    resumir(resultados, nomes)
    meta = _meta(args.manifest, splits, nomes, len(resultados), falhas, segundos)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path, meta_path = escrever(resultados, meta, timestamp)

    print(f"\nfalhas: {len(falhas)}")
    for onde, erro in falhas[:10]:
        print(f"  {onde}: {erro}")
    print(f"tempo total: {segundos:.0f}s")
    print(f"escrito {csv_path.relative_to(ROOT).as_posix()} "
          f"({len(resultados)} linhas)")
    print(f"escrito {meta_path.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    main()
