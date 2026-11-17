"""
analise_externo.py
==================
Entregáveis das bases externas e dos baselines (protocolo em
`docs/ADENDO_REVISAO.md` §8). Só LÊ CSVs já commitados; não roda pipeline.

Entradas, localizadas pelo meta.json (nunca por nome digitado à mão):
  - ablações das 8 variantes congeladas: GuitarSet teste chord[0] (as rodadas
    de setembro) e as duas bases externas (`post_review=true`);
  - baselines `baseline_<chordino|madmom>_*_ref0.csv` dos mesmos conjuntos;
  - `stats_*` dos 15 contrastes por base (GuitarSet teste com a família
    completa de 15; externas com `post_review=true`);
  - cobertura da referência por nível (`coverage.csv` para o GuitarSet,
    `coverage_externo_*.csv` para as externas).

Saídas (post_review=true):
  data/results/externo_resumo_<ts>.csv          base × sistema × métrica
  data/results/transferencia_<ts>.csv           15 contrastes × base
  data/results/transferencia_guitarra_<ts>.csv  15 contrastes × guitarra (IDMT-SMT-Guitar)
  artigo-ACDSA/tabelas/tab_externo.tex
  artigo-ACDSA/tabelas/tab_transferencia.tex
  artigo-ACDSA/figuras/fig_transferencia.pdf/.png

    python analise_externo.py
"""

import csv
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

import runner
import stats

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "data" / "results"
ARTIGO = ROOT / "artigo-ACDSA"

VARIANTES = ["V4", "V4b", "C", "D", "E", "C0rg", "D0rg", "F0rg"]
BASELINES = ["chordino", "madmom"]
METRICAS = ["root", "root_rotulado", "cobertura", "majmin", "sevenths", "overseg"]
NIVEIS_COB = ["root", "majmin", "sevenths", "mirex"]

# (chave, rótulo, manifest, split, dataset no coverage)
BASES = [
    ("gs_test", "GuitarSet teste", "guitarset_comping.csv", "test", "guitarset"),
    ("idmt_g", "IDMT-SMT-Guitar", "idmt_smt_guitar.csv", "external",
     "idmt-smt-guitar"),
    ("idmt_c", "IDMT-SMT-Chords", "idmt_smt_chords.csv", "eval",
     "idmt-smt-chords"),
]


# --------------------------------------------------------------------------
# localização das entradas
# --------------------------------------------------------------------------
def _meta(p):
    return json.loads(p.with_name(p.stem + "_meta.json").read_text(encoding="utf-8"))


def _rel(p):
    return Path(p).resolve().relative_to(ROOT).as_posix()


def ablacoes(manifest, split):
    """CSVs de ablação chord[0] daquele manifest e split, com as variantes."""
    achados = []
    for p in sorted(RESULTS.glob("ablation_*_ref0.csv")):
        m = _meta(p)
        if (str(m.get("manifest", "")).replace("\\", "/").endswith(manifest)
                and m.get("splits") == [split]
                and set(m.get("variantes", [])) & set(VARIANTES)):
            achados.append(p)
    # no GuitarSet teste, só as rodadas congeladas (sem post_review): as
    # variantes pós-revisão não entram nesta tabela
    if split == "test":
        achados = [p for p in achados if not _meta(p).get("post_review")]
    return achados


def baseline(nome, manifest, split):
    cands = []
    for p in sorted(RESULTS.glob(f"baseline_{nome}_*_ref0.csv")):
        m = _meta(p)
        if (str(m.get("manifest", "")).replace("\\", "/").endswith(manifest)
                and sorted(m.get("splits", [])) == [split]):
            cands.append(p)
    return cands[-1] if cands else None


def stats_de(split):
    def ok(m):
        return (m.get("split") == split and m.get("ref_camada") == "chord[0]"
                and m.get("n_comparacoes") == 15)
    cands = [p for p in sorted(RESULTS.glob(f"stats_{split}_ref0_*.csv"))
             if ok(_meta(p)) and (split == "test" or _meta(p).get("post_review"))]
    if not cands:
        raise SystemExit(f"sem stats de 15 comparações para o split {split}")
    return cands[-1]


