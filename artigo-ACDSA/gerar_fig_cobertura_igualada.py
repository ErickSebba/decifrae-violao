"""
gerar_fig_cobertura_igualada.py
===============================
Figura fig_cobertura_igualada (camera-ready): Δ root rotulado = D − C em
cobertura igualada, NO TESTE, com IC 95 %.

Só lê o CSV já existente (nenhum experimento novo):
    data/results/cobertura_igualada_teste_20261117_011711.csv
(gerado por curvas_teste_revisao.py; protocolo em docs/ADENDO_REVISAO.md §5/§7).

Saídas (via estilo_figuras.salvar), em artigo-ACDSA/figuras/:
    fig_cobertura_igualada.pdf, .png e fig_cobertura_igualada_dados.csv
"""

import csv
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import estilo_figuras as ef  # noqa: E402

RAIZ = AQUI.parent
CSV_REL = "data/results/cobertura_igualada_teste_20261117_011711.csv"
METRICA = "root_rotulado"
ALVOS = [0.6, 0.7, 0.77, 0.9]       # ordem do eixo x categórico
DESTAQUE = 0.9

# Texto exato do método do IC, conforme curvas_teste_revisao.py e o _meta.json.
METODO_IC = ("bootstrap pareado por faixa (10000 reamostragens, seed 0, "
             "n=58 faixas do teste); em cada reamostragem as curvas C e D são "
             "reagregadas com os mesmos pesos (duração da faixa × multiplicidade "
             "na reamostragem) e reinterpoladas linearmente no "
             "alvo de cobertura; IC 95% por percentis 2,5/97,5")


def ler():
    with open(RAIZ / CSV_REL, encoding="utf-8", newline="") as fp:
        linhas = [r for r in csv.DictReader(fp) if r["metrica"] == METRICA]
    por_alvo = {round(float(r["alvo_cobertura"]), 4): r for r in linhas}
    return [por_alvo[a] for a in ALVOS]


def main():
    dados = ler()
    fig, ax = ef.figura(altura=2.2)
    ef.linha_zero(ax, "h")

    linhas = []
    for x, (alvo, r) in enumerate(zip(ALVOS, dados)):
        d = 100 * float(r["delta"])
        lo = 100 * float(r["ic95_min"])
        hi = 100 * float(r["ic95_max"])
        dest = alvo == DESTAQUE
        ef.ponto_ic(ax, x, d, lo, hi, marcador="o", preenchido=dest,
                    cor=ef.ESCURO if dest else ef.CINZA)
        if dest:
            # acima da tampa superior, centrada: não cruza a barra de 77 %
            ef.anotar(ax, f"{d:+.2f} [{lo:.2f}, {hi:.2f}]", (x, hi),
                      xytext=(0, 4), textcoords="offset points",
                      ha="center", va="bottom")
        linhas.append({
            "cobertura_alvo": alvo,
            "x_posicao": x,
            "delta_pp": round(d, 4),
            "ic95_min_pp": round(lo, 4),
            "ic95_max_pp": round(hi, 4),
            "destaque": "sim" if dest else "nao",
            "C_interp_pct": round(100 * float(r["C_interp"]), 4),
            "D_interp_pct": round(100 * float(r["D_interp"]), 4),
            "n_faixas": int(r["n_faixas"]),
            "n_boot_validos": int(r["n_boot_validos"]),
            "metodo_ic": METODO_IC,
            "csv_origem": CSV_REL,
        })

    ax.set_xticks(range(len(ALVOS)))
    ax.set_xticklabels([f"{round(100 * a)}%" for a in ALVOS])
    ax.set_xlim(-0.5, len(ALVOS) - 0.5)
    y0, y1 = ax.get_ylim()
    ax.set_ylim(y0, y1 + 0.12 * (y1 - y0))   # folga para a anotação
    ax.set_xlabel("Matched coverage")
    ax.set_ylabel("Δ labeled-time root (pp)")

    for p in ef.salvar(fig, "fig_cobertura_igualada", linhas):
        print(p)
    for l in linhas:
        print(f"{l['cobertura_alvo']:.2f}: {l['delta_pp']:+.2f} "
              f"[{l['ic95_min_pp']:.2f}, {l['ic95_max_pp']:.2f}]")


if __name__ == "__main__":
    main()
