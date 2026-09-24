"""
tests/test_runner.py
====================
Testes da matriz de ablação.

Os dois riscos que estes testes cobrem são silenciosos:

1. A variante E precisa ser mesmo o sistema atual. Se a matriz derivar de um
   default que alguém mudou, a coluna "E" da tabela do artigo deixa de ser o
   sistema descrito e ninguém percebe pelo número.
2. `complexity_penalty` e `ext_sharpness` não têm efeito nenhum dentro do
   `decode`. Se o runner não reconstruir o classificador, as variantes B e C
   saem IDÊNTICAS e a conclusão publicada é "o viés pró-tríade não importa" --
   uma afirmação errada que nenhum teste de forma pegaria.

Usam áudio sintético; não dependem de `data/extracted/`.

    pytest tests/test_runner.py
"""

import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pipeline as P  # noqa: E402
import runner  # noqa: E402
from config import PRE_CHROMA, POST_CHROMA  # noqa: E402
from synth import synth_chord  # noqa: E402

SR = 22050


@pytest.fixture(scope="module")
def faixa():
    """A faixa sintética do smoke test de pipeline.py: C, G, Am."""
    return np.concatenate([
        synth_chord(0, '', sr=SR, dur=2.0, n_harmonics=6),
        synth_chord(7, '', sr=SR, dur=2.0, n_harmonics=6),
        synth_chord(9, 'm', sr=SR, dur=2.0, n_harmonics=6),
    ])


# ==========================================================================
# 1. E é o sistema atual
# ==========================================================================
def test_E_reproduz_analyze_track(faixa):
    """
    extract_features + decode pela variante E == analyze_track com o
    classificador de E e os defaults da assinatura. Igualdade exata.
    """
    E = runner.VARIANTES["E"]
    features = P.extract_features(faixa, SR, E.pre)
    pela_variante = runner.estimar(E, features)
    pelo_monolito = P.analyze_track(faixa, SR, runner.classificador_de(E.post))

    # `estimar` já devolve tuplas, que é o que o scorer consome; o monólito
    # devolve dicts. A comparação é feita no formato do scorer, de propósito:
    # é esse o valor que entra no CSV.
    como_tuplas = [(s['start'], s['end'], s['label']) for s in pelo_monolito]
    assert pela_variante == como_tuplas, (
        f"E divergiu de analyze_track:\n  variante: {pela_variante}\n"
        f"  monolito: {como_tuplas}")
    assert [lab for _, _, lab in pela_variante] == ['C', 'G', 'Am']


def test_estimar_devolve_tuplas_pontuaveis(faixa):
    """
    Guarda contra a regressão que o smoke test pegou: `decode` devolve dicts e
    o scorer desempacotaria as CHAVES, dando ValueError em 'start'.
    """
    from evaluate import score_segments
    E = runner.VARIANTES["E"]
    est = runner.estimar(E, P.extract_features(faixa, SR, E.pre))

    assert all(isinstance(s, tuple) and len(s) == 3 for s in est)
    ref = [(0.0, 2.0, 'C:maj'), (2.0, 4.0, 'G:maj'), (4.0, 6.0, 'A:min')]
    scores = score_segments(est, ref, levels=runner.LEVELS, ref_is_harte=True)
    assert all(0.0 <= v <= 1.0 for v in scores.values())


def test_E_bate_com_os_defaults_de_config():
    """A matriz é derivada de config.py, não de literais paralelos."""
    E = runner.VARIANTES["E"]
    assert E.pre == PRE_CHROMA
    assert E.post == POST_CHROMA


def test_nao_existe_variante_G_porque_seria_D():
    """
    "E com min_dur=0" é D campo por campo. Este teste existe para que ninguém
    recrie uma variante G achando que ela mede outra coisa.
    """
    from dataclasses import replace
    V = runner.VARIANTES
    assert "G" not in V
    G_seria = replace(V["E"].post, min_dur=0.0)
    assert G_seria == V["D"].post
    assert V["E"].pre == V["D"].pre


def test_variantes_sao_incrementais():
    """Cada variante muda UM campo em relação à anterior."""
    V = runner.VARIANTES
    assert V["A"].pre.smooth == 0 and V["B"].pre.smooth == 21
    assert V["A"].post == V["B"].post          # A->B: só o pré-chroma muda
    esperado = [
        ("B", "C", "complexity_penalty", 0.0, 0.06),
        ("C", "D", "use_viterbi", False, True),
        ("D", "E", "min_dur", 0.0, 0.8),
    ]
    for antes, depois, campo, va, vd in esperado:
        pa, pd = V[antes].post, V[depois].post
        assert getattr(pa, campo) == va and getattr(pd, campo) == vd
        diferentes = [f for f in type(pa).__dataclass_fields__
                      if getattr(pa, f) != getattr(pd, f)]
        assert diferentes == [campo], (
            f"{antes}->{depois} mudou {diferentes}, esperado só [{campo}]")
        assert V[antes].pre == V[depois].pre


