"""
figuras_artigo.py
=================
Gera as figuras e as tabelas LaTeX de `artigo-ACDSA/` a partir dos CSV de
`data/results/`. **Nenhum número é digitado aqui**: tudo é lido do CSV e
agregado por média ponderada pela duração da faixa -- a mesma ponderação que o
mir_eval usa dentro de cada faixa, aplicada agora entre faixas.

Quais CSV entram é decidido pelo `*_meta.json` ao lado de cada um (split,
camada de referência, variantes), nunca pelo nome do arquivo.

Saídas (todas sobrescritas a cada execução):

    artigo-ACDSA/figuras/fig_cobertura_acerto.pdf   + .png
    artigo-ACDSA/figuras/fig_acuracia_segmentacao.pdf + .png
    artigo-ACDSA/tabelas/tab_ablacao.tex
    artigo-ACDSA/tabelas/tab_camadas.tex
    artigo-ACDSA/tabelas/tab_segmentacao.tex
    artigo-ACDSA/tabelas/tab_stats.tex

Formato das figuras: PDF vetorial (sem raster embutido), 3,5 pol de largura
(uma coluna IEEE), fontes >= 8 pt, `pdf.fonttype = 42`; PNG a 200 dpi da mesma
figura. Números com duas casas decimais e vírgula decimal.

    python figuras_artigo.py
    python figuras_artigo.py --so-tabelas
"""

from __future__ import annotations

import argparse
import csv
import json
import textwrap
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "data" / "results"
ARTIGO = ROOT / "artigo-ACDSA"
FIGURAS = ARTIGO / "figuras"
TABELAS = ARTIGO / "tabelas"

NIVEIS = ["root", "majmin", "sevenths", "mirex"]
NIVEIS_CURVA = ["root", "majmin"]

# Larguras IEEE: 3,5 pol = uma coluna. Fonte mínima 8 pt (exigência da tarefa).
LARGURA_POL = 3.5
FONTE = 8
DPI_PNG = 200

# Curvas da validação: C varre o confidence_gate, D e F varrem o n_logprob.
ESTILO_CURVA = {
    "C": dict(cor="#2a6f97", marcador="o", rotulo="C (argmax, confidence_gate)"),
    "D": dict(cor="#e07a5f", marcador="s", rotulo="D (Viterbi MEDIUM, n_logprob)"),
    "F": dict(cor="#3d8361", marcador="^", rotulo="F (Viterbi BASIC, n_logprob)"),
}
# Pontos das variantes congeladas medidas no teste: marcadores distintos das
# curvas (preenchimento branco e borda grossa) para não se confundirem com elas.
ESTILO_PONTO = {
    "V4":   dict(cor="#6c584c", marcador="*"),
    "C":    dict(cor="#2a6f97", marcador="P"),
    "D":    dict(cor="#e07a5f", marcador="X"),
    "E":    dict(cor="#b5179e", marcador="D"),
    "F0rg": dict(cor="#3d8361", marcador="v"),
    "D0rg": dict(cor="#8d6a9f", marcador="h"),
}
CLASSIF = {"confirmado": "confirmado", "empate": "empate", "fragil": "frágil"}


# --------------------------------------------------------------------------- #
# leitura e seleção dos CSV pelo meta.json
# --------------------------------------------------------------------------- #

def _meta(csv_path: Path) -> dict:
    p = csv_path.with_name(csv_path.stem + "_meta.json")
    if not p.exists():
        raise SystemExit(f"sem meta.json ao lado de {csv_path.name}")
    return json.loads(p.read_text(encoding="utf-8"))


def _linhas(csv_path: Path) -> list[dict]:
    with csv_path.open(encoding="utf-8", newline="") as fp:
        return list(csv.DictReader(fp))


def _escolher(padrao: str, aceita) -> tuple[Path, dict]:
    """O CSV mais recente (nome com timestamp) cujo meta satisfaz `aceita`."""
    achados = []
    for p in sorted(RESULTS.glob(padrao)):
        m = _meta(p)
        if aceita(m):
            achados.append((p, m))
    if not achados:
        raise SystemExit(f"nenhum {padrao} com meta compatível em {RESULTS}")
    return achados[-1]


