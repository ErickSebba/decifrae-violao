# Avaliação cross-corpus — especificação

Status: **proposta, não executada.** Branch `artigo/cross-corpus`.
Este documento fixa o protocolo **antes** de qualquer faixa externa passar pelo
pipeline, pelo mesmo motivo do `CONGELAMENTO.md`: escolha feita depois de ver o
resultado é ajuste disfarçado de resultado.

## 1. Pergunta

As configurações congeladas no GuitarSet (`docs/CONGELAMENTO.md`) mantêm o
desempenho — e a **ordem relativa** entre elas — em gravações de outro corpus,
com outros músicos, instrumentos e cadeia de captação, **sem nenhum reajuste**?

A resposta vale mesmo se for "não". Uma queda grande entre corpora é resultado,
não falha do experimento.

## 2. Papel de cada dataset

| Dataset | Papel | Split no manifest | Situação |
|---|---|---|---|
| GuitarSet, músicos 00–03 | busca e seleção | `val` | feito |
| GuitarSet, músicos 04–05 | teste intra-corpus | `test` | feito (execução única) |
| **IDMT-SMT-Guitar, subconjunto 4** | **cross-corpus principal — pipeline completo** | `ext` | a inspecionar |
| Guitar-TECHS, categoria *Music* | cross-domain acústico (opcional) | `ext` | só se a §7 for aprovada |
| IDMT-SMT-Chords | controle **sintético** de vocabulário | `synth` | reclassificar ou retirar — decisão pendente |

Descartados, com o motivo registrado para a seção de trabalhos relacionados:

| Dataset | Motivo |
|---|---|
| Isophonics, McGill Billboard, JAAH | áudio comercial não distribuído — quebra a reprodutibilidade |
| IDMT-SMT-Chord-Sequences | áudio sintetizado (FluidSynth) |
| EGSet12 | 6 min, um único guitarrista, anotação de tablatura e não de acordes |
| Osmalsky (ULiège), Isolated Guitar Chords | acordes isolados — só testam o classificador; o primeiro sem distribuição versionada |

### 2.1 IDMT-SMT-Chords: o que muda

O áudio é gerado a partir de MIDI com instrumentos de software (Ableton Live,
GarageBand). Portanto:

- **não** é apresentado no artigo como avaliação em gravação real;
- se ficar, entra como controle sintético (`split=synth`), numa tabela à parte,
  com a origem do áudio escrita na legenda;
- `docs/DATASETS.md` §3 e o `CLAUDE.md` precisam registrar isso. Essa edição é
  feita no mesmo commit que decidir o destino do dataset.

## 3. Regras (não negociáveis)

1. **Nada é ajustado em dado externo.** As configurações rodadas são exatamente
   as de `CONGELAMENTO.md`: `V4, C, D, E, F0rg, D0rg`. Nenhum hiperparâmetro,
   template, limiar ou regra de merge muda por causa do corpus externo.
2. **`ext` é protegido como `test`.** Entra em `runner.SPLITS_PROTEGIDOS`, exige
   `--splits ext` explícito e é lido **uma única vez**. O CSV é commitado logo
   depois, antes de qualquer análise.
3. **Antes da execução, só a anotação pode ser lida.** A auditoria da §5 lê
   rótulos, tempos e duração do áudio; **não** roda o classificador nem calcula
   métrica. Uma "rodada de teste" em faixa externa conta como a execução única.
4. **O adaptador não conhece o classificador.** Toda diferença de formato fica
   em `dataset_io.py`; `runner.py` só despacha pelo campo `dataset`.
5. **Oráculo intacto.** As mudanças de código deste branch são neutras para o
   GuitarSet e para `Musicas/`:
   `python benchmark_musicas.py && git diff --exit-code out/musicas_bench/metrics.json`.
6. **Nenhuma lista de faixas em script.** Faixas, exclusões e motivos vivem no
   manifest e em `docs/DATASETS.md`.
7. **Áudio e anotações originais não entram no Git** (licença CC BY-NC-ND 4.0
   no IDMT: não redistribuir, não alterar). Entram manifests, CSVs e o código do
   adaptador.

## 4. Organização local e manifest

```text
data/raw/idmt-smt-guitar/IDMT-SMT-GUITAR_V2.zip       # MD5 conferido
data/extracted/idmt-smt-guitar/...                   # descompactado, intocado
data/manifests/idmt_smt_guitar.csv
```

Colunas: as de `dataset_io.MANIFEST_FIELDS` e mais as de estratificação, que o
IDMT fornece e o GuitarSet não:

| Coluna | Conteúdo |
|---|---|
| `dataset` | `idmt-smt-guitar` |
| `track_id` | nome do arquivo sem extensão |
| `audio_path`, `annotation_path` | relativos à raiz do repositório |
| `player_id` | vazio se o dataset não identificar o músico |
| `split` | `ext` |
| `excluded`, `exclude_reason` | exclusão explícita, nunca silenciosa |
| `guitar_id` | qual das três guitarras |
| `tempo` | andamento da gravação (lento/rápido) |
| `genre` | gênero da peça |
| `capture` | `di` ou `mic` |

MD5, data do download e versão do Zenodo vão para `docs/DATASETS.md`, como já
é feito para o GuitarSet.

## 5. Auditoria da anotação (antes de rodar)

