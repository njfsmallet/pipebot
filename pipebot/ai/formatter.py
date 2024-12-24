import json
from typing import Any, Dict, List
from pipebot.config import AppConfig

class ResponseFormatter:
    def __init__(self, app_config: AppConfig):
        self.app_config = app_config
    
    def format_tool_output(self, output: Any) -> str:
        if isinstance(output, dict):
            if 'organic' in output:
                return self.format_search_results(output['organic'])
            return json.dumps(output, indent=2)
        return str(output)
    
    def format_search_results(self, results: List[Dict[str, Any]]) -> str:
        formatted = ["Search Results:"]
        for idx, result in enumerate(results[:5], 1):
            formatted.extend([
                f"\n{idx}. {result.get('title', 'No title')}",
                f"Link: {result.get('link', 'No link')}",
                f"Snippet: {result.get('snippet', 'No description')}"
            ])
        return "\n".join(formatted)
    
    def format_command_output(self, output: str) -> str:
        lines = str(output).strip().split('\n')
        if len(lines) > 1:
            header = lines[0]
            data = lines[1:]
            return f"{self.app_config.colors.green}{header}{self.app_config.colors.reset}\n" + "\n".join(data)
        return output 