"""
curvas.py
=========
Curvas de acerto × cobertura: o que se ganha e o que se perde ao deixar o
sistema abster-se.

A ablação (`runner.py`) mostrou que as variantes sem Viterbi acertam 74,7 % no
tempo que rotulam e só 46,7 % na faixa toda, porque devolvem N em 39,5 % do
tempo -- e que forçá-las a rotular tudo PIORA o acerto. Isso quer dizer que
existe um trade-off, não um bug: cada valor do limiar de abstenção é um ponto
de operação diferente. Este script varre esses pontos.

Três curvas, todas no split val e na camada chord[0]:

    C  confidence_gate em 0.00 e de 0.50 a 0.90 (passo 0.05) -- a abstenção
       do argmax, que olha um segmento por vez.
    D  n_logprob em -1, -1.5, -2, -2.5, -3, -4, -5, -6, -8, -1e9 -- a
       abstenção do Viterbi, com vocabulário MEDIUM.
    F  o mesmo n_logprob, com vocabulário BASIC.

Mais o V4 como ponto único: ele não abstém (N est = 0 %), então vive em
cobertura 1,0 e serve de régua horizontal.

Para cada ponto e cada faixa:
    cobertura       = 1 - (fração do tempo devolvida como N)
    acerto_rotulado = acerto restrito ao tempo rotulado
    acerto_total    = acerto sobre a faixa toda
nos níveis root e majmin.

Uma linha por (curva, ponto, faixa), como manda o CLAUDE.md -- a agregação
ponderada por duração é feita por quem lê o CSV (`figura_curvas.py`), não
aqui. Assim o mesmo CSV serve para barras de erro depois.

Saída: data/results/curvas_<timestamp>.csv + _meta.json

    python curvas.py --manifest data/manifests/guitarset_comping.csv
"""

import argparse
import csv
import json
import sys
import time
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path

import numpy as np

import cache
import dataset_io as ds
import runner
from config import PRE_CHROMA
from evaluate import score_segments

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "data" / "results"

NIVEIS = ['root', 'majmin']
REF_CAMADA = 0

GATES_C = [0.00] + [round(0.50 + 0.05 * i, 2) for i in range(9)]   # 0.50..0.90
N_LOGPROBS = [-1.0, -1.5, -2.0, -2.5, -3.0, -4.0, -5.0, -6.0, -8.0, -1e9]

CSV_FIELDS = (["curva", "variante_base", "vocabulario", "parametro", "valor",
               "track_id", "split", "ref_camada", "duracao_s", "cobertura"]
              + [f"acerto_rotulado_{n}" for n in NIVEIS]
              + [f"acerto_total_{n}" for n in NIVEIS])


def _pontos():
    """[(curva, nome_do_parametro, valor, Variante), ...] na ordem do CSV."""
    C = runner.VARIANTES["C"]
    D = runner.VARIANTES["D"]
    F = runner.VARIANTES["F"]
    pontos = []
    for g in GATES_C:
        pontos.append(("C", "confidence_gate", g,
                       replace(C, post=replace(C.post, confidence_gate=g))))
    for lp in N_LOGPROBS:
        pontos.append(("D", "n_logprob", lp,
                       replace(D, post=replace(D.post, n_logprob=lp))))
    for lp in N_LOGPROBS:
        pontos.append(("F", "n_logprob", lp,
                       replace(F, post=replace(F.post, n_logprob=lp))))
    pontos.append(("V4", "(baseline)", "", runner.VARIANTES["V4"]))
    return pontos


def _linhas_manifest(manifest, splits):
    return runner._linhas(manifest, splits)


def _uma_linha(curva, parametro, valor, variante, row, ref, est):
    """Cobertura e os dois acertos, para uma faixa e um ponto."""
    diag = runner.diagnostico(est, ref)
    rotulado = runner.acerto_no_tempo_rotulado(est, ref)
    total = score_segments(est, ref, levels=NIVEIS, ref_is_harte=True)
    frac_n = diag["frac_n_est"]
    saida = {
        "curva": curva,
        "variante_base": variante.nome,
        "vocabulario": variante.vocab,
        "parametro": parametro,
        "valor": valor,
        "track_id": row.get("track_id", ""),
        "split": row.get("split", ""),
        "ref_camada": f"chord[{REF_CAMADA}]",
        "duracao_s": round(float(ref[-1][1] - ref[0][0]), 3) if ref else 0.0,
        "cobertura": round(1.0 - frac_n, 6) if frac_n != "" else "",
    }
    for n in NIVEIS:
        saida[f"acerto_rotulado_{n}"] = rotulado[f"{n}_rotulado"]
        saida[f"acerto_total_{n}"] = round(total[n], 9)
    return saida


