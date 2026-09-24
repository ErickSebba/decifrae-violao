"""
tests/test_pipeline_split.py
============================
Testes da separação do pipeline em extração (cara) e decisão (barata).

Cobrem três coisas:

1. `extract_features` + `decode` produz EXATAMENTE o mesmo que `analyze_track`
   na faixa sintética do smoke test de `pipeline.py`.
2. `Features.save`/`Features.load` fazem round-trip em .npz sem mudar nada --
   requisito do cache em disco.
3. Os campos pré-chroma que antes eram literais dentro de `beat_sync_chroma`
   (`smooth`, `hpss_margin`, `bins_per_octave`) estão de fato LIGADOS: mudar
   cada um muda o chroma extraído.

Nota sobre o item 3: a asserção é sobre o CHROMA, não sobre os rótulos finais.
Na faixa sintética limpa os três parâmetros mudam o chroma mas não mudam a
decisão (C, G, Am saem iguais nos dois casos), então afirmar diferença de
rótulos aqui seria afirmar algo falso. O chroma é a prova direta de que o
parâmetro chegou ao librosa/scipy.

Estes testes não dependem de `Musicas/` -- só de áudio sintético.

Como rodar (de dentro de `Decifra-Violão/`):

    pytest tests/test_pipeline_split.py
"""

import os
import sys
from dataclasses import replace

import numpy as np
import pytest

# Os módulos do projeto vivem na raiz, em layout plano e sem `__init__.py`;
# o pytest só põe `tests/` no sys.path, então a raiz entra aqui.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pipeline as P  # noqa: E402
from chord_templates import build_templates, MEDIUM  # noqa: E402
from classifier import CosineChordClassifier  # noqa: E402
from config import PRE_CHROMA, POST_CHROMA  # noqa: E402
from synth import synth_chord  # noqa: E402

SR = 22050


@pytest.fixture(scope="module")
def faixa():
    """A mesma faixa sintética do bloco __main__ de pipeline.py: C, G, Am."""
    return np.concatenate([
        synth_chord(0, '', sr=SR, dur=2.0, n_harmonics=6),
        synth_chord(7, '', sr=SR, dur=2.0, n_harmonics=6),
        synth_chord(9, 'm', sr=SR, dur=2.0, n_harmonics=6),
    ])


@pytest.fixture(scope="module")
def clf():
    return CosineChordClassifier(templates=build_templates(MEDIUM))


@pytest.fixture(scope="module")
def features(faixa):
    return P.extract_features(faixa, SR, PRE_CHROMA)


# ==========================================================================
# 1. A composição reproduz analyze_track
# ==========================================================================
def test_composicao_igual_a_analyze_track(faixa, clf, features):
    """extract_features + decode == analyze_track, igualdade exata."""
    composto = P.decode(features, clf, POST_CHROMA)
    monolito = P.analyze_track(faixa, SR, clf)

    assert composto == monolito, (
        f"composição divergiu do monólito:\n"
        f"  extract+decode: {composto}\n"
        f"  analyze_track : {monolito}"
    )
    # A faixa é C(2s) G(2s) Am(2s): guarda contra os dois lados quebrarem
    # juntos e a igualdade passar comparando lixo com lixo.
    assert [s['label'] for s in composto] == ['C', 'G', 'Am']


# ==========================================================================
# 2. Round-trip em .npz
# ==========================================================================
def test_features_roundtrip_npz_preserva_arrays(features, tmp_path):
    """save() seguido de load() devolve os três arrays bit a bit."""
    destino = tmp_path / "features.npz"
    features.save(destino)
    lido = P.Features.load(destino)

    for campo in ('chroma', 'beat_times', 'seg_rms'):
        original, recarregado = getattr(features, campo), getattr(lido, campo)
        assert recarregado.dtype == original.dtype, f"dtype mudou em {campo}"
        assert np.array_equal(recarregado, original), f"valores mudaram em {campo}"


def test_decode_nao_muda_depois_do_roundtrip(features, clf, tmp_path):
    """O resultado do decode é o mesmo com Features vindo do disco."""
    destino = tmp_path / "features.npz"
    features.save(destino)

    antes = P.decode(features, clf, POST_CHROMA)
    depois = P.decode(P.Features.load(destino), clf, POST_CHROMA)

    assert antes == depois


# ==========================================================================
# 3. Os campos pré-chroma estão ligados
# ==========================================================================
@pytest.mark.parametrize("campo,valor", [
    ("smooth", 0),              # desliga o filtro de mediana (default 21)
    ("hpss_margin", 1.0),       # default 3.0
    ("bins_per_octave", 12),    # default 36
])
def test_campo_pre_chroma_muda_o_chroma(faixa, features, campo, valor):
    """
    Mudar o campo muda o chroma extraído -- prova que ele chega ao librosa /
    scipy em vez de ficar inerte na dataclass. Não afirma qual valor é melhor.
    """
    variante = P.extract_features(faixa, SR, replace(PRE_CHROMA, **{campo: valor}))

    assert variante.chroma.shape == features.chroma.shape
    assert not np.array_equal(variante.chroma, features.chroma), (
        f"{campo}={valor} produziu o mesmo chroma do default "
        f"({getattr(PRE_CHROMA, campo)}): o campo não está ligado"
    )


def test_smooth_1_equivale_a_desligado(faixa):
    """
    O filtro só roda com `smooth > 1`, então 0 e 1 significam a mesma coisa.
    Pin da semântica documentada no campo.
    """
    zero = P.extract_features(faixa, SR, replace(PRE_CHROMA, smooth=0))
    um = P.extract_features(faixa, SR, replace(PRE_CHROMA, smooth=1))
    assert np.array_equal(zero.chroma, um.chroma)
