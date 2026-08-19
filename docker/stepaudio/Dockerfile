FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3-pip python3.10-venv \
    git git-lfs ffmpeg libsndfile1 ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN python3.10 -m pip install --upgrade pip setuptools wheel

RUN python3.10 -m pip install \
    torch==2.3.1 torchaudio==2.3.1 \
    --index-url https://download.pytorch.org/whl/cu121

RUN python3.10 -m pip install \
    transformers==4.49.0 \
    accelerate \
    safetensors \
    librosa \
    soundfile \
    numpy \
    pandas \
    pyarrow \
    pydantic \
    PyYAML \
    tqdm \
    huggingface_hub \
    scikit-learn

RUN git clone --depth 1 https://github.com/stepfun-ai/Step-Audio2.git /opt/Step-Audio2

ENV PYTHONPATH="/app/src:/opt/Step-Audio2:${PYTHONPATH}"

WORKDIR /app
COPY pyproject.toml /app/
COPY src /app/src
COPY scripts /app/scripts
COPY deploy /app/deploy

RUN python3.10 -m pip install -e . && \
    chmod +x /app/deploy/common/*.sh

CMD ["bash"]
