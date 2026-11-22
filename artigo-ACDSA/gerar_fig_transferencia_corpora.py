"""
gerar_fig_transferencia_corpora.py
==================================
Figura fig_transferencia_corpora: os seis contrastes principais
(PRINCIPAIS em beat_tracking_idmt.py) no GuitarSet teste e no
IDMT-SMT-Guitar, com Δ = b − a em p.p. e IC 95 % (bootstrap pareado).

Fonte única: data/results/transferencia_20261117_122651.csv (a mesma da
tab_transferencia_curta.tex). Nenhum experimento novo: só leitura.

IDMT-SMT-Chords (6 faixas) fica FORA da escala: os Δ de −67,9 e −30,9 p.p.
achatariam o eixo. Opção padrão "b": não desenhado, citado no texto/tabela.
A opção "a" (triângulo na borda esquerda com o valor escrito) fica
disponível para comparação via --opcao a.

Uso (de dentro de artigo-ACDSA/ ou da raiz):
    python artigo-ACDSA/gerar_fig_transferencia_corpora.py [--opcao a|b]
                                                          [--destino DIR]
"""

import argparse
import csv
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import estilo_figuras as ef  # noqa: E402

RAIZ = AQUI.parent
CSV_ORIGEM = "data/results/transferencia_20261117_122651.csv"

# (a, b, métrica, rótulo curto) — ordem de cima para baixo
CONTRASTES = [
    ("C", "D", "root", "C→D root"),
    ("C0rg", "D0rg", "majmin", "C0rg→D0rg majmin"),
    ("D", "E", "overseg", "D→E overseg"),
    ("V4b", "V4", "overseg", "V4b→V4 overseg"),
    ("V4", "F0rg", "majmin", "V4→F0rg majmin"),
    ("D0rg", "F0rg", "sevenths", "D0rg→F0rg 7ths"),
]
# (base no CSV, nome no CSV de dados, legenda, marcador, deslocamento em y)
CORPORA = [
    ("gs_test", "GuitarSet_test", "GuitarSet (test)", "o", -0.15),
    ("idmt_g", "IDMT-SMT-Guitar", "IDMT-SMT-Guitar", "s", +0.15),
]
FORA = ("idmt_c", "IDMT-SMT-Chords")


def ler():
    with open(RAIZ / CSV_ORIGEM, encoding="utf-8") as fp:
        return {(r["par"], r["metrica"], r["base"]): r
                for r in csv.DictReader(fp)}


def linha(rot, m, corpus, r, desenho, fora_da_escala):
    return {"contraste": rot, "metrica": m, "corpus": corpus,
            "delta_pp": round(100 * float(r["delta"]), 4),
            "ic95_min_pp": round(100 * float(r["ic95_min"]), 4),
            "ic95_max_pp": round(100 * float(r["ic95_max"]), 4),
            "classificacao": r["classificacao"],
            "sinal_igual_gs_teste": r["sinal_igual_gs_teste"],
            "desenho": desenho, "fora_da_escala": fora_da_escala,
            "csv_origem": CSV_ORIGEM}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--opcao", choices=("a", "b"), default="b")
    ap.add_argument("--destino", default=str(ef.FIGURAS))
    args = ap.parse_args()

    dados = ler()
    n = len(CONTRASTES)
    fig, ax = ef.figura(altura=2.2)
    linhas = []

    if args.opcao == "a":
        # com a 3ª linha por contraste, os dois corpora sobem um pouco
        desloc = {"gs_test": -0.22, "idmt_g": 0.0}
    else:
        desloc = {c[0]: c[4] for c in CORPORA}

    for i, (a, b, m, rot) in enumerate(CONTRASTES):
        y0 = n - 1 - i
        par = f"{a} vs {b}"
        for base, nome, leg, marc, _ in CORPORA:
            r = dados[(par, m, base)]
            x = 100 * float(r["delta"])
            ef.ponto_ic(ax, x, y0 - desloc[base], 100 * float(r["ic95_min"]),
                        100 * float(r["ic95_max"]), marcador=marc,
                        preenchido=(marc == "o"), horizontal=True,
                        rotulo=leg if i == 0 else None)
            linhas.append(linha(rot, m, nome, r, "ponto", "nao"))
        if args.opcao == "a":
            r = dados[(par, m, FORA[0])]
            linhas.append(linha(rot, m, FORA[1], r, "anotacao_borda", "sim"))

    ef.linha_zero(ax, "v")
    ax.set_yticks(range(n))
    ax.set_yticklabels([c[3] for c in CONTRASTES][::-1])
    ax.set_ylim(-0.6, n - 0.4)
    ax.set_xlabel("Δ (pp)")
    xmin = -4 if args.opcao == "a" else -2
    ax.set_xlim(xmin, 22)
    ax.tick_params(axis="y", length=0)

    if args.opcao == "a":
        for i, (a, b, m, rot) in enumerate(CONTRASTES):
            y = n - 1 - i - 0.24
            r = dados[(f"{a} vs {b}", m, FORA[0])]
            ax.plot([xmin], [y], marker="<", color=ef.ESCURO,
                    markersize=ef.MARCADOR, linestyle="none", clip_on=False,
                    label="IDMT-SMT-Chords (off scale)" if i == 0 else None)
            ef.anotar(ax, f"{100 * float(r['delta']):+.1f}", (xmin, y),
                      xytext=(4, 0), textcoords="offset points",
                      va="center", ha="left")

    ax.legend(loc="upper right", handletextpad=0.3, borderaxespad=0.2,
              labelspacing=0.3, numpoints=1)

    saidas = ef.salvar(fig, "fig_transferencia_corpora", linhas,
                       destino=args.destino)
    for p in saidas:
        print(p)


if __name__ == "__main__":
    main()