def cobertura_ref():
    """{dataset: {nivel: fração comparável}} (GuitarSet teste chord[0])."""
    cob = {}
    for r in csv.DictReader((RESULTS / "coverage.csv").open(encoding="utf-8")):
        if r["dataset"] == "guitarset" and r["camada"] == "chord[0]" and r["split"] == "test":
            cob.setdefault("guitarset", {})[r["nivel"]] = float(r["comparavel_frac"])
    ext = sorted(RESULTS.glob("coverage_externo_*.csv"))[-1]
    for r in csv.DictReader(ext.open(encoding="utf-8")):
        cob.setdefault(r["dataset"], {})[r["nivel"]] = float(r["comparavel_frac"])
    return cob, ["data/results/coverage.csv", _rel(ext)]


# --------------------------------------------------------------------------
# agregação
# --------------------------------------------------------------------------
def _wmean(linhas, col):
    pares = [(float(l[col]), float(l["duracao_s"])) for l in linhas if l[col] != ""]
    w = sum(d for _, d in pares)
    return sum(v * d for v, d in pares) / w if w else float("nan")


def resumo_base(chave, rotulo, manifest, split):
    """Linhas (sistema, métricas) e as fontes usadas."""
    por_variante, _ = stats.carregar(*ablacoes(manifest, split))
    fontes = [_rel(p) for p in ablacoes(manifest, split)]
    sistemas = [(v, list(por_variante[v].values())) for v in VARIANTES
                if v in por_variante]
    for b in BASELINES:
        p = baseline(b, manifest, split)
        if p is None:
            continue
        fontes.append(_rel(p))
        with p.open(encoding="utf-8", newline="") as fp:
            sistemas.append((b.capitalize() if b == "chordino" else "madmom",
                             list(csv.DictReader(fp))))
    linhas = []
    for nome, ls in sistemas:
        for l in ls:
            l["cobertura"] = (1 - float(l["frac_n_est"])) if l["frac_n_est"] != "" else ""
        linhas.append({"base": chave, "rotulo_base": rotulo, "sistema": nome,
                       "n_faixas": len(ls),
                       **{m: round(_wmean(ls, m), 9) for m in METRICAS}})
    return linhas, fontes


def transferencia():
    """15 contrastes × base: Δ, IC, classe; e se o sinal do GS teste se mantém."""
    linhas, fontes = [], {}
    tabelas = {}
    for chave, rotulo, _, split, _ in BASES:
        p = stats_de(split)
        fontes[chave] = _rel(p)
        with p.open(encoding="utf-8", newline="") as fp:
            tabelas[chave] = {(r["par"], r["metrica"]): r for r in csv.DictReader(fp)}
    for a, b, metricas, isola in stats.PARES:
        for m in metricas:
            ref = tabelas["gs_test"][(f"{a} vs {b}", m)]
            s_ref = np.sign(float(ref["diferenca"]))
            for chave, rotulo, *_ in BASES:
                r = tabelas[chave][(f"{a} vs {b}", m)]
                d = float(r["diferenca"])
                linhas.append({
                    "par": f"{a} vs {b}", "metrica": m, "base": chave,
                    "rotulo_base": rotulo, "n_faixas": r["n_faixas"],
                    "delta": round(d, 9), "ic95_min": r["ic95_min"],
                    "ic95_max": r["ic95_max"], "classificacao": r["classificacao"],
                    "p_bootstrap_holm": r["p_bootstrap_holm"],
                    # Δ = 0 exato (sistemas idênticos na base) não é troca
                    # de sinal: fica "nulo" e sai da contagem
                    "sinal_igual_gs_teste": ("" if chave == "gs_test" else
                                             "nulo" if d == 0 else
                                             ("sim" if np.sign(d) == s_ref else "nao")),
                })
    return linhas, fontes


