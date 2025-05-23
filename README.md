# PipeBot (pb)

PipeBot is a command-line interface tool that allows you to interact with models using AWS Bedrock. It's designed for expert users working with Linux, AWS, Kubernetes, Helm, and Python.

```ascii
    ____  ________  __________  ____  ______
   / __ \/  _/ __ \/ ____/ __ )/ __ \/_  __/
  / /_/ // // /_/ / __/ / __  / / / / / /
 / ____// // ____/ /___/ /_/ / /_/ / / /
/_/   /___/_/   /_____/_____/\____/ /_/

+-+-+-+-+-+-+-+ +-+-+ +-+-+-+-+-+-+-+
|p|o|w|e|r|e|d| |b|y| |B|e|d|r|o|c|k|
+-+-+-+-+-+-+-+ +-+-+ +-+-+-+-+-+-+-+
```

## Features

- Interact with Bedrock directly from your command line
- Web interface for easy access and management
- REST API for programmatic access
- Support for both single-query and interactive conversation modes
- Streaming responses for real-time interaction
- Colorized output for improved readability
- Multi-line input support in interactive mode
- Seamless integration with Unix pipes
- Execute read-only AWS CLI, kubectl, and Helm commands through AI interaction
- Secure Python code execution with access to common data science libraries
- Limit on output size to prevent excessive responses
- Conversation memory management for improved context retention
- Embedding-based retrieval of relevant past interactions
- OAuth authentication support
- Proxy configuration for enterprise environments

## Architecture

PipeBot consists of three main components:

1. **Backend (FastAPI)**
   - REST API server running on port 8001
   - Handles all AI interactions and command execution
   - Manages authentication and authorization
   - Provides endpoints for web interface

2. **Frontend (Web Interface)**
   - Modern web interface for easy interaction
   - Built with React/Vue.js
   - Served by Nginx on port 8080

3. **CLI Tool**
   - Command-line interface for direct interaction
   - Supports both interactive and non-interactive modes
   - Can be used in scripts and pipelines

## Prerequisites

- Python 3.6+
- AWS account with Bedrock access
- Boto3 library
- Colored library
- Configured AWS CLI
- Configured kubectl (for Kubernetes-related queries)
- Installed Helm (for Helm-related queries)
- ChromaDB library
- BeautifulSoup4 library (for web search capabilities)
- PrettyTable library
- Urllib3 library
- Requests library
- Serper API key (for web search capabilities)
- FastAPI and Uvicorn (for backend)
- Nginx (for frontend hosting)
- MSAL library (for OAuth authentication)

## Installation

1. Clone this repository:
   ```
   git clone <repository_url>
   ```

2. Install the required Python libraries:
   ```
   pip3 install -r requirements.txt
   ```

3. Configure your AWS credentials:
   ```
   aws configure
   ```

4. Set up the environment variables:
   ```
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. **Set up the `pb` alias**:
   To simplify the usage of PipeBot, you can set up an alias in your shell configuration file (e.g., `~/.bashrc` or `~/.zshrc`):

   ```bash
   alias pb='PYTHONPATH="/home/ec2-user/llm/pipebot" python3 /home/ec2-user/llm/pipebot/pipebot/main.py'
   ```

   After adding the alias, reload your shell configuration:

   ```bash
   source ~/.bashrc
   # or
   source ~/.zshrc
   ```

6. Deploy the service:
   ```bash
   ./deploy-pipebot.sh
   ```

## Usage

### Web Interface

Access the web interface at `http://localhost:8080` (or your configured domain).

### CLI Tool

#### Interactive mode

```
echo hi | pb
```

or

```
uname -a | pb
```

In interactive mode:
- Type your query and press Enter for multi-line input
- Type 'EOF' on a new line and press Enter to send your query
- Use Ctrl+C to interrupt the AI's response
- Use Ctrl+D to end the session

#### Non-interactive mode (single query)

```
git diff | pb --non-interactive
```

### API Usage

The API is available at `http://localhost:8001/api/`. See the API documentation at `/api/docs` for available endpoints.

### Options

- `--non-interactive`: Run in non-interactive mode (exit after first response)
- `--no-memory`: Disable conversation memory
- `--clear`: Clear conversation memory and exit
- `--debug`: Enable debug mode
- `--scan`: Scan and index knowledge base documents
- `--status`: Show knowledge base status and list indexed files
- `--smart`: Use enhanced model capabilities

### Memory Management

PipeBot now includes a memory management feature that stores and retrieves relevant parts of past conversations. This allows for improved context retention across multiple interactions.

- Conversations are automatically stored in a local ChromaDB database.
- Relevant past interactions are retrieved based on the similarity to the current query.
- The AI assistant uses this context to provide more informed and consistent responses.

The memory database is stored in `~/.pipebot/memory` by default.

## Knowledge Base Management

PipeBot includes a knowledge base feature that provides offline access to documentation for various Kubernetes-related tools. The knowledge base is managed using two commands:

### Downloading Documentation

The `knowledge_base.sh` script downloads and organizes documentation from official repositories:

```bash
./knowledge_base.sh
```

Currently supported documentation sources:
- Kubernetes official documentation
- AWS Karpenter
- Kubernetes Dashboard
- GitOps & CI/CD:
  - ArgoCD
  - FluxCD
  - Concourse
