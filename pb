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

# Constants
CLAUDE_MODEL = "anthropic.claude-3-5-sonnet-20240620-v1:0"
REGION_NAME = 'us-east-1'
COLOR_BLUE = fg('light_blue')
COLOR_GREEN = fg('light_green')
COLOR_RED = fg('light_red')
RESET_COLOR = attr('reset')

def create_bedrock_client():
    # Create a new session with the 'default' profile for Bedrock
    bedrock_session = boto3.Session(profile_name='default')
    return bedrock_session.client(service_name='bedrock-runtime', region_name=REGION_NAME)

def check_for_pipe():
    if os.isatty(sys.stdin.fileno()):
        print(f"{COLOR_GREEN}PipeBot (pb) is intended to be used via a pipe.\nUsage: $ <command> | pb{RESET_COLOR}")
        sys.exit(0)

class CommandExecutor:
    @staticmethod
    def execute(command: str, tool: str, prefix: str = "") -> Dict[str, Any]:
        try:
            piped_commands = command.split('|')
            cmd_parts = shlex.split(piped_commands[0].replace('`', "'"))
        except ValueError as e:
            return {"error": f"Invalid command syntax: {str(e)}"}

        try:
            process = subprocess.Popen([prefix] + cmd_parts if prefix else cmd_parts,
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE,
                                       text=True)

            for cmd in piped_commands[1:]:
                process = subprocess.Popen(shlex.split(cmd),
                                           stdin=process.stdout,
                                           stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE,
                                           text=True)

            output, error = process.communicate()

            if process.returncode != 0:
                return {"error": f"Error running {tool} command: {error}"}

            max_output_size = 10000
            if len(output) > max_output_size:
                truncated_output = output[:max_output_size] + "\n... (output truncated)"
                return {"output": truncated_output, "truncated": True}

            return {"output": output}
        except Exception as e:
            return {"error": f"Error executing command: {str(e)}"}

