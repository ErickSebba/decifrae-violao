"""
stats.py
========
Comparações pareadas entre variantes, sobre as notas POR FAIXA do split de
validação.

Até aqui a ablação comparava médias ponderadas. Uma diferença de 1,6 ponto
entre D e E pode ser real ou pode ser ruído de 120 faixas -- a média sozinha
não distingue. Este script responde três perguntas por par:

  1. Qual é a diferença média ponderada por duração? (o efeito)
  2. Qual é o intervalo de 95 % dessa diferença? (bootstrap pareado, 10 000
     reamostragens de FAIXAS -- reamostrar faixas, e não segmentos, porque a
     faixa é a unidade independente: dois segmentos da mesma execução do
     mesmo músico não são observações independentes)
  3. A diferença é consistente faixa a faixa? (Wilcoxon pareado, que só olha
     o sinal e a ordem das diferenças -- não a magnitude)

As três respondem coisas diferentes e podem discordar. Um efeito médio grande
com IC cruzando zero significa "poucas faixas dominam o resultado". Um efeito
médio pequeno com Wilcoxon muito significativo significa "quase toda faixa
melhora, mas pouco". Ambos os casos aparecem nos pares abaixo.

Os pares são PRÉ-REGISTRADOS em `docs/CONGELAMENTO.md`: cada um existe para
isolar uma etapa, e as métricas de cada um foram escolhidas antes de olhar os
p-valores. Rodar aqui, na validação, é o ensaio; o teste roda os mesmos pares
uma única vez.

Entrada: o CSV de ablação mais recente do chord[0] (uma linha por variante e
faixa). Saída: data/results/stats_val_<timestamp>.csv + _meta.json

    python stats.py
    python stats.py --csv data/results/ablation_<ts>_ref0.csv
"""

import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy import stats as sps

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "data" / "results"

N_BOOTSTRAP = 10_000
SEED = 0
ALFA = 0.05

# (variante_a, variante_b, [métricas], o que o par isola)
# A diferença reportada é sempre b - a: positivo = b melhor.
PARES = [
    ("C", "D", ["root", "root_rotulado"],
     "o Viterbi na métrica usual"),
    ("C0rg", "D0rg", ["root", "majmin"],
     "o Viterbi com cobertura igualada (nenhuma fonte de N)"),
    ("D", "E", ["root", "seg", "overseg"],
     "o trade-off do min_dur: acurácia contra segmentação"),
    ("V4b", "V4", ["root", "overseg"],
     "a inércia temporal do baseline"),
    ("V4", "F0rg", ["root", "majmin", "seg"],
     "baseline contra a melhor variante"),
    ("D0rg", "F0rg", ["root", "majmin", "sevenths"],
     "o vocabulário (MEDIUM vs BASIC) com cobertura igualada"),
]

CSV_FIELDS = ["par", "variante_a", "variante_b", "metrica", "isola",
              "n_faixas", "n_descartadas",
              "media_a", "media_b", "diferenca", "ic95_min", "ic95_max",
              "ic_cruza_zero", "p_bootstrap", "p_bootstrap_holm",
              "wilcoxon_estatistica", "wilcoxon_p", "wilcoxon_p_holm",
              "classificacao",
              "b_melhor", "b_pior", "empate", "mediana_diferenca"]


# ==========================================================================
# Correção de múltiplas comparações
# ==========================================================================
def holm(ps):
    """
    p-valores ajustados por Holm-Bonferroni.

    Ordena os p crescentes e multiplica o k-ésimo por (n - k), impondo
    monotonicidade (um p ajustado nunca pode ser menor que o de um p bruto
    menor) e teto em 1. Controla a taxa de erro familiar sem supor
    independência entre as comparações -- o que importa aqui, já que as 15
    comparações reusam as mesmas 120 faixas e vários pares compartilham uma
    variante.

    Entradas NaN (comparações sem p, ex.: Wilcoxon de diferença nula) saem
    NaN e NÃO entram na contagem da família: incluí-las inflaria n e tornaria
    a correção mais conservadora do que o declarado.
    """
    ps = np.asarray(ps, dtype=float)
    ajustados = np.full(ps.shape, np.nan)
    validos = np.flatnonzero(~np.isnan(ps))
    if validos.size == 0:
        return ajustados
    n = validos.size
    ordem = validos[np.argsort(ps[validos], kind="stable")]
    corrente = 0.0
    for k, idx in enumerate(ordem):
        corrente = max(corrente, (n - k) * ps[idx])
        ajustados[idx] = min(1.0, corrente)
    return ajustados


