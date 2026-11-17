"""
beat_tracking_idmt.py
=====================
Andamento estimado pelo beat tracking do pipeline contra o andamento nominal
do IDMT-SMT-Guitar (protocolo em `docs/ADENDO_REVISAO.md` §9.3), e os 6
contrastes principais separados por "razão ~1" e "erro de oitava".
Descritivo: IC do bootstrap pareado por faixa, sem Holm.

Saídas (post_review=true):
  data/results/beat_tracking_idmt_<ts>.csv           uma linha por faixa
  data/results/beat_tracking_contrastes_<ts>.csv     contraste × grupo

    python beat_tracking_idmt.py
"""

import csv
import json
from datetime import datetime
from pathlib import Path

import numpy as np

import cache
import runner
import stats

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "data" / "results"
TOL = 0.08

# um por par de stats.PARES: a métrica que o par isola (adendo §9.3)
PRINCIPAIS = [("C", "D", "root"), ("C0rg", "D0rg", "majmin"),
              ("D", "E", "overseg"), ("V4b", "V4", "overseg"),
              ("V4", "F0rg", "majmin"), ("D0rg", "F0rg", "sevenths")]


def classe(r):
    if abs(r - 1) <= TOL:
        return "~1"
    if abs(r / 2 - 1) <= TOL:
        return "~2"
    if abs(2 * r - 1) <= TOL:
        return "~0,5"
    return "outro"


def ablacao_idmt():
    """O CSV de ablação das 8 variantes no IDMT-SMT-Guitar (post_review)."""
    import analise_externo as ae
    ps = ae.ablacoes("idmt_smt_guitar.csv", "external")
    if not ps:
        raise SystemExit("sem ablação do IDMT-SMT-Guitar")
    return ps


def main():
    projeto = runner._commit()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = runner._variantes()["D"].pre
    man = ROOT / "data" / "manifests" / "idmt_smt_guitar.csv"
    faixas = []
    for row in csv.DictReader(man.open(encoding="utf-8")):
        if row["excluded"].strip().lower() == "true":
            continue
        bt = cache.get_features(ROOT / row["audio_path"], pre).beat_times
        est = 60.0 / float(np.median(np.diff(bt)))
        nom = float(row["andamento_bpm"])
        faixas.append({"track_id": row["track_id"], "guitarra": row["guitarra"],
                       "andamento_nominal": nom,
                       "andamento_estimado": round(est, 3),
                       "razao": round(est / nom, 4), "classe": classe(est / nom)})
    grupo = {f["track_id"]: ("razao_1" if f["classe"] == "~1" else
                             "oitava" if f["classe"] in ("~2", "~0,5") else
                             "outro") for f in faixas}
    cont = {}
    for f in faixas:
        cont[f["classe"]] = cont.get(f["classe"], 0) + 1
    print("classes:", cont)

    fontes = ablacao_idmt()
    por_variante, dur = stats.carregar(*fontes)
    linhas = []
    for g in ("razao_1", "oitava"):
        ids = {t for t, x in grupo.items() if x == g}
        sub = {v: {t: l for t, l in d.items() if t in ids}
               for v, d in por_variante.items()}
        for a, b, m in PRINCIPAIS:
            va, vb, w, _ = stats._pares_alinhados(sub, dur, a, b, m)
            d = vb - va
            lo, hi, _ = stats.bootstrap(d, w)
            linhas.append({"grupo": g, "par": f"{a} vs {b}", "metrica": m,
                           "n_faixas": len(d),
                           "delta": round(stats._media_ponderada(d, w), 9),
                           "ic95_min": round(lo, 9), "ic95_max": round(hi, 9)})
            print(f"{g:8} {a}→{b} {m:9} n={len(d):3} "
                  f"Δ={100 * stats._media_ponderada(d, w):+.2f} "
                  f"[{100 * lo:+.2f}; {100 * hi:+.2f}]")

    meta = {"gerado_em": ts, "post_review": True, "projeto": projeto,
            "protocolo": "docs/ADENDO_REVISAO.md §9.3", "tolerancia": TOL,
            "contagem_classes": cont, "principais": PRINCIPAIS,
            "fontes": [Path(p).resolve().relative_to(ROOT).as_posix()
                       for p in fontes],
            "nota": "descritivo; IC do bootstrap pareado por faixa, sem Holm"}
    for nome, ls in (("beat_tracking_idmt", faixas),
                     ("beat_tracking_contrastes", linhas)):
        p = RESULTS / f"{nome}_{ts}.csv"
        with p.open("w", encoding="utf-8", newline="") as fp:
            w = csv.DictWriter(fp, fieldnames=list(ls[0]))
            w.writeheader()
            w.writerows(ls)
        p.with_name(p.stem + "_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saídas: beat_tracking_idmt_{ts}.csv, beat_tracking_contrastes_{ts}.csv")


if __name__ == "__main__":
    main()