def _splits(m: dict) -> list[str]:
    return m.get("splits") or ([m["split"]] if m.get("split") else [])


def selecionar() -> dict:
    fontes = {}
    fontes["curvas_val"] = _escolher(
        "curvas_*.csv", lambda m: "val" in _splits(m))
    for cam, suf in (("chord[0]", "ref0"), ("chord[1]", "ref1")):
        fontes[f"abl_test_{suf}"] = _escolher(
            "ablation_*.csv",
            lambda m, c=cam: _splits(m) == ["test"] and m.get("ref_camada") == c)
        fontes[f"abl_val_{suf}"] = _escolher(
            "ablation_*.csv",
            lambda m, c=cam: _splits(m) == ["val"] and m.get("ref_camada") == c
            and len(m.get("variantes", [])) >= 16)
    # Estatística: prefere o teste se existir, na mesma camada de referência
    # das outras tabelas (chord[0]); a validação entra como tabela extra,
    # porque só ela tem as 15 comparações (C0rg e V4b não foram ao teste).
    fontes["stats_val"] = _escolher(
        "stats_*.csv",
        lambda m: _splits(m) == ["val"] and m.get("ref_camada") == "chord[0]")
    try:
        fontes["stats"] = _escolher(
            "stats_*.csv",
            lambda m: _splits(m) == ["test"] and m.get("ref_camada") == "chord[0]")
    except SystemExit:
        fontes["stats"] = fontes["stats_val"]
    return fontes


# --------------------------------------------------------------------------- #
# agregação
# --------------------------------------------------------------------------- #

def wmean(linhas, coluna) -> float:
    pares = [(float(l[coluna]), float(l["duracao_s"])) for l in linhas
             if l.get(coluna) not in ("", None)]
    peso = sum(d for _, d in pares)
    return sum(v * d for v, d in pares) / peso if peso else float("nan")


def mean(linhas, coluna) -> float:
    vals = [float(l[coluna]) for l in linhas if l.get(coluna) not in ("", None)]
    return sum(vals) / len(vals) if vals else float("nan")


def por_variante(linhas) -> dict[str, list[dict]]:
    g = defaultdict(list)
    for l in linhas:
        g[l["variante"]].append(l)
    return g


def curvas_agregadas(csv_path: Path) -> dict[str, list[dict]]:
    """CSV por faixa -> {curva: [{valor, cobertura, rotulado{nivel}}, ...]}."""
    por_ponto = defaultdict(list)
    for l in _linhas(csv_path):
        por_ponto[(l["curva"], l["valor"])].append(l)
    curvas = defaultdict(list)
    for (curva, valor), grupo in por_ponto.items():
        curvas[curva].append({
            "valor": valor,
            "cobertura": wmean(grupo, "cobertura"),
            "rotulado": {n: wmean(grupo, f"acerto_rotulado_{n}")
                         for n in NIVEIS_CURVA},
        })
    for curva in curvas:
        curvas[curva].sort(key=lambda p: p["cobertura"])
    return dict(curvas)


# --------------------------------------------------------------------------- #
# formatação de números: duas casas, vírgula decimal
# --------------------------------------------------------------------------- #

def num(v: float, casas: int = 2) -> str:
    if v != v:  # NaN
        return "--"
    return f"{v:.{casas}f}".replace(".", ",")


def pct(v: float, casas: int = 2) -> str:
    return num(v * 100.0, casas)


def sinal(v: float, casas: int = 2) -> str:
    return f"{v * 100.0:+.{casas}f}".replace(".", ",").replace("-", "$-$")


_virgula = FuncFormatter(lambda v, pos: f"{v:g}".replace(".", ","))


def tex_escape(s: str) -> str:
    for a, b in (("\\", r"\textbackslash{}"), ("%", r"\%"), ("_", r"\_"),
                 ("&", r"\&"), ("#", r"\#"), ("$", r"\$")):
        s = s.replace(a, b)
    return s


# --------------------------------------------------------------------------- #
# estilo comum das figuras
# --------------------------------------------------------------------------- #

