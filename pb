#!/usr/bin/env python3

# Standard library imports
import argparse
import datetime
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Dict, Any

# Third-party imports
import boto3
import chromadb
from chromadb.config import Settings
from colored import fg, attr
from prettytable import PrettyTable
import requests

# Constants
## AWS Related
CLAUDE_SMART = "anthropic.claude-3-5-sonnet-20241022-v2:0"
CLAUDE_FAST = "anthropic.claude-3-haiku-20240307-v1:0"
EMBEDDING_MODEL = "amazon.titan-embed-text-v2:0"
REGION_NAME = 'us-west-2'
EMBEDDING_DIMENSION = 1024

## API Keys
SERPER_API_KEY = os.getenv('SERPER_API_KEY')

## UI Colors
COLOR_BLUE = fg('light_blue')
COLOR_GREEN = fg('light_green')
COLOR_RED = fg('light_red')
RESET_COLOR = attr('reset')

## Storage
MEMORY_DIR = os.path.expanduser("~/.pipebot/memory")
COLLECTION_NAME = "conversation_memory"

def create_bedrock_client():
    """Create and return a Bedrock client using the default AWS profile."""
    bedrock_session = boto3.Session(profile_name='default')
    return bedrock_session.client(
        service_name='bedrock-runtime',
        region_name=REGION_NAME,
        config=boto3.session.Config(
            retries={'max_attempts': 3, 'mode': 'adaptive'},
            connect_timeout=2,
            read_timeout=20,
            tcp_keepalive=True
        )
    )

def check_for_pipe():
    """Check if the script is being used with piped input. Exit if not."""
    if os.isatty(sys.stdin.fileno()):
        print(f"{COLOR_GREEN}PipeBot (pb) - AI Assistant powered by Anthropic\n")
        print("Usage:")
        print("  Basic:     $ <command> | pb")
        print("  Fast:      $ <command> | pb --fast")
        print("  No Memory: $ <command> | pb --no-memory")
        print("\nOptions:")
        print("  --non-interactive  Stop after first response")
        print("  --fast            Use faster but simpler model")
        print("  --no-memory       Disable conversation memory")
        print("  --clear-memory    Clear conversation memory and exit")
        print("  --debug           Enable debug output")
        print("\nExamples:")
        print("  $ echo 'What is Docker?' | pb")
        print("  $ kubectl get ns | pb --fast")
        print("  $ aws s3 ls | pb --no-memory")
        print(f"{RESET_COLOR}")
        sys.exit(0)

class CommandExecutor:
    """A class to handle command execution for various tools."""

    @staticmethod
    def execute(command: str, tool: str, prefix: str = "") -> Dict[str, Any]:
        """
        Execute a shell command and return the result.
        
        :param command: The command to execute
        :param tool: The name of the tool being used (for error messages)
        :param prefix: An optional prefix to add to the command (e.g., 'aws' for AWS CLI commands)
        :return: A dictionary containing either the command output or an error message
        """
        try:
            # Use a shell to execute the command, which handles pipes and quotes correctly
            process = subprocess.Popen(f"{prefix} {command}", 
                                       shell=True, 
                                       stdout=subprocess.PIPE, 
                                       stderr=subprocess.PIPE, 
                                       text=True)

            output, error = process.communicate()

            if process.returncode != 0:
                return {"error": f"Error running {tool} command: {error}"}

            # Truncate output if it's too long
            max_output_size = 10000
            if len(output) > max_output_size:
                truncated_output = output[:max_output_size] + "\n... (output truncated)"
                return {"output": truncated_output, "truncated": True}

            return {"output": output}
        except Exception as e:
            return {"error": f"Error executing command: {str(e)}"}