class ToolExecutor:
    @staticmethod
    def awscli(command: str) -> Dict[str, Any]:
        allowed_services = [
            'acm', 'autoscaling', 'cloudformation', 'cloudfront', 'cloudtrail', 'cloudwatch',
            'directconnect', 'ebs', 'ec2', 'ecr', 'ecs', 'efs', 'eks', 'elb', 'elbv2', 'iam',
            'kafka', 'kms', 'lambda', 'logs', 'rds', 'route53', 's3', 'secretsmanager', 'sns', 'sqs',
            'ce'  # Ajout du service 'ce'
        ]
        allowed_actions = {
            'describe': ['describe-'],
            'get': ['get-', 'get-policy-version'],  # Ajout de 'get-policy-version'
            'list': ['list-'],
            'search': ['search-'],
            'lookup': ['lookup-events'],
            'filter': ['filter-log-events']
        }
        disallowed_options = ['--profile', '--region']

        try:
            cmd_parts = shlex.split(command)
            if any(option in cmd_parts for option in disallowed_options):
                return {"error": f"Disallowed options detected. The following options are not permitted: {', '.join(disallowed_options)}"}

            service = cmd_parts[0]
            if service not in allowed_services:
                return {"error": f"Service '{service}' is not allowed. Allowed services are: {', '.join(allowed_services)}"}

            if len(cmd_parts) < 2:
                return {"error": "Invalid AWS CLI command format. Action is missing."}

            action = cmd_parts[1]
            if not any(action.startswith(prefix) for prefixes in allowed_actions.values() for prefix in prefixes):
                return {"error": f"Action '{action}' is not allowed. Allowed actions start with: {', '.join([item for sublist in allowed_actions.values() for item in sublist])}"}

            # Additional parameter validation could be added here

        except Exception as e:
            return {"error": f"Error parsing AWS CLI command: {str(e)}"}

        return CommandExecutor.execute(command, "AWS CLI", prefix="aws")

    @staticmethod
    def helm(command: str) -> Dict[str, Any]:
        allowed_actions = {
            'search': ['search', 'search repo'],
            'list': ['list'],
            'get': ['get all', 'get hooks', 'get manifest', 'get notes', 'get values'],
            'history': ['history'],
            'show': ['show all', 'show chart', 'show readme', 'show values'],
            'status': ['status'],
            'env': ['env'],
            'version': ['version'],
            'dependency': ['dependency list', 'dependency build'],
            'lint': ['lint'],
            'template': ['template'],
            'verify': ['verify']
        }
        disallowed_options = ['--kube-context', '--kubeconfig']

        try:
            cmd_parts = shlex.split(command)

            # Check for disallowed options
            if any(option in cmd_parts for option in disallowed_options):
                return {"error": f"Disallowed options detected. The following options are not permitted: {', '.join(disallowed_options)}"}

            if len(cmd_parts) < 1:
                return {"error": "Invalid Helm command format. Action is missing."}

            action = cmd_parts[0]
            full_action = ' '.join(cmd_parts[:2]) if len(cmd_parts) > 1 else action

            # Check if the action (or full action) is allowed
            if not any(full_action.startswith(allowed_action) for allowed_actions in allowed_actions.values() for allowed_action in allowed_actions):
                return {"error": f"Action '{full_action}' is not allowed. Allowed actions are: {', '.join([item for sublist in allowed_actions.values() for item in sublist])}"}

            # Additional checks for specific commands
            if action == 'get' and len(cmd_parts) > 1 and cmd_parts[1] not in ['all', 'hooks', 'manifest', 'notes', 'values']:
                return {"error": f"Invalid 'get' subcommand. Allowed subcommands are: all, hooks, manifest, notes, values"}

            if action == 'show' and len(cmd_parts) > 1 and cmd_parts[1] not in ['all', 'chart', 'readme', 'values']:
                return {"error": f"Invalid 'show' subcommand. Allowed subcommands are: all, chart, readme, values"}

            # Check for potentially dangerous flags
            dangerous_flags = ['--output', '-o']  # flags that could potentially write to filesystem
            if any(flag in cmd_parts for flag in dangerous_flags):
                return {"error": f"Potentially dangerous flags detected: {', '.join(dangerous_flags)}"}

            # Additional parameter validation could be added here

        except Exception as e:
            return {"error": f"Error parsing Helm command: {str(e)}"}

        return CommandExecutor.execute(command, "Helm", prefix="helm")

    @staticmethod
    def kubectl(command: str) -> Dict[str, Any]:
        allowed_actions = {
            'get': ['get'],
            'describe': ['describe'],
            'logs': ['logs'],
            'top': ['top node', 'top pod'],
            'version': ['version'],
            'api-resources': ['api-resources'],
            'explain': ['explain']
        }
        allowed_resources = {
            'pods': ['pod', 'pods', 'po'],
            'services': ['service', 'services', 'svc'],
            'deployments': ['deployment', 'deployments', 'deploy'],
            'replicasets': ['replicaset', 'replicasets', 'rs'],
            'nodes': ['node', 'nodes', 'no'],
            'namespaces': ['namespace', 'namespaces', 'ns'],
            'configmaps': ['configmap', 'configmaps', 'cm'],
            'secrets': ['secret', 'secrets'],
            'persistentvolumes': ['persistentvolume', 'persistentvolumes', 'pv'],
            'persistentvolumeclaims': ['persistentvolumeclaim', 'persistentvolumeclaims', 'pvc'],
            'events': ['event', 'events', 'ev'],
            'ingresses': ['ingress', 'ingresses', 'ing'],
            'jobs': ['job', 'jobs'],
            'cronjobs': ['cronjob', 'cronjobs'],
            'roles': ['role', 'roles'],
            'rolebindings': ['rolebinding', 'rolebindings'],
            'clusterroles': ['clusterrole', 'clusterroles'],
            'clusterrolebindings': ['clusterrolebinding', 'clusterrolebindings'],
            'serviceaccounts': ['serviceaccount', 'serviceaccounts', 'sa'],
            'networkpolicies': ['networkpolicy', 'networkpolicies'],
            'crds': ['crd', 'crds', 'customresourcedefinition', 'customresourcedefinitions'],
            'ec2nodeclasses': ['ec2nodeclass', 'ec2nodeclasses'],
            'nodepools': ['nodepool', 'nodepools']
        }
        disallowed_options = ['--kubeconfig', '--as', '--as-group', '--token']

        try:
            cmd_parts = shlex.split(command)

            # Check for disallowed options
            if any(option in cmd_parts for option in disallowed_options):
                return {"error": f"Disallowed options detected. The following options are not permitted: {', '.join(disallowed_options)}"}

            if len(cmd_parts) < 1:
                return {"error": "Invalid kubectl command format. Action is missing."}

            action = cmd_parts[0]
            full_action = ' '.join(cmd_parts[:2]) if len(cmd_parts) > 1 else action

            # Check if the action (or full action) is allowed
            if not any(full_action.startswith(allowed_action) for allowed_actions in allowed_actions.values() for allowed_action in allowed_actions):
                return {"error": f"Action '{full_action}' is not allowed. Allowed actions are: {', '.join([item for sublist in allowed_actions.values() for item in sublist])}"}

            # Additional checks for specific commands
            if action in ['get', 'describe']:
                if len(cmd_parts) < 2:
                    return {"error": f"Invalid {action} command. Resource type is missing."}
                resource = cmd_parts[1]
                if not any(resource in aliases for aliases in allowed_resources.values()):
                    return {"error": f"Resource '{resource}' is not allowed. Allowed resources are: {', '.join([alias for aliases in allowed_resources.values() for alias in aliases])}"}

            # Check for potentially dangerous flags
            dangerous_flags = ['--filename', '-f']  # flags that could potentially write to filesystem or expose sensitive data
            if any(flag in cmd_parts for flag in dangerous_flags):
                return {"error": f"Potentially dangerous flags detected: {', '.join(dangerous_flags)}"}

            # Additional parameter validation could be added here

        except Exception as e:
            return {"error": f"Error parsing kubectl command: {str(e)}"}

        return CommandExecutor.execute(command, "kubectl", prefix="kubectl")