def _rc():
    plt.rcParams.update({
        "font.size": FONTE,
        "axes.labelsize": FONTE,
        "axes.titlesize": FONTE,
        "xtick.labelsize": FONTE,
        "ytick.labelsize": FONTE,
        "legend.fontsize": FONTE,
        "legend.title_fontsize": FONTE,
        "pdf.fonttype": 42,     # TrueType embutida: texto selecionável
        "ps.fonttype": 42,
        "svg.fonttype": "none",
        "axes.grid": True,
        "grid.alpha": 0.3,
        "grid.linewidth": 0.4,
        "figure.dpi": 100,
    })


def _salvar(fig, base: Path) -> list[Path]:
    base.parent.mkdir(parents=True, exist_ok=True)
    pdf, png = base.with_suffix(".pdf"), base.with_suffix(".png")
    fig.savefig(pdf, format="pdf", bbox_inches="tight")
    fig.savefig(png, format="png", dpi=DPI_PNG, bbox_inches="tight")
    plt.close(fig)
    return [pdf, png]


def checar_vetorial(pdf: Path) -> tuple[bool, list[str]]:
    dados = pdf.read_bytes()
    marcas = [m for m in (b"/Subtype /Image", b"/Subtype/Image", b"/DCTDecode",
                          b"/JPXDecode") if m in dados]
    return (not marcas), [m.decode() for m in marcas]


# --------------------------------------------------------------------------- #
# A) figura cobertura x acerto no tempo rotulado
# --------------------------------------------------------------------------- #

def fig_cobertura_acerto(fontes) -> tuple[list[Path], dict]:
    curvas = curvas_agregadas(fontes["curvas_val"][0])
    linhas_teste = _linhas(fontes["abl_test_ref0"][0])
    ordem = fontes["abl_test_ref0"][1]["variantes"]
    g = por_variante(linhas_teste)

    pontos = {}
    for v in ordem:
        rs = g[v]
        pontos[v] = {
            "cobertura": 1.0 - wmean(rs, "frac_n_est"),
            "rotulado": {n: wmean(rs, f"{n}_rotulado") for n in NIVEIS_CURVA},
        }

    # A cobertura máxima ALCANÇADA PELAS CURVAS da validação. Note que as
    # curvas mantêm rel_gate = 0,2: é esse gate, e não o piso absoluto de RMS,
    # que impede as curvas de chegarem a 100 %. As variantes `rg` (rel_gate=0),
    # que não estão nas curvas, chegam a 100,00 % exatos na validação.
    cob_max = max(p["cobertura"] for c in ("C", "D", "F")
                  for p in curvas.get(c, []))
    cob_v4 = pontos["V4"]["cobertura"]
    rel_gate = _meta(fontes["abl_val_ref0"][0])["config_base"]["post"]["rel_gate"]

    _rc()
    fig, axs = plt.subplots(2, 1, figsize=(LARGURA_POL, 4.4), sharex=True)
    for ax, nivel in zip(axs, NIVEIS_CURVA):
        for c in ("C", "D", "F"):
            ps = curvas.get(c)
            if not ps:
                continue
            e = ESTILO_CURVA[c]
            ax.plot([p["cobertura"] * 100 for p in ps],
                    [p["rotulado"][nivel] * 100 for p in ps],
                    marker=e["marcador"], color=e["cor"], markersize=3,
                    linewidth=1.0, label=e["rotulo"], zorder=2)
        for v in ordem:
            e = ESTILO_PONTO[v]
            ax.plot([pontos[v]["cobertura"] * 100],
                    [pontos[v]["rotulado"][nivel] * 100],
                    marker=e["marcador"], color=e["cor"], markersize=7,
                    markerfacecolor="white", markeredgewidth=1.4,
                    linestyle="none", label=v, zorder=3)
        ax.axvline(cob_max * 100, color="0.45", linewidth=0.7, linestyle=":",
                   zorder=1)
        ax.set_ylabel(f"acerto rotulado em {nivel} (%)")
        ax.xaxis.set_major_formatter(_virgula)
        ax.yaxis.set_major_formatter(_virgula)
        ax.set_title(f"({'ab'[NIVEIS_CURVA.index(nivel)]}) {nivel}",
                     loc="left", fontsize=FONTE)
    axs[-1].set_xlabel("cobertura: fração do tempo rotulada (%)")

    # Duas legendas separadas: as curvas (validação) e os pontos (teste).
    h_curva = [Line2D([], [], color=ESTILO_CURVA[c]["cor"],
                      marker=ESTILO_CURVA[c]["marcador"], markersize=3,
                      linewidth=1.0, label=ESTILO_CURVA[c]["rotulo"])
               for c in ("C", "D", "F") if c in curvas]
    h_ponto = [Line2D([], [], color=ESTILO_PONTO[v]["cor"],
                      marker=ESTILO_PONTO[v]["marcador"], markersize=7,
                      markerfacecolor="white", markeredgewidth=1.4,
                      linestyle="none", label=v) for v in ordem]
    fig.tight_layout(pad=0.4)

    leg1 = fig.legend(handles=h_curva, loc="upper center",
                      bbox_to_anchor=(0.5, -0.01), ncol=1, frameon=False,
                      handlelength=1.8, borderaxespad=0.0,
                      title="curvas: varredura na validação")
    leg1._legend_box.align = "left"
    leg2 = fig.legend(handles=h_ponto, loc="upper center",
                      bbox_to_anchor=(0.5, -0.175), ncol=3, frameon=False,
                      handlelength=1.2, columnspacing=1.2, borderaxespad=0.0,
                      title="pontos: variantes congeladas, medidas no teste")
    leg2._legend_box.align = "left"

    nota = (f"As curvas param em {pct(cob_max)} % de cobertura (linha "
            f"pontilhada), não em 100 %: mesmo com o gate de confiança e o "
            f"estado N do Viterbi desligados, o gate RELATIVO de silêncio "
            f"(rel_gate = {num(rel_gate, 1)}) força N em {pct(1 - cob_max)} % "
            f"do tempo. As variantes rg, que zeram esse gate, e o V4, que não "
            f"abstém, chegam a {pct(cob_v4)} %.")
    fig.text(0.5, -0.30, textwrap.fill(nota, 62), ha="center", va="top",
             fontsize=FONTE, transform=fig.transFigure)

    saidas = _salvar(fig, FIGURAS / "fig_cobertura_acerto")
    return saidas, {"cob_max": cob_max, "cob_v4": cob_v4,
                    "rel_gate": rel_gate, "nota": nota}


