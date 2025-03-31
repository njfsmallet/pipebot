# Stage 1: Build Frontend
FROM node:20-alpine as frontend-build
WORKDIR /app/frontend
# Set proxy for npm
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ .
RUN npm run build

# Stage 2: Build Backend
FROM amazonlinux:2023 as backend-build
WORKDIR /app/backend
# Set proxy for pip
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
COPY backend/requirements.txt .
RUN dnf install -y python3.9 python3.9-pip && \
    python3.9 -m pip install --no-cache-dir -r requirements.txt gunicorn
COPY backend/ .

# Stage 3: Final Image
FROM amazonlinux:2023
WORKDIR /app

# Set proxy for dnf
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

# Install nginx, redis and other dependencies
RUN dnf install -y nginx python3.9 python3.9-pip redis6 unzip openssl git tar && \
    systemctl enable redis6 && \
    mkdir -p /var/run/redis && \
    chown redis6:redis6 /var/run/redis && \
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
    rm -rf aws awscliv2.zip

# Create necessary directories and ec2-user
RUN mkdir -p /var/www/pipebot && \
    useradd -m -s /bin/bash ec2-user && \
    chown -R ec2-user:ec2-user /app && \
    chown -R ec2-user:ec2-user /var/www/pipebot && \
    # Create and set permissions for nginx directories
    mkdir -p /var/lib/nginx/tmp && \
    mkdir -p /var/cache/nginx && \
    mkdir -p /var/log/nginx && \
    chown -R ec2-user:ec2-user /var/lib/nginx && \
    chown -R ec2-user:ec2-user /var/cache/nginx && \
    chown -R ec2-user:ec2-user /var/log/nginx

# Install gunicorn
RUN python3.9 -m pip install --no-cache-dir gunicorn

# Copy backend
COPY --from=backend-build /app/backend /app/backend
COPY --from=backend-build /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages

# Copy pipebot scripts and configuration
COPY pipebot/ /app/pipebot/
COPY pipebot.conf /etc/nginx/conf.d/pipebot.conf
COPY pipebot.service /etc/systemd/system/pipebot.service

# Install pipebot dependencies
COPY pipebot/requirements.txt /app/pipebot/
RUN python3.9 -m pip install --no-cache-dir -r /app/pipebot/requirements.txt

# Copy frontend build
COPY --from=frontend-build /app/frontend/dist /var/www/pipebot/dist

# Configure nginx
RUN rm -f /etc/nginx/conf.d/default.conf && \
    # Remove the user nginx line and change port to 8080
    sed -i '/user nginx;/d' /etc/nginx/nginx.conf && \
    sed -i 's/pid \/run\/nginx.pid;/pid \/tmp\/nginx.pid;/' /etc/nginx/nginx.conf && \
    sed -i 's/listen\s*80;/listen 8080;/' /etc/nginx/nginx.conf && \
    sed -i 's/listen\s*\[::\]:80;/listen [::]:8080;/' /etc/nginx/nginx.conf && \
    chown -R ec2-user:ec2-user /etc/nginx

# Set environment variables
ENV PYTHONPATH=/app
ENV PORT=8001
ENV HTTP_PROXY=http://proxy.example.com:8000
ENV HTTPS_PROXY=http://proxy.example.com:8000
ENV NO_PROXY=localhost,127.0.0.1,169.254.169.254,example.com,eks.amazonaws.com,eks.amazonaws.com.cn
ENV PIPEBOT_SUPPRESS_OUTPUT=true

# Expose ports
EXPOSE 8080 8001 6379

# Create startup script
RUN printf '#!/bin/bash\nredis6-server --daemonize yes\nnginx -c /etc/nginx/nginx.conf -g "daemon off;" &\ncd /app/backend\ngunicorn main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8001 --timeout 600 --log-level info\n' > /app/start.sh && \
    chmod +x /app/start.sh && \
    chown ec2-user:ec2-user /app/start.sh

# Switch to ec2-user
USER ec2-user

# Start the application
CMD ["/app/start.sh"] 
