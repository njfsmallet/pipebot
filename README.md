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
- Execute read-only commands through AI interaction via MCP framework
- Secure Python code execution with access to common data science libraries
- Limit on output size to prevent excessive responses
- Conversation memory management for improved context retention
- Embedding-based retrieval of relevant past interactions
- OAuth authentication support
- Proxy configuration for enterprise environments
- Model Context Protocol (MCP) framework integration

## Architecture

PipeBot consists of four main components:

1. **Backend (FastAPI)**
   - REST API server running on port 8001
   - Handles all AI interactions and command execution
   - Manages authentication and authorization
   - Provides endpoints for web interface
   - Implemented in Python using FastAPI

2. **Frontend (React/Vite)**
   - Modern web interface for interaction with the AI assistant
   - Built with React and TypeScript
   - Uses a terminal-like interface for command input and response display
   - Uses Tailwind CSS for styling
   - Development server runs on port 5173
   - Production build served by Nginx on port 8080

3. **CLI Tool**
   - Command-line interface for direct interaction
   - Supports both interactive and non-interactive modes
   - Can be used in scripts and pipelines
   - Integrates with Unix pipes

4. **MCP Framework**
   - Model Context Protocol (MCP) integration for tool execution
   - Standardized way for tool execution and interaction with large language models
   - Enhanced context management for complex interactions
   - Supports multiple specialized MCP servers for different tools

## Prerequisites

- Python 3.12+
- AWS account with Bedrock access
- Configured AWS CLI
- Node.js and npm (for frontend development)

### Required Python Packages
- FastAPI and Uvicorn
- Boto3
- ChromaDB
- MCP framework
- Additional packages listed in `pipebot/requirements.txt`

## Installation

1. Clone this repository:
   ```
   git clone <repository_url>
   ```

2. Set up Python 3.12 virtual environment and install requirements:
   ```bash
   # Create Python 3.12 virtual environment
   mkdir -p ~/llm/pipebot/venv
   python3.12 -m venv ~/llm/pipebot/venv/py3.12
   
   # Activate the virtual environment
   source ~/llm/pipebot/venv/py3.12/bin/activate
   
   # Update pip and setuptools
   pip install -U pip setuptools wheel
   
   # Install requirements
   pip install -r pipebot/requirements.txt
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

5. **Set up the `pb` function**:
   To simplify the usage of PipeBot, you can set up a function in your shell configuration file (e.g., `~/.bashrc` or `~/.zshrc`):

   ```bash
   function pb() {
       source /home/ec2-user/llm/pipebot/venv/py3.12/bin/activate && PYTHONPATH="/home/ec2-user/llm/pipebot" python /home/ec2-user/llm/pipebot/pipebot/main.py "$@"
   }
   ```

   After adding the function, reload your shell configuration:

   ```bash
   source ~/.bashrc
   # or
   source ~/.zshrc
   ```

## Starting the Services

### Backend

To start the FastAPI backend server:

```bash
cd /home/ec2-user/llm/pipebot/backend && source ../venv/py3.12/bin/activate && export PYTHONPATH="/home/ec2-user/llm/pipebot" && uvicorn main:app --reload --host 0.0.0.0 --port 8001 --log-level debug
```

### Frontend

To start the frontend development server:

```bash
cd /home/ec2-user/llm/pipebot/frontend && npm run dev
```

## Usage

### Web Interface

Access the web interface at `http://localhost:5173` during development, or at your configured domain/port in production.

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
- `--smart`: Use enhanced model capabilities (Claude 3.7 Sonnet)
- `--debug`: Enable debug mode for detailed logging output

## Memory Management

PipeBot includes a memory management feature that stores and retrieves relevant parts of past conversations. This allows for improved context retention across multiple interactions.

- Conversations are automatically stored in a local ChromaDB database.
- Relevant past interactions are retrieved based on the similarity to the current query.
- The AI assistant uses this context to provide more informed and consistent responses.

