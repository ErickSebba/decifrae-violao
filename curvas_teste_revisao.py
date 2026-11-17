"""
curvas_teste_revisao.py
=======================
Curvas de acerto × cobertura NO TESTE e comparação de C e D na mesma
cobertura, por interpolação linear. Análise pós-revisão; protocolo em
`docs/ADENDO_REVISAO.md` §5, commitado antes desta execução.

    C  confidence_gate em {0} ∪ {0,50 … 0,90, passo 0,01}
    D  n_logprob em {−1 … −8, passo 0,25} ∪ {−1e9}

Por ponto e faixa (chord[0], nível root): cobertura, root_rotulado e root na
faixa toda. Agregação ponderada pela duração; root_rotulado exclui as faixas
de cobertura zero. Nos alvos de cobertura, cada curva é interpolada
linearmente (métrica agregada contra cobertura agregada) e Δ = D − C. IC por
bootstrap pareado por faixa: em cada reamostragem as duas curvas são
reagregadas com os mesmos pesos e reinterpoladas.

Saídas (post_review=true):
    data/results/curvas_teste_<ts>.csv              uma linha por curva×ponto×faixa
    data/results/cobertura_igualada_teste_<ts>.csv  resumo por alvo e métrica
    artigo-ACDSA/tabelas/tab_cobertura_igualada.tex
    artigo-ACDSA/figuras/fig_cobertura_teste.pdf/.png

    python curvas_teste_revisao.py
"""

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
import stats
from config import PRE_CHROMA
from evaluate import score_segments

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "data" / "results"
MANIFEST = ROOT / "data" / "manifests" / "guitarset_comping.csv"
ARTIGO = ROOT / "artigo-ACDSA"

REF_CAMADA = 0
GATES_C = [0.0] + [round(0.50 + 0.01 * i, 2) for i in range(41)]
LOGPROBS_D = sorted(set(
    [round(-1.0 - 0.25 * i, 2) for i in range(29)]
    # refinamento entre -2,25 e -2,75 (docs/ADENDO_REVISAO.md §7)
    + [round(-2.25 - 0.05 * i, 2) for i in range(1, 10)]), reverse=True) + [-1e9]
ALVOS = [0.60, 0.70, 0.77, 0.90]
METRICAS = ["root_rotulado", "root"]

CAMPOS_PONTOS = ["curva", "parametro", "valor", "track_id", "split",
                 "ref_camada", "duracao_s", "cobertura", "root_rotulado", "root"]
CAMPOS_RESUMO = ["alvo_cobertura", "metrica", "C_interp", "D_interp", "delta",
                 "ic95_min", "ic95_max", "ic_cruza_zero", "p_bootstrap",
                 "n_boot_validos", "n_faixas"]


def _pontos():
    C, D = runner.VARIANTES["C"], runner.VARIANTES["D"]
    pts = [("C", "confidence_gate", g,
            replace(C, post=replace(C.post, confidence_gate=g))) for g in GATES_C]
    pts += [("D", "n_logprob", b,
             replace(D, post=replace(D.post, n_logprob=b))) for b in LOGPROBS_D]
    return pts


def medir():
    linhas = runner._linhas(MANIFEST, {"test"})
    refs, feats = {}, {}
    for row in linhas:
        tid = row["track_id"]
        refs[tid] = ds.load_guitarset(ROOT / row["annotation_path"],
                                      index=REF_CAMADA)
        feats[tid] = cache.get_features(ROOT / row["audio_path"], PRE_CHROMA)
    out = []
    pts = _pontos()
    for i, (curva, par, valor, var) in enumerate(pts, start=1):
        for row in linhas:
            tid = row["track_id"]
            est = runner.estimar(var, feats[tid])
            ref = refs[tid]
            diag = runner.diagnostico(est, ref)
            rot = runner.acerto_no_tempo_rotulado(est, ref)
            sc = score_segments(est, ref, levels=["root"], ref_is_harte=True)
            out.append({
                "curva": curva, "parametro": par, "valor": valor,
                "track_id": tid, "split": row["split"],
                "ref_camada": f"chord[{REF_CAMADA}]",
                "duracao_s": round(runner._duracao(ref), 3),
                "cobertura": round(1.0 - diag["frac_n_est"], 6),
                "root_rotulado": rot["root_rotulado"],
                "root": round(sc["root"], 9)})
        sys.stdout.write(f"\r  ponto {i}/{len(pts)}   ")
        sys.stdout.flush()
    print()
    return out


def _matrizes(linhas, curva):
    """(valores, faixas, cobertura[P,T], métricas{nome: [P,T] com nan}, w[T])."""
    sub = [l for l in linhas if l["curva"] == curva]
    valores = sorted({l["valor"] for l in sub}, key=float)
    faixas = sorted({l["track_id"] for l in sub})
    iv = {v: i for i, v in enumerate(valores)}
    it = {t: j for j, t in enumerate(faixas)}
    cob = np.full((len(valores), len(faixas)), np.nan)
    mets = {m: np.full_like(cob, np.nan) for m in METRICAS}
    w = np.zeros(len(faixas))
    for l in sub:
        i, j = iv[l["valor"]], it[l["track_id"]]
        cob[i, j] = float(l["cobertura"])
        for m in METRICAS:
            mets[m][i, j] = float(l[m]) if l[m] != "" else np.nan
        w[j] = float(l["duracao_s"])
    return valores, faixas, cob, mets, w


