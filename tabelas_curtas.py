"""
tabelas_curtas.py
=================
Tabelas de uma coluna para o camera-ready (`docs/ADENDO_REVISAO.md` §9.4).
Só lê os CSVs mais recentes de `analise_externo.py`; não calcula métrica.

  artigo-ACDSA/tabelas/tab_principal.tex             GuitarSet teste
  artigo-ACDSA/tabelas/tab_transferencia_curta.tex   6 contrastes × 3 corpora

    python tabelas_curtas.py
"""

import csv
from pathlib import Path

from beat_tracking_idmt import PRINCIPAIS
from figuras_artigo import _tabela, tex_escape

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "data" / "results"
TABELAS = ROOT / "artigo-ACDSA" / "tabelas"

SISTEMAS = ["V4", "V4b", "C", "D", "E", "C0rg", "D0rg", "F0rg",
            "Chordino", "madmom"]
COLS = [("root", "root"), ("root_rotulado", "rot."), ("cobertura", "cob."),
        ("majmin", "mm"), ("sevenths", "7ths"), ("overseg", "overs.")]
BASES = [("gs_test", "GuitarSet"), ("idmt_g", "IDMT-G"), ("idmt_c", "IDMT-C")]
def letra(classe, delta, delta_gs):
    """S/R/U/F, sem pacote LaTeX extra. S e R comparam o sinal com o do
    GuitarSet teste (na própria coluna do GuitarSet, confirmado = S)."""
    if classe == "empate":
        return "U"
    if classe == "fragil":
        return "F"
    return "S" if (delta > 0) == (delta_gs > 0) else "R"


def _ultimo(prefixo):
    ps = sorted(p for p in RESULTS.glob(f"{prefixo}_2*.csv")
                if not p.stem.endswith("_meta"))
    if not ps:
        raise SystemExit(f"sem {prefixo}_*.csv")
    return ps[-1]


def _ler(p):
    with p.open(encoding="utf-8", newline="") as fp:
        return list(csv.DictReader(fp))


def _salvar(nome, tex):
    tex = tex.replace("% gerado por figuras_artigo.py",
                      "% gerado por tabelas_curtas.py", 1)
    (TABELAS / f"{nome}.tex").write_text(tex, encoding="utf-8")


def tab_principal():
    fonte = _ultimo("externo_resumo")
    linhas = {r["sistema"]: r for r in _ler(fonte) if r["base"] == "gs_test"}
    corpo = ["Sistema & " + " & ".join(c for _, c in COLS) + " \\\\", "\\midrule"]
    for s in SISTEMAS:
        if s == "Chordino":
            corpo.append("\\midrule")
        r = linhas[s]
        nome = f"\\texttt{{{tex_escape(s)}}}" if s not in ("Chordino", "madmom") else s
        corpo.append(nome + " & " + " & ".join(
            f"{100 * float(r[m]):.1f}" for m, _ in COLS) + " \\\\")
    cap = ("GuitarSet \\emph{test} (58 faixas): variantes e baselines de "
           "terceiros. Acurácia em \\%, média ponderada pela duração. "
           "\\emph{rot.} = \\texttt{root} no tempo rotulado; \\emph{cob.} = "
           "cobertura; \\emph{mm} e \\emph{7ths} = \\texttt{majmin} e "
           "\\texttt{sevenths} em \\texttt{chord[0]} (as demais colunas são "
           "iguais nas duas camadas).")
    _salvar("tab_principal", _tabela(
        "table", "l" + "r" * len(COLS), corpo, cap, "tab:principal",
        notas=[f"Fonte: \\texttt{{{tex_escape(fonte.name)}}}"]))
    return fonte


def tab_transferencia_curta():
    fonte = _ultimo("transferencia")
    t = {(r["par"], r["metrica"], r["base"]): r for r in _ler(fonte)}
    corpo = ["Contraste & " + " & ".join(
                 f"\\multicolumn{{2}}{{c}}{{{b}}}" for _, b in BASES) + " \\\\",
             "\\cmidrule(lr){2-3}\\cmidrule(lr){4-5}\\cmidrule(lr){6-7}",
             " & " + " & ".join(["$\\Delta$ & "] * len(BASES)) + " \\\\",
             "\\midrule"]
    for a, b, m in PRINCIPAIS:
        cel = []
        for chave, _ in BASES:
            r = t[(f"{a} vs {b}", m, chave)]
            v = 100 * float(r["delta"])
            txt = "$0$" if v == 0 else (f"${v:+.2f}$" if abs(v) < 0.05
                                        else f"${v:+.1f}$")
            ref = float(t[(f"{a} vs {b}", m, "gs_test")]["delta"])
            cel += [txt, letra(r["classificacao"], float(r["delta"]), ref)]
        corpo.append(f"{tex_escape(a)}$\\to${tex_escape(b)} "
                     f"\\texttt{{{tex_escape(m)}}} & " + " & ".join(cel) + " \\\\")
    cap = ("Os seis contrastes principais no GuitarSet \\emph{test} e nas "
           "bases externas (IDMT-SMT-Guitar, 506 faixas; IDMT-SMT-Chords, 6). "
           "$\\Delta = b - a$ em p.p. S: confirmado com o sinal do GuitarSet; "
           "R: confirmado com o sinal invertido; U: IC 95\\% cruza zero; "
           "F: frágil (IC exclui zero, Holm sobre 15 não confirma). "
           "Nenhuma configuração ajustada fora do GuitarSet.")
    _salvar("tab_transferencia_curta", _tabela(
        "table", "l" + "rc" * len(BASES), corpo, cap, "tab:transferencia_curta",
        notas=[f"Fonte: \\texttt{{{tex_escape(fonte.name)}}}"]))
    return fonte


if __name__ == "__main__":
    print("tab_principal <-", tab_principal().name)
    print("tab_transferencia_curta <-", tab_transferencia_curta().name)