# --------------------------------------------------------------------------- #
# B) figura acurácia x segmentação
# --------------------------------------------------------------------------- #

def fig_acuracia_segmentacao(fontes) -> tuple[list[Path], dict]:
    ordem = fontes["abl_test_ref0"][1]["variantes"]
    g0 = por_variante(_linhas(fontes["abl_test_ref0"][0]))
    g1 = por_variante(_linhas(fontes["abl_test_ref1"][0]))

    # root e seg não dependem da camada de referência (chord[1] muda só a
    # qualidade do acorde, não a tônica nem as fronteiras). Checado aqui para
    # que a escolha de painéis seja um fato do CSV, não uma suposição.
    iguais = all(
        abs(wmean(g0[v], c) - wmean(g1[v], c)) < 1e-9
        for v in ordem for c in ("root", "seg"))

    _rc()
    fig, axs = plt.subplots(2, 1, figsize=(LARGURA_POL, 5.2))
    paineis = [("root", axs[0], False), ("majmin", axs[1], True)]
    for nivel, ax, duas_camadas in paineis:
        for v in ordem:
            e = ESTILO_PONTO[v]
            x0, y0 = wmean(g0[v], "seg") * 100, wmean(g0[v], nivel) * 100
            ax.plot([x0], [y0], marker=e["marcador"], color=e["cor"],
                    markersize=7, linestyle="none", zorder=3)
            ax.annotate(v, (x0, y0), textcoords="offset points",
                        xytext=(5, 3), fontsize=FONTE, color=e["cor"])
            if duas_camadas:
                x1, y1 = wmean(g1[v], "seg") * 100, wmean(g1[v], nivel) * 100
                ax.plot([x1], [y1], marker=e["marcador"], color=e["cor"],
                        markersize=7, markerfacecolor="white",
                        markeredgewidth=1.4, linestyle="none", zorder=3)
                ax.plot([x0, x1], [y0, y1], color=e["cor"], linewidth=0.7,
                        alpha=0.6, zorder=2)
        ax.set_xlabel("seg: qualidade da segmentação (%)")
        ax.set_ylabel(f"acerto em {nivel} (%)")
        ax.margins(x=0.14, y=0.16)
        ax.xaxis.set_major_formatter(_virgula)
        ax.yaxis.set_major_formatter(_virgula)
    axs[0].set_title("(a) root — idêntico nas duas camadas", loc="left",
                     fontsize=FONTE)
    axs[1].set_title("(b) majmin — chord[0] cheio, chord[1] vazado", loc="left",
                     fontsize=FONTE)
    axs[1].legend(handles=[
        Line2D([], [], color="0.3", marker="o", linestyle="none",
               markersize=6, label="chord[0]"),
        Line2D([], [], color="0.3", marker="o", linestyle="none", markersize=6,
               markerfacecolor="white", markeredgewidth=1.4, label="chord[1]"),
    ], loc="best", frameon=False, handlelength=1.2, fontsize=FONTE)
    fig.tight_layout(pad=0.4)

    saidas = _salvar(fig, FIGURAS / "fig_acuracia_segmentacao")
    return saidas, {"root_seg_invariantes": iguais}


