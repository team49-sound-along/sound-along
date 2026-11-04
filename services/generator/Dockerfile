# Build from the project root:  docker build --platform linux/arm64 -f services/generator/Dockerfile -t sound-along-generator .
# ReadWorks' technical document requires Python 3.14 (a supported Lambda runtime). Kokoro declares support for 3.10 to
# 3.12 only, so it is installed with --ignore-requires-python and proven by scripts/smoke_generator_image.sh.
ARG PYTHON_VERSION=3.14
FROM public.ecr.aws/lambda/python:${PYTHON_VERSION}

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

# CPU-only PyTorch first (official CPU index), then everything else from PyPI.
COPY services/generator/requirements.txt /tmp/requirements.txt
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.15.0 \
 && pip install --ignore-requires-python -r /tmp/requirements.txt

# spaCy model used by misaki (G2P). Fetched at build time and verified; never downloaded at runtime.
ARG SPACY_MODEL_URL=https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl
ARG SPACY_MODEL_SHA256=1932429db727d4bff3deed6b34cfc05df17794f4a52eeb26cf8928f7c1a0fb85
RUN curl -fsSL -o /tmp/en_core_web_sm-3.8.0-py3-none-any.whl "$SPACY_MODEL_URL" \
 && echo "$SPACY_MODEL_SHA256  /tmp/en_core_web_sm-3.8.0-py3-none-any.whl" | sha256sum -c - \
 && pip install /tmp/en_core_web_sm-3.8.0-py3-none-any.whl \
 && rm -f /tmp/en_core_web_sm-3.8.0-py3-none-any.whl

# Bake Kokoro-82M weights and voices, and the Phonon model with its four voices, into the image (pinned revisions).
ENV HF_HOME=/opt/hf
COPY services/generator/bake_model.py /tmp/bake_model.py
RUN python /tmp/bake_model.py && rm /tmp/bake_model.py
# Lambda hides /sys/devices/system/cpu, so PyTorch cannot count CPUs: fix the thread pools instead (see synth/engine.py configure_torch).
ENV OMP_NUM_THREADS=2 TORCH_THREADS=2
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PHONON_MODEL_DIR=/opt/phonon/model PHONON_VOICES_DIR=/opt/phonon/voices TRANSLATE_MODELS_DIR=/opt/translate POSSESSIVE_LM_DIR=/opt/lm/smollm2-135m

# Whole directories, not file lists: a new module can no longer be forgotten (tests and caches are excluded by
# Dockerfile.dockerignore). The synth and parse folders are the same code the local CLI runs.
COPY services/parse/ ${LAMBDA_TASK_ROOT}/parse/
COPY services/synth/ ${LAMBDA_TASK_ROOT}/synth/
COPY services/generator/*.py ${LAMBDA_TASK_ROOT}/

CMD ["handler.handler"]
