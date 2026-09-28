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
    artigo-ACDSA/figuras/fig_pipeline.pdf           + .png
    artigo-ACDSA/figuras/fig_exemplo.pdf            + .png
    artigo-ACDSA/figuras/fig_cobertura.pdf          + .png
    artigo-ACDSA/figuras/fig_comparacoes.pdf        + .png
    artigo-ACDSA/tabelas/tab_ablacao.tex
    artigo-ACDSA/tabelas/tab_camadas.tex
    artigo-ACDSA/tabelas/tab_segmentacao.tex
    artigo-ACDSA/tabelas/tab_stats.tex

Formato das figuras: PDF vetorial (sem raster embutido), 3,5 pol de largura
(uma coluna IEEE), fontes >= 8 pt, `pdf.fonttype = 42`; PNG a 200 dpi da mesma
figura. Números com duas casas decimais e vírgula decimal.

    python figuras_artigo.py
    python figuras_artigo.py --so-tabelas
    python figuras_artigo.py --figura fig_exemplo

`fig_pipeline` é a única que não lê CSV: é um diagrama, e as suas caixas
nomeiam PARÂMETROS (rel_gate, confidence_gate, n_logprob), não valores.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import textwrap
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch, Rectangle
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
# Estilos das figuras novas
# --------------------------------------------------------------------------- #

# Cor de destaque das TRÊS fontes de N no diagrama do pipeline.
COR_N = "#c1121f"

# Estilo sistemático das 16 variantes da validação: a cor vem da família
# (a letra da matriz de ablação) e o marcador do sufixo (0 = sem a fonte de N
# daquela família; 0rg = também sem o gate relativo de RMS; b = sem os termos
# temporais do baseline). Assim C, C0 e C0rg saem na mesma cor, com marcadores
# diferentes -- a leitura "mesma variante, fonte de N desligada" fica direta.
COR_FAMILIA = {
    "V4": "#6c584c", "A": "#89c2d9", "B": "#468faf", "C": "#2a6f97",
    "D": "#e07a5f", "E": "#b5179e", "F": "#3d8361",
}
MARCA_SUFIXO = {"": "o", "b": "v", "0": "s", "0rg": "^"}

# Forest plot: validação contra teste.
COR_VAL = "#2a6f97"
COR_TESTE = "#c1121f"
COR_FAIXA = "#5c677d"


def familia_sufixo(nome: str) -> tuple[str, str]:
    """`C0rg` -> ('C', '0rg'); `V4b` -> ('V4', 'b'); `A` -> ('A', '')."""
    base = "V4" if nome.startswith("V4") else nome[:1]
    return base, nome[len(base):]


def estilo_variante(nome: str) -> dict:
    fam, suf = familia_sufixo(nome)
    if fam not in COR_FAMILIA or suf not in MARCA_SUFIXO:
        raise SystemExit(f"variante sem estilo definido: {nome!r}")
    return dict(cor=COR_FAMILIA[fam], marcador=MARCA_SUFIXO[suf])


def _cor_do_texto(cor) -> str:
    """Preto ou branco, o que tiver contraste sobre `cor`."""
    r, g, b = mcolors.to_rgb(cor)
    return "black" if (0.299 * r + 0.587 * g + 0.114 * b) > 0.55 else "white"


# Nomes curtos das doze classes de altura (uma ou duas letras: cabem na barra).
NOTAS = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
_SEMITOM = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def pc_do_rotulo(rotulo: str):
    """Rótulo Harte -> classe de altura da tônica; None para N/X/vazio."""
    if not rotulo:
        return None
    raiz = rotulo.split(":")[0].split("/")[0].strip()
    if not raiz or raiz[0].upper() not in _SEMITOM:
        return None
    pc = _SEMITOM[raiz[0].upper()]
    for ch in raiz[1:]:
        if ch == "#":
            pc += 1
        elif ch == "b":
            pc -= 1
        else:
            return None
    return pc % 12


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


def _todos(padrao: str, aceita) -> list[tuple[Path, dict]]:
    """Todos os CSV cujo meta satisfaz `aceita`, em ordem de timestamp."""
    achados = []
    for p in sorted(RESULTS.glob(padrao)):
        m = _meta(p)
        if aceita(m):
            achados.append((p, m))
    if not achados:
        raise SystemExit(f"nenhum {padrao} com meta compatível em {RESULTS}")
    return achados


def _escolher(padrao: str, aceita) -> tuple[Path, dict]:
    """O CSV mais recente (nome com timestamp) cujo meta satisfaz `aceita`."""
    return _todos(padrao, aceita)[-1]


def _splits(m: dict) -> list[str]:
    return m.get("splits") or ([m["split"]] if m.get("split") else [])


def selecionar() -> dict:
    fontes = {}
    fontes["curvas_val"] = _escolher(
        "curvas_*.csv", lambda m: "val" in _splits(m))
    for cam, suf in (("chord[0]", "ref0"), ("chord[1]", "ref1")):
        # >= 6 variantes: a rodada do teste foi partida em dois CSV (as seis
        # congeladas e, depois, C0rg e V4b). Sem o filtro, o "mais recente"
        # seria o CSV de duas variantes e as tabelas do teste sairiam truncadas.
        fontes[f"abl_test_{suf}"] = _escolher(
            "ablation_*.csv",
            lambda m, c=cam: _splits(m) == ["test"] and m.get("ref_camada") == c
            and len(m.get("variantes", [])) >= 6)
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
    # Fontes do forest plot: exige `n_comparacoes == 15` no meta, porque a
    # figura põe validação e teste lado a lado e só serve se as duas tiverem a
    # família pré-registrada inteira (as rodadas antigas do teste têm 11).
    for chave, split in (("stats15_val", "val"), ("stats15_test", "test")):
        fontes[chave] = _escolher(
            "stats_*.csv",
            lambda m, s=split: _splits(m) == [s]
            and m.get("ref_camada") == "chord[0]"
            and m.get("n_comparacoes") == 15)
    fontes["mascara"] = _escolher(
        "mascara_comum_*.csv",
        lambda m: m.get("ref_camada") == "chord[0]" and m.get("nivel") == "root")
    return fontes


