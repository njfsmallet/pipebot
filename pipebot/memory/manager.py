import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import chromadb
from chromadb.config import Settings
from pipebot.aws import create_bedrock_client
from pipebot.ai.embeddings import generate_embeddings
from pipebot.config import AppConfig
from pipebot.logging_config import StructuredLogger
import logging
import uuid

class MemoryManager:
    def __init__(self, app_config: AppConfig):
        self.app_config = app_config
        self.logger = StructuredLogger("MemoryManager")
        self.collection = self.setup_memory()

    def setup_memory(self):
        Path(self.app_config.storage.memory_dir).mkdir(parents=True, exist_ok=True)
        
        client = chromadb.PersistentClient(
            path=self.app_config.storage.memory_dir, 
            settings=Settings(anonymized_telemetry=False)
        )
        
        try:
            collection = client.get_collection(self.app_config.storage.collection_name)
        except Exception as e:
            collection = client.create_collection(
                self.app_config.storage.collection_name,
                metadata={"dimension": self.app_config.aws.embedding_dimension}
            )
        
        return collection

    def get_relevant_history(self, query: str, limit: int = 3) -> List[Dict[str, str]]:
        bedrock_client = None
        try:
            bedrock_client = create_bedrock_client(self.app_config)
            query_embedding = generate_embeddings(query, self.app_config, bedrock_client)
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=limit
            )
        except Exception as e:
            self.logger.error("Error querying memory", error=str(e))
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

    def store_interaction(self, role: str, content: str):
        if not content or not isinstance(content, str):
            return
        
        timestamp = datetime.datetime.now().isoformat()
        content_hash = hashlib.md5(content.encode()).hexdigest()
        id = f"{timestamp}-{content_hash}"
        
        bedrock_client = None
        try:
            bedrock_client = create_bedrock_client(self.app_config)
            embeddings = generate_embeddings(content, self.app_config, bedrock_client)
            
            self.collection.add(
                documents=[content],
                metadatas=[{"role": role, "timestamp": timestamp}],
                ids=[id],
                embeddings=[embeddings]
            )
        except Exception as e:
            self.logger.error("Error storing memory", error=str(e)) 