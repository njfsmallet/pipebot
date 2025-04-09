import json
import sys
import time
import datetime
import urllib3
import tiktoken
import os
import logging
from typing import Any, Dict, List
from pipebot.aws import create_bedrock_client
from pipebot.memory.manager import MemoryManager
from pipebot.memory.knowledge_base import KnowledgeBase
from pipebot.logging_config import StructuredLogger
from pipebot.ai.formatter import ResponseFormatter
from pipebot.tools.tool_executor import ToolExecutor
from pipebot.config import AppConfig

class AIAssistant:
    def __init__(self, app_config: AppConfig, use_memory=True, smart_mode=False):
        self.app_config = app_config
        self.memory_manager = MemoryManager(app_config) if use_memory else None
        self.knowledge_base = KnowledgeBase(app_config)
        self.use_memory = use_memory
        self.smart_mode = smart_mode
        self.logger = StructuredLogger("AIAssistant")
        self.formatter = ResponseFormatter(app_config)
        self.encoding = tiktoken.get_encoding("cl100k_base")  # Claude models use cl100k_base encoding
        
    def generate_response(self, conversation_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        bedrock_client = None
        try:
            bedrock_client = create_bedrock_client(self.app_config)

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
                            "name": "switch_context",
                            "description": "Search for matching AWS profile and kubectl context based on a search term. This tool helps identify the appropriate AWS profile and kubectl context to use for subsequent commands. It searches through available AWS profiles and kubectl contexts to find matches containing the search term. Examples: 'switch_context k-nine-npr' to find profiles/contexts for the k-nine-npr cluster, 'switch_context 123456789012' to find profiles/contexts for a specific AWS account.",
                            "inputSchema": {
                                "json": {
                                    "type": "object",
                                    "properties": {
                                        "command": {
                                            "type": "string",
                                            "description": "The search term to find matching AWS profile and kubectl context. Examples: 'k-nine-npr' for a cluster name, '123456789012' for an AWS account ID, 'prod' for a production environment. The tool will return all matching profiles and contexts found."
                                        }
                                    },
                                    "required": ["command"]
                                }
                            }
                        }
                    },
                    {
                        "toolSpec": {
                            "name": "aws",
                            "description": "Execute a read-only AWS CLI command for any AWS service. Allowed actions include commands starting with: analyze, check, describe, estimate, export, filter, generate, get, help, list, lookup, ls, preview, scan, search, show, summarize, test, validate, and view. You must specify the AWS profile using the --profile option to ensure the command runs with the correct credentials.",
                            "inputSchema": {
                                "json": {
                                    "type": "object",
                                    "properties": {
                                        "command": {
                                            "type": "string",
                                            "description": "The AWS CLI command to execute, without the 'aws' prefix. Format: '<service> <action> [parameters] --profile <profile_name>'. For example, use 'ec2 describe-instances --profile my-profile' or 's3 ls s3://bucket-name --profile my-profile'. The --profile option is required to specify which AWS profile to use."
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
                            "description": "Execute a read-only kubectl command. Allowed actions include: api-resources, api-versions, cluster-info, describe, explain, get, logs, top, and version. You must specify the kubectl context using the --context option to ensure the command runs with the correct cluster configuration.",
                            "inputSchema": {
                                "json": {
                                    "type": "object",
                                    "properties": {
                                        "command": {
                                            "type": "string",
                                            "description": "The kubectl command to execute, without the 'kubectl' prefix. Format: '<command> [parameters] --context <context_name>'. For example, use 'get pods --context my-cluster' or 'describe node --context my-cluster'. The --context option is required to specify which cluster to use. The options '--kubeconfig', '--as', '--as-group', and '--token' are not permitted."
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
                            "description": "Execute a read-only Helm command. Allowed actions include: dependency, env, get, history, inspect, lint, list, search, show, status, template, verify, and version. You must specify the kubectl context using the --kube-context option to ensure the command runs with the correct cluster configuration.",
                            "inputSchema": {
                                "json": {
                                    "type": "object",
                                    "properties": {
                                        "command": {
                                            "type": "string",
                                            "description": "The Helm command to execute, without the 'helm' prefix. Format: '<command> [parameters] --kube-context <context_name>'. For example, use 'list --kube-context my-cluster' or 'status my-release --kube-context my-cluster'. The --kube-context option is required to specify which cluster to use. The option '--kubeconfig' is not permitted."
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
                            "description": "Search the web using Serper, a Google Search API that returns search results. This tool provides search results including organic results, knowledge graphs, and related searches. It does not fetch or parse specific web pages - it only returns search results. Use this tool to find current information, documentation, examples, solutions to technical problems, verify technical details, check current best practices, and fact-check information. The results will include titles, snippets, and links to relevant pages.",
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
                    },
                    {
                        "toolSpec": {
                            "name": "think",
                            "description": "Use this tool for two purposes: 1) Complex reasoning and planning - when you need to think through a problem step by step or plan your approach. 2) Memory retrieval - when you need to force recall specific information from previous conversations. The thought will be appended to the conversation history and can help trigger relevant memory retrieval in future interactions. This is particularly useful when you need to ensure certain information from past conversations is brought back into context.",
                            "inputSchema": {
                                "json": {
                                    "type": "object",
                                    "properties": {
                                        "command": {
                                            "type": "string",
                                            "description": "A thought to think about or a specific memory to recall."
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
                            # Ne garder que le premier outil utilisé
                            first_tool_use = None
                            for content in output_message['content']:
                                if 'toolUse' in content:
                                    first_tool_use = content
                                    break
                            
                            if first_tool_use:
                                conversation_history.append({
                                    'role': 'assistant',
                                    'content': [first_tool_use]
                                })
                                
                                conversation_history.append({
                                    'role': 'user',
                                    'content': [{
                                        'toolResult': tool_results[0]['toolResult']
                                    }]
                                })
                                
                                return self.generate_response(conversation_history)
                        except Exception as e:
                            self.logger.error("Error processing tool results", error=str(e), tool="tool_processor")
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
                self.logger.info(f"AI response halted by user.")
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
        
        self.logger.debug(f"Starting message reduction process:")
        self.logger.debug(f"Initial conversation messages: {len(ordered_messages)}")
        self.logger.debug(f"Context threshold: {self.app_config.aws.context_threshold} tokens")
        
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

        final_conv_tokens = self._count_tokens(final_conversation_messages)
        final_total_tokens = self._count_tokens(final_messages)
        self.logger.debug(f"Final trimming results:")
        self.logger.debug(f"Final conversation messages: {len(final_conversation_messages)}")
        self.logger.debug(f"Final conversation tokens: {final_conv_tokens}")
        self.logger.debug(f"Final total messages: {len(final_messages)}")
        self.logger.debug(f"Final total tokens: {final_total_tokens}")
        reduction_percent = ((original_message_count - len(final_conversation_messages)) / original_message_count) * 100 if original_message_count > 0 else 0
        self.logger.debug(f"Conversation reduction percentage: {reduction_percent:.1f}%\n")

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
                kb_message = {
                    "role": "user",
                    "content": [{
                        "text": "Relevant information from knowledge base:\n" + kb_context
                    }]
                }
                kb_tokens = self._count_tokens([kb_message])
                if kb_tokens <= self.app_config.aws.max_context_tokens_kb_memory:
                    messages.append(kb_message)
                    messages.append({
                        "role": "assistant",
                        "content": [{
                            "text": "I understand the context from the knowledge base. Let me help you with your query."
                        }]
                    })
                else:
                    self.logger.warning(f"Knowledge base context too large ({kb_tokens} tokens), skipping...")
        
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
            # Calculate total tokens for memory context
            memory_tokens = self._count_tokens(memory_context)
            if memory_tokens > self.app_config.aws.max_context_tokens_kb_memory:
                # If memory context is too large, keep only the most recent messages
                while memory_tokens > self.app_config.aws.max_context_tokens_kb_memory and memory_context:
                    removed = memory_context.pop(0)
                    memory_tokens -= self._count_tokens([removed])
                self.logger.warning(f"Memory context reduced to {memory_tokens} tokens")
            
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
                system_prompt = f"""Purpose: General-purpose AI assistant with expertise in technology. Current date: {current_date}

You must follow these guidelines:

FORMATTING
Format your responses professionally without emojis or decorative symbols using Markdown formatting to enhance readability and structure. Present information in a clear, well-organized format.
- Use Markdown formatting extensively (``` for code blocks, ** for bold, _ for italic, etc.)
- Use proper spacing, indentation, and Markdown headers (#, ##, ###)
- Use Markdown bullet points (-) and numbered lists for structured information
- Use code blocks with language specification for technical content
- Use blockquotes for important notes or warnings

ANALYSIS
When analyzing information, clearly label the analysis section, use concise bullet points for key findings, and maintain clean indentation for configurations and details.

TECHNICAL OUTPUT 
Keep all technical output clean, consistently spaced, and well-organized. Focus on clarity and readability.

SECURITY
Maintain strict read-only access to services. Proactively suggest secure alternatives and adhere to AWS and Kubernetes best practices.

SEARCH CAPABILITY
You have the ability to search the internet using the 'serper' tool. Use it proactively when you need to verify information, find current documentation, or research solutions. Never say you cannot search - instead, use the serper tool to find the information.

THINK TOOL USAGE
Before taking any action or responding to the user after receiving tool results, use the think tool as a scratchpad to:
- List the specific requirements and constraints
- Verify all required information is collected
- Iterate over tool results for correctness
- Force recall relevant information from previous conversations

Here are some examples of what to iterate over inside the think tool:
<think_tool_example_1>
User: "I want to list the namespaces in the prod cluster"
- Need to verify:
  * Available kubectl contexts for prod cluster
  * AWS profiles for prod account
  * Cluster access
- Analysis:
  * Need to find the correct context and profile for the prod cluster
  * Will need to use kubectl get namespaces command
  * Should verify cluster access before proceeding
- Plan:
1. Use switch_context tool to find matching AWS profile and kubectl context for prod cluster:
   - Example: 'switch_context k-nine-prod'
2. Use the found context with kubectl command: 'kubectl get namespaces --context <found_context>'
3. If needed, use the found profile with AWS commands: 'aws eks describe-cluster --name <cluster_name> --profile <found_profile>'
4. If access issues, use serper to check documentation for troubleshooting
</think_tool_example_1>

<think_tool_example_2>
User: "I want to list all S3 buckets in the prod account"
- Need to verify:
  * Available AWS profiles for prod account
  * Region settings
  * S3 access permissions
- Analysis:
  * Need to find the correct AWS profile for the prod account
  * Will need to use aws s3 ls command
  * Should verify S3 access before proceeding
- Plan:
1. Use switch_context tool to find matching AWS profile for prod account:
   - Example: 'switch_context 123456789012' (prod account ID)
2. Use the found profile with AWS command: 'aws s3 ls --profile <found_profile>'
3. If needed, verify account access: 'aws sts get-caller-identity --profile <found_profile>'
4. If access issues, use serper to check documentation for troubleshooting
</think_tool_example_2>

<think_tool_example_3>
User: "Last week we had an issue with the prod cluster where pods were failing to start. Can you help me recall what we did to fix it?"
- Need to recall:
  * Previous incident details
  * Commands executed
  * Context and profile used
  * Resolution steps
- Memory retrieval strategy:
  * Generate a thought that references the incident:
    - Time period (last week)
    * Environment (prod cluster)
    * Issue type (pods failing to start)
    * Commands used (kubectl, aws)
  * Example thought:
    "Recalling last week's incident where prod cluster pods were failing to start. We used kubectl describe pods and aws eks describe-cluster to diagnose the issue. Need to find the correct context and profile we used."
- Plan:
1. Use think tool to force memory retrieval of the incident
2. Use switch_context to find matching profile and context for prod cluster:
   - Example: 'switch_context k-nine-prod'
3. Once context is restored, retry the diagnostic commands:
   - kubectl describe pods --context <found_context>
   - aws eks describe-cluster --name <cluster_name> --profile <found_profile>
4. If needed, search for similar incidents in documentation
</think_tool_example_3>

TONE
Maintain a friendly and approachable tone while being professional. Be helpful and engaging in all interactions, whether technical or general. Focus on clarity and accuracy in your responses."""

                debug_payload = {
                    "messages": messages,
                    "system": [{"text": system_prompt}],
                    "inferenceConfig": inference_config,
                    "toolConfig": tool_config
                }
                self.logger.debug(f"Bedrock Request:\n{json.dumps(debug_payload, indent=2)}\n")

                try:
                    response = bedrock_client.converse(
                        modelId=model_id,
                        messages=messages,
                        system=[{"text": system_prompt}],
                        inferenceConfig=inference_config,
                        toolConfig=tool_config
                    )

                    for content in response['output']['message']['content']:
                        if 'text' in content:
                            self.logger.info(content['text'])

                    return {
                        "output": {
                            "message": response['output']['message']
                        },
                        "stopReason": response['stopReason']
                    }

                except (urllib3.exceptions.ReadTimeoutError, TimeoutError) as e:
                    if attempt < max_retries - 1:
                        self.logger.info("Response timeout, retrying", attempt=attempt + 1, max_retries=max_retries)
                        time.sleep(retry_delay * (attempt + 1))
                        bedrock_client = create_bedrock_client(self.app_config)
                        continue
                    else:
                        self.logger.error("Maximum retries reached", error="The response was incomplete")
                        raise

            except Exception as e:
                if attempt < max_retries - 1:
                    self.logger.info("Error occurred, retrying", attempt=attempt + 1, max_retries=max_retries)
                    time.sleep(retry_delay * (attempt + 1))
                    bedrock_client = create_bedrock_client(self.app_config)
                    continue
                else:
                    self.logger.error("Maximum retries reached", error=str(e))
                    raise

    def _print_thought_process(self, output_message: Dict[str, Any]):
        has_tool_use = any('toolUse' in content for content in output_message['content'])
        if has_tool_use:
            for content in output_message['content']:
                if 'toolUse' in content:
                    tool = content['toolUse']
                    self.logger.info(f"└── {tool['name']} {tool['input']['command']}")

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
                    if tool['name'] == 'switch_context':
                        result = ToolExecutor.switch_context(tool['input']['command'], app_config=self.app_config)
                    elif tool['name'] == 'kubectl':
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
                    elif tool['name'] == 'think':
                        result = ToolExecutor.think(tool['input']['command'])
                    else:
                        continue

                    self.logger.info(f"└─ {tool['name']} {tool['input']['command']}")
                    
                    self.logger.debug("Tool command result", tool=tool['name'], result=result)
                        
                    if 'output' in result:
                        self.logger.info(f"   └─ {self.app_config.colors.green}✓ Success{self.app_config.colors.reset}")
                    elif 'error' in result:
                        self.logger.info(f"   └─ {self.app_config.colors.red}✗ Error{self.app_config.colors.reset}")
                    else:
                        self.logger.info(f"   └─ {self.app_config.colors.blue}? Unknown status{self.app_config.colors.reset}")

                    if 'output' in result:
                        simplified_result = self._simplify_output_for_context(result['output'])
                        tool_result = {
                            "toolUseId": tool['toolUseId'],
                            "content": [
                                {"text": simplified_result["content"]},
                                {"text": f"[Output truncated: {str(simplified_result['truncated']).lower()}]"}
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
                        result_str = str(result)
                        if result_str:
                            tool_result = {
                                "toolUseId": tool['toolUseId'],
                                "content": [
                                    {"text": result_str},
                                    {"text": "[Output truncated: false]"}
                                ]
                            }
                        else:
                            tool_result = {
                                "toolUseId": tool['toolUseId'],
                                "content": [
                                    {"text": "No output available"},
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
