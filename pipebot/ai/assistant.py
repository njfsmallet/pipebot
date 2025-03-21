import json
import sys
import time
import datetime
import urllib3
import tiktoken
from typing import Any, Dict, List
from pipebot.aws import create_bedrock_client
from pipebot.memory.manager import MemoryManager
from pipebot.memory.knowledge_base import KnowledgeBase
from pipebot.logging_utils import Logger
from pipebot.ai.formatter import ResponseFormatter
from pipebot.tools.tool_executor import ToolExecutor
from pipebot.config import AppConfig

class AIAssistant:
    def __init__(self, app_config: AppConfig, debug=False, use_memory=True, smart_mode=False):
        self.app_config = app_config
        self.memory_manager = MemoryManager(app_config, debug=debug) if use_memory else None
        self.knowledge_base = KnowledgeBase(app_config, debug=debug)
        self.debug = debug
        self.use_memory = use_memory
        self.smart_mode = smart_mode
        self.logger = Logger(app_config, debug)
        self.formatter = ResponseFormatter(app_config)
        self.encoding = tiktoken.get_encoding("cl100k_base")  # Claude models use cl100k_base encoding
        
    def generate_response(self, conversation_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        bedrock_client = None
        try:
            bedrock_client = create_bedrock_client(self.app_config, debug=self.debug)

            current_query = conversation_history[-1]["content"]
            if isinstance(current_query, list):
                if len(current_query) == 1 and isinstance(current_query[0], dict):
                    if "toolResult" in current_query[0]:
                        tool_result = current_query[0]["toolResult"]
                        if isinstance(tool_result, dict) and "content" in tool_result:
                            current_query = str(tool_result["content"])
                    else:
                        current_query = current_query[0].get("text", "")
                else:
                    current_query = str(current_query)
            
            relevant_history = []
            if self.use_memory and current_query:
                relevant_history = self.memory_manager.get_relevant_history(current_query)
                self.memory_manager.store_interaction("user", current_query)
            
            merged_history = relevant_history + conversation_history
            
            tool_config = {
                "tools": [
                    {
                        "toolSpec": {
                            "name": "aws",
                            "description": "Execute a read-only AWS CLI command for any AWS service. Allowed actions include commands starting with: analyze, check, describe, estimate, export, filter, generate, get, help, list, lookup, ls, preview, scan, search, show, summarize, test, validate, and view.",
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
                            "description": "Search the web using Serper to find current information, documentation, examples, solutions to technical problems, verify technical details, check current best practices, and fact-check information. Use this tool whenever you need up-to-date information or need to verify your knowledge.",
                            "inputSchema": {
                                "json": {
                                    "type": "object",
                                    "properties": {
                                        "command": {
                                            "type": "string",
                                            "description": "The search query to execute. Be specific and include technical terms when searching for technical information. Format your query to get the most relevant results."
                                        }
                                    },
                                    "required": ["command"]
                                }
                            }
                        }
                    },
                    {
                        "toolSpec": {
                            "name": "python_exec",
                            "description": "Execute Python code in a secure sandbox environment. The code runs with restricted access to Python's built-in functions for safety. Available Modules: array, base64, binascii, bisect, bson, calendar, cmath, codecs, collections, datetime, dateutil, difflib, enum, fractions, functools, gzip, hashlib, heapq, itertools, json, math, matplotlib, mpmath, numpy, operator, pandas, pymongo, re, random, secrets, scipy.special, sklearn, statistics, string, sympy, textwrap, time, timeit, unicodedata, uuid, zlib. Modules can be imported directly. Example: import math, import numpy as np, from datetime import datetime. Only safe, read-only operations are allowed.",
                            "inputSchema": {
                                "json": {
                                    "type": "object",
                                    "properties": {
                                        "command": {
                                            "type": "string",
                                            "description": "The Python code to execute. The code should be complete and properly indented. Only safe operations are allowed."
                                        }
                                    },
                                    "required": ["command"]
                                }
                            }
                        }
                    }
                ]
            }

            try:
                response = self._invoke_model(self._build_prompt(merged_history), tool_config, bedrock_client)
                output_message = response['output']['message']
                stop_reason = response['stopReason']

                if stop_reason == 'tool_use':
                    tool_results = self._process_tool_use(output_message)
                    
                    if tool_results:
                        try:
                            conversation_history.append({
                                'role': 'assistant',
                                'content': output_message['content']
                            })
                            
                            tool_results_text = json.dumps(tool_results, indent=2)
                            
                            conversation_history.append({
                                'role': 'user',
                                'content': [{
                                    'toolResult': tool_results[0]['toolResult']
                                }]
                            })
                            
                            return self.generate_response(conversation_history)
                        except Exception as e:
                            self.logger.error(f"Error processing tool results: {str(e)}")
                            return conversation_history
                    else:
                        conversation_history.append({
                            'role': 'assistant',
                            'content': [{
                                'text': "I proposed to use a tool, but the execution was skipped. How else can I assist you?"
                            }]
                        })
                else:
                    conversation_history.append({
                        'role': 'assistant',
                        'content': output_message['content']
                    })

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
                sys.stdout.write(f"\n{self.app_config.colors.green}AI response halted by user.{self.app_config.colors.reset}\n")
                conversation_history.append({
                    'role': 'assistant',
                    'content': [{
                        'text': '[Response halted by user]'
                    }]
                })
            
            return conversation_history

        finally:
            pass

    def _count_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """Count the number of tokens in a list of messages."""
        token_count = 0
        
        for message in messages:
            # Count role
            token_count += len(self.encoding.encode(message["role"]))
            
            # Count content
            content = message.get("content", [])
            if isinstance(content, str):
                token_count += len(self.encoding.encode(content))
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        if "text" in item:
                            token_count += len(self.encoding.encode(item["text"]))
                        elif "toolUse" in item:
                            tool_use = item["toolUse"]
                            token_count += len(self.encoding.encode(json.dumps(tool_use)))
                        elif "toolResult" in item:
                            tool_result = item["toolResult"]
                            token_count += len(self.encoding.encode(json.dumps(tool_result)))
                    else:
                        token_count += len(self.encoding.encode(str(item)))
        
        return token_count

    def _trim_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Trim messages to stay under context limit while preserving user/assistant alternation.
        Handles tool-related messages (toolUse/toolResult) as pairs based on toolUseId.
        Context messages are preserved and not counted against the token limit.
        """
        if self.debug:
            total_tokens = self._count_tokens(messages)
            self.logger.debug(f"Starting message trimming with {len(messages)} total messages ({total_tokens} tokens)")
            
        # Find first non-context message index (skip KB and memory context messages)
        start_idx = 0
        for idx, msg in enumerate(messages):
            content = msg.get('content', [])
            if content and isinstance(content[0], dict):
                text = content[0].get('text', '')
                if not (text.startswith('Relevant information from knowledge base:') or 
                       text.startswith('Context from previous conversation:') or
                       text == 'I understand the context from the knowledge base. Let me help you with your query.' or
                       text == 'I understand the context from our previous conversation. How can I help you now?'):
                    start_idx = idx
                    break

        # Keep context messages and trim conversation messages
        context_messages = messages[:start_idx]
        conversation_messages = messages[start_idx:]

        if self.debug:
            context_tokens = self._count_tokens(context_messages)
            conv_tokens = self._count_tokens(conversation_messages)
            self.logger.debug(f"Found {len(context_messages)} context messages ({context_tokens} tokens) and {len(conversation_messages)} conversation messages ({conv_tokens} tokens)")

        # First pass: Identify and group tool pairs and regular messages
        tool_pairs = {}  # Dictionary to store tool pairs by toolUseId
        regular_messages = []  # List to store non-tool messages in order
        tool_use_positions = {}  # Store positions of toolUse messages
        
        for idx, msg in enumerate(conversation_messages):
            content = msg.get('content', [])
            is_tool_message = False
            
            if content and isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        if 'toolUse' in item:
                            tool_id = item['toolUse']['toolUseId']
                            if tool_id not in tool_pairs:
                                tool_pairs[tool_id] = {'use': None, 'result': None, 'position': idx}
                            tool_pairs[tool_id]['use'] = msg
                            tool_use_positions[idx] = tool_id
                            is_tool_message = True
                            break
                        elif 'toolResult' in item:
                            tool_id = item['toolResult']['toolUseId']
                            if tool_id not in tool_pairs:
                                tool_pairs[tool_id] = {'use': None, 'result': None, 'position': idx}
                            tool_pairs[tool_id]['result'] = msg
                            is_tool_message = True
                            break
            
            if not is_tool_message:
                regular_messages.append((idx, msg))

        # Create chronologically ordered list of complete tool pairs and regular messages
        ordered_messages = []
        
        # Add only complete tool pairs (both use and result present)
        valid_tool_pairs = {
            tool_id: pair for tool_id, pair in tool_pairs.items() 
            if pair['use'] is not None and pair['result'] is not None
        }
        
        # Combine regular messages and tool pairs while maintaining order
        current_position = 0
        while current_position < len(conversation_messages):
            if current_position in tool_use_positions:
                tool_id = tool_use_positions[current_position]
                if tool_id in valid_tool_pairs:
                    pair = valid_tool_pairs[tool_id]
                    ordered_messages.append(pair['use'])
                    ordered_messages.append(pair['result'])
                    current_position += 2  # Skip both toolUse and toolResult
                else:
                    current_position += 1
            else:
                # Find next regular message at or after current_position
                for pos, msg in regular_messages:
                    if pos == current_position:
                        ordered_messages.append(msg)
                        break
                current_position += 1

        # Trim messages until under threshold while preserving pairs
        final_conversation_messages = []
        original_message_count = len(ordered_messages)
        
        if self.debug:
            self.logger.debug(f"\nStarting message reduction process:")
            self.logger.debug(f"- Initial conversation messages: {len(ordered_messages)}")
            self.logger.debug(f"- Context threshold: {self.app_config.aws.context_threshold} tokens")
        
        # Remove messages from the beginning while preserving tool pairs
        while ordered_messages:
            conversation_tokens = self._count_tokens(ordered_messages)
            
            if conversation_tokens <= self.app_config.aws.context_threshold:
                final_conversation_messages = ordered_messages
                break
                
            # Remove two messages at a time if they form a tool pair
            if len(ordered_messages) >= 2:
                first_msg = ordered_messages[0]
                second_msg = ordered_messages[1]
                
                is_tool_pair = False
                if isinstance(first_msg.get('content', []), list) and isinstance(second_msg.get('content', []), list):
                    first_content = first_msg['content'][0] if first_msg['content'] else {}
                    second_content = second_msg['content'][0] if second_msg['content'] else {}
                    
                    if isinstance(first_content, dict) and isinstance(second_content, dict):
                        if ('toolUse' in first_content and 'toolResult' in second_content and
                            first_content.get('toolUse', {}).get('toolUseId') == 
                            second_content.get('toolResult', {}).get('toolUseId')):
                            is_tool_pair = True
                
                if is_tool_pair:
                    ordered_messages = ordered_messages[2:]  # Remove both messages
                else:
                    ordered_messages = ordered_messages[1:]  # Remove just the first message
            else:
                ordered_messages = ordered_messages[1:]  # Remove the remaining message

        # Combine context messages with trimmed conversation messages
        final_messages = context_messages + final_conversation_messages

        if self.debug:
            final_conv_tokens = self._count_tokens(final_conversation_messages)
            final_total_tokens = self._count_tokens(final_messages)
            self.logger.debug(f"\nFinal trimming results:")
            self.logger.debug(f"- Final conversation messages: {len(final_conversation_messages)}")
            self.logger.debug(f"- Final conversation tokens: {final_conv_tokens}")
            self.logger.debug(f"- Final total messages: {len(final_messages)}")
            self.logger.debug(f"- Final total tokens: {final_total_tokens}")
            reduction_percent = ((original_message_count - len(final_conversation_messages)) / original_message_count) * 100 if original_message_count > 0 else 0
            self.logger.debug(f"- Conversation reduction percentage: {reduction_percent:.1f}%\n")

        return final_messages

    def _build_prompt(self, conversation_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        messages = []
        memory_context = []
        current_conversation = []
        
        current_query = None
        for msg in reversed(conversation_history):
            if msg["role"] == "user":
                if isinstance(msg.get("content"), str):
                    current_query = msg["content"]
                elif isinstance(msg.get("content"), list) and len(msg["content"]) > 0:
                    content_item = msg["content"][0]
                    if isinstance(content_item, dict):
                        if "text" in content_item:
                            current_query = content_item["text"]
                        elif "toolResult" in content_item:
                            tool_result = content_item["toolResult"]
                            if isinstance(tool_result, dict) and "content" in tool_result:
                                content_list = tool_result["content"]
                                if isinstance(content_list, list) and len(content_list) > 0:
                                    first_content = content_list[0]
                                    if isinstance(first_content, dict) and "text" in first_content:
                                        current_query = first_content["text"]
                break
        
        if current_query:
            kb_context = self.knowledge_base.get_relevant_context(current_query)
            if kb_context:
                messages.append({
                    "role": "user",
                    "content": [{
                        "text": "Relevant information from knowledge base:\n" + kb_context
                    }]
                })
                messages.append({
                    "role": "assistant",
                    "content": [{
                        "text": "I understand the context from the knowledge base. Let me help you with your query."
                    }]
                })
        
        for idx, message in enumerate(conversation_history):
            if message.get("from_memory", False):
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
            
                if isinstance(message.get("content"), str):
                    current_conversation.append({
                        "role": message["role"],
                        "content": [{"text": message["content"]}]
                    })
                else:
                    current_conversation.append(message)
        
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
        
        messages.extend(current_conversation)
        
        # Trim messages to stay under context limit
        messages = self._trim_messages(messages)
        
        return messages

    def _invoke_model(self, messages: List[Dict[str, Any]], tool_config: Dict[str, Any], bedrock_client) -> Dict[str, Any]:
        model_id = self.app_config.aws.model_id_smart if self.smart_mode else self.app_config.aws.model_id
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                max_tokens = self.app_config.aws.max_tokens
                
                inference_config = {
                    "temperature": 0.0,
                    "maxTokens": max_tokens
                }

                current_date = datetime.datetime.now().strftime("%Y-%m-%d")
                system_prompt = f"""Purpose: Technical assistant specializing in Linux, AWS, Kubernetes, and Python. Current date: {current_date}

You must follow these guidelines:

FORMATTING
Format your responses professionally without emojis or decorative symbols. Use standard bullet points and plain text headers. Present technical information in a structured, easy-to-read format.

ANALYSIS
When analyzing information, clearly label the analysis section, use concise bullet points for key findings, and maintain clean indentation for configurations and details.

TECHNICAL OUTPUT 
Keep all technical output clean, consistently spaced, and well-organized. Focus on clarity and readability.

SECURITY
Maintain strict read-only access to services. Proactively suggest secure alternatives and adhere to AWS and Kubernetes best practices.

SEARCH CAPABILITY
You have the ability to search the internet using the 'serper' tool. Use it proactively when you need to verify information, find current documentation, or research solutions. Never say you cannot search - instead, use the serper tool to find the information.

TONE
Maintain professionalism while being helpful and approachable. Focus on accuracy and clarity in all responses."""

                if self.debug:
                    debug_payload = {
                        "messages": messages,
                        "system": [{"text": system_prompt}],
                        "inferenceConfig": inference_config,
                        "toolConfig": tool_config
                    }
                    self.logger.debug(f"Bedrock Request:\n{json.dumps(debug_payload, indent=2)}\n")

                response = bedrock_client.converse_stream(
                    modelId=model_id,
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

                try:
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

                except (urllib3.exceptions.ReadTimeoutError, TimeoutError) as e:
                    if attempt < max_retries - 1:
                        self.logger.info(f"Response timeout, retrying... ({attempt + 1}/{max_retries})")
                        time.sleep(retry_delay * (attempt + 1))
                        bedrock_client = create_bedrock_client(self.app_config)
                        continue
                    else:
                        self.logger.error("Maximum retries reached. The response was incomplete.")
                        if content:
                            return {"output": {"message": message}, "stopReason": "timeout"}
                        raise

                return {"output": {"message": message}, "stopReason": stop_reason}

            except Exception as e:
                if attempt < max_retries - 1:
                    self.logger.info(f"Error occurred, retrying... ({attempt + 1}/{max_retries})")
                    time.sleep(retry_delay * (attempt + 1))
                    bedrock_client = create_bedrock_client(self.app_config)
                    continue
                else:
                    self.logger.error(f"Maximum retries reached. Error: {str(e)}")
                    raise

    def _print_thought_process(self, output_message: Dict[str, Any]):
        has_tool_use = any('toolUse' in content for content in output_message['content'])
        if has_tool_use:
            for content in output_message['content']:
                if 'toolUse' in content:
                    tool = content['toolUse']
                    print(f"└── {tool['name']} {tool['input']['command']}")

    def _simplify_output_for_context(self, output: Any) -> Dict[str, Any]:
        if isinstance(output, dict):
            output = json.dumps(output, ensure_ascii=False, indent=2)
        
        output_str = str(output)
        simplified = ' '.join(output_str.split())
        
        truncated = len(simplified) > self.app_config.max_output_size
        if truncated:
            simplified = simplified[:self.app_config.max_output_size] + "..."
        
        return {
            "content": simplified,
            "truncated": truncated
        }

    def _process_tool_use(self, output_message: Dict[str, Any]) -> List[Dict[str, Any]]:
        tool_results = []
        try:
            for content in output_message['content']:
                if 'toolUse' in content:
                    tool = content['toolUse']
                    
                    result = None
                    if tool['name'] == 'kubectl':
                        result = ToolExecutor.kubectl(tool['input']['command'], app_config=self.app_config)
                    elif tool['name'] == 'aws':
                        result = ToolExecutor.aws(tool['input']['command'], app_config=self.app_config)
                    elif tool['name'] == 'helm':
                        result = ToolExecutor.helm(tool['input']['command'], app_config=self.app_config)
                    elif tool['name'] == 'serper':
                        command = tool['input'].get('command')
                        result = ToolExecutor.serper(command, app_config=self.app_config)
                    elif tool['name'] == 'python_exec':
                        result = ToolExecutor.python_exec(tool['input']['command'])
                    else:
                        continue

                    print()
                    print(f"└─ {tool['name']} {tool['input']['command']}")
                    
                    if self.debug:
                        self.logger.debug(f"{tool['name']} command result:")
                        
                        if 'output' in result:
                            self._print_formatted_output(result['output'])
                        elif 'error' in result:
                            self.logger.error(f"Error: {result['error']}")
                        else:
                            print(json.dumps(result, indent=2))
                        print()
                    else:
                        if 'output' in result:
                            print(f"   └─ {self.app_config.colors.green}✓ Success{self.app_config.colors.reset}")
                        elif 'error' in result:
                            print(f"   └─ {self.app_config.colors.red}✗ Error{self.app_config.colors.reset}")
                        else:
                            print(f"   └─ {self.app_config.colors.blue}? Unknown status{self.app_config.colors.reset}")

                    if 'output' in result:
                        simplified_result = self._simplify_output_for_context(result['output'])
                        tool_result = {
                            "toolUseId": tool['toolUseId'],
                            "content": [
                                {"text": simplified_result["content"]},
                                {"text": f"[Output truncated: {simplified_result['truncated']}]"}
                            ]
                        }
                    elif 'error' in result:
                        tool_result = {
                            "toolUseId": tool['toolUseId'],
                            "content": [
                                {"text": f"Error: {result['error']}"},
                                {"text": "[Output truncated: false]"}
                            ]
                        }
                    else:
                        tool_result = {
                            "toolUseId": tool['toolUseId'],
                            "content": [
                                {"text": str(result)},
                                {"text": "[Output truncated: false]"}
                            ]
                        }
                    
                    tool_results.append({"toolResult": tool_result})
                    
        except Exception as e:
            print(f"{self.app_config.colors.red}[ERROR] Error in _process_tool_use: {str(e)}{self.app_config.colors.reset}")
        
        return tool_results

    def _print_formatted_output(self, output: Any):
        if isinstance(output, dict):
            if 'organic' in output:
                print(self.formatter.format_search_results(output['organic']))
            else:
                print(self.formatter.format_tool_output(output))
        else:
            print(self.formatter.format_command_output(output)) 