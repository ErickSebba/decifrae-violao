# Revisões recebidas (texto integral)

Paper ID 1766 — *Disentangling Classical DSP-Based Automatic Chord
Recognition: Component Contributions and Coverage–Accuracy Trade-offs*

Os identificadores R2.1–R2.6 e R4 são usados em `CAMERA_READY.md` e
`RESPOSTA_REVISORES.md`; o texto abaixo é o original, sem edição.

---

## Reviewer #2

### R2.1 — Limited test-set diversity and statistical generalizability

The paper reports 58 test tracks but only two test performers (performers
04 and 05). Track-level bootstrap resampling does not capture variation
across independently sampled performers. Consequently, the confidence
intervals may characterize the observed tracks while providing limited
evidence about generalization to new guitarists.

Required revision: Add evaluation on more held-out performers, if feasible.
Otherwise, explicitly identify the findings as exploratory and
performer-conditional, and avoid broad claims about general ACR
performance.

### R2.2 — Reproducibility and implementation details

The manuscript describes the main stages and equations, but several
implementation choices remain insufficiently specified. The authors
themselves acknowledge uncertainty regarding CQT alignment,
initialization, numerical ties, and duration-filter edge cases.

Required revision: Provide a reproducible implementation or pseudocode,
software/library versions, exact dataset split and exclusions,
beat-to-chroma aggregation details, chord-template construction, and
deterministic tie-breaking rules. Specify how duration filtering handles
track edges, equal-length neighboring segments, and repeated reassignment.

### R2.3 — Isolation of component contributions

The C→D comparison is presented as an assessment of temporal decoding, but
Viterbi decoding also changes how the no-chord state is handled. The gate,
abstention mechanism, and decoder interact in determining which cells
receive labels. Therefore, the observed difference cannot automatically be
attributed to temporal continuity alone.

Required revision: Clarify precisely which mechanisms differ in each
ablation. Where possible, include factorial or matched-condition
experiments that separate temporal smoothing from abstention and gating
effects. Interpret the reported contrasts as configuration-level effects
when individual mechanisms cannot be isolated.

### R2.4 — Evaluation metrics and common-mask analysis

The common-mask analysis is a valuable methodological contribution.
However, the reported C–D common-mask difference is only +0.22 percentage
points, with a 95% confidence interval of [−1.74, 2.10]. This does not
establish a classification improvement or statistical equivalence.

Required revision: Define the common mask and its aggregation in a readily
reproducible manner. Report the number of tracks and total duration
retained, and discuss selection bias: the cells labeled by both systems
may be easier than cells on which either system abstains. Do not interpret
a nonsignificant result as proof that the systems are equivalent.

### R2.5 — Chord-vocabulary comparison and interpretation

The 24-template system cannot predict seventh chords, whereas the
60-template system can. The reported advantage of the smaller vocabulary
at the secondary annotation layer's sevenths metric is therefore partly a
consequence of the smaller system avoiding false seventh-chord
predictions. It does not show better recognition of seventh chords.

Required revision: Make the distinction between label-space restriction
and recognition quality more prominent. Report performance on the shared
major/minor label space, seventh-chord precision and recall where
appropriate, and the proportion of reference time belonging to chord
qualities that each vocabulary can represent.

### R2.6 — Baseline strength and comparison fairness

The study includes legacy baselines V4 and V4b, but their relationship to
the proposed pipeline and to established ACR systems is not sufficiently
clear from the experimental presentation. The manuscript also notes that
the same transition penalty is retained across vocabularies despite
different state spaces.

Required revision: Document the precise algorithms represented by V4 and
V4b, explain their parameter settings, and justify why the comparisons are
fair. If possible, include a stronger published or standard baseline and
assess sensitivity to vocabulary-specific transition calibration.

---

## Reviewer #4 (R4)

The main weaknesses of this article are as follows:

1. Limited generalizability due to dataset and performers: the experiments
and conclusions are based solely on the GuitarSet dataset, specifically
recordings from only two performers in the test split (performers 04 and
05). This limits the ability to generalize findings to other datasets,
recording conditions, performers, or broader populations of guitar music
or other instruments.
2. Conditional statistical interpretation: track-level bootstrap
resampling was used to estimate uncertainty, but it does not capture
variability between different performers. Because the test set contains
only two performers, statistical results are conditional on these specific
performers and do not represent population-level uncertainty.

To improve this article, we suggest the following points:

1. Please extend experiments to additional datasets beyond GuitarSet,
incorporating more performers, musical genres, and recording conditions to
assess the generalizability of findings and to enable statistical
inference beyond the observed performers. This would provide more reliable
estimates of uncertainty and performance variability and also help to
reduce performer-specific bias and capture broader acoustic and stylistic
variability.
2. Kindly conduct evaluations across multiple independent corpora to
verify that component effects and trade-offs hold consistently under
different annotation schemes and acoustic conditions.

In my opinion, this article could be accepted after minor revision.
