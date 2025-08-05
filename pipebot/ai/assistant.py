import json
import sys
import time
import datetime
import urllib3
import tiktoken
import os
import logging
import asyncio
from typing import Any, Dict, List, AsyncGenerator
from pipebot.aws import create_bedrock_client
from pipebot.memory.manager import MemoryManager
from pipebot.memory.knowledge_base import KnowledgeBase
from pipebot.logging_config import StructuredLogger
from pipebot.ai.formatter import ResponseFormatter
from pipebot.tools.mcp_executor import get_mcp_executor, close_mcp_executor
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
        self.current_conversation = []  # Track current conversation for streaming updates
        


    def _get_tool_config(self):
        """Get tool configuration dynamically from MCP server."""
        # Since we're using MCP exclusively, we'll return an empty tool config
        # The tools are defined in the MCP server and will be discovered dynamically
        return {
            "tools": []
        }
    
    async def _get_mcp_tools_config(self):
        """Get tool configuration dynamically from all MCP servers."""
        try:
            from pipebot.tools.mcp_executor import get_mcp_executor
            
            mcp_executor = await get_mcp_executor(self.app_config)
            
            # Use the new list_available_tools method
            tools_result = await mcp_executor.list_available_tools()
            
            if 'error' in tools_result:
                self.logger.error(f"Failed to get tools: {tools_result['error']}")
                return {"tools": []}
            
            all_tools = []
            tools_info = tools_result.get('tools', {})
            
            # Convert discovered tools to Bedrock format
            for tool_name, tool_info in tools_info.items():
                bedrock_tool = {
                    "toolSpec": {
                        "name": tool_name,
                        "description": tool_info.get('description', ''),
                        "inputSchema": {
                            "json": tool_info.get('inputSchema', {})
                        }
                    }
                }
                all_tools.append(bedrock_tool)
            
            self.logger.debug(f"Discovered {len(all_tools)} tools from MCP servers")
            
            # Add cachePoint configuration
            all_tools.append({
                "cachePoint": {
                    "type": "default"
                }
            })
            
            return {"tools": all_tools}
                    
        except Exception as e:
            self.logger.error(f"Error getting MCP tools config: {e}")
            # Fallback to empty config
            return {"tools": []}
        
    async def generate_response(self, conversation_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
            
            # Use MCP tools configuration dynamically
            tool_config = await self._get_mcp_tools_config()

            try:
                response = self._invoke_model(self._build_prompt(merged_history), tool_config, bedrock_client)
                output_message = response['output']['message']
                stop_reason = response['stopReason']

                # Log detailed usage metrics
                if 'usage' in response:
                    usage = response['usage']
                    self.logger.debug(f"Usage Summary - Input: {usage.get('inputTokens', 0)} tokens, "
                                     f"Output: {usage.get('outputTokens', 0)} tokens, "
                                     f"Total: {usage.get('totalTokens', 0)} tokens, "
                                     f"Cache Read: {usage.get('cacheReadInputTokens', 0)} tokens, "
                                     f"Cache Write: {usage.get('cacheWriteInputTokens', 0)} tokens, "
                                     f"Response Latency: {response['latencyMs']} ms")

                if stop_reason == 'tool_use':
                    tool_results = await self._process_tool_use(output_message)
                    
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
                                
                                return await self.generate_response(conversation_history)
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
    
    def get_current_conversation(self) -> List[Dict[str, Any]]:
        """Get the current conversation history."""
        return self.current_conversation.copy()
    
    async def generate_response_stream(self, conversation_history: List[Dict[str, Any]], max_tool_iterations: int = 25) -> AsyncGenerator[Dict[str, Any], None]:
        """Generate response with streaming updates for tool execution."""
        self.current_conversation = conversation_history.copy()
        bedrock_client = None
        
        # Protection contre récursion infinie
        if max_tool_iterations <= 0:
            yield {"type": "error", "message": "Maximum tool iterations reached"}
            return
        
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
            
            # Use MCP tools configuration dynamically
            tool_config = await self._get_mcp_tools_config()

            try:
                # Status message removed for cleaner output
                response = self._invoke_model(self._build_prompt(merged_history), tool_config, bedrock_client)
                output_message = response['output']['message']
                stop_reason = response['stopReason']

                # Log detailed usage metrics
                if 'usage' in response:
                    usage = response['usage']
                    self.logger.debug(f"Usage Summary - Input: {usage.get('inputTokens', 0)} tokens, "
                                     f"Output: {usage.get('outputTokens', 0)} tokens, "
                                     f"Total: {usage.get('totalTokens', 0)} tokens, "
                                     f"Cache Read: {usage.get('cacheReadInputTokens', 0)} tokens, "
                                     f"Cache Write: {usage.get('cacheWriteInputTokens', 0)} tokens, "
                                     f"Response Latency: {response['latencyMs']} ms")

                if stop_reason == 'tool_use':
                    # Process tool use with streaming updates
                    async for update in self._process_tool_use_stream(output_message):
                        yield update
                    
                    # Continue processing - recursively call to handle next response
                    # Status message removed for cleaner output
                    
                    self.logger.debug(f"About to continue recursively. Conversation length: {len(self.current_conversation)}")
                    
                    # Recursively process the conversation to get the final response
                    async for update in self.generate_response_stream(self.current_conversation, max_tool_iterations - 1):
                        yield update
                    
                    # Exit here since recursive call handles the rest
                    return
                else:
                    self.current_conversation.append({
                        'role': 'assistant',
                        'content': output_message['content']
                    })
                    
                    yield {
                        "type": "assistant_response",
                        "content": output_message['content']
                    }

                if self.use_memory and self.current_conversation[-1]["role"] == "assistant":
                    assistant_response = self.current_conversation[-1]["content"]
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
                self.current_conversation.append({
                    'role': 'assistant',
                    'content': [{
                        'text': '[Response halted by user]'
                    }]
                })
                yield {
                    "type": "assistant_response",
                    "content": [{'text': '[Response halted by user]'}]
                }

        except Exception as e:
            self.logger.error(f"Error in generate_response_stream: {str(e)}")
            yield {"type": "error", "message": str(e)}
        finally:
            pass
    
    async def _process_tool_use_stream(self, output_message: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        """Process tool use with streaming updates."""
        try:
            for content in output_message['content']:
                if 'toolUse' in content:
                    tool = content['toolUse']
                    
                    self.logger.debug(f"Processing tool: {tool['name']} with command: {self._get_tool_parameter(tool)}")
                    
                    # Send tool execution start update
                    command_to_display = self._get_tool_parameter(tool)
                    
                    yield {
                        "type": "tool_start",
                        "tool_name": tool['name'], 
                        "command": command_to_display
                    }
                    
                    # Execute the tool
                    result = await self._execute_tool(tool)
                    
                    # Send tool execution result update
                    if 'output' in result:
                        # Limit output size for streaming to prevent JSON parsing errors
                        output_str = str(result['output'])
                        if len(output_str) > 10000:  # Limit to prevent JSON parsing issues
                            output_str = output_str[:10000] + "\n... [Output truncated for display]"
                        
                        yield {
                            "type": "tool_result",
                            "tool_name": tool['name'],
                            "success": True,
                            "output": output_str
                        }
                    elif 'error' in result:
                        yield {
                            "type": "tool_result", 
                            "tool_name": tool['name'],
                            "success": False,
                            "error": result['error']
                        }
                    
                    # Add tool use to conversation
                    first_tool_use = content
                    self.current_conversation.append({
                        'role': 'assistant',
                        'content': [first_tool_use]
                    })
                    
                    # Create tool result for conversation
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
                        tool_result = {
                            "toolUseId": tool['toolUseId'],
                            "content": [
                                {"text": result_str if result_str else "No output available"},
                                {"text": "[Output truncated: false]"}
                            ]
                        }
                    
                    self.current_conversation.append({
                        'role': 'user',
                        'content': [{
                            'toolResult': tool_result
                        }]
                    })
                    
                    self.logger.debug(f"Added tool result to conversation. Conversation now has {len(self.current_conversation)} messages")
                    
                    break  # Only process first tool for now
                    
        except Exception as e:
            self.logger.error("Error processing tool use stream", error=str(e))
            yield {"type": "error", "message": f"Error processing tool: {str(e)}"}
    
    
    async def _execute_tool(self, tool: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool asynchronously."""
        return await self._execute_tool_mcp(tool)
    
    async def _execute_tool_mcp(self, tool: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool using MCP with dynamic discovery."""
        try:
            mcp_executor = await get_mcp_executor(self.app_config)
            
            tool_name = tool['name']
            tool_input = tool['input']
            
            # Pass the tool input directly to the MCP executor
            # The MCP server will handle parameter validation and mapping
            return await mcp_executor.call_tool(tool_name, tool_input)
            
        except Exception as e:
            self.logger.error(f"Error executing tool {tool['name']} via MCP: {e}")
            return {"error": f"Error executing {tool['name']}: {str(e)}"}
    

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
        
    def _summarize_message_content(self, message: Dict[str, Any]) -> str:
        """Create a concise summary of message content for debugging purposes."""
        content = message.get('content', [])
        summary = []
        
        # Summarize based on content type
        if isinstance(content, str):
            # Truncate string content if too long
            if len(content) > 50:
                summary.append(f"text='{content[:50]}...'")
            else:
                summary.append(f"text='{content}'")
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    if "text" in item:
                        text = item["text"]
                        # Truncate text if too long
                        if len(text) > 50:
                            summary.append(f"text='{text[:50]}...'")
                        else:
                            summary.append(f"text='{text}'")
                    elif "toolUse" in item:
                        tool_use = item["toolUse"]
                        tool_name = tool_use.get('name', 'unknown')
                        tool_id = tool_use.get('toolUseId', 'no-id')
                        # Get summary of tool input
                        param_summary = self._get_tool_parameter(tool_use)
                        summary.append(f"toolUse={tool_name}(id={tool_id}, {param_summary})")
                    elif "toolResult" in item:
                        tool_result = item["toolResult"]
                        tool_id = tool_result.get('toolUseId', 'no-id')
                        # Summarize content if available
                        if 'content' in tool_result:
                            result_content = tool_result['content']
                            if isinstance(result_content, list) and len(result_content) > 0:
                                first_item = result_content[0]
                                if isinstance(first_item, dict) and 'text' in first_item:
                                    text = first_item['text']
                                    if len(text) > 30:
                                        text = text[:30] + '...'
                                    summary.append(f"toolResult(id={tool_id}, text='{text}')")
                                    continue
                            summary.append(f"toolResult(id={tool_id})")
                        else:
                            summary.append(f"toolResult(id={tool_id})")
                    elif "cachePoint" in item:
                        summary.append("cachePoint")
        
        if not summary:
            return "empty"
        return ", ".join(summary)

    def _trim_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Trim messages to stay under context limit while preserving user/assistant alternation.
        Handles tool-related messages (toolUse/toolResult) as pairs based on toolUseId.
        
        Note: This version treats all messages equally in terms of token budget, without 
        special handling for context messages (knowledge base or memory context).
        """
        total_tokens = self._count_tokens(messages)
        self.logger.debug(f"Starting message trimming with {len(messages)} messages ({total_tokens} tokens)")
        
        # First pass: Identify and group tool pairs and regular messages
        tool_pairs = {}  # Dictionary to store tool pairs by toolUseId
        regular_messages = []  # List to store non-tool messages in order
        tool_use_positions = {}  # Store positions of toolUse messages
        
        if hasattr(self.app_config.aws, 'debug_trim_messages') and self.app_config.aws.debug_trim_messages:
            self.logger.debug("=== DETAILED TRIM MESSAGES DEBUG ENABLED ===")
            self.logger.debug(f"Initial message count: {len(messages)}")
            for idx, msg in enumerate(messages):
                content_summary = self._summarize_message_content(msg)
                self.logger.debug(f"Message {idx}: role={msg.get('role')}, content={content_summary}")
        
        for idx, msg in enumerate(messages):
            content = msg.get('content', [])
            is_tool_message = False
            
            if content and isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        if 'toolUse' in item:
                            tool_id = item['toolUse']['toolUseId']
                            tool_name = item['toolUse'].get('name', 'unknown')
                            if tool_id not in tool_pairs:
                                tool_pairs[tool_id] = {'use': None, 'result': None, 'position': idx}
                            tool_pairs[tool_id]['use'] = msg
                            tool_use_positions[idx] = tool_id
                            is_tool_message = True
                            
                            if hasattr(self.app_config.aws, 'debug_trim_messages') and self.app_config.aws.debug_trim_messages:
                                self.logger.debug(f"Tool Use detected: id={tool_id}, name={tool_name}, position={idx}")
                            break
                        elif 'toolResult' in item:
                            tool_id = item['toolResult']['toolUseId']
                            if tool_id not in tool_pairs:
                                tool_pairs[tool_id] = {'use': None, 'result': None, 'position': idx}
                            tool_pairs[tool_id]['result'] = msg
                            is_tool_message = True
                            
                            if hasattr(self.app_config.aws, 'debug_trim_messages') and self.app_config.aws.debug_trim_messages:
                                self.logger.debug(f"Tool Result detected: id={tool_id}, position={idx}")
                            break
            
            if not is_tool_message:
                regular_messages.append((idx, msg))
                if hasattr(self.app_config.aws, 'debug_trim_messages') and self.app_config.aws.debug_trim_messages:
                    self.logger.debug(f"Regular message detected: position={idx}, role={msg.get('role')}")

        # Create chronologically ordered list of complete tool pairs and regular messages
        ordered_messages = []
        
        # Add only complete tool pairs (both use and result present)
        valid_tool_pairs = {
            tool_id: pair for tool_id, pair in tool_pairs.items() 
            if pair['use'] is not None and pair['result'] is not None
        }
        
        if hasattr(self.app_config.aws, 'debug_trim_messages') and self.app_config.aws.debug_trim_messages:
            self.logger.debug(f"Tool pairs found: {len(tool_pairs)}, Valid (complete) pairs: {len(valid_tool_pairs)}")
            self.logger.debug(f"Regular messages found: {len(regular_messages)}")
            for tool_id, pair in valid_tool_pairs.items():
                self.logger.debug(f"Valid tool pair: id={tool_id}, position={pair['position']}, has_use={pair['use'] is not None}, has_result={pair['result'] is not None}")
        
        # Combine regular messages and tool pairs while maintaining order
        current_position = 0
        while current_position < len(messages):
            if current_position in tool_use_positions:
                tool_id = tool_use_positions[current_position]
                if tool_id in valid_tool_pairs:
                    pair = valid_tool_pairs[tool_id]
                    ordered_messages.append(pair['use'])
                    ordered_messages.append(pair['result'])
                    
                    if hasattr(self.app_config.aws, 'debug_trim_messages') and self.app_config.aws.debug_trim_messages:
                        self.logger.debug(f"Adding tool pair at position {current_position}: tool_id={tool_id}")
                    
                    current_position += 2  # Skip both toolUse and toolResult
                else:
                    if hasattr(self.app_config.aws, 'debug_trim_messages') and self.app_config.aws.debug_trim_messages:
                        self.logger.debug(f"Skipping incomplete tool use at position {current_position}: tool_id={tool_id}")
                    current_position += 1
            else:
                # Find next regular message at or after current_position
                found = False
                for pos, msg in regular_messages:
                    if pos == current_position:
                        ordered_messages.append(msg)
                        
                        if hasattr(self.app_config.aws, 'debug_trim_messages') and self.app_config.aws.debug_trim_messages:
                            self.logger.debug(f"Adding regular message at position {current_position}: role={msg.get('role')}")
                        
                        found = True
                        break
                if not found:
                    # No regular message at this position
                    if hasattr(self.app_config.aws, 'debug_trim_messages') and self.app_config.aws.debug_trim_messages:
                        self.logger.debug(f"No message at position {current_position}, skipping")
                    pass
                current_position += 1

        # Trim messages until under threshold while preserving pairs
        final_messages = []
        original_message_count = len(ordered_messages)
        
        self.logger.debug(f"Starting message reduction process:")
        self.logger.debug(f"Initial messages: {len(ordered_messages)}")
        self.logger.debug(f"Context threshold: {self.app_config.aws.context_threshold} tokens")
        
        # Make a copy of ordered_messages for iterative trimming
        trimming_messages = ordered_messages.copy()
        removed_messages = []
        
        # Remove messages from the beginning while preserving tool pairs
        while trimming_messages:
            conversation_tokens = self._count_tokens(trimming_messages)
            
            if conversation_tokens <= self.app_config.aws.context_threshold:
                final_messages = trimming_messages
                if hasattr(self.app_config.aws, 'debug_trim_messages') and self.app_config.aws.debug_trim_messages:
                    self.logger.debug(f"Message size under threshold: {conversation_tokens} tokens <= {self.app_config.aws.context_threshold} tokens")
                break
            
            if hasattr(self.app_config.aws, 'debug_trim_messages') and self.app_config.aws.debug_trim_messages:
                self.logger.debug(f"Current message size: {conversation_tokens} tokens > {self.app_config.aws.context_threshold} tokens threshold")
                
            # Remove two messages at a time if they form a tool pair
            if len(trimming_messages) >= 2:
                first_msg = trimming_messages[0]
                second_msg = trimming_messages[1]
                
                is_tool_pair = False
                tool_id = None
                if isinstance(first_msg.get('content', []), list) and isinstance(second_msg.get('content', []), list):
                    first_content = first_msg['content'][0] if first_msg['content'] else {}
                    second_content = second_msg['content'][0] if second_msg['content'] else {}
                    
                    if isinstance(first_content, dict) and isinstance(second_content, dict):
                        if ('toolUse' in first_content and 'toolResult' in second_content):
                            first_tool_id = first_content.get('toolUse', {}).get('toolUseId')
                            second_tool_id = second_content.get('toolResult', {}).get('toolUseId')
                            if first_tool_id == second_tool_id:
                                is_tool_pair = True
                                tool_id = first_tool_id
                
                if is_tool_pair:
                    if hasattr(self.app_config.aws, 'debug_trim_messages') and self.app_config.aws.debug_trim_messages:
                        tool_name = first_content.get('toolUse', {}).get('name', 'unknown')
                        self.logger.debug(f"Removing tool pair: id={tool_id}, name={tool_name}")
                        first_tokens = self._count_tokens([first_msg])
                        second_tokens = self._count_tokens([second_msg])
                        self.logger.debug(f"  - Tool use: {first_tokens} tokens")
                        self.logger.debug(f"  - Tool result: {second_tokens} tokens")
                        self.logger.debug(f"  - Total removed: {first_tokens + second_tokens} tokens")
                    
                    removed_messages.append(first_msg)
                    removed_messages.append(second_msg)
                    trimming_messages = trimming_messages[2:]  # Remove both messages
                else:
                    if hasattr(self.app_config.aws, 'debug_trim_messages') and self.app_config.aws.debug_trim_messages:
                        role = first_msg.get('role', 'unknown')
                        tokens = self._count_tokens([first_msg])
                        content_summary = self._summarize_message_content(first_msg)
                        self.logger.debug(f"Removing single message: role={role}, tokens={tokens}")
                        self.logger.debug(f"  - Content summary: {content_summary}")
                    
                    removed_messages.append(first_msg)
                    trimming_messages = trimming_messages[1:]  # Remove just the first message
            else:
                if hasattr(self.app_config.aws, 'debug_trim_messages') and self.app_config.aws.debug_trim_messages:
                    role = trimming_messages[0].get('role', 'unknown')
                    tokens = self._count_tokens([trimming_messages[0]])
                    content_summary = self._summarize_message_content(trimming_messages[0])
                    self.logger.debug(f"Removing last message: role={role}, tokens={tokens}")
                    self.logger.debug(f"  - Content summary: {content_summary}")
                
                removed_messages.append(trimming_messages[0])
                trimming_messages = trimming_messages[1:]  # Remove the remaining message

        final_total_tokens = self._count_tokens(final_messages)
        self.logger.debug(f"Final trimming results:")
        self.logger.debug(f"Final messages: {len(final_messages)}")
        self.logger.debug(f"Final total tokens: {final_total_tokens}")
        
        if hasattr(self.app_config.aws, 'debug_trim_messages') and self.app_config.aws.debug_trim_messages:
            self.logger.debug(f"Messages removed: {len(removed_messages)}")
            self.logger.debug(f"Original message count: {original_message_count}")
            self.logger.debug(f"Kept message count: {len(final_messages)}")
        
        # Calculate reduction based on original input messages vs final messages
        input_message_count = len(messages)
        reduction_percent = ((input_message_count - len(final_messages)) / input_message_count) * 100 if input_message_count > 0 else 0
        self.logger.debug(f"Message reduction percentage: {reduction_percent:.1f}%\n")
        
        if hasattr(self.app_config.aws, 'debug_trim_messages') and self.app_config.aws.debug_trim_messages:
            # Log detailed statistics about what was kept vs removed
            total_input_tokens = self._count_tokens(messages)
            tokens_removed = total_input_tokens - final_total_tokens
            self.logger.debug(f"Token reduction: {tokens_removed} tokens removed ({(tokens_removed/total_input_tokens*100):.1f}%)")
            
            # Log detailed information about kept messages by role
            role_counts = {}
            role_tokens = {}
            for msg in final_messages:
                role = msg.get('role', 'unknown')
                if role not in role_counts:
                    role_counts[role] = 0
                    role_tokens[role] = 0
                role_counts[role] += 1
                role_tokens[role] += self._count_tokens([msg])
                
            self.logger.debug("=== KEPT MESSAGES BY ROLE ===")
            for role, count in role_counts.items():
                self.logger.debug(f"  - {role}: {count} messages, {role_tokens[role]} tokens")
            
            # Mark end of trimming debug section
            self.logger.debug("=== END OF DETAILED TRIM MESSAGES DEBUG ===")

        return final_messages

    def _build_prompt(self, conversation_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        messages = []
        memory_context = []
        conversation_without_last_exchange = []
        last_exchange_messages = []
        
        # First, normalize all messages to ensure content is always a list
        normalized_history = []
        for message in conversation_history:
            normalized_msg = {"role": message["role"]}
            
            # Ensure content is always in the correct format (list of objects)
            if isinstance(message.get("content"), str):
                normalized_msg["content"] = [{"text": message["content"]}]
            elif isinstance(message.get("content"), list):
                normalized_msg["content"] = message["content"]
            else:
                # Default to empty content if none exists
                normalized_msg["content"] = []
                
            # Copy any other fields
            for key, value in message.items():
                if key not in ["role", "content"]:
                    normalized_msg[key] = value
                    
            normalized_history.append(normalized_msg)
            
        # Find the last two messages that use the 'sequentialthinking' tool
        think_message_indices = []
        for idx, message in enumerate(normalized_history):
            if message["role"] == "assistant" and isinstance(message.get("content"), list):
                for content_item in message.get("content", []):
                    if isinstance(content_item, dict) and "toolUse" in content_item:
                        if content_item["toolUse"].get("name") == "sequentialthinking":
                            think_message_indices.append(idx)
                            break
        
        # Get the last two 'sequentialthinking' tool messages
        last_think_indices = think_message_indices[-2:] if len(think_message_indices) >= 2 else think_message_indices
        
        # Extract the last complete exchange (user + assistant pair if available)
        last_user_idx = None
        for idx, msg in reversed(list(enumerate(normalized_history))):
            if msg["role"] == "user":
                last_user_idx = idx
                break
        
        # Get current query for knowledge base lookup
        current_query = None
        if last_user_idx is not None:
            last_user_msg = normalized_history[last_user_idx]
            content = last_user_msg.get("content", [])
            if content and isinstance(content[0], dict):
                if "text" in content[0]:
                    current_query = content[0]["text"]
                elif "toolResult" in content[0]:
                    tool_result = content[0]["toolResult"]
                    if isinstance(tool_result, dict) and "content" in tool_result:
                        content_list = tool_result["content"]
                        if isinstance(content_list, list) and len(content_list) > 0:
                            first_content = content_list[0]
                            if isinstance(first_content, dict) and "text" in first_content:
                                current_query = first_content["text"]
        
        # Find the last exchange (user + optional assistant response)
        # We'll capture either just the user message or the user + assistant pair
        if last_user_idx is not None:
            # Always include the last user message
            last_exchange_messages.append(normalized_history[last_user_idx])
            
            # If there's an assistant response after the user message, include it too
            if last_user_idx + 1 < len(normalized_history) and normalized_history[last_user_idx + 1]["role"] == "assistant":
                last_exchange_messages.append(normalized_history[last_user_idx + 1])
        
        # Process the conversation history
        for idx, message in enumerate(normalized_history):
            # Skip messages that are part of the last exchange
            if message in last_exchange_messages:
                continue
                
            if message.get("from_memory", False):
                cleaned_message = {
                    "role": message["role"],
                    "content": []
                }
                
                for content_item in message.get("content", []):
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
                if message["role"] == "user" and isinstance(message.get("content"), list) and len(message["content"]) == 1:
                    content_item = message["content"][0]
                    if isinstance(content_item, dict) and "text" in content_item:
                        text_content = content_item["text"]
                        if "toolResult" in text_content:
                            try:
                                tool_results = json.loads(text_content)
                                if isinstance(tool_results, list) and len(tool_results) > 0:
                                    tool_result = tool_results[0].get("toolResult", {})
                                    conversation_without_last_exchange.append({
                                        "role": message["role"],
                                        "content": [{
                                            "toolResult": tool_result
                                        }]
                                    })
                                    continue
                            except json.JSONDecodeError:
                                pass
                
                conversation_without_last_exchange.append(message)
        
        # New order as requested:
        # 1) Conversation history (excluding the last exchange)
        messages.extend(conversation_without_last_exchange)
        
        # 2) Knowledge base context
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
        
        # 3) Memory context
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
        
        # 4) Last exchange - ensure we end with a user message
        if last_exchange_messages:
            # If we have both user and assistant in the last exchange
            if len(last_exchange_messages) == 2:
                # Check if the last one is assistant
                if last_exchange_messages[1]["role"] == "assistant":
                    # Add both in order but only if the user message comes last
                    messages.append(last_exchange_messages[0])  # User message
                    
                    # Only add the assistant message if there's another user message after it
                    # that will be processed in the current conversation
                    has_user_after = False
                    for msg in normalized_history:
                        if msg not in last_exchange_messages and msg["role"] == "user":
                            has_user_after = True
                            break
                    
                    if has_user_after:
                        messages.append(last_exchange_messages[1])  # Assistant message
                else:
                    # Just add the messages in order
                    messages.extend(last_exchange_messages)
            else:
                # Just one message (presumably user)
                messages.extend(last_exchange_messages)
        
        # Ensure we don't end with an assistant message
        if messages and messages[-1]["role"] == "assistant":
            # Check conversation history for a user message to append
            for msg in reversed(normalized_history):
                if msg["role"] == "user" and msg not in messages:
                    messages.append(msg)
                    break
            
            # If we couldn't find one, we need to ensure we don't end with an assistant message
            if messages[-1]["role"] == "assistant":
                # Remove the last assistant message
                messages.pop()
        
        # Apply context trimming to ensure we're under the token limit
        messages = self._trim_messages(messages)
        
        # Final validation check - ensure we don't end with an assistant message
        if messages and messages[-1]["role"] == "assistant":
            messages.pop()
        
        # Final validation pass: ensure all messages have content as a list
        validated_messages = []
        for message in messages:
            validated_msg = {"role": message["role"]}
            
            if not isinstance(message.get("content"), list):
                self.logger.warning(f"Found message with invalid content format: {message.get('content')}")
                validated_msg["content"] = [{"text": str(message.get("content", ""))}]
            else:
                validated_msg["content"] = message["content"]
                
            # Copy any other fields
            for key, value in message.items():
                if key not in ["role", "content"]:
                    validated_msg[key] = value
                    
            validated_messages.append(validated_msg)
        
        # First, remove any existing cachePoint elements from all messages
        for message in validated_messages:
            if "content" in message:
                # Filter out any cachePoint items
                message["content"] = [
                    item for item in message["content"] 
                    if not (isinstance(item, dict) and "cachePoint" in item)
                ]
                
        # Find the two most recent assistant messages that use the 'sequentialthinking' tool
        think_messages = []
        for val_idx, val_msg in enumerate(validated_messages):
            if val_msg["role"] == "assistant" and "content" in val_msg:
                has_think_tool = False
                for content_item in val_msg.get("content", []):
                    if isinstance(content_item, dict) and "toolUse" in content_item:
                        if content_item["toolUse"].get("name") == "sequentialthinking":
                            has_think_tool = True
                            break
                
                if has_think_tool:
                    think_messages.append((val_idx, val_msg))
        
        # Get the last two 'sequentialthinking' tool messages
        last_two_think_messages = think_messages[-2:] if len(think_messages) >= 2 else think_messages
        
        # Add cachePoint to only these messages
        for val_idx, _ in last_two_think_messages:
            # Add cachePoint to the content list (exactly once)
            validated_messages[val_idx]["content"].append({
                "cachePoint": {
                    "type": "default"
                }
            })
            self.logger.debug(f"Added cachePoint to sequentialthinking tool message at index {val_idx}")
        
        return validated_messages

    def _invoke_model(self, messages: List[Dict[str, Any]], tool_config: Dict[str, Any], bedrock_client) -> Dict[str, Any]:
        model_id = self.app_config.aws.model_id_smart if self.smart_mode else self.app_config.aws.model_id
        max_retries = 3
        retry_delay = 2
        cache_metrics = {"read": 0, "write": 0}
        
        for attempt in range(max_retries):
            try:
                max_tokens = self.app_config.aws.max_tokens
                
                inference_config = {
                    "temperature": 0.1,
                    "maxTokens": max_tokens
                }

                current_date = datetime.datetime.now().strftime("%Y-%m-%d")
                system_prompt = f"""Purpose: General-purpose AI assistant with expertise in technology. Current date: {current_date}

You must follow these guidelines:

FORMATTING
Use Markdown formatting for ALL responses:
- Headers (#, ##, ###) for organization
- **Bold** for emphasis, _italic_ for technical terms, `code` for commands
- Bullet points (-) and numbered lists (1., 2., 3.)
- Tables with Markdown syntax for structured data
- Blockquotes (>) for important notes, --- for section breaks
- NO emojis, HTML, or plain text without formatting

ANALYSIS & OUTPUT
- Label analysis sections clearly with concise bullet points
- Keep technical output clean, organized, and well-spaced
- Maintain strict read-only access to services
- Follow AWS and Kubernetes best practices

SERPER TOOL USAGE
Use the 'serper' tool proactively to verify information, find documentation, or research solutions. Always include a "## Sources" section with categorized links when using serper.

FETCH TOOL USAGE
Do not use the fetch tool for Git repositories. Use dedicated Git tools instead

PYTHON_EXEC TOOL USAGE
- Runs in secure sandbox with limited modules only
- NO subprocess, file system, or network access beyond allowed modules
- Limit debugging to 3 attempts, then change approach
- Break complex operations into smaller, testable parts

THINK TOOL USAGE
Use sequentialthinking for complex tasks requiring analysis, planning, or multiple steps. Skip for simple greetings, basic questions, or straightforward requests.

MEMORY TOOL USAGE
- Assume interaction with default_user
- Always refer to your knowledge graph as your "memory"
- Check memory for names, entities, organizations, or relationships
- Observe and update memory for: identity, behaviors, preferences, goals, relationships, organizations, projects, technical topics
- Create entities and connect them with relations

TONE
Maintain friendly, professional, and helpful tone. Focus on clarity and accuracy."""

                debug_payload = {
                    "messages": messages,
                    "system": [{"text": system_prompt}, {"cachePoint": {"type": "default"}}],
                    "inferenceConfig": inference_config,
                    "toolConfig": tool_config
                }
                self.logger.debug(f"Bedrock Request:\n{json.dumps(debug_payload, indent=2)}\n")

                try:
                    response = bedrock_client.converse(
                        modelId=model_id,
                        messages=messages,
                        system=[
                            {"text": system_prompt},
                            {"cachePoint": {"type": "default"}}
                        ],
                        inferenceConfig=inference_config,
                        toolConfig=tool_config
                    )

                    for content in response['output']['message']['content']:
                        if 'text' in content:
                            self.logger.info(content['text'])

                    # Extract usage and metrics information
                    usage_metrics = {}
                    if 'usage' in response:
                        usage_metrics = response['usage']
                        
                        # Cache metrics are in the usage object
                        if 'cacheReadInputTokens' in usage_metrics:
                            cache_metrics["read"] = usage_metrics['cacheReadInputTokens']
                        if 'cacheWriteInputTokens' in usage_metrics:
                            cache_metrics["write"] = usage_metrics['cacheWriteInputTokens']
                    
                    # Extract latency information
                    latency_ms = None
                    if 'metrics' in response and 'latencyMs' in response['metrics']:
                        latency_ms = response['metrics']['latencyMs']

                    return {
                        "output": {
                            "message": response['output']['message']
                        },
                        "stopReason": response['stopReason'],
                        "usage": usage_metrics,
                        "latencyMs": latency_ms
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
                    self.logger.info(f"└── {tool['name']} {self._get_tool_parameter(tool)}")

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

    async def _process_tool_use(self, output_message: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process tool use with MCP execution."""
        tool_results = []
        try:
            for content in output_message['content']:
                if 'toolUse' in content:
                    tool = content['toolUse']
                    
                    # Execute tool using MCP
                    result = await self._execute_tool(tool)

                    # Get the appropriate parameter for logging
                    param_value = self._get_tool_parameter(tool)
                    
                    # Improved display with separator and colors
                    tool_name = f"{self.app_config.colors.blue}{tool['name']}{self.app_config.colors.reset}"
                    if param_value:
                        self.logger.info(f"└─ {tool_name}")
                        # Indent the JSON parameters for better readability
                        indented_params = "\n".join(f"   {line}" for line in param_value.split('\n'))
                        self.logger.info(indented_params)
                    else:
                        self.logger.info(f"└─ {tool_name}")
                    
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
    
    async def cleanup(self):
        """Clean up resources, especially MCP connections."""
        try:
            await close_mcp_executor()
        except Exception as e:
            self.logger.error(f"Error cleaning up MCP resources: {e}")

    def _get_tool_parameter(self, tool: Dict[str, Any]) -> str:
        """Extract all parameters from a tool in JSON format.
        
        Args:
            tool: The tool dictionary containing name and input parameters
            
        Returns:
            str: A JSON string representation of all input parameters
        """
        tool_input = tool.get('input', {})
        
        if not tool_input:
            return ""
        
        # Return parameters in JSON format (compact)
        return json.dumps(tool_input, ensure_ascii=False, indent=1)
