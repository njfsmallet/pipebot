import asyncio
import json
import os
from typing import Any, Dict, Optional, List
from pipebot.config import AppConfig, MCPServerConfig
from pipebot.logging_config import StructuredLogger
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MultiMCPServerClient:
    """Multi-MCP Client for interacting with multiple MCP servers."""
    
    def __init__(self, mcp_config):
        self.mcp_config = mcp_config
        self.logger = StructuredLogger("MultiMCPServerClient")
    
    def _get_server_params(self, server_name: str) -> StdioServerParameters:
        """Get server parameters for a specific MCP server."""
        if server_name not in self.mcp_config.mcp_servers:
            raise ValueError(f"Unknown MCP server: {server_name}")
        
        server_config = self.mcp_config.mcp_servers[server_name]
        
        # Use current environment variables and add custom ones if specified
        env = dict(os.environ)
        if server_config.env:
            env.update(server_config.env)
            
        return StdioServerParameters(
            command=server_config.command,
            args=server_config.args,
            env=env
        )
    
    async def _create_temporary_session(self, server_name: str):
        """Create a temporary session for a specific MCP server."""
        try:
            server_params = self._get_server_params(server_name)
            stdio_connection = stdio_client(server_params)
            read, write = await stdio_connection.__aenter__()
            session = ClientSession(read, write)
            await session.__aenter__()
            await session.initialize()
            self.logger.debug(f"Temporary MCP session created for server: {server_name}")
            return session, stdio_connection
        except Exception as e:
            self.logger.error(f"Failed to create MCP session for {server_name}: {e}")
            raise
    
    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool on a specific MCP server."""
        session = None
        stdio_connection = None
        try:
            session, stdio_connection = await self._create_temporary_session(server_name)
            result = await session.call_tool(tool_name, arguments)
            
            # Convert MCP result to ToolExecutor format
            if result.content and len(result.content) > 0:
                text_content = result.content[0].text
                return {"output": text_content}
            else:
                return {"output": "No output from tool"}
                
        except Exception as e:
            self.logger.error(f"Error calling tool {tool_name} on server {server_name}: {e}")
            return {"error": f"Error executing {tool_name} on {server_name}: {str(e)}"}
        finally:
            # Always clean up the session
            if session:
                try:
                    await session.__aexit__(None, None, None)
                except Exception as e:
                    self.logger.debug(f"Error closing session for {server_name}: {e}")
            if stdio_connection:
                try:
                    await stdio_connection.__aexit__(None, None, None)
                except Exception as e:
                    self.logger.debug(f"Error closing stdio connection for {server_name}: {e}")
    
    async def list_tools(self, server_name: str) -> Dict[str, Any]:
        """List available tools from a specific MCP server."""
        session = None
        stdio_connection = None
        try:
            session, stdio_connection = await self._create_temporary_session(server_name)
            tools_response = await session.list_tools()
            return {"output": tools_response.tools}
        except Exception as e:
            self.logger.error(f"Error listing tools from server {server_name}: {e}")
            return {"error": f"Error listing tools from {server_name}: {str(e)}"}
        finally:
            # Always clean up the session
            if session:
                try:
                    await session.__aexit__(None, None, None)
                except Exception as e:
                    self.logger.debug(f"Error closing session for {server_name}: {e}")
            if stdio_connection:
                try:
                    await stdio_connection.__aexit__(None, None, None)
                except Exception as e:
                    self.logger.debug(f"Error closing stdio connection for {server_name}: {e}")
    
    async def close(self):
        """Close MCP client (no persistent sessions to close)."""
        self.logger.debug("Multi-MCP client closed (no persistent sessions)")


class MCPToolExecutor:
    """Dynamic tool executor that discovers and routes tools from multiple MCP servers."""
    
    def __init__(self, app_config: AppConfig):
        self.app_config = app_config
        self.logger = StructuredLogger("MCPToolExecutor")
        self._client = None
        self._client_lock = asyncio.Lock()
        
        # Dynamic tool discovery and routing
        self._tool_routing: Dict[str, str] = {}  # tool_name -> server_name
        self._tool_info: Dict[str, Dict] = {}    # tool_name -> tool_info
        self._discovery_complete = False
        self._discovery_lock = asyncio.Lock()
        
        # Custom routing rules from config (optional)
        self._custom_routing = getattr(self.app_config.mcp, 'tool_routing', {})
    
    async def _get_client(self) -> MultiMCPServerClient:
        """Get or create MCP client with proper locking."""
        if self._client is None:
            async with self._client_lock:
                if self._client is None:
                    try:
                        self._client = MultiMCPServerClient(self.app_config.mcp)
                        self.logger.debug("Multi-MCP client created successfully")
                    except Exception as e:
                        self.logger.error(f"Failed to create Multi-MCP client: {e}")
                        raise
        return self._client
    
    async def _discover_tools(self):
        """Discover all available tools from all MCP servers."""
        if self._discovery_complete:
            return
            
        async with self._discovery_lock:
            if self._discovery_complete:  # Double-check after acquiring lock
                return
                
            try:
                client = await self._get_client()
                
                # Discover tools from each server
                for server_name in self.app_config.mcp.mcp_servers.keys():
                    try:
                        result = await client.list_tools(server_name)
                        if "output" in result and result["output"]:
                            for tool in result["output"]:
                                tool_name = tool.name
                                self._tool_routing[tool_name] = server_name
                                self._tool_info[tool_name] = {
                                    "name": tool.name,
                                    "description": tool.description,
                                    "inputSchema": tool.inputSchema,
                                    "server": server_name
                                }
                                self.logger.debug(f"Discovered tool '{tool_name}' on server '{server_name}'")
                        else:
                            self.logger.warning(f"No tools found on server '{server_name}' or error occurred")
                    except Exception as e:
                        self.logger.error(f"Failed to discover tools from server '{server_name}': {e}")
                
                # Apply custom routing rules (override discovered routing)
                for tool_name, server_name in self._custom_routing.items():
                    if server_name in self.app_config.mcp.mcp_servers:
                        self._tool_routing[tool_name] = server_name
                        self.logger.info(f"Applied custom routing: '{tool_name}' -> '{server_name}'")
                    else:
                        self.logger.warning(f"Custom routing for '{tool_name}' -> '{server_name}' ignored: server not found")
                
                self._discovery_complete = True
                self.logger.debug(f"Tool discovery complete. Found {len(self._tool_routing)} tools across {len(self.app_config.mcp.mcp_servers)} servers")
                
            except Exception as e:
                self.logger.error(f"Failed to discover tools: {e}")
                raise
    
    def _get_server_for_tool(self, tool_name: str) -> Optional[str]:
        """Get the server that should handle a specific tool."""
        return self._tool_routing.get(tool_name)
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call any tool by name with the given arguments."""
        try:
            # Ensure tools are discovered
            await self._discover_tools()
            
            # Find the server for this tool
            server_name = self._get_server_for_tool(tool_name)
            if not server_name:
                return {"error": f"Tool '{tool_name}' not found on any server"}
            
            # Call the tool
            client = await self._get_client()
            return await client.call_tool(server_name, tool_name, arguments)
                
        except Exception as e:
            self.logger.error(f"Error calling tool '{tool_name}': {e}")
            return {"error": f"Error executing '{tool_name}': {str(e)}"}
    
    async def list_available_tools(self) -> Dict[str, Any]:
        """Get a list of all available tools with their information."""
        try:
            await self._discover_tools()
            return {
                "tools": self._tool_info,
                "routing": self._tool_routing,
                "total_tools": len(self._tool_info)
            }
        except Exception as e:
            self.logger.error(f"Error listing available tools: {e}")
            return {"error": f"Error listing tools: {str(e)}"}
    
    async def get_tool_info(self, tool_name: str) -> Dict[str, Any]:
        """Get detailed information about a specific tool."""
        try:
            await self._discover_tools()
            if tool_name in self._tool_info:
                return {
                    "tool": self._tool_info[tool_name],
                    "server": self._tool_routing.get(tool_name)
                }
            else:
                return {"error": f"Tool '{tool_name}' not found"}
        except Exception as e:
            self.logger.error(f"Error getting tool info for '{tool_name}': {e}")
            return {"error": f"Error getting tool info: {str(e)}"}
    
    async def refresh_tools(self):
        """Refresh the tool discovery (useful if servers are restarted)."""
        async with self._discovery_lock:
            self._tool_routing.clear()
            self._tool_info.clear()
            self._discovery_complete = False
            await self._discover_tools()
    
    async def close(self):
        """Close MCP client connection."""
        if self._client:
            try:
                await self._client.close()
                self._client = None
                self.logger.debug("Multi-MCP client disconnected")
            except Exception as e:
                self.logger.error(f"Error closing Multi-MCP client: {e}")

# Global instance for easy access
_mcp_executor = None

async def get_mcp_executor(app_config: AppConfig) -> MCPToolExecutor:
    """Get global MCP executor instance."""
    global _mcp_executor
    if _mcp_executor is None:
        _mcp_executor = MCPToolExecutor(app_config)
    return _mcp_executor

async def close_mcp_executor():
    """Close global MCP executor instance."""
    global _mcp_executor
    if _mcp_executor:
        await _mcp_executor.close()
        _mcp_executor = None 