# Stage 1: Build Frontend
FROM node:20-alpine as frontend-build
WORKDIR /app/frontend
# Set proxy for npm
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
# Copy package files first for better layer caching
COPY frontend/package*.json ./
RUN npm install
# Copy the rest of the frontend files
COPY frontend/ .
RUN npm run build

# Stage 2: Build Backend
FROM python:3.12-slim as backend-build
WORKDIR /app/backend
# Set proxy for pip
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
# Copy requirements first for better layer caching
COPY backend/requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt
# Copy the rest of the backend files
COPY backend/ .

# Stage 3: Final Image
FROM python:3.12-slim
WORKDIR /app

# Set proxy
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

# Install nginx, redis and other dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    nginx \
    redis-server \
    unzip \
    openssl \
    git \
    tar \
    curl \
    procps \
    ca-certificates \
    gnupg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    mkdir -p /var/run/redis && \
    chown redis:redis /var/run/redis && \
    # Install kubectl 1.30
    curl -LO "https://dl.k8s.io/release/v1.30.0/bin/linux/amd64/kubectl" && \
    chmod +x kubectl && \
    mv kubectl /usr/local/bin/ && \
    # Install Helm
    curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash && \
    # Install AWS CLI v2
    curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" && \
    unzip awscliv2.zip && \
    ./aws/install && \
    rm -rf aws awscliv2.zip && \
    # Install Huawei KooCLI
    curl -LO "https://ap-southeast-3-hwcloudcli.obs.ap-southeast-3.myhuaweicloud.com/cli/latest/huaweicloud-cli-linux-amd64.tar.gz" && \
    tar -zxvf huaweicloud-cli-linux-amd64.tar.gz && \
    mv $(pwd)/hcloud /usr/local/bin/ && \
    chmod 755 /usr/local/bin/hcloud && \
    rm -rf huaweicloud-cli-linux-amd64.tar.gz && \
    # Install Node.js and npm
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && \
    apt-get install -y nodejs && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    # Install Bun
    npm install -g bun

# Create necessary directories and app user
RUN mkdir -p /var/www/pipebot && \
    groupadd -r -g 1000 ec2-user && useradd -r -u 1000 -g ec2-user -m -s /bin/bash ec2-user && \
    chown -R ec2-user:ec2-user /app && \
    chown -R ec2-user:ec2-user /var/www/pipebot && \
    # Create and set permissions for nginx directories
    mkdir -p /var/lib/nginx/tmp && \
    mkdir -p /var/lib/nginx/body && \
    mkdir -p /var/lib/nginx/fastcgi && \
    mkdir -p /var/lib/nginx/proxy && \
    mkdir -p /var/lib/nginx/scgi && \
    mkdir -p /var/lib/nginx/uwsgi && \
    mkdir -p /var/cache/nginx && \
    mkdir -p /var/log/nginx && \
    chown -R ec2-user:ec2-user /var/lib/nginx && \
    chown -R ec2-user:ec2-user /var/cache/nginx && \
    chmod -R 775 /var/log/nginx && \
    chown -R ec2-user:ec2-user /var/log/nginx && \
    touch /var/log/nginx/error.log /var/log/nginx/pipebot.access.log /var/log/nginx/pipebot.error.log && \
    chmod 664 /var/log/nginx/error.log /var/log/nginx/pipebot.access.log /var/log/nginx/pipebot.error.log && \
    chown ec2-user:ec2-user /var/log/nginx/error.log /var/log/nginx/pipebot.access.log /var/log/nginx/pipebot.error.log



# Copy backend
COPY --from=backend-build /app/backend /app/backend
COPY --from=backend-build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=backend-build /usr/local/bin/ /usr/local/bin/

# Copy pipebot scripts and configuration
COPY pipebot/ /app/pipebot/
COPY pipebot.conf /etc/nginx/conf.d/pipebot.conf

# Install pipebot dependencies
COPY pipebot/requirements.txt /app/pipebot/
RUN python3.12 -m pip install --no-cache-dir --upgrade pip setuptools wheel && \
    python3.12 -m pip install --no-cache-dir -r /app/pipebot/requirements.txt

# Copy frontend build
COPY --from=frontend-build /app/frontend/dist /var/www/pipebot/dist

# Configure nginx
RUN rm -f /etc/nginx/conf.d/default.conf && \
    rm -f /etc/nginx/sites-enabled/default && \
    # Configure nginx for Debian
    sed -i '/user www-data;/d' /etc/nginx/nginx.conf && \
    sed -i 's/pid \/run\/nginx.pid;/pid \/tmp\/nginx.pid;/' /etc/nginx/nginx.conf && \
    chown -R ec2-user:ec2-user /etc/nginx

# Expose ports
EXPOSE 8080 8001 6379

# Create startup script
RUN printf '#!/bin/bash\nredis-server --daemonize yes\nnginx -c /etc/nginx/nginx.conf -g "daemon off;" &\ncd /app/backend\ngunicorn main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8001 --timeout 600 --log-level info\n' > /app/start.sh && \
    chmod +x /app/start.sh && \
    chown ec2-user:ec2-user /app/start.sh

# Switch to appuser
USER ec2-user

# Install uv
RUN pip install --user --no-cache-dir uv
ENV PATH="/home/ec2-user/.local/bin:$PATH"

# Start the application
CMD ["/app/start.sh"] 