def por_guitarra():
    """Δ dos 15 contrastes por guitarra no IDMT-SMT-Guitar, IC por bootstrap
    pareado reamostrando faixas dentro da guitarra."""
    man = ROOT / "data" / "manifests" / "idmt_smt_guitar.csv"
    guit = {r["track_id"]: r["guitarra"]
            for r in csv.DictReader(man.open(encoding="utf-8"))
            if r["excluded"].strip().lower() != "true"}
    por_variante, dur = stats.carregar(*ablacoes("idmt_smt_guitar.csv", "external"))
    linhas = []
    for g in sorted(set(guit.values())):
        faixas = {t for t, x in guit.items() if x == g}
        sub = {v: {t: l for t, l in d.items() if t in faixas}
               for v, d in por_variante.items()}
        for a, b, metricas, _ in stats.PARES:
            for m in metricas:
                va, vb, w, desc = stats._pares_alinhados(sub, dur, a, b, m)
                d = vb - va
                lo, hi, _ = stats.bootstrap(d, w)
                linhas.append({"guitarra": g, "par": f"{a} vs {b}", "metrica": m,
                               "n_faixas": len(d),
                               "delta": round(stats._media_ponderada(d, w), 9),
                               "ic95_min": round(lo, 9), "ic95_max": round(hi, 9)})
    return linhas


# --------------------------------------------------------------------------
# saídas
# --------------------------------------------------------------------------
def _pct(x, casas=1):
    return "--" if x == "" or x != x else f"{100 * float(x):.{casas}f}"


def tab_externo(resumo, cob, fontes):
    from figuras_artigo import _tabela, tex_escape
    corpo = ["Sistema & root & rot. & cob. & majmin & 7ths & overseg \\\\",
             "\\midrule"]
    for chave, rotulo, _, _, ds in BASES:
        c = cob.get(ds, {})
        cab = (f"\\multicolumn{{7}}{{l}}{{\\emph{{{rotulo}}} --- ref. comparável: "
               + ", ".join(f"{n} {_pct(c.get(n, ''), 0)}\\%" for n in NIVEIS_COB)
               + "} \\\\")
        corpo += ["\\addlinespace", cab]
        for l in [x for x in resumo if x["base"] == chave]:
            corpo.append(" & ".join(
                [f"\\texttt{{{tex_escape(l['sistema'])}}}"]
                + [_pct(l[m]) for m in METRICAS]) + " \\\\")
    cap = ("Variantes congeladas e baselines de terceiros nas bases externas e "
           "no \\emph{test} do GuitarSet (\\texttt{chord[0]}). Acurácias em \\%, "
           "média ponderada pela duração; \\emph{rot.} = \\texttt{root} no tempo "
           "rotulado, \\emph{cob.} = cobertura. Nenhuma configuração foi ajustada "
           "fora do GuitarSet. Análise pós-revisão.")
    tex = _tabela("table*", "lrrrrrr", corpo, cap, "tab:externo",
                  notas=["Fontes: " + "; ".join(f"\\texttt{{{tex_escape(f)}}}"
                                                for f in fontes)])
    tex = tex.replace("% gerado por figuras_artigo.py",
                      "% gerado por analise_externo.py", 1)
    (ARTIGO / "tabelas" / "tab_externo.tex").write_text(tex, encoding="utf-8")


def _delta_tex(d):
    v = 100 * float(d)
    if v == 0:
        return "$0$"
    return f"${v:+.2f}$" if abs(v) < 0.05 else f"${v:+.1f}$"


