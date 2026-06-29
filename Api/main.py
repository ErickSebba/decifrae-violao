# API com FastAPI
import os
import tempfile
import shutil
from fastapi import FastAPI, UploadFile, File, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware

from app.audio_processing import detectar_acordes
from app.audio_processing_baixo import pipeline_completo

API_KEY = os.getenv("API_KEY")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://www.decifrae.com.br", "https://decifrae.com.br"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CHUNK_SIZE = 1024 * 1024  # 1 MB
FORMATOS_SUPORTADOS = (".wav", ".mp3", ".ogg", ".m4a")


def _validar_request(api_key: str, filename: str) -> None:
    """Valida API key e formato do arquivo. Levanta HTTPException em caso de erro."""
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API_KEY não configurada")
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="API Key inválida")
    if not filename.lower().endswith(FORMATOS_SUPORTADOS):
        raise HTTPException(status_code=400, detail="Formato não suportado")


def _salvar_upload(file: UploadFile) -> str:
    """Persiste o upload em um arquivo temporário e retorna o caminho."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        shutil.copyfileobj(file.file, tmp)
        return tmp.name


# ── Warmup ────────────────────────────────────────────────────────────────────

@app.get("/_warmup")
def warmup_audio():
    import numpy as np
    import librosa

    y  = np.zeros(22050)
    sr = 22050
    librosa.feature.chroma_stft(y=y, sr=sr)
    return {"warm": True}


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


# ── Acordes ──────────────────────────────────────────────────────────────────

@app.post("/process-audio")
async def process_audio(
    file: UploadFile = File(...),
    x_api_key: str = Header(None),
):
    """Detecta acordes em um arquivo de áudio."""
    _validar_request(x_api_key, file.filename)

    tmp_path = None
    try:
        tmp_path = _salvar_upload(file)
        return detectar_acordes(tmp_path)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


# ── Baixo ─────────────────────────────────────────────────────────────────────

@app.post("/process-bass")
async def process_bass(
    file: UploadFile = File(...),
    x_api_key: str = Header(None),
    num_cordas: int = 5,
    prob_min: float = 0.6,
):
    """
    Transcreve a linha de baixo de um arquivo de áudio.

    Retorna segmentos de nota, caminho ótimo no braço e tablatura ASCII.
    - `num_cordas`: 4 ou 5 (padrão: 5)
    - `prob_min`: limiar de probabilidade de voicing do pYIN (0–1, padrão: 0.6).
      Valores mais altos = menos notas detectadas mas com mais confiança.
    """
    _validar_request(x_api_key, file.filename)

    if num_cordas not in (4, 5):
        raise HTTPException(status_code=400, detail="num_cordas deve ser 4 ou 5")
    if not (0.0 < prob_min <= 1.0):
        raise HTTPException(status_code=400, detail="prob_min deve estar entre 0 e 1")

    tmp_path = None
    try:
        tmp_path = _salvar_upload(file)
        resultado = pipeline_completo(tmp_path, plotar=False, num_cordas=num_cordas, prob_min=prob_min)
        if not resultado:
            raise HTTPException(status_code=422, detail="Nenhuma nota detectada no áudio")
        return resultado
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)