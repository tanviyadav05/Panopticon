# llm-core/docker/sandbox.Dockerfile
#
# A slightly more useful sandbox image than bare python:3.12-slim (the
# default in agents_config.yaml's tools.code_sandbox.image) — pre-installs
# the packages Coder-agent-generated code most often reaches for, so
# "write a script to analyze this data" doesn't fail on a missing numpy
# import inside a container that has no network access to pip install it.
#
# Build once:
#   docker build -t panopticon/code-sandbox:latest -f sandbox.Dockerfile .
#
# Then point agents_config.yaml's tools.code_sandbox.image at
# "panopticon/code-sandbox:latest" instead of "python:3.12-slim".
#
# Still runs with network_disabled=True at the container level (see
# tools/code_sandbox.py) — pre-installing packages at build time (when the
# image DOES have network access) is what makes that compatible with
# actually useful sandboxed code, rather than forcing every script to be
# stdlib-only.

FROM python:3.12-slim

RUN pip install --no-cache-dir \
    numpy==2.4.4 \
    pandas==3.0.2 \
    requests==2.33.1 \
    matplotlib==3.10.8

# Non-root user — defense in depth on top of network_disabled + mem_limit,
# in case a future change ever runs this image without those flags.
RUN useradd --no-create-home --shell /usr/sbin/nologin sandbox
USER sandbox

WORKDIR /sandbox