class ToolExecutor:
    """A class to handle execution of specific tools (AWS CLI, Helm, kubectl)."""

    @staticmethod
    def _execute_tool_command(command: str, tool_name: str, allowed_commands: List[str], disallowed_options: List[str], prefix: str, command_index: int) -> Dict[str, Any]:
        """
        Execute a tool command with security checks.
        
        :param command: The command to execute (without tool prefix)
        :param tool_name: The name of the tool (e.g., 'AWS CLI', 'Helm', 'kubectl')
        :param allowed_commands: List of allowed commands for this tool
        :param disallowed_options: List of disallowed options for security reasons
        :param prefix: The command prefix to use (e.g., 'aws', 'helm', 'kubectl')
        :param command_index: The index of the command part to check (0 for helm/kubectl, 1 for aws)
        :return: The result of the command execution
        """
        # Ensure the command doesn't start with the tool name
        if command.strip().startswith(prefix):
            command = command.strip()[len(prefix):].strip()

        # Split the command into parts
        cmd_parts = shlex.split(command)

        # Check if the command is allowed
        if len(cmd_parts) <= command_index or not any(cmd_parts[command_index].startswith(allowed_cmd) for allowed_cmd in allowed_commands):
            return {"error": f"Only specific read-only {tool_name} commands are allowed. Allowed commands are: {', '.join(allowed_commands)}"}

        # Check for disallowed options
        if any(option in cmd_parts for option in disallowed_options):
            return {"error": f"Disallowed options detected. The following options are not permitted: {', '.join(disallowed_options)}"}

        try:
            # Execute the command
            return CommandExecutor.execute(command, tool_name, prefix=prefix)
        except Exception as e:
            return {"error": f"Error executing {tool_name} command: {str(e)}"}

    @staticmethod
    def aws(command: str) -> Dict[str, Any]:
        allowed_commands = [
            'analyze', 'check', 'describe', 'estimate', 'export',
            'filter', 'generate', 'get', 'list', 'lookup',
            'ls', 'preview', 'scan', 'search', 'show', 
            'summarize', 'test', 'validate', 'view'
        ]
        # Remove '--region' from disallowed options
        disallowed_options = ['--profile']
        return ToolExecutor._execute_tool_command(command, "AWS CLI", allowed_commands, disallowed_options, "aws", 1)

    @staticmethod
    def helm(command: str) -> Dict[str, Any]:
        allowed_commands = [
            'dependency', 'env', 'get', 'history', 'inspect', 'lint',
            'list', 'search', 'show', 'status', 'template', 'verify', 'version'
        ]
        disallowed_options = ['--kube-context', '--kubeconfig']
        return ToolExecutor._execute_tool_command(command, "Helm", allowed_commands, disallowed_options, "helm", 0)

    @staticmethod
    def kubectl(command: str) -> Dict[str, Any]:
        allowed_commands = [
            'api-resources', 'api-versions', 'cluster-info', 'describe', 
            'explain', 'get', 'logs', 'top', 'version'
        ]
        disallowed_options = ['--kubeconfig', '--as', '--as-group', '--token']
        return ToolExecutor._execute_tool_command(command, "kubectl", allowed_commands, disallowed_options, "kubectl", 0)

    @staticmethod
    def serper(query: str) -> Dict[str, Any]:
        """Execute a Serper search query."""
        if not SERPER_API_KEY:
            return {"error": "SERPER_API_KEY environment variable is not set"}

        try:
            headers = {
                'X-API-KEY': SERPER_API_KEY,
                'Content-Type': 'application/json'
            }
            payload = {
                'q': query,
                'num': 5  # Limit to top 5 results
            }
            response = requests.post(
                'https://google.serper.dev/search',
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            return {"output": response.json()}
        except Exception as e:
            return {"error": f"Error executing Serper search: {str(e)}"}

def generate_embeddings(text: str, bedrock_client) -> List[float]:
    """Generate embeddings for the given text using the Bedrock embedding model."""
    response = bedrock_client.invoke_model(
        modelId=EMBEDDING_MODEL,
        body=json.dumps({
            "inputText": text,
            "normalize": True,
            "dimensions": EMBEDDING_DIMENSION,
            "embeddingTypes": ["float"]
        }),
        contentType='application/json',
        accept='application/json'
    )
    response_body = json.loads(response['body'].read())
    return response_body['embeddingsByType']['float']

class MemoryManager:
    def __init__(self, bedrock_client):
        self.bedrock_client = bedrock_client
        self.collection = self.setup_memory()

    def setup_memory(self):
        """Setup and return the ChromaDB collection for conversation memory."""
        Path(MEMORY_DIR).mkdir(parents=True, exist_ok=True)
        
        client = chromadb.PersistentClient(path=MEMORY_DIR, settings=Settings(anonymized_telemetry=False))
        
        try:
            collection = client.get_collection(COLLECTION_NAME)
        except ValueError:
            collection = client.create_collection(
                COLLECTION_NAME,
                metadata={"dimension": EMBEDDING_DIMENSION}
            )
        
        return collection

    def store_interaction(self, role: str, content: str):
        """Store an interaction in the memory database."""
        # Skip if content is empty or not a string
        if not content or not isinstance(content, str):
            print(f"{COLOR_BLUE}[DEBUG] Skipping memory storage for empty or invalid content{RESET_COLOR}")
            return
        
        timestamp = datetime.datetime.now().isoformat()
        content_hash = hashlib.md5(content.encode()).hexdigest()
        id = f"{timestamp}-{content_hash}"
        
        try:
            embeddings = generate_embeddings(content, self.bedrock_client)
            
            self.collection.add(
                documents=[content],
                metadatas=[{"role": role, "timestamp": timestamp}],
                ids=[id],
                embeddings=[embeddings]
            )
        except Exception as e:
            print(f"{COLOR_BLUE}[DEBUG] Error storing interaction in memory: {str(e)}{RESET_COLOR}")

    def get_relevant_history(self, query: str, limit: int = 5) -> List[Dict[str, str]]:
        """Retrieve relevant conversation history based on the query."""
        try:
            query_embedding = generate_embeddings(query, self.bedrock_client)
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=limit
            )
        except Exception as e:
            print(f"Warning: Error querying memory: {str(e)}")
            return []
        
        history = []
        if results and results['documents']:
            sorted_results = sorted(
                zip(results['documents'][0], results['metadatas'][0]),
                key=lambda x: x[1]["timestamp"]
            )
            for doc, metadata in sorted_results:
                history.append({
                    "role": metadata["role"],
                    "content": [{"text": doc}],
                    "from_memory": True
                })
        return history