def abl_test_unida(camada: str = "chord[0]"):
    """
    União de TODAS as ablações do teste nessa camada de referência.

    A rodada do teste saiu em dois CSV (as seis variantes congeladas e, depois,
    C0rg e V4b). Os pares pré-registrados atravessam os dois arquivos, então o
    Δ por faixa só existe na união. Devolve
    ({variante: {track_id: linha}}, ordem_das_variantes, arquivos).
    """
    arquivos = _todos(
        "ablation_*.csv",
        lambda m: _splits(m) == ["test"] and m.get("ref_camada") == camada)
    tabela: dict[str, dict[str, dict]] = defaultdict(dict)
    ordem: list[str] = []
    for p, m in arquivos:
        for v in m.get("variantes", []):
            if v not in ordem:
                ordem.append(v)
        for l in _linhas(p):
            tabela[l["variante"]][l["track_id"]] = l
    return dict(tabela), ordem, [p for p, _ in arquivos]


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
    fig.savefig(pdf, format="pdf", bbox_inches="tight", pad_inches=0.02)
    fig.savefig(png, format="png", dpi=DPI_PNG, bbox_inches="tight",
                pad_inches=0.02)
    plt.close(fig)
    return [pdf, png]


def largura_pdf(pdf: Path) -> float:
    """Largura do PDF em polegadas, lida do /MediaBox."""
    import re
    m = re.search(rb"/MediaBox\s*\[([^\]]*)\]", pdf.read_bytes())
    if not m:
        return float("nan")
    v = [float(x) for x in m.group(1).split()]
    return (v[2] - v[0]) / 72.0


def _base(fig, artista=None) -> float:
    """
    Borda inferior de um artista (ou de todos os eixos) em fração da figura.

    Serve para empilhar legendas e nota SEM chutar deslocamentos: cada peça é
    desenhada, medida, e a próxima entra logo abaixo da anterior. Chutar o
    `bbox_to_anchor` faz as legendas se sobreporem assim que o número de
    entradas muda.
    """
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    inv = fig.transFigure.inverted()
    if artista is not None:
        return artista.get_window_extent(r).transformed(inv).y0
    return min(ax.get_tightbbox(r).transformed(inv).y0 for ax in fig.axes)


def _encaixar(fig, margem: float = 0.02):
    """
    Puxa os eixos para dentro da tela quando um rótulo escapa pela borda.

    O `tight_layout` erra a margem esquerda quando o ylabel é horizontal
    (`rotation=0`): ele reserva menos do que o rótulo ocupa e o texto sai da
    figura, que então o `bbox_inches="tight"` alarga além das 3,5 pol. Aqui a
    sobra é MEDIDA e devolvida ao eixo, em até três passadas.
    """
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    inv = fig.dpi_scale_trans.inverted()
    largura = fig.get_size_inches()[0]
    for _ in range(3):
        caixas = [ax.get_tightbbox(r).transformed(inv) for ax in fig.axes]
        de = max(0.0, margem - min(b.x0 for b in caixas))
        para = max(0.0, max(b.x1 for b in caixas) - (largura - margem))
        if de < 1e-3 and para < 1e-3:
            break
        for ax in fig.axes:
            p = ax.get_position()
            ax.set_position([p.x0 + de / largura, p.y0,
                             p.width - (de + para) / largura, p.height])
        fig.canvas.draw()
    return fig


def _nota(fig, texto: str, y: float, limite: float = None):
    """
    Escreve a nota de rodapé quebrada na largura que REALMENTE cabe em uma
    coluna IEEE. Quebrar em um número fixo de caracteres não serve: 62
    caracteres de DejaVu Sans a 8 pt dão ~3,8 pol, e o `bbox_inches="tight"`
    faria a figura sair mais larga que as 3,5 pol exigidas. Aqui a largura é
    medida no renderizador e o número de colunas é ajustado até caber.
    """
    limite = LARGURA_POL - 0.26 if limite is None else limite

    def _por(n):
        t = fig.text(0.5, y, textwrap.fill(texto, n), ha="center", va="top",
                     fontsize=FONTE, transform=fig.transFigure)
        fig.canvas.draw()
        larg = (t.get_window_extent(fig.canvas.get_renderer()).width
                / fig.get_dpi())
        return t, larg

    t, larg = _por(64)
    n = max(20, int(64 * limite / larg)) if larg > 0 else 64
    while larg > limite and n > 20:
        t.remove()
        t, larg = _por(n)
        n -= 2
    return t


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
    _nota(fig, nota, -0.30)

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
# C) diagrama do pipeline e das três fontes de N
# --------------------------------------------------------------------------- #

