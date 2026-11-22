"""
estilo_figuras.py
=================
Estilo comum das figuras do camera-ready (coluna IEEE).

Regras:
  - largura de uma coluna: 3,5 pol; altura entre 2,0 e 2,4 pol;
  - fonte serifada (Times New Roman / Times / STIX), 8 pt em eixos e rótulos,
    7 pt em anotações; pdf.fonttype = 42 (TrueType embutida);
  - marcador: ponto de 4 pt; barra de erro fina, com tampa;
  - linha de referência em zero: cinza, tracejada, fina;
  - legível em preto e branco: grupos distinguidos por FORMA (e
    preenchimento) do marcador, nunca só por cor;
  - sem título dentro da figura (a legenda fica no LaTeX);
  - `salvar` grava PDF vetorial + PNG 300 dpi + "<nome>_dados.csv" com
    exatamente os números desenhados e o CSV de origem de cada um.

Uso (de dentro de artigo-ACDSA/ ou com artigo-ACDSA/ no sys.path):

    import estilo_figuras as ef
    fig, ax = ef.figura(altura=2.2)
    ef.ponto_ic(ax, x, y, lo, hi, marcador="o", preenchido=True)
    ef.linha_zero(ax, "h")
    ef.salvar(fig, "fig_nome", linhas)   # linhas: list[dict]
"""

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

AQUI = Path(__file__).resolve().parent
FIGURAS = AQUI / "figuras"

LARGURA = 3.5          # pol, uma coluna IEEE
ALTURA_MIN, ALTURA_MAX = 2.0, 2.4
FONTE = 8              # pt, eixos e rótulos
FONTE_ANOT = 7         # pt, anotações
MARCADOR = 4           # pt
LINHA_FINA = 0.6       # pt
TAMPA = 2.0            # pt, tampa da barra de erro
CINZA = "0.55"
ESCURO = "0.0"

# formas de marcador para grupos (legíveis em P&B)
FORMAS = ("o", "s", "^", "D", "v", "P")


def aplicar():
    """Aplica o estilo ao matplotlib (idempotente)."""
    matplotlib.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Times", "Nimbus Roman",
                       "STIXGeneral", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "font.size": FONTE,
        "axes.labelsize": FONTE,
        "axes.titlesize": FONTE,
        "xtick.labelsize": FONTE,
        "ytick.labelsize": FONTE,
        "legend.fontsize": FONTE_ANOT,
        "axes.linewidth": LINHA_FINA,
        "xtick.major.width": LINHA_FINA,
        "ytick.major.width": LINHA_FINA,
        "xtick.major.size": 2.5,
        "ytick.major.size": 2.5,
        "lines.linewidth": LINHA_FINA,
        "lines.markersize": MARCADOR,
        "errorbar.capsize": TAMPA,
        "axes.grid": False,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "savefig.dpi": 300,
        "figure.dpi": 100,
    })


def figura(altura=2.2, ncols=1, nrows=1, **kw):
    """Figura de 3,5 pol de largura. Devolve (fig, ax) ou (fig, axes)."""
    if not ALTURA_MIN <= altura <= ALTURA_MAX:
        raise ValueError(f"altura {altura} fora de [{ALTURA_MIN}, {ALTURA_MAX}] pol")
    aplicar()
    kw.setdefault("layout", "constrained")
    return plt.subplots(nrows, ncols, figsize=(LARGURA, altura), **kw)


def linha_zero(ax, orient="h"):
    """Linha de referência em zero: cinza, tracejada, fina."""
    kw = dict(color=CINZA, linestyle=(0, (3, 2)), linewidth=LINHA_FINA, zorder=0)
    (ax.axhline if orient == "h" else ax.axvline)(0, **kw)


def ponto_ic(ax, x, y, lo, hi, marcador="o", preenchido=True, cor=ESCURO,
             horizontal=False, rotulo=None):
    """Um ponto com barra de erro do IC (lo, hi), sem linha ligando pontos.

    preenchido=False desenha o marcador vazado (face branca, borda `cor`).
    horizontal=True desenha a barra no eixo x (y categórico)."""
    face = cor if preenchido else "white"
    if horizontal:
        erro = dict(xerr=[[x - lo], [hi - x]])
    else:
        erro = dict(yerr=[[y - lo], [hi - y]])
    return ax.errorbar([x], [y], **erro, fmt=marcador, linestyle="none",
                       color=cor, ecolor=cor, elinewidth=LINHA_FINA,
                       capsize=TAMPA, capthick=LINHA_FINA,
                       markersize=MARCADOR, markerfacecolor=face,
                       markeredgecolor=cor, markeredgewidth=LINHA_FINA,
                       label=rotulo)


def anotar(ax, texto, xy, **kw):
    """Anotação em 7 pt."""
    kw.setdefault("fontsize", FONTE_ANOT)
    return ax.annotate(texto, xy, **kw)


def salvar(fig, nome, linhas, destino=FIGURAS):
    """PDF vetorial + PNG 300 dpi + <nome>_dados.csv.

    linhas: list[dict] com exatamente os números desenhados; cada dict deve
    trazer a coluna 'csv_origem'. A ordem das colunas segue o 1º dict."""
    if not linhas or any("csv_origem" not in l for l in linhas):
        raise ValueError("cada linha de dados precisa de 'csv_origem'")
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    fig.savefig(destino / f"{nome}.pdf", format="pdf")
    fig.savefig(destino / f"{nome}.png", format="png", dpi=300)
    campos = list(linhas[0])
    for l in linhas[1:]:
        campos += [c for c in l if c not in campos]
    with open(destino / f"{nome}_dados.csv", "w", encoding="utf-8",
              newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=campos, lineterminator="\n")
        w.writeheader()
        w.writerows(linhas)
    plt.close(fig)
    return [destino / f"{nome}{s}" for s in (".pdf", ".png", "_dados.csv")]
