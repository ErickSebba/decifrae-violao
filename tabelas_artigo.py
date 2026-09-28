"""
tabelas_artigo.py
=================
Gera duas tabelas LaTeX em `artigo-ACDSA/tabelas/`:

  tab_config.tex   -- os campos de `PreChromaConfig` e `PostChromaConfig`, o
                      estágio em que cada um age, o valor da configuração de
                      produção e os valores que aparecem em alguma execução
                      registrada.
  tab_ablacao.tex  -- as oito variantes do split `test` nas duas camadas de
                      referência, em uma única tabela de duas colunas.

Convenções copiadas de `figuras_artigo.py`: vírgula decimal, `booktabs`,
`\\caption`/`\\label`, `\\footnotesize`, nenhum `\\begin{document}` (os arquivos
são feitos para `\\input`).

Nenhum número é digitado aqui. Os valores das tabelas vêm de:

  - `config.py`, por `dataclasses.fields`, para a coluna de produção;
  - os CSVs de `data/results/`, escolhidos pelo `_meta.json` ao lado
    (`split`/`splits`, `ref_camada`, `variantes`, `n_linhas`), nunca pelo nome.

Uso:

    ./.venv/Scripts/python.exe tabelas_artigo.py

O script não executa nada do pipeline: só lê CSV já gravado.
"""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from dataclasses import fields
from pathlib import Path

from config import PRE_CHROMA, POST_CHROMA, PreChromaConfig, PostChromaConfig

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "data" / "results"
TABELAS = ROOT / "artigo-ACDSA" / "tabelas"

# As oito variantes do teste. A ordem agrupa por mecanismo e deixa cada par
# pré-registrado em linhas vizinhas: V4b/V4 (inércia temporal do baseline),
# C/D (o Viterbi), D/E (a absorção de segmentos curtos), C0rg/D0rg (o Viterbi
# com cobertura igualada).
ORDEM = ["V4", "V4b", "C", "D", "E", "C0rg", "D0rg", "F0rg"]

# Colunas por camada e colunas que não dependem da camada.
POR_CAMADA = ["majmin", "sevenths"]
INVARIANTES = ["root", "root_rotulado", "overseg"]


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


def _splits(m: dict) -> list[str]:
    return m.get("splits") or ([m["split"]] if m.get("split") else [])


def _todos(padrao: str) -> list[tuple[Path, dict]]:
    return [(p, _meta(p)) for p in sorted(RESULTS.glob(padrao))]


def fontes_teste(camada: str) -> list[tuple[Path, dict]]:
    """Todos os CSVs de ablação do split `test` naquela camada de referência.

    O teste foi rodado em duas execuções (seis variantes e depois duas), então
    a tabela precisa das duas; a união é por variante.
    """
    achados = [(p, m) for p, m in _todos("ablation_*.csv")
               if _splits(m) == ["test"] and m.get("ref_camada") == camada]
    if not achados:
        raise SystemExit(f"nenhuma ablação de test em {camada}")
    return achados


def fontes_config() -> list[tuple[Path, dict]]:
    """Toda execução que registra colunas de configuração: ablações e curvas."""
    return _todos("ablation_*.csv") + _todos("curvas_*.csv")


def unir_por_variante(fontes) -> dict[str, list[dict]]:
    """{variante: linhas}, juntando execuções e recusando variante repetida."""
    g: dict[str, list[dict]] = {}
    origem: dict[str, str] = {}
    for p, _m in fontes:
        for v, rs in por_variante(_linhas(p)).items():
            if v in g:
                raise SystemExit(
                    f"variante {v} aparece em {origem[v]} e em {p.name}: "
                    "a união por variante seria ambígua")
            g[v], origem[v] = rs, p.name
    return g


# --------------------------------------------------------------------------- #
# agregação: média ponderada pela duração da faixa
# --------------------------------------------------------------------------- #

def wmean(linhas, coluna) -> float:
    pares = [(float(l[coluna]), float(l["duracao_s"])) for l in linhas
             if l.get(coluna) not in ("", None)]
    peso = sum(d for _, d in pares)
    return sum(v * d for v, d in pares) / peso if peso else float("nan")


def por_variante(linhas) -> dict[str, list[dict]]:
    g = defaultdict(list)
    for l in linhas:
        g[l["variante"]].append(l)
    return dict(g)


# --------------------------------------------------------------------------- #
# formatação de números: duas casas, vírgula decimal
# --------------------------------------------------------------------------- #

def num(v: float, casas: int = 2) -> str:
    if v != v:  # NaN
        return "--"
    return f"{v:.{casas}f}".replace(".", ",")


def pct(v: float, casas: int = 2) -> str:
    return num(v * 100.0, casas)


def tex_escape(s: str) -> str:
    for a, b in (("\\", r"\textbackslash{}"), ("%", r"\%"), ("_", r"\_"),
                 ("&", r"\&"), ("#", r"\#"), ("$", r"\$")):
        s = s.replace(a, b)
    return s