class AIAssistant:
    def __init__(self, bedrock_client):
        self.bedrock = bedrock_client

    def generate_response(self, conversation_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        tool_config = {
            "tools": [
                {
                    "toolSpec": {
                        "name": "awscli",
                        "description": "Execute a read-only AWS CLI command for allowed services including acm, autoscaling, cloudformation, cloudfront, cloudtrail, cloudwatch, directconnect, ebs, ec2, ecr, ecs, efs, eks, elb, elbv2, iam, kafka, kms, lambda, logs, rds, route53, s3, secretsmanager, sns, sqs, and ce. Only commands starting with 'describe', 'get', 'list', 'search', 'lookup-events', or 'filter-log-events' are allowed.",
                        "inputSchema": {
                            "json": {
                                "type": "object",
                                "properties": {
                                    "command": {
                                        "type": "string",
                                        "description": "The AWS CLI command to execute, without the 'aws' prefix. Format: '<service> <action> [parameters]'. For example, use 'ec2 describe-instances' instead of 'aws ec2 describe-instances'."
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
                        "description": "Execute a read-only kubectl command. Allowed actions include: get, describe, logs, top (node, pod), version, api-resources, and explain. Allowed resources for get and describe include: pods, services, deployments, replicasets, nodes, namespaces, configmaps, secrets, persistentvolumes, persistentvolumeclaims, events, ingresses, jobs, cronjobs, roles, rolebindings, clusterroles, clusterrolebindings, serviceaccounts, networkpolicies, crds (customresourcedefinitions), ec2nodeclasses, and nodepools.",
                        "inputSchema": {
                            "json": {
                                "type": "object",
                                "properties": {
                                    "command": {
                                        "type": "string",
                                        "description": "The kubectl command to execute, without the 'kubectl' prefix. For example, use 'get pods' instead of 'kubectl get pods'."
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
                        "description": "Execute a read-only Helm command. Allowed actions include: search, list, get (all, hooks, manifest, notes, values), history, show (all, chart, readme, values), status, env, version, dependency (list, build), lint, template, and verify.",
                        "inputSchema": {
                            "json": {
                                "type": "object",
                                "properties": {
                                    "command": {
                                        "type": "string",
                                        "description": "The Helm command to execute, without the 'helm' prefix. For example, use 'list' instead of 'helm list'."
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
            response = self._invoke_model(messages, tool_config)
            output_message = response['output']['message']
            stop_reason = response['stopReason']

            self._print_thought_process(output_message)

            if stop_reason == 'tool_use':
                tool_results = self._process_tool_use(output_message)
                
                print(f"{COLOR_BLUE}[INFO] Stop reason: {stop_reason}{RESET_COLOR}")

                if tool_results:
                    conversation_history.append({'role': 'assistant', 'content': json.dumps(output_message['content'])})
                    conversation_history.append({'role': 'user', 'content': json.dumps(tool_results)})
                    return self.generate_response(conversation_history)
                else:
                    conversation_history.append({'role': 'assistant', 'content': "I proposed to use a tool, but the execution was skipped. How else can I assist you?"})
            else:
                conversation_history.append({'role': 'assistant', 'content': output_message['content'][0]['text']})

        except KeyboardInterrupt:
            sys.stdout.write(f"\n{COLOR_GREEN}AI response halted by user.{RESET_COLOR}\n")
            conversation_history.append({'role': 'assistant', 'content': '[Response halted by user]'})

        return conversation_history

    def _build_prompt(self, conversation_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        messages = []
        for message in conversation_history:
            role = message["role"]
            content = message["content"]
            try:
                parsed_content = json.loads(content)
                messages.append({"role": role, "content": parsed_content})
            except json.JSONDecodeError:
                messages.append({"role": role, "content": [{"text": content}]})
        return messages

    def _invoke_model(self, messages: List[Dict[str, Any]], tool_config: Dict[str, Any]) -> Dict[str, Any]:
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

        Remember:
        - You have read-only access to specific AWS services and Kubernetes resources.
        - Avoid suggesting any actions that could modify the infrastructure or compromise security.
        - If you're unsure about a command's safety or appropriateness, ask for clarification before proceeding.

        Your goal is to provide expert-level assistance while maintaining the integrity and security of the user's environment."""

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
        tool_results = []
        for content in output_message['content']:
            if 'toolUse' in content:
                tool = content['toolUse']
                command = tool['input']['command']
                
                if tool['name'] == 'kubectl':
                    result = ToolExecutor.kubectl(command)
                elif tool['name'] == 'awscli':
                    result = ToolExecutor.awscli(command)
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
        # Diviser la sortie en lignes
        lines = output.strip().split('\n')
        
        # Si la sortie a un en-tête (comme pour kubectl), l'afficher différemment
        if len(lines) > 1:
            header = lines[0]
            data = lines[1:]
            print(f"{COLOR_GREEN}{header}{RESET_COLOR}")
            for line in data:
                print(line)
        else:
            print(output)

def print_interaction_info():
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
    with open("/dev/tty") as tty:
        sys.stdin = tty
        while True:
            try:
                sys.stdout.write(f"{COLOR_BLUE}>>>{RESET_COLOR}\n")
                user_input = []
                for line in iter(input, "EOF"):
                    user_input.append(line)
                user = "\n".join(user_input)
                conversation_history.append({"role": "user", "content": user})
                sys.stdout.write(f"{COLOR_BLUE}<<<{RESET_COLOR}\n")
                conversation_history = assistant.generate_response(conversation_history)
                sys.stdout.write("\n")
            except EOFError:
                break

def main():
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