def _agrega(M, W):
    """Média ponderada por linha de M [P,T] com pesos W [B,T] -> [B,P]; nan exclui."""
    ok = ~np.isnan(M)
    return (W @ np.where(ok, M, 0.0).T) / (W @ ok.T.astype(float))


def _interp(cob, met, alvo):
    """Interpolação linear da métrica na cobertura `alvo`; nan fora da faixa."""
    ordem = np.argsort(cob, kind="stable")
    x, y = cob[ordem], met[ordem]
    ok = ~np.isnan(x) & ~np.isnan(y)
    x, y = x[ok], y[ok]
    if len(x) < 2 or alvo < x[0] or alvo > x[-1]:
        return np.nan
    return float(np.interp(alvo, x, y))


def comparar(linhas):
    _, fc, cobC, metC, wC = _matrizes(linhas, "C")
    _, fd, cobD, metD, wD = _matrizes(linhas, "D")
    assert fc == fd and np.allclose(wC, wD)
    w, T = wC, len(fc)
    rng = np.random.default_rng(stats.SEED)
    idx = rng.integers(0, T, size=(stats.N_BOOTSTRAP, T))
    K = np.zeros((stats.N_BOOTSTRAP, T))
    np.add.at(K, (np.repeat(np.arange(stats.N_BOOTSTRAP), T), idx.ravel()), 1)
    Wb = K * w                                   # [B,T]
    W0 = w[None, :]                              # estimativa pontual
    aggC = {"cob": _agrega(cobC, W0)[0], **{m: _agrega(metC[m], W0)[0] for m in METRICAS}}
    aggD = {"cob": _agrega(cobD, W0)[0], **{m: _agrega(metD[m], W0)[0] for m in METRICAS}}
    bC = {"cob": _agrega(cobC, Wb), **{m: _agrega(metC[m], Wb) for m in METRICAS}}
    bD = {"cob": _agrega(cobD, Wb), **{m: _agrega(metD[m], Wb) for m in METRICAS}}
    resumo = []
    for alvo in ALVOS:
        for m in METRICAS:
            c0 = _interp(aggC["cob"], aggC[m], alvo)
            d0 = _interp(aggD["cob"], aggD[m], alvo)
            ds_ = np.array([_interp(bD["cob"][b], bD[m][b], alvo)
                            - _interp(bC["cob"][b], bC[m][b], alvo)
                            for b in range(stats.N_BOOTSTRAP)])
            ds_ = ds_[~np.isnan(ds_)]
            if len(ds_):
                lo, hi = np.percentile(ds_, [100 * stats.ALFA / 2,
                                             100 * (1 - stats.ALFA / 2)])
                cauda = min(np.mean(ds_ <= 0), np.mean(ds_ >= 0))
                p = min(1.0, max(2 * cauda, 1 / len(ds_)))
            else:
                lo = hi = p = np.nan
            resumo.append({
                "alvo_cobertura": alvo, "metrica": m,
                "C_interp": round(c0, 9), "D_interp": round(d0, 9),
                "delta": round(d0 - c0, 9),
                "ic95_min": round(float(lo), 9), "ic95_max": round(float(hi), 9),
                "ic_cruza_zero": "sim" if lo <= 0 <= hi else "nao",
                "p_bootstrap": f"{p:.6g}", "n_boot_validos": int(len(ds_)),
                "n_faixas": T})
    return resumo, aggC, aggD


def tabela(resumo, nome_csv):
    from figuras_artigo import _tabela, pct, sinal, tex_escape
    corpo = ["Cobertura & Métrica & C & D & $\\Delta$ (D$-$C) [IC 95\\%] & $n_{boot}$ \\\\",
             "\\midrule"]
    ant = None
    for r in resumo:
        if ant is not None and r["alvo_cobertura"] != ant:
            corpo.append("\\addlinespace")
        cel = (f"{pct(r['alvo_cobertura'], 0)}\\,\\%"
               if r["alvo_cobertura"] != ant else "")
        ant = r["alvo_cobertura"]
        corpo.append(" & ".join([
            cel, "rotulado" if r["metrica"] == "root_rotulado" else "faixa toda",
            pct(r["C_interp"]), pct(r["D_interp"]),
            f"{sinal(r['delta'])} [{sinal(r['ic95_min'])}; {sinal(r['ic95_max'])}]",
            str(r["n_boot_validos"])]) + " \\\\")
    cap = ("C e D na mesma cobertura, no \\emph{test} (\\texttt{chord[0]}, "
           "\\texttt{root}, \\%): cada curva (C varia \\texttt{confidence\\_gate}, "
           "D varia \\texttt{n\\_logprob}) é interpolada linearmente no alvo de "
           "cobertura. $\\Delta$ em pontos percentuais; IC por bootstrap pareado "
           "por faixa (10\\,000, semente 0), reinterpolando a cada reamostragem. "
           "Análise pós-revisão, protocolo registrado antes da execução. Fonte: "
           "\\texttt{" + tex_escape(nome_csv) + "}.")
    tex = _tabela("table", "llrrrr", corpo, cap, "tab:cobertura_igualada")
    tex = tex.replace("% gerado por figuras_artigo.py",
                      "% gerado por curvas_teste_revisao.py", 1)
    destino = ARTIGO / "tabelas" / "tab_cobertura_igualada.tex"
    destino.write_text(tex, encoding="utf-8")
    return destino


