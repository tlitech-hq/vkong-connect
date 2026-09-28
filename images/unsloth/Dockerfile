# syntax=docker/dockerfile:1.7
# The base image supplies CUDA, the Unsloth runtime, and /opt/unsloth-venv.
# For the POC, build that image from the tlitech-hq/unsloth-vkong checkout first.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG BASE_IMAGE
ARG VENV=/opt/unsloth-venv
ARG UNSLOTH_FORK_COMMIT
ARG BRIDGE_BUILD_ID
ARG REMOTE_PLATFORM=linux/amd64

# Refuse a moving base or an abbreviated source identity before installation.
RUN case "${BASE_IMAGE}" in *@sha256:*) ;; *) exit 1 ;; esac \
 && test "${#UNSLOTH_FORK_COMMIT}" -eq 40 \
 && test -z "$(printf '%s' "${UNSLOTH_FORK_COMMIT}" | tr -d '0123456789abcdef')" \
 && test "${#BRIDGE_BUILD_ID}" -eq 40 \
 && test -z "$(printf '%s' "${BRIDGE_BUILD_ID}" | tr -d '0123456789abcdef')"

# BASE_IMAGE may have been assembled from the upstream-oriented core Dockerfile.
# Reinstall the TLI fork at an explicit immutable ref so the image identity does
# not depend on a misleading local tag.
RUN test -n "${UNSLOTH_FORK_COMMIT}" \
 && ${VENV}/bin/pip install --no-deps --force-reinstall \
      "unsloth @ git+https://github.com/tlitech-hq/unsloth-vkong.git@${UNSLOTH_FORK_COMMIT}"

COPY pyproject.toml README.md /opt/vkong-connect/
COPY src /opt/vkong-connect/src
COPY schemas /opt/vkong-connect/schemas

RUN ${VENV}/bin/pip install --no-deps /opt/vkong-connect \
 && ${VENV}/bin/python -c \
      "import studio; from vkong_connect.adapters.unsloth.runner import _load_unsloth_worker; assert callable(_load_unsloth_worker())" \
 && ${VENV}/bin/python -m vkong_connect.adapters.unsloth.runtime_image \
      --expected-commit "${UNSLOTH_FORK_COMMIT}" \
 && ${VENV}/bin/python -m vkong_connect.runtime_manifest \
      --output /opt/vkong-connect-runtime.json \
      --adapter-name unsloth \
      --adapter-schema unsloth.v1 \
      --job-schema vkong.connect.job.v2 \
      --source-commit "${UNSLOTH_FORK_COMMIT}" \
      --bridge-build-id "${BRIDGE_BUILD_ID}" \
      --platform "${REMOTE_PLATFORM}" \
 && rm -rf /opt/vkong-connect

ENV PATH="/opt/unsloth-venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    VKONG_CONNECT_RUNTIME_MANIFEST=/opt/vkong-connect-runtime.json

LABEL org.opencontainers.image.source="https://github.com/tlitech-hq/vkong-connect" \
      org.opencontainers.image.revision="${BRIDGE_BUILD_ID}" \
      com.tlitech.unsloth-fork-commit="${UNSLOTH_FORK_COMMIT}" \
      com.tlitech.remote-platform="${REMOTE_PLATFORM}"

# The inherited Unsloth entrypoint performs its GPU pre-flight. VKong overrides
# CMD using start_argv in the generated task bundle.
CMD ["vkong-connect-runner", "--help"]