def classificar(cruza_zero, p_holm, alfa=ALFA):
    """
    A regra do `docs/CONGELAMENTO.md` §5, aplicada por código e não à mão:

      confirmado : o IC 95 % do bootstrap exclui zero E o p de Holm do
                   bootstrap fica abaixo de alfa;
      empate     : o IC cruza zero (não há efeito distinguível de ruído);
      frágil     : o IC exclui zero mas Holm não rejeita.

    O critério PRINCIPAL é o IC do bootstrap; o Wilcoxon é secundário e não
    entra nesta classificação.
    """
    if cruza_zero:
        return "empate"
    if p_holm == p_holm and p_holm < alfa:
        return "confirmado"
    return "fragil"


# ==========================================================================
# Leitura
# ==========================================================================
def _csv_mais_recente():
    candidatos = sorted(RESULTS.glob("ablation_*_ref0.csv"))
    if not candidatos:
        raise SystemExit("nenhum ablation_*_ref0.csv em data/results/ -- "
                         "rode `python runner.py --manifest ... --ref-layer 0`")
    return candidatos[-1]


def _relativo(caminho):
    """Caminho relativo à raiz quando possível; absoluto quando fora dela."""
    caminho = Path(caminho)
    try:
        return caminho.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return caminho.as_posix()


def _camada_de(csv_path):
    """
    A camada de anotação, lida do NOME do arquivo de entrada.

    Fixar 'chord[0]' aqui gravaria procedência errada ao rodar sobre o CSV do
    chord[1] -- e procedência errada num meta.json é pior que ausente, porque
    parece confiável.
    """
    nome = Path(csv_path).name
    if "_ref1" in nome:
        return "chord[1]"
    if "_ref0" in nome:
        return "chord[0]"
    return "desconhecida"


def _split_de(csv_path):
    """O split, lido das linhas do CSV -- não do nome, que não o carrega."""
    with Path(csv_path).open(encoding="utf-8", newline="") as fp:
        splits = sorted({r.get("split", "") for r in csv.DictReader(fp)})
    return ",".join(s for s in splits if s) or "desconhecido"


def carregar(csv_path):
    """{variante: {track_id: linha}} e a duração de cada faixa."""
    with Path(csv_path).open(encoding="utf-8", newline="") as fp:
        linhas = list(csv.DictReader(fp))
    por_variante = defaultdict(dict)
    duracoes = {}
    for l in linhas:
        por_variante[l["variante"]][l["track_id"]] = l
        duracoes[l["track_id"]] = float(l["duracao_s"])
    return por_variante, duracoes


def _pares_alinhados(por_variante, duracoes, a, b, metrica):
    """
    Arrays alinhados por faixa: (valores_a, valores_b, pesos, n_descartadas).

    Descarta a faixa quando a métrica está vazia em qualquer dos dois lados --
    é o que acontece com `*_rotulado` quando a cobertura é zero. Devolver zero
    no lugar inventaria um dado.
    """
    faltando = [v for v in (a, b) if v not in por_variante]
    if faltando:
        raise KeyError(f"variante(s) ausente(s) no CSV: {faltando}")

    comuns = sorted(set(por_variante[a]) & set(por_variante[b]))
    va, vb, w = [], [], []
    descartadas = 0
    for tid in comuns:
        xa = por_variante[a][tid][metrica]
        xb = por_variante[b][tid][metrica]
        if xa == "" or xb == "":
            descartadas += 1
            continue
        va.append(float(xa))
        vb.append(float(xb))
        w.append(duracoes[tid])
    return (np.array(va), np.array(vb), np.array(w), descartadas)


