"""
gerar_fig_executantes.py
========================
Figura fig_executantes (camera-ready): Δ por executante do GuitarSet com
IC 95 % (bootstrap pareado dentro do executante), camada chord[0], para três
contrastes: C→D root, D→E overseg, D0rg→F0rg sevenths.

Fonte: data/results/por_executante_20261117_004132.csv (a mesma citada em
tabelas/tab_executantes.tex). Só lê o CSV; nenhum experimento novo.

Saídas (via estilo_figuras.salvar): figuras/fig_executantes.pdf, .png e
fig_executantes_dados.csv.
"""

import csv
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import estilo_figuras as ef  # noqa: E402

RAIZ = AQUI.parent
CSV_REL = "data/results/por_executante_20261117_004132.csv"
CAMADA = "chord[0]"
EXECUTANTES = ["00", "01", "02", "03", "04", "05"]
TESTE = {"04", "05"}

# (painel, par no CSV, métrica, rótulo curto do painel)
PAINEIS = [
    ("a", "C vs D", "root", "(a) C→D root"),
    ("b", "D vs E", "overseg", "(b) D→E overseg"),
    ("c", "D0rg vs F0rg", "sevenths", "(c) D0rg→F0rg 7ths"),
]


def ler_linhas():
    with open(RAIZ / CSV_REL, encoding="utf-8", newline="") as fp:
        return list(csv.DictReader(fp))


def achar(linhas, par, metrica):
    sel = [l for l in linhas if l["ref_camada"] == CAMADA
           and l["par"] == par and l["metrica"] == metrica]
    if len(sel) != 1:
        raise ValueError(f"{par}/{metrica}: {len(sel)} linhas em {CSV_REL}")
    return sel[0]


def main():
    linhas = ler_linhas()
    fig, axes = ef.figura(altura=2.2, ncols=3)
    dados = []
    for ax, (painel, par, metrica, rotulo) in zip(axes, PAINEIS):
        l = achar(linhas, par, metrica)
        a, b = l["variante_a"], l["variante_b"]
        for x, e in enumerate(EXECUTANTES):
            # o CSV está em fração; a figura em pontos percentuais
            d = 100 * float(l[f"delta_{e}"])
            lo = 100 * float(l[f"ic95_min_{e}"])
            hi = 100 * float(l[f"ic95_max_{e}"])
            teste = e in TESTE
            ef.ponto_ic(ax, x, d, lo, hi, marcador="o", preenchido=teste)
            dados.append({
                "painel": painel,
                "contraste": f"{a}->{b}",
                "metrica": metrica,
                "camada": CAMADA,
                "executante": e,
                "grupo": "teste" if teste else "desenvolvimento",
                "delta_pp": round(d, 4),
                "ic95_min_pp": round(lo, 4),
                "ic95_max_pp": round(hi, 4),
                "n_faixas": int(l[f"n_faixas_{e}"]),
                "csv_origem": CSV_REL,
            })
        ef.linha_zero(ax, "h")
        # separação desenvolvimento | teste
        ax.axvline(3.5, color=ef.CINZA, linewidth=ef.LINHA_FINA * 0.8,
                   linestyle="-", zorder=0)
        ax.set_xlim(-0.6, 5.6)
        ax.set_xticks(range(6))
        ax.set_xticklabels(EXECUTANTES)
        ax.set_title(rotulo, fontsize=ef.FONTE_ANOT, pad=3)
        # zero sempre visível
        y0, y1 = ax.get_ylim()
        ax.set_ylim(min(y0, -1.0), max(y1, 1.0))
    axes[0].set_ylabel("Δ (pp)")
    axes[1].set_xlabel("Player")
    saidas = ef.salvar(fig, "fig_executantes", dados)
    for s in saidas:
        print(s)
    print(f"{len(dados)} pontos")


if __name__ == "__main__":
    main()