# (texto, n_linhas, indentada, alternativa, irmã, tag) -- tag = (título, sub)
# `alternativa=True` é a rota que só existe com use_viterbi=False: sai da
# emissão, volta para o merge, e é desenhada tracejada e indentada.
# `irmã=True` marca a caixa que ocupa o lugar da alternativa na rota principal
# (o Viterbi), para que a alternativa não seja ligada a ela por engano.
_PIPELINE = [
    ("cara", [
        ("HPSS", 1, False, False, False, None),
        ("beat track", 1, False, False, False, None),
        ("CQT", 1, False, False, False, None),
        ("filtro de mediana", 1, False, False, False, None),
        ("sync por batida", 1, False, False, False, None),
        ("RMS por segmento", 1, False, False, False, None),
    ]),
    ("barata", [
        ("gate de silêncio", 1, False, False, False,
         ("rel_gate", "N por silêncio")),
        ("emissão por cosseno", 1, False, False, False, None),
        ("argmax por segmento\nuse_viterbi = False", 2, True, True, False,
         ("confidence_gate", "N por dúvida")),
        ("Viterbi\nuse_viterbi = True", 2, False, False, True,
         ("n_logprob", "estado N")),
        ("merge de vizinhos iguais", 1, False, False, False, None),
        ("absorção de curtos\n(min_dur)", 2, False, False, False, None),
    ]),
]
_TITULO_GRUPO = {
    "cara": "etapa cara — extract_features (cache em disco)",
    "barata": "etapa barata — decode",
}

# Geometria em "unidades de linha"; 1 unidade vira ALT_UNIDADE polegadas.
_ALT_TITULO = 0.95
_ALT_VAO = 0.45
ALT_UNIDADE = 0.30


