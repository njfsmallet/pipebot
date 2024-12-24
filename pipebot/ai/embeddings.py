import json
from typing import List
from pipebot.config import AppConfig

def generate_embeddings(text: str, app_config: AppConfig, bedrock_client) -> List[float]:
    if not isinstance(text, str):
        if isinstance(text, (list, dict)):
            text = str(text)
            text = ' '.join(text.split())
        else:
            text = str(text)
    
    if not text.strip():
        raise ValueError("Cannot generate embeddings for empty text")
    
    estimated_tokens = len(text) // 2
    max_tokens = 7000
    
    if estimated_tokens > max_tokens:
        char_limit = max_tokens * 2
        text = text[:char_limit] + "..."
    
    try:
        response = bedrock_client.invoke_model(
            modelId=app_config.aws.embedding_model,
            body=json.dumps({
                "inputText": text,
                "normalize": True,
                "dimensions": app_config.aws.embedding_dimension,
                "embeddingTypes": ["float"]
            }),
            contentType='application/json',
            accept='application/json'
        )
        response_body = json.loads(response['body'].read())
        
        if 'embeddingsByType' not in response_body or 'float' not in response_body['embeddingsByType']:
            raise RuntimeError("Invalid response format from embedding model")
            
        return response_body['embeddingsByType']['float']
        
    except Exception as e:
        if "Too many input tokens" in str(e):
            char_limit = max_tokens
            truncated_text = text[:char_limit] + "..."
            return generate_embeddings(truncated_text, app_config, bedrock_client)
        raise RuntimeError(f"Failed to generate embeddings: {str(e)}") 