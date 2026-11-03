# Build from the project root:  docker build --platform linux/arm64 -f services/generator/Dockerfile -t sound-along-generator .
FROM public.ecr.aws/lambda/python:3.12

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

# CPU-only PyTorch first (official CPU index), then everything else from PyPI.
COPY services/generator/requirements.txt /tmp/requirements.txt
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.15.0 \
 && pip install -r /tmp/requirements.txt

# spaCy model used by misaki (G2P). Fetched at build time and verified; never downloaded at runtime.
ARG SPACY_MODEL_URL=https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl
ARG SPACY_MODEL_SHA256=1932429db727d4bff3deed6b34cfc05df17794f4a52eeb26cf8928f7c1a0fb85
RUN curl -fsSL -o /tmp/en_core_web_sm-3.8.0-py3-none-any.whl "$SPACY_MODEL_URL" \
 && echo "$SPACY_MODEL_SHA256  /tmp/en_core_web_sm-3.8.0-py3-none-any.whl" | sha256sum -c - \
 && pip install /tmp/en_core_web_sm-3.8.0-py3-none-any.whl \
 && rm -f /tmp/en_core_web_sm-3.8.0-py3-none-any.whl

# Bake Kokoro-82M weights and the af_heart voice into the image (pinned revision).
ENV HF_HOME=/opt/hf
COPY services/generator/bake_model.py /tmp/bake_model.py
RUN python /tmp/bake_model.py && rm /tmp/bake_model.py
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

COPY services/parse/tokenizer.py ${LAMBDA_TASK_ROOT}/parse/
COPY services/synth/engine.py services/synth/pipeline.py services/synth/word_mapper.py services/synth/artifacts.py \
     services/synth/mastering.py services/synth/pronunciations.py services/synth/pronunciations.json \
     services/synth/engines.py services/synth/polly_engine.py ${LAMBDA_TASK_ROOT}/synth/
COPY services/generator/_bootstrap.py services/generator/audio.py services/generator/clients.py services/generator/dynamo.py \
     services/generator/engine_cache.py services/generator/handler.py services/generator/summary.py ${LAMBDA_TASK_ROOT}/

CMD ["handler.handler"]