Script `audit_ext.py` (novo), que lê **só** manifest, anotação e duração do WAV,
e escreve `data/results/audit_idmt_smt_guitar.csv`, uma linha por faixa:

| Coluna | Para quê |
|---|---|
| `dur_audio`, `dur_anot` | detectar anotação desalinhada ou truncada (> 0,5 s de diferença → exclusão candidata) |
| `n_segmentos`, `n_acordes_distintos` | detectar faixa de acorde único ou isolado |
| `trocas_por_minuto` | medir se há progressão de verdade |
| `pct_medium`, `pct_fora`, `pct_n` | tempo dentro do vocabulário MEDIUM, fora dele (dim, sus, aug…), e em N |
| `rotulos_fora` | quais rótulos ficaram fora, para o texto do artigo |

Critérios **fixados agora**, antes da auditoria:

- **Progressão:** o corpus serve para testar o pipeline completo se a mediana
  de `trocas_por_minuto` for ≥ 6 e ≥ 80 % das faixas tiverem
  `n_acordes_distintos ≥ 2`. Se não, o IDMT-SMT-Guitar é reportado como teste
  do **classificador**, e as conclusões sobre Viterbi, `CHANGE_PENALTY` e
  `MIN_DUR` não se estendem a ele.
- **Vocabulário:** as faixas são todas avaliadas. `pct_fora` agregado é
  reportado ao lado da acurácia. Nenhuma faixa é excluída por ter acordes fora
  do vocabulário.
- **Exclusão:** só por defeito da anotação (desalinhamento, arquivo corrompido,
  anotação ausente), registrada no manifest.

## 6. Execução e análise

1. `python runner.py --manifest data/manifests/idmt_smt_guitar.csv --splits ext --variants V4,C,D,E,F0rg,D0rg`
   — **uma vez**. Sem `--ref-layer`: o IDMT tem uma camada só.
2. Commit do CSV e do `_meta.json` antes de abrir os números.
3. `stats.py` sobre o CSV externo: os mesmos pares e o mesmo critério de decisão
   de `CONGELAMENTO.md` §5.1 (IC 95 % bootstrap pareado, semente 0, Holm),
   **dentro** do corpus externo.
4. GuitarSet `test` × IDMT **não** é comparação pareada (faixas diferentes).
   É reportada de forma descritiva: média ponderada por duração e IC bootstrap
   de cada corpus, lado a lado, e se a **ordem** das configurações se mantém.
5. Estratificação descritiva por `guitar_id`, `tempo`, `genre` e `capture`.
   Exploratória: não entra na família de Holm e é rotulada como tal.
6. Métricas: as mesmas do runner (`root`, `majmin`, `mirex`, `sevenths`,
   `seg`, `overseg`, e as versões sobre tempo rotulado).

## 7. Guitar-TECHS (opcional)

Só entra se houver tempo **e** se a derivação do ground truth for aceita antes
de ver qualquer resultado:

- o rótulo de acorde é derivado do MIDI por corda, por um algoritmo escrito e
  testado em `dataset_io.py` (janela, conjunto de classes de altura ativas,
  casamento com o template Harte, regra para quando nada casa);
- o algoritmo é validado nas gravações da categoria *Chords*, onde o acorde
  tocado é conhecido pelo nome do arquivo;
- o artigo diz explicitamente que esse ground truth é derivado, e não anotado
  por um humano.

Ganho específico: as mesmas execuções em DI e em microfone permitem medir
quanto do erro vem da cadeia de captação. Licença CC BY 4.0.

## 8. Ameaças à validade (texto para o artigo)

- A captação é quase toda em linha (DI), enquanto o GuitarSet usa microfone. Se
  houver queda, parte dela pode vir da captação e não do corpus.
- Guitarra elétrica e violão acústico têm espectros harmônicos diferentes.
- `change_penalty`, `temp` e `ext_sharpness` nunca foram variados
  (`CONGELAMENTO.md` §4). O cross-corpus não os valida; só verifica se os
  valores fixos continuam funcionando.
- Acordes fora do MEDIUM contam como erro para o sistema, que não tem como
  acertá-los. `pct_fora` delimita esse teto.

## 9. Entregáveis

- `data/manifests/idmt_smt_guitar.csv`
- `data/results/audit_idmt_smt_guitar.csv`
- `data/results/ablation_<timestamp>_ext.csv` + `_meta.json`
- `data/results/stats_ext_<timestamp>.csv` + `_meta.json`
- Seção "Generalização entre corpora" em `artigo-ACDSA/RESULTADOS.md` e
  `METODOLOGIA.md`, com as tabelas geradas por script a partir desses CSVs.

## 10. Ordem das tarefas (um commit cada)

1. Adaptador `load_idmt_guitar` + testes com um arquivo sintético de fixture.
2. `runner.py` despachando o loader pelo campo `dataset`; `ext` em
   `SPLITS_PROTEGIDOS`. Oráculo verificado.
3. Geração do manifest + registro no `DATASETS.md`.
4. `audit_ext.py` + CSV da auditoria + veredito da §5 escrito aqui.
5. Execução única do `ext` + commit do CSV.
6. `stats.py` no `ext` + commit.
7. Tabelas, figuras e texto no `artigo-ACDSA/`.
