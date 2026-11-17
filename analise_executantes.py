"""
analise_executantes.py
======================
Variação dos contrastes pré-registrados ENTRE EXECUTANTES (resposta ao
revisor R2.1). Análise pós-revisão: não altera nenhum resultado congelado,
só reagrupa as notas por faixa já gravadas nos CSVs de ablação.

Para cada contraste de `stats.PARES` (6 pares, 15 linhas par × métrica),
calcula Δ = b − a como média ponderada pela duração das faixas de CADA
executante (player_id 00–05 do manifesto do GuitarSet). Executantes 00–03
formam o split de desenvolvimento (val); 04–05, o de teste. As faixas
marcadas `excluded=true` no manifesto ficam de fora.

Colunas por contraste:
  - delta_00 … delta_05: Δ médio ponderado por executante (fração, não %);
  - delta_dev / delta_teste: Δ agregado (ponderado) em 00–03 e em 04–05;
  - delta_todos: Δ agregado nos seis executantes juntos;
  - n_mesmo_sinal: quantos dos 6 Δ por executante têm o sinal de delta_todos
    (Δ exatamente zero não conta como mesmo sinal);
  - n_mesmo_sinal_dev: idem, tomando o sinal de delta_dev (a direção vista
    no desenvolvimento, antes do teste);
  - delta_min / delta_max: amplitude dos 6 Δ por executante;
  - ic95_min_XX / ic95_max_XX: IC 95 % do Δ do executante XX, bootstrap
    pareado reamostrando faixas DENTRO do executante (`stats.bootstrap`,
    10 000 reamostragens, seed 0, peso = duração).

Saídas:
  data/results/por_executante_<timestamp>.csv + _meta.json
  artigo-ACDSA/tabelas/tab_executantes.tex  (só chord[0])

    python analise_executantes.py
"""

import csv
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

import stats
from stats import PARES, carregar, _pares_alinhados, _media_ponderada, _relativo

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "data" / "results"
MANIFEST = ROOT / "data" / "manifests" / "guitarset_comping.csv"
TABELAS = ROOT / "artigo-ACDSA" / "tabelas"

EXEC_DEV = ["00", "01", "02", "03"]
EXEC_TESTE = ["04", "05"]
EXECUTANTES = EXEC_DEV + EXEC_TESTE

# Entradas por camada: (CSVs do val, CSVs do teste). O teste está partido em
# dois arquivos (as seis variantes congeladas e as duas do adendo).
ENTRADAS = {
    "chord[0]": (["ablation_20260927_005629_ref0.csv"],
                 ["ablation_20260927_014253_ref0.csv",
                  "ablation_20260927_201422_ref0.csv"]),
    "chord[1]": (["ablation_20260927_010621_ref1.csv"],
                 ["ablation_20260927_014445_ref1.csv",
                  "ablation_20260927_201649_ref1.csv"]),
}

CSV_FIELDS = (["ref_camada", "par", "variante_a", "variante_b", "metrica",
               "isola"]
              + [f"delta_{e}" for e in EXECUTANTES]
              + [f"n_faixas_{e}" for e in EXECUTANTES]
              + ["delta_dev", "delta_teste", "delta_todos",
                 "n_mesmo_sinal", "n_mesmo_sinal_dev", "n_executantes",
                 "delta_min", "delta_max"]
              + [f"ic95_{lado}_{e}" for e in EXECUTANTES
                 for lado in ("min", "max")])


def _executantes():
    """{track_id: player_id} das faixas NÃO excluídas, e o split de cada um."""
    mapa, split_de = {}, {}
    with MANIFEST.open(encoding="utf-8", newline="") as fp:
        for r in csv.DictReader(fp):
            if r["excluded"].strip().lower() == "true":
                continue
            mapa[r["track_id"]] = r["player_id"]
            split_de.setdefault(r["player_id"], set()).add(r["split"])
    # Salvaguarda: a divisão 00–03 = val, 04–05 = test tem de bater com o
    # manifesto; se não bater, o rótulo "teste" da tabela estaria errado.
    for e in EXEC_DEV:
        assert split_de.get(e) == {"val"}, (e, split_de.get(e))
    for e in EXEC_TESTE:
        assert split_de.get(e) == {"test"}, (e, split_de.get(e))
    return mapa


def _uniao(val_paths, test_paths):
    """Junta val e teste num só {variante: {track_id: linha}}."""
    pv_val, dur_val = carregar(*val_paths)
    pv_test, dur_test = carregar(*test_paths)
    por_variante = {}
    for v in set(pv_val) | set(pv_test):
        d = dict(pv_val.get(v, {}))
        sobrepostas = set(d) & set(pv_test.get(v, {}))
        if sobrepostas:
            raise ValueError(f"faixas em val e teste para {v}: {sobrepostas}")
        d.update(pv_test.get(v, {}))
        por_variante[v] = d
    return por_variante, {**dur_val, **dur_test}


