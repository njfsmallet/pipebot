#!/bin/bash

# Enable strict error handling
set -euo pipefail
IFS=$'\n\t'

# Define variables
readonly KB_DIR="${HOME}/.pipebot/kb"
readonly TEMP_DIR="/tmp/pipebot-kb-$$"

# Logging functions
log_info() {
    echo "[INFO] $*" >&2
}

log_error() {
    echo "[ERROR] $*" >&2
}

# Cleanup function
cleanup() {
    log_info "Cleaning up temporary files..."
    rm -rf "${TEMP_DIR}"
}

# Set trap for cleanup
trap cleanup EXIT

# Let's simplify the clone_docs function
clone_docs() {
    local repo_url=$1
    local target_dir=$2
    local source_path=${3:-}

    if [[ -d "${target_dir}" ]]; then
        log_info "Updating ${target_dir##*/} documentation..."
        rm -rf "${target_dir}"
    else
        log_info "Downloading ${target_dir##*/} documentation..."
    fi
    
    local temp_clone_dir="${TEMP_DIR}/$(basename "${repo_url%.*}")"
    git clone --depth 1 "${repo_url}" "${temp_clone_dir}" || {
        log_error "Failed to clone ${repo_url}"
        return 1
    }

    mkdir -p "${target_dir}"
    if [[ -n "${source_path}" ]]; then
        cp -r "${temp_clone_dir}/${source_path}"/* "${target_dir}/"
    else
        cp -r "${temp_clone_dir}"/* "${target_dir}/"
    fi

    rm -rf "${temp_clone_dir}"
}

# Let's simplify the main function
main() {
    # Create temporary directory
    mkdir -p "${TEMP_DIR}"
    mkdir -p "${KB_DIR}"

    log_info "Starting documentation download to: ${KB_DIR}"

    # Clone documentation repositories
    log_info "Cloning documentation repositories..."

    # Kubernetes & AWS
    clone_docs "https://github.com/aws/aws-cli.git" "${KB_DIR}/aws-cli" "awscli"
    clone_docs "https://github.com/kubernetes/website.git" "${KB_DIR}/kubernetes" "content/en"
    #clone_docs "https://github.com/aws/karpenter-provider-aws.git" "${KB_DIR}/karpenter" "website/content/en"
    #clone_docs "https://github.com/kubernetes/dashboard.git" "${KB_DIR}/kubernetes-dashboard" "docs"

    # GitOps & CI/CD
    #clone_docs "https://github.com/argoproj/argo-cd.git" "${KB_DIR}/argocd" "docs"
    #clone_docs "https://github.com/fluxcd/website.git" "${KB_DIR}/fluxcd" "content/en"
    #clone_docs "https://github.com/concourse/docs.git" "${KB_DIR}/concourse" "lit"

    # Security & Access Control
    #clone_docs "https://github.com/cert-manager/website.git" "${KB_DIR}/cert-manager" "content"
    #clone_docs "https://github.com/open-policy-agent/gatekeeper.git" "${KB_DIR}/gatekeeper" "website/docs"
    #clone_docs "https://github.com/hashicorp/vault.git" "${KB_DIR}/vault" "website/content"

    # Networking & Service Mesh
    #clone_docs "https://github.com/kubernetes/ingress-nginx.git" "${KB_DIR}/ingress-nginx" "docs"
    #clone_docs "https://github.com/kubernetes-sigs/external-dns.git" "${KB_DIR}/external-dns" "docs"
    #clone_docs "https://github.com/tigera/docs.git" "${KB_DIR}/calico"

    # Monitoring & Observability
    #clone_docs "https://github.com/cortexproject/cortex.git" "${KB_DIR}/cortex" "docs"
    #clone_docs "https://github.com/grafana/grafana.git" "${KB_DIR}/grafana" "docs"
    #clone_docs "https://github.com/prometheus/docs.git" "${KB_DIR}/prometheus" "content"
    #clone_docs "https://github.com/open-telemetry/opentelemetry.io.git" "${KB_DIR}/opentelemetry" "content/en"
    #clone_docs "https://github.com/kubecost/docs.git" "${KB_DIR}/kubecost"

    # Elastic Stack
    #clone_docs "https://github.com/elastic/cloud-on-k8s.git" "${KB_DIR}/eck" "docs"
    #clone_docs "https://github.com/elastic/beats.git" "${KB_DIR}/filebeat" "filebeat/docs"
    #clone_docs "https://github.com/elastic/beats.git" "${KB_DIR}/metricbeat" "metricbeat/docs"

    # Container Registry
    #clone_docs "https://github.com/goharbor/website.git" "${KB_DIR}/harbor" "docs"

    # Autoscaling
    #clone_docs "https://github.com/kedacore/keda-docs.git" "${KB_DIR}/keda" "content"

    log_info "Documentation download completed successfully!"
    log_info "Run 'pb --scan' to index the new documentation."
}

# Execute main script
main "$@"
