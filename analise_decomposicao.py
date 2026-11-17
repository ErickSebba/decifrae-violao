"""
analise_decomposicao.py
=======================
Revisão camera-ready (R2.3, R2.4): de onde vem o Δroot(C → D), e se a máscara
comum de C e D é um subconjunto "fácil" do tempo.

DECOMPOSIÇÃO EXATA. Por faixa, C e D são re-decodificados do cache de
features e alinhados com a referência na MESMA grade do mir_eval
(`_grade4`, a mesma fusão de `mascara_comum._grade`
estendida a D0rg). Cada célula comparável (comparação root >= 0) cai
em uma de quatro regiões:

    ambos   C e D rotularam (nenhum estimou N)
    so_D    só D rotulou (C estimou N)
    so_C    só C rotulou (D estimou N)
    nenhum  os dois estimaram N

O root de uma faixa é Σ comp·dur / W, com W = tempo comparável da faixa (é o
`weighted_accuracy` do mir_eval). Logo

    Δ_t = root_D − root_C = Σ_regiões Σ_{células ∈ r} (comp_D − comp_C)·dur / W

e a parcela agregada da região r é Σ_t w_t·Δ_{t,r} / Σ_t w_t, com w_t =
`duracao_s` do CSV de ablação — a mesma média ponderada da métrica "root na
faixa toda" agregada. As quatro parcelas somam o Δ agregado dos CSVs; o
script confere e grava o resíduo. N estimado conta como erro no root (exceto
contra N na referência, onde o mir_eval o conta como acerto).

VIÉS DE SELEÇÃO. D0rg rotula praticamente tudo. Sua acurácia root dentro da
máscara comum (células rotuladas por C E por D) e fora dela diz se a máscara
seleciona tempo mais fácil. Por faixa: acerto dentro e fora; diferença
pareada dentro − fora (faixas com tempo nas duas partes), peso = duração,
bootstrap pareado por faixa.

STATUS: pós-especificada (post_review = true). Os CSVs do teste já estão
commitados. Decodifica do cache: nenhuma extração de chroma é refeita.

Saída: data/results/decomposicao_<ts>.csv, vies_selecao_<ts>.csv (+ _meta),
       artigo-ACDSA/tabelas/tab_decomposicao.tex

    python analise_decomposicao.py
"""

import csv
import json
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
import mir_eval  # noqa: E402

import cache  # noqa: E402
import dataset_io as ds  # noqa: E402
import runner  # noqa: E402
import stats  # noqa: E402
from evaluate import _to_arrays  # noqa: E402
from mascara_comum import _e_n  # noqa: E402

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "data" / "results"
TABELAS = ROOT / "artigo-ACDSA" / "tabelas"
MANIFEST = "data/manifests/guitarset_comping.csv"
REF_CAMADA = 0
SPLITS = ("val", "test")
REGIOES = ("ambos", "so_D", "so_C", "nenhum")
FONTES = {  # para conferir o Δ agregado e tirar os pesos w_t
    "val": ["ablation_20260927_005629_ref0.csv"],
    "test": ["ablation_20260927_014253_ref0.csv"],
}

CAMPOS_DEC = ["split", "ref_camada", "regiao", "duracao_s", "frac_tempo",
              "n_faixas_contribuem", "acerto_C", "acerto_D", "parcela_delta",
              "ic95_min", "ic95_max", "delta_agregado_csv", "soma_parcelas",
              "residuo", "max_dif_root_por_faixa"]
CAMPOS_VIES = ["split", "ref_camada", "variante", "n_faixas",
               "acerto_dentro", "acerto_fora", "frac_tempo_dentro",
               "n_faixas_par", "dentro_par", "fora_par", "diferenca",
               "ic95_min", "ic95_max", "p_bootstrap", "ic_cruza_zero"]


def _grade4(ref, *ests):
    """
    Referência e várias estimativas na MESMA grade (generaliza
    `mascara_comum._grade` para n estimativas). Partir células não muda as
    somas ponderadas do mir_eval, então o root por faixa é o mesmo.
    """
    ref_int, ref_lab = _to_arrays(ref, translate=False)
    lo, hi = ref_int.min(), ref_int.max()
    inter, rotulos = ref_int, [(l,) for l in ref_lab]
    for est in ests:
        i, l = _to_arrays(est)
        i, l = mir_eval.util.adjust_intervals(
            i, l, lo, hi, mir_eval.chord.NO_CHORD, mir_eval.chord.NO_CHORD)
        inter, ant, novo = mir_eval.util.merge_labeled_intervals(
            inter, rotulos, i, l)
        rotulos = [a + (b,) for a, b in zip(ant, novo)]
    dur = mir_eval.util.intervals_to_durations(inter)
    return dur, [list(c) for c in zip(*rotulos)]