def figura(aggC, aggD):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from figuras_artigo import _rc
    _rc()
    fig, axs = plt.subplots(2, 1, figsize=(3.5, 3.6), sharex=True,
                            layout="constrained")
    for ax, m, titulo in zip(axs, METRICAS, ("root no tempo rotulado (%)",
                                             "root na faixa toda (%)")):
        for agg, nome, cor, mk in ((aggC, "C (confidence_gate)", "#2a6f97", "o"),
                                   (aggD, "D (n_logprob)", "#c1121f", "s")):
            o = np.argsort(agg["cob"])
            ax.plot(100 * agg["cob"][o], 100 * agg[m][o], color=cor, lw=1.0,
                    marker=mk, ms=2.2, label=nome)
        for a in ALVOS:
            ax.axvline(100 * a, color="0.6", lw=0.6, ls=":")
        ax.set_ylabel(titulo)
    axs[1].set_xlabel("cobertura (%)")
    axs[0].legend(loc="lower left", frameon=False)
    base = ARTIGO / "figuras" / "fig_cobertura_teste"
    saidas = []
    for ext, kw in (("pdf", {}), ("png", {"dpi": 200})):
        p = base.with_suffix(f".{ext}")
        fig.savefig(p, format=ext, **kw)       # sem bbox tight: 3,5 pol exatas
        saidas.append(p)
    plt.close(fig)
    return saidas


def _escrever(nome, ts, linhas, campos, extra):
    p = RESULTS / f"{nome}_{ts}.csv"
    if p.exists():
        raise SystemExit(f"{p.name} já existe; não sobrescrevo")
    with p.open("w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=campos)
        w.writeheader()
        w.writerows(linhas)
    import librosa
    import mir_eval
    meta = {"gerado_em": datetime.now().isoformat(timespec="seconds"),
            "post_review": True, "script": "curvas_teste_revisao.py",
            "protocolo": "docs/ADENDO_REVISAO.md §5",
            "splits": ["test"], "ref_camada": f"chord[{REF_CAMADA}]",
            "gates_C": GATES_C, "n_logprobs_D": LOGPROBS_D, "alvos": ALVOS,
            "n_bootstrap": stats.N_BOOTSTRAP, "seed": stats.SEED,
            "n_linhas": len(linhas),
            "versoes": {"python": sys.version.split()[0],
                        "numpy": np.__version__, "librosa": librosa.__version__,
                        "mir_eval": mir_eval.__version__},
            "projeto": _PROJETO, **extra}
    p.with_name(p.stem + "_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def main():
    # commit e estado da árvore lidos antes de escrever qualquer saída
    global _PROJETO
    _PROJETO = runner._commit()
    t0 = time.perf_counter()
    linhas = medir()
    resumo, aggC, aggD = comparar(linhas)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    # meta gravado ANTES de escrever tabela/figura, para a árvore estar limpa
    p1 = _escrever("curvas_teste", ts, linhas, CAMPOS_PONTOS, {})
    p2 = _escrever("cobertura_igualada_teste", ts, resumo, CAMPOS_RESUMO,
                   {"entrada": p1.name,
                    "definicao": "Δ = D − C na mesma cobertura agregada, "
                                 "interpolação linear; IC por bootstrap pareado "
                                 "por faixa, reinterpolando"})
    tex = tabela(resumo, p2.name)
    figs = figura(aggC, aggD)
    for r in resumo:
        print(f"{100*r['alvo_cobertura']:4.0f}% {r['metrica']:14s} "
              f"C={100*r['C_interp']:.2f} D={100*r['D_interp']:.2f} "
              f"Δ={100*r['delta']:+.2f} [{100*r['ic95_min']:+.2f}; "
              f"{100*r['ic95_max']:+.2f}] n={r['n_boot_validos']}")
    print("cobertura C: min %.4f max %.4f | D: min %.4f max %.4f" % (
        np.nanmin(aggC["cob"]), np.nanmax(aggC["cob"]),
        np.nanmin(aggD["cob"]), np.nanmax(aggD["cob"])))
    print(f"{time.perf_counter() - t0:.0f}s | {p1.name} {p2.name} {tex.name} "
          + " ".join(f.name for f in figs))


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    main()
