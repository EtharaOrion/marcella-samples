# syntax=docker/dockerfile:1.10@sha256:865e5dd094beca432e8c0a1d5e1c465db5f998dca4e439981029b3b81fb39ed5
FROM --platform=$BUILDPLATFORM ghcr.io/astral-sh/uv:0.11.28@sha256:0f36cb9361a3346885ca3677e3767016687b5a170c1a6b88465ec14aefec90aa AS uv
FROM --platform=$BUILDPLATFORM python:3.12-slim-bookworm@sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70 AS build
ARG TARGETOS
ARG TARGETARCH
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /build
COPY requirements.lock.txt /build/
# The task stack goes to /opt/site. Only FlowIO, pure Python, builds from source.
RUN case "$TARGETARCH" in amd64) plat=x86_64-manylinux_2_28 ;; arm64) plat=aarch64-manylinux_2_28 ;; *) echo "unsupported $TARGETOS/$TARGETARCH" >&2; exit 1 ;; esac \
 && uv pip install --no-cache --require-hashes --only-binary=:all: --no-binary=flowio --python-version=3.12 --python-platform="$plat" --target=/opt/site -r /build/requirements.lock.txt

# Claude Code 2.1.312 and Codex 0.165.0, the official native builds on the npm registry, pre-baked because the agent
# network is closed (contract agent_runtime): each tarball is checked against a pinned sha256 before extraction, and
# Codex keeps its package layout because its binary finds the bundled rg and bwrap beside it.
FROM --platform=$BUILDPLATFORM python:3.12-slim-bookworm@sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70 AS agents
ARG TARGETARCH
RUN python3 - <<'PY'
import hashlib
import os
import tarfile
import tempfile
import urllib.request
from pathlib import Path

NPM = "https://registry.npmjs.org"
PINS = {
    "amd64": {
        "claude": (f"{NPM}/@anthropic-ai/claude-code-linux-x64/-/claude-code-linux-x64-2.1.312.tgz",
                   "f1c3d923ff3ac7e7080b8b9c638833dde72feab15e46940a65a0122d728c6bfd"),
        "codex": (f"{NPM}/@openai/codex/-/codex-0.165.0-linux-x64.tgz",
                  "f997cd6ef5987126e19cd3c82e847a4a6461270f32f97340c5e99a65fb6f9b8a"),
        "triple": "x86_64-unknown-linux-musl",
    },
    "arm64": {
        "claude": (f"{NPM}/@anthropic-ai/claude-code-linux-arm64/-/claude-code-linux-arm64-2.1.312.tgz",
                   "3aa8e624d35e8a77a851e7009b83ae95d3168f24f1afdb0a1ed580a2313d9e5c"),
        "codex": (f"{NPM}/@openai/codex/-/codex-0.165.0-linux-arm64.tgz",
                  "c9955808e3598198afe1b8525b5864c0e3f2477339d26e91924e95ed45473baf"),
        "triple": "aarch64-unknown-linux-musl",
    },
}[os.environ["TARGETARCH"]]
OUT = Path("/out")


def fetch(url, sha256):
    digest = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=600) as response, tempfile.NamedTemporaryFile(delete=False) as tmp:
        for chunk in iter(lambda: response.read(1 << 20), b""):
            digest.update(chunk)
            tmp.write(chunk)
    if digest.hexdigest() != sha256:
        raise SystemExit(f"sha256 mismatch for {url}: got {digest.hexdigest()}, pinned {sha256}")
    return tmp.name


with tarfile.open(fetch(*PINS["claude"])) as tf:
    member = tf.getmember("package/claude")
    member.name = "usr/local/bin/claude"
    tf.extract(member, OUT, filter="data")

prefix = f"package/vendor/{PINS['triple']}/"
with tarfile.open(fetch(*PINS["codex"])) as tf:
    members = [m for m in tf.getmembers() if m.name.startswith(prefix) and m.name != prefix.rstrip("/")]
    for m in members:
        m.name = "opt/codex/" + m.name[len(prefix):]
    tf.extractall(OUT, members=members, filter="data")
(OUT / "usr/local/bin/codex").symlink_to("/opt/codex/bin/codex")
PY

FROM python:3.12-slim-bookworm@sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70 AS runtime
LABEL org.opencontainers.image.source="https://github.com/EtharaOrion/marcella" \
      org.opencontainers.image.revision="b88fc934d744ed77453028976d943ff8aef7b767" \
      org.opencontainers.image.licenses="CC-BY-4.0" \
      org.opencontainers.image.base.name="docker.io/library/python:3.12-slim-bookworm" \
      org.opencontainers.image.base.digest="sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70"
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
# curl, procps and ripgrep come from a dated Debian snapshot so the image is reproducible; procps and ripgrep are
# the system packages Harbor's own installers add for these two agents.
RUN printf 'Types: deb\nURIs: http://snapshot.debian.org/archive/debian/20261020T000000Z\nSuites: bookworm bookworm-updates\nComponents: main\nSigned-By: /usr/share/keyrings/debian-archive-keyring.gpg\n\nTypes: deb\nURIs: http://snapshot.debian.org/archive/debian-security/20261020T000000Z\nSuites: bookworm-security\nComponents: main\nSigned-By: /usr/share/keyrings/debian-archive-keyring.gpg\n' > /etc/apt/sources.list.d/debian.sources \
 && apt-get -o Acquire::Check-Valid-Until=false update \
 && apt-get install -y --no-install-recommends curl procps ripgrep \
 && rm -rf /var/lib/apt/lists/*
COPY --from=build /opt/site /opt/site
COPY --from=agents /out/ /
# The system interpreter reaches the task stack through a .pth file, never PYTHONPATH.
RUN echo /opt/site > /usr/local/lib/python3.12/site-packages/opt-site.pth
ENV PATH=/opt/site/bin:$PATH PYTHONDONTWRITEBYTECODE=1
RUN groupadd -g 1001 agent && useradd -u 1001 -g 1001 -m -s /bin/bash agent && mkdir -p /app && chown 1001:1001 /app
COPY data/ /data/
WORKDIR /app
USER 1001:1001
CMD ["/bin/bash"]