def medir(est_c, est_d, est_0, ref):
    """Por faixa: somas por região e por parte da máscara, e o W."""
    dur, (ref_l, c_l, d_l, o_l) = _grade4(ref, est_c, est_d, est_0)
    comp_c = np.asarray(mir_eval.chord.root(ref_l, c_l), dtype=float)
    comp_d = np.asarray(mir_eval.chord.root(ref_l, d_l), dtype=float)
    comp_o = np.asarray(mir_eval.chord.root(ref_l, o_l), dtype=float)
    valido = comp_c >= 0          # no root, a validade só depende da ref
    lab_c, lab_d = ~_e_n(c_l), ~_e_n(d_l)
    regioes = {"ambos": lab_c & lab_d, "so_D": ~lab_c & lab_d,
               "so_C": lab_c & ~lab_d, "nenhum": ~lab_c & ~lab_d}
    W = float(dur[valido].sum())
    saida = {"W": W,
             "root_C": float((comp_c * dur)[valido].sum()) / W,
             "root_D": float((comp_d * dur)[valido].sum()) / W}
    for r, m in regioes.items():
        m = m & valido
        saida[r] = (float(dur[m].sum()), float((comp_c * dur)[m].sum()),
                    float((comp_d * dur)[m].sum()))
    dentro = regioes["ambos"] & valido
    fora = valido & ~regioes["ambos"]
    saida["vies"] = (float(dur[dentro].sum()),
                     float((comp_o * dur)[dentro].sum()),
                     float(dur[fora].sum()),
                     float((comp_o * dur)[fora].sum()))
    return saida


def rodar(split):
    linhas = runner._linhas(ROOT / MANIFEST, {split})
    vc, vd, v0 = (runner.VARIANTES[n] for n in ("C", "D", "D0rg"))
    assert vc.pre == vd.pre == v0.pre
    por_faixa = {}
    for i, row in enumerate(linhas, start=1):
        ref = ds.load_guitarset(ROOT / row["annotation_path"],
                                index=REF_CAMADA)
        feats = cache.get_features(ROOT / row["audio_path"], vc.pre)
        por_faixa[row["track_id"]] = medir(runner.estimar(vc, feats),
                                           runner.estimar(vd, feats),
                                           runner.estimar(v0, feats), ref)
        sys.stdout.write(f"\r  {split}: {i}/{len(linhas)}")
        sys.stdout.flush()
    print()
    return por_faixa


def decompor(split, por_faixa):
    por_variante, duracoes = stats.carregar(*[RESULTS / a
                                              for a in FONTES[split]])
    faixas = sorted(por_faixa)
    assert set(faixas) == set(por_variante["C"]) == set(por_variante["D"])
    w = np.array([duracoes[t] for t in faixas])
    csv_c = np.array([float(por_variante["C"][t]["root"]) for t in faixas])
    csv_d = np.array([float(por_variante["D"][t]["root"]) for t in faixas])
    delta_csv = float(np.sum((csv_d - csv_c) * w) / np.sum(w))
    max_dif = max(
        np.max(np.abs(csv_c - [por_faixa[t]["root_C"] for t in faixas])),
        np.max(np.abs(csv_d - [por_faixa[t]["root_D"] for t in faixas])))

    tempo_total = sum(sum(por_faixa[t][r][0] for r in REGIOES)
                      for t in faixas)
    linhas, soma = [], 0.0
    for r in REGIOES:
        dr = np.array([por_faixa[t][r][0] for t in faixas])
        sc = np.array([por_faixa[t][r][1] for t in faixas])
        sd = np.array([por_faixa[t][r][2] for t in faixas])
        Wt = np.array([por_faixa[t]["W"] for t in faixas])
        d = (sd - sc) / Wt                       # Δ_{t,r}
        parcela = float(np.sum(d * w) / np.sum(w))
        soma += parcela
        lo, hi, _ = stats.bootstrap(d, w)
        linhas.append({
            "split": split, "ref_camada": f"chord[{REF_CAMADA}]",
            "regiao": r, "duracao_s": round(float(dr.sum()), 3),
            "frac_tempo": round(float(dr.sum()) / tempo_total, 9),
            "n_faixas_contribuem": int(np.sum(dr > 0)),
            "acerto_C": round(float(sc.sum() / dr.sum()), 9)
            if dr.sum() > 0 else "",
            "acerto_D": round(float(sd.sum() / dr.sum()), 9)
            if dr.sum() > 0 else "",
            "parcela_delta": round(parcela, 12),
            "ic95_min": round(lo, 9), "ic95_max": round(hi, 9)})
    for l in linhas:
        l.update({"delta_agregado_csv": round(delta_csv, 12),
                  "soma_parcelas": round(soma, 12),
                  "residuo": f"{soma - delta_csv:.3e}",
                  "max_dif_root_por_faixa": f"{max_dif:.3e}"})
    return linhas, tempo_total, duracoes


