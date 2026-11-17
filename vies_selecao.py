"""
vies_selecao.py
===============
Viés de seleção da máscara comum C–D: UMA estatística para o artigo.

  acurácia root de D0rg agregada por duração DENTRO da máscara comum
      A_in  = Σ_t acerto_in_t / Σ_t tempo_in_t
  e FORA dela (tempo comparável em que C ou D estimaram N)
      A_out = Σ_t acerto_out_t / Σ_t tempo_out_t
  Δ = A_in − A_out.

IC 95 % por bootstrap pareado por faixa (10 000, seed 0): sorteia faixas com
reposição e recalcula as DUAS razões de somas na mesma reamostra. Entram só
as faixas com tempo nas duas regiões (o número é informado).

Substitui a "diferença pareada" de `vies_selecao_20261117_004137.csv`, que
era a média das diferenças POR FAIXA ponderada pela duração total da faixa
(66,03 − 47,74 = +18,29 no teste) e por isso não batia com os níveis
agregados (77,80 / 38,69). Mesmas células e mesma decodificação
(`analise_decomposicao.rodar`, chord[0], nível root).

    python vies_selecao.py              # recalcula e reescreve a nota
    python vies_selecao.py --so-nota    # só a nota da tab_decomposicao
"""

import csv
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

import analise_decomposicao as ad
import runner
import stats

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "data" / "results"
CAMPOS = ["split", "ref_camada", "variante", "nivel", "n_faixas",
          "n_faixas_duas_regioes", "tempo_dentro_s", "tempo_fora_s",
          "acerto_dentro", "acerto_fora", "delta", "ic95_min", "ic95_max",
          "p_bootstrap"]


def estatistica(split, por_faixa):
    faixas = sorted(por_faixa)
    v = np.array([por_faixa[t]["vies"] for t in faixas], dtype=float)
    ok = (v[:, 0] > 0) & (v[:, 2] > 0)
    v = v[ok]
    a_in = v[:, 1].sum() / v[:, 0].sum()
    a_out = v[:, 3].sum() / v[:, 2].sum()
    rng = np.random.default_rng(stats.SEED)
    idx = rng.integers(0, len(v), size=(stats.N_BOOTSTRAP, len(v)))
    amostra = v[idx]                                  # (B, n, 4)
    deltas = (amostra[..., 1].sum(1) / amostra[..., 0].sum(1)
              - amostra[..., 3].sum(1) / amostra[..., 2].sum(1))
    alfa = stats.ALFA
    lo, hi = np.percentile(deltas, [100 * alfa / 2, 100 * (1 - alfa / 2)])
    cauda = min(float(np.mean(deltas <= 0)), float(np.mean(deltas >= 0)))
    p = min(1.0, max(2.0 * cauda, 1.0 / stats.N_BOOTSTRAP))
    return {"split": split, "ref_camada": f"chord[{ad.REF_CAMADA}]",
            "variante": "D0rg", "nivel": "root", "n_faixas": len(faixas),
            "n_faixas_duas_regioes": int(ok.sum()),
            "tempo_dentro_s": round(float(v[:, 0].sum()), 3),
            "tempo_fora_s": round(float(v[:, 2].sum()), 3),
            "acerto_dentro": round(float(a_in), 9),
            "acerto_fora": round(float(a_out), 9),
            "delta": round(float(a_in - a_out), 9),
            "ic95_min": round(float(lo), 9), "ic95_max": round(float(hi), 9),
            "p_bootstrap": f"{p:.6g}"}


def main():
    projeto = runner._commit()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    linhas = []
    for split in ad.SPLITS:
        r = estatistica(split, ad.rodar(split))
        linhas.append(r)
        print(f"{split}: dentro {100 * r['acerto_dentro']:.2f} fora "
              f"{100 * r['acerto_fora']:.2f} Δ {100 * r['delta']:+.2f} "
              f"[{100 * r['ic95_min']:+.2f}; {100 * r['ic95_max']:+.2f}] "
              f"faixas {r['n_faixas_duas_regioes']}/{r['n_faixas']}")
    p = RESULTS / f"vies_selecao_agregado_{ts}.csv"
    with p.open("w", encoding="utf-8", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=CAMPOS)
        w.writeheader()
        w.writerows(linhas)
    meta = {"gerado_em": ts, "gerado_por": "vies_selecao.py",
            "post_review": True, "projeto": projeto,
            "manifest": ad.MANIFEST, "ref_camada": f"chord[{ad.REF_CAMADA}]",
            "seed": stats.SEED, "n_bootstrap": stats.N_BOOTSTRAP,
            "alfa": stats.ALFA,
            "definicao": "Δ = Σacerto_in/Σtempo_in − Σacerto_out/Σtempo_out "
                         "(D0rg, root); IC: bootstrap pareado por faixa "
                         "recalculando as duas razões de somas; só faixas "
                         "com tempo nas duas regiões",
            "substitui": "coluna diferenca de vies_selecao_20261117_004137.csv"}
    p.with_name(p.stem + "_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("escrito", p.relative_to(ROOT).as_posix())
    nota_tex(p)


def nota_tex(csv_path):
    """Reescreve a nota de viés de seleção em tab_decomposicao.tex a partir
    do CSV (a linha que começa com 'Viés de seleção')."""
    def f(x, sinal=False):
        s = f"{100 * float(x):{'+' if sinal else ''}.2f}"
        return s.replace(".", ",")
    with Path(csv_path).open(encoding="utf-8", newline="") as fp:
        rs = {r["split"]: r for r in csv.DictReader(fp)}
    partes = [f"\\emph{{{s}}}: dentro {f(r['acerto_dentro'])} \\%, fora "
              f"{f(r['acerto_fora'])} \\%, $\\Delta$ = {f(r['delta'], True)} "
              f"p.p., IC [{f(r['ic95_min'], True)}; {f(r['ic95_max'], True)}], "
              f"$n$ = {r['n_faixas_duas_regioes']}"
              for s, r in rs.items()]
    nome = Path(csv_path).name.replace("_", "\\_")
    nova = ("  \\parbox{\\linewidth}{\\footnotesize Viés de seleção --- acurácia "
            "root de \\texttt{D0rg} agregada por duração dentro e fora da "
            "máscara comum (células rotuladas por \\texttt{C} e por "
            "\\texttt{D}); IC 95 \\% do bootstrap pareado por faixa: "
            + "; ".join(partes) + f". Fonte: \\texttt{{{nome}}}.}}")
    tex = ad.TABELAS / "tab_decomposicao.tex"
    linhas = tex.read_text(encoding="utf-8").split("\n")
    alvo = [i for i, l in enumerate(linhas) if "Viés de seleção ---" in l]
    if len(alvo) != 1:
        raise SystemExit("nota de viés não encontrada em tab_decomposicao.tex")
    linhas[alvo[0]] = nova
    tex.write_text("\n".join(linhas), encoding="utf-8")
    print("nota reescrita em", tex.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    if "--so-nota" in sys.argv:
        nota_tex(sorted(RESULTS.glob("vies_selecao_agregado_2*.csv"))[-1])
    else:
        sys.exit(main())
