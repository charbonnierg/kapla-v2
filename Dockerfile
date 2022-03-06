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

COPY --from=build /opt/kapla/ /opt/kapla
