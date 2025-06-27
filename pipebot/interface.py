import sys
import os
from typing import Optional, List, Dict, Union, Any, AsyncGenerator
from dataclasses import dataclass
import json
import base64
import boto3
import re
import asyncio
from pipebot.cli import CLIParser
from pipebot.ai.assistant import AIAssistant
from backend.logging_config import StructuredLogger, correlation_id
from backend.session_manager import SessionManager
import logging
from pipebot.config import AppConfig

@dataclass
class MessageContent:
    """Data class to represent message content in a structured way."""
    text: Optional[str] = None
    image: Optional[Dict[str, Any]] = None
    tool_use: Optional[Dict[str, Any]] = None
    tool_result: Optional[Dict[str, Any]] = None

class MessageFormatter:
    """Helper class to format messages for different contexts."""
    
    @staticmethod
    def format_for_frontend(message: Dict[str, Any]) -> Dict[str, Any]:
        """Format a message for frontend display."""
        interaction = {
            "role": message["role"],
            "content": []
        }
        
        if isinstance(message["content"], list):
            for item in message["content"]:
                if isinstance(item, dict):
                    if "text" in item:
                        # Replace only single backticks, avoiding code blocks
                        text = re.sub(r'(?<!`)`(?!`)', '**', item["text"])
                        interaction["content"].append({
                            "type": "text",
                            "content": text
                        })
                    elif "image" in item:
                        image_data = item["image"]
                        interaction["content"].append({
                            "type": "image",
                            "format": image_data.get("format", "png")
                        })
                    elif "toolUse" in item:
                        tool_use = item["toolUse"]
                        command = tool_use.get("input", {}).get("command", "")
                        if tool_use.get("name") == "think":
                            interaction["content"].append({
                                "type": "toolUse",
                                "toolId": tool_use.get("toolUseId", ""),
                                "tool": tool_use.get("name", ""),
                                "command": ""
                            })
                        else:
                            if tool_use.get("name") == "python_exec":
                                # Pour python_exec, ne pas afficher le script généré
                                command = ""
                            interaction["content"].append({
                                "type": "toolUse",
                                "toolId": tool_use.get("toolUseId", ""),
                                "tool": tool_use.get("name", ""),
                                "command": command
                            })
                    elif "toolResult" in item:
                        tool_result = item["toolResult"]
                        content = tool_result.get("content", [])
                        if not isinstance(content, list):
                            content = [{"text": str(content)}]
                        interaction["content"].append({
                            "type": "toolResult",
                            "toolId": tool_result.get("toolUseId", ""),
                            "content": content
                        })
        
        return interaction

