"""
traduzir_figuras.py
===================
Versões em inglês (`<nome>_en.pdf/.png`) das 10 figuras do projeto cujos
rótulos estão em português. Não altera as figuras originais nem os scripts
que as geram: refaz cada figura com a MESMA função e as MESMAS fontes da
conferência de 2026-11-21 (regeneração idêntica pixel a pixel) e, no
momento de salvar, troca cada texto pelo equivalente em inglês.

- Notas longas embutidas na figura (rodapés explicativos) são REMOVIDAS na
  versão em inglês; a explicação vai para a legenda do LaTeX. Nesses casos a
  figura é salva com recorte justo (bbox_inches="tight").
- Números com vírgula decimal ("57,5") passam a ponto ("57.5").
- Só lê CSVs e o cache de features; não grava nada em data/results/.

    python traduzir_figuras.py
"""

import csv
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.text import Text  # noqa: E402

ROOT = Path(__file__).resolve().parent
FIGURAS = ROOT / "artigo-ACDSA" / "figuras"

NOTA = None   # marcador: texto removido na versão em inglês

EN = {
    "$\\max_k \\ell_i(k)$ por célula (D, 60 templates)":
        "$\\max_k \\ell_i(k)$ per cell (D, 60 templates)",
    "(a) chroma sinc. por batida": "(a) beat-synchronous chroma",
    "(a) root — idêntico nas duas camadas": "(a) root — identical in both layers",
    "(b) majmin — chord[0] cheio, chord[1] vazado":
        "(b) majmin — chord[0] filled, chord[1] open",
    "C (argmax, confidence_gate)": "C (arg-max, confidence_gate)",
    "D (Viterbi MEDIUM, n_logprob)": "D (Viterbi, 60 chords, n_logprob)",
    "F (Viterbi BASIC, n_logprob)": "F (Viterbi, 24 chords, n_logprob)",
    "C→D root_rotulado": "C→D labeled root",
    "GuitarSet teste": "GuitarSet test",
    "N por dúvida": "N when unsure",
    "N por silêncio": "N by silence",
    "RMS por segmento": "RMS per segment",
    "absorção de curtos\n(min_dur)": "short-segment absorption\n(min_dur)",
    "acerto em majmin (%)": "majmin accuracy (%)",
    "acerto em root (%)": "root accuracy (%)",
    "acerto rotulado em majmin (%)": "labeled-time majmin accuracy (%)",
    "acerto rotulado em root (%)": "labeled-time root accuracy (%)",
    "argmax por segmento\nuse_viterbi = False": "per-segment arg-max\nuse_viterbi = False",
    "cobertura (%)": "coverage (%)",
    "cobertura: fração do tempo rotulada (%)": "coverage: fraction of time labeled (%)",
    "confirmado": "supported",
    "curvas: varredura na validação": "curves: validation sweep",
    "densidade": "density",
    "emissão por cosseno": "cosine emission",
    "empate": "unresolved",
    "escolhido no val": "chosen on validation",
    "estado N": "N state",
    "etapa barata — decode": "cheap stage — decode",
    "etapa cara — extract_features (cache em disco)":
        "expensive stage — extract_features (disk cache)",
    "filtro de mediana": "median filter",
    "frágil": "fragile",
    "gate de silêncio": "silence gate",
    "merge de vizinhos iguais": "merge equal neighbors",
    "padrão (2,0)": "default (2.0)",
    "pontos: variantes congeladas, medidas no teste":
        "markers: frozen variants, measured on test",
    "pontos: variantes medidas na validação": "markers: variants measured on validation",
    "root na faixa toda (%)": "whole-track root (%)",
    "root no tempo rotulado (%)": "labeled-time root (%)",
    "seg: qualidade da segmentação (%)": "seg: segmentation quality (%)",
    "sync por batida": "beat sync",
    "tempo (s)": "time (s)",
    "teste: 2,0 → calib.": "test: 2.0 → calib.",
    "teste: Δ e IC 95 %": "test: Δ and 95% CI",
    "validação: Δ e IC 95 %": "validation: Δ and 95% CI",
    "Δ = B − A (pontos percentuais)": "Δ = B − A (percentage points)",
    "Δ = b − a (pontos percentuais), IC 95 %": "Δ = b − a (percentage points), 95% CI",
    "Δ por faixa (teste)": "per-track Δ (test)",
    "-67.9 [-74.5; -58.6]": "−67.9 [−74.5, −58.6]",
}
# notas longas embutidas: identificadas pelo início do texto
NOTAS = ("As curvas param em 99,75 %", "Em vermelho, as três fontes de N",
         "Faixa 03_SS2-88-F_comp", "Só validação. As três curvas",
         "Um par por linha, camada chord[0]")

