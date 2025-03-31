#!/bin/bash

# Build the Docker image
docker build --no-cache \
  --build-arg HTTP_PROXY=http://proxy.example.com:8000 \
  --build-arg HTTPS_PROXY=http://proxy.example.com:8000 \
  --build-arg NO_PROXY=localhost,127.0.0.1,169.254.169.254,example.com \
  -t harbor.example.com/infra/nma/pipebot:latest .

docker push harbor.example.com/infra/nma/pipebot:latest

exit 0
