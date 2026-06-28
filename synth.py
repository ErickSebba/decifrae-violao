"""
synth.py
========
Gerador sintético de acordes a partir de série harmônica.

POR QUE NÃO SENÓIDE PURA: três senóides puras dão um chroma quase perfeito e o
classificador acerta sempre -- não testa nada. O mundo real quebra por causa
dos HARMÔNICOS. O 7º harmônico de C (~7*Cf) cai perto de Bb; é literalmente por
isso que Cmaj é confundido com C7. Aqui controlamos n_harmonics para varrer
exatamente esse efeito.

Funções principais:
  - synth_chord(...)  -> gera o áudio (waveform) de um acorde
  - synth_pause(...)  -> gera um trecho de "pausa" (quase silêncio + ruído leve)
  - midi_to_freq / pc_to_midi -> utilidades de afinação
"""

import numpy as np
from chord_templates import chord_pitch_classes

A4_FREQ = 440.0
A4_MIDI = 69


def midi_to_freq(midi, detune_cents=0.0):
    """MIDI -> frequência (Hz), com desafinação opcional em cents."""
    return A4_FREQ * 2.0 ** ((midi - A4_MIDI + detune_cents / 100.0) / 12.0)


def pc_to_midi(pitch_class, octave=4):
    """
    Pitch class (0-11, C=0) + oitava -> número MIDI.
    octave=4 -> C4 = MIDI 60 (dó central).
    """
    return 12 * (octave + 1) + pitch_class


def synth_note(freq, sr, dur, n_harmonics=6, decay=0.6,
               amp=1.0, fade=0.01):
    """
    Sintetiza UMA nota como soma de harmônicos com decaimento.

    sig(t) = sum_{h=1..H} decay^(h-1) * sin(2*pi*h*f*t)

    n_harmonics=1 -> senóide pura (caso 'fácil', controle).
    n_harmonics>=6 -> espectro rico, surge o vazamento harmônico.
    """
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    sig = np.zeros_like(t)
    for h in range(1, n_harmonics + 1):
        sig += (decay ** (h - 1)) * np.sin(2 * np.pi * freq * h * t)

    # envelope de ataque/release suave pra evitar cliques nas bordas
    n_fade = max(1, int(sr * fade))
    env = np.ones_like(sig)
    ramp = np.linspace(0, 1, n_fade)
    env[:n_fade] = ramp
    env[-n_fade:] = ramp[::-1]

    return amp * env * sig


def synth_chord(root_pc, suffix, sr=22050, dur=2.0,
                base_octave=3, n_harmonics=6, decay=0.6,
                spread_octaves=True, detune_cents=0.0,
                normalize=True):
    """
    Sintetiza o áudio de um acorde somando suas notas.

    Parameters
    ----------
    root_pc : int        tônica (0-11)
    suffix  : str        tipo do acorde (chave de CHORD_TYPES)
    base_octave : int    oitava da tônica
    n_harmonics : int    nº de harmônicos por nota (varredura do 'dificuldade')
    spread_octaves : bool
        Se True, distribui as notas em oitavas como um voicing real
        (tônica grave, demais acima) em vez de tudo na mesma oitava.
    detune_cents : float
        Desafina TODAS as notas (simula instrumento fora de tom).

    Returns
    -------
    y : np.ndarray   waveform mono
    """
    pcs = chord_pitch_classes(root_pc, suffix)
    n_samples = int(sr * dur)
    y = np.zeros(n_samples)

    for k, pc in enumerate(pcs):
        # voicing: tônica na base_octave; notas seguintes sobem de oitava
        # quando "dão a volta" abaixo da tônica, imitando um dedilhado real.
        octave = base_octave
        if spread_octaves:
            # garante ordem ascendente de altura
            if pc < pcs[0]:
                octave += 1
            if k >= 3:  # 4ª nota (tétrades) sobe mais
                octave += 1
        midi = pc_to_midi(pc, octave)
        freq = midi_to_freq(midi, detune_cents)
        # nota grave (tônica) um pouco mais forte, como num acorde tocado
        amp = 1.0 if k == 0 else 0.85
        note = synth_note(freq, sr, dur, n_harmonics=n_harmonics,
                          decay=decay, amp=amp)
        if len(note) < n_samples:
            note = np.pad(note, (0, n_samples - len(note)))
        y += note[:n_samples]

    if normalize:
        peak = np.max(np.abs(y)) + 1e-9
        y = y / peak * 0.9
    return y


def synth_pause(sr=22050, dur=1.0, noise_level=0.01, seed=None):
    """
    Trecho de 'pausa' entre acordes: quase silêncio + ruído leve.

    É o caso que testa se o classificador rotula QUALQUER ruído como acorde.
    O classificador correto deve devolver 'N' (sem acorde) aqui.

    noise_level : amplitude RMS aproximada do ruído (0.01 = bem baixo).
    """
    rng = np.random.default_rng(seed)
    n = int(sr * dur)
    return rng.normal(0, noise_level, n)


if __name__ == "__main__":
    import soundfile as sf
    sr = 22050
    # C maior com poucos harmônicos vs muitos
    y_easy = synth_chord(0, '', sr=sr, dur=1.5, n_harmonics=1)
    y_hard = synth_chord(0, '', sr=sr, dur=1.5, n_harmonics=8)
    print("C (1 harm) RMS:", np.sqrt(np.mean(y_easy**2)).round(3))
    print("C (8 harm) RMS:", np.sqrt(np.mean(y_hard**2)).round(3))
    pause = synth_pause(sr=sr, dur=1.0, noise_level=0.01)
    print("Pausa RMS:", np.sqrt(np.mean(pause**2)).round(4))
    print("OK: síntese rodando.")
