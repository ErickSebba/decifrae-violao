"""
config.py
=========
Lugar único dos hiperparâmetros do pipeline real.

Até aqui os mesmos valores viviam em quatro lugares (constantes no topo de
`musicas.py`, argumentos em `benchmark_musicas.py::run_atual`, defaults de
`pipeline.py`/`classifier.py` e a cópia da API). Este módulo passa a ser a
fonte para os dois primeiros; ver `docs/HIPERPARAMETROS.md` para a tabela
completa e o efeito de cada parâmetro.

A separação em dois grupos é a que os experimentos do artigo precisam:

  PreChromaConfig  — caros. Mudar qualquer um obriga a recalcular HPSS, beat
                     track e CQT. Não podem ser varridos sobre um cache.
  PostChromaConfig — baratos. Operam sobre o chroma já sincronizado por
                     batida, então uma busca pode varrê-los reusando o mesmo
                     chroma extraído uma vez.

Os defaults reproduzem os valores EFETIVOS do pipeline real de hoje: o que
`musicas.py` passa, e o default de `pipeline.py` onde `musicas.py` não passa
nada (`abs_floor`). Atenção a `complexity_penalty`: 0.06 é o valor do pipeline
real, enquanto o default de `CosineChordClassifier` é 0.0 (cosseno puro, usado
pelo bench sintético). Os defaults das funções de `pipeline.py` e
`classifier.py` NÃO foram alterados; este módulo é passado explicitamente pelos
entry points.

Este módulo é folha da árvore de dependências: não importa nada do projeto.
Constantes de domínio (`NO_CHORD`, `NOTE_NAMES`, `CHORD_TYPES`, os
vocabulários) NÃO vivem aqui — continuam em `chord_templates.py`.

Uso típico, incluindo uma variante para experimento:

    from dataclasses import replace
    from config import PRE_CHROMA, POST_CHROMA

    variante = replace(POST_CHROMA, change_penalty=3.0)
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PreChromaConfig:
    """
    Parâmetros da etapa de extração (caros: exigem recalcular o chroma).

    Todos os campos estão ligados em `pipeline.extract_features`, que é quem
    consome esta configuração. Duas ressalvas de escopo:

    - `sr` é usado pelos entry points no `librosa.load`; `extract_features`
      recebe o `sr` do áudio já carregado e não consulta este campo.
    - `classifier.extract_chroma` tem um `bins_per_octave=36` literal próprio.
      É outro caminho (bench sintético e `classify_audio`), não o do pipeline,
      e não foi ligado a esta configuração.
    """

    sr: int = 22050                 # taxa de amostragem do librosa.load
    method: str = "cqt"             # 'cqt' | 'cens' | 'stft'
    smooth: int = 21                # janela do median filter temporal (0/1 desliga)
    hpss_margin: float = 3.0        # margem do HPSS
    bins_per_octave: int = 36       # resolução do CQT, 1/3 de semitom


@dataclass(frozen=True)
class PostChromaConfig:
    """
    Parâmetros da etapa de decisão (baratos: operam sobre o chroma pronto).

    Todos estão efetivamente ligados: `complexity_penalty` e `ext_sharpness`
    vão para `CosineChordClassifier`; os demais, para `analyze_track`.
    """

    complexity_penalty: float = 0.06   # viés pró-tríade (default da classe é 0.0)
    ext_sharpness: float = 4.0         # limiar p/ aceitar a 6ª/7ª como real
    use_viterbi: bool = True           # False = argmax por segmento
    change_penalty: float = 2.0        # custo (log) de trocar de acorde
    temp: float = 0.1                  # temperatura do softmax das emissões
    n_logprob: float = -2.5            # log-prob base do estado N
    rel_gate: float = 0.2              # silêncio = RMS < 20% da mediana da faixa
    abs_floor: float = 5e-4            # piso absoluto de RMS (silêncio digital)
    min_dur: float = 0.8               # absorve segmentos mais curtos que isso


# Instâncias padrão: é o que os entry points usam.
PRE_CHROMA = PreChromaConfig()
POST_CHROMA = PostChromaConfig()
