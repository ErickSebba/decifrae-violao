"""Testes do parser do Chordino e da conversão CSV -> segmentos (sem executável)."""

import sys
from pathlib import Path

import mir_eval
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import baselines_externos as be  # noqa: E402


@pytest.mark.parametrize("rotulo, harte", [
    ("C", "C:maj"),
    ("Cm", "C:min"),
    ("G7", "G:7"),
    ("Ebmaj7", "Eb:maj7"),
    ("F#m7", "F#:min7"),
    ("Bdim", "B:dim"),
    ("Caug", "C:aug"),
    ("A6", "A:maj6"),
    ("Dm6", "D:min6"),
    ("C#dim7", "C#:dim7"),
    ("Bm7b5", "B:hdim7"),
    ("Ab", "Ab:maj"),
    ("Bb7", "Bb:7"),
    ("C/E", "C:maj/3"),
    ("C/G", "C:maj/5"),
    ("Am7/G", "A:min7/b7"),
    ("Am/C", "A:min/b3"),
    ("D7/F#", "D:7/3"),
    ("Bb/F", "Bb:maj/5"),
    ("Eb/Bb", "Eb:maj/5"),
    ("Caug/G#", "C:aug/#5"),
    ("Cdim7/A", "C:dim7/bb7"),
    ("C/C", "C:maj"),
    ("N", "N"),
    ('"N"', "N"),
])
def test_parse_chordino(rotulo, harte):
    assert be.parse_chordino(rotulo) == harte


@pytest.mark.parametrize("rotulo", ["C", "Cm", "Am7/G", "Bm7b5", "Caug/G#",
                                    "Cdim7/A", "Eb/Bb"])
def test_harte_e_valido_no_mir_eval(rotulo):
    mir_eval.chord.encode(be.parse_chordino(rotulo))


def test_bemol_e_sustenido_mesma_classe():
    assert (mir_eval.chord.encode(be.parse_chordino("Bb7"))[0]
            == mir_eval.chord.encode(be.parse_chordino("A#7"))[0])


def test_inversao_preserva_semitom_do_baixo():
    # A:min7/b7 -> baixo em G (10 semitons acima de A)
    assert mir_eval.chord.encode(be.parse_chordino("Am7/G"))[2] == 10


@pytest.mark.parametrize("rotulo", ["Csus9x", "H", "C/H", "Cfoo/E"])
def test_rotulo_desconhecido_falha(rotulo):
    with pytest.raises(ValueError):
        be.parse_chordino(rotulo)


def test_harte_direto_passa():
    assert be.parse_chordino("C:maj/3") == "C:maj/3"


def test_csv_para_segmentos(tmp_path):
    csv_path = tmp_path / "x.csv"
    csv_path.write_text('0.000000000,"N"\n0.046439909,"Ebmaj7"\n'
                        '7.15,"Fm"\n9.5,"Am7/G"\n', encoding="utf-8")
    eventos = be.ler_csv_sonic(csv_path)
    assert eventos[0] == (0.0, "N")
    segs = be.eventos_para_segmentos(eventos, duracao=12.0)
    assert segs == [(0.0, 0.046439909, "N"),
                    (0.046439909, 7.15, "Eb:maj7"),
                    (7.15, 9.5, "F:min"),
                    (9.5, 12.0, "A:min7/b7")]


def test_csv_com_coluna_de_arquivo_e_evento_duplicado(tmp_path):
    csv_path = tmp_path / "y.csv"
    csv_path.write_text('"faixa.wav",0.0,"N"\n,1.0,"C"\n,1.0,"G"\n,2.0,"N"\n',
                        encoding="utf-8")
    segs = be.eventos_para_segmentos(be.ler_csv_sonic(csv_path), duracao=3.0)
    # o segmento de duração nula (C em 1.0 -> 1.0) é descartado
    assert [s[2] for s in segs] == ["N", "G:maj", "N"]
    assert segs[-1][1] == 3.0


def test_lab_ida_e_volta(tmp_path):
    segs = [(0.0, 1.5, "N"), (1.5, 3.25, "C:maj/3")]
    lab = tmp_path / "a" / "t.lab"
    be.escrever_lab(lab, segs)
    assert be.ler_lab(lab) == segs


def test_estimado_harte_nao_vira_x():
    import evaluate
    ref = [(0.0, 2.0, "C:maj"), (2.0, 4.0, "A:min7/b7")]
    est = [(0.0, 2.0, "C:maj"), (2.0, 4.0, "A:min7/b7")]
    sem = evaluate.score_segments(est, ref, ref_is_harte=True)
    with be._estimado_em_harte():
        com = evaluate.score_segments(est, ref, ref_is_harte=True)
    assert com["mirex"] == pytest.approx(1.0)
    assert com["root"] == pytest.approx(1.0)
    assert sem["root"] < 1.0          # sem o contexto, o Harte vira 'X'
    # e o contexto restaura a tradução original
    assert evaluate._to_mireval("Am") == "A:min"


def test_fora_da_referencia_descarta_so_segmentos_externos():
    from baselines_externos import fora_da_referencia
    ref = [(9.6, 20.0, "C:maj"), (20.0, 30.0, "G:maj")]
    est = [(0.0, 9.6, "N"), (9.6, 25.0, "C:maj"), (25.0, 30.0, "G:maj"),
           (30.0, 31.0, "N")]
    assert fora_da_referencia(est, ref) == est[1:3]
    # segmento que atravessa o início fica (o mir_eval corta)
    est2 = [(0.0, 10.0, "N"), (10.0, 30.0, "C:maj")]
    assert fora_da_referencia(est2, ref) == est2


def test_fronteira_no_inicio_da_referencia_nao_quebra_underseg():
    import runner
    from baselines_externos import fora_da_referencia, _estimado_em_harte
    ref = [(9.6, 20.0, "C:maj"), (20.0, 30.0, "G:maj")]
    est = [(0.0, 9.6, "N"), (9.6, 20.0, "C:maj"), (20.0, 30.0, "G:maj")]
    with _estimado_em_harte():
        linha = runner._linha_csv(
            runner.Variante("madmom", motor="madmom", vocab="madmom"),
            {"track_id": "t", "split": "external"}, ref,
            fora_da_referencia(est, ref), runner._duracao(ref), 0)
    assert linha["root"] == 1.0
