# Decifrae — Bench sintético de reconhecimento de acordes

Bancada de testes modular para medir e melhorar a acurácia do reconhecimento de
acordes, com foco em escalar das tríades para acordes de 4 notas (tétrades).

A ideia central: gerar acordes sintéticos com **série harmônica** (não senóide
pura), aplicar uma **bateria de ruídos** controlados, classificar e montar uma
**matriz de confusão por condição** — descobrindo *onde* o algoritmo falha.

## Módulos

| Arquivo | Papel |
|---|---|
| `chord_templates.py` | Vocabulário de acordes + templates binários de 12 dim. Base de tudo. |
| `synth.py` | Síntese de acordes por série harmônica + geração de pausas. |
| `noise.py` | Bateria de ruídos: branco, rosa, desafinação, percussão, reverb. |
| `classifier.py` | Classificador por **cosseno** + `emission()` (p/ Viterbi) + gates. |
| `viterbi.py` | Suavização temporal por **Viterbi/HMM** sobre as emissões de cosseno. |
| `pipeline.py` | Segmentação por **beat-sync** (igual V4) + classificação + Viterbi. |
| `musicas.py` | Analisa a pasta `Musicas/` e gera timeline por faixa. |
| `bench.py` | Motor do bench: matriz de confusão, teste de pausa, varredura. |
| `run_bench.py` | Bench sintético: compara **cosseno vs V4**. |
| `legacy_v4.py` | Seu **V4 + comparar_metodos preservados** e intocados (baseline). |

## Como rodar

```bash
pip install librosa numpy scipy scikit-learn matplotlib soundfile
python3 run_bench.py        # bench sintético (cosseno vs V4)
python3 musicas.py          # analisa Musicas/ -> out/musicas/*.png
```

Coloque os áudios em `Musicas/`. A timeline e o log de acordes saem por faixa.

## Pipeline de análise de faixa (musicas.py)

Ordem: **HPSS → beat-sync chroma → cosseno (emissão) → Viterbi → mescla**.

Pontos-chave da V2 (frente à primeira versão do musicas.py):
- **Beat-sync**: o chroma é extraído UMA vez no áudio inteiro e sincronizado
  por batida (como o V4). Isso acabou com os segmentos de ~22ms e os avisos
  `n_fft too large` que vinham de extrair chroma de pedacinhos.
- **Viterbi**: colapsa o flicker (ex.: `G / Gmaj7 / Gsus2` viram um `G` limpo).
  A penalidade de troca é **fixa** (independente do tamanho do vocabulário),
  evitando o "acorde preso" que acontece com matriz de transição normalizada.
- **Estado N ajustável**: silêncio real vira N (gate de RMS por segmento), mas
  mix densa (violão + voz, tipo Tempo_Perdido) volta a receber acordes em vez
  de "tudo N" — sem depender do gate fixo de 0.72.
- **Bug corrigido**: não há mais HPSS duplicado.

Parâmetros no topo de `musicas.py`:
- `CHANGE_PENALTY` (≈2.0): maior = timeline mais suave/grudenta.
- `TEMP` (≈0.1): menor = emissão mais decidida.
- `N_LOGPROB` (≈-2.5): mais negativo = N só em silêncio real.
- `REL_GATE` (≈0.2): silêncio = RMS abaixo de 20% da MEDIANA da faixa. É
  RELATIVO ao nível da gravação -- foi o que destravou o Tempo_Perdido, que
  é silencioso (RMS ~0.01) e um gate absoluto marcava 100% como N.
- `MIN_DUR` (≈0.8): absorve segmentos curtos (blips de transição) no vizinho.
- `complexity_penalty` (no CLF, ≈0.06): viés pró-tríade. Suprime o flicker
  maj7/7 que vem de cordas soltas ressoando. Para repertório com tétrades
  reais (jazz/MPB), reduza p/ ~0.02 ou 0. **No classificador o default é 0**
  (p/ o bench medir cosseno puro); o viés é setado só na instância do musicas.

Vocabulário atual: **MEDIUM** (maior, menor, 7, maj7, m7).

## Resultados em áudio real (violão)

Com o pipeline acima nas faixas de teste:
- **Tempo_Perdido** (cifra C Am Bm Em em loop): reconhecido como N (intro) +
  três ciclos limpos de C Am Bm Em. A faixa que antes saía 100% N.
- **Sol_1** (G): N (intro) + G limpo, sem flicker.
- **TrocaDeAcordes** (C G A F): C, G, A, F na ordem, com pequenos resíduos de
  transição (~0.9s) nas bordas de troca.


## O que o bench já revelou

1. **Cosseno escala para tétrades; V4 não.** O V4 só conhece maior/menor, então
   em qualquer acorde de 4 notas ele devolve uma tríade. O cosseno acerta 7,
   maj7, m7, m6, dim, sus2 a 100% sem nenhum bias manual — é o efeito da
   auto-normalização pela norma do template.

2. **Ambiguidades harmônicas reais (não são bugs).** Alguns acordes têm o
   *mesmo conjunto de notas* e o chroma (que dobra oitavas e descarta o baixo)
   não consegue separá-los:
   - `Csus4 = Fsus2`  ({C,F,G})
   - `C6 = Am7`       ({C,E,G,A})
   - `Cm7b5 = Ebm6`   ({C,Eb,Gb,Bb})
   - Acordes simétricos: `aug` (3 raízes equivalentes → ~33%), `dim7` (4 →
     ~25%). O bench confirma a teoria: a ambiguidade é exatamente o fator de
     simetria. **Solução:** detecção de baixo/raiz (conecta com o módulo de
     baixo / PYIN).

3. **Gate de "sem acorde" funciona.** Nas pausas com ruído crescente, o cosseno
   mantém 0% de falso-positivo; o V4 começa a alucinar acordes a partir de ruído
   moderado (~37% em ruído 0.02, 100% em 0.05), porque não tem detecção real de
   silêncio.

4. **Cosseno é robusto ao vazamento harmônico.** Na varredura de 1 a 12
   harmônicos a acurácia se mantém em 100% (maj/m/7/maj7) — o cosseno não cai
   no maj→7 que derrubaria um scoring por soma de energia.

## Próximos passos sugeridos

- Detecção de raiz/baixo para quebrar as ambiguidades de rotação e simetria.
- Suavização por Viterbi/HMM sobre as emissões de cosseno (sequência temporal).
- Validar em áudio real rotulado (ex.: `TrocaDeAcordes(C-G-A-F).wav`) com
  `mir_eval.chord` para um número comparável/publicável (TCC).
