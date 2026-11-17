"""
mecanismo_n.py
==============
Mecanismo do N da variante D, por base (GuitarSet teste, IDMT-SMT-Guitar,
IDMT-SMT-Chords). Três números por base, nas células de batida da D:

  (a) trocas de acorde da referência por célula: nº de fronteiras da
      referência estritamente dentro de [t_i, t_{i+1}); mediana;
  (b) células por segmento de referência (segmentos com acorde; a célula
      pertence ao segmento que contém seu ponto médio); mediana;
  (c) custo por célula de ficar em N em vez do melhor acorde:
      max_k ℓ_i(k) − β (ℓ como em `viterbi.decode`); mediana, comparada com
      change_penalty. Se (c) < change_penalty e a referência troca a cada
      célula, seguir os acordes custa mais do que ficar em N.

Células forçadas a N pelo gate de RMS ficam fora de (a) e (c), como em
`diagnostico_n.py`. Só diagnóstico; nada é ajustado.

    python mecanismo_n.py
"""

import csv
import json
from datetime import datetime
from pathlib import Path

import numpy as np

import cache
import dataset_io as ds
import diagnostico_n as dn
import runner

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "data" / "results"


def main():
    projeto = runner._commit()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    v = runner._variantes()["D"]
    beta, cp = v.post.n_logprob, v.post.change_penalty
    saida = []
    for chave, rotulo, manifest, split in dn.BASES:
        trocas, por_seg, custo = [], [], []
        for row in dn._linhas(manifest, split):
            feat = cache.get_features(ROOT / row["audio_path"], v.pre)
            m, forc = dn.celulas(feat, v)
            bt = feat.beat_times
            n = len(m)
            t0, t1 = bt[:n], bt[1:n + 1]
            ref = ds.load_reference(row, index=0)
            fronteiras = np.array([s for s, _, _ in ref[1:]])
            dentro = ((fronteiras[None, :] > t0[:, None])
                      & (fronteiras[None, :] < t1[:, None])).sum(1)
            trocas.append(dentro[~forc])
            custo.append((m - beta)[~forc])
            meio = (t0 + t1) / 2
            for s, e, lab in ref:
                if lab == "N":
                    continue
                por_seg.append(int(((meio >= s) & (meio < e)).sum()))
        tr = np.concatenate(trocas)
        cu = np.concatenate(custo)
        ps = np.array(por_seg)
        r = {"base": chave, "rotulo": rotulo, "n_celulas": len(tr),
             "n_segmentos_ref": len(ps),
             "mediana_trocas_por_celula": float(np.median(tr)),
             "media_trocas_por_celula": round(float(np.mean(tr)), 4),
             "frac_celulas_com_troca": round(float(np.mean(tr >= 1)), 4),
             "mediana_celulas_por_segmento": float(np.median(ps)),
             "mediana_custo_n": round(float(np.median(cu)), 4),
             "frac_custo_n_menor_cp": round(float(np.mean(cu < cp)), 4),
             "beta": beta, "change_penalty": cp}
        saida.append(r)
        print(f"{rotulo:16} trocas/célula (mediana) {r['mediana_trocas_por_celula']:g} "
              f"[células com troca {100 * r['frac_celulas_com_troca']:.1f} %]; "
              f"células/segmento {r['mediana_celulas_por_segmento']:g}; "
              f"custo N {r['mediana_custo_n']:.3f} < cp {cp:g} em "
              f"{100 * r['frac_custo_n_menor_cp']:.1f} % das células")
    p = RESULTS / f"mecanismo_n_{ts}.csv"
    with p.open("w", encoding="utf-8", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=list(saida[0]))
        w.writeheader()
        w.writerows(saida)
    meta = {"gerado_em": ts, "gerado_por": "mecanismo_n.py",
            "post_review": True, "projeto": projeto, "variante": "D",
            "ref_camada": "chord[0]",
            "definicoes": {
                "trocas_por_celula": "fronteiras da referência estritamente "
                                     "dentro da célula de batida",
                "celulas_por_segmento": "células cujo ponto médio cai no "
                                        "segmento de referência (sem N)",
                "custo_n": "max_k ℓ_i(k) − β, ℓ = log softmax(e/temp)"},
            "nota": "células forçadas a N pelo gate ficam fora de trocas e custo"}
    p.with_name(p.stem + "_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("escrito", p.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()
