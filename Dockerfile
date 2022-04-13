ARG BASE_IMAGE=python:3.8-slim

FROM $BASE_IMAGE as build

COPY dist/ /build

RUN mkdir -p /opt/kapla \
    && cd /opt/kapla \
    && python3 -m venv .venv \
    && .venv/bin/pip install -U --no-cache-dir pip setuptools wheel

WORKDIR /opt/kapla

RUN .venv/bin/pip --no-cache-dir install /build/*.whl

FROM $BASE_IMAGE

RUN apt-get update && apt-get install -y curl wget ca-certificates apt-transport-https && apt-get clean

RUN mkdir -p /opt/poetry \
    && curl -sSL https://install.python-poetry.org | POETRY_PREVIEW=1 POETRY_HOME=/opt/poetry python3 -

RUN curl https://sh.rustup.rs -sSf | bash -s -- -y --profile minimal

COPY --from=build /opt/kapla/ /opt/kapla