def rodar(manifest, splits=("val",), verbose=True):
    linhas_manifest = _linhas_manifest(manifest, splits)
    if not linhas_manifest:
        raise SystemExit(f"nenhuma faixa em {manifest} com split em {sorted(splits)}")

    # Referências e features carregadas UMA vez e reusadas por todos os
    # pontos: a varredura é toda pós-chroma, então o chroma não muda.
    refs, features, audios = {}, {}, {}
    falhas = []
    for row in linhas_manifest:
        tid = row["track_id"]
        try:
            refs[tid] = ds.load_guitarset(ROOT / row["annotation_path"],
                                          index=REF_CAMADA)
            features[tid] = cache.get_features(ROOT / row["audio_path"],
                                               PRE_CHROMA)
        except Exception as exc:
            falhas.append((f"carga/{tid}", f"{type(exc).__name__}: {exc}"))
    if verbose:
        print(f"  {len(refs)} faixas carregadas, {len(falhas)} falhas de carga")

    pontos = _pontos()
    resultados = []
    for i, (curva, parametro, valor, variante) in enumerate(pontos, start=1):
        for row in linhas_manifest:
            tid = row["track_id"]
            if tid not in refs:
                continue
            try:
                if variante.motor == "v4":
                    import librosa
                    if tid not in audios:
                        y, sr = librosa.load(ROOT / row["audio_path"],
                                             sr=PRE_CHROMA.sr, mono=True)
                        audios[tid] = (y, sr)
                    est = runner.estimar_v4(*audios[tid])
                else:
                    est = runner.estimar(variante, features[tid])
                resultados.append(_uma_linha(curva, parametro, valor, variante,
                                             row, refs[tid], est))
            except Exception as exc:
                falhas.append((f"{curva}/{valor}/{tid}",
                               f"{type(exc).__name__}: {exc}"))
        if verbose:
            sys.stdout.write(f"\r  ponto {i}/{len(pontos)}: {curva} "
                             f"{parametro}={valor}        ")
            sys.stdout.flush()
    if verbose:
        print()
    return resultados, falhas, len(pontos)


def resumir(resultados):
    """Agregado ponderado por duração, um bloco por curva."""
    for curva in ("C", "D", "F", "V4"):
        linhas = [l for l in resultados if l["curva"] == curva]
        if not linhas:
            continue
        valores = sorted({l["valor"] for l in linhas},
                         key=lambda v: (v == "", v if v != "" else 0))
        print(f"\n--- curva {curva} ---")
        print(f"{'valor':>10} | {'cobertura':>9} | {'rot.root':>9} | "
              f"{'tot.root':>9} | {'rot.majmin':>10} | {'tot.majmin':>10}")
        print("-" * 70)
        for v in valores:
            sub = [l for l in linhas if l["valor"] == v]
            def med(col):
                return runner._media_ponderada(sub, col)
            print(f"{str(v):>10} | {med('cobertura')*100:8.2f}% | "
                  f"{med('acerto_rotulado_root')*100:8.2f}% | "
                  f"{med('acerto_total_root')*100:8.2f}% | "
                  f"{med('acerto_rotulado_majmin')*100:9.2f}% | "
                  f"{med('acerto_total_majmin')*100:9.2f}%")


def escrever(resultados, meta, timestamp):
    RESULTS.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS / f"curvas_{timestamp}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(resultados)
    meta_path = RESULTS / f"curvas_{timestamp}_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False),
                         encoding="utf-8")
    return csv_path, meta_path


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Curvas de acerto x cobertura no split val.")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--splits", default="val")
    args = ap.parse_args(argv)

    splits = {s.strip() for s in args.splits.split(",") if s.strip()}
    if splits & runner.SPLITS_PROTEGIDOS:
        raise SystemExit(f"este script não roda split protegido: "
                         f"{sorted(splits & runner.SPLITS_PROTEGIDOS)}")

    print(f"manifest {args.manifest} | splits {sorted(splits)} | "
          f"referência chord[{REF_CAMADA}]")
    t0 = time.perf_counter()
    resultados, falhas, n_pontos = rodar(args.manifest, splits)
    segundos = time.perf_counter() - t0

    resumir(resultados)

    import librosa
    import mir_eval
    meta = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "manifest": str(args.manifest),
        "splits": sorted(splits),
        "ref_camada": f"chord[{REF_CAMADA}]",
        "niveis": NIVEIS,
        "n_pontos": n_pontos,
        "n_linhas": len(resultados),
        "gates_C": GATES_C,
        "n_logprobs": N_LOGPROBS,
        "falhas": [{"onde": o, "erro": e} for o, e in falhas],
        "segundos": round(segundos, 1),
        "versoes": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "librosa": librosa.__version__,
            "mir_eval": mir_eval.__version__,
        },
        "projeto": runner._commit(),
        "config_base": {"pre": asdict(PRE_CHROMA)},
    }
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