# --------------------------------------------------------------------------- #
# tabelas LaTeX
# --------------------------------------------------------------------------- #

def _tabela(env, colunas, corpo, caption, label, notas=(), pequena=True):
    linhas = [f"% gerado por figuras_artigo.py -- não editar à mão",
              f"\\begin{{{env}}}[t]",
              "  \\centering",
              f"  \\caption{{{caption}}}",
              f"  \\label{{{label}}}"]
    if pequena:
        linhas.append("  \\footnotesize")
    linhas += [f"  \\begin{{tabular}}{{{colunas}}}", "    \\toprule"]
    linhas += [f"    {l}" for l in corpo]
    linhas += ["    \\bottomrule", "  \\end{tabular}"]
    for n in notas:
        linhas.append("  \\vspace{2pt}")
        linhas.append(f"  \\parbox{{\\linewidth}}{{\\footnotesize {n}}}")
    linhas.append(f"\\end{{{env}}}")
    return "\n".join(linhas) + "\n"


def tab_ablacao(fontes) -> Path:
    csv_path, meta = fontes["abl_test_ref0"]
    ordem = meta["variantes"]
    g = por_variante(_linhas(csv_path))
    corpo = ["Variante & root & majmin & sevenths & mirex & N est. & Cobertura \\\\",
             "\\midrule"]
    for v in ordem:
        rs = g[v]
        fn = wmean(rs, "frac_n_est")
        corpo.append(" & ".join([
            f"\\texttt{{{tex_escape(v)}}}",
            *[pct(wmean(rs, n)) for n in NIVEIS],
            pct(fn), pct(1 - fn)]) + " \\\\")
    cap = ("Ablação no split \\emph{test}: as seis configurações congeladas, "
           "camada de referência \\texttt{chord[0]}. Todos os valores em \\%, "
           "média ponderada pela duração da faixa "
           f"($n = {len(g[ordem[0]])}$ faixas). \\emph{{N est.}} é a fração do "
           "tempo em que o sistema estimou N (abstenção); \\emph{Cobertura} é "
           "o complemento. Fonte: \\texttt{" + tex_escape(csv_path.name) + "}.")
    tex = _tabela("table", "l" + "r" * 6, corpo, cap, "tab:ablacao")
    destino = TABELAS / "tab_ablacao.tex"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(tex, encoding="utf-8")
    return destino