def vies(split, por_faixa, duracoes):
    faixas = sorted(por_faixa)
    v = np.array([por_faixa[t]["vies"] for t in faixas])  # dd, sd, df, sf
    w_all = np.array([duracoes[t] for t in faixas])
    ok = (v[:, 0] > 0) & (v[:, 2] > 0)
    acc_in = v[ok, 1] / v[ok, 0]
    acc_out = v[ok, 3] / v[ok, 2]
    w = w_all[ok]
    d = acc_in - acc_out
    lo, hi, p = stats.bootstrap(d, w)
    return {"split": split, "ref_camada": f"chord[{REF_CAMADA}]",
            "variante": "D0rg", "n_faixas": len(faixas),
            "acerto_dentro": round(float(v[:, 1].sum() / v[:, 0].sum()), 9),
            "acerto_fora": round(float(v[:, 3].sum() / v[:, 2].sum()), 9),
            "frac_tempo_dentro": round(float(v[:, 0].sum()
                                             / (v[:, 0].sum() + v[:, 2].sum())), 9),
            "n_faixas_par": int(ok.sum()),
            "dentro_par": round(float(np.sum(acc_in * w) / np.sum(w)), 9),
            "fora_par": round(float(np.sum(acc_out * w) / np.sum(w)), 9),
            "diferenca": round(float(np.sum(d * w) / np.sum(w)), 9),
            "ic95_min": round(lo, 9), "ic95_max": round(hi, 9),
            "p_bootstrap": f"{p:.6g}",
            "ic_cruza_zero": "sim" if lo <= 0 <= hi else "nao"}


