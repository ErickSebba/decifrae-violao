"""
calibracao_revisao.py
=====================
Calibrações pedidas na revisão (camera-ready), APENAS no split de validação.
Escolhe os valores das variantes `Cmatch`, `Dmatch`, `D0rg_cal` e `F0rg_cal`
que `runner.py` congela; o registro da escolha fica em `docs/ADENDO_REVISAO.md`.

Três varreduras, todas pós-chroma (o cache de features não muda):

  cob_C   C com confidence_gate de 0,50 a 0,90, passo 0,01. Escolhe θ* cuja
          cobertura média de C fica mais próxima da cobertura de D.
  cob_D   D com n_logprob de -1 a -8, passo 0,25. Escolhe β* cuja cobertura
          média de D fica mais próxima da cobertura de C.
  cp_D0rg / cp_F0rg
          change_penalty em {0.5, 1, 1.5, 2, 2.5, 3, 4, 6} para D0rg (MEDIUM,
          60) e F0rg (BASIC, 24). Escolhe o valor de maior root (faixa toda,
          chord[0]) por vocabulário. A curva sai nas duas camadas.

Cobertura = 1 - fração do tempo estimada como N, média ponderada por duração
sobre as faixas. Não depende da camada de referência (as duas camadas do
GuitarSet têm as mesmas fronteiras), por isso as varreduras de cobertura são
medidas só em chord[0].

Desempate (fixado antes de rodar): menor |valor - default de config.py|; se
ainda empatar, o menor valor.

Uma linha por (varredura, valor, faixa, camada), como manda o CLAUDE.md.
Saída: data/results/calibracao_revisao_<ts>.csv + _meta.json (post_review=true)

    python calibracao_revisao.py --manifest data/manifests/guitarset_comping.csv
"""

import argparse
import csv
import json
import sys
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import numpy as np

import cache
import dataset_io as ds
import runner
from config import PRE_CHROMA, POST_CHROMA
from evaluate import score_segments

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "data" / "results"

NIVEIS = ["root", "majmin", "sevenths"]

THETAS = [round(0.50 + 0.01 * i, 2) for i in range(41)]          # 0.50..0.90
BETAS = [round(-1.0 - 0.25 * i, 2) for i in range(29)]           # -1..-8
CHANGE_PENALTIES = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 6.0]

CSV_FIELDS = (["varredura", "variante_base", "vocabulario", "parametro",
               "valor", "track_id", "split", "ref_camada", "duracao_s",
               "cobertura"] + NIVEIS + ["root_rotulado"])


def _com(variante, **campos):
    return replace(variante, post=replace(variante.post, **campos))


def _pontos():
    """[(varredura, parametro, valor, Variante, camadas)]."""
    V = runner.VARIANTES
    pts = [("ref_C", "(base)", "", V["C"], (0,)),
           ("ref_D", "(base)", "", V["D"], (0,))]
    pts += [("cob_C", "confidence_gate", t, _com(V["C"], confidence_gate=t), (0,))
            for t in THETAS]
    pts += [("cob_D", "n_logprob", b, _com(V["D"], n_logprob=b), (0,))
            for b in BETAS]
    for base in ("D0rg", "F0rg"):
        pts += [(f"cp_{base}", "change_penalty", cp,
                 _com(V[base], change_penalty=cp), (0, 1))
                for cp in CHANGE_PENALTIES]
    return pts


def _linha(varredura, parametro, valor, variante, row, ref, camada, est):
    diag = runner.diagnostico(est, ref)
    rot = runner.acerto_no_tempo_rotulado(est, ref)
    sc = score_segments(est, ref, levels=NIVEIS, ref_is_harte=True)
    saida = {
        "varredura": varredura, "variante_base": variante.nome,
        "vocabulario": variante.vocab, "parametro": parametro, "valor": valor,
        "track_id": row["track_id"], "split": row["split"],
        "ref_camada": f"chord[{camada}]",
        "duracao_s": round(runner._duracao(ref), 3),
        "cobertura": round(1.0 - diag["frac_n_est"], 6)
        if diag["frac_n_est"] != "" else "",
        "root_rotulado": rot["root_rotulado"],
    }
    for n in NIVEIS:
        saida[n] = round(sc[n], 9)
    return saida


