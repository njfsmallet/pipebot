from dataclasses import dataclass
import os
from colored import attr, fg

@dataclass(frozen=True)
class AWSConfig:
    region_name: str = 'us-west-2'
    model_id: str = "arn:aws:bedrock:us-west-2:651602706704:inference-profile/us.anthropic.claude-3-5-haiku-20241022-v1:0"
    max_tokens: int = 4000
    embedding_model: str = "amazon.titan-embed-text-v2:0"
    embedding_dimension: int = 1024

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
    max_output_size: int = 25000 
