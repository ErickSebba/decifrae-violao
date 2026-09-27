"""
tests/test_mascara_comum.py
===========================
Testes da comparação sob máscara comum.

O risco específico aqui é a máscara errada: se `M_C` incluísse células em que C
disse `N`, ou se as duas variantes fossem avaliadas em grades temporais
diferentes, o Δ sairia plausível e sem sentido. Os testes montam casos em que
as máscaras e os acertos são conhecidos à mão.

    pytest tests/test_mascara_comum.py
"""

import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import mascara_comum as mc  # noqa: E402


def test_mascaras_excluem_o_n_de_cada_variante():
    """
    4 s. C rotula os 3 primeiros e diz N no último; D rotula o 1º e o 4º e diz
    N no meio.

      t:      0-1     1-2     2-3     3-4
      ref:    C:maj   C:maj   C:maj   C:maj
      C:      C       G       C       N
      D:      C       N       N       C

      M_C  = {0-1, 1-2, 2-3}      (3 s; onde C não disse N)
      M_CD = {0-1}                (1 s; onde nenhum disse N)

      em M_C : C acerta 2 de 3 s (errou 1-2); D acerta 1 de 3 s (N nos outros)
      em M_CD: C acerta 1 de 1;  D acerta 1 de 1
    """
    ref = [(0.0, 1.0, 'C:maj'), (1.0, 2.0, 'C:maj'),
           (2.0, 3.0, 'C:maj'), (3.0, 4.0, 'C:maj')]
    est_c = [(0.0, 1.0, 'C'), (1.0, 2.0, 'G'), (2.0, 3.0, 'C'), (3.0, 4.0, 'N')]
    est_d = [(0.0, 1.0, 'C'), (1.0, 3.0, 'N'), (3.0, 4.0, 'C')]

    r = mc.medir_faixa(est_c, est_d, ref)

    soma_c, soma_d, peso, total = r["M_C"]
    assert peso == pytest.approx(3.0)
    assert soma_c == pytest.approx(2.0)
    assert soma_d == pytest.approx(1.0)
    assert total == pytest.approx(4.0)

    soma_c, soma_d, peso, _ = r["M_CD"]
    assert peso == pytest.approx(1.0)
    assert soma_c == pytest.approx(1.0)
    assert soma_d == pytest.approx(1.0)


def test_m_cd_e_subconjunto_de_m_c():
    """A interseção nunca pode cobrir mais tempo que o domínio de C."""
    ref = [(0.0, 4.0, 'C:maj')]
    est_c = [(0.0, 3.0, 'C'), (3.0, 4.0, 'N')]
    est_d = [(0.0, 2.0, 'C'), (2.0, 4.0, 'N')]
    r = mc.medir_faixa(est_c, est_d, ref)
    assert r["M_CD"][2] <= r["M_C"][2]
    assert r["M_CD"][2] == pytest.approx(2.0)


def test_sem_n_as_duas_mascaras_coincidem():
    """Quando nenhuma variante abstém, M_C == M_CD == tempo comparável."""
    ref = [(0.0, 2.0, 'C:maj'), (2.0, 4.0, 'A:min')]
    est_c = [(0.0, 2.0, 'C'), (2.0, 4.0, 'Am')]
    est_d = [(0.0, 4.0, 'C')]
    r = mc.medir_faixa(est_c, est_d, ref)
    assert r["M_C"][2] == pytest.approx(r["M_CD"][2])
    assert r["M_C"][2] == pytest.approx(4.0)


def test_as_duas_variantes_sao_avaliadas_na_mesma_grade():
    """
    C e D têm fronteiras diferentes entre si e da referência. Se a fusão não
    juntasse as três, os pesos das duas não somariam o mesmo total.
    """
    ref = [(0.0, 3.0, 'C:maj')]
    est_c = [(0.0, 1.5, 'C'), (1.5, 3.0, 'G')]
    est_d = [(0.0, 1.0, 'C'), (1.0, 3.0, 'C')]
    r = mc.medir_faixa(est_c, est_d, ref)
    # nenhum N: a máscara cobre os 3 s, e C acerta 1,5 e D acerta 3,0
    assert r["M_C"][2] == pytest.approx(3.0)
    assert r["M_C"][0] == pytest.approx(1.5)
    assert r["M_C"][1] == pytest.approx(3.0)


def test_faixa_toda_n_nao_entra_na_agregacao():
    """
    Uma faixa em que C só diz N tem máscara vazia. Contá-la como acerto zero
    inventaria um dado; ela tem de ser descartada.
    """
    por_faixa = {
        "vazia": {"M_C": (0.0, 0.0, 0.0, 4.0), "M_CD": (0.0, 0.0, 0.0, 4.0)},
        "cheia": {"M_C": (3.0, 2.0, 4.0, 4.0), "M_CD": (3.0, 2.0, 4.0, 4.0)},
    }
    linha = mc.agregar(por_faixa, "M_C")
    assert linha["n_faixas"] == 1
    assert linha["acerto_a"] == pytest.approx(0.75)
    assert linha["acerto_b"] == pytest.approx(0.50)
    assert linha["diferenca"] == pytest.approx(-0.25)


def test_peso_da_faixa_e_o_tempo_na_mascara():
    """
    Duas faixas: uma contribui 1 s para a máscara com Δ = +1, outra contribui
    9 s com Δ = 0. A média ponderada tem de dar +0,1, não +0,5.
    """
    por_faixa = {
        "curta": {"M_C": (0.0, 1.0, 1.0, 10.0)},
        "longa": {"M_C": (9.0, 9.0, 9.0, 10.0)},
    }
    linha = mc.agregar(por_faixa, "M_C")
    assert linha["diferenca"] == pytest.approx(0.1)
    assert linha["n_faixas"] == 2


def test_status_post_hoc_esta_nos_campos_do_csv():
    """O CSV precisa carregar o status; o do teste é pós-especificado."""
    assert "status" in mc.CSV_FIELDS
    assert mc.MASCARAS == ("M_C", "M_CD")
    assert mc.VARIANTE_A == "C" and mc.VARIANTE_B == "D"
