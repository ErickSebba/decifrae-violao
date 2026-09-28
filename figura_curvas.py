"""
figura_curvas.py
================
Figura das curvas de acerto × cobertura, a partir do CSV de `curvas.py`.

Nenhum número é digitado aqui: tudo vem do CSV, agregado por média ponderada
pela duração da faixa -- a mesma ponderação que o mir_eval usa dentro de cada
faixa, aplicada agora entre faixas.

Formato: PDF vetorial, 3,5 pol de largura (uma coluna IEEE), fontes >= 8 pt,
dois painéis (root e majmin) compartilhando o eixo x.

    python figura_curvas.py                        # usa o CSV mais recente
    python figura_curvas.py --csv data/results/curvas_<ts>.csv
"""

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "data" / "results"
FIGURAS = ROOT / "out" / "figuras"

NIVEIS = ["root", "majmin"]
TITULOS = {"root": "root", "majmin": "majmin"}

# Larguras IEEE: 3,5 pol = uma coluna. Fonte mínima 8 pt (exigência da tarefa).
LARGURA_POL = 3.5
ALTURA_POL = 4.2
FONTE = 8

ESTILO = {
    "C":  dict(cor="#2a6f97", marcador="o", rotulo="C (argmax, gate)"),
    "D":  dict(cor="#e07a5f", marcador="s", rotulo="D (Viterbi, MEDIUM)"),
    "F":  dict(cor="#3d8361", marcador="^", rotulo="F (Viterbi, BASIC)"),
}
ESTILO_V4 = dict(cor="#6c584c", marcador="*", rotulo="V4 (não abstém)")


def _csv_mais_recente():
    candidatos = sorted(RESULTS.glob("curvas_*.csv"))
    if not candidatos:
        raise SystemExit("nenhum curvas_*.csv em data/results/ -- "
                         "rode `python curvas.py --manifest ...` primeiro")
    return candidatos[-1]


def _media_ponderada(linhas, coluna):
    pares = [(float(l[coluna]), float(l["duracao_s"])) for l in linhas
             if l[coluna] not in ("", None)]
    peso = sum(d for _, d in pares)
    return sum(v * d for v, d in pares) / peso if peso else float("nan")


def agregar(csv_path):
    """CSV por faixa -> {curva: [(cobertura, {nivel: acerto}, valor), ...]}."""
    with Path(csv_path).open(encoding="utf-8", newline="") as fp:
        linhas = list(csv.DictReader(fp))

    por_ponto = defaultdict(list)
    for l in linhas:
        por_ponto[(l["curva"], l["valor"])].append(l)

    curvas = defaultdict(list)
    for (curva, valor), grupo in por_ponto.items():
        ponto = {
            "valor": valor,
            "cobertura": _media_ponderada(grupo, "cobertura"),
            "rotulado": {n: _media_ponderada(grupo, f"acerto_rotulado_{n}")
                         for n in NIVEIS},
        }
        curvas[curva].append(ponto)
    for curva in curvas:
        curvas[curva].sort(key=lambda p: p["cobertura"])
    return curvas


def desenhar(curvas, destino):
    plt.rcParams.update({
        "font.size": FONTE,
        "axes.labelsize": FONTE,
        "axes.titlesize": FONTE,
        "xtick.labelsize": FONTE - 1,
        "ytick.labelsize": FONTE - 1,
        "legend.fontsize": FONTE - 1,
        "pdf.fonttype": 42,        # TrueType: texto selecionável/embutido
        "ps.fonttype": 42,
        "axes.grid": True,
        "grid.alpha": 0.3,
        "grid.linewidth": 0.4,
    })

    fig, axs = plt.subplots(len(NIVEIS), 1, figsize=(LARGURA_POL, ALTURA_POL),
                            sharex=True)
    for ax, nivel in zip(axs, NIVEIS):
        for curva in ("C", "D", "F"):
            pontos = curvas.get(curva)
            if not pontos:
                continue
            est = ESTILO[curva]
            ax.plot([p["cobertura"] * 100 for p in pontos],
                    [p["rotulado"][nivel] * 100 for p in pontos],
                    marker=est["marcador"], color=est["cor"],
                    markersize=3, linewidth=1.0, label=est["rotulo"])
        v4 = curvas.get("V4")
        if v4:
            ax.plot([v4[0]["cobertura"] * 100], [v4[0]["rotulado"][nivel] * 100],
                    marker=ESTILO_V4["marcador"], color=ESTILO_V4["cor"],
                    markersize=8, linestyle="none", label=ESTILO_V4["rotulo"])
        ax.set_ylabel(f"acerto em {TITULOS[nivel]} (%)")
        ax.set_title(f"({'ab'[NIVEIS.index(nivel)]}) {TITULOS[nivel]}",
                     loc="left", fontsize=FONTE)

    axs[-1].set_xlabel("cobertura: fração do tempo rotulada (%)")
    axs[0].legend(loc="lower left", frameon=False, handlelength=1.6,
                  borderaxespad=0.2)
    fig.tight_layout(pad=0.4)

    FIGURAS.mkdir(parents=True, exist_ok=True)
    fig.savefig(destino, format="pdf", bbox_inches="tight")
    plt.close(fig)
    return destino


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Figura acerto x cobertura a partir do CSV de curvas.")
    ap.add_argument("--csv", default=None,
                    help="default: o curvas_*.csv mais recente")
    ap.add_argument("--out", default=None,
                    help="default: out/figuras/curvas_<mesmo timestamp>.pdf")
    args = ap.parse_args(argv)

    csv_path = Path(args.csv) if args.csv else _csv_mais_recente()
    curvas = agregar(csv_path)

    sufixo = csv_path.stem.replace("curvas_", "")
    destino = Path(args.out) if args.out else FIGURAS / f"curvas_{sufixo}.pdf"
    desenhar(curvas, destino)

    print(f"lido    {csv_path.relative_to(ROOT).as_posix()}")
    for curva, pontos in sorted(curvas.items()):
        cob = [p["cobertura"] * 100 for p in pontos]
        print(f"  {curva:<3} {len(pontos):>2} ponto(s), "
              f"cobertura {min(cob):.1f}%–{max(cob):.1f}%")
    print(f"escrito {destino.relative_to(ROOT).as_posix()} "
          f"({LARGURA_POL}x{ALTURA_POL} pol, fonte {FONTE} pt)")


if __name__ == "__main__":
    main()
