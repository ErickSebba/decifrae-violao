"""
analise_vocabulario.py
======================
Análises pós-revisão (R2.5, R2.6) sobre vocabulário e penalidade de transição.
Pós-especificadas: todo `_meta.json` sai com `"post_review": true`.

1. REPRESENTABILIDADE -- por camada (chord[0], chord[1]) e split (val, test),
   que fração do tempo de referência o vocabulário de 24 (maj, min) e o de 60
   (maj, min, 7, maj7, min7) conseguem representar EXATAMENTE.
2. SÉTIMAS -- precisão e revocação das sétimas (7, maj7, min7) de D0rg (60)
   e F0rg (24), ponderadas por tempo na grade comum do mir_eval.
3. TRANSIÇÃO -- curva root × change_penalty da validação (lida do CSV da
   calibração) e Δ no teste entre D0rg/F0rg (cp = 2,0) e D0rg_cal/F0rg_cal,
   com IC bootstrap pareado por faixa.

CONVENÇÕES (decididas antes de olhar os números)
------------------------------------------------
* Qualidade = bitmap de 12 semitons relativo à tônica, de
  `mir_eval.chord.encode(rótulo, reduce_extended_chords=False)` -- a mesma
  codificação que o nível `sevenths` usa. Um rótulo é da classe q se o bitmap
  é IGUAL ao de `mir_eval.chord.QUALITIES[q]`. Extensões dentro da
  oitava que mudam o bitmap (`min6`, `sus4`, `hdim7`, `dim`...) caem em
  "outra". Extensões acima da oitava (9, 11, 13) são DESCARTADAS pelo `encode`
  sem redução -- convenção do mir_eval: `C:maj(9)` conta como maj, `C:9` como 7.
* Inversões (`/x`): o baixo é IGNORADO na classe (C:maj/3 conta como maj),
  como em root/majmin/sevenths do mir_eval (não os níveis `_inv`). O tempo
  com inversão é registrado à parte (`t_inv`).
* N e X: não representáveis (ficam no denominador, fora do numerador) e
  registrados à parte; no GuitarSet são 0 % do tempo.
* Também se registra a validade segundo o próprio mir_eval (`t_valido_majmin`,
  `t_valido_sevenths`): o nível majmin compara só os 8 primeiros semitons, de
  modo que um acorde com sétima conta como maj/min nele -- por isso a
  validade do majmin é MAIOR que a representabilidade estrita do vocab. 24.
* Sétimas: precisão = tempo estimado como q ∈ {7, maj7, min7} em que a
  referência tem a mesma tônica e a mesma classe q / tempo estimado como
  sétima; revocação = tempo de referência da classe q em que o estimado tem
  mesma tônica e mesma classe / tempo de referência com sétima. Agregado por
  soma de tempo sobre as faixas do split (média ponderada pela duração).

Saídas (um timestamp por execução, nada é sobrescrito):

    data/results/representabilidade_<ts>.csv  (+ _meta.json)  uma linha por faixa×camada
    data/results/setimas_<ts>.csv              (+ _meta.json)  uma linha por variante×faixa×camada
    data/results/transicao_<ts>.csv            (+ _meta.json)  curva (val) e Δ do teste
    artigo-ACDSA/tabelas/tab_vocabulario.tex
    artigo-ACDSA/figuras/fig_transicao.pdf + .png

    python analise_vocabulario.py
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

import cache
import dataset_io as ds
import runner
import stats
import figuras_artigo as fa
from config import PRE_CHROMA

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "data" / "results"
MANIFEST = ROOT / "data" / "manifests" / "guitarset_comping.csv"

CAMADAS = (0, 1)
SPLITS = ("val", "test")
Q24 = ("maj", "min")
Q60 = ("maj", "min", "7", "maj7", "min7")
SETIMAS = ("7", "maj7", "min7")
VAR_SETIMAS = ("D0rg", "F0rg")

# Entradas da análise de transição (fixadas pela tarefa R2.6).
CALIB = RESULTS / "calibracao_revisao_20261116_231220.csv"
TESTE = {
    0: {"base": RESULTS / "ablation_20260927_014253_ref0.csv",
        "cal": RESULTS / "ablation_20261116_231650_ref0.csv"},
    1: {"base": RESULTS / "ablation_20260927_014445_ref1.csv",
        "cal": RESULTS / "ablation_20261116_231706_ref1.csv"},
}
PARES_CAL = (("D0rg", "D0rg_cal", "MEDIUM", "cp_D0rg", runner.CP_CAL_MEDIUM),
             ("F0rg", "F0rg_cal", "BASIC", "cp_F0rg", runner.CP_CAL_BASIC))
CP_DEFAULT = 2.0
METRICAS_DELTA = ("root", "majmin", "sevenths")


# ==========================================================================
# Classificação de rótulos
# ==========================================================================
def _bitmaps():
    import mir_eval
    return {q: np.asarray(mir_eval.chord.QUALITIES[q], dtype=int) for q in Q60}


def classes(rotulos):
    """
    Rótulos Harte -> (raiz, classe, N?, X?, inversão?) por rótulo.
    classe ∈ Q60 ou 'outra' (inclui N/X).
    """
    import mir_eval
    bm = _bitmaps()
    raizes, semis, baixos = mir_eval.chord.encode_many(list(rotulos), False)
    cls, eh_n, eh_x = [], [], []
    for lab, r, s in zip(rotulos, raizes, semis):
        n = (r == -1) and not s.any()
        x = str(lab).strip().upper() == "X"
        eh_n.append(n and not x)
        eh_x.append(x)
        c = "outra"
        if not n and not x:
            for q, b in bm.items():
                if np.array_equal(np.asarray(s, dtype=int), b):
                    c = q
                    break
        cls.append(c)
    inv = (np.asarray(baixos) != 0) & ~np.asarray(eh_n) & ~np.asarray(eh_x)
    return (np.asarray(raizes), np.asarray(cls), np.asarray(eh_n),
            np.asarray(eh_x), inv)


# ==========================================================================
# 1. Representabilidade
# ==========================================================================
def representabilidade(linhas_manifest):
    import mir_eval
    saida = []
    for row in linhas_manifest:
        for cam in CAMADAS:
            ref = ds.load_guitarset(ROOT / row["annotation_path"], index=cam)
            dur = np.array([e - s for s, e, _ in ref], dtype=float)
            labs = [l for _, _, l in ref]
            _, cls, n, x, inv = classes(labs)
            vmaj = np.asarray(mir_eval.chord.majmin(labs, labs)) >= 0
            vsev = np.asarray(mir_eval.chord.sevenths(labs, labs)) >= 0
            linha = {"track_id": row["track_id"], "split": row["split"],
                     "ref_camada": f"chord[{cam}]",
                     "duracao_s": round(runner._duracao(ref), 3),
                     "t_total": round(float(dur.sum()), 6),
                     "t_N": round(float(dur[n].sum()), 6),
                     "t_X": round(float(dur[x].sum()), 6)}
            for q in Q60:
                linha[f"t_{q}"] = round(float(dur[cls == q].sum()), 6)
            linha["t_outra"] = round(float(dur[(cls == "outra") & ~n & ~x].sum()), 6)
            linha["t_inv"] = round(float(dur[inv].sum()), 6)
            # N é "válido" para o mir_eval; aqui só interessa o tempo com acorde
            linha["t_valido_majmin"] = round(float(dur[vmaj & ~n & ~x].sum()), 6)
            linha["t_valido_sevenths"] = round(float(dur[vsev & ~n & ~x].sum()), 6)
            saida.append(linha)
    return saida


def resumo_repr(linhas):
    """(camada, split) -> frações agregadas por tempo."""
    g = defaultdict(lambda: defaultdict(float))
    for l in linhas:
        k = (l["ref_camada"], l["split"])
        for c, v in l.items():
            if c.startswith("t_"):
                g[k][c] += float(v)
        g[k]["n"] += 1
    out = {}
    for k, s in g.items():
        T = s["t_total"]
        out[k] = {"n": int(s["n"]), "T_h": T / 3600,
                  "r24": sum(s[f"t_{q}"] for q in Q24) / T,
                  "r60": sum(s[f"t_{q}"] for q in Q60) / T,
                  **{f"f_{q}": s[f"t_{q}"] / T for q in Q60},
                  "f_outra": s["t_outra"] / T, "f_N": s["t_N"] / T,
                  "f_X": s["t_X"] / T, "f_inv": s["t_inv"] / T,
                  "v_majmin": s["t_valido_majmin"] / T,
                  "v_sevenths": s["t_valido_sevenths"] / T}
    return out


# ==========================================================================
# 2. Sétimas
# ==========================================================================
def setimas(linhas_manifest):
    import mir_eval
    saida, checagem = [], []
    for row in linhas_manifest:
        feats = cache.get_features(ROOT / row["audio_path"], PRE_CHROMA)
        ests = {v: runner.estimar(runner.VARIANTES[v], feats) for v in VAR_SETIMAS}
        for cam in CAMADAS:
            ref = ds.load_guitarset(ROOT / row["annotation_path"], index=cam)
            dur_ref = runner._duracao(ref)
            for v, est in ests.items():
                dur, ref_lab, est_lab, _ = runner._grade_comum(est, ref)
                rr, rc, _, _, _ = classes(ref_lab)
                er, ec, _, _, _ = classes(est_lab)
                mesma = (rr == er) & (rc == ec)
                linha = {"variante": v, "vocabulario": runner.VARIANTES[v].vocab,
                         "track_id": row["track_id"], "split": row["split"],
                         "ref_camada": f"chord[{cam}]",
                         "duracao_s": round(dur_ref, 3)}
                for q in SETIMAS:
                    linha[f"est_{q}"] = round(float(dur[ec == q].sum()), 6)
                    linha[f"est_{q}_ok"] = round(float(dur[(ec == q) & mesma].sum()), 6)
                    linha[f"ref_{q}"] = round(float(dur[rc == q].sum()), 6)
                    linha[f"ref_{q}_ok"] = round(float(dur[(rc == q) & mesma].sum()), 6)
                # checagem: o nível sevenths recalculado aqui
                comp = np.asarray(mir_eval.chord.sevenths(ref_lab, est_lab), float)
                ok = comp >= 0
                sev = float((comp[ok] * dur[ok]).sum() / dur[ok].sum()) if dur[ok].sum() else float("nan")
                linha["sevenths"] = round(sev, 9)
                saida.append(linha)
    return saida


def _ic_razao(num, den, n=stats.N_BOOTSTRAP, seed=stats.SEED, alfa=stats.ALFA):
    """
    IC 95 % de sum(num)/sum(den) reamostrando FAIXAS com reposição (a faixa
    viaja com o seu numerador e o seu denominador). Reamostragens com
    denominador zero ficam de fora; devolve (lo, hi, n_validas).
    """
    num, den = np.asarray(num, float), np.asarray(den, float)
    if den.sum() <= 0:
        return float("nan"), float("nan"), 0
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(num), size=(n, len(num)))
    sn, sd = num[idx].sum(axis=1), den[idx].sum(axis=1)
    ok = sd > 0
    r = sn[ok] / sd[ok]
    lo, hi = np.percentile(r, [100 * alfa / 2, 100 * (1 - alfa / 2)])
    return float(lo), float(hi), int(ok.sum())


def resumo_setimas(linhas):
    """(variante, camada, split) -> precisão e revocação, total e por q."""
    g = defaultdict(lambda: defaultdict(float))
    porfaixa = defaultdict(lambda: defaultdict(list))
    for l in linhas:
        k = (l["variante"], l["ref_camada"], l["split"])
        for c, v in l.items():
            if c.startswith(("est_", "ref_")) and c != "ref_camada":
                g[k][c] += float(v)
        pf = porfaixa[k]
        pf["e"].append(sum(float(l[f"est_{q}"]) for q in SETIMAS))
        pf["eok"].append(sum(float(l[f"est_{q}_ok"]) for q in SETIMAS))
        pf["r"].append(sum(float(l[f"ref_{q}"]) for q in SETIMAS))
        pf["rok"].append(sum(float(l[f"ref_{q}_ok"]) for q in SETIMAS))
    out = {}
    for k, s in g.items():
        e = sum(s[f"est_{q}"] for q in SETIMAS)
        eok = sum(s[f"est_{q}_ok"] for q in SETIMAS)
        r = sum(s[f"ref_{q}"] for q in SETIMAS)
        rok = sum(s[f"ref_{q}_ok"] for q in SETIMAS)
        d = {"t_est": e, "t_ref": r,
             "prec": eok / e if e > 0 else float("nan"),
             "rev": rok / r if r > 0 else float("nan")}
        for q in SETIMAS:
            d[f"prec_{q}"] = (s[f"est_{q}_ok"] / s[f"est_{q}"]
                              if s[f"est_{q}"] > 0 else float("nan"))
            d[f"rev_{q}"] = (s[f"ref_{q}_ok"] / s[f"ref_{q}"]
                             if s[f"ref_{q}"] > 0 else float("nan"))
            d[f"t_est_{q}"] = s[f"est_{q}"]
            d[f"t_ref_{q}"] = s[f"ref_{q}"]
        pf = porfaixa[k]
        d["prec_ic_min"], d["prec_ic_max"], d["prec_n_boot"] = _ic_razao(
            pf["eok"], pf["e"])
        d["rev_ic_min"], d["rev_ic_max"], d["rev_n_boot"] = _ic_razao(
            pf["rok"], pf["r"])
        d["n_faixas"] = len(pf["e"])
        out[k] = d
    return out


def checar_setimas(linhas):
    """Diferença máxima entre o sevenths recalculado e o do CSV de teste."""
    difs = []
    for cam in CAMADAS:
        base = {(l["variante"], l["track_id"]): float(l["sevenths"])
                for l in fa._linhas(TESTE[cam]["base"])}
        for l in linhas:
            k = (l["variante"], l["track_id"])
            if l["ref_camada"] == f"chord[{cam}]" and k in base:
                difs.append(abs(float(l["sevenths"]) - base[k]))
    return (max(difs) if difs else float("nan")), len(difs)


# ==========================================================================
# 3. Transição
# ==========================================================================
def _wmean(x, w):
    return float(np.sum(x * w) / np.sum(w))


def transicao():
    calib = fa._linhas(CALIB)
    linhas = []
    for base, cal, vocab, varr, cp_cal in PARES_CAL:
        g = defaultdict(list)
        for l in calib:
            if l["varredura"] == varr:
                g[(l["ref_camada"], float(l["valor"]))].append(l)
        for (cam, cp), ls in sorted(g.items()):
            w = np.array([float(l["duracao_s"]) for l in ls])
            linha = {"tipo": "curva_val", "split": "val", "ref_camada": cam,
                     "vocabulario": vocab, "variante": base,
                     "change_penalty": cp, "n_faixas": len(ls),
                     "default": cp == CP_DEFAULT, "escolhido": cp == cp_cal}
            for m in METRICAS_DELTA:
                linha[m] = round(_wmean(np.array([float(l[m]) for l in ls]), w), 9)
            linhas.append(linha)
    for cam in CAMADAS:
        b = fa.por_variante(fa._linhas(TESTE[cam]["base"]))
        c = fa.por_variante(fa._linhas(TESTE[cam]["cal"]))
        for base, cal, vocab, _, cp_cal in PARES_CAL:
            lb = {l["track_id"]: l for l in b[base]}
            lc = {l["track_id"]: l for l in c[cal]}
            tids = sorted(set(lb) & set(lc))
            assert len(tids) == len(lb) == len(lc), "faixas desalinhadas"
            assert all(lb[t]["split"] == "test" for t in tids)
            w = np.array([float(lb[t]["duracao_s"]) for t in tids])
            for m in METRICAS_DELTA:
                xb = np.array([float(lb[t][m]) for t in tids])
                xc = np.array([float(lc[t][m]) for t in tids])
                d = xc - xb
                lo, hi, p = stats.bootstrap(d, w, n=stats.N_BOOTSTRAP, seed=stats.SEED)
                linhas.append({
                    "tipo": "delta_teste", "split": "test",
                    "ref_camada": f"chord[{cam}]", "vocabulario": vocab,
                    "variante": f"{cal}-{base}", "change_penalty": cp_cal,
                    "n_faixas": len(tids), "metrica": m,
                    "media_base": round(_wmean(xb, w), 9),
                    "media_cal": round(_wmean(xc, w), 9),
                    "delta": round(_wmean(d, w), 9),
                    "ic_min": round(lo, 9), "ic_max": round(hi, 9),
                    "p_bootstrap": round(p, 6)})
    return linhas


# ==========================================================================
# Saída
# ==========================================================================
def _escrever(nome, ts, linhas, entradas, extra=None):
    RESULTS.mkdir(parents=True, exist_ok=True)
    campos = []
    for l in linhas:
        for c in l:
            if c not in campos:
                campos.append(c)
    p = RESULTS / f"{nome}_{ts}.csv"
    if p.exists():
        raise SystemExit(f"{p.name} já existe; CSV de experimento não é sobrescrito")
    with p.open("w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=campos)
        w.writeheader()
        w.writerows(linhas)
    meta = {"gerado_em": datetime.now().isoformat(timespec="seconds"),
            "post_review": True, "script": "analise_vocabulario.py",
            "entradas": [str(Path(e).relative_to(ROOT)).replace("\\", "/")
                         for e in entradas],
            "seed": stats.SEED, "n_bootstrap": stats.N_BOOTSTRAP,
            "n_linhas": len(linhas), "projeto": _PROJETO}
    meta.update(extra or {})
    p.with_name(p.stem + "_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def figura(trans, ts_csv):
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    fa._rc()
    # o bbox "tight" corta a margem branca: 3,77 pol de figura saem ~3,5 pol
    fig, ax = plt.subplots(figsize=(fa.LARGURA_POL + 0.27, 2.5))
    estilo = {"MEDIUM": (fa.COR_FAMILIA["D"], "s", "60 (D0rg)"),
              "BASIC": (fa.COR_FAMILIA["F"], "^", "24 (F0rg)")}
    for base, cal, vocab, _, cp_cal in PARES_CAL:
        cor, mk, rot = estilo[vocab]
        cv = [l for l in trans if l["tipo"] == "curva_val"
              and l["vocabulario"] == vocab and l["ref_camada"] == "chord[0]"]
        x = [l["change_penalty"] for l in cv]
        y = [100 * l["root"] for l in cv]
        ax.plot(x, y, color=cor, marker=mk, ms=4, lw=1.2)
        yc = next(100 * l["root"] for l in cv if l["escolhido"])
        ax.plot([cp_cal], [yc], marker=mk, ms=9, color=cor, mec="black",
                mew=0.8, ls="none", zorder=5)
        dt = [l for l in trans if l["tipo"] == "delta_teste" and l["metrica"] == "root"
              and l["vocabulario"] == vocab and l["ref_camada"] == "chord[0]"][0]
        ax.plot([CP_DEFAULT, cp_cal], [100 * dt["media_base"], 100 * dt["media_cal"]],
                color=cor, marker=mk, ms=5, mfc="white", mew=1.0, ls=":", lw=0.9)
    ax.axvline(CP_DEFAULT, color="0.4", lw=0.8, ls="--", zorder=0)
    ax.set_xlabel("change_penalty")
    ax.set_ylabel("root (%)")
    ax.yaxis.set_major_locator(plt.MultipleLocator(5))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: fa.num(v, 0)))
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: fa.num(v, 1)))
    alca = [Line2D([], [], color=estilo[v][0], marker=estilo[v][1], ms=4, lw=1.2,
                   label=f"{estilo[v][2]}, val") for v in ("MEDIUM", "BASIC")]
    alca += [Line2D([], [], color="0.3", marker="o", ms=5, mfc="white", ls=":",
                    lw=0.9, label="teste: 2,0 → calib."),
             Line2D([], [], color="0.3", marker="o", ms=8, mec="black", ls="none",
                    label="escolhido no val"),
             Line2D([], [], color="0.4", ls="--", lw=0.8, label="padrão (2,0)")]
    ax.legend(handles=alca, loc="upper center", bbox_to_anchor=(0.45, -0.22),
              ncol=2, frameon=False, handlelength=2.0, columnspacing=0.8)
    return fa._salvar(fig, fa.FIGURAS / "fig_transicao")


def tabela(rr, ss, trans, nomes):
    corpo = ["Camada & Split & $n$ & Repr.\\ 24 & Repr.\\ 60 & P 7ª (60) & "
             "R 7ª (60) & R 7ª (24) \\\\", "\\midrule"]
    for cam in CAMADAS:
        c = f"chord[{cam}]"
        for sp in SPLITS:
            r = rr[(c, sp)]
            d = ss[("D0rg", c, sp)]
            f = ss[("F0rg", c, sp)]
            corpo.append(" & ".join([
                f"\\texttt{{{c}}}", sp, str(r["n"]), fa.pct(r["r24"]),
                fa.pct(r["r60"]),
                f"{fa.pct(d['prec'])} [{fa.pct(d['prec_ic_min'])}; "
                f"{fa.pct(d['prec_ic_max'])}]",
                f"{fa.pct(d['rev'])} [{fa.pct(d['rev_ic_min'])}; "
                f"{fa.pct(d['rev_ic_max'])}]",
                fa.pct(f["rev"])]) + " \\\\")
    cap1 = ("Representabilidade e sétimas no GuitarSet. \\emph{Repr.}: fração do "
            "tempo de referência cuja qualidade (bitmap do \\texttt{mir\\_eval}, "
            "baixo ignorado) é exatamente maj/min (24) ou maj/min/7/maj7/min7 (60). "
            "P e R: precisão e revocação de sétima (mesma tônica e mesma qualidade) "
            "de \\texttt{D0rg} (60) e \\texttt{F0rg} (24); \\texttt{F0rg} não emite "
            "sétima, logo sua precisão é indefinida. Valores em \\%, ponderados por "
            "tempo; entre colchetes, IC 95 \\% por bootstrap reamostrando faixas "
            "(10\\,000, semente 0).Fontes: \\texttt{" + fa.tex_escape(nomes["repr"]) + "}, "
            "\\texttt{" + fa.tex_escape(nomes["set"]) + "}.")
    t1 = fa._tabela("table", "llrrrrrr", corpo, cap1, "tab:vocabulario")

    corpo2 = ["Camada & Par & cp & Base & Cal. & $\\Delta$ root [IC 95\\%] \\\\",
              "\\midrule"]
    for cam in CAMADAS:
        for base, cal, vocab, _, cp_cal in PARES_CAL:
            l = [x for x in trans if x["tipo"] == "delta_teste" and x["metrica"] == "root"
                 and x["ref_camada"] == f"chord[{cam}]" and x["vocabulario"] == vocab][0]
            corpo2.append(" & ".join([
                f"\\texttt{{chord[{cam}]}}",
                f"\\texttt{{{fa.tex_escape(cal)}}} vs.\\ \\texttt{{{fa.tex_escape(base)}}}",
                f"{fa.num(cp_cal, 1)} vs.\\ {fa.num(CP_DEFAULT, 1)}",
                fa.pct(l["media_base"]), fa.pct(l["media_cal"]),
                f"{fa.sinal(l['delta'])} [{fa.sinal(l['ic_min'])}; {fa.sinal(l['ic_max'])}]"
            ]) + " \\\\")
    cap2 = ("Sensibilidade à penalidade de transição no split \\emph{test}: "
            "\\texttt{root} (\\%) com o \\texttt{change\\_penalty} congelado (2,0) e "
            "com o calibrado na validação (pós-revisão). $\\Delta$ em pontos "
            "percentuais, média ponderada pela duração; IC bootstrap pareado por "
            "faixa (10\\,000 reamostragens, semente 0). Fonte: \\texttt{"
            + fa.tex_escape(nomes["trans"]) + "}.")
    t2 = fa._tabela("table", "lllrrr", corpo2, cap2, "tab:transicao")
    tex = (t1 + "\n" + t2).replace("gerado por figuras_artigo.py",
                                   "gerado por analise_vocabulario.py")
    destino = fa.TABELAS / "tab_vocabulario.tex"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(tex, encoding="utf-8")
    return destino


def main(argv=None):
    # commit e estado da árvore lidos UMA vez, antes de escrever qualquer
    # saída: senão o primeiro CSV novo suja a árvore para os seguintes
    global _PROJETO
    _PROJETO = runner._commit()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    linhas_manifest = runner._linhas(MANIFEST, set(SPLITS))
    print(f"{len(linhas_manifest)} faixas (val + test, sem excluídas)")

    rep = representabilidade(linhas_manifest)
    p_rep = _escrever("representabilidade", ts, rep, [MANIFEST], {
        "definicao": "classe = bitmap exato de mir_eval.chord.encode (sem reduzir "
                     "extensões); baixo ignorado; N/X fora do numerador",
        "qualidades_24": list(Q24), "qualidades_60": list(Q60)})
    rr = resumo_repr(rep)

    st = setimas(linhas_manifest)
    p_set = _escrever("setimas", ts, st, [MANIFEST], {
        "variantes": list(VAR_SETIMAS), "grade": "runner._grade_comum",
        "definicao": "precisão = t(est q e ref mesma tônica e q)/t(est q); "
                     "revocação = t(ref q e est mesma tônica e q)/t(ref q); q em "
                     "{7, maj7, min7}"})
    ss = resumo_setimas(st)
    resumo = [{"variante": k[0], "ref_camada": k[1], "split": k[2],
               **{c: (round(v, 9) if isinstance(v, float) else v)
                  for c, v in d.items()}}
              for k, d in sorted(ss.items())]
    p_set_res = _escrever("setimas_resumo", ts, resumo, [p_set], {
        "definicao": "prec/rev agregadas por soma de tempo; IC 95 % por "
                     "bootstrap reamostrando faixas (num e den juntos)"})
    dmax, nchk = checar_setimas(st)

    tr = transicao()
    p_tr = _escrever("transicao", ts, tr,
                     [CALIB] + [p for d in TESTE.values() for p in d.values()],
                     {"cp_default": CP_DEFAULT,
                      "cp_calibrado": {"D0rg_cal": runner.CP_CAL_MEDIUM,
                                       "F0rg_cal": runner.CP_CAL_BASIC}})

    figs = figura(tr, ts)
    tex = tabela(rr, ss, tr, {"repr": p_rep.name, "set": p_set.name,
                              "trans": p_tr.name})

    print("\n== representabilidade (%) ==")
    for k in sorted(rr):
        r = rr[k]
        print(f"{k[0]} {k[1]:5s} n={r['n']:3d} r24={100*r['r24']:6.2f} "
              f"r60={100*r['r60']:6.2f} | 7={100*r['f_7']:.2f} maj7={100*r['f_maj7']:.2f} "
              f"min7={100*r['f_min7']:.2f} outra={100*r['f_outra']:.2f} "
              f"N={100*r['f_N']:.2f} X={100*r['f_X']:.2f} inv={100*r['f_inv']:.2f} "
              f"| valido majmin={100*r['v_majmin']:.2f} sevenths={100*r['v_sevenths']:.2f}")
    print("\n== sétimas (%) ==")
    for k in sorted(ss):
        d = ss[k]
        porq = " ".join(f"{q}: P={100*d[f'prec_{q}']:.1f} R={100*d[f'rev_{q}']:.1f}"
                        for q in SETIMAS)
        print(f"{k[0]:5s} {k[1]} {k[2]:5s} P={100*d['prec']:.2f} "
              f"[{100*d['prec_ic_min']:.2f}; {100*d['prec_ic_max']:.2f}] "
              f"R={100*d['rev']:.2f} [{100*d['rev_ic_min']:.2f}; "
              f"{100*d['rev_ic_max']:.2f}] "
              f"t_est={d['t_est']:.0f}s t_ref={d['t_ref']:.0f}s | {porq}")
    print(f"checagem sevenths vs CSV de teste: max|dif|={dmax:.2e} em {nchk} linhas")
    print("\n== transição ==")
    for l in tr:
        if l["tipo"] == "delta_teste":
            print(f"{l['ref_camada']} {l['variante']:14s} {l['metrica']:8s} "
                  f"base={100*l['media_base']:.2f} cal={100*l['media_cal']:.2f} "
                  f"Δ={100*l['delta']:+.2f} [{100*l['ic_min']:+.2f}; {100*l['ic_max']:+.2f}] "
                  f"p={l['p_bootstrap']:.4f}")
    ig = {}
    for l in tr:
        if l["tipo"] == "curva_val":
            ig.setdefault((l["vocabulario"], l["change_penalty"]), []).append(l["root"])
    print("curva root chord[0]==chord[1]:",
          all(abs(v[0] - v[1]) < 1e-12 for v in ig.values() if len(v) == 2))
    print("\nsaídas:", p_rep.name, p_set.name, p_tr.name, tex.name,
          *[f.name for f in figs], "largura pol =", round(fa.largura_pdf(figs[0]), 2))


if __name__ == "__main__":
    sys.exit(main())
