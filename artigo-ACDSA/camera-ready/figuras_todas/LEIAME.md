# Todas as figuras utilizáveis (conferidas em 2026-11-21)

Esta pasta tem **todas** as figuras do projeto que podem entrar no artigo ou
no material suplementar. A seleção proposta para o artigo continua em
`../figuras/` (ver `CAMERA_READY.md` §5–§6).

**Conferência com os dados atuais:** as 13 figuras batem com os CSVs atuais.
- **As 10 figuras com script gerador próprio:** foram regeneradas numa pasta
  temporária, a partir dos CSVs e do código atuais. A saída ficou **idêntica
  pixel a pixel** à figura existente.
- **As 3 figuras do estilo comum:** foram geradas e revisadas em 2026-11-21.
  Os números de cada uma conferem com o seu `_dados.csv` e com a origem.

Nenhuma figura divergiu. Por isso não há pasta de figuras desatualizadas.

| figura | serve para | dados de origem (`data/results/`) | idioma / estilo |
|---|---|---|---|
| `fig_cobertura_igualada` | R2.3 — C vs D na mesma cobertura (teste) | `cobertura_igualada_teste_20261117_011711.csv` | inglês, estilo comum |
| `fig_executantes` | R2.1 — Δ por executante | `por_executante_20261117_004132.csv` | inglês, estilo comum |
| `fig_transferencia_corpora` | R4 — 6 contrastes, GuitarSet × IDMT-SMT-Guitar | `transferencia_20261117_122651.csv` | inglês, estilo comum |
| `fig_cobertura_teste` | R2.3 — curvas acerto × cobertura no teste | `curvas_teste_20261117_011711.csv`, `cobertura_igualada_teste_20261117_011711.csv` | português |
| `fig_transferencia` | R4 — os 15 contrastes nos três corpora | `transferencia_20261117_122651.csv` | português |
| `fig_diagnostico_n` | R4/V — por que o N vence no IDMT-SMT-Chords | `diagnostico_n_20261117_135637.csv` (cache de features) | português |
| `fig_transicao` | R2.6 — penalidade de transição por vocabulário | `calibracao_revisao_20261116_231220.csv`, `transicao_20261117_004150.csv` | português |
| `fig_cobertura_acerto` | acerto rotulado × cobertura (validação) + variantes no teste | `curvas_20260926_015602.csv`, ablações de 2026-09-27 | português |
| `fig_cobertura` | curvas de cobertura na validação, todas as variantes | `curvas_20260926_015602.csv`, `ablation_20260927_005629_ref0.csv` | português, legenda longa dentro da figura |
| `fig_acuracia_segmentacao` | acurácia × segmentação das variantes no teste | `ablation_20260927_014253_ref0.csv`, `ablation_20260927_014445_ref1.csv` | português |
| `fig_comparacoes` | forest plot dos 15 contrastes (validação e teste) + máscara comum | `stats_val_ref0_20260927_020511.csv`, `stats_test_ref0_20260927_202140.csv`, `mascara_comum_20260927_202401.csv` | português, legenda longa dentro da figura |
| `fig_exemplo` | exemplo de faixa (chroma, referência, C, D, E) | `ablation_20260927_005629_ref0.csv` + cache | português, legenda longa dentro da figura |
| `fig_pipeline` | diagrama do pipeline e das três fontes de N | nenhum (diagrama) | português, legenda longa dentro da figura |

**Versões em inglês (`<nome>_en.pdf/.png`).** As 10 figuras que estavam em
português têm agora uma versão em inglês ao lado da original. Para o artigo,
use a versão `_en`; as originais em português ficam como referência.
- **Como foram geradas:** por `traduzir_figuras.py`, com as mesmas funções e
  os mesmos dados que reproduzem as originais pixel a pixel. Na hora de
  salvar, cada texto é trocado pelo equivalente em inglês. Nada nos dados nem
  no desenho muda.
- **Termos:** vírgula decimal virou ponto. As classes viraram "supported",
  "unresolved" e "fragile" (antes "confirmado", "empate" e "frágil").
- **Notas removidas:** cinco figuras tinham um texto explicativo dentro da
  figura. Na versão `_en` esse texto foi removido, porque a explicação vai na
  legenda do LaTeX. A tradução de cada nota está abaixo, para servir de base
  à legenda.

| figura | nota traduzida (base para a legenda) |
|---|---|
| `fig_cobertura_acerto_en` | The curves stop at 99.75% coverage (dotted line), not 100%: even with the confidence gate and the Viterbi N state disabled, the relative silence gate (rel_gate = 0.2) forces N on 0.25% of the time. The rg variants, which set this gate to zero, and V4, which never abstains, reach 100.00%. |
| `fig_cobertura_en` | Validation only. The three curves stop at 99.75% coverage (dotted line), not 100%: even with the confidence gate and the Viterbi N state disabled, they keep the relative silence gate (rel_gate = 0.2), and it is this gate, not abs_floor, that forces N on the remaining 0.25%. The variants that set rel_gate to zero and the baselines (V4, V4b, C0rg, D0rg, E0rg, F0rg) reach 100.00%. |
| `fig_comparacoes_en` | One pair per row, chord[0] layer; vertical line at zero. The class in the margin is the test-set class. The last two rows, highlighted, are post hoc (common mask): they are not among the pre-registered pairs and have no published per-track Δ. The axis is clipped at ±35 pp; 21 of 870 per-track points fall outside. |
| `fig_exemplo_en` | Track 03_SS2-88-F_comp, chosen by rule rather than by hand: the validation track whose D − C root difference is the lower median of the 120 tracks (position 60 of 120 in ascending order); Δroot(D − C) = +12.02 pp. Bar color = chord root; N in gray. A bar is labeled with its root only when the text fits. |
| `fig_pipeline_en` | In red, the three sources of N and where each acts. The relative silence gate (rel_gate) overrides the other two: the segments it marks enter as force_n, which zeroes the chord emissions in the Viterbi and emits N directly in the arg-max. Hence confidence_gate, consulted only by the arg-max (use_viterbi = False), and the Viterbi N state (n_logprob) decide only where rel_gate has not. |

**Outras observações:**
- **Estilo:** as 10 versões `_en` mantêm o estilo original (fonte sem serifa,
  cores). Só as três figuras do estilo comum seguem o padrão Times
  3,5 × 2,2 pol.
- **Arquivos `_dados.csv`:** existem só para as figuras do estilo comum.