def tab_transferencia(trans, fontes):
    from figuras_artigo import _tabela, tex_escape, CLASSIF
    abrev = {"confirmado": "conf.", "empate": "emp.", "fragil": "frág."}
    corpo = ["Par ($b-a$) & Métrica & "
             + " & ".join(f"\\multicolumn{{2}}{{c}}{{{r}}}" for _, r, *_ in BASES)
             + " & Sinal \\\\",
             "\\cmidrule(lr){3-4}\\cmidrule(lr){5-6}\\cmidrule(lr){7-8}",
             " & & " + " & ".join(["$\\Delta$ & classe"] * len(BASES)) + " & \\\\",
             "\\midrule"]
    ant = None
    for a, b, metricas, _ in stats.PARES:
        for m in metricas:
            par = f"{a} vs {b}"
            ls = {l["base"]: l for l in trans if l["par"] == par and l["metrica"] == m}
            cel = []
            for chave, *_ in BASES:
                l = ls[chave]
                cel += [_delta_tex(l["delta"]), abrev[l["classificacao"]]]
            sinais = [ls[k]["sinal_igual_gs_teste"] for k in ("idmt_g", "idmt_c")]
            mantem = sinais.count("sim")
            validos = len(sinais) - sinais.count("nulo")
            if par != ant and ant is not None:
                corpo.append("\\addlinespace")
            corpo.append(" & ".join(
                [(f"\\texttt{{{tex_escape(a)}}}$\\to$\\texttt{{{tex_escape(b)}}}"
                  if par != ant else ""), f"\\texttt{{{tex_escape(m)}}}"]
                + cel + [f"{mantem}/{validos}"
                         + ("$^\\dagger$" if validos < len(sinais) else "")])
                + " \\\\")
            ant = par
    cap = ("Os 15 contrastes pré-registrados no \\emph{test} do GuitarSet "
           "(\\texttt{chord[0]}) e nas duas bases externas. $\\Delta$ em pontos "
           "percentuais; classe pelo critério do congelamento (IC 95\\% do bootstrap "
           "pareado por faixa e Holm sobre 15). \\emph{Sinal}: em quantas das duas "
           "bases externas o sinal de $\\Delta$ é o mesmo do GuitarSet; "
           "$^\\dagger$: $\\Delta = 0$ exato no IDMT-SMT-Chords (\\texttt{D} e "
           "\\texttt{E} produzem a mesma saída lá), fora da contagem. "
           "O IDMT-SMT-Chords tem 6 faixas. Análise pós-revisão.")
    tex = _tabela("table*", "ll" + "rl" * len(BASES) + "c", corpo, cap,
                  "tab:transferencia",
                  notas=["Fontes: " + "; ".join(f"\\texttt{{{tex_escape(f)}}}"
                                                for f in fontes.values())])
    tex = tex.replace("% gerado por figuras_artigo.py",
                      "% gerado por analise_externo.py", 1)
    (ARTIGO / "tabelas" / "tab_transferencia.tex").write_text(tex, encoding="utf-8")


X_MIN = -45.0   # eixo cortado; valores abaixo são anotados na borda