def _delta(por_variante, duracoes, a, b, metrica, faixas):
    """Δ = b − a ponderado por duração, restrito ao conjunto `faixas`."""
    sub = {v: {t: l for t, l in por_variante[v].items() if t in faixas}
           for v in (a, b)}
    va, vb, w, _ = _pares_alinhados(sub, duracoes, a, b, metrica)
    if len(w) == 0:
        return float("nan"), 0
    return _media_ponderada(vb - va, w), len(w)


def _ic(por_variante, duracoes, a, b, metrica, faixas):
    """IC 95 % do Δ, bootstrap pareado por faixa só dentro de `faixas`."""
    sub = {v: {t: l for t, l in por_variante[v].items() if t in faixas}
           for v in (a, b)}
    va, vb, w, _ = _pares_alinhados(sub, duracoes, a, b, metrica)
    lo, hi, _ = stats.bootstrap(vb - va, w)
    return lo, hi


def _sinal(x):
    return 0 if (x == 0 or np.isnan(x)) else (1 if x > 0 else -1)


def calcular(camada, mapa):
    val_paths, test_paths = ENTRADAS[camada]
    por_variante, duracoes = _uniao([RESULTS / p for p in val_paths],
                                    [RESULTS / p for p in test_paths])
    faixas_de = {e: {t for t, p in mapa.items() if p == e} for e in EXECUTANTES}
    dev = set().union(*(faixas_de[e] for e in EXEC_DEV))
    teste = set().union(*(faixas_de[e] for e in EXEC_TESTE))
    linhas = []
    for a, b, metricas, isola in PARES:
        for m in metricas:
            linha = {"ref_camada": camada, "par": f"{a} vs {b}",
                     "variante_a": a, "variante_b": b, "metrica": m,
                     "isola": isola}
            ds = []
            for e in EXECUTANTES:
                d, n = _delta(por_variante, duracoes, a, b, m, faixas_de[e])
                linha[f"delta_{e}"] = d
                linha[f"n_faixas_{e}"] = n
                (linha[f"ic95_min_{e}"],
                 linha[f"ic95_max_{e}"]) = _ic(por_variante, duracoes, a, b,
                                               m, faixas_de[e])
                ds.append(d)
            linha["delta_dev"], _ = _delta(por_variante, duracoes, a, b, m, dev)
            linha["delta_teste"], _ = _delta(por_variante, duracoes, a, b, m,
                                             teste)
            linha["delta_todos"], _ = _delta(por_variante, duracoes, a, b, m,
                                             dev | teste)
            validos = [d for d in ds if not np.isnan(d)]
            s_tot, s_dev = _sinal(linha["delta_todos"]), _sinal(linha["delta_dev"])
            linha["n_mesmo_sinal"] = sum(_sinal(d) == s_tot != 0 for d in validos)
            linha["n_mesmo_sinal_dev"] = sum(_sinal(d) == s_dev != 0
                                             for d in validos)
            linha["n_executantes"] = len(validos)
            linha["delta_min"] = min(validos) if validos else float("nan")
            linha["delta_max"] = max(validos) if validos else float("nan")
            linhas.append(linha)
    return linhas


def _pp(x):
    """Fração -> pontos percentuais com 1 casa e sinal explícito (LaTeX)."""
    if np.isnan(x):
        return "--"
    v = round(100 * x, 1)
    if v == 0:
        v = 0.0  # evita "-0.0"
    return f"${v:+.1f}$"


def tabela_tex(linhas, csv_nome):
    # Importado aqui: figuras_artigo puxa matplotlib, desnecessário no cálculo.
    from figuras_artigo import _tabela, tex_escape
    corpo = [
        " & & \\multicolumn{4}{c}{desenvolvimento} & "
        "\\multicolumn{2}{c}{teste} & & & \\\\",
        "\\cmidrule(lr){3-6}\\cmidrule(lr){7-8}",
        "Par ($b-a$) & Métrica & "
        + " & ".join(EXECUTANTES)
        + " & Dev & Teste & Sinal \\\\",
        "\\midrule",
    ]
    par_ant = None
    for l in linhas:
        if l["ref_camada"] != "chord[0]":
            continue
        par = l["par"]
        if par_ant is not None and par != par_ant:
            corpo.append("\\addlinespace")
        rotulo = (f"\\texttt{{{tex_escape(l['variante_a'])}}}$\\to$"
                  f"\\texttt{{{tex_escape(l['variante_b'])}}}"
                  if par != par_ant else "")
        par_ant = par
        corpo.append(" & ".join(
            [rotulo, f"\\texttt{{{tex_escape(l['metrica'])}}}"]
            + [_pp(l[f"delta_{e}"]) for e in EXECUTANTES]
            + [_pp(l["delta_dev"]), _pp(l["delta_teste"]),
               f"{l['n_mesmo_sinal']}/{l['n_executantes']}"]) + " \\\\")
    cap = ("Contrastes pré-registrados por executante do GuitarSet "
           "(camada \\texttt{chord[0]}). Cada célula é $\\Delta = b - a$ em "
           "pontos percentuais, média ponderada pela duração das faixas do "
           "executante. Executantes 00--03 formam o desenvolvimento "
           "(\\emph{val}); 04--05, o \\emph{test}. \\emph{Dev} e "
           "\\emph{Teste} são os $\\Delta$ agregados de cada split; "
           "\\emph{Sinal} conta os executantes cujo $\\Delta$ tem o sinal do "
           "$\\Delta$ agregado nos seis. Análise pós-revisão. Fonte: "
           "\\texttt{" + tex_escape(csv_nome) + "}.")
    tex = _tabela("table*", "ll" + "r" * 9, corpo, cap, "tab:executantes")
    tex = tex.replace("% gerado por figuras_artigo.py",
                      "% gerado por analise_executantes.py", 1)
    tex += "\n" + tabela_ic_tex(linhas, csv_nome)
    destino = TABELAS / "tab_executantes.tex"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(tex, encoding="utf-8")
    return destino