def rodar(manifest, verbose=True):
    linhas = runner._linhas(manifest, {"val"})
    refs, feats, falhas = {}, {}, []
    for row in linhas:
        tid = row["track_id"]
        try:
            for c in (0, 1):
                refs[(tid, c)] = ds.load_guitarset(ROOT / row["annotation_path"],
                                                   index=c)
            feats[tid] = cache.get_features(ROOT / row["audio_path"], PRE_CHROMA)
        except Exception as exc:
            falhas.append((f"carga/{tid}", f"{type(exc).__name__}: {exc}"))
    pontos = _pontos()
    out = []
    for i, (vr, par, val, var, camadas) in enumerate(pontos, start=1):
        for row in linhas:
            tid = row["track_id"]
            if tid not in feats:
                continue
            try:
                est = runner.estimar(var, feats[tid])
                for c in camadas:
                    out.append(_linha(vr, par, val, var, row, refs[(tid, c)],
                                      c, est))
            except Exception as exc:
                falhas.append((f"{vr}/{val}/{tid}", f"{type(exc).__name__}: {exc}"))
        if verbose:
            sys.stdout.write(f"\r  ponto {i}/{len(pontos)}   ")
            sys.stdout.flush()
    if verbose:
        print()
    return out, falhas


def _agrega(linhas, varredura, coluna, camada="chord[0]"):
    """{valor: média ponderada por duração} de uma varredura."""
    por_valor = {}
    for l in linhas:
        if l["varredura"] == varredura and l["ref_camada"] == camada:
            por_valor.setdefault(l["valor"], []).append(l)
    return {v: runner._media_ponderada(ls, coluna) for v, ls in por_valor.items()}


def _escolhe(candidatos, chave, default):
    """Mínimo de `chave`; desempate por |v - default| e depois pelo menor v."""
    return min(candidatos, key=lambda v: (round(chave(v), 12),
                                          abs(v - default), v))


def escolher(linhas):
    cobC = _agrega(linhas, "ref_C", "cobertura")[""]
    cobD = _agrega(linhas, "ref_D", "cobertura")[""]
    curva_C = _agrega(linhas, "cob_C", "cobertura")
    curva_D = _agrega(linhas, "cob_D", "cobertura")
    theta = _escolhe(list(curva_C), lambda t: abs(curva_C[t] - cobD),
                     POST_CHROMA.confidence_gate)
    beta = _escolhe(list(curva_D), lambda b: abs(curva_D[b] - cobC),
                    POST_CHROMA.n_logprob)
    cal = {}
    for base in ("D0rg", "F0rg"):
        root = _agrega(linhas, f"cp_{base}", "root")
        cal[base] = {
            "valor": _escolhe(list(root), lambda cp: -root[cp],
                              POST_CHROMA.change_penalty),
            "root_chord0": {str(k): round(v, 6) for k, v in sorted(root.items())},
            "root_chord1": {str(k): round(v, 6) for k, v in sorted(
                _agrega(linhas, f"cp_{base}", "root", "chord[1]").items())},
        }
    return {
        "cobertura_C": round(cobC, 6), "cobertura_D": round(cobD, 6),
        "theta_estrela": theta, "cobertura_Cmatch": round(curva_C[theta], 6),
        "beta_estrela": beta, "cobertura_Dmatch": round(curva_D[beta], 6),
        "change_penalty_cal": cal,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--manifest", required=True)
    args = ap.parse_args(argv)

    t0 = time.perf_counter()
    linhas, falhas = rodar(args.manifest)
    segundos = time.perf_counter() - t0
    escolha = escolher(linhas)
    print(json.dumps(escolha, indent=2, ensure_ascii=False))

    import librosa
    import mir_eval
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    RESULTS.mkdir(parents=True, exist_ok=True)
    base = RESULTS / f"calibracao_revisao_{ts}"
    with base.with_suffix(".csv").open("w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(linhas)
    meta = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "post_review": True,
        "manifest": args.manifest, "splits": ["val"],
        "ref_camada": "chord[0] (cobertura e escolha); chord[1] só na curva cp_*",
        "thetas": THETAS, "betas": BETAS, "change_penalties": CHANGE_PENALTIES,
        "criterios": {
            "theta": "argmin |cob(C,θ) - cob(D)|",
            "beta": "argmin |cob(D,β) - cob(C)|",
            "change_penalty": "argmax root faixa toda, chord[0], por vocabulário",
            "desempate": "menor |valor - default de config.py|, depois menor valor",
            "media": "ponderada por duração da referência",
        },
        "escolha": escolha,
        "n_linhas": len(linhas),
        "falhas": [{"onde": o, "erro": e} for o, e in falhas],
        "segundos": round(segundos, 1),
        "versoes": {"python": sys.version.split()[0], "numpy": np.__version__,
                    "librosa": librosa.__version__,
                    "mir_eval": mir_eval.__version__},
        "projeto": runner._commit(),
    }
    Path(f"{base}_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"falhas: {len(falhas)} | {segundos:.0f}s | escrito "
          f"{base.with_suffix('.csv').relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    main()