def canonico(texto: str, exemplo):
    """Texto do CSV -> forma canônica, com o tipo do campo de `config.py`.

    Serve para deduplicar: '0.5' e '0.50' são o mesmo valor, e o mesmo campo
    aparece como coluna nas ablações e como par (parametro, valor) nas curvas.
    """
    t = texto.strip()
    if isinstance(exemplo, bool):
        return t == "True"
    if isinstance(exemplo, int):
        return int(float(t))
    if isinstance(exemplo, float):
        return float(t)
    return t


def valor_tex(v) -> str:
    """Um valor de configuração em LaTeX, com vírgula decimal."""
    if isinstance(v, bool):
        return r"\texttt{" + ("True" if v else "False") + "}"
    if isinstance(v, str):
        return r"\texttt{" + tex_escape(v) + "}"
    if isinstance(v, int):
        return str(v)
    if abs(v) >= 1e6:  # o n_logprob de -1e9 usado para desligar o estado N
        e = int(round(math.log10(abs(v))))
        corpo = f"10^{{{e}}}"
        return f"$-{corpo}$" if v < 0 else f"${corpo}$"
    s = repr(float(v))
    return s.replace(".", ",").replace("-", "$-$")


def ordenar(valores) -> list:
    numericos = [v for v in valores if not isinstance(v, str)]
    textos = sorted(v for v in valores if isinstance(v, str))
    return sorted(numericos, key=float) + textos


# --------------------------------------------------------------------------- #
# esqueleto das tabelas
# --------------------------------------------------------------------------- #