# ==========================================================================
# Estatística
# ==========================================================================
def _media_ponderada(x, w):
    return float(np.sum(x * w) / np.sum(w)) if np.sum(w) > 0 else float("nan")


def bootstrap(d, w, n=N_BOOTSTRAP, seed=SEED, alfa=ALFA):
    """
    IC e p-valor da diferença média ponderada, por reamostragem PAREADA de
    faixas.

    Cada reamostragem sorteia faixas com reposição e recalcula a média
    ponderada das diferenças -- o par (d_i, w_i) viaja junto, que é o que
    torna o teste pareado. Semente própria por comparação, para que rodar um
    par isolado dê o mesmo número.

    O p-valor é o nível de significância atingido (ASL) da distribuição
    bootstrap: duas vezes a menor das duas caudas em relação a zero, com piso
    em 1/n -- não faz sentido reportar p = 0 a partir de 10 000 reamostragens.
    NÃO é um teste de permutação; é a probabilidade de a reamostragem cair do
    outro lado de zero.

    Devolve (ic_min, ic_max, p).
    """
    if len(d) == 0:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), size=(n, len(d)))
    pesos = w[idx]
    medias = np.sum(d[idx] * pesos, axis=1) / np.sum(pesos, axis=1)
    lo, hi = np.percentile(medias, [100 * alfa / 2, 100 * (1 - alfa / 2)])
    cauda = min(float(np.mean(medias <= 0)), float(np.mean(medias >= 0)))
    p = min(1.0, max(2.0 * cauda, 1.0 / n))
    return float(lo), float(hi), p


def bootstrap_ic(d, w, **kwargs):
    """Só o intervalo, para quem não precisa do p."""
    lo, hi, _ = bootstrap(d, w, **kwargs)
    return lo, hi


def wilcoxon(d):
    """
    Wilcoxon pareado sobre as diferenças por faixa. Não é ponderado: o teste
    é de ranks, e ponderar rank por duração não tem interpretação.

    Devolve (estatística, p) ou (nan, nan) quando não há diferença nenhuma --
    caso em que o scipy levanta, e reportar p=1 seria inventar.
    """
    if len(d) == 0 or np.allclose(d, 0):
        return float("nan"), float("nan")
    try:
        res = sps.wilcoxon(d, zero_method="wilcox", alternative="two-sided")
        return float(res.statistic), float(res.pvalue)
    except ValueError:
        return float("nan"), float("nan")


def comparar(por_variante, duracoes, a, b, metrica, isola):
    va, vb, w, descartadas = _pares_alinhados(por_variante, duracoes, a, b,
                                              metrica)
    d = vb - va
    media_a = _media_ponderada(va, w)
    media_b = _media_ponderada(vb, w)
    diferenca = _media_ponderada(d, w)
    lo, hi, p_boot = bootstrap(d, w)
    est, p = wilcoxon(d)
    tol = 1e-12
    return {
        "par": f"{a} vs {b}",
        "variante_a": a,
        "variante_b": b,
        "metrica": metrica,
        "isola": isola,
        "n_faixas": len(d),
        "n_descartadas": descartadas,
        "media_a": round(media_a, 9),
        "media_b": round(media_b, 9),
        "diferenca": round(diferenca, 9),
        "ic95_min": round(lo, 9),
        "ic95_max": round(hi, 9),
        "ic_cruza_zero": "sim" if (lo <= 0 <= hi) else "nao",
        # os dois p brutos; os ajustados por Holm entram em `rodar`, que é
        # onde a família das 15 comparações fica conhecida
        "p_bootstrap": f"{p_boot:.6g}" if p_boot == p_boot else "",
        "p_bootstrap_holm": "",
        "wilcoxon_estatistica": round(est, 6) if est == est else "",
        "wilcoxon_p": f"{p:.6g}" if p == p else "",
        "wilcoxon_p_holm": "",
        "classificacao": "",
        "_p_boot_bruto": p_boot,
        "_p_wilc_bruto": p,
        "_cruza_zero": bool(lo <= 0 <= hi),
        "b_melhor": int(np.sum(d > tol)),
        "b_pior": int(np.sum(d < -tol)),
        "empate": int(np.sum(np.abs(d) <= tol)),
        "mediana_diferenca": round(float(np.median(d)), 9) if len(d) else "",
    }


