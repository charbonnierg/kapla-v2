ARG BASE_IMAGE=python:3.8-slim

FROM $BASE_IMAGE as build

RUN mkdir -p /opt/kapla \
    && cd /opt/kapla \
    && python3 -m venv .venv \
    && .venv/bin/pip install -U --no-cache-dir pip setuptools wheel build poetry-core

COPY ./ /source

RUN /opt/kapla/.venv/bin/python -m pip install --no-cache-dir /source


FROM $BASE_IMAGE

RUN apt-get update && apt-get install -y --no-install-recommends curl wget ca-certificates apt-transport-https && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/poetry \
    && curl -sSL https://install.python-poetry.org | POETRY_HOME=/opt/poetry python3 -

COPY --from=build /opt/kapla/ /opt/kapla

RUN ln -s /opt/kapla/.venv/bin/k /usr/local/bin/k

WORKDIR /build

CMD ["k"]
