ARG PY_VER=3.12
ARG DIST_VER="-trixie"

# Multistage Dockerfile https://docs.docker.com/develop/develop-images/multistage-build/
FROM python:${PY_VER}${DIST_VER} AS base

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
  && apt-get upgrade -y \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

# Python modules builder
FROM base AS builder
ENV PYTHONUNBUFFERED=1

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
  && apt-get install -y \
    build-essential \
    default-libmysqlclient-dev \
    libevent-dev \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /wheels

COPY requirements.txt .

RUN python3 -m pip install -U pip setuptools \
  && python3 -m pip wheel -r ./requirements.txt
RUN python3 -m pip wheel mysqlclient cython gunicorn[gevent]

# D-Genies image builder
FROM base AS dgenies
ENV PYTHONUNBUFFERED=1

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
  && apt-get install -y \
    time \
    wait-for-it \
    libevent-2.1-7 \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*
# Use volume to free transient data from docker layers
VOLUME /wheels
COPY --from=builder /wheels /wheels
RUN python3 -m pip install --no-cache-dir -r /wheels/requirements.txt -f /wheels --no-index \
  && python3 -m pip install --no-cache-dir -f /wheels --no-index mysqlclient cython gunicorn[gevent] \
  && rm -rf /wheels/*

WORKDIR /app

ENV PYTHONPATH="/app/"
