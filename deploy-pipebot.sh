#!/bin/bash

# Exit on any error
set -e

# Change to frontend directory
cd frontend/

# Build the frontend
npm run build

# Copy dist to web directory
cp -avp dist/ /var/www/pipebot/

# Restart nginx with sudo
sudo systemctl restart nginx

# Optional: Check nginx status
sudo systemctl status nginx

# Optional: Restart pipebot backend
sudo systemctl restart pipebot
#
# Change to root directory
cd ../
