"""
noise.py
========
Bateria de ruídos / degradações aplicadas ao áudio antes da classificação.

Cada função recebe um waveform y e devolve uma versão degradada. O objetivo é
estressar o classificador em condições controladas e descobrir ONDE ele quebra:

  - add_white_noise / add_pink_noise : ruído aditivo a um SNR alvo
  - detune                           : instrumento fora de afinação (cents)
  - add_percussive                   : transientes percussivos (testa o HPSS)
  - reverb_tail                       : cauda de reverberação simples
  - apply_condition                   : dispatcher por nome de condição

As "condições" são (nome, kwargs) e ficam catalogadas em DEFAULT_CONDITIONS,
que o bench varre para montar uma matriz de confusão por condição.
"""

import numpy as np
import librosa


def _rms(x):
    return np.sqrt(np.mean(x ** 2) + 1e-12)


def add_white_noise(y, snr_db=20.0, seed=None):
    """Ruído branco gaussiano a um SNR (dB) alvo."""
    rng = np.random.default_rng(seed)
    sig_power = np.mean(y ** 2) + 1e-12
    noise_power = sig_power / (10 ** (snr_db / 10.0))
    noise = rng.normal(0, np.sqrt(noise_power), len(y))
    return y + noise


def add_pink_noise(y, snr_db=20.0, seed=None):
    """
    Ruído rosa (1/f) -- mais realista que branco para ambientes acústicos.
    Gerado por filtragem simples no domínio da frequência.
    """
    rng = np.random.default_rng(seed)
    n = len(y)
    white = rng.normal(0, 1, n)
    # filtro 1/sqrt(f) no espectro
    spectrum = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n)
    freqs[0] = freqs[1] if len(freqs) > 1 else 1.0
    spectrum = spectrum / np.sqrt(freqs)
    pink = np.fft.irfft(spectrum, n)
    pink = pink / (_rms(pink) + 1e-12)

    sig_power = np.mean(y ** 2) + 1e-12
    noise_power = sig_power / (10 ** (snr_db / 10.0))
    pink = pink * np.sqrt(noise_power)
    return y + pink


def detune(y, sr, cents=20.0):
    """Desafina o sinal inteiro por 'cents' (pitch shift)."""
    if abs(cents) < 1e-6:
        return y
    return librosa.effects.pitch_shift(y=y, sr=sr, n_steps=cents / 100.0)


def add_percussive(y, sr, n_hits=4, amp=0.4, seed=None):
    """
    Adiciona batidas percussivas (clicks de banda larga) ao longo do sinal.
    Serve pra testar o quanto o HPSS consegue isolar a harmonia depois.
    """
    rng = np.random.default_rng(seed)
    out = y.copy()
    n = len(y)
    for _ in range(n_hits):
        pos = rng.integers(0, max(1, n - sr // 10))
        dur = sr // 20  # ~50 ms
        click = rng.normal(0, 1, dur) * np.exp(-np.linspace(0, 8, dur))
        out[pos:pos + dur] += amp * click
    return out


def reverb_tail(y, sr, decay=0.3, delay_ms=80):
    """Reverberação simples: soma de ecos decaindo."""
    out = y.copy()
    delay = int(sr * delay_ms / 1000.0)
    for k in range(1, 4):
        d = delay * k
        if d < len(y):
            out[d:] += (decay ** k) * y[:len(y) - d]
    peak = np.max(np.abs(out)) + 1e-9
    return out / peak * 0.9


# --------------------------------------------------------------------------
# Dispatcher por condição nomeada
# --------------------------------------------------------------------------
def apply_condition(y, sr, name, **kwargs):
    """Aplica uma condição de ruído pelo nome."""
    if name == 'clean':
        return y
    if name == 'white':
        return add_white_noise(y, **kwargs)
    if name == 'pink':
        return add_pink_noise(y, **kwargs)
    if name == 'detune':
        return detune(y, sr, **kwargs)
    if name == 'percussive':
        return add_percussive(y, sr, **kwargs)
    if name == 'reverb':
        return reverb_tail(y, sr, **kwargs)
    raise ValueError(f"Condição desconhecida: {name}")


# Catálogo padrão de condições que o bench varre.
# Cada item: (rótulo, nome_da_condição, kwargs)
DEFAULT_CONDITIONS = [
    ('clean',         'clean',      {}),
    ('white_30dB',    'white',      {'snr_db': 30.0}),
    ('white_15dB',    'white',      {'snr_db': 15.0}),
    ('white_5dB',     'white',      {'snr_db': 5.0}),
    ('pink_15dB',     'pink',       {'snr_db': 15.0}),
    ('detune_25c',    'detune',     {'cents': 25.0}),
    ('detune_50c',    'detune',     {'cents': 50.0}),
    ('percussive',    'percussive', {'n_hits': 5, 'amp': 0.4}),
    ('reverb',        'reverb',     {'decay': 0.35}),
]


if __name__ == "__main__":
    from V1.synth import synth_chord
    sr = 22050
    y = synth_chord(0, '', sr=sr, dur=1.5, n_harmonics=6)
    for label, name, kw in DEFAULT_CONDITIONS:
        yd = apply_condition(y, sr, name, **kw)
        print(f"{label:14s} -> RMS {_rms(yd):.3f}  len {len(yd)}")
    print("OK: bateria de ruídos rodando.")
