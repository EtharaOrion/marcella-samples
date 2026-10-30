# syntax=docker/dockerfile:1.10@sha256:865e5dd094beca432e8c0a1d5e1c465db5f998dca4e439981029b3b81fb39ed5
FROM --platform=$BUILDPLATFORM ghcr.io/astral-sh/uv:0.11.28@sha256:0f36cb9361a3346885ca3677e3767016687b5a170c1a6b88465ec14aefec90aa AS uv
FROM --platform=$BUILDPLATFORM python:3.12-slim-bookworm@sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70 AS build
ARG TARGETOS
ARG TARGETARCH
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /build
COPY requirements.lock.txt /build/requirements.lock.txt
RUN case "$TARGETARCH" in amd64) plat=x86_64-manylinux_2_28 ;; arm64) plat=aarch64-manylinux_2_28 ;; *) echo "unsupported $TARGETOS/$TARGETARCH" >&2; exit 1 ;; esac \
 && uv pip install --no-cache --require-hashes --only-binary=:all: --python-version=3.12 --python-platform="$plat" --target=/opt/site -r /build/requirements.lock.txt

FROM python:3.12-slim-bookworm@sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70 AS runtime
LABEL org.opencontainers.image.source="https://github.com/EtharaOrion/marcella" \
      org.opencontainers.image.revision="b88fc934d744ed77453028976d943ff8aef7b767" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.base.name="docker.io/library/python:3.12-slim-bookworm" \
      org.opencontainers.image.base.digest="sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70"
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
COPY --from=build /opt/site /opt/site
ENV PYTHONPATH=/opt/site PATH=/opt/site/bin:$PATH PYTHONDONTWRITEBYTECODE=1 LITELLM_LOCAL_MODEL_COST_MAP=True
RUN groupadd -g 1000 grader && useradd -u 1000 -g 1000 -M -s /usr/sbin/nologin grader
COPY --chmod=0555 test.sh /tests/test.sh
COPY --chmod=0444 test_output.py reward.toml judge.toml reference.md judge_not_called.py.in /tests/
# The private key lives outside /tests, read-only, so no scan of /tests ever reads it as a scoring input.
COPY --chmod=0444 key/ /opt/mrd-key/
RUN chmod -R a-w,a+rX /opt/mrd-key
WORKDIR /tests
USER 1000:1000
CMD ["/bin/bash"]