def fig_pipeline(fontes=None) -> tuple[list[Path], dict]:
    """
    Diagrama do pipeline com as três fontes de N destacadas.

    É desenho, não dado: nenhum número sai de CSV aqui (nem entra à mão --
    as caixas nomeiam PARÂMETROS, não valores). O que a figura precisa deixar
    claro é a precedência: o `rel_gate` produz a máscara `force_n`, que zera as
    emissões de acorde no Viterbi e emite N direto no argmax. Ou seja,
    SOBREPÕE tanto o `n_logprob` quanto o `confidence_gate`.
    """
    x0, larg, x_ind = 0.0, 0.58, 0.06       # caixas (a alternativa é indentada)
    x_tag, larg_tag = 0.62, 0.41            # coluna das etiquetas de fonte de N
    x_sobrepoe = 1.065                      # trilho vertical do force_n
    x_desvio = 0.028                        # desvio da rota principal (esquerda)
    x_retorno = 0.605                       # retorno da rota alternativa
    x_grupo = 0.56                          # ligação entre as duas etapas

    # posições verticais, de cima para baixo, em unidades de linha
    y = 0.0
    titulos, caixas = [], []
    for i, (grupo, etapas) in enumerate(_PIPELINE):
        if i:
            y += _ALT_VAO
        titulos.append((y + _ALT_TITULO * 0.55, _TITULO_GRUPO[grupo]))
        y += _ALT_TITULO
        inicio = y
        for texto, nlin, indent, alt, irma, tag in etapas:
            alt_caixa = 0.55 + 0.42 * nlin
            caixas.append(dict(texto=texto, y=y, h=alt_caixa, indent=indent,
                               alt=alt, irma=irma, tag=tag, grupo=i))
            y += alt_caixa + 0.38
        titulos[-1] = titulos[-1] + (inicio - 0.12, y - 0.38 + 0.14)
    total = y - 0.38 + 0.20

    _rc()
    fig, ax = plt.subplots(figsize=(LARGURA_POL, total * ALT_UNIDADE))
    ax.set_xlim(-0.11, 1.17)
    ax.set_ylim(total, 0.0)                 # y cresce para BAIXO
    ax.axis("off")
    ax.set_frame_on(False)

    for yt, rotulo, ya, yb in titulos:
        ax.add_patch(Rectangle((x0 - 0.025, ya), larg + 0.05, yb - ya,
                               facecolor="#f2f2f2", edgecolor="#d9d9d9",
                               linewidth=0.5, zorder=0))
        ax.text(x0 - 0.02, yt, rotulo, fontsize=FONTE, style="italic",
                color="0.35", ha="left", va="center")

    def _seta(xa, ya, xb, yb, tracejada=False, cor="0.25"):
        ax.annotate("", xy=(xb, yb), xytext=(xa, ya),
                    arrowprops=dict(arrowstyle="-|>", linewidth=0.8,
                                    color=cor, shrinkA=0, shrinkB=0,
                                    mutation_scale=7,
                                    linestyle="--" if tracejada else "-"))

    for c in caixas:
        xi = x_ind if c["indent"] else x0
        wi = larg - (x_ind - x0) if c["indent"] else larg
        ax.add_patch(FancyBboxPatch(
            (xi, c["y"]), wi, c["h"],
            boxstyle="round,pad=0,rounding_size=0.025",
            facecolor="white", edgecolor="0.25", zorder=2,
            linewidth=1.0, linestyle="--" if c["alt"] else "-"))
        ax.text(xi + wi / 2, c["y"] + c["h"] / 2, c["texto"], fontsize=FONTE,
                ha="center", va="center", zorder=3, linespacing=1.25)

    # Encadeamento. A rota principal salta a caixa alternativa pela ESQUERDA
    # (x = x_desvio, à esquerda da indentação); a alternativa sai da emissão,
    # entra na caixa indentada e VOLTA para o merge por um canal à direita.
    principais = [c for c in caixas if not c["alt"]]
    for a, b in zip(principais, principais[1:]):
        if a["grupo"] != b["grupo"]:
            x = x_grupo
        elif any(c["alt"] and a["y"] < c["y"] < b["y"] for c in caixas):
            x = x_desvio
        else:
            x = x0 + larg / 2
        _seta(x, a["y"] + a["h"], x, b["y"])
    for c in caixas:
        if not c["alt"]:
            continue
        antes = [p for p in principais
                 if p["y"] < c["y"] and not p["irma"]][-1]
        depois = [p for p in principais
                  if p["y"] > c["y"] and not p["irma"]][0]
        _seta(0.42, antes["y"] + antes["h"], 0.42, c["y"], tracejada=True)
        yc, yd = c["y"] + c["h"] / 2, depois["y"] + depois["h"] / 2
        ax.plot([x0 + larg, x_retorno, x_retorno], [yc, yc, yd],
                color="0.25", linewidth=0.8, linestyle="--", zorder=1)
        _seta(x_retorno, yd, x0 + larg, yd, tracejada=True)

    # as TRÊS fontes de N, na cor de destaque, na altura de onde cada uma age
    tags = [c for c in caixas if c["tag"]]
    for c in tags:
        titulo, sub = c["tag"]
        yc = c["y"] + c["h"] / 2
        ax.add_patch(FancyBboxPatch(
            (x_tag, yc - 0.44), larg_tag, 0.88,
            boxstyle="round,pad=0,rounding_size=0.025",
            facecolor="#fdeaec", edgecolor=COR_N, linewidth=1.0, zorder=2))
        ax.text(x_tag + larg_tag / 2, yc - 0.16, titulo, fontsize=FONTE,
                color=COR_N, ha="center", va="center", zorder=3,
                fontfamily="monospace")
        ax.text(x_tag + larg_tag / 2, yc + 0.22, sub, fontsize=FONTE,
                color=COR_N, ha="center", va="center", zorder=3)
        xi = x_ind if c["indent"] else x0
        _seta(x_tag, yc, xi + (larg - (x_ind - x0) if c["indent"] else larg),
              yc, cor=COR_N)

    # precedência: o rel_gate (primeira etiqueta) sobrepõe as outras duas
    y_rg = tags[0]["y"] + tags[0]["h"] / 2
    ax.plot([x_tag + larg_tag, x_sobrepoe], [y_rg, y_rg], color=COR_N,
            linewidth=1.2, zorder=3)
    ax.plot([x_sobrepoe, x_sobrepoe], [y_rg, tags[-1]["y"] + tags[-1]["h"] / 2],
            color=COR_N, linewidth=1.2, zorder=3)
    for c in tags[1:]:
        yc = c["y"] + c["h"] / 2
        _seta(x_sobrepoe, yc, x_tag + larg_tag, yc, cor=COR_N)
    ax.text(x_sobrepoe + 0.035, (y_rg + tags[-1]["y"] + tags[-1]["h"] / 2) / 2,
            "force_n", fontsize=FONTE, color=COR_N, rotation=90,
            ha="center", va="center", fontfamily="monospace")

    nota = ("Em vermelho, as três fontes de N e o ponto em que cada uma age. "
            "O gate relativo de silêncio (rel_gate) SOBREPÕE as outras duas: "
            "os segmentos que ele marca entram como force_n, que zera as "
            "emissões de acorde no Viterbi e emite N direto no argmax. Logo o "
            "confidence_gate — que só o argmax consulta, com "
            "use_viterbi = False — e o estado N do Viterbi (n_logprob) só "
            "decidem onde o rel_gate não decidiu.")
    fig.tight_layout(pad=0.2)
    _nota(fig, nota, _base(fig) - 0.012)

    saidas = _salvar(fig, FIGURAS / "fig_pipeline")
    return saidas, {"caixas": len(caixas), "fontes_de_N": len(tags),
                    "nota": nota}


# --------------------------------------------------------------------------- #
# D) figura de exemplo: uma faixa da validação, escolhida por regra
# --------------------------------------------------------------------------- #

REGRA_EXEMPLO = ("a faixa da validação cuja diferença de root entre D e C é a "
                 "mediana INFERIOR das 120 — ordenação crescente dos 120 Δ, "
                 "posição 60 de 120 (índice 59, contando de 0): a menor das "
                 "duas estatísticas centrais")
VARIANTES_EXEMPLO = ["C", "D", "E"]


