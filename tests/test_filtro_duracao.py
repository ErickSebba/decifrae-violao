"""
tests/test_filtro_duracao.py
============================
Casos de borda do filtro de duração mínima (`pipeline._absorb_short`).

Estes testes FIXAM o comportamento atual do código; não o corrigem nem o
julgam. Servem de referência para `artigo-ACDSA/ESPECIFICACAO.md` (item 7) e
para o pseudocódigo de `artigo-ACDSA/tabelas/alg_duracao.tex`.

Regras do código que os testes travam (pipeline.py:170-197):
  - a cada iteração escolhe-se o segmento MAIS CURTO da lista inteira (não há
    varredura da esquerda para a direita); empate -> o mais à esquerda
    (`min` do Python devolve o primeiro mínimo);
  - curto = duração estritamente menor que `min_dur`;
  - o rótulo vem do vizinho MAIS LONGO; empate de duração -> vizinho da
    esquerda (`>=`); na borda da faixa, o único vizinho existente;
  - depois de cada reatribuição faz-se `_merge`, e as durações são
    recalculadas: um segmento que cresceu por absorção pode continuar curto e
    ser absorvido depois (cadeia);
  - para quando o mais curto tem duração >= `min_dur` ou resta um segmento.

Todos os tempos são múltiplos de 1/8 s, exatos em ponto flutuante binário,
para que os empates de duração sejam empates de verdade.

Como rodar (de dentro de `Decifra-Violão/`):

    pytest tests/test_filtro_duracao.py
"""

import os
import sys

# Os módulos do projeto vivem na raiz, em layout plano e sem `__init__.py`;
# o pytest só põe `tests/` no sys.path, então a raiz entra aqui.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from pipeline import _absorb_short  # noqa: E402


def _segs(*triplas):
    """(start, end, label) -> lista de segmentos no formato do pipeline."""
    return [{'start': s, 'end': e, 'label': l} for s, e, l in triplas]


def _triplas(segs):
    return [(s['start'], s['end'], s['label']) for s in segs]


def test_a_segmento_curto_na_borda_da_faixa():
    """(a) Na borda só há um vizinho, que herda o segmento qualquer que seja
    a duração dele. Um segmento com duração EXATAMENTE min_dur não é curto.
    Um segmento único, mesmo curto, sobrevive (o laço exige len > 1)."""
    # borda esquerda: o primeiro segmento vai para o da direita
    out = _absorb_short(_segs((0.0, 0.25, 'N'), (0.25, 2.0, 'G'),
                              (2.0, 4.0, 'C')), min_dur=0.8)
    assert _triplas(out) == [(0.0, 2.0, 'G'), (2.0, 4.0, 'C')]

    # borda direita: o último vai para o da esquerda, mesmo que este seja
    # mais curto que o vizinho do outro lado dele
    out = _absorb_short(_segs((0.0, 3.0, 'A'), (3.0, 4.0, 'D'),
                              (4.0, 4.5, 'N')), min_dur=0.8)
    assert _triplas(out) == [(0.0, 3.0, 'A'), (3.0, 4.5, 'D')]

    # duração == min_dur: mantém (critério é `<`)
    out = _absorb_short(_segs((0.0, 0.75, 'E'), (0.75, 3.0, 'A')),
                        min_dur=0.75)
    assert _triplas(out) == [(0.0, 0.75, 'E'), (0.75, 3.0, 'A')]

    # faixa com um único segmento curto: devolvido intacto
    out = _absorb_short(_segs((0.0, 0.5, 'C')), min_dur=0.8)
    assert _triplas(out) == [(0.0, 0.5, 'C')]


def test_b_vizinhos_iguais():
    """(b) Empate de duração entre os vizinhos -> vence o da ESQUERDA.
    Vizinhos de mesmo rótulo -> os três segmentos fundem num só.
    Dois segmentos curtos de mesma duração -> o mais à esquerda é tratado
    primeiro."""
    # mesma duração dos dois lados (2.0 s e 2.0 s): herda da esquerda
    out = _absorb_short(_segs((0.0, 2.0, 'A'), (2.0, 2.5, 'X'),
                              (2.5, 4.5, 'B')), min_dur=0.8)
    assert _triplas(out) == [(0.0, 2.5, 'A'), (2.5, 4.5, 'B')]

    # mesmo rótulo dos dois lados: o _merge funde A + X + A
    out = _absorb_short(_segs((0.0, 2.0, 'A'), (2.0, 2.5, 'X'),
                              (2.5, 3.0, 'A')), min_dur=0.8)
    assert _triplas(out) == [(0.0, 3.0, 'A')]

    # dois curtos de 0.5 s com vizinhos de 2.0 s: X (à esquerda) é absorvido
    # primeiro, por A; depois Y, por B (empate 2.0 vs 2.0 -> esquerda).
    out = _absorb_short(_segs((0.0, 2.0, 'A'), (2.0, 2.5, 'X'),
                              (2.5, 4.5, 'B'), (4.5, 5.0, 'Y'),
                              (5.0, 7.0, 'C')), min_dur=0.8)
    assert _triplas(out) == [(0.0, 2.5, 'A'), (2.5, 5.0, 'B'),
                             (5.0, 7.0, 'C')]


def test_c_reatribuicao_em_cadeia():
    """(c) O mais curto (Y, 0.25 s) herda de X, o vizinho mais longo mas
    também curto. X+Y (0.75 s) continua curto. Depois Z (0.375 s) vai para B,
    e por fim X+Y (agora entre A=2.0 s e B=2.25 s) vai para B. O trecho que
    era Y termina com o rótulo B, não X -- a reatribuição é repetida até
    estabilizar, com durações recalculadas a cada passo."""
    entrada = _segs((0.0, 2.0, 'A'), (2.0, 2.5, 'X'), (2.5, 2.75, 'Y'),
                    (2.75, 3.125, 'Z'), (3.125, 5.0, 'B'))

    # passo intermediário, reconstituído à mão para documentar a cadeia:
    # depois do 1º passo, X ocupa 2.0-2.75 (0.75 s < 0.8): ainda curto.
    out = _absorb_short(entrada, min_dur=0.8)
    assert _triplas(out) == [(0.0, 2.0, 'A'), (2.0, 5.0, 'B')]

    # com min_dur menor que 0.75, a cadeia para depois de absorver Y e Z:
    # X+Y (0.75 s) já não é curto e mantém o rótulo X.
    out = _absorb_short(entrada, min_dur=0.7)
    assert _triplas(out) == [(0.0, 2.0, 'A'), (2.0, 2.75, 'X'),
                             (2.75, 5.0, 'B')]

    # a entrada não é modificada (o filtro trabalha sobre cópias)
    assert _triplas(entrada)[2] == (2.5, 2.75, 'Y')
