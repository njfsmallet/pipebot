#!/bin/bash

# Build the Docker image
# Replace proxy settings with your own if needed
docker build --no-cache \
  --build-arg HTTP_PROXY=http://your-proxy-server:8000 \
  --build-arg HTTPS_PROXY=http://your-proxy-server:8000 \
  --build-arg NO_PROXY=localhost,127.0.0.1,169.254.169.254,your-domain.com \
  -t your-registry.com/your-org/pipebot:latest .

docker push your-registry.com/your-org/pipebot:latest

exit 0