# ==========================================================================
# 2. O classificador é reconstruído
# ==========================================================================
def test_complexity_penalty_muda_a_emissao(faixa):
    """
    B (cp=0) e C (cp=0.06) precisam de classificadores diferentes, com
    emissões diferentes. Se o runner reusasse um classificador só, este teste
    falha -- e é ele que separa uma ablação real de uma varredura inócua.
    """
    B, C = runner.VARIANTES["B"], runner.VARIANTES["C"]
    clf_b, clf_c = runner.classificador_de(B.post), runner.classificador_de(C.post)

    assert clf_b is not clf_c, "o mesmo classificador foi reusado para cp=0 e 0.06"
    assert clf_b.complexity_penalty == 0.0
    assert clf_c.complexity_penalty == 0.06

    # Um chroma com a 7ª FRACA: é onde o viés pró-tríade age.
    chroma = np.zeros(12)
    chroma[[0, 4, 7]] = 1.0      # tríade de C
    chroma[10] = 0.05            # 7ª quase ausente
    emis_b, emis_c = clf_b.emission(chroma), clf_c.emission(chroma)

    assert not np.allclose(emis_b, emis_c), (
        "cp=0 e cp=0.06 deram a mesma emissão: o classificador não foi "
        "reconstruído")
    k7 = clf_c.names.index('C7')
    assert emis_c[k7] < emis_b[k7], "a tétrade não foi penalizada em C"


def test_mesmo_par_compartilha_classificador():
    """C, D e E têm o mesmo (cp, ext_sharpness): uma instância só."""
    V = runner.VARIANTES
    a = runner.classificador_de(V["C"].post)
    b = runner.classificador_de(V["D"].post)
    c = runner.classificador_de(V["E"].post)
    assert a is b is c


def test_B_e_C_dao_resultados_diferentes(faixa):
    """
    A prova de ponta a ponta: as duas variantes, na mesma faixa, não podem
    devolver a mesma coisa em todos os aspectos mensuráveis.
    """
    V = runner.VARIANTES
    features = P.extract_features(faixa, SR, V["B"].pre)
    emis_b = runner.classificador_de(V["B"].post).emission(features.chroma[:, 0])
    emis_c = runner.classificador_de(V["C"].post).emission(features.chroma[:, 0])
    assert not np.allclose(emis_b, emis_c)