def tab_camadas(fontes) -> Path:
    p0, meta = fontes["abl_test_ref0"]
    p1, _ = fontes["abl_test_ref1"]
    ordem = meta["variantes"]
    g0, g1 = por_variante(_linhas(p0)), por_variante(_linhas(p1))
    grupos = " & ".join(f"\\multicolumn{{2}}{{c}}{{{n}}}" for n in NIVEIS)
    cmid = " ".join(f"\\cmidrule(lr){{{2 + 2 * i}-{3 + 2 * i}}}"
                    for i in range(len(NIVEIS)))
    corpo = [f"Variante & {grupos} \\\\",
             cmid,
             " & " + " & ".join(["[0] & [1]"] * len(NIVEIS)) + " \\\\",
             "\\midrule"]
    for v in ordem:
        celulas = []
        for n in NIVEIS:
            celulas += [pct(wmean(g0[v], n)), pct(wmean(g1[v], n))]
        corpo.append(f"\\texttt{{{tex_escape(v)}}} & " + " & ".join(celulas) + " \\\\")
    cap = ("Efeito da camada de referência no split \\emph{test}: "
           "\\texttt{chord[0]} (colunas [0]) contra \\texttt{chord[1]} "
           "(colunas [1]), nos quatro níveis de vocabulário. Valores em \\%, "
           "média ponderada pela duração. \\texttt{root} é idêntico nas duas "
           "camadas por construção: \\texttt{chord[1]} altera a qualidade do "
           "acorde, não a tônica. Fontes: \\texttt{"
           + tex_escape(p0.name) + "} e \\texttt{" + tex_escape(p1.name) + "}.")
    # `table*`: nove colunas não cabem nas 3,5 pol de uma coluna IEEE.
    tex = _tabela("table*", "l" + "rr" * len(NIVEIS), corpo, cap, "tab:camadas")
    destino = TABELAS / "tab_camadas.tex"
    destino.write_text(tex, encoding="utf-8")
    return destino


def tab_segmentacao(fontes) -> Path:
    csv_path, meta = fontes["abl_test_ref0"]
    ordem = meta["variantes"]
    g = por_variante(_linhas(csv_path))
    corpo = ["Variante & overseg & underseg & seg & Segm. est. & Segm. ref. \\\\",
             "\\midrule"]
    for v in ordem:
        rs = g[v]
        corpo.append(" & ".join([
            f"\\texttt{{{tex_escape(v)}}}",
            pct(wmean(rs, "overseg")), pct(wmean(rs, "underseg")),
            pct(wmean(rs, "seg")),
            num(mean(rs, "n_segmentos_est"), 1),
            num(mean(rs, "n_segmentos_ref"), 1)]) + " \\\\")
    cap = ("Segmentação no split \\emph{test}, camada \\texttt{chord[0]}. "
           "\\emph{overseg}, \\emph{underseg} e \\emph{seg} em \\% "
           "(média ponderada pela duração; \\emph{seg} é o mínimo dos dois "
           "primeiros). \\emph{Segm. est.} e \\emph{Segm. ref.} são o número "
           "médio de segmentos por faixa, estimado e de referência "
           "(média simples). Fonte: \\texttt{"
           + tex_escape(csv_path.name) + "}.")
    tex = _tabela("table", "l" + "r" * 5, corpo, cap, "tab:segmentacao")
    destino = TABELAS / "tab_segmentacao.tex"
    destino.write_text(tex, encoding="utf-8")
    return destino


