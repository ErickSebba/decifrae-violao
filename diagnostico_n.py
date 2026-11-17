"""
diagnostico_n.py
================
Diagnóstico do estado N (protocolo em `docs/ADENDO_REVISAO.md` §9.2).

Por base e célula de batida i: ℓ_i(k) = log softmax(e_i / temp)_k, como em
`viterbi.decode`. Mede max_k ℓ_i(k): mediana, IQR e fração abaixo de
β = n_logprob da D (−2,5). Variantes: D (60 templates, sem as células
forçadas a N pelo gate), D0rg-60 e D0rg-24 (o classificador da F0rg).

Só lê features do cache; não ajusta nada.

Saídas (post_review=true):
  data/results/diagnostico_n_<ts>.csv          uma linha por faixa × variante
  data/results/diagnostico_n_resumo_<ts>.csv   base × variante
  artigo-ACDSA/figuras/fig_diagnostico_n.pdf/.png

    python diagnostico_n.py
"""

import csv
import json
from datetime import datetime
from pathlib import Path

import numpy as np

import cache
import runner

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "data" / "results"
ARTIGO = ROOT / "artigo-ACDSA"

BASES = [
    ("gs_test", "GuitarSet teste", "guitarset_comping.csv", "test"),
    ("idmt_g", "IDMT-SMT-Guitar", "idmt_smt_guitar.csv", "external"),
    ("idmt_c", "IDMT-SMT-Chords", "idmt_smt_chords.csv", "eval"),
]
# (rótulo, variante do runner, descarta células forçadas pelo gate)
CASOS = [("D", "D", True), ("D0rg-60", "D0rg", False), ("D0rg-24", "F0rg", False)]


def _linhas(manifest, split):
    with (ROOT / "data" / "manifests" / manifest).open(encoding="utf-8") as fp:
        return [r for r in csv.DictReader(fp)
                if r["split"] == split
                and r["excluded"].strip().lower() != "true"]


def max_logprob(emissoes, temp):
    """max_k log softmax(e/temp)_k por linha; igual ao `viterbi._softmax`."""
    z = (emissoes - emissoes.max(axis=1, keepdims=True)) / max(temp, 1e-6)
    p = np.exp(z)
    p = p / (p.sum(axis=1, keepdims=True) + 1e-12)
    return np.log(p.max(axis=1) + 1e-12)


def celulas(feat, variante):
    """(max ℓ por célula, máscara de células forçadas a N pelo gate)."""
    post = variante.post
    clf = runner.classificador_de(post, variante.vocab)
    rms = feat.seg_rms
    n = feat.chroma.shape[1]
    vivos = rms > post.abs_floor
    mediana = float(np.median(rms[vivos])) if np.any(vivos) else 0.0
    gate = max(post.abs_floor, post.rel_gate * mediana)
    em = np.array([clf.emission(feat.chroma[:, i]) for i in range(n)])
    return max_logprob(em, post.temp), rms[:n] < gate


def main():
    projeto = runner._commit()
    variantes = runner._variantes()
    beta = variantes["D"].post.n_logprob
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    por_faixa, valores = [], {}
    for chave, rotulo, manifest, split in BASES:
        for i, row in enumerate(_linhas(manifest, split), 1):
            feat = cache.get_features(ROOT / row["audio_path"],
                                      variantes["D"].pre)
            for nome, vnome, tira_gate in CASOS:
                v = variantes[vnome]
                m, forc = celulas(feat, v)
                usa = m[~forc] if tira_gate else m
                valores.setdefault((chave, nome), []).append(usa)
                por_faixa.append({
                    "base": chave, "track_id": row["track_id"], "caso": nome,
                    "variante": vnome, "vocabulario": v.vocab,
                    "temp": v.post.temp, "beta": beta,
                    "n_celulas": len(m), "n_forcadas_gate": int(forc.sum()),
                    "n_usadas": len(usa),
                    "mediana": round(float(np.median(usa)), 6) if len(usa) else "",
                    "frac_abaixo_beta": (round(float(np.mean(usa < beta)), 6)
                                         if len(usa) else ""),
                })
            print(f"\r  {rotulo}: {i}", end="", flush=True)
        print()

    resumo = []
    for (chave, nome), ls in valores.items():
        x = np.concatenate(ls)
        q25, q50, q75 = np.percentile(x, [25, 50, 75])
        n_forc = sum(r["n_forcadas_gate"] for r in por_faixa
                     if r["base"] == chave and r["caso"] == nome)
        n_tot = sum(r["n_celulas"] for r in por_faixa
                    if r["base"] == chave and r["caso"] == nome)
        resumo.append({"base": chave, "caso": nome, "n_faixas": len(ls),
                       "n_celulas": n_tot, "n_forcadas_gate": n_forc,
                       "n_usadas": len(x), "mediana": round(q50, 4),
                       "q25": round(q25, 4), "q75": round(q75, 4),
                       "frac_abaixo_beta": round(float(np.mean(x < beta)), 4),
                       "beta": beta})
        print(f"{chave:8} {nome:8} n={len(x):6} mediana={q50:.3f} "
              f"IQR=[{q25:.3f}; {q75:.3f}] <β={np.mean(x < beta):.3f} "
              f"forçadas={n_forc}/{n_tot}")

    meta = {"gerado_em": ts, "post_review": True, "projeto": projeto,
            "protocolo": "docs/ADENDO_REVISAO.md §9.2", "beta": beta,
            "casos": CASOS, "bases": BASES,
            "nota": "contagem por célula de batida, não ponderada por duração"}
    for nome, linhas in (("diagnostico_n", por_faixa),
                         ("diagnostico_n_resumo", resumo)):
        p = RESULTS / f"{nome}_{ts}.csv"
        with p.open("w", encoding="utf-8", newline="") as fp:
            w = csv.DictWriter(fp, fieldnames=list(linhas[0]))
            w.writeheader()
            w.writerows(linhas)
        p.with_name(p.stem + "_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    figura(valores, beta)
    print(f"saídas: diagnostico_n_{ts}.csv, diagnostico_n_resumo_{ts}.csv")


def figura(valores, beta):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from figuras_artigo import _rc
    _rc()
    fig, ax = plt.subplots(figsize=(3.5, 2.2), layout="constrained")
    cores = {"gs_test": "#2a6f97", "idmt_g": "#c1121f", "idmt_c": "#6a994e"}
    bins = np.linspace(-4.2, 0, 43)
    for chave, rotulo, *_ in BASES:
        x = np.clip(np.concatenate(valores[(chave, "D")]), bins[0], 0)
        ax.hist(x, bins=bins, density=True, histtype="step", lw=1.1,
                color=cores[chave], label=rotulo)
    ax.axvline(beta, color="0.2", lw=0.8, ls="--")
    ax.text(beta, ax.get_ylim()[1] * 0.95, f" β = {beta:g}", fontsize=6,
            va="top", ha="left")
    ax.set_xlabel(r"$\max_k \ell_i(k)$ por célula (D, 60 templates)")
    ax.set_ylabel("densidade")
    ax.legend(frameon=False, fontsize=6, loc="upper left")
    base = ARTIGO / "figuras" / "fig_diagnostico_n"
    for ext, kw in (("pdf", {}), ("png", {"dpi": 200})):
        fig.savefig(base.with_suffix(f".{ext}"), format=ext, **kw)
    plt.close(fig)


if __name__ == "__main__":
    main()
