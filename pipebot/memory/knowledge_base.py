import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import chromadb
from chromadb.config import Settings
from tqdm import tqdm
from pipebot.aws import create_bedrock_client
from pipebot.ai.embeddings import generate_embeddings
from pipebot.config import AppConfig
from pipebot.logging_config import StructuredLogger
from pipebot.utils.token_estimator import TokenEstimator
import chromadb.errors
import logging

class KnowledgeBase:
    MAX_FILE_SIZE = 250_000
    MAX_CHUNK_TOKENS = 500
    OVERLAP_TOKENS = 50
    
    def __init__(self, app_config: AppConfig):
        self.app_config = app_config
        self.logger = StructuredLogger("KnowledgeBase")
        
        self.client = chromadb.PersistentClient(
            path=self.app_config.storage.memory_dir,
            settings=Settings(anonymized_telemetry=False)
        )
        self.collection = self._get_or_create_collection()

    def _get_or_create_collection(self):
        try:
            return self.client.get_collection(self.app_config.storage.kb_collection_name)
        except Exception as e:
            return self.client.create_collection(
                self.app_config.storage.kb_collection_name,
                metadata={"dimension": self.app_config.aws.embedding_dimension}
            )

    def _chunk_text(self, text: str, file_path: str, max_tokens: int = 500, overlap_tokens: int = 50) -> List[Dict[str, Any]]:
        if not text or not text.strip():
            return []
        
        file_hash = hashlib.md5(str(file_path).encode()).hexdigest()[:8]
        file_content_hash = hashlib.md5(text.encode()).hexdigest()[:8]
        
        token_estimator = TokenEstimator()
        
        paragraphs = text.split('\n\n')
        chunks = []
        current_chunk = []
        current_tokens = 0
        
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            
            para_tokens = token_estimator.estimate_tokens(paragraph)
            
            if para_tokens > max_tokens:
                sentences = [s.strip() + '.' for s in paragraph.split('. ') if s.strip()]
                for sentence in sentences:
                    sent_tokens = token_estimator.estimate_tokens(sentence)
                    
                    if current_tokens + sent_tokens > max_tokens:
                        if current_chunk:
                            chunks.append(' '.join(current_chunk))
                            current_chunk = current_chunk[-2:] if len(current_chunk) > 2 else []
                            current_tokens = sum(token_estimator.estimate_tokens(c) for c in current_chunk)
                    
                    current_chunk.append(sentence)
                    current_tokens += sent_tokens
            else:
                if current_tokens + para_tokens > max_tokens:
                    if current_chunk:
                        chunks.append(' '.join(current_chunk))
                        current_chunk = current_chunk[-2:] if len(current_chunk) > 2 else []
                        current_tokens = sum(token_estimator.estimate_tokens(c) for c in current_chunk)
                
                current_chunk.append(paragraph)
                current_tokens += para_tokens
        
        if current_chunk:
            chunks.append(' '.join(current_chunk))
        
        processed_chunks = []
        for idx, chunk in enumerate(chunks):
            chunk_hash = hashlib.md5(chunk.encode()).hexdigest()[:8]
            chunk_id = f"{file_hash}-{file_content_hash}-{chunk_hash}-{idx}"
            
            processed_chunks.append({
                "text": chunk,
                "id": chunk_id,
                "metadata": {
                    "source": str(file_path),
                    "file_hash": file_hash,
                    "content_hash": file_content_hash,
                    "chunk_hash": chunk_hash,
                    "chunk_index": idx,
                    "timestamp": datetime.datetime.now().isoformat()
                }
            })
        
        return processed_chunks

    def scan_documents(self):
        kb_path = Path(self.app_config.storage.kb_dir)
        if not kb_path.exists():
            raise FileNotFoundError(f"Knowledge base directory not found: {kb_path}")

        cache_dir = Path(self.app_config.storage.memory_dir) / "embedding_cache"
        cache_dir.mkdir(exist_ok=True)
        
        bedrock_client = None
        try:
            bedrock_client = create_bedrock_client(self.app_config)
            supported_extensions = {'.txt', '.md', '.mdx', '.html', '.yaml', '.yml', 
                                 '.lit', '.asciidoc', '.rst'}
            
            self.logger.info("Scanning knowledge base directory...")
            files = [f for f in kb_path.rglob('*') 
                    if f.is_file() 
                    and f.suffix in supported_extensions 
                    and f.stat().st_size < self.MAX_FILE_SIZE]
            
            large_files = [f for f in kb_path.rglob('*') 
                          if f.is_file() 
                          and f.suffix in supported_extensions 
                          and f.stat().st_size >= self.MAX_FILE_SIZE]
            if large_files:
                self.logger.warning(f"Skipping {len(large_files)} files larger than 250KB:")
                for f in large_files:
                    self.logger.warning(
                        f"  - {f.relative_to(kb_path)} "
                        f"({f.stat().st_size / 1_000:.1f}KB)"
                    )
                    self.logger.info(
                        f"    Consider splitting this file into smaller documents "
                        f"for better processing"
                    )

            current_files = {str(f) for f in files}
            
            self.logger.info("Checking existing documents...")
            existing_docs = {}
            try:
                results = self.collection.get(
                    include=['metadatas']
                )
                if results and results['metadatas']:
                    for metadata in results['metadatas']:
                        if 'source' in metadata and 'content_hash' in metadata:
                            existing_docs[metadata['source']] = metadata['content_hash']
            except Exception as e:
                self.logger.error(f"Error fetching existing documents: {str(e)}")

            files_to_remove = set(existing_docs.keys()) - current_files
            if files_to_remove:
                self.logger.info(f"Removing {len(files_to_remove)} old files...")
                for file_path in tqdm(files_to_remove, desc="Removing old files"):
                    try:
                        self.collection.delete(
                            where={"source": file_path}
                        )
                    except Exception as e:
                        self.logger.error(f"Error removing {file_path}: {str(e)}")

            self.logger.info("Identifying files to process...")
            files_to_process = []
            for file_path in tqdm(files, desc="Scanning files"):
                if file_path.suffix not in supported_extensions:
                    continue
                    
                file_str = str(file_path)
                try:
                    content = file_path.read_text(encoding='utf-8')
                    content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
                    
                    if file_str not in existing_docs or existing_docs[file_str] != content_hash:
                        files_to_process.append((file_path, content))
                except Exception as e:
                    self.logger.error(f"Error reading {file_path}: {str(e)}")
                    continue

            if not files_to_process and not files_to_remove:
                self.logger.success("Knowledge base is up to date.")
                return

            if files_to_process:
                total_files = len(files_to_process)
                self.logger.info(f"Processing {total_files} files...")
                
                for file_path, content in tqdm(files_to_process, desc="Processing files"):
                    try:
                        self.collection.delete(
                            where={"source": str(file_path)}
                        )
                        
                        chunks = self._chunk_text(content, file_path)
                        if not chunks:
                            continue
                        
                        chunk_embeddings = []
                        chunk_ids = []
                        chunk_texts = []
                        chunk_metadatas = []
                        
                        for chunk in tqdm(chunks, desc=f"Processing chunks for {file_path.name}", leave=False):
                            cached_embedding = self._get_cached_embedding(chunk["text"], cache_dir / f"{chunk['metadata']['file_hash']}.json")
                            if cached_embedding:
                                chunk_embeddings.append(cached_embedding)
                            else:
                                chunk_embeddings.append(None)
                            
                            chunk_ids.append(chunk["id"])
                            chunk_texts.append(chunk["text"])
                            chunk_metadatas.append(chunk["metadata"])
                        
                        chunks_to_embed = [
                            text for text, embedding 
                            in zip(chunk_texts, chunk_embeddings) 
                            if embedding is None
                        ]
                        
                        if chunks_to_embed:
                            self.logger.debug(f"Generating {len(chunks_to_embed)} embeddings for {file_path.name}")
                            new_embeddings = self._batch_generate_embeddings(chunks_to_embed, bedrock_client)
                            
                            embed_idx = 0
                            for i, embedding in enumerate(chunk_embeddings):
                                if embedding is None:
                                    chunk_embeddings[i] = new_embeddings[embed_idx]
                                    self._save_cached_embedding(
                                        chunk_texts[i], 
                                        new_embeddings[embed_idx], 
                                        cache_dir / f"{chunk_metadatas[i]['file_hash']}.json"
                                    )
                                    embed_idx += 1
                        
                        self.collection.add(
                            documents=chunk_texts,
                            metadatas=chunk_metadatas,
                            ids=chunk_ids,
                            embeddings=chunk_embeddings
                        )
                        
                    except Exception as e:
                        self.logger.error(f"Error processing {file_path}: {str(e)}")
                        continue
                
                self.logger.success("\nKnowledge base scanning completed!")
            
        finally:
            pass

    def get_relevant_context(self, query: str, limit: int = 3) -> str:
        bedrock_client = None
        try:
            bedrock_client = create_bedrock_client(self.app_config)
            query_embedding = generate_embeddings(query, self.app_config, bedrock_client)
            
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=limit
            )
            
            if not results or not results['documents']:
                return ""
            
            context_parts = []
            for doc, metadata in zip(results['documents'][0], results['metadatas'][0]):
                source = metadata["source"]
                context_parts.append(f"[From {source}]\n{doc}")
            
            return "\n\n".join(context_parts)
            
        finally:
            pass

    def _get_cached_embedding(self, content: str, cache_file: Path) -> Optional[List[float]]:
        if not cache_file.exists():
            return None
        
        content_hash = hashlib.md5(content.encode()).hexdigest()
        try:
            with cache_file.open('r') as f:
                cache = json.load(f)
                return cache.get(content_hash)
        except Exception as e:
            self.logger.debug(f"Cache read error: {str(e)}")
            return None

    def _save_cached_embedding(self, content: str, embedding: List[float], cache_file: Path):
        content_hash = hashlib.md5(content.encode()).hexdigest()
        try:
            cache = {}
            if cache_file.exists():
                with cache_file.open('r') as f:
                    cache = json.load(f)
            
            cache[content_hash] = embedding
            
            with cache_file.open('w') as f:
                json.dump(cache, f)
        except Exception as e:
            self.logger.debug(f"Cache write error: {str(e)}")

    def _batch_generate_embeddings(self, texts: List[str], bedrock_client) -> List[List[float]]:
        embeddings = []
        batch_size = 5
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            try:
                response = bedrock_client.invoke_model(
                    modelId=self.app_config.aws.embedding_model,
                    body=json.dumps({
                        "inputTexts": batch,
                        "normalize": True,
                        "dimensions": self.app_config.aws.embedding_dimension,
                        "embeddingTypes": ["float"]
                    }),
                    contentType='application/json',
                    accept='application/json'
                )
                
                response_body = json.loads(response['body'].read())
                batch_embeddings = response_body['embeddingsByType']['float']
                embeddings.extend(batch_embeddings)
                
            except Exception as e:
                self.logger.debug(f"Batch embedding failed: {str(e)}, falling back to individual processing")
                for text in batch:
                    try:
                        embedding = generate_embeddings(text, self.app_config, bedrock_client)
                        embeddings.append(embedding)
                    except Exception as e:
                        self.logger.error(f"Failed to generate embedding: {str(e)}")
                        embeddings.append([0.0] * self.app_config.aws.embedding_dimension)
        
        return embeddings 