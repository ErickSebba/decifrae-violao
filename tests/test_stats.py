"""
tests/test_stats.py
===================
Testes das comparações pareadas.

O risco aqui é um número com aparência de rigor. Um IC que na verdade não é
pareado, um Wilcoxon rodando sobre a lista errada ou um bootstrap que
reamostra segmentos em vez de faixas produzem p-valores plausíveis e errados,
e ninguém confere um p-valor à mão.

Os testes atacam isso por três frentes: casos com resposta conhecida
analiticamente, propriedades que a estatística tem de obedecer (antissimetria,
reprodutibilidade pela semente) e a recusa em inventar dado quando não há.

    pytest tests/test_stats.py
"""

import csv
import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import congelar  # noqa: E402
import stats  # noqa: E402


# ==========================================================================
# Fixture: um CSV de ablação minúsculo com resposta conhecida
# ==========================================================================
@pytest.fixture
def csv_pequeno(tmp_path):
    """
    Duas variantes, 4 faixas. A ganha em 1, B ganha em 3, e as durações são
    desiguais de propósito: a média ponderada e a simples divergem.

      faixa  dur   A     B     d = B-A
      t1     10    0.50  0.60  +0.10
      t2     10    0.50  0.70  +0.20
      t3     10    0.80  0.40  -0.40
      t4     70    0.50  0.60  +0.10

      média ponderada de d = (0.10*10 + 0.20*10 - 0.40*10 + 0.10*70)/100
                           = (1 + 2 - 4 + 7)/100 = +0.06
      média simples        = 0.00
    """
    caminho = tmp_path / "ablation_teste_ref0.csv"
    campos = ["variante", "track_id", "duracao_s", "root", "majmin",
              "root_rotulado"]
    dados = [
        ("A", "t1", 10, 0.50), ("A", "t2", 10, 0.50),
        ("A", "t3", 10, 0.80), ("A", "t4", 70, 0.50),
        ("B", "t1", 10, 0.60), ("B", "t2", 10, 0.70),
        ("B", "t3", 10, 0.40), ("B", "t4", 70, 0.60),
    ]
    with caminho.open("w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=campos)
        w.writeheader()
        for var, tid, dur, root in dados:
            w.writerow({"variante": var, "track_id": tid, "duracao_s": dur,
                        "root": root, "majmin": root, "root_rotulado": root})
    return caminho


# ==========================================================================
# A diferença é ponderada pela duração
# ==========================================================================
def test_diferenca_e_ponderada_nao_simples(csv_pequeno):
    por_variante, duracoes = stats.carregar(csv_pequeno)
    r = stats.comparar(por_variante, duracoes, "A", "B", "root", "teste")

    assert r["diferenca"] == pytest.approx(0.06), (
        "a diferença não está ponderada pela duração (média simples = 0)")
    assert r["media_a"] == pytest.approx((0.5*10 + 0.5*10 + 0.8*10 + 0.5*70)/100)
    assert r["mediana_diferenca"] == pytest.approx(0.10)


def test_contagem_de_faixas(csv_pequeno):
    por_variante, duracoes = stats.carregar(csv_pequeno)
    r = stats.comparar(por_variante, duracoes, "A", "B", "root", "teste")
    assert (r["b_melhor"], r["b_pior"], r["empate"]) == (3, 1, 0)
    assert r["n_faixas"] == 4
    assert r["n_descartadas"] == 0


def test_inverter_o_par_inverte_o_sinal(csv_pequeno):
    """Antissimetria: comparar(A,B) = -comparar(B,A) em tudo que é diferença."""
    por_variante, duracoes = stats.carregar(csv_pequeno)
    ab = stats.comparar(por_variante, duracoes, "A", "B", "root", "t")
    ba = stats.comparar(por_variante, duracoes, "B", "A", "root", "t")

    assert ab["diferenca"] == pytest.approx(-ba["diferenca"])
    assert ab["ic95_min"] == pytest.approx(-ba["ic95_max"])
    assert ab["ic95_max"] == pytest.approx(-ba["ic95_min"])
    assert (ab["b_melhor"], ab["b_pior"]) == (ba["b_pior"], ba["b_melhor"])
    assert ab["wilcoxon_p"] == ba["wilcoxon_p"]


# ==========================================================================
# O bootstrap
# ==========================================================================
def test_bootstrap_e_reprodutivel_pela_semente():
    """
    Mesma semente, mesmo IC — é o que torna o número do artigo reproduzível.
    A amostra é grande de propósito: com 4 ou 5 faixas a distribuição do
    bootstrap é tão grossa que os percentis coincidem entre sementes, e o
    teste não distinguiria reprodutibilidade de degenerescência.
    """
    rng = np.random.default_rng(11)
    d = rng.normal(0.03, 0.05, size=80)
    w = rng.uniform(5, 40, size=80)

    assert stats.bootstrap_ic(d, w) == stats.bootstrap_ic(d, w)
    assert stats.bootstrap_ic(d, w, seed=0) == stats.bootstrap_ic(d, w, seed=0)
    assert stats.bootstrap_ic(d, w, seed=0) != stats.bootstrap_ic(d, w, seed=1)


def test_bootstrap_contem_a_estimativa_pontual():
    rng = np.random.default_rng(3)
    d = rng.normal(0.05, 0.02, size=60)
    w = rng.uniform(5, 40, size=60)
    ponto = float(np.sum(d * w) / np.sum(w))
    lo, hi = stats.bootstrap_ic(d, w)
    assert lo < ponto < hi


def test_bootstrap_de_diferenca_constante_nao_tem_largura():
    """Se toda faixa melhora exatamente 0.1, não há incerteza a estimar."""
    d = np.full(30, 0.1)
    w = np.linspace(5, 50, 30)
    lo, hi = stats.bootstrap_ic(d, w)
    assert lo == pytest.approx(0.1) and hi == pytest.approx(0.1)


def test_bootstrap_usa_a_faixa_como_unidade():
    """
    Reamostrar faixas, e não observações soltas: o par (diferença, peso) tem de
    viajar junto. Se o peso fosse sorteado à parte, uma diferença grande cairia
    num peso pequeno e o IC encolheria de mentira.
    """
    # uma faixa longa domina e diverge das outras
    d = np.array([0.0, 0.0, 0.0, 0.0, 1.0])
    w = np.array([1.0, 1.0, 1.0, 1.0, 96.0])
    lo, hi = stats.bootstrap_ic(d, w)
    # a média ponderada é 0.96; reamostrando faixas, há sorteios sem a longa
    # (diferença 0) e sorteios com ela repetida (diferença ~0.96+)
    assert lo < 0.5 < hi, (lo, hi)


# ==========================================================================
# O Wilcoxon
# ==========================================================================
def test_wilcoxon_detecta_melhora_consistente():
    d = np.linspace(0.01, 0.30, 40)          # toda faixa melhora
    _, p = stats.wilcoxon(d)
    assert p < 0.001


def test_wilcoxon_nao_inventa_p_quando_nao_ha_diferenca():
    """Diferença toda zero: o scipy levanta, e reportar p=1 seria invenção."""
    est, p = stats.wilcoxon(np.zeros(20))
    assert est != est and p != p            # ambos NaN


def test_wilcoxon_ignora_magnitude():
    """
    É um teste de ranks: multiplicar todas as diferenças positivas por 100 não
    muda o p. Serve de guarda contra alguém trocá-lo por um t-test.
    """
    d = np.array([0.01, 0.02, 0.03, -0.005, 0.04, 0.05, 0.06, -0.001])
    _, p1 = stats.wilcoxon(d)
    _, p2 = stats.wilcoxon(np.where(d > 0, d * 100, d))
    assert p1 == pytest.approx(p2)


# ==========================================================================
# Holm
# ==========================================================================
def test_holm_caso_conhecido():
    """
    Caso clássico com resposta calculável à mão. n = 4, p ordenados
    0.01, 0.02, 0.03, 0.04:

        k=0: (4-0)*0.01 = 0.04
        k=1: (4-1)*0.02 = 0.06
        k=2: (4-2)*0.03 = 0.06   -> monotonicidade mantém 0.06
        k=3: (4-3)*0.04 = 0.04   -> monotonicidade eleva para 0.06
    """
    obtido = stats.holm([0.01, 0.02, 0.03, 0.04])
    assert obtido == pytest.approx([0.04, 0.06, 0.06, 0.06])


def test_holm_respeita_a_ordem_de_entrada():
    """O ajustado volta na posição do p original, não na ordem crescente."""
    obtido = stats.holm([0.04, 0.01, 0.03, 0.02])
    assert obtido == pytest.approx([0.06, 0.04, 0.06, 0.06])


def test_holm_e_monotono_e_limitado_a_um():
    ps = [0.001, 0.2, 0.3, 0.5, 0.9]
    ajustados = stats.holm(ps)
    ordem = np.argsort(ps)
    seq = np.array(ajustados)[ordem]
    assert np.all(np.diff(seq) >= -1e-12), "Holm não saiu monótono"
    assert np.all(np.array(ajustados) <= 1.0)


def test_holm_de_uma_comparacao_nao_corrige():
    assert stats.holm([0.03]) == pytest.approx([0.03])


def test_holm_e_mais_conservador_que_o_p_bruto_e_menos_que_bonferroni():
    ps = np.array([0.001, 0.01, 0.02, 0.04, 0.3])
    h = stats.holm(ps)
    bonferroni = np.minimum(1.0, ps * len(ps))
    assert np.all(h >= ps - 1e-12)
    assert np.all(h <= bonferroni + 1e-12)
    assert np.any(h < bonferroni), "Holm ficou igual a Bonferroni em tudo"


def test_holm_ignora_nan_sem_inflar_a_familia():
    """
    Um NaN não deve encolher o poder dos outros: a família é só o que tem p.
    Com [0.01, NaN, 0.02], n = 2 e não 3.
    """
    obtido = stats.holm([0.01, float("nan"), 0.02])
    assert obtido[1] != obtido[1]                    # NaN preservado
    assert obtido[0] == pytest.approx(0.02)          # 2 * 0.01
    assert obtido[2] == pytest.approx(0.02)          # monotonicidade


# ==========================================================================
# p-valor do bootstrap e classificação
# ==========================================================================
def test_p_bootstrap_pequeno_quando_o_efeito_e_claro():
    d = np.full(60, 0.10)
    w = np.full(60, 10.0)
    lo, hi, p = stats.bootstrap(d, w)
    assert lo > 0 and p == pytest.approx(1 / stats.N_BOOTSTRAP)


def test_p_bootstrap_grande_quando_nao_ha_efeito():
    rng = np.random.default_rng(5)
    d = rng.normal(0.0, 0.05, size=80)
    w = rng.uniform(5, 40, size=80)
    lo, hi, p = stats.bootstrap(d, w)
    assert lo < 0 < hi
    assert p > 0.05


def test_p_bootstrap_tem_piso():
    """Nunca reportar p = 0 a partir de um número finito de reamostragens."""
    d = np.full(40, 1.0)
    w = np.full(40, 1.0)
    _, _, p = stats.bootstrap(d, w)
    assert p >= 1 / stats.N_BOOTSTRAP


@pytest.mark.parametrize("cruza,p_holm,esperado", [
    (False, 0.001, "confirmado"),
    (False, 0.049, "confirmado"),
    (False, 0.051, "fragil"),
    (False, float("nan"), "fragil"),
    (True, 0.001, "empate"),      # IC manda: cruzar zero é empate
    (True, 0.9, "empate"),
])
def test_classificacao_segue_a_regra_do_congelamento(cruza, p_holm, esperado):
    assert stats.classificar(cruza, p_holm) == esperado


def test_classificacao_prioriza_o_ic_sobre_o_p():
    """
    O critério principal é o IC. Um p minúsculo com IC cruzando zero continua
    empate -- é o que impede escolher o critério que favorece a conclusão.
    """
    assert stats.classificar(True, 1e-9) == "empate"


# ==========================================================================
# Células vazias
# ==========================================================================
def test_celula_vazia_descarta_a_faixa_em_vez_de_virar_zero(tmp_path):
    """
    `*_rotulado` vem vazio quando a cobertura é zero. Tratar como 0.0
    inventaria uma faixa que errou tudo.
    """
    caminho = tmp_path / "ablation_vazio_ref0.csv"
    campos = ["variante", "track_id", "duracao_s", "root_rotulado"]
    with caminho.open("w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=campos)
        w.writeheader()
        w.writerow({"variante": "A", "track_id": "t1", "duracao_s": 10,
                    "root_rotulado": 0.8})
        w.writerow({"variante": "B", "track_id": "t1", "duracao_s": 10,
                    "root_rotulado": ""})
        w.writerow({"variante": "A", "track_id": "t2", "duracao_s": 10,
                    "root_rotulado": 0.5})
        w.writerow({"variante": "B", "track_id": "t2", "duracao_s": 10,
                    "root_rotulado": 0.7})

    por_variante, duracoes = stats.carregar(caminho)
    r = stats.comparar(por_variante, duracoes, "A", "B", "root_rotulado", "t")
    assert r["n_faixas"] == 1
    assert r["n_descartadas"] == 1
    assert r["diferenca"] == pytest.approx(0.2)


def test_variante_ausente_levanta():
    por_variante, duracoes = {"A": {}}, {}
    with pytest.raises(KeyError):
        stats.comparar(por_variante, duracoes, "A", "INEXISTENTE", "root", "t")


# ==========================================================================
# Os pares pré-registrados
# ==========================================================================
def test_pares_existem_no_runner():
    import runner
    for a, b, metricas, isola in stats.PARES:
        assert a in runner.VARIANTES, a
        assert b in runner.VARIANTES, b
        assert metricas and isola


def test_pares_usam_colunas_que_o_runner_escreve():
    import runner
    for _, _, metricas, _ in stats.PARES:
        for m in metricas:
            assert m in runner.CSV_FIELDS, f"coluna {m} não existe no CSV"


def test_parametros_do_bootstrap_sao_os_pedidos():
    assert stats.N_BOOTSTRAP == 10_000
    assert stats.SEED == 0
    assert stats.ALFA == 0.05


def test_familia_de_holm_tem_15_comparacoes():
    """O congelamento declara 15; a família tem de ser exatamente essa."""
    assert sum(len(m) for _, _, m, _ in stats.PARES) == 15


def test_rodar_preenche_holm_e_classificacao(csv_pequeno, monkeypatch):
    """A saída de `rodar` não pode ter coluna de Holm vazia nem campo interno."""
    monkeypatch.setattr(stats, "PARES",
                        [("A", "B", ["root", "majmin"], "teste")])
    linhas, avisos = stats.rodar(csv_pequeno)
    assert not avisos
    for l in linhas:
        assert l["p_bootstrap_holm"] != ""
        assert l["classificacao"] in ("confirmado", "empate", "fragil")
        assert not any(k.startswith("_") for k in l), "campo interno vazou"
        assert set(l) == set(stats.CSV_FIELDS)


# ==========================================================================
# O congelamento acompanha
# ==========================================================================
def test_congelamento_traz_os_pares_pre_registrados():
    texto = congelar.gerar()
    for a, b, metricas, _ in stats.PARES:
        assert f"`{a}` vs `{b}`" in texto, f"par {a} vs {b} ausente"
        for m in metricas:
            assert f"`{m}`" in texto
    assert "pré-registrada" in texto.lower()


def test_congelamento_registra_o_change_penalty_nao_ablacionado():
    texto = congelar.gerar()
    assert "change_penalty" in texto
    assert "Nunca variado" in texto
    assert "NÃO foi ablacionado" in texto


def test_congelamento_ainda_tem_as_seis_configuracoes():
    """A tarefa pedia acrescentar seções sem mexer nas configurações."""
    assert congelar.CONGELADAS == ["V4", "C", "D", "E", "F0rg", "D0rg"]
    texto = congelar.gerar()
    for nome in congelar.CONGELADAS:
        assert f"`{nome}`" in texto


def test_tabelas_do_congelamento_tem_uma_linha_por_celula():
    """
    Uma linha de tabela Markdown quebrada em várias linhas de texto deixa de
    ser tabela. Toda linha que começa com '|' tem de terminar com '|'.
    """
    for i, linha in enumerate(congelar.gerar().splitlines(), start=1):
        if linha.startswith("|"):
            assert linha.rstrip().endswith("|"), (
                f"linha {i} de tabela não fecha com '|': {linha[:60]!r}")