# ==========================================================================
def _tex(dec, vs, ts):
    from figuras_artigo import _tabela, num, pct, sinal
    tsx = ts.replace("_", r"\_")  # o _ do timestamp quebra o LaTeX

    nomes = {"ambos": "rotulada por ambos", "so_D": "só por \\texttt{D}",
             "so_C": "só por \\texttt{C}", "nenhum": "por nenhum"}
    corpo = ["Split & Região & Tempo (s) & Tempo (\\%) & Faixas & "
             "root \\texttt{C} & root \\texttt{D} & Parcela de $\\Delta$ "
             "(p.p.) & IC 95 \\% (p.p.) \\\\", "\\midrule"]
    for split in SPLITS:
        ls = [l for l in dec if l["split"] == split]
        for i, l in enumerate(ls):
            corpo.append(" & ".join([
                f"\\emph{{{split}}}" if i == 0 else "", nomes[l["regiao"]],
                num(l["duracao_s"], 1), pct(l["frac_tempo"], 1),
                str(l["n_faixas_contribuem"]),
                pct(l["acerto_C"]) if l["acerto_C"] != "" else "--",
                pct(l["acerto_D"]) if l["acerto_D"] != "" else "--",
                sinal(l["parcela_delta"]),
                f"[{sinal(l['ic95_min'])}; {sinal(l['ic95_max'])}]"]) + " \\\\")
        corpo.append(f" & \\multicolumn{{6}}{{l}}{{Soma = $\\Delta$root "
                     f"agregado (resíduo {float(ls[0]['residuo']):.0e})}} & "
                     f"{sinal(ls[0]['soma_parcelas'])} & \\\\")
        if split != SPLITS[-1]:
            corpo.append("\\midrule")
    v = {l["split"]: l for l in vs}
    nota_vies = "; ".join(
        f"\\emph{{{s}}}: dentro {pct(v[s]['acerto_dentro'])} \\%, fora "
        f"{pct(v[s]['acerto_fora'])} \\% (diferença pareada "
        f"{sinal(v[s]['diferenca'])} p.p., IC [{sinal(v[s]['ic95_min'])}; "
        f"{sinal(v[s]['ic95_max'])}], $n$ = {v[s]['n_faixas_par']})"
        for s in SPLITS)
    cap = ("Decomposição exata de $\\Delta$root (\\texttt{C} $\\to$ "
           "\\texttt{D}), camada \\texttt{chord[0]}, na grade comum do "
           "\\texttt{mir\\_eval}. Análise pós-especificada (revisão). "
           f"Fonte: \\texttt{{decomposicao\\_{tsx}.csv}}.")
    notas = [("Tempo: só células comparáveis no nível root. \\emph{Faixas}: "
              "número de faixas com tempo na região. Acurácia root agregada "
              "por duração dentro da região (N estimado conta como erro). "
              "Parcela: contribuição da região para a média ponderada pela "
              "duração da faixa; IC 95 \\% do bootstrap pareado por faixa "
              "(10000 reamostragens, semente 0)."),
             ("Viés de seleção --- acurácia root de \\texttt{D0rg} dentro e "
              "fora da máscara comum (células rotuladas por \\texttt{C} e por "
              f"\\texttt{{D}}): {nota_vies}. Fonte: "
              f"\\texttt{{vies\\_selecao\\_{tsx}.csv}}.")]
    tex = _tabela("table*", "llrrrrrrr", corpo, cap, "tab:decomposicao",
                  notas=notas)
    tex = tex.replace("% gerado por figuras_artigo.py",
                      "% gerado por analise_decomposicao.py", 1)
    destino = TABELAS / "tab_decomposicao.tex"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(tex, encoding="utf-8")
    return destino


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
    t0 = time.perf_counter()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dec, vs = [], []
    for split in SPLITS:
        por_faixa = rodar(split)
        linhas, _, duracoes = decompor(split, por_faixa)
        dec += linhas
        vs.append(vies(split, por_faixa, duracoes))
    base = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "gerado_por": "analise_decomposicao.py",
        "post_review": True,
        "status": "pós-especificada (revisão camera-ready, R2.3/R2.4)",
        "entradas": {"manifest": MANIFEST,
                     "ablacao_para_pesos_e_conferencia": FONTES,
                     "variantes_decodificadas": ["C", "D", "D0rg"],
                     "features": "cache (cache.get_features); nenhuma "
                                 "extração refeita"},
        "ref_camada": f"chord[{REF_CAMADA}]", "nivel": "root",
        "seed": stats.SEED, "n_bootstrap": stats.N_BOOTSTRAP,
        "alfa": stats.ALFA,
        "segundos": round(time.perf_counter() - t0, 1),
        "commit": runner._commit(),
    }
    m_dec = {**base, "regioes": {
        "ambos": "C e D rotularam", "so_D": "só D rotulou (C = N)",
        "so_C": "só C rotulou (D = N)", "nenhum": "C e D estimaram N"},
        "parcela": "Σ_t w_t Σ_{células∈r}(comp_D − comp_C)·dur / W_t / Σ_t w_t;"
                   " w_t = duracao_s do CSV; W_t = tempo comparável da faixa",
        "residuo": "soma das parcelas − Δ agregado dos CSVs de ablação"}
    m_vies = {**base, "mascara_comum": "células comparáveis em que nem C "
                                       "nem D estimaram N",
              "acerto_dentro/fora": "agregado por duração sobre todas as "
                                    "faixas",
              "diferenca": "média ponderada (duracao_s) de acerto_dentro − "
                           "acerto_fora por faixa, nas faixas com tempo nas "
                           "duas partes (n_faixas_par)"}
    p1 = _escrever("decomposicao", CAMPOS_DEC, dec, m_dec, ts)
    p2 = _escrever("vies_selecao", CAMPOS_VIES, vs, m_vies, ts)
    p3 = _tex(dec, vs, ts)
    for p in (p1, p2, p3):
        print("escrito", p.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    sys.exit(main())
