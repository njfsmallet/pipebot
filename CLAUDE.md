# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend Development

```bash
# Navigate to the backend directory
cd /home/ec2-user/llm/pipebot

# No need to manually activate the virtual environment - it's handled by the pb function
# Run the Pipebot CLI using the function defined in pipebot.sh
# Example: Running in interactive mode
echo "Your query" | pb

# Example: Running without conversation memory
echo "Your query" | pb --no-memory

# Example: Running with enhanced model capabilities
echo "Your query" | pb --smart

# Example: Scan and index knowledge base documents
pb --scan

# Example: Show knowledge base status
pb --status

# Example: Clear conversation memory
pb --clear

# Example: Enable debug mode for detailed logging
pb --debug
```

### Frontend Development

```bash
# Navigate to the frontend directory
cd /home/ec2-user/llm/pipebot/frontend

# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build

# Run linter
npm run lint

# Preview production build
npm run preview

# Type checking
tsc -b
```

### Development Setup

```bash
# Set up Python 3.12 virtual environment
mkdir -p ~/llm/pipebot/venv
python3.12 -m venv ~/llm/pipebot/venv/py3.12

# Activate the virtual environment
source ~/llm/pipebot/venv/py3.12/bin/activate

# Install backend dependencies
pip install -r pipebot/requirements.txt

# Install frontend dependencies
cd frontend && npm install
```

### Starting Services

```bash
# Start the backend FastAPI server
cd /home/ec2-user/llm/pipebot/backend && source ../venv/py3.12/bin/activate && export PYTHONPATH="/home/ec2-user/llm/pipebot" && uvicorn main:app --reload --host 0.0.0.0 --port 8001 --log-level debug

# Start the frontend development server
cd /home/ec2-user/llm/pipebot/frontend && npm run dev
```

### Deployment

```bash
# Deploy the full service
./deploy-pipebot.sh

# Download and organize documentation for the knowledge base
./knowledge_base.sh
```

## Architecture Overview

PipeBot is a CLI tool that allows users to interact with AWS Bedrock models. It consists of three main components:

1. **Backend (FastAPI)**
   - REST API server running on port 8001
   - Handles AI model interactions via AWS Bedrock
   - Manages authentication and authorization
   - Provides endpoints for the web interface
   - Implemented in Python using FastAPI

2. **Frontend (React/Vite)**
   - Modern web interface for interaction with the AI assistant
   - Built with React and TypeScript
   - Uses a terminal-like interface for command input and response display
   - Served by Nginx on port 8080

3. **CLI Tool**
   - Command-line interface for direct interaction
   - Supports both interactive and non-interactive modes
   - Can be used in scripts and pipelines
   - Integrates with Unix pipes

### Core Components

- **pipebot/main.py**: Entry point for the CLI tool
- **pipebot/cli.py**: Command-line argument parsing
- **pipebot/config.py**: Configuration settings for AWS, UI colors, and storage
- **pipebot/ai/assistant.py**: AI assistant implementation using AWS Bedrock
- **pipebot/memory**: Conversation memory management using ChromaDB
- **pipebot/tools**: Tool executors for AWS CLI, Kubernetes, Helm, etc.
- **pipebot/mcp_server.py**: Model Context Protocol server implementation
- **backend/main.py**: FastAPI server implementation
- **frontend/src/components**: React components for the web interface

### Key Features

- Direct interaction with Bedrock models from the command line
- Conversation memory management for context retention across interactions
- Knowledge base for offline access to documentation
- Support for executing read-only AWS CLI, kubectl, and Helm commands
- Web interface for easy access and interaction
- Streaming responses for real-time interaction
- Authentication via Azure Entra ID (OAuth)
- Support for image input (multimodal capabilities)
- Python code execution in a secure environment

### AWS Integration

PipeBot uses AWS Bedrock for AI model inference and requires proper AWS credentials configuration. The application is currently configured to use:

- AWS Region: us-west-2
- Model ID: Claude Sonnet 4 (as specified in config.py)
- Embedding model: amazon.titan-embed-text-v2:0

### Data Storage

- Conversation memory is stored in `~/.pipebot/memory`
- Knowledge base documentation is stored in `~/.pipebot/kb`
- Both use ChromaDB for vector storage and retrieval

### Security Considerations

- Only read-only operations are allowed for AWS CLI, kubectl, and Helm commands
- Restricted Python execution environment with limited module access
- No network or file system access from the Python execution environment
- OAuth authentication for the web interface
- Local storage of conversation history and knowledge base
- Input validation and sanitization for all user inputs

## File Structure

```
pipebot/
├── backend/          # FastAPI backend server
│   ├── config.py     # Backend configuration
│   ├── main.py       # FastAPI application
│   └── session_manager.py # User session management
│
├── frontend/         # React/Vite web interface
│   ├── src/          # Source code
│   │   ├── components/ # React components
│   │   ├── hooks/    # Custom React hooks
│   │   └── styles/   # CSS styles
│   ├── package.json  # NPM dependencies
│   └── vite.config.ts # Vite configuration
│
├── pipebot/          # CLI tool core
│   ├── ai/           # AI assistant implementation
│   ├── auth/         # Authentication modules
│   ├── memory/       # Conversation memory management
│   ├── tools/        # Tool executors (AWS, K8s, etc.)
│   ├── utils/        # Utility functions
│   ├── cli.py        # CLI argument parsing
│   ├── config.py     # Configuration settings
│   ├── main.py       # CLI entry point
│   └── mcp_server.py # MCP server implementation
│
├── .env.example      # Environment variables example
├── knowledge_base.sh # Knowledge base management script
└── pipebot.sh        # Helper script for the CLI tool
```

## Development Workflow

1. Make changes to the codebase
2. Test changes using the appropriate commands:
   - For backend changes: Start the backend server and test API endpoints
   - For frontend changes: Start the development server and test UI components
   - For CLI changes: Use the pb function to test the CLI tool
3. Run linting and type checking before committing changes
4. For frontend: `npm run lint && tsc -b`
5. For deployment, use the `./deploy-pipebot.sh` script

## Environment Configuration

The application uses environment variables for configuration. Create a `.env` file based on the `.env.example` template with the following important variables:

- AWS credentials and region
- API endpoints and ports
- OAuth configuration
- Proxy settings (if needed)
- Debug and logging settings