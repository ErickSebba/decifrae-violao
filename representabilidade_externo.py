"""
representabilidade_externo.py
=============================
Fração do tempo de referência do IDMT-SMT-Guitar (subconjunto 4) que cada
vocabulário representa (24 = maj/min; 60 = + 7, maj7, min7). Mesma definição
de `analise_vocabulario.representabilidade` (classe pela codificação do
mir_eval; denominador = tempo total de referência, com N), para comparar com
o GuitarSet (`representabilidade_20261117_004150.csv`).

    python representabilidade_externo.py
"""

import csv
import json
from datetime import datetime
from pathlib import Path

import numpy as np

import analise_vocabulario as av
import dataset_io as ds
import runner

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "data" / "results"
MANIFEST = ROOT / "data" / "manifests" / "idmt_smt_guitar.csv"


def main():
    projeto = runner._commit()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    linhas = []
    with MANIFEST.open(encoding="utf-8") as fp:
        rows = [r for r in csv.DictReader(fp)
                if r["excluded"].strip().lower() != "true"]
    for row in rows:
        ref = ds.load_reference(row, index=0)
        dur = np.array([e - s for s, e, _ in ref], dtype=float)
        _, cls, n, x, _ = av.classes([l for _, _, l in ref])
        linhas.append({
            "track_id": row["track_id"], "split": row["split"],
            "t_total": round(float(dur.sum()), 6),
            "t_N": round(float(dur[n].sum()), 6),
            "t_X": round(float(dur[x].sum()), 6),
            "t_24": round(float(dur[np.isin(cls, av.Q24)].sum()), 6),
            "t_60": round(float(dur[np.isin(cls, av.Q60)].sum()), 6)})
    T = sum(l["t_total"] for l in linhas)
    tn = sum(l["t_N"] for l in linhas)
    r24 = sum(l["t_24"] for l in linhas) / T
    r60 = sum(l["t_60"] for l in linhas) / T
    print(f"IDMT-SMT-Guitar: {len(linhas)} faixas, {T:.1f} s; "
          f"24 = {100 * r24:.2f} %, 60 = {100 * r60:.2f} % do tempo total; "
          f"N = {100 * tn / T:.2f} %; sem N: 24 = {100 * r24 * T / (T - tn):.2f} %, "
          f"60 = {100 * r60 * T / (T - tn):.2f} %")
    p = RESULTS / f"representabilidade_externo_{ts}.csv"
    with p.open("w", encoding="utf-8", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=list(linhas[0]))
        w.writeheader()
        w.writerows(linhas)
    meta = {"gerado_em": ts, "gerado_por": "representabilidade_externo.py",
            "post_review": True, "projeto": projeto,
            "manifest": "data/manifests/idmt_smt_guitar.csv",
            "definicao": "Σ tempo das classes do vocabulário / Σ tempo total "
                         "de referência (com N); classes por "
                         "analise_vocabulario.classes",
            "resumo": {"n_faixas": len(linhas), "t_total_s": round(T, 3),
                       "r24": round(r24, 6), "r60": round(r60, 6),
                       "f_N": round(tn / T, 6)}}
    p.with_name(p.stem + "_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("escrito", p.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()