def rodar(csv_path):
    """
    Roda as comparações e aplica Holm sobre a família inteira.

    A correção é feita AQUI, e não em `comparar`, porque Holm depende de todos
    os p da família: uma comparação isolada não tem p ajustado.
    """
    por_variante, duracoes = carregar(csv_path)
    linhas, avisos = [], []
    for a, b, metricas, isola in PARES:
        for metrica in metricas:
            try:
                linhas.append(comparar(por_variante, duracoes, a, b, metrica,
                                       isola))
            except KeyError as exc:
                avisos.append(f"{a} vs {b} / {metrica}: {exc}")

    holm_boot = holm([l["_p_boot_bruto"] for l in linhas])
    holm_wilc = holm([l["_p_wilc_bruto"] for l in linhas])
    for l, pb, pw in zip(linhas, holm_boot, holm_wilc):
        l["p_bootstrap_holm"] = f"{pb:.6g}" if pb == pb else ""
        l["wilcoxon_p_holm"] = f"{pw:.6g}" if pw == pw else ""
        l["classificacao"] = classificar(l["_cruza_zero"], pb)
        for chave in ("_p_boot_bruto", "_p_wilc_bruto", "_cruza_zero"):
            l.pop(chave)
    return linhas, avisos


# ==========================================================================
# Saída
# ==========================================================================
def variantes_pre_registradas_ausentes(por_variante):
    """
    Variantes que os pares pré-registrados exigem e que o CSV não tem.

    Existe porque o congelamento saiu inconsistente: a §1 congelou seis
    configurações e a §5 pré-registrou pares que exigem oito. No CSV do teste
    faltam `C0rg` e `V4b`, e com elas quatro das quinze comparações. Isso não
    pode passar em silêncio: uma família de Holm menor dá p-valores menos
    conservadores, e comparar Holm entre splits de famílias diferentes é
    inválido.
    """
    exigidas = {v for a, b, _, _ in PARES for v in (a, b)}
    return sorted(exigidas - set(por_variante))


def imprimir(linhas, csv_path=None, ausentes=()):
    titulo = "Comparações pareadas"
    if csv_path is not None:
        titulo += f" — split {_split_de(csv_path)}, {_camada_de(csv_path)}"
    titulo += ". Diferença = b − a (positivo: b melhor)"
    print("=" * 118)
    print(titulo)
    if ausentes:
        print(f"ATENÇÃO: variantes pré-registradas ausentes do CSV: "
              f"{', '.join(ausentes)}. As comparações que dependem delas NÃO "
              f"foram avaliadas.")
    print("=" * 118)
    cab = (f"{'par':<14} | {'métrica':<14} | {'dif':>7} | {'IC 95 %':>17} | "
           f"{'p boot':>9} | {'Holm boot':>9} | {'Holm Wilc':>9} | "
           f"{'classe':<11} | {'b+/b−/=':>11}")
    print(cab)
    print("-" * len(cab))
    par_anterior = None
    for l in linhas:
        if par_anterior is not None and l["par"] != par_anterior:
            print("-" * len(cab))
        par_anterior = l["par"]
        ic = f"[{l['ic95_min']*100:+.2f}, {l['ic95_max']*100:+.2f}]"
        print(f"{l['par']:<14} | {l['metrica']:<14} | "
              f"{l['diferenca']*100:+6.2f} | {ic:>17} | "
              f"{str(l['p_bootstrap']):>9} | {str(l['p_bootstrap_holm']):>9} | "
              f"{str(l['wilcoxon_p_holm']):>9} | {l['classificacao']:<11} | "
              f"{l['b_melhor']:>3}/{l['b_pior']:>3}/{l['empate']:>3}")
    print("-" * len(cab))
    print("Critério principal: IC 95 % do bootstrap pareado. Wilcoxon é "
          "secundário.")
    print(f"confirmado = IC exclui zero E Holm(boot) < {ALFA};  "
          f"empate = IC cruza zero;  fragil = IC exclui zero mas Holm não "
          f"rejeita.")
    esperadas = sum(len(m) for _, _, m, _ in PARES)
    print(f"Família de Holm: {len(linhas)} comparações"
          + (f" de {esperadas} pré-registradas — os p de Holm NÃO são "
             f"comparáveis com uma família de tamanho diferente."
             if len(linhas) != esperadas else " (a família pré-registrada)"))


