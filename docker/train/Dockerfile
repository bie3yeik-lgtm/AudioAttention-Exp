FROM nvcr.io/nvidia/pytorch:25.07-py3

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH="/app/src:${PYTHONPATH}"

WORKDIR /app

COPY pyproject.toml /app/
COPY src /app/src
COPY scripts /app/scripts
COPY deploy /app/deploy

RUN python -m pip install --upgrade pip && \
    python -m pip install -e . && \
    chmod +x /app/deploy/common/*.sh

CMD ["bash"]