def tab_stats(fontes, chave="stats", nome="tab_stats.tex",
              label="tab:stats") -> Path:
    csv_path, meta = fontes[chave]
    linhas = _linhas(csv_path)
    corpo = ["Comparação & Métrica & $\\Delta$ (p.p.) & IC 95 \\% (p.p.) & "
             "$p$ bruto & $p$ Holm & Classificação \\\\", "\\midrule"]
    for l in linhas:
        d = float(l["diferenca"])
        corpo.append(" & ".join([
            f"\\texttt{{{tex_escape(l['variante_a'])}}} vs. "
            f"\\texttt{{{tex_escape(l['variante_b'])}}}",
            f"\\texttt{{{tex_escape(l['metrica'])}}}",
            sinal(d),
            f"[{sinal(float(l['ic95_min']))}; {sinal(float(l['ic95_max']))}]",
            num(float(l["p_bootstrap"]), 4),
            num(float(l["p_bootstrap_holm"]), 4),
            CLASSIF.get(l["classificacao"], l["classificacao"]),
        ]) + " \\\\")
    split = (_splits(meta) or ["?"])[0]
    # Variantes que os pares do meta pedem mas que não existem no CSV de
    # entrada: é o que explica haver menos comparações do que pares previstos.
    pedidas = {v for par in meta.get("pares", []) for v in (par["a"], par["b"])}
    presentes = {l[c] for l in linhas for c in ("variante_a", "variante_b")}
    ausentes = sorted(pedidas - presentes)
    previstas = sum(len(par["metricas"]) for par in meta.get("pares", []))
    nota = ("$\\Delta$ = média de B menos média de A, em pontos percentuais, "
            "média ponderada pela duração; IC 95 \\% do bootstrap pareado por "
            f"faixa ($n = {meta.get('n_bootstrap', '?')}$ reamostragens, "
            f"semente {meta.get('seed', '?')}). O $p$ do bootstrap tem piso "
            f"$1/{meta.get('n_bootstrap', '?')}$ "
            f"({num(1 / meta['n_bootstrap'], 4) if meta.get('n_bootstrap') else '?'})"
            ": os valores nesse piso são o mínimo mensurável, não zero. "
            "$p$ Holm: Holm--Bonferroni sobre as "
            f"{meta.get('n_comparacoes', len(linhas))} comparações. "
            "\\emph{confirmado} = IC exclui zero e Holm rejeita; "
            "\\emph{frágil} = IC exclui zero mas Holm não rejeita; "
            "\\emph{empate} = IC cruza zero.")
    if ausentes:
        nota += (" Das " + str(previstas) + " comparações previstas, "
                 + str(len(linhas)) + " puderam ser feitas neste split: as "
                 "demais envolvem \\texttt{"
                 + "}, \\texttt{".join(tex_escape(a) for a in ausentes)
                 + "}, que não " + ("foram" if len(ausentes) > 1 else "foi")
                 + f" ao split \\emph{{{split}}}.")
    cap = (f"Comparações pareadas no split \\emph{{{split}}}, camada "
           f"\\texttt{{{meta.get('ref_camada', '?')}}}. Fonte: \\texttt{{"
           + tex_escape(csv_path.name) + "}.")
    tex = _tabela("table*", "llrrrrl", corpo, cap, label, notas=[nota])
    destino = TABELAS / nome
    destino.write_text(tex, encoding="utf-8")
    return destino


# --------------------------------------------------------------------------- #

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Figuras e tabelas LaTeX de artigo-ACDSA/, a partir dos "
                    "CSV de data/results/.")
    ap.add_argument("--so-tabelas", action="store_true",
                    help="não redesenha as figuras")
    ap.add_argument("--so-figuras", action="store_true",
                    help="não regera as tabelas")
    args = ap.parse_args(argv)

    fontes = selecionar()
    print("fontes escolhidas pelo meta.json:")
    for chave, (p, m) in fontes.items():
        print(f"  {chave:<14} {p.name:<40} split={_splits(m)} "
              f"camada={m.get('ref_camada', '-')} "
              f"variantes={len(m.get('variantes', [])) or '-'}")

    saidas = []
    if not args.so_tabelas:
        for func in (fig_cobertura_acerto, fig_acuracia_segmentacao):
            arqs, extra = func(fontes)
            saidas += arqs
            print(f"\n{func.__name__}: {extra}")
    if not args.so_figuras:
        for func in (tab_ablacao, tab_camadas, tab_segmentacao, tab_stats):
            saidas.append(func(fontes))
        if fontes["stats"][0] != fontes["stats_val"][0]:
            # A tabela do teste não tem as 15 comparações (C0rg e V4b não
            # foram ao teste); a da validação tem, e vai como tabela extra.
            saidas.append(tab_stats(fontes, chave="stats_val",
                                    nome="tab_stats_val.tex",
                                    label="tab:stats-val"))

    print("\narquivos escritos:")
    for p in saidas:
        print(f"  {p.relative_to(ROOT).as_posix():<52} {p.stat().st_size:>8} B")

    print("\nchecagem de raster nos PDF:")
    for p in saidas:
        if p.suffix == ".pdf":
            ok, marcas = checar_vetorial(p)
            estado = "vetorial (sem /Subtype /Image, sem /DCTDecode)" \
                if ok else f"RASTER ENCONTRADO: {marcas}"
            print(f"  {p.name:<34} {estado}")


if __name__ == "__main__":
    main()