def escrever(linhas, meta, timestamp, split="val", camada="chord[0]"):
    """
    O nome carrega o split e a camada. O prefixo era `stats_val_` fixo, o que
    batizava de "val" a saída do teste -- um arquivo que mente no nome é pior
    que um arquivo sem nome.
    """
    RESULTS.mkdir(parents=True, exist_ok=True)
    sufixo_camada = "ref1" if camada == "chord[1]" else "ref0"
    base = f"stats_{split}_{sufixo_camada}_{timestamp}"
    csv_path = RESULTS / f"{base}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(linhas)
    meta_path = RESULTS / f"{base}_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False),
                         encoding="utf-8")
    return csv_path, meta_path


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Comparações pareadas entre variantes no split val.")
    ap.add_argument("--csv", default=None,
                    help="default: o ablation_*_ref0.csv mais recente")
    args = ap.parse_args(argv)

    # `--csv` aceita caminho relativo OU absoluto: resolver contra ROOT antes
    # de usar, senão `relative_to` estoura com a forma relativa que a própria
    # docstring sugere.
    if args.csv:
        csv_path = Path(args.csv)
        if not csv_path.is_absolute():
            csv_path = (ROOT / csv_path).resolve()
    else:
        csv_path = _csv_mais_recente()
    print(f"lendo {_relativo(csv_path)}")

    t0 = time.perf_counter()
    linhas, avisos = rodar(csv_path)
    segundos = time.perf_counter() - t0

    por_variante, _ = carregar(csv_path)
    ausentes = variantes_pre_registradas_ausentes(por_variante)
    imprimir(linhas, csv_path, ausentes)
    for aviso in avisos:
        print(f"AVISO: {aviso}")

    import runner
    import scipy
    meta = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "entrada": csv_path.name,
        "split": _split_de(csv_path),
        "ref_camada": _camada_de(csv_path),
        "n_bootstrap": N_BOOTSTRAP,
        "seed": SEED,
        "alfa": ALFA,
        "unidade_de_reamostragem": "faixa",
        "criterio_principal": "IC 95 % do bootstrap pareado sobre a média "
                              "ponderada por duração",
        "criterio_secundario": "Wilcoxon pareado (complementa, não decide)",
        "correcao_multipla": f"Holm-Bonferroni sobre as {len(linhas)} "
                             f"comparações, famílias separadas para bootstrap "
                             f"e Wilcoxon",
        "p_bootstrap": "nível de significância atingido: 2x a menor cauda da "
                       "distribuição bootstrap em relação a zero, piso 1/n",
        "classificacao": {
            "confirmado": "IC exclui zero E p de Holm (bootstrap) < alfa",
            "empate": "IC cruza zero",
            "fragil": "IC exclui zero mas Holm não rejeita",
        },
        "wilcoxon": "scipy.stats.wilcoxon, two-sided, zero_method=wilcox",
        "pares": [{"a": a, "b": b, "metricas": m, "isola": i}
                  for a, b, m, i in PARES],
        "n_comparacoes": len(linhas),
        "n_comparacoes_pre_registradas": sum(len(m) for _, _, m, _ in PARES),
        "variantes_pre_registradas_ausentes": ausentes,
        "familia_holm_completa": not ausentes,
        "avisos": avisos,
        "segundos": round(segundos, 1),
        "versoes": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "scipy": scipy.__version__,
        },
        "projeto": runner._commit(),
    }
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_out, meta_out = escrever(linhas, meta, timestamp,
                                 split=_split_de(csv_path),
                                 camada=_camada_de(csv_path))
    print(f"\ntempo: {segundos:.1f}s")
    print(f"escrito {_relativo(csv_out)} ({len(linhas)} comparações)")
    print(f"escrito {_relativo(meta_out)}")


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    main()
