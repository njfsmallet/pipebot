#!/usr/bin/env python3
import argparse
import boto3
import json
import os
import sys
from typing import List, Dict, Any
from colored import fg, attr
import shlex
import subprocess
import time

# Constants for AWS Bedrock model and region
CLAUDE_MODEL = "anthropic.claude-3-5-sonnet-20240620-v1:0"
REGION_NAME = 'us-east-1'

# Color constants for terminal output
COLOR_BLUE = fg('light_blue')
COLOR_GREEN = fg('light_green')
COLOR_RED = fg('light_red')
RESET_COLOR = attr('reset')

def create_bedrock_client():
    """Create and return a Bedrock client using the default AWS profile."""
    bedrock_session = boto3.Session(profile_name='default')
    return bedrock_session.client(
        service_name='bedrock-runtime',
        region_name=REGION_NAME,
        config=boto3.session.Config(
            retries={'max_attempts': 10, 'mode': 'adaptive'},
            connect_timeout=5,
            read_timeout=30
        )
    )

def check_for_pipe():
    """Check if the script is being used with piped input. Exit if not."""
    if os.isatty(sys.stdin.fileno()):
        print(f"{COLOR_GREEN}PipeBot (pb) is intended to be used via a pipe.\nUsage: $ <command> | pb{RESET_COLOR}")
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
        disallowed_options = ['--profile', '--region']
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

class AIAssistant:
    """A class to handle interactions with the AI model."""

    def __init__(self, bedrock_client):
        """Initialize the AI Assistant with a Bedrock client."""
        self.bedrock = bedrock_client
        self.last_interaction_time = time.time()
        self.session_timeout = 300

    def generate_response(self, conversation_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Generate a response from the AI model based on the conversation history.
        
        :param conversation_history: List of previous messages in the conversation
        :return: Updated conversation history including the AI's response
        """
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
                                        "description": "The AWS CLI command to execute, without the 'aws' prefix. Format: '<service> <action> [parameters]'. For example, use 'ec2 describe-instances' or 's3 ls s3://bucket-name'. The options '--profile' and '--region' are not permitted."
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
                }
            ]
        }

        messages = self._build_prompt(conversation_history)

        try:
            # Invoke the AI model
            response = self._invoke_model(messages, tool_config)
            output_message = response['output']['message']
            stop_reason = response['stopReason']

            self._print_thought_process(output_message)

            if stop_reason == 'tool_use':
                # Process tool use if the AI suggests using a tool
                tool_results = self._process_tool_use(output_message)
                
                print(f"{COLOR_BLUE}[INFO] Stop reason: {stop_reason}{RESET_COLOR}")

                if tool_results:
                    # Add tool results to conversation history and generate a new response
                    conversation_history.append({'role': 'assistant', 'content': output_message['content']})
                    conversation_history.append({'role': 'user', 'content': tool_results})
                    return self.generate_response(conversation_history)
                else:
                    conversation_history.append({'role': 'assistant', 'content': "I proposed to use a tool, but the execution was skipped. How else can I assist you?"})
            else:
                # Add AI's response to conversation history
                conversation_history.append({'role': 'assistant', 'content': output_message['content']})

        except KeyboardInterrupt:
            sys.stdout.write(f"\n{COLOR_GREEN}AI response halted by user.{RESET_COLOR}\n")
            conversation_history.append({'role': 'assistant', 'content': '[Response halted by user]'})

        return conversation_history

    def _build_prompt(self, conversation_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Build the prompt for the AI model based on the conversation history.
        
        :param conversation_history: List of previous messages in the conversation
        :return: Formatted list of messages for the AI model
        """
        messages = []
        for message in conversation_history:
            role = message["role"]
            content = message["content"]
            if isinstance(content, list):
                # If the content is already a list, leave it as is
                messages.append({"role": role, "content": content})
            elif isinstance(content, dict):
                # If the content is a dictionary, put it in a list
                messages.append({"role": role, "content": [{"text": json.dumps(content)}]})
            else:
                try:
                    parsed_content = json.loads(content)
                    if isinstance(parsed_content, dict):
                        messages.append({"role": role, "content": [{"text": json.dumps(parsed_content)}]})
                    elif isinstance(parsed_content, list):
                        messages.append({"role": role, "content": parsed_content})
                    else:
                        messages.append({"role": role, "content": [{"text": content}]})
                except (json.JSONDecodeError, TypeError):
                    messages.append({"role": role, "content": [{"text": content}]})
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

        system_prompt = """You are an advanced AI assistant specializing in Linux, AWS, Kubernetes and Python. You are interacting with expert users who expect precise, concise, and relevant responses. Your primary function is to provide accurate information and assist with read-only operations on AWS and EKS environments.

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
                command = tool['input']['command']
                
                if tool['name'] == 'kubectl':
                    result = ToolExecutor.kubectl(command)
                elif tool['name'] == 'aws':
                    result = ToolExecutor.aws(command)
                elif tool['name'] == 'helm':
                    result = ToolExecutor.helm(command)
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

    def _print_formatted_output(self, output: str):
        """
        Print the formatted output of a tool execution.
        
        :param output: The output string from the tool execution
        """
        # Split the output into lines
        lines = output.strip().split('\n')
        
        # If the output has a header (like for kubectl), display it differently
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
    parser = argparse.ArgumentParser()
    parser.add_argument('--non-interactive', action='store_true', help='Stop the script after the first response')
    args = parser.parse_args()

    check_for_pipe()

    bedrock = create_bedrock_client()
    assistant = AIAssistant(bedrock)

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
