"""
tests/test_coverage.py
======================
Testes da medida de cobertura.

A afirmação que o `coverage_report.py` faz é forte: "esta fração do tempo é o que o
mir_eval realmente pondera neste nível". O teste central não confere a
implementação contra ela mesma -- monta um caso onde o estimado está CERTO só
na parte comparável e ERRADO em todo o resto, e exige que o mir_eval devolva
100 %. Se o descarte não funcionasse como o script supõe, esse número cairia.

Não dependem de `data/extracted/`: usam anotações minúsculas escritas à mão.

    pytest tests/test_coverage.py
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import coverage_report as cov  # noqa: E402
from evaluate import score_segments  # noqa: E402


# ==========================================================================
# A premissa do script
# ==========================================================================
def test_o_que_e_incomparavel_e_mesmo_descartado_pelo_mir_eval():
    """
    1 s de 'C:maj' (comparável em majmin) + 2 s de 'C:dim7' (não comparável).
    O estimado acerta o primeiro segundo e erra feio os outros dois.
    Se o mir_eval descarta o que o coverage_report marca como incomparável, majmin
    sai 1.0 -- e o nosso comparavel_frac tem de ser 1/3.
    """
    ref = [(0.0, 1.0, 'C:maj'), (1.0, 3.0, 'C:dim7')]
    est = [(0.0, 1.0, 'C'), (1.0, 3.0, 'Fm')]

    scores = score_segments(est, ref, levels=['majmin'], ref_is_harte=True)
    assert scores['majmin'] == pytest.approx(1.0), (
        "o mir_eval não descartou o trecho incomparável")

    labels = [l for _, _, l in ref]
    duracoes = [e - s for s, e, _ in ref]
    mask = cov._comparavel(labels, 'majmin')
    fracao = sum(d for d, m in zip(duracoes, mask) if m) / sum(duracoes)
    assert fracao == pytest.approx(1 / 3)


def test_mascara_bate_com_o_menos_um_do_mir_eval():
    """A máscara é exatamente 'a comparação não é -1', em todos os níveis."""
    import mir_eval
    labels = ['C:maj', 'A:min7', 'C:dim7', 'D#:sus2(7)/1', 'N', 'X', 'C:7']
    for nivel in cov.LEVELS:
        esperado = mir_eval.chord.__dict__[nivel](labels, labels) != -1
        assert list(cov._comparavel(labels, nivel)) == list(esperado)


def test_x_nunca_e_comparavel_e_n_sempre_e():
    for nivel in cov.LEVELS:
        assert not cov._comparavel(['X'], nivel)[0], f"'X' passou em {nivel}"
        assert cov._comparavel(['N'], nivel)[0], f"'N' foi descartado em {nivel}"


# ==========================================================================
# Decomposição do rótulo
# ==========================================================================
@pytest.mark.parametrize("label,esperado", [
    ('C:maj', 'maj'),
    ('A:min7', 'min7'),
    ('D#:sus2(7)/1', 'sus2(7)'),
    ('G#:maj6(*5)/1', 'maj6(*5)'),
    ('D:maj(2)/2', 'maj(2)'),
    ('N', 'N'),
])
def test_qualidade_ignora_tonica_e_baixo(label, esperado):
    assert cov._qualidade(label) == esperado


# ==========================================================================
# Agregação
# ==========================================================================
@pytest.fixture
def manifest_minimo(tmp_path, monkeypatch):
    """Um manifest de 1 faixa apontando para um .lab escrito à mão."""
    lab = tmp_path / "anotacao.lab"
    lab.write_text(
        "0.0\t1.0\tC:maj\n"
        "1.0\t3.0\tC:dim7\n"
        "3.0\t4.0\tN\n",
        encoding="utf-8")
    manifest = tmp_path / "m.csv"
    manifest.write_text(
        "dataset,track_id,annotation_path,excluded\n"
        f"t,boa,{lab.name},false\n"
        f"t,pulada,{lab.name},true\n",
        encoding="utf-8")
    monkeypatch.setattr(cov, "ROOT", tmp_path)
    return manifest


def test_agregacao_respeita_exclusoes_e_pondera_por_tempo(manifest_minimo):
    import dataset_io as ds
    linhas, top = cov.medir_camada("t", "lab", manifest_minimo.name,
                                   ds.load_idmt_lab)

    assert len(linhas) == len(cov.LEVELS)
    assert {l["nivel"] for l in linhas} == set(cov.LEVELS)

    por_nivel = {l["nivel"]: l for l in linhas}
    # a linha excluded=true não entra: 1 faixa, 4 s
    assert por_nivel['majmin']["n_faixas"] == 1
    assert por_nivel['majmin']["duracao_total_s"] == pytest.approx(4.0)
    # 1 s de maj + 1 s de N comparáveis; 2 s de dim7 descartados
    assert por_nivel['majmin']["comparavel_frac"] == pytest.approx(0.5)
    assert por_nivel['majmin']["descartado_frac"] == pytest.approx(0.5)
    # root não descarta nada aqui
    assert por_nivel['root']["comparavel_frac"] == pytest.approx(1.0)
    # 1 s dos 4 é N
    assert por_nivel['majmin']["n_frac"] == pytest.approx(0.25)

    assert dict(top)['dim7'] == pytest.approx(0.5)
    assert por_nivel['majmin']["split"] == "todos"


def test_recorte_por_split_muda_a_distribuicao(tmp_path, monkeypatch):
    """
    O recorte por split existe porque a distribuição de qualidades difere
    entre os splits. Usar a fração agregada para normalizar um resultado de um
    split só erra a favor de quem escolhe a normalização.
    """
    import dataset_io as ds
    a = tmp_path / "a.lab"
    a.write_text("0.0\t2.0\tC:maj\n", encoding="utf-8")       # val: só tríade
    b = tmp_path / "b.lab"
    b.write_text("0.0\t2.0\tC:7\n", encoding="utf-8")         # test: só sétima
    manifest = tmp_path / "m.csv"
    manifest.write_text(
        "dataset,track_id,annotation_path,split,excluded\n"
        f"t,t1,{a.name},val,false\n"
        f"t,t2,{b.name},test,false\n", encoding="utf-8")
    monkeypatch.setattr(cov, "ROOT", tmp_path)

    def frac7(split):
        linhas, top = cov.medir_camada("t", "lab", manifest.name,
                                       ds.load_idmt_lab, split=split)
        return dict(top).get("7", 0.0), linhas[0]["split"]

    assert frac7("val") == (pytest.approx(0.0), "val")
    assert frac7("test") == (pytest.approx(1.0), "test")
    agregado, rotulo = frac7(None)
    assert agregado == pytest.approx(0.5) and rotulo == "todos"


def test_medir_tudo_emite_agregado_e_recortes(tmp_path, monkeypatch):
    """
    O CSV precisa ter a linha agregada E uma por split, para cada camada.

    A versão anterior deste teste só afirmava `"split" in CSV_FIELDS`, e uma
    regressão que fizesse `medir_tudo` parar de emitir os recortes passaria
    por ele. Agora a asserção é sobre a saída.
    """
    import dataset_io as ds
    assert "split" in cov.CSV_FIELDS

    lab = tmp_path / "a.lab"
    lab.write_text("0.0\t2.0\tC:maj\n", encoding="utf-8")
    manifest = tmp_path / "m.csv"
    manifest.write_text(
        "dataset,track_id,annotation_path,split,excluded\n"
        f"d,t1,{lab.name},val,false\n"
        f"d,t2,{lab.name},test,false\n"
        f"d,t3,{lab.name},val,true\n", encoding="utf-8")
    monkeypatch.setattr(cov, "ROOT", tmp_path)
    monkeypatch.setattr(cov, "CAMADAS",
                        [("d", "lab", manifest.name, ds.load_idmt_lab)])

    linhas, _ = cov.medir_tudo()
    splits = {l["split"] for l in linhas}
    assert splits == {"todos", "val", "test"}, splits
    # uma linha por (split, nível), e a excluída não conta em nenhum
    assert len(linhas) == 3 * len(cov.LEVELS)
    por_split = {l["split"]: l for l in linhas if l["nivel"] == "root"}
    assert por_split["todos"]["n_faixas"] == 2
    assert por_split["val"]["n_faixas"] == 1
    assert por_split["test"]["n_faixas"] == 1
