#!/usr/bin/env bash

docker buildx build -f Dockerfile --tag quara/kapla:latest --load .
