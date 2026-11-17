"""
analise_fatorial.py
===================
Revisão camera-ready (R2.3, R2.4): fatorial 2×2×2 e cobertura igualada,
lidos dos CSVs de ablação já gerados pelo `runner.py`. Nenhuma faixa é
decodificada de novo aqui.

FATORIAL. Três fatores binários, oito células:

    decodificador   C (argmax)        vs  D (Viterbi)
    abstenção       ligada (C, D, Crg, Drg)  vs  desligada (C0, D0, C0rg, D0rg)
    gate relativo   ligado (C, C0, D, D0)    vs  desligado (Crg, Drg, C0rg, D0rg)

Métricas: `root` na faixa toda, cobertura (1 − frac_n_est) e `root_rotulado`.

Convenção dos termos (todos calculados POR FAIXA, depois média ponderada pela
duração e bootstrap pareado por faixa, `stats.bootstrap`):

    efeito principal de X   = média, sobre as 4 combinações dos outros dois
                              fatores, de  Y(X alto) − Y(X baixo)
    interação X×Y           = média, sobre o 3º fator, da diferença de
                              diferenças  [efeito de X com Y alto]
                                        − [efeito de X com Y baixo]
    interação X×Y×Z         = [interação X×Y com Z alto] − [com Z baixo]

"Alto" = D / ligada / ligado. Com essa convenção a interação é a mudança no
efeito de um fator quando o outro é ligado (não o coeficiente ±1/2 da
codificação de contrastes).

`root_rotulado` é vazio quando a variante estimou N na faixa inteira: a faixa
sai da conta dessa métrica em TODAS as células (n reportado), para que efeitos
e células sejam medidos no mesmo conjunto de faixas.

COBERTURA IGUALADA. Cmatch vs D e C vs Dmatch, Δ = 2º − 1º, mesmas métricas.

STATUS: pós-especificada (post_review = true). Os CSVs do teste lidos aqui já
estão commitados pela sessão principal.

Saída: data/results/fatorial_<ts>.csv, cobertura_igualada_<ts>.csv (+ _meta),
       artigo-ACDSA/tabelas/tab_fatorial.tex

    python analise_fatorial.py
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
TABELAS = ROOT / "artigo-ACDSA" / "tabelas"

FONTES = {
    ("val", 0): ["ablation_20260927_005629_ref0.csv",
                 "ablation_20261116_231602_ref0.csv"],
    ("test", 0): ["ablation_20260927_014253_ref0.csv",
                  "ablation_20260927_201422_ref0.csv",
                  "ablation_20261116_231650_ref0.csv"],
    ("val", 1): ["ablation_20260927_010621_ref1.csv",
                 "ablation_20261116_231627_ref1.csv"],
    ("test", 1): ["ablation_20260927_014445_ref1.csv",
                  "ablation_20260927_201649_ref1.csv",
                  "ablation_20261116_231706_ref1.csv"],
}

# (decodificador, abstenção, gate relativo) -> variante; 1 = D / ligada / ligado
CELULAS = {
    (0, 1, 1): "C",   (1, 1, 1): "D",
    (0, 0, 1): "C0",  (1, 0, 1): "D0",
    (0, 1, 0): "Crg", (1, 1, 0): "Drg",
    (0, 0, 0): "C0rg", (1, 0, 0): "D0rg",
}
FATORES = ("dec", "abst", "gate")
NOMES_FATOR = {"dec": "decodificador (D − C)",
               "abst": "abstenção (ligada − desligada)",
               "gate": "gate relativo (ligado − desligado)"}
METRICAS = ("root", "cobertura", "root_rotulado")
PARES_MATCH = (("Cmatch", "D"), ("C", "Dmatch"))

CAMPOS_FATORIAL = ["split", "ref_camada", "metrica", "tipo", "termo",
                   "decodificador", "abstencao", "gate_rel", "variante",
                   "n_faixas", "valor", "ic95_min", "ic95_max", "p_bootstrap",
                   "ic_cruza_zero"]
CAMPOS_MATCH = ["split", "ref_camada", "metrica", "variante_a", "variante_b",
                "n_faixas", "media_a", "media_b", "diferenca", "ic95_min",
                "ic95_max", "p_bootstrap", "ic_cruza_zero"]


def _valor(linha, metrica):
    if metrica == "cobertura":
        return 1.0 - float(linha["frac_n_est"])
    v = linha[metrica]
    return float(v) if v != "" else None


def matriz(por_variante, duracoes, variantes, metrica):
    """(valores {variante: array}, pesos, faixas) nas faixas com valor em todas."""
    faixas = sorted(set.intersection(
        *[set(por_variante[v]) for v in variantes]))
    faixas = [t for t in faixas
              if all(_valor(por_variante[v][t], metrica) is not None
                     for v in variantes)]
    valores = {v: np.array([_valor(por_variante[v][t], metrica)
                            for t in faixas]) for v in variantes}
    w = np.array([duracoes[t] for t in faixas])
    return valores, w, faixas


def _media(x, w):
    return float(np.sum(x * w) / np.sum(w))


def termos_fatoriais(Y):
    """
    Y: array (2, 2, 2, n) indexado [dec, abst, gate]. Devolve
    [(tipo, termo, d_por_faixa)].
    """
    saida = []
    for k, f in enumerate(FATORES):
        dif = np.take(Y, 1, axis=k) - np.take(Y, 0, axis=k)   # (2, 2, n)
        saida.append(("efeito", f, dif.mean(axis=(0, 1))))
    for k, l in ((0, 1), (0, 2), (1, 2)):
        dif = np.take(Y, 1, axis=k) - np.take(Y, 0, axis=k)   # sem o eixo k
        l2 = l - 1                                            # eixo l em dif
        dd = np.take(dif, 1, axis=l2) - np.take(dif, 0, axis=l2)  # (2, n)
        saida.append(("interacao", f"{FATORES[k]}×{FATORES[l]}",
                      dd.mean(axis=0)))
    dif = Y[1] - Y[0]                                         # (abst, gate, n)
    dd = dif[:, 1] - dif[:, 0]                                # (abst, n)
    saida.append(("interacao", "dec×abst×gate", dd[1] - dd[0]))
    return saida


def _ic(d, w):
    lo, hi, p = stats.bootstrap(d, w)
    return {"ic95_min": round(lo, 9), "ic95_max": round(hi, 9),
            "p_bootstrap": f"{p:.6g}",
            "ic_cruza_zero": "sim" if lo <= 0 <= hi else "nao"}


def fatorial(por_variante, duracoes, split, camada):
    linhas = []
    for metrica in METRICAS:
        valores, w, faixas = matriz(por_variante, duracoes,
                                    list(CELULAS.values()), metrica)
        Y = np.zeros((2, 2, 2, len(faixas)))
        base = {"split": split, "ref_camada": f"chord[{camada}]",
                "metrica": metrica, "n_faixas": len(faixas)}
        for (a, b, c), v in CELULAS.items():
            Y[a, b, c] = valores[v]
            linhas.append({**base, "tipo": "celula", "termo": v,
                           "decodificador": "D" if a else "C",
                           "abstencao": "ligada" if b else "desligada",
                           "gate_rel": "ligado" if c else "desligado",
                           "variante": v,
                           "valor": round(_media(valores[v], w), 9)})
        for tipo, termo, d in termos_fatoriais(Y):
            linhas.append({**base, "tipo": tipo, "termo": termo,
                           "valor": round(_media(d, w), 9), **_ic(d, w)})
    return linhas


def cobertura_igualada(por_variante, duracoes, split, camada):
    linhas = []
    for a, b in PARES_MATCH:
        for metrica in METRICAS:
            valores, w, faixas = matriz(por_variante, duracoes, [a, b], metrica)
            d = valores[b] - valores[a]
            linhas.append({"split": split, "ref_camada": f"chord[{camada}]",
                           "metrica": metrica, "variante_a": a,
                           "variante_b": b, "n_faixas": len(faixas),
                           "media_a": round(_media(valores[a], w), 9),
                           "media_b": round(_media(valores[b], w), 9),
                           "diferenca": round(_media(d, w), 9),
                           **_ic(d, w)})
    return linhas


# ==========================================================================
# Tabela LaTeX
# ==========================================================================
def _tex_tabela(linhas, ts):
    from figuras_artigo import _tabela, pct, sinal
    tsx = ts.replace("_", r"\_")  # o _ do timestamp quebra o LaTeX

    def achar(split, metrica, tipo, termo):
        for l in linhas:
            if (l["split"], l["ref_camada"], l["metrica"], l["tipo"],
                    l["termo"]) == (split, "chord[0]", metrica, tipo, termo):
                return l
        raise KeyError((split, metrica, tipo, termo))

    colunas_num = [(s, m) for s in ("val", "test") for m in METRICAS]
    cab = ["& & & & \\multicolumn{3}{c}{\\emph{val}} & "
           "\\multicolumn{3}{c}{\\emph{test}} \\\\",
           "\\cmidrule(lr){5-7} \\cmidrule(lr){8-10}",
           "Célula & Dec. & Abst. & Gate & root & Cob. & root rot. & "
           "root & Cob. & root rot. \\\\",
           "\\midrule"]
    corpo = list(cab)
    for (a, b, c), v in CELULAS.items():
        vals = [pct(achar(s, m, "celula", v)["valor"]) for s, m in colunas_num]
        corpo.append(" & ".join([f"\\texttt{{{v}}}", "D" if a else "C",
                                 "sim" if b else "não",
                                 "sim" if c else "não", *vals]) + " \\\\")
    corpo.append("\\midrule")
    rotulos = {"dec": "Decodificador (D$-$C)",
               "abst": "Abstenção (sim$-$não)",
               "gate": "Gate rel. (sim$-$não)",
               "dec×abst": "Dec.$\\times$Abst.",
               "dec×gate": "Dec.$\\times$Gate",
               "abst×gate": "Abst.$\\times$Gate",
               "dec×abst×gate": "Dec.$\\times$Abst.$\\times$Gate"}
    for termo, rot in rotulos.items():
        tipo = "efeito" if "×" not in termo else "interacao"
        ls = [achar(s, m, tipo, termo) for s, m in colunas_num]
        corpo.append(f"\\multicolumn{{4}}{{l}}{{{rot}}} & "
                     + " & ".join(sinal(l["valor"]) for l in ls) + " \\\\")
        corpo.append("\\multicolumn{4}{l}{} & "
                     + " & ".join(f"{{\\scriptsize [{sinal(l['ic95_min'])}; "
                                  f"{sinal(l['ic95_max'])}]}}" for l in ls)
                     + " \\\\")
    n = {s: achar(s, "root_rotulado", "celula", "C")["n_faixas"]
         for s in ("val", "test")}
    n_tot = {s: achar(s, "root", "celula", "C")["n_faixas"]
             for s in ("val", "test")}
    cap = ("Fatorial $2\\times2\\times2$ (decodificador $\\times$ abstenção "
           "própria $\\times$ gate relativo), camada \\texttt{chord[0]}, "
           "valores em \\%. Análise pós-especificada (revisão). "
           f"Fonte: \\texttt{{fatorial\\_{tsx}.csv}}.")
    nota = ("Células: média ponderada pela duração. Efeito principal = média "
            "das 4 diferenças pareadas do fator; interação de 2ª ordem = "
            "variação do efeito do 1º fator quando o 2º é ligado (média sobre "
            "o 3º); 3ª ordem = variação da interação Dec.$\\times$Abst. "
            "quando o gate é ligado. Abaixo de cada efeito, IC 95 \\% do "
            "bootstrap pareado por faixa (10000 reamostragens, semente 0). "
            f"$n$ = {n_tot['val']} (\\emph{{val}}) e {n_tot['test']} "
            "(\\emph{test}) faixas; em \\emph{root rot.}, só as faixas com "
            f"tempo rotulado nas 8 células: $n$ = {n['val']} e {n['test']}.")
    tex = _tabela("table*", "llll" + "r" * 6, corpo, cap, "tab:fatorial",
                  notas=[nota])
    tex = tex.replace("% gerado por figuras_artigo.py",
                      "% gerado por analise_fatorial.py", 1)
    destino = TABELAS / "tab_fatorial.tex"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(tex, encoding="utf-8")
    return destino


# ==========================================================================
def _escrever(nome, campos, linhas, meta, ts):
    caminho = RESULTS / f"{nome}_{ts}.csv"
    with caminho.open("w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=campos)
        w.writeheader()
        w.writerows(linhas)
    (RESULTS / f"{nome}_{ts}_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return caminho


def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fat, match = [], []
    for (split, camada), arquivos in FONTES.items():
        por_variante, duracoes = stats.carregar(
            *[RESULTS / a for a in arquivos])
        fat += fatorial(por_variante, duracoes, split, camada)
        match += cobertura_igualada(por_variante, duracoes, split, camada)

    base_meta = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "gerado_por": "analise_fatorial.py",
        "post_review": True,
        "status": "pós-especificada (revisão camera-ready, R2.3/R2.4)",
        "entradas": {f"{s}/chord[{c}]": a for (s, c), a in FONTES.items()},
        "seed": stats.SEED, "n_bootstrap": stats.N_BOOTSTRAP,
        "alfa": stats.ALFA,
        "pesos": "duracao_s da referência; bootstrap pareado por faixa",
        "cobertura": "1 - frac_n_est",
        "root_rotulado": "faixas com valor vazio em qualquer variante "
                         "envolvida são descartadas (n_faixas)",
        "commit": runner._commit(),
    }
    meta_fat = {**base_meta,
                "celulas": {v: dict(zip(FATORES, k))
                            for k, v in CELULAS.items()},
                "convencao": {
                    "efeito": "média das 4 diferenças pareadas alto − baixo",
                    "interacao_2a": "média sobre o 3º fator de "
                                    "[efeito X | Y alto] − [efeito X | Y baixo]",
                    "interacao_3a": "[interação dec×abst | gate ligado] − "
                                    "[idem | gate desligado]"}}
    meta_match = {**base_meta, "pares": [list(p) for p in PARES_MATCH],
                  "diferenca": "variante_b − variante_a"}
    p1 = _escrever("fatorial", CAMPOS_FATORIAL, fat, meta_fat, ts)
    p2 = _escrever("cobertura_igualada", CAMPOS_MATCH, match, meta_match, ts)
    p3 = _tex_tabela(fat, ts)
    for p in (p1, p2, p3):
        print("escrito", p.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    sys.exit(main())