def _tabela(env, colunas, corpo, caption, label, notas=(), pequena=True):
    linhas = ["% gerado por tabelas_artigo.py -- não editar à mão",
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


# --------------------------------------------------------------------------- #
# tabela 1: os campos de configuração
# --------------------------------------------------------------------------- #

def _valores_vistos(campos: dict) -> tuple[dict[str, set], list[str]]:
    """Para cada campo, o conjunto de valores presente em alguma execução.

    Duas formas de registro: as ablações trazem uma coluna por campo (vazia
    nas variantes que têm caminho próprio, como V4 e V4b), e o CSV de curvas
    traz o par (parametro, valor).
    """
    vistos: dict[str, set] = {k: set() for k in campos}
    usados = []
    for p, _m in fontes_config():
        linhas = _linhas(p)
        if not linhas:
            continue
        colunas = set(linhas[0])
        usados.append(p.name)
        for l in linhas:
            for k in campos:
                if k in colunas and l.get(k) not in ("", None):
                    vistos[k].add(canonico(l[k], campos[k]))
            if "parametro" in colunas and l["parametro"] in campos:
                k = l["parametro"]
                vistos[k].add(canonico(l["valor"], campos[k]))
    return vistos, usados


def tab_config() -> tuple[Path, list[str], list[str]]:
    campos = {}
    estagio = {}
    for cfg, classe, nome in ((PRE_CHROMA, PreChromaConfig, "pré-chroma"),
                              (POST_CHROMA, PostChromaConfig, "pós-chroma")):
        for f in fields(classe):
            campos[f.name] = getattr(cfg, f.name)
            estagio[f.name] = nome

    vistos, usados = _valores_vistos(campos)
    fixos = []
    corpo = ["Parâmetro & Estágio & Valor & Valores testados \\\\", "\\midrule"]
    for k, producao in campos.items():
        vs = vistos[k]
        if len(vs) <= 1:
            fixos.append(k)
            celula = "fixo"
        else:
            celula = "; ".join(valor_tex(v) for v in ordenar(vs))
        corpo.append(" & ".join([
            f"\\texttt{{{tex_escape(k)}}}",
            estagio[k],
            valor_tex(producao),
            celula]) + " \\\\")

    cap = ("Campos de \\texttt{PreChromaConfig} e \\texttt{PostChromaConfig}. "
           "\\emph{Estágio} distingue os campos que exigem recalcular o chroma "
           "(pré-chroma: HPSS, \\emph{beat track}, CQT) dos que operam sobre o "
           "chroma já sincronizado por batida (pós-chroma: gate de silêncio, "
           "emissão, Viterbi, junção e absorção de segmentos). \\emph{Valor} é "
           "a configuração de produção, lida dos defaults de "
           "\\texttt{config.py}. \\emph{Valores testados} são os valores que "
           "aparecem em alguma execução registrada da ablação ou das curvas; "
           "\\emph{fixo} marca o campo que manteve o mesmo valor em todas "
           "elas.")
    nota = ("Fontes: " + ", ".join(
        "\\texttt{" + tex_escape(n) + "}" for n in usados) + ".")
    # `table*`: a coluna dos valores testados não cabe nas 3,5 pol de uma
    # coluna IEEE quando o campo tem dez ou onze valores registrados.
    tex = _tabela("table*", "llrl", corpo, cap, "tab:config", notas=[nota])
    destino = TABELAS / "tab_config.tex"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(tex, encoding="utf-8")
    return destino, fixos, usados


# --------------------------------------------------------------------------- #
# tabela 2: a ablação no teste, nas duas camadas
# --------------------------------------------------------------------------- #

def tab_ablacao() -> tuple[Path, list[str], list[dict], list[str]]:
    f0, f1 = fontes_teste("chord[0]"), fontes_teste("chord[1]")
    g0, g1 = unir_por_variante(f0), unir_por_variante(f1)

    faltam = [v for v in ORDEM if v not in g0 or v not in g1]
    if faltam:
        raise SystemExit(f"variantes ausentes no teste: {faltam}")
    extras = sorted((set(g0) | set(g1)) - set(ORDEM))
    if extras:
        raise SystemExit(f"variantes no teste fora da ordem declarada: {extras}")

    # Verificação: root, root no tempo rotulado e overseg não dependem da
    # camada de referência (chord[1] muda a qualidade do acorde, não a tônica
    # nem as fronteiras). Se divergirem, a união por variante está errada.
    divergencias = []
    for v in ORDEM:
        for col in INVARIANTES:
            a, b = wmean(g0[v], col), wmean(g1[v], col)
            if not (abs(a - b) <= 1e-9):
                divergencias.append((v, col, a, b))
    if divergencias:
        det = "; ".join(f"{v}/{c}: {a!r} vs {b!r}" for v, c, a, b in divergencias)
        raise SystemExit("root/overseg divergem entre as camadas -- " + det)

    linhas_md = []
    corpo = [
        ("Variante & root & root rot. & Cobertura & "
         "\\multicolumn{2}{c}{majmin} & \\multicolumn{2}{c}{sevenths} & "
         "overseg \\\\"),
        "\\cmidrule(lr){5-6} \\cmidrule(lr){7-8}",
        " & & & & [0] & [1] & [0] & [1] & \\\\",
        "\\midrule",
    ]
    for v in ORDEM:
        rs0, rs1 = g0[v], g1[v]
        cobertura = 1.0 - wmean(rs0, "frac_n_est")
        celulas = [pct(wmean(rs0, "root")), pct(wmean(rs0, "root_rotulado")),
                   pct(cobertura)]
        for n in POR_CAMADA:
            celulas += [pct(wmean(rs0, n)), pct(wmean(rs1, n))]
        celulas.append(pct(wmean(rs0, "overseg")))
        corpo.append(f"\\texttt{{{tex_escape(v)}}} & " + " & ".join(celulas)
                     + " \\\\")
        linhas_md.append({"variante": v, "celulas": celulas})

    n_faixas = len(g0[ORDEM[0]])
    nomes = [p.name for p, _ in f0] + [p.name for p, _ in f1]
    cap = ("Ablação no split \\emph{test}: as oito variantes pré-registradas, "
           "nas duas camadas de referência. Valores em \\%, média ponderada "
           f"pela duração da faixa ($n = {n_faixas}$ faixas). \\emph{{root}} é "
           "o acerto sobre a faixa toda e \\emph{root rot.} o acerto restrito "
           "ao tempo em que o sistema rotulou algo; \\emph{Cobertura} é a "
           "fração do tempo rotulado, $1 -$ \\texttt{frac\\_n\\_est}. As "
           "colunas [0] e [1] são as camadas \\texttt{chord[0]} e "
           "\\texttt{chord[1]}. \\emph{root}, \\emph{root rot.}, "
           "\\emph{Cobertura} e \\emph{overseg} não dependem da camada por "
           "construção: \\texttt{chord[1]} altera a qualidade do acorde, não a "
           "tônica nem as fronteiras. Fontes: " + ", ".join(
               "\\texttt{" + tex_escape(n) + "}" for n in nomes) + ".")
    # `table*`: nove colunas não cabem nas 3,5 pol de uma coluna IEEE.
    tex = _tabela("table*", "l" + "r" * 8, corpo, cap, "tab:ablacao")
    destino = TABELAS / "tab_ablacao.tex"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(tex, encoding="utf-8")
    return destino, nomes, linhas_md, [str(n_faixas)]


def main() -> int:
    p1, fixos, usados = tab_config()
    p2, nomes, linhas_md, extra = tab_ablacao()
    print(f"{p1}  ({p1.stat().st_size} bytes)")
    print(f"  fixo: {', '.join(fixos)}")
    print(f"  fontes: {', '.join(usados)}")
    print(f"{p2}  ({p2.stat().st_size} bytes)")
    print(f"  fontes: {', '.join(nomes)}")
    print(f"  faixas: {extra[0]}")
    print("  root/root_rotulado/overseg idênticos entre chord[0] e chord[1]: ok")
    cols = ["root", "root rot.", "cobertura", "majmin[0]", "majmin[1]",
            "sevenths[0]", "sevenths[1]", "overseg"]
    print("| variante | " + " | ".join(cols) + " |")
    print("|" + "---|" * (len(cols) + 1))
    for r in linhas_md:
        print(f"| {r['variante']} | " + " | ".join(r["celulas"]) + " |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