def fig_transferencia(trans):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from figuras_artigo import _rc
    _rc()
    rot = [(f"{a}→{b} {m}") for a, b, ms, _ in stats.PARES for m in ms]
    chaves = [(f"{a} vs {b}", m) for a, b, ms, _ in stats.PARES for m in ms]
    fig, ax = plt.subplots(figsize=(3.5, 4.6), layout="constrained")
    estilos = {"gs_test": ("#2a6f97", "o", -0.22), "idmt_g": ("#c1121f", "s", 0.0),
               "idmt_c": ("#6a994e", "^", 0.22)}
    for chave, rotulo, *_ in BASES:
        cor, mk, dy = estilos[chave]
        for i, (par, m) in enumerate(chaves):
            l = [x for x in trans if x["base"] == chave and x["par"] == par
                 and x["metrica"] == m][0]
            d, lo, hi = (100 * float(l[k]) for k in ("delta", "ic95_min", "ic95_max"))
            y = len(chaves) - 1 - i + dy
            if d < X_MIN:
                # fora da escala: seta na borda com o valor (e o IC) escrito
                ax.annotate("", xy=(X_MIN, y), xytext=(X_MIN + 4, y),
                            arrowprops=dict(arrowstyle="->", color=cor, lw=0.8))
                ax.text(X_MIN + 4.5, y, f"{d:.1f} [{lo:.1f}; {hi:.1f}]",
                        color=cor, fontsize=5.5, va="center")
                ax.plot([], [], mk, color=cor, ms=3,
                        label=rotulo if i == 0 else None)
                continue
            ax.plot([max(lo, X_MIN), hi], [y, y], color=cor, lw=0.8)
            ax.plot(d, y, mk, color=cor, ms=3,
                    label=rotulo if i == 0 else None)
    ax.axvline(0, color="0.3", lw=0.6)
    ax.set_xlim(X_MIN, None)
    ax.set_yticks(range(len(chaves)))
    ax.set_yticklabels(rot[::-1])
    ax.set_xlabel("Δ = b − a (pontos percentuais), IC 95 %")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=2,
              frameon=False, fontsize=6, handletextpad=0.2, columnspacing=0.8)
    ax.grid(axis="y", visible=False)
    base = ARTIGO / "figuras" / "fig_transferencia"
    for ext, kw in (("pdf", {}), ("png", {"dpi": 200})):
        fig.savefig(base.with_suffix(f".{ext}"), format=ext, **kw)
    plt.close(fig)


def _escrever(nome, ts, linhas, extra, projeto):
    p = RESULTS / f"{nome}_{ts}.csv"
    if p.exists():
        raise SystemExit(f"{p.name} já existe; não sobrescrevo")
    campos = list(linhas[0])
    with p.open("w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=campos)
        w.writeheader()
        w.writerows(linhas)
    meta = {"gerado_em": datetime.now().isoformat(timespec="seconds"),
            "post_review": True, "script": "analise_externo.py",
            "protocolo": "docs/ADENDO_REVISAO.md §8",
            "n_bootstrap": stats.N_BOOTSTRAP, "seed": stats.SEED,
            "projeto": projeto, **extra}
    p.with_name(p.stem + "_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def main():
    projeto = runner._commit()        # antes de qualquer saída
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    cob, fontes_cob = cobertura_ref()
    resumo, fontes_res = [], []
    for chave, rotulo, manifest, split, _ in BASES:
        ls, fs = resumo_base(chave, rotulo, manifest, split)
        resumo += ls
        fontes_res += fs
    trans, fontes_trans = transferencia()
    guit = por_guitarra()

    p1 = _escrever("externo_resumo", ts, resumo,
                   {"entradas": fontes_res + fontes_cob}, projeto)
    p2 = _escrever("transferencia", ts, trans,
                   {"entradas": list(fontes_trans.values())}, projeto)
    p3 = _escrever("transferencia_guitarra", ts, guit,
                   {"entradas": [_rel(p) for p in ablacoes("idmt_smt_guitar.csv",
                                                           "external")]}, projeto)
    tab_externo(resumo, cob, [p1.name])
    tab_transferencia(trans, {"csv": p2.name})
    fig_transferencia(trans)

    for l in resumo:
        print(f"{l['rotulo_base']:16s} {l['sistema']:9s} n={l['n_faixas']:3d} "
              + " ".join(f"{m}={_pct(l[m])}" for m in METRICAS))
    print()
    for a, b, ms, _ in stats.PARES:
        for m in ms:
            ls = [x for x in trans if x["par"] == f"{a} vs {b}" and x["metrica"] == m]
            print(f"{a+'→'+b:12s} {m:9s} " + " | ".join(
                f"{x['base']}: {100*x['delta']:+.1f} {x['classificacao'][:4]}"
                + (f" sinal={x['sinal_igual_gs_teste']}" if x['sinal_igual_gs_teste'] else "")
                for x in ls))
    print("\nsaídas:", p1.name, p2.name, p3.name)


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    main()