NUM_VIRGULA = re.compile(r"^([−\-+]?\d+),(\d+)(%?)$")
PORTUGUES = re.compile(r"[áéíóúâêôãõçÁÉÍÓÚÃÕÇ]")


def traduz(s):
    if any(s.startswith(n) for n in NOTAS):
        return NOTA
    if s in EN:
        return EN[s]
    m = NUM_VIRGULA.match(s)
    if m:
        return f"{m.group(1)}.{m.group(2)}{m.group(3)}"
    return s


SOBRAS = set()
_savefig = Figure.savefig


def savefig_en(self, fname, *args, **kwargs):
    nome = Path(str(fname)).stem
    ext = Path(str(fname)).suffix or "." + kwargs.get("format", "png")
    self.canvas.draw()
    removeu = False
    # rótulos de tick: fixa os textos traduzidos (vírgula -> ponto)
    for ax in self.axes:
        for eixo, get_ticks, set_ticks in (
                ("x", ax.get_xticks, ax.set_xticks),
                ("y", ax.get_yticks, ax.set_yticks)):
            rotulos = (ax.get_xticklabels() if eixo == "x"
                       else ax.get_yticklabels())
            textos = [r.get_text() for r in rotulos]
            novos = [traduz(t) or "" for t in textos]
            if novos != textos:
                # set_ticks pode alargar o eixo para ticks fora do intervalo:
                # os limites originais são restaurados
                lim = ax.get_xlim() if eixo == "x" else ax.get_ylim()
                set_ticks(get_ticks(), novos)
                (ax.set_xlim if eixo == "x" else ax.set_ylim)(lim)
    for t in self.findobj(Text):
        s = t.get_text()
        if not s or not s.strip():
            continue
        novo = traduz(s)
        if novo is NOTA:
            t.set_text("")
            t.set_visible(False)
            removeu = True
        elif novo != s:
            t.set_text(novo)
        elif PORTUGUES.search(s):
            SOBRAS.add(s)
    kwargs.pop("format", None)
    # a 2ª chamada (pdf/png) já não encontra a nota: lembra na própria figura
    removeu = removeu or getattr(self, "_en_sem_nota", False)
    self._en_sem_nota = removeu
    if removeu:
        kwargs.setdefault("bbox_inches", "tight")
        kwargs.setdefault("pad_inches", 0.03)
    destino = FIGURAS / f"{nome}_en{ext}"
    _savefig(self, destino, *args, format=ext.lstrip("."), **kwargs)
    print("escrito", destino.relative_to(ROOT).as_posix())


def main():
    Figure.savefig = savefig_en
    import figuras_artigo as fa
    # as figuras do artigo original usam só rodadas pré-revisão
    todos = fa._todos
    fa._todos = lambda p, ac: todos(p, lambda m: ac(m) and not m.get("post_review"))
    fontes = fa.selecionar()
    for f in (fa.fig_cobertura_acerto, fa.fig_acuracia_segmentacao,
              fa.fig_pipeline, fa.fig_exemplo, fa.fig_cobertura,
              fa.fig_comparacoes):
        f(fontes)

    import analise_externo as ae
    import analise_vocabulario as av
    import curvas_teste_revisao as ct
    import diagnostico_n as dn
    trans, _ = ae.transferencia()
    ae.fig_transferencia(trans)
    av.figura(av.transicao(), "20261117_004150")
    with open(ROOT / "data" / "results" / "curvas_teste_20261117_011711.csv",
              encoding="utf-8", newline="") as fp:
        linhas = list(csv.DictReader(fp))
    _, aggC, aggD = ct.comparar(linhas)
    ct.figura(aggC, aggD)

    import cache
    import runner
    v = runner._variantes()
    beta = v["D"].post.n_logprob
    valores = {}
    for chave, _rot, man, split in dn.BASES:
        for row in dn._linhas(man, split):
            feat = cache.get_features(dn.ROOT / row["audio_path"], v["D"].pre)
            for nome, vnome, tira in dn.CASOS:
                m, forc = dn.celulas(feat, v[vnome])
                valores.setdefault((chave, nome), []).append(m[~forc] if tira else m)
    dn.figura(valores, beta)

    if SOBRAS:
        print("TEXTOS EM PORTUGUÊS NÃO TRADUZIDOS:")
        for s in sorted(SOBRAS):
            print("  ", repr(s))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
