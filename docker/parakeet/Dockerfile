FROM nvcr.io/nvidia/nemo:25.07

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH="/app/src:${PYTHONPATH}"

WORKDIR /app

COPY pyproject.toml /app/
COPY src /app/src
COPY scripts /app/scripts

RUN python -m pip install --upgrade pip && \
    python -m pip install -e .

CMD ["bash"]