def escolher_faixa_exemplo(fontes) -> dict:
    """A faixa do exemplo, por REGRA, lida do CSV de ablação da validação."""
    csv_path, meta = fontes["abl_val_ref0"]
    g = defaultdict(dict)
    for l in _linhas(csv_path):
        g[l["variante"]][l["track_id"]] = l
    faltam = [v for v in ("C", "D") if v not in g]
    if faltam:
        raise SystemExit(f"{csv_path.name} não tem as variantes {faltam}")
    comuns = sorted(set(g["C"]) & set(g["D"]))
    deltas = sorted((float(g["D"][t]["root"]) - float(g["C"][t]["root"]), t)
                    for t in comuns)
    i = (len(deltas) - 1) // 2          # mediana inferior; 120 -> índice 59
    delta, track_id = deltas[i]
    return {
        "track_id": track_id, "delta": delta, "indice": i,
        "n_faixas": len(deltas), "fonte": csv_path.name,
        "delta_min": deltas[0][0], "delta_max": deltas[-1][0],
        "mediana_numerica": (deltas[len(deltas) // 2 - 1][0]
                             + deltas[len(deltas) // 2][0]) / 2,
        "root_C": float(g["C"][track_id]["root"]),
        "root_D": float(g["D"][track_id]["root"]),
        "duracao_s": float(g["C"][track_id]["duracao_s"]),
    }


def _linha_do_manifest(track_id: str) -> dict:
    manifest = ROOT / "data" / "manifests" / "guitarset_comping.csv"
    for row in _linhas(manifest):
        if row["track_id"] == track_id:
            return row
    raise SystemExit(f"{track_id} não está em {manifest.name}")


def _barras_de_acorde(ax, segs, cores, seg_por_pol: float):
    """Desenha (start, end, label) como barras coloridas pela tônica."""
    for inicio, fim, rotulo in segs:
        pc = pc_do_rotulo(rotulo)
        cor = "0.78" if pc is None else cores[pc]
        ax.add_patch(Rectangle((inicio, 0.0), fim - inicio, 1.0,
                               facecolor=cor, edgecolor="white",
                               linewidth=0.35))
        texto = "N" if pc is None else NOTAS[pc]
        # só rotula a barra que couber: 8 pt tem ~0,062 pol por caractere.
        if (fim - inicio) >= len(texto) * 0.062 * 1.35 * seg_por_pol:
            ax.text((inicio + fim) / 2, 0.5, texto, ha="center", va="center",
                    fontsize=FONTE, color=_cor_do_texto(cor))
    ax.set_ylim(0, 1)
    ax.set_yticks([])
    ax.grid(False)


def fig_exemplo(fontes) -> tuple[list[Path], dict]:
    """
    Painéis empilhados de UMA faixa da validação, escolhida pela regra de
    `REGRA_EXEMPLO`. Chroma do cache, referência do JAMS, saídas decodificadas
    do cache pelo `runner.estimar` (nenhuma extração de chroma refeita).
    """
    import cache
    import dataset_io
    import runner
    from config import PRE_CHROMA

    escolha = escolher_faixa_exemplo(fontes)
    linha = _linha_do_manifest(escolha["track_id"])
    audio = ROOT / linha["audio_path"]
    jams = ROOT / linha["annotation_path"]

    features = cache.get_features(audio, PRE_CHROMA)
    ref = dataset_io.load_guitarset(jams, index=0)
    saidas_var = {v: runner.estimar(runner.VARIANTES[v], features)
                  for v in VARIANTES_EXEMPLO}

    chroma, bordas = features.chroma, features.beat_times
    n_seg = chroma.shape[1]
    if len(bordas) < n_seg + 1:           # fecha a cauda se faltar uma borda
        passo = bordas[-1] - bordas[-2] if len(bordas) > 1 else 0.5
        bordas = list(bordas) + [bordas[-1] + passo]
    bordas = list(bordas)[:n_seg + 1]
    t_fim = max(float(bordas[-1]), max(s[1] for s in ref),
                *[max(s[1] for s in segs) for segs in saidas_var.values()])

    cores = [mcolors.to_hex(c) for c in
             plt.get_cmap("twilight_shifted")([(i + 0.5) / 12 for i in range(12)])]

    _rc()
    fig, axs = plt.subplots(
        5, 1, figsize=(LARGURA_POL, 4.7), sharex=True,
        gridspec_kw=dict(height_ratios=[2.7, 0.62, 0.62, 0.62, 0.62],
                         hspace=0.16))
    seg_por_pol = t_fim / 2.55            # estimativa da largura útil do eixo

    # (a) chromagrama sincronizado por batida -- pcolormesh (malha vetorial),
    # nunca imshow: imshow embutiria um /Subtype /Image no PDF.
    axs[0].pcolormesh(bordas, range(13), chroma, cmap="magma", vmin=0.0,
                      shading="flat", rasterized=False)
    axs[0].set_yticks([i + 0.5 for i in range(12)])
    axs[0].set_yticklabels(NOTAS)
    axs[0].set_ylabel("chroma", fontsize=FONTE)
    axs[0].grid(False)
    # O track_id vai para a nota, não para o título: a 8 pt ele empurraria o
    # título para fora das 3,5 pol da coluna.
    axs[0].set_title("(a) chroma sinc. por batida", loc="left", fontsize=FONTE)

    painéis = [("(b) ref chord[0]", ref)] + [
        (f"({l}) {v}", saidas_var[v])
        for l, v in zip("cde", VARIANTES_EXEMPLO)]
    for ax, (rotulo, segs) in zip(axs[1:], painéis):
        _barras_de_acorde(ax, segs, cores, seg_por_pol)
        ax.set_ylabel(rotulo, rotation=0, ha="right", va="center",
                      fontsize=FONTE, labelpad=4)
    for ax in axs:
        ax.set_xlim(0, t_fim)
        ax.xaxis.set_major_formatter(_virgula)
    axs[-1].set_xlabel("tempo (s)")

    nota = (f"Faixa {escolha['track_id']}, escolhida por REGRA e não a dedo: "
            f"{REGRA_EXEMPLO}. "
            f"Δroot(D−C) = {sinal(escolha['delta']).replace('$-$', '−')} p.p. "
            f"Cor da barra = tônica do acorde; N em cinza. A barra só recebe "
            f"o nome da tônica quando o texto cabe nela. Fonte da regra: "
            f"{escolha['fonte']}.")
    fig.tight_layout(pad=0.3)
    _encaixar(fig)
    _nota(fig, nota, _base(fig) - 0.02)

    rotulos = {v: sorted({s[2] for s in saidas_var[v]}) for v in VARIANTES_EXEMPLO}
    resumo = {**escolha, "regra": REGRA_EXEMPLO,
              "n_segmentos": {v: len(saidas_var[v]) for v in VARIANTES_EXEMPLO},
              "rotulos": rotulos,
              "n_segmentos_ref": len(ref),
              "rotulos_ref": sorted({s[2] for s in ref})}
    return _salvar(fig, FIGURAS / "fig_exemplo"), resumo


# --------------------------------------------------------------------------- #
# E) cobertura x acerto, SÓ validação, painel único, nível root
# --------------------------------------------------------------------------- #

def fig_cobertura(fontes) -> tuple[list[Path], dict]:
    """
    Painel único, nível `root`, só validação: as três curvas varridas (C pelo
    confidence_gate, D e F pelo n_logprob) e os pontos das 16 variantes
    medidas na validação. Nada do teste entra aqui.
    """
    curvas = curvas_agregadas(fontes["curvas_val"][0])
    csv_val, meta_val = fontes["abl_val_ref0"]
    ordem = meta_val["variantes"]
    g = por_variante(_linhas(csv_val))
    pontos = {v: dict(cobertura=1.0 - wmean(g[v], "frac_n_est"),
                      rotulado=wmean(g[v], "root_rotulado")) for v in ordem}

    # As curvas mantêm rel_gate > 0; é ESSE gate que as trava abaixo de 100 %.
    cob_max = max(p["cobertura"] for c in ("C", "D", "F")
                  for p in curvas.get(c, []))
    rel_gate = _meta(csv_val)["config_base"]["post"]["rel_gate"]
    cob_total = max(p["cobertura"] for p in pontos.values())
    cheias = [v for v in ordem if pontos[v]["cobertura"] >= cob_total - 1e-9]

    _rc()
    fig, ax = plt.subplots(figsize=(LARGURA_POL, 2.9))
    for c in ("C", "D", "F"):
        ps = curvas.get(c)
        if not ps:
            continue
        e = ESTILO_CURVA[c]
        ax.plot([p["cobertura"] * 100 for p in ps],
                [p["rotulado"]["root"] * 100 for p in ps],
                marker=e["marcador"], color=e["cor"], markersize=3,
                linewidth=1.0, zorder=2)
    for v in ordem:
        e = estilo_variante(v)
        ax.plot([pontos[v]["cobertura"] * 100], [pontos[v]["rotulado"] * 100],
                marker=e["marcador"], color=e["cor"], markersize=5.5,
                markerfacecolor="white", markeredgewidth=1.2,
                linestyle="none", zorder=3)
    ax.axvline(cob_max * 100, color="0.45", linewidth=0.7, linestyle=":",
               zorder=1)
    ax.set_xlabel("cobertura: fração do tempo rotulada (%)")
    ax.set_ylabel("acerto rotulado em root (%)")
    ax.xaxis.set_major_formatter(_virgula)
    ax.yaxis.set_major_formatter(_virgula)

    h_curva = [Line2D([], [], color=ESTILO_CURVA[c]["cor"],
                      marker=ESTILO_CURVA[c]["marcador"], markersize=3,
                      linewidth=1.0, label=ESTILO_CURVA[c]["rotulo"])
               for c in ("C", "D", "F") if c in curvas]
    h_ponto = [Line2D([], [], color=estilo_variante(v)["cor"],
                      marker=estilo_variante(v)["marcador"], markersize=5.5,
                      markerfacecolor="white", markeredgewidth=1.2,
                      linestyle="none", label=v) for v in ordem]
    fig.tight_layout(pad=0.4)
    leg1 = fig.legend(handles=h_curva, loc="upper center",
                      bbox_to_anchor=(0.5, _base(fig) - 0.03), ncol=1,
                      frameon=False, handlelength=1.8, borderaxespad=0.0,
                      title="curvas: varredura na validação")
    leg1._legend_box.align = "left"
    leg2 = fig.legend(handles=h_ponto, loc="upper center",
                      bbox_to_anchor=(0.5, _base(fig, leg1) - 0.035), ncol=4,
                      frameon=False, handlelength=1.0, columnspacing=1.0,
                      labelspacing=0.3, borderaxespad=0.0,
                      title="pontos: variantes medidas na validação")
    leg2._legend_box.align = "left"

    nota = (f"Só validação. As três curvas param em {pct(cob_max)} % de "
            f"cobertura (linha pontilhada), não em 100 %: mesmo com o gate de "
            f"confiança e o estado N do Viterbi desligados, elas mantêm o gate "
            f"RELATIVO de silêncio (rel_gate = {num(rel_gate, 1)}), e é ele — "
            f"não o abs_floor — que força N nos {pct(1 - cob_max)} % restantes. "
            f"As variantes que zeram o rel_gate e os baselines "
            f"({', '.join(cheias)}) chegam a {pct(cob_total)} %.")
    _nota(fig, nota, _base(fig, leg2) - 0.045)

    saidas = _salvar(fig, FIGURAS / "fig_cobertura")
    return saidas, {"cob_max": cob_max, "cob_total": cob_total,
                    "cheias": cheias, "rel_gate": rel_gate, "nota": nota}


# --------------------------------------------------------------------------- #
# F) forest plot das comparações pré-registradas + duas linhas post hoc
# --------------------------------------------------------------------------- #

def _percentil(ordenado, q):
    if not ordenado:
        return float("nan")
    i = min(len(ordenado) - 1, max(0, int(round(q * (len(ordenado) - 1)))))
    return ordenado[i]


def fig_comparacoes(fontes) -> tuple[list[Path], dict]:
    """
    Forest plot das 15 comparações pré-registradas em chord[0]: Δ e IC 95 % da
    validação e do teste na mesma linha, Δ por faixa do teste ao fundo, classe
    do teste na margem. No fim, duas linhas POST HOC da máscara comum.
    """
    p_test, m_test = fontes["stats15_test"]
    p_val, m_val = fontes["stats15_val"]
    p_masc, m_masc = fontes["mascara"]
    teste, valid = _linhas(p_test), _linhas(p_val)
    chave = lambda l: (l["variante_a"], l["variante_b"], l["metrica"])
    val_por = {chave(l): l for l in valid}
    ausentes = [chave(l) for l in teste if chave(l) not in val_por]
    if ausentes:
        raise SystemExit(f"comparações do teste sem par na validação: {ausentes}")

    tabela, _ordem, arquivos = abl_test_unida("chord[0]")

    linhas = []
    for lt in teste:
        lv = val_por[chave(lt)]
        a, b, met = chave(lt)
        faixas = sorted(set(tabela.get(a, {})) & set(tabela.get(b, {})))
        por_faixa = sorted(
            (float(tabela[b][t][met]) - float(tabela[a][t][met])) * 100
            for t in faixas)
        linhas.append(dict(
            rotulo=f"{a}→{b} {met}",
            val=(float(lv["diferenca"]), float(lv["ic95_min"]),
                 float(lv["ic95_max"])),
            test=(float(lt["diferenca"]), float(lt["ic95_min"]),
                  float(lt["ic95_max"])),
            classe=CLASSIF.get(lt["classificacao"], lt["classificacao"]),
            por_faixa=por_faixa, post_hoc=False))

    # duas linhas POST HOC: a análise de máscara comum (C vs D em root)
    mc = _linhas(p_masc)
    for masc in ("M_C", "M_CD"):
        def _um(split):
            achado = [l for l in mc if l["mascara"] == masc
                      and l["split"] == split]
            if len(achado) != 1:
                raise SystemExit(
                    f"{p_masc.name}: esperava 1 linha {masc}/{split}, "
                    f"achei {len(achado)}")
            l = achado[0]
            return (float(l["diferenca"]), float(l["ic95_min"]),
                    float(l["ic95_max"])), l
        (dv, lov, hiv), _ = _um("val")
        (dt, lot, hit), lt = _um("test")
        linhas.append(dict(
            rotulo=f"{lt['variante_a']}→{lt['variante_b']} {lt['nivel']} "
                   f"({masc})",
            val=(dv, lov, hiv), test=(dt, lot, hit),
            classe="post hoc", por_faixa=[], post_hoc=True))

    # limites do eixo: cobrem todos os IC e o miolo (p2,5--p97,5) das nuvens.
    # Pontos fora ficam recortados e o número deles entra na nota.
    todos = sorted(v for l in linhas for v in l["por_faixa"])
    lim_ic = max(abs(v) for l in linhas for v in (l["val"] + l["test"])) * 100
    lim = max(lim_ic * 1.12,
              abs(_percentil(todos, 0.025)), abs(_percentil(todos, 0.975)))
    lim = 5.0 * ((lim // 5.0) + 1)
    fora = sum(1 for v in todos if abs(v) > lim)

    n = len(linhas)
    _rc()
    fig, ax = plt.subplots(figsize=(LARGURA_POL, 0.30 * n + 1.25))
    ax.set_axisbelow(True)
    # Jitter vertical determinístico (sem RNG), pela sequência áurea: como os
    # Δ entram ordenados, um passo de período curto desenharia faixas
    # diagonais falsas; o passo irracional não tem período.
    jitter = lambda k: (((k + 1) * 0.6180339887498949) % 1.0 - 0.5) * 0.34
    for i, l in enumerate(linhas):
        if l["post_hoc"]:
            ax.axhspan(i - 0.5, i + 0.5, color="#fdf0d5", zorder=0)
        elif i % 2 == 0:
            ax.axhspan(i - 0.5, i + 0.5, color="0.955", zorder=0)
        if l["por_faixa"]:
            ax.scatter(l["por_faixa"],
                       [i + jitter(k) for k in range(len(l["por_faixa"]))],
                       s=2.6, color=COR_FAIXA, alpha=0.20, linewidths=0,
                       zorder=1)
        for desl, (d, lo, hi), cor, marca, cheio in (
                (-0.19, l["val"], COR_VAL, "o", False),
                (+0.19, l["test"], COR_TESTE, "s", True)):
            ax.errorbar([d * 100], [i + desl],
                        xerr=[[(d - lo) * 100], [(hi - d) * 100]],
                        fmt=marca, markersize=3.4, color=cor,
                        markerfacecolor=cor if cheio else "white",
                        markeredgewidth=0.9, elinewidth=0.9, capsize=1.6,
                        capthick=0.9, zorder=4 if cheio else 3)
        ax.text(1.025, i, l["classe"], transform=ax.get_yaxis_transform(),
                ha="left", va="center", fontsize=FONTE,
                color=COR_N if l["post_hoc"] else "0.25",
                style="italic" if l["post_hoc"] else "normal")
    primeiro_ph = min((i for i, l in enumerate(linhas) if l["post_hoc"]),
                      default=None)
    if primeiro_ph is not None:
        ax.axhline(primeiro_ph - 0.5, color=COR_N, linewidth=0.8,
                   linestyle="--", zorder=5)
    ax.axvline(0.0, color="0.15", linewidth=0.9, zorder=2)
    ax.set_yticks(range(n))
    ax.set_yticklabels([l["rotulo"] for l in linhas], fontsize=FONTE)
    ax.set_ylim(n - 0.5, -0.5)
    ax.set_xlim(-lim, lim)
    ax.set_xlabel("Δ = B − A (pontos percentuais)")
    ax.xaxis.set_major_formatter(_virgula)
    ax.grid(axis="x", alpha=0.3)
    ax.grid(axis="y", visible=False)

    handles = [
        Line2D([], [], color=COR_VAL, marker="o", markerfacecolor="white",
               markeredgewidth=0.9, markersize=3.4, linewidth=0.9,
               label="validação: Δ e IC 95 %"),
        Line2D([], [], color=COR_TESTE, marker="s", markersize=3.4,
               linewidth=0.9, label="teste: Δ e IC 95 %"),
        Line2D([], [], color=COR_FAIXA, marker="o", linestyle="none",
               markersize=2.6, alpha=0.45, label="Δ por faixa (teste)"),
    ]
    # A classe fica FORA do eixo (x = 1,025 em fração do eixo). O tight_layout
    # não enxerga esse texto, então a margem direita é reservada à mão -- sem
    # isso a figura sai mais larga que as 3,5 pol de uma coluna.
    # `confirmado` é a classe mais larga (~0,62 pol a 8 pt); 0,68 pol de
    # reserva bastam e deixam o painel o mais largo possível.
    fig.tight_layout(pad=0.4,
                     rect=(0.0, 0.0, 1.0 - 0.68 / LARGURA_POL, 1.0))
    _encaixar(fig)
    leg = fig.legend(handles=handles, loc="upper center",
                     bbox_to_anchor=(0.5, _base(fig) - 0.02), ncol=1,
                     frameon=False, handlelength=1.8, borderaxespad=0.0)
    leg._legend_box.align = "left"

    nota = (f"Um par por linha, camada chord[0]. Linha vertical em zero. A "
            f"classe na margem é a do TESTE. As duas últimas linhas, em "
            f"destaque, são POST HOC (máscara comum, "
            f"{p_masc.name}): não constam dos pares pré-registrados e não têm "
            f"Δ por faixa publicado. O eixo foi cortado em "
            f"±{num(lim, 0)} p.p.; {fora} de {len(todos)} pontos por faixa "
            f"ficam fora do corte.")
    _nota(fig, nota, _base(fig, leg) - 0.025)

    saidas = _salvar(fig, FIGURAS / "fig_comparacoes")
    return saidas, {
        "n_linhas": n, "n_pre_registradas": len(teste), "n_post_hoc": 2,
        "lim_pp": lim, "pontos_fora": fora, "pontos_por_faixa": len(todos),
        "stats_teste": p_test.name, "stats_val": p_val.name,
        "mascara": p_masc.name,
        "ablacoes_teste": [p.name for p in arquivos],
        "classes": {l["rotulo"]: l["classe"] for l in linhas},
    }


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
    # O console do Windows é cp1252: sem isto, imprimir "C→D" derruba o script
    # DEPOIS de as figuras já estarem no disco.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        description="Figuras e tabelas LaTeX de artigo-ACDSA/, a partir dos "
                    "CSV de data/results/.")
    ap.add_argument("--so-tabelas", action="store_true",
                    help="não redesenha as figuras")
    ap.add_argument("--so-figuras", action="store_true",
                    help="não regera as tabelas")
    ap.add_argument("--figura", action="append", metavar="NOME",
                    help="redesenha só esta figura (repetível); implica "
                         "--so-figuras")
    args = ap.parse_args(argv)
    if args.figura:
        args.so_figuras = True

    fontes = selecionar()
    print("fontes escolhidas pelo meta.json:")
    for chave, (p, m) in fontes.items():
        print(f"  {chave:<14} {p.name:<40} split={_splits(m)} "
              f"camada={m.get('ref_camada', '-')} "
              f"variantes={len(m.get('variantes', [])) or '-'}")

    saidas = []
    if not args.so_tabelas:
        todas = (fig_cobertura_acerto, fig_acuracia_segmentacao, fig_pipeline,
                 fig_exemplo, fig_cobertura, fig_comparacoes)
        if args.figura:
            escolhidas = [f for f in todas if f.__name__ in args.figura]
            faltam = set(args.figura) - {f.__name__ for f in escolhidas}
            if faltam:
                raise SystemExit(f"figura desconhecida: {sorted(faltam)}")
        else:
            escolhidas = list(todas)
        for func in escolhidas:
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

    print("\nchecagem de raster e de largura nos PDF:")
    for p in saidas:
        if p.suffix == ".pdf":
            ok, marcas = checar_vetorial(p)
            estado = "vetorial (sem /Subtype /Image, sem /DCTDecode)" \
                if ok else f"RASTER ENCONTRADO: {marcas}"
            larg = largura_pdf(p)
            cabe = "ok" if larg <= LARGURA_POL + 0.02 else "LARGA DEMAIS"
            print(f"  {p.name:<34} {estado}; "
                  f"{num(larg, 2)} pol ({cabe})")


if __name__ == "__main__":
    main()