- Security & Access Control:
  - Cert Manager
  - OPA Gatekeeper
  - HashiCorp Vault
- Networking & Service Mesh:
  - Ingress NGINX
  - External DNS
  - Calico
- Monitoring & Observability:
  - Cortex
  - Grafana
  - Prometheus
  - OpenTelemetry
  - Kubecost
- Elastic Stack:
  - ECK (Elastic Cloud on Kubernetes)
  - Filebeat
  - Metricbeat
- Container Registry:
  - Harbor
- Autoscaling:
  - KEDA

### Indexing Documentation

After downloading documentation, index it using:

```bash
pb --scan
```

This command:
- Processes all documentation in `~/.pipebot/kb`
- Creates embeddings for efficient searching
- Stores the indexed content for quick retrieval

The knowledge base helps PipeBot provide more accurate and detailed responses about:
- Kubernetes concepts and best practices
- Tool-specific documentation
- Configuration examples
- Troubleshooting guides

## Configuration

- The script uses the 'default' AWS profile.
- The AWS region is set to 'us-west-2'.
- The conversation memory is stored in `~/.pipebot/memory`.
- The knowledge base is stored in `~/.pipebot/kb`.
- The embedding model used is "amazon.titan-embed-text-v2:0".
- Set your Serper API key in the environment variable `SERPER_API_KEY`.
- Proxy settings can be configured in the environment variables.
- OAuth configuration is managed through the `.env` file.

## AWS CLI Integration

PipeBot can execute read-only AWS CLI commands for allowed services. Supported services include:
acm, autoscaling, cloudformation, cloudfront, cloudtrail, cloudwatch, directconnect, ebs, ec2, ecr, ecs, efs, eks, elb, elbv2, iam, kafka, kms, lambda, logs, rds, route53, s3, secretsmanager, sns, sqs, and ce.

Only commands starting with 'describe', 'get', 'list', 'search', 'lookup-events', or 'filter-log-events' are allowed.

## Kubernetes Integration

PipeBot can execute read-only kubectl commands. Supported kubectl operations include:
- get
- describe
- logs
- top (node, pod)
- version
- api-resources
- explain

Allowed resources for get and describe include: pods, services, deployments, replicasets, nodes, namespaces, configmaps, secrets, persistentvolumes, persistentvolumeclaims, events, ingresses, jobs, cronjobs, roles, rolebindings, clusterroles, clusterrolebindings, serviceaccounts, networkpolicies, crds (customresourcedefinitions), ec2nodeclasses, and nodepools.

## Helm Integration

PipeBot can execute read-only Helm commands. Supported Helm operations include:
- search
- list
- get (all, hooks, manifest, notes, values)
- history
- show (all, chart, readme, values)
- status
- env
- version
- dependency (list, build)
- lint
- template
- verify

## Web Search Integration

PipeBot can perform web searches using Serper, a Google Search API. This feature provides:
- Access to current documentation and technical resources
- Solutions to technical problems
- Up-to-date information about technologies and tools
- Research on best practices and common patterns

To use the web search feature:
1. Get your API key from [Serper.dev](https://serper.dev)
2. Set the environment variable:
   ```bash
   export SERPER_API_KEY='your_api_key_here'
   ```

Example usage:
```
echo "Search for Kubernetes best practices" | pb
```

Search results are limited to the top 5 most relevant matches to keep responses focused and concise.

## Python Code Execution

PipeBot includes a secure Python code execution environment that allows you to run Python code snippets with access to common data science and mathematical libraries. This feature is designed with security in mind and only allows access to safe, read-only operations.

Supported libraries include:
- NumPy (as np)
- Pandas (as pd)
- Math and Cmath
- Statistics
- DateTime
- Collections
- Itertools
- JSON
- Random
- UUID
- Base64
- HashLib
- And more common Python utilities

Security features:
- Restricted to safe, read-only operations
- No file system access
- No network access
- Limited to approved modules
- Sandboxed execution environment

Example usage:

```
echo "Calculate fibonacci sequence using Python" | pb
```

## Examples

1. Get information about EC2 instances:
   ```
   echo "List all clusters EKS" | pb
   ```

2. Describe a specific Kubernetes deployment:
   ```
   echo "Describe the nginx deployment in kube-system" | pb
   ```

3. List Helm releases:
   ```
   echo "List all Helm releases" | pb
   ```

4. Search for technical documentation:
   ```
   echo "Find documentation about AWS EKS best practices" | pb
   ```

## Directory Structure

```
pipebot/
├── backend/          # FastAPI backend
├── frontend/         # Web interface
├── pipebot/          # CLI tool
├── .env              # Environment configuration
├── pipebot.conf      # Nginx configuration
├── pipebot.service   # Systemd service configuration
├── deploy-pipebot.sh # Deployment script
└── knowledge_base.sh # Knowledge base management

~/.pipebot/
├── memory/           # Conversation history database
├── kb/              # Knowledge base documentation
├── .aws/            # AWS credentials
└── .kube/           # Kubernetes configuration
```

## Security Features

- Only read-only operations are allowed for AWS CLI, kubectl, and Helm
- Certain potentially dangerous flags and options are disallowed
- Output size is limited to prevent excessive responses
- Conversation memory and knowledge base are stored locally, ensuring data privacy
- Documentation is downloaded only from official repositories

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- AWS for the Bedrock service