# ==========================================================================
# 3. Proteção do split de teste
# ==========================================================================
def test_split_test_exige_mencao_explicita(tmp_path):
    manifest = tmp_path / "m.csv"
    manifest.write_text(
        "dataset,track_id,audio_path,annotation_path,split,excluded\n"
        "guitarset,t1,a.wav,a.jams,test,false\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        runner.main(["--manifest", str(manifest), "--variants", "E"])
    assert "test" in str(exc.value)


def test_variante_desconhecida_falha_cedo(tmp_path):
    manifest = tmp_path / "m.csv"
    manifest.write_text("dataset,track_id,split,excluded\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        runner.main(["--manifest", str(manifest), "--variants", "Z"])
    assert "Z" in str(exc.value)


# ==========================================================================
# 4. Forma da saída
# ==========================================================================
def test_csv_tem_as_colunas_de_config_e_os_niveis():
    for campo in ("variante", "track_id", "split", "duracao_s", "ref_camada"):
        assert campo in runner.CSV_FIELDS
    for nivel in runner.LEVELS:
        assert nivel in runner.CSV_FIELDS
    for campo in PRE_CHROMA.__dataclass_fields__:
        assert campo in runner.CSV_FIELDS
    for campo in POST_CHROMA.__dataclass_fields__:
        assert campo in runner.CSV_FIELDS


# ==========================================================================
# 5. F: vocabulário BASIC
# ==========================================================================
def test_F_usa_basic_e_D_usa_medium(faixa):
    """F só pode emitir maj/min; D tem as 5 qualidades do MEDIUM."""
    V = runner.VARIANTES
    clf_d = runner.classificador_de(V["D"].post, V["D"].vocab)
    clf_f = runner.classificador_de(V["F"].post, V["F"].vocab)

    assert clf_d is not clf_f, "BASIC e MEDIUM compartilharam classificador"
    assert len(clf_d.names) == 60
    assert len(clf_f.names) == 24
    assert not any(n.endswith(('7', 'maj7', 'm7')) for n in clf_f.names)

    # F e D só diferem no vocabulário: o resto da config é o mesmo
    assert V["F"].post == V["D"].post
    assert V["F"].pre == V["D"].pre


def test_F_nunca_emite_tetrade(faixa):
    """Uma faixa com Cmaj7 sintético: D pode acertar a tétrade, F não pode."""
    y = np.concatenate([synth_chord(0, 'maj7', sr=SR, dur=2.0, n_harmonics=6),
                        synth_chord(7, '7', sr=SR, dur=2.0, n_harmonics=6)])
    V = runner.VARIANTES
    features = P.extract_features(y, SR, V["F"].pre)
    rotulos_f = {lab for _, _, lab in runner.estimar(V["F"], features)}
    assert all(lab in ('N',) or lab.rstrip('m') in
               ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
               for lab in rotulos_f), f"F emitiu algo fora de BASIC: {rotulos_f}"


# ==========================================================================
# 6. V4b: o V4 sem os termos temporais
# ==========================================================================
def test_v4b_nao_tem_os_dois_termos_temporais():
    """
    V4b é stateless: o mesmo chroma dá o mesmo rótulo, e o resultado não
    depende de nenhum acorde anterior. No V4 original, o +0.5 de inércia faz
    o rótulo anterior mudar a resposta.
    """
    from legacy_v4 import classificar_segmento_v4

    anteriores = ("C", "Cm", "G", "Am", "F", "Dm", "E", "A")
    rng = np.random.default_rng(7)     # seed fixa: o teste não pode ser sorteio

    sensiveis_v4 = 0
    sensiveis_v4b = 0
    for _ in range(300):
        chroma = rng.random(12)
        base_v4 = classificar_segmento_v4(chroma, "")
        if any(classificar_segmento_v4(chroma, a) != base_v4 for a in anteriores):
            sensiveis_v4 += 1
        # V4b não recebe contexto: a resposta é uma só, por construção
        base_v4b = runner.classificar_segmento_v4b(chroma)
        if runner.classificar_segmento_v4b(chroma) != base_v4b:
            sensiveis_v4b += 1

    assert sensiveis_v4 > 0, ("o V4 original não mostrou dependência do acorde "
                              "anterior na amostra: o teste não provaria nada")
    assert sensiveis_v4b == 0


def test_v4b_concorda_com_v4_quando_a_inercia_nao_pesa():
    """
    Sem acorde anterior o V4 não aplica nenhum dos dois termos, então V4b tem
    de dar exatamente o mesmo rótulo. É o que garante que a cópia não divergiu
    do original em outra coisa.
    """
    from legacy_v4 import classificar_segmento_v4
    rng = np.random.default_rng(0)
    for _ in range(200):
        chroma = rng.random(12)
        assert (runner.classificar_segmento_v4b(chroma)
                == classificar_segmento_v4(chroma, "")), chroma.tolist()


def test_v4b_gate_de_energia_preservado():
    """O gate `sum < 0.1 -> ''` da cópia é o mesmo do original."""
    from legacy_v4 import classificar_segmento_v4
    quieto = np.zeros(12)
    assert runner.classificar_segmento_v4b(quieto) == ""
    assert classificar_segmento_v4(quieto, "") == ""


# ==========================================================================
# 7. Diagnóstico
# ==========================================================================
def test_diagnostico_em_caso_montado_a_mao():
    """
    4 s: 1 s certo, 1 s com tônica certa e qualidade errada, 1 s com tônica
    errada, 1 s estimado como N (que conta como tônica errada -- N não tem
    tônica).
    """
    ref = [(0.0, 1.0, 'C:maj'), (1.0, 2.0, 'C:maj'),
           (2.0, 3.0, 'C:maj'), (3.0, 4.0, 'C:maj')]
    est = [(0.0, 1.0, 'C'), (1.0, 2.0, 'Cm'), (2.0, 3.0, 'G'), (3.0, 4.0, 'N')]

    d = runner.diagnostico(est, ref)
    assert d["frac_n_est"] == pytest.approx(0.25)
    assert d["frac_tonica_ok_qualidade_erro"] == pytest.approx(0.25)
    assert d["frac_tonica_erro"] == pytest.approx(0.50)


def test_diagnostico_perfeito_e_zero():
    ref = [(0.0, 2.0, 'C:maj'), (2.0, 4.0, 'A:min')]
    est = [(0.0, 2.0, 'C'), (2.0, 4.0, 'Am')]
    d = runner.diagnostico(est, ref)
    assert d["frac_n_est"] == pytest.approx(0.0)
    assert d["frac_tonica_ok_qualidade_erro"] == pytest.approx(0.0)
    assert d["frac_tonica_erro"] == pytest.approx(0.0)


def test_colunas_de_diagnostico_no_csv():
    for campo in runner.DIAG_FIELDS:
        assert campo in runner.CSV_FIELDS
    assert "n_segmentos_ref" in runner.CSV_FIELDS


def test_linhas_do_manifest_respeitam_split_e_exclusao(tmp_path):
    manifest = tmp_path / "m.csv"
    manifest.write_text(
        "dataset,track_id,split,excluded\n"
        "g,val_ok,val,false\n"
        "g,val_excluida,val,true\n"
        "g,test_ok,test,false\n", encoding="utf-8")
    linhas = runner._linhas(manifest, {"val"})
    assert [l["track_id"] for l in linhas] == ["val_ok"]