The memory database is stored in `~/.pipebot/memory` by default.

## Knowledge Base Management

PipeBot includes a knowledge base feature that provides offline access to documentation for various tools. The knowledge base is managed using:

```bash
./knowledge_base.sh
```

After downloading documentation, index it using:

```bash
pb --scan
```

## Model Context Protocol (MCP) Framework

PipeBot integrates with the Model Context Protocol (MCP) framework, which provides a standardized way for tool execution and interaction with large language models. This integration enables:

- Consistent tool execution patterns across different models
- Enhanced context management for complex interactions
- Improved handling of multimodal inputs (text and images)
- Structured tool inputs and outputs for better reliability
- More efficient context utilization for longer conversations

The MCP framework is implemented in the `mcp_server.py` component, which handles:

- Tool registration and validation
- Input/output formatting for model interactions
- Context window management
- Execution of tools based on model requests

PipeBot supports various MCP servers defined in `mcp.json` including:
- context7: For context-aware operations
- fetch: For web fetching capabilities
- mapbox: For mapping and geospatial tools
- memory: For enhanced memory management
- sequential-thinking: For complex reasoning tasks
- pipebot: For core PipeBot functionalities

## Configuration

- The AWS region is set to 'us-east-2'.
- Models:
  - Standard mode: Claude 3.5 Haiku (`us.anthropic.claude-3-5-haiku-20241022-v1:0`)
  - Smart mode (--smart flag): Claude 3.7 Sonnet (`us.anthropic.claude-3-7-sonnet-20250219-v1:0`)
- The conversation memory is stored in `~/.pipebot/memory`.
- The knowledge base is stored in `~/.pipebot/kb`.
- The embedding model used is "amazon.titan-embed-text-v2:0".
- Proxy settings can be configured in the environment variables.
- OAuth configuration is managed through the `.env` file.
- MCP server configurations are managed in `mcp.json`.

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
├── backend/          # FastAPI backend server
│   ├── config.py     # Backend configuration
│   ├── logging_config.py # Logging configuration
│   ├── main.py       # FastAPI application
│   ├── requirements.txt # Backend-specific requirements
│   └── session_manager.py # User session management
│
├── frontend/         # React/Vite web interface
│   ├── src/          # Source code
│   │   ├── components/ # React components
│   │   │   └── markdown/ # Markdown rendering components
│   │   ├── hooks/    # Custom React hooks
│   │   ├── styles/   # CSS styles
│   │   └── config/   # Frontend configuration
│   ├── package.json  # NPM dependencies
│   └── vite.config.ts # Vite configuration
│
├── pipebot/          # CLI tool core
│   ├── ai/           # AI assistant implementation
│   ├── auth/         # Authentication modules
│   ├── memory/       # Conversation memory management
│   ├── tools/        # Tool executors
│   ├── utils/        # Utility functions
│   ├── cli.py        # CLI argument parsing
│   ├── config.py     # Configuration settings
│   ├── main.py       # CLI entry point
│   └── mcp_server.py # MCP server implementation
│
├── image-builder.sh  # Docker image building script
├── mcp.json          # MCP server configuration
├── setup.py          # Package setup script
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
   - For frontend: `npm run lint && tsc -b`
4. For deployment, use container-based deployment with Dockerfile

## Environment Configuration

The application uses environment variables for configuration. Create a `.env` file based on the `.env.example` template with the following important variables:

- AWS credentials and region
- API endpoints and ports
- OAuth configuration
- Proxy settings (if needed)
- Debug and logging settings

## Security Features

- Only read-only operations are allowed through the MCP framework
- Conversation memory and knowledge base are stored locally, ensuring data privacy
- Documentation is downloaded only from official repositories
- Restricted Python execution environment with limited module access
- No network or file system access from the Python execution environment
- OAuth authentication for the web interface
- Input validation and sanitization for all user inputs

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
