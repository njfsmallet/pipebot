from dataclasses import dataclass
import os
import json
from typing import Dict, List, Optional
from colored import attr, fg

@dataclass(frozen=True)
class AWSConfig:
    region_name: str = 'us-east-2'
    model_id: str = os.getenv('PIPEBOT_MODEL_ID', "us.anthropic.claude-3-5-haiku-20241022-v1:0")
    model_id_smart: str = os.getenv('PIPEBOT_MODEL_ID_SMART', "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
    max_tokens: int = 8192
    max_context_tokens: int = 200000
    context_threshold_ratio: float = 0.6
    max_context_tokens_kb_memory: int = 32000
    embedding_model: str = "amazon.titan-embed-text-v2:0"
    embedding_dimension: int = 1024
    debug_trim_messages: bool = True

    @property
    def context_threshold(self) -> int:
        """Returns the token threshold at which we should start rolling conversation messages."""
        return int(self.max_context_tokens * self.context_threshold_ratio)

@dataclass(frozen=True)
class MCPServerConfig:
    command: str
    args: List[str]
    env: Optional[Dict[str, str]] = None

@dataclass(frozen=True)
class MCPConfig:
    mcp_servers: Dict[str, MCPServerConfig]
    config_path: str = os.path.expanduser("~/.pipebot/mcp.json")
    
    @classmethod
    def load_from_file(cls, config_path: Optional[str] = None) -> 'MCPConfig':
        """Load MCP configuration from JSON file."""
        if config_path is None:
            config_path = os.path.expanduser("~/.pipebot/mcp.json")
        
        if not os.path.exists(config_path):
            # Return default configuration with only pipebot server
            return cls(mcp_servers={
                "pipebot": MCPServerConfig(
                    command="python",
                    args=["/app/pipebot/mcp_server.py"]
                )
            })
        
        try:
            with open(config_path, 'r') as f:
                data = json.load(f)
            
            mcp_servers = {}
            for server_name, server_config in data.get("mcpServers", {}).items():
                mcp_servers[server_name] = MCPServerConfig(
                    command=server_config["command"],
                    args=server_config.get("args", []),
                    env=server_config.get("env")
                )
            
            return cls(mcp_servers=mcp_servers, config_path=config_path)
        except Exception as e:
            # Fallback to default configuration
            return cls(mcp_servers={
                "pipebot": MCPServerConfig(
                    command="python",
                    args=["/app/pipebot/mcp_server.py"]
                )
            })

@dataclass(frozen=True)
class UIColors:
    blue: str = fg('light_blue')
    green: str = fg('light_green') 
    red: str = fg('light_red')
    reset: str = attr('reset')

@dataclass(frozen=True)
class StorageConfig:
    memory_dir: str = os.path.expanduser("~/.pipebot/memory")
    kb_dir: str = os.path.expanduser("~/.pipebot/kb")
    collection_name: str = "conversation_memory"
    kb_collection_name: str = "knowledge_base"

@dataclass(frozen=True)
class AppConfig:
    aws: AWSConfig = AWSConfig()
    colors: UIColors = UIColors()
    storage: StorageConfig = StorageConfig()
    mcp: MCPConfig = MCPConfig.load_from_file()
    max_output_size: int = 25000 
