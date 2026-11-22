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

**Para usar no artigo:**
- **As 10 figuras sem estilo comum** têm rótulos em português, e quatro delas
  trazem um texto explicativo dentro da figura. Para o artigo é preciso uma
  versão em inglês, sem esse texto (a legenda vai no LaTeX). Os números não
  mudam.
- **`fig_comparacoes`:** usa "empate" para IC que cruza zero; no texto novo o
  termo é "unresolved".
- **Arquivos `_dados.csv`:** existem só para as figuras do estilo comum.