def tabela_ic_tex(linhas, csv_nome):
    """Os 6 contrastes principais (1ª métrica de cada par), Δ e IC 95 %."""
    from figuras_artigo import _tabela, tex_escape
    primeiras = {f"{a} vs {b}": m[0] for a, b, m, _ in PARES}
    corpo = ["Par ($b-a$) & Métrica & "
             + " & ".join(EXECUTANTES[:4] + [f"{e}$^t$" for e in EXEC_TESTE])
             + " \\\\", "\\midrule"]
    for l in linhas:
        if l["ref_camada"] != "chord[0]" or primeiras[l["par"]] != l["metrica"]:
            continue
        celulas = []
        for e in EXECUTANTES:
            d, lo, hi = (l[f"delta_{e}"], l[f"ic95_min_{e}"],
                         l[f"ic95_max_{e}"])
            celulas.append(f"\\shortstack{{{_pp(d)}\\\\"
                           f"\\scriptsize[${100*lo:+.1f}$; ${100*hi:+.1f}$]}}")
        corpo.append(" & ".join(
            [f"\\texttt{{{tex_escape(l['variante_a'])}}}$\\to$"
             f"\\texttt{{{tex_escape(l['variante_b'])}}}",
             f"\\texttt{{{tex_escape(l['metrica'])}}}"] + celulas) + " \\\\")
    cap = ("Os seis contrastes principais por executante, \\texttt{chord[0]}: "
           "$\\Delta = b - a$ em pontos percentuais e IC 95 \\% por bootstrap "
           "pareado reamostrando faixas dentro do executante (10\\,000, seed 0). "
           "$^t$ executantes do teste. Análise pós-revisão. Fonte: "
           "\\texttt{" + tex_escape(csv_nome) + "}.")
    tex = _tabela("table*", "ll" + "c" * 6, corpo, cap, "tab:executantes_ic")
    return tex.replace("% gerado por figuras_artigo.py",
                       "% gerado por analise_executantes.py", 1)


def main():
    import runner  # só para _commit(); importa o pipeline, mas não o executa
    # lido ANTES de escrever qualquer saída: senão o próprio CSV novo suja a árvore
    projeto = runner._commit()
    mapa = _executantes()
    linhas = []
    for camada in ENTRADAS:
        linhas += calcular(camada, mapa)

    esperadas = sum(len(m) for _, _, m, _ in PARES)
    for camada in ENTRADAS:
        n = sum(l["ref_camada"] == camada for l in linhas)
        assert n == esperadas, (camada, n, esperadas)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = RESULTS / f"por_executante_{ts}.csv"
    if csv_path.exists():
        raise SystemExit(f"{csv_path} já existe; não sobrescrevo")
    with csv_path.open("w", encoding="utf-8", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=CSV_FIELDS)
        w.writeheader()
        for l in linhas:
            w.writerow({k: (f"{v:.6f}" if isinstance(v, float) else v)
                        for k, v in l.items()})

    meta = {
        "script": "analise_executantes.py",
        "post_review": True,
        "motivo": "resposta ao revisor R2.1: variação entre executantes",
        "timestamp": ts,
        "entradas": {c: {"val": [_relativo(RESULTS / p) for p in v],
                         "test": [_relativo(RESULTS / p) for p in t]}
                     for c, (v, t) in ENTRADAS.items()},
        "manifesto": _relativo(MANIFEST),
        "exclusoes": "faixas com excluded=true no manifesto",
        "pares": [{"a": a, "b": b, "metricas": m, "isola": i}
                  for a, b, m, i in PARES],
        "definicao_delta": ("delta = b - a; por executante, média de "
                            "(nota_b - nota_a) por faixa ponderada pela "
                            "duracao_s, só nas faixas daquele executante; "
                            "valores em fração (multiplique por 100 para pp)"),
        "definicao_n_mesmo_sinal": ("executantes cujo delta tem o sinal de "
                                    "delta_todos (agregado nos 6); delta == 0 "
                                    "não conta. n_mesmo_sinal_dev usa o sinal "
                                    "de delta_dev"),
        "executantes": {"dev_val": EXEC_DEV, "teste": EXEC_TESTE},
        "saida_tex": _relativo(TABELAS / "tab_executantes.tex"),
        **projeto,
    }
    csv_path.with_name(csv_path.stem + "_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    tex = tabela_tex(linhas, csv_path.name)
    print(f"CSV:  {_relativo(csv_path)}")
    print(f"TEX:  {_relativo(tex)}")
    return csv_path


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