class AIAssistant:
    """A class to handle interactions with the AI model."""

    def __init__(self, bedrock_client, debug=False, use_memory=True):
        """Initialize the AI Assistant with a Bedrock client and memory."""
        self.bedrock = bedrock_client
        self.last_interaction_time = time.time()
        self.session_timeout = 60
        self.memory_manager = MemoryManager(bedrock_client) if use_memory else None
        self.debug = debug
        self.use_memory = use_memory
        
    def generate_response(self, conversation_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Modified to include memory storage and retrieval."""
        # Get the current query
        current_query = conversation_history[-1]["content"]
        if isinstance(current_query, list):
            if len(current_query) == 1 and isinstance(current_query[0], dict):
                # If it's a tool result, extract the relevant content
                if "toolResult" in current_query[0]:
                    tool_result = current_query[0]["toolResult"]
                    if isinstance(tool_result, dict) and "content" in tool_result:
                        current_query = str(tool_result["content"])
                else:
                    current_query = current_query[0].get("text", "")
            else:
                current_query = str(current_query)
        
        # Skip memory operations if memory is disabled or for empty queries
        relevant_history = []
        if self.use_memory and current_query:
            # Get relevant history first
            relevant_history = self.memory_manager.get_relevant_history(current_query)
            # Then store the user's query in memory
            self.memory_manager.store_interaction("user", current_query)
        
        # Create a new conversation history that includes relevant past interactions
        merged_history = relevant_history + conversation_history
        
        current_time = time.time()
        if current_time - self.last_interaction_time > self.session_timeout:
            self.bedrock = create_bedrock_client()

        self.last_interaction_time = current_time

        # Define the available tools for the AI
        tool_config = {
            "tools": [
                {
                    "toolSpec": {
                        "name": "aws",
                        "description": "Execute a read-only AWS CLI command for any AWS service. Allowed actions include commands starting with: analyze, check, describe, estimate, export, filter, generate, get, list, lookup, ls, preview, scan, search, show, summarize, test, validate, and view.",
                        "inputSchema": {
                            "json": {
                                "type": "object",
                                "properties": {
                                    "command": {
                                        "type": "string",
                                        "description": "The AWS CLI command to execute, without the 'aws' prefix. Format: '<service> <action> [parameters]'. For example, use 'ec2 describe-instances' or 's3 ls s3://bucket-name'. The option '--profile' is not permitted, but '--region' can be used to specify a different region."
                                    }
                                },
                                "required": ["command"]
                            }
                        }
                    }
                },
                {
                    "toolSpec": {
                        "name": "kubectl",
                        "description": "Execute a read-only kubectl command. Allowed actions include: api-resources, api-versions, cluster-info, describe, explain, get, logs, top, and version.",
                        "inputSchema": {
                            "json": {
                                "type": "object",
                                "properties": {
                                    "command": {
                                        "type": "string",
                                        "description": "The kubectl command to execute, without the 'kubectl' prefix. For example, use 'get pods' instead of 'kubectl get pods'. The options '--kubeconfig', '--as', '--as-group', and '--token' are not permitted."
                                    }
                                },
                                "required": ["command"]
                            }
                        }
                    }
                },
                {
                    "toolSpec": {
                        "name": "helm",
                        "description": "Execute a read-only Helm command. Allowed actions include: dependency, env, get, history, inspect, lint, list, search, show, status, template, verify, and version.",
                        "inputSchema": {
                            "json": {
                                "type": "object",
                                "properties": {
                                    "command": {
                                        "type": "string",
                                        "description": "The Helm command to execute, without the 'helm' prefix. For example, use 'list' instead of 'helm list'. The options '--kube-context' and '--kubeconfig' are not permitted."
                                    }
                                },
                                "required": ["command"]
                            }
                        }
                    }
                },
                {
                    "toolSpec": {
                        "name": "serper",
                        "description": "Search the web using Google Search API via Serper. Use this tool to find current information about topics, documentation, or solutions to technical problems.",
                        "inputSchema": {
                            "json": {
                                "type": "object",
                                "properties": {
                                    "query": {
                                        "type": "string",
                                        "description": "The search query to execute. Be specific and include technical terms when searching for technical information."
                                    }
                                },
                                "required": ["query"]
                            }
                        }
                    }
                }
            ]
        }

        try:
            # Invoke the AI model
            response = self._invoke_model(self._build_prompt(merged_history), tool_config)
            output_message = response['output']['message']
            stop_reason = response['stopReason']

            self._print_thought_process(output_message)

            if stop_reason == 'tool_use':
                # Process tool use if the AI suggests using a tool
                tool_results = self._process_tool_use(output_message)
                print(f"{COLOR_BLUE}[INFO] Stop reason: {stop_reason}{RESET_COLOR}")

                if tool_results:
                    # Add the assistant's message and tool results to conversation history
                    conversation_history.append({
                        'role': 'assistant',
                        'content': output_message['content']
                    })
                    
                    # Format tool results as a user message
                    tool_results_text = json.dumps(tool_results, indent=2)
                    conversation_history.append({
                        'role': 'user',
                        'content': [{
                            'toolResult': tool_results[0]['toolResult']
                        }]
                    })
                    
                    # Recursive call to let the model process the tool results
                    return self.generate_response(conversation_history)
                else:
                    conversation_history.append({
                        'role': 'assistant',
                        'content': [{
                            'text': "I proposed to use a tool, but the execution was skipped. How else can I assist you?"
                        }]
                    })
            else:
                # Add AI's response to conversation history
                conversation_history.append({
                    'role': 'assistant',
                    'content': output_message['content']
                })

            # Store the assistant's final response
            if self.use_memory and conversation_history[-1]["role"] == "assistant":
                assistant_response = conversation_history[-1]["content"]
                if isinstance(assistant_response, list):
                    response_text = ' '.join(
                        item.get("text", "") 
                        for item in assistant_response 
                        if isinstance(item, dict) and "text" in item
                    )
                else:
                    response_text = str(assistant_response)
                self.memory_manager.store_interaction("assistant", response_text)

        except KeyboardInterrupt:
            sys.stdout.write(f"\n{COLOR_GREEN}AI response halted by user.{RESET_COLOR}\n")
            conversation_history.append({
                'role': 'assistant',
                'content': [{
                    'text': '[Response halted by user]'
                }]
            })
        
        return conversation_history

    def _build_prompt(self, conversation_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Build the prompt for the AI model based on the conversation history.
        """
        if self.debug:
            # Create and configure the table
            table = PrettyTable()
            table.field_names = ["#", "Role", "Content", "M"]
            
            # Configure table style
            table.align = "l"  # Left alignment
            table.max_width["Content"] = 50  # Limit Content column width
            table.border = False  # No external borders
            table.header_style = "upper"
            
            # Add rows
            for idx, message in enumerate(conversation_history):
                # Extract content
                content = message.get('content', '')
                if isinstance(content, list):
                    content = content[0].get('text', str(content)) if content else ''
                elif isinstance(content, dict):
                    content = str(content)
                
                # Truncate content if necessary
                content = content[:47] + "..." if len(content) > 47 else content
                
                # Add the row
                table.add_row([
                    f"{idx:02d}",
                    message['role'][:6],  # Limit role length
                    content,
                    "*" if message.get('from_memory', False) else "-"
                ])
            
            print(f"\n{COLOR_BLUE}[DEBUG] Messages: {len(conversation_history)}")
            print(table.get_string())
            print(f"{'-' * 78}{RESET_COLOR}\n")
        
        messages = []
        memory_context = []
        current_conversation = []
        
        for idx, message in enumerate(conversation_history):
            if message.get("from_memory", False):
                # For memory messages
                cleaned_message = {
                    "role": message["role"],
                    "content": []
                }
                
                for content_item in message["content"]:
                    if isinstance(content_item, dict):
                        if "toolUse" in content_item:
                            tool_info = content_item["toolUse"]
                            cleaned_message["content"].append({
                                "text": f"[Historical command: {tool_info['name']} {json.dumps(tool_info['input'])}]"
                            })
                        elif "toolResult" in content_item:
                            tool_result = content_item["toolResult"]
                            cleaned_message["content"].append({
                                "text": f"[Historical result: {json.dumps(tool_result['content'])}]"
                            })
                        else:
                            cleaned_message["content"].append(content_item)
                    else:
                        cleaned_message["content"].append({"text": str(content_item)})
                
                memory_context.append(cleaned_message)
            else:
                # For the current conversation
                if message["role"] == "user" and isinstance(message["content"], list) and len(message["content"]) == 1:
                    content_item = message["content"][0]
                    if isinstance(content_item, dict) and "text" in content_item:
                        text_content = content_item["text"]
                        if "toolResult" in text_content:
                            try:
                                tool_results = json.loads(text_content)
                                if isinstance(tool_results, list) and len(tool_results) > 0:
                                    tool_result = tool_results[0].get("toolResult", {})
                                    current_conversation.append({
                                        "role": message["role"],
                                        "content": [{
                                            "toolResult": tool_result
                                        }]
                                    })
                                    continue
                            except json.JSONDecodeError:
                                pass
            
                # If it's not a toolResult message, process normally
                if isinstance(message.get("content"), str):
                    current_conversation.append({
                        "role": message["role"],
                        "content": [{"text": message["content"]}]
                    })
                else:
                    current_conversation.append(message)
        
        # Add memory context
        if memory_context:
            context_summary = {
                "role": "user",
                "content": [{
                    "text": "Context from previous conversation: " + 
                            " | ".join([
                                f"{msg['role']}: {' '.join(item.get('text', '') for item in msg['content'])}" 
                                for msg in memory_context
                            ])
                }]
            }
            messages.append(context_summary)
            messages.append({
                "role": "assistant",
                "content": [{
                    "text": "I understand the context from our previous conversation. How can I help you now?"
                }]
            })
        
        # Add the current conversation
        messages.extend(current_conversation)
        
        if self.debug:
            # Replace existing display with a PrettyTable
            final_table = PrettyTable()
            final_table.field_names = ["#", "Role", "Type", "Content"]
            final_table.align = "l"
            final_table.max_width["Content"] = 50
            final_table.border = False
            final_table.header_style = "upper"

            for idx, msg in enumerate(messages):
                content = msg.get('content', [])
                if isinstance(content, list) and content:
                    content_type = next(
                        (key for key in content[0].keys() if key != 'text'),
                        'text'
                    )
                    content_preview = str(content[0].get('text', content[0]))[:47] + "..." \
                        if len(str(content[0].get('text', content[0]))) > 47 \
                        else str(content[0].get('text', content[0]))
                else:
                    content_type = 'unknown'
                    content_preview = str(content)

                final_table.add_row([
                    f"{idx:02d}",
                    msg['role'][:8],
                    content_type[:10],
                    content_preview
                ])

            print(f"\n{COLOR_BLUE}[DEBUG] Final structure: {len(messages)} messages")
            print(final_table.get_string())
            print(f"[DEBUG] {'-' * 80}{RESET_COLOR}\n")
        
        return messages

    def _invoke_model(self, messages: List[Dict[str, Any]], tool_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Invoke the AI model with the given messages and tool configuration.
        
        :param messages: List of formatted messages for the AI model
        :param tool_config: Configuration of available tools for the AI
        :return: The AI model's response
        """
        inference_config = {
            "temperature": 0.0,
            "maxTokens": 4000
        }

        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        system_prompt = f"""You are an advanced AI assistant specializing in Linux, AWS, Kubernetes and Python. You are interacting with expert users who expect precise, concise, and relevant responses. Your primary function is to provide accurate information and assist with read-only operations on AWS and EKS environments. Current date: {current_date}

        Key points:
        1. Provide concise yet comprehensive answers, tailored for expert-level users.
        2. Utilize your deep knowledge of AWS CLI, kubectl, and Helm commands when appropriate.
        3. Always prioritize security and best practices in your recommendations.
        4. When suggesting the use of tools, clearly separate your explanations from the actual command suggestions.
        5. Focus on addressing the most recent question or request in the conversation.
        6. For each new task or question, always re-evaluate which tool is most appropriate:
           - Use AWS CLI for AWS-specific tasks (EC2, S3, Lambda, etc.)
           - Use kubectl for Kubernetes-related operations
           - Use Helm for Helm chart and release management
           - Don't hesitate to use multiple tools if the task requires it
           - Your choice of tool should be based on the current task, not on which tools were used previously
        7. Always remember that you have access to multiple tools (AWS CLI, kubectl, Helm) and can use them in combination to solve complex problems.
        8. If a command with one tool fails or doesn't provide enough information, consider using a different tool or approach to gather more data.
        9. Be aware that the output of tool calls is limited to 10,000 characters. Use pipes and other command-line techniques to optimize and filter results when necessary.

        Remember:
        - You have read-only access to specific AWS services and Kubernetes resources.
        - Avoid suggesting any actions that could modify the infrastructure or compromise security.
        - If you're unsure about a command's safety or appropriateness, ask for clarification before proceeding.
        - When dealing with large datasets, use command-line tools like grep, awk, sed, or jq to filter and process data efficiently.

        Your goal is to provide expert-level assistance while maintaining the integrity and security of the user's environment."""

        # Stream the response from the AI model
        response = self.bedrock.converse_stream(
            modelId=CLAUDE_MODEL,
            messages=messages,
            system=[{"text": system_prompt}],
            inferenceConfig=inference_config,
            toolConfig=tool_config
        )

        stop_reason = ""
        message = {}
        content = []
        message['content'] = content
        text = ''
        tool_use = {}

        for chunk in response['stream']:
            if 'messageStart' in chunk:
                message['role'] = chunk['messageStart']['role']
            elif 'contentBlockStart' in chunk:
                tool = chunk['contentBlockStart']['start']['toolUse']
                tool_use['toolUseId'] = tool['toolUseId']
                tool_use['name'] = tool['name']
            elif 'contentBlockDelta' in chunk:
                delta = chunk['contentBlockDelta']['delta']
                if 'toolUse' in delta:
                    if 'input' not in tool_use:
                        tool_use['input'] = ''
                    tool_use['input'] += delta['toolUse']['input']
                elif 'text' in delta:
                    text += delta['text']
                    sys.stdout.write(delta['text'])
                    sys.stdout.flush()
            elif 'contentBlockStop' in chunk:
                if 'input' in tool_use:
                    tool_use['input'] = json.loads(tool_use['input'])
                    content.append({'toolUse': tool_use})
                    tool_use = {}
                else:
                    content.append({'text': text})
                    text = ''
            elif 'messageStop' in chunk:
                stop_reason = chunk['messageStop']['stopReason']

        return {"output": {"message": message}, "stopReason": stop_reason}

    def _print_thought_process(self, output_message: Dict[str, Any]):
        """
        Print the AI's thought process when it suggests using a tool.
        
        :param output_message: The AI's output message
        """
        has_tool_use = any('toolUse' in content for content in output_message['content'])
        if has_tool_use:
            print(f"{COLOR_BLUE}\n[INFO] Model's thought process:{RESET_COLOR}")
            for content in output_message['content']:
                if 'toolUse' in content:
                    print(json.dumps({
                        "name": content['toolUse']['name'],
                        "input": content['toolUse']['input']
                    }, indent=2, ensure_ascii=False))

    def _process_tool_use(self, output_message: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Process and execute the tools suggested by the AI.
        
        :param output_message: The AI's output message containing tool use suggestions
        :return: List of tool results
        """
        tool_results = []
        for content in output_message['content']:
            if 'toolUse' in content:
                tool = content['toolUse']
                
                if tool['name'] == 'kubectl':
                    result = ToolExecutor.kubectl(tool['input']['command'])
                elif tool['name'] == 'aws':
                    result = ToolExecutor.aws(tool['input']['command'])
                elif tool['name'] == 'helm':
                    result = ToolExecutor.helm(tool['input']['command'])
                elif tool['name'] == 'serper':
                    query = tool['input'].get('query')  # Use get() for safe access
                    result = ToolExecutor.serper(query)
                else:
                    continue

                print(f"{COLOR_BLUE}[INFO] {tool['name']} command result:{RESET_COLOR}")
                
                if 'output' in result:
                    self._print_formatted_output(result['output'])
                elif 'error' in result:
                    print(f"{COLOR_RED}Error: {result['error']}{RESET_COLOR}")
                else:
                    print(json.dumps(result, indent=2))
                
                tool_result = {
                    "toolUseId": tool['toolUseId'],
                    "content": [{"json": result}]
                }
                tool_results.append({"toolResult": tool_result})
        return tool_results

    def _print_formatted_output(self, output: Any):
        """
        Print the formatted output of a tool execution.
        
        :param output: The output from the tool execution (can be string or dict)
        """
        if isinstance(output, dict):
            # Handle Serper JSON output
            if 'organic' in output:
                print("\nSearch Results:")
                for idx, result in enumerate(output['organic'][:5], 1):
                    print(f"\n{COLOR_GREEN}{idx}. {result.get('title', 'No title')}{RESET_COLOR}")
                    print(f"Link: {result.get('link', 'No link')}")
                    print(f"Snippet: {result.get('snippet', 'No description')}")
            else:
                # Fallback for other JSON outputs
                print(json.dumps(output, indent=2))
        else:
            # Handle string output (existing logic)
            lines = str(output).strip().split('\n')
            if len(lines) > 1:
                header = lines[0]
                data = lines[1:]
                print(f"{COLOR_GREEN}{header}{RESET_COLOR}")
                for line in data:
                    print(line)
            else:
                print(output)

def print_interaction_info():
    """Print information about how to interact with the AI assistant."""
    ascii_banner = """
    ____  ________  __________  ____  ______
   / __ \/  _/ __ \/ ____/ __ )/ __ \/_  __/
  / /_/ // // /_/ / __/ / __  / / / / / /
 / ____// // ____/ /___/ /_/ / /_/ / / /
/_/   /___/_/   /_____/_____/\____/ /_/

+-+-+-+-+-+-+-+ +-+-+ +-+-+-+-+-+-+-+-+-+
|p|o|w|e|r|e|d| |b|y| |A|n|t|h|r|o|p|i|c|
+-+-+-+-+-+-+-+ +-+-+ +-+-+-+-+-+-+-+-+-+
"""

    sys.stdout.write(f"{COLOR_GREEN}{ascii_banner}{RESET_COLOR}\n")
    sys.stdout.write(f"{COLOR_GREEN}When interacting, type 'EOF' and hit Enter to finalize your input.{RESET_COLOR}\n")
    sys.stdout.write(f"{COLOR_GREEN}Use 'Ctrl+c' to halt the AI's ongoing response.{RESET_COLOR}\n")
    sys.stdout.write(f"{COLOR_GREEN}Press 'Ctrl+d' when you wish to end the session.{RESET_COLOR}\n")

def run_interactive_mode(assistant: AIAssistant, conversation_history: List[Dict[str, Any]]):
    """
    Run the interactive mode of the AI assistant.
    
    :param assistant: The AIAssistant instance
    :param conversation_history: The current conversation history
    """
    with open("/dev/tty") as tty:
        sys.stdin = tty
        while True:
            try:
                sys.stdout.write(f"{COLOR_BLUE}>>>{RESET_COLOR}\n")
                user_input = []
                for line in iter(input, "EOF"):
                    user_input.append(line)
                user = "\n".join(user_input)
                conversation_history.append({"role": "user", "content": [{"text": user}]})
                sys.stdout.write(f"{COLOR_BLUE}<<<{RESET_COLOR}\n")
                conversation_history = assistant.generate_response(conversation_history)
                sys.stdout.write("\n")
            except EOFError:
                break

def main():
    """Main function to run the AI assistant."""
    parser = argparse.ArgumentParser(description='AI assistant powered by Anthropic')
    
    # Mode options
    mode_group = parser.add_argument_group('Mode options')
    mode_group.add_argument('--non-interactive', action='store_true', 
                           help='Stop after first response (default: interactive)')
    mode_group.add_argument('--fast', action='store_true',
                           help='Use Claude 3 Haiku for faster responses (default: Claude 3 Sonnet)')
    
    # Memory options
    memory_group = parser.add_argument_group('Memory options')
    memory_group.add_argument('--no-memory', action='store_true',
                            help='Disable conversation memory')
    memory_group.add_argument('--clear-memory', action='store_true',
                            help='Clear conversation memory and exit')
    
    # Debug options
    debug_group = parser.add_argument_group('Debug options')
    debug_group.add_argument('--debug', action='store_true',
                            help='Enable debug mode')
    
    args = parser.parse_args()

    check_for_pipe()

    # Clear memory if requested
    if args.clear_memory:
        try:
            memory_path = Path(MEMORY_DIR)
            if memory_path.exists():
                import shutil
                shutil.rmtree(memory_path)
                print(f"{COLOR_GREEN}Memory cleared successfully.{RESET_COLOR}")
        except Exception as e:
            print(f"{COLOR_RED}Error clearing memory: {str(e)}{RESET_COLOR}")
            sys.exit(1)
        if not args.non_interactive:
            sys.exit(0)

    bedrock = create_bedrock_client()
    # Modify the CLAUDE_MODEL based on the --fast flag
    global CLAUDE_MODEL
    CLAUDE_MODEL = CLAUDE_FAST if args.fast else CLAUDE_SMART
    
    assistant = AIAssistant(bedrock, debug=args.debug, use_memory=not args.no_memory)

    if not args.non_interactive:
        print_interaction_info()

    user = sys.stdin.read().strip()
    if not user:
        print(f"{COLOR_RED}Error: No input provided. Please pipe in some text or use interactive mode.{RESET_COLOR}")
        sys.exit(1)

    conversation_history = [
        {"role": "user", "content": user},
    ]

    sys.stdout.write(f"{COLOR_BLUE}>>>{RESET_COLOR}\n")
    sys.stdout.write(f"{user}\n\n")
    sys.stdout.write(f"{COLOR_BLUE}<<<{RESET_COLOR}\n")

    assistant.generate_response(conversation_history)

    sys.stdout.write("\n")

    if not args.non_interactive:
        run_interactive_mode(assistant, conversation_history)

if __name__ == "__main__":
    main()