class PipebotInterface:
    """Main interface for the Pipebot application.
    
    This class handles the communication between the CLI, AI assistant, and AWS Bedrock.
    It manages conversation history and processes both text and image inputs.
    """
    
    # Default configuration for the assistant
    DEFAULT_DEBUG = False
    DEFAULT_USE_MEMORY = True
    DEFAULT_SMART_MODE = False
    
    def __init__(self, app_config: AppConfig, session_manager: Optional[SessionManager] = None):
        """Initialize the PipebotInterface.
        
        Args:
            app_config: The application configuration
            session_manager: Optional SessionManager instance. If None, a new one will be created.
        """
        self.app_config = app_config
        self.cli = CLIParser()
        self.logger = StructuredLogger("Interface")
        self.assistant = None  # Initialize as None, will be created when needed
        self.bedrock_client = self._initialize_bedrock_client()
        self.session_manager = session_manager or SessionManager()
        self._correlation_id = None
        
    def _initialize_bedrock_client(self) -> boto3.client:
        """Initialize the AWS Bedrock client.
        
        Returns:
            boto3.client: Initialized Bedrock client
        """
        try:
            return boto3.client(
                service_name='bedrock-runtime',
                region_name='us-west-2'
            )
        except Exception as e:
            self.logger.error(f"Failed to initialize Bedrock client: {str(e)}")
            raise
        
    async def _process_image(self, image_bytes: bytes, image_type: str, text: Optional[str] = None) -> str:
        """Process an image request using the Bedrock API.
        
        Args:
            image_bytes: The image data in bytes
            image_type: The MIME type of the image
            text: Optional text instruction from the user
            
        Returns:
            str: The model's response describing the image
            
        Raises:
            Exception: If there's an error processing the image
        """
        try:
            # Créer le message avec l'instruction personnalisée ou générique
            instruction = text.strip()
            self.logger.debug(f"Processing image with instruction: '{instruction}'")
            
            message = {
                "role": "user",
                "content": [
                    {"text": instruction},
                    {
                        "image": {
                            "format": image_type.split('/')[-1],
                            "source": {"bytes": image_bytes}
                        }
                    }
                ]
            }
            
            response = self.bedrock_client.converse_stream(
                modelId="anthropic.claude-3-5-sonnet-20241022-v2:0",
                messages=[message]
            )
            
            text = ""
            for chunk in response['stream']:
                if 'contentBlockDelta' in chunk:
                    delta = chunk['contentBlockDelta']['delta']
                    if 'text' in delta:
                        text += delta['text']
            
            return text
            
        except Exception as e:
            self.logger.error(f"Error processing image: {str(e)}")
            raise
    
    def _create_user_message(self, text: Optional[str] = None, 
                           image_bytes: Optional[bytes] = None, 
                           image_type: Optional[str] = None) -> Dict[str, Any]:
        """Create a user message with optional text and image content.
        
        Args:
            text: Optional text content
            image_bytes: Optional image data
            image_type: Optional image MIME type
            
        Returns:
            Dict[str, Any]: Formatted user message
        """
        message_content = []
        
        if text and text.strip():
            message_content.append({"text": text})
            
        if image_bytes:
            message_content.append({
                "image": {
                    "format": image_type.split('/')[-1] if image_type else "png",
                    "source": {"bytes": image_bytes}
                }
            })
        
        return {
            "role": "user",
            "content": message_content
        }
    
    async def process_input(self, text: str, 
                          image_bytes: Optional[bytes] = None, 
                          image_type: Optional[str] = None,
                          session_id: Optional[str] = None,
                          smart_mode: bool = False) -> str:
        """Process user input, handling both text and image content.
        
        Args:
            text: The text input from the user
            image_bytes: Optional image data
            image_type: Optional image MIME type
            session_id: The session ID for the current user
            smart_mode: Whether to use smart mode for processing
            
        Returns:
            str: JSON string containing the formatted conversation response
            
        Raises:
            Exception: If there's an error processing the input
        """
        if not text.strip() and not image_bytes:
            return ""
        
        try:
            self.logger.debug(f"Interface processing input - Text: '{text}', Has image: {image_bytes is not None}, Smart Mode: {smart_mode}")
            user_message = self._create_user_message(text, image_bytes, image_type)
            
            if image_bytes:
                return await self._handle_image_input(user_message, image_bytes, image_type, session_id)
            else:
                return await self._handle_text_input(user_message, session_id, smart_mode)
                
        except Exception as e:
            self.logger.error(f"Error processing input: {str(e)}")
            return json.dumps({
                "type": "error",
                "message": f"Error processing input: {str(e)}"
            })
    
    async def process_input_stream(self, text: str, 
                                 image_bytes: Optional[bytes] = None, 
                                 image_type: Optional[str] = None,
                                 session_id: Optional[str] = None,
                                 smart_mode: bool = False) -> AsyncGenerator[Dict[str, Any], None]:
        """Process user input with streaming updates, handling both text and image content.
        
        Args:
            text: The text input from the user
            image_bytes: Optional image data
            image_type: Optional image MIME type
            session_id: The session ID for the current user
            smart_mode: Whether to use smart mode for processing
            
        Yields:
            Dict[str, Any]: Streaming updates during processing
        """
        if not text.strip() and not image_bytes:
            yield {"type": "error", "message": "Empty input"}
            return
        
        try:
            self.logger.debug(f"Interface processing input stream - Text: '{text}', Has image: {image_bytes is not None}, Smart Mode: {smart_mode}")
            user_message = self._create_user_message(text, image_bytes, image_type)
            
            if image_bytes:
                async for update in self._handle_image_input_stream(user_message, image_bytes, image_type, session_id):
                    yield update
            else:
                async for update in self._handle_text_input_stream(user_message, session_id, smart_mode):
                    yield update
                    
        except Exception as e:
            self.logger.error(f"Error processing input stream: {str(e)}")
            yield {"type": "error", "message": f"Error processing input: {str(e)}"}
    
    async def _handle_image_input_stream(self, user_message: Dict[str, Any], 
                                       image_bytes: bytes, 
                                       image_type: str,
                                       session_id: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Handle image input processing with streaming updates."""
        yield {"type": "status", "message": "Processing image..."}
        
        # Extract text from user message if it exists
        user_text = None
        if user_message["content"] and len(user_message["content"]) > 0:
            text_content = next((item for item in user_message["content"] if "text" in item), None)
            if text_content:
                user_text = text_content["text"]
                
        response_text = await self._process_image(image_bytes, image_type, user_text)
        
        assistant_response = {
            "role": "assistant",
            "content": [{"text": response_text}]
        }
        
        # Create simplified user message for history
        simplified_user_message = {
            "role": "user",
            "content": [{"text": f"[Image submitted: {image_type}]"}]
        }
        
        # Add to session history
        self.session_manager.add_to_conversation_history(session_id, simplified_user_message)
        self.session_manager.add_to_conversation_history(session_id, assistant_response)
        
        # Format for frontend
        formatted_interactions = [
            MessageFormatter.format_for_frontend(assistant_response)
        ]
        
        yield {
            "type": "conversation",
            "messages": formatted_interactions
        }
    
    async def _handle_text_input_stream(self, user_message: Dict[str, Any], 
                                      session_id: str, 
                                      smart_mode: bool = False) -> AsyncGenerator[Dict[str, Any], None]:
        """Handle text input processing with streaming updates."""
        # Add user message to session history
        self.session_manager.add_to_conversation_history(session_id, user_message)
        
        # Get complete conversation history
        conversation_history = self.session_manager.get_conversation_history(session_id)
        
        # Initialize or update assistant with current smart mode
        self.assistant = self._initialize_assistant(smart_mode=smart_mode)
        
        # Status message removed for cleaner output
        
        try:
            # Generate response with streaming
            async for update in self.assistant.generate_response_stream(conversation_history):
                yield update
            
            # Get the updated conversation history with new interactions
            updated_history = self.assistant.get_current_conversation()
            
            # Extract new interactions since the last user message
            new_interactions = self._get_new_interactions(updated_history)
            
            if not new_interactions:
                yield {"type": "error", "message": "No response generated"}
                return
            
            # Add new interactions to session history
            for interaction in new_interactions:
                self.session_manager.add_to_conversation_history(session_id, interaction)
            
            # Format interactions for frontend
            formatted_interactions = [
                MessageFormatter.format_for_frontend(message)
                for message in new_interactions
            ]
            
            yield {
                "type": "conversation",
                "messages": formatted_interactions
            }
        except Exception as e:
            self.logger.error(f"Error in text input stream: {str(e)}")
            yield {"type": "error", "message": f"Error generating response: {str(e)}"}
    
    async def _handle_image_input(self, user_message: Dict[str, Any], 
                                image_bytes: bytes, 
                                image_type: str,
                                session_id: str) -> str:
        """Handle image input processing.
        
        Args:
            user_message: The user message containing the image
            image_bytes: The image data
            image_type: The image MIME type
            session_id: The session ID for the current user
            
        Returns:
            str: JSON string containing the formatted conversation response
        """
        # Extraire le texte du message utilisateur s'il existe
        user_text = None
        if user_message["content"] and len(user_message["content"]) > 0:
            text_content = next((item for item in user_message["content"] if "text" in item), None)
            if text_content:
                user_text = text_content["text"]
                
        response_text = await self._process_image(image_bytes, image_type, user_text)
        
        assistant_response = {
            "role": "assistant",
            "content": [{"text": response_text}]
        }
        
        # Créer un message utilisateur simplifié pour l'historique interne
        simplified_user_message = {
            "role": "user",
            "content": [{"text": f"[Image submitted: {image_type}]"}]
        }
        
        # Ajouter à l'historique de la session
        self.session_manager.add_to_conversation_history(session_id, simplified_user_message)
        self.session_manager.add_to_conversation_history(session_id, assistant_response)
        
        # Ne renvoyer que la réponse de l'assistant au frontend
        formatted_interactions = [
            MessageFormatter.format_for_frontend(assistant_response)
        ]
        
        return json.dumps({
            "type": "conversation",
            "messages": formatted_interactions
        })
    
    async def _handle_text_input(self, user_message: Dict[str, Any], session_id: str, smart_mode: bool = False) -> str:
        """Handle text input processing.
        
        Args:
            user_message: The user message containing the text
            session_id: The session ID for the current user
            smart_mode: Whether to use smart mode for processing
            
        Returns:
            str: JSON string containing the formatted conversation response
        """
        # Ajouter le message utilisateur à l'historique de la session
        self.session_manager.add_to_conversation_history(session_id, user_message)
        
        # Récupérer l'historique complet de la session
        conversation_history = self.session_manager.get_conversation_history(session_id)
        
        # Initialize or update assistant with current smart mode
        self.assistant = self._initialize_assistant(smart_mode=smart_mode)
        
        # Generate response
        conversation_history = self.assistant.generate_response(conversation_history)
        
        # Extraire les nouvelles interactions depuis le dernier message utilisateur
        new_interactions = self._get_new_interactions(conversation_history)
        
        if not new_interactions:
            return json.dumps({
                "type": "error",
                "message": "No response generated"
            })
        
        # Ajouter les nouvelles interactions à l'historique de la session
        for interaction in new_interactions:
            self.session_manager.add_to_conversation_history(session_id, interaction)
        
        # Format interactions for frontend
        formatted_interactions = [
            MessageFormatter.format_for_frontend(message)
            for message in new_interactions
        ]
        
        return json.dumps({
            "type": "conversation",
            "messages": formatted_interactions
        })
    
    def _get_new_interactions(self, conversation_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Get new interactions since the last user message.
        
        Args:
            conversation_history: The complete conversation history
            
        Returns:
            List[Dict[str, Any]]: List of new interactions
        """
        last_user_index = -1
        
        # Find the last user message that is not a tool result
        for i in range(len(conversation_history) - 1, -1, -1):
            message = conversation_history[i]
            if message["role"] == "user":
                content = message.get("content", [])
                if not (isinstance(content, list) and len(content) == 1 and 
                       isinstance(content[0], dict) and "toolResult" in content[0]):
                    last_user_index = i
                    break
        
        if last_user_index >= 0:
            return conversation_history[last_user_index + 1:]
        
        return []

    def _set_correlation_id(self):
        """Set the correlation ID for the current operation if one exists."""
        current_id = correlation_id.get()
        if current_id and current_id != self._correlation_id:
            self._correlation_id = current_id
            self.logger.set_correlation_id(current_id)

    def clear_conversation_history(self, session_id: str) -> None:
        """Clear the conversation history for a session."""
        self._set_correlation_id()
        # Clear the conversation history while preserving the session
        self.session_manager.clear_conversation_history(session_id)
        # Reset the assistant for this session
        self.assistant = None

    def _initialize_assistant(self, smart_mode: bool = DEFAULT_SMART_MODE) -> AIAssistant:
        """Initialize the AI assistant with the current configuration.
        
        Args:
            smart_mode: Whether to use smart mode for processing
            
        Returns:
            AIAssistant: The initialized assistant
        """
        return AIAssistant(
            self.app_config,
            use_memory=self.DEFAULT_USE_MEMORY,
            smart_mode=smart_mode
        )
