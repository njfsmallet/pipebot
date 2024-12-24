import shlex
from typing import Any, Dict, List
from pipebot.tools.executor import CommandExecutor
from pipebot.config import AppConfig
import urllib.parse
import requests
from bs4 import BeautifulSoup

class ToolExecutor:
    @staticmethod
    def _parse_command(command: str) -> List[str]:
        operators = ['|', '&&', '||', ';']
        result = []
        current_cmd = ''
        i = 0
        
        while i < len(command):
            for op in operators:
                if command[i:].startswith(op):
                    if current_cmd.strip():
                        result.append(current_cmd.strip())
                    current_cmd = ''
                    i += len(op)
                    break
            else:
                current_cmd += command[i]
                i += 1
        
        if current_cmd.strip():
            result.append(current_cmd.strip())
        
        return result

    @staticmethod
    def _validate_tool_command(command: str, tool_name: str, allowed_commands: List[str], disallowed_options: List[str], command_index: int) -> bool:
        try:
            cmd_parts = shlex.split(command)
            
            tool_index = -1
            for i, part in enumerate(cmd_parts):
                if part == tool_name:
                    tool_index = i
                    break
            
            if tool_index == -1:
                return True
            
            validate_index = tool_index + 1 + command_index
            if validate_index >= len(cmd_parts):
                raise ValueError(f"Invalid {tool_name} command: missing required parts")
            
            command_to_validate = cmd_parts[validate_index]
            
            if not any(command_to_validate.startswith(allowed_cmd) for allowed_cmd in allowed_commands):
                raise ValueError(f"Only specific read-only {tool_name} commands are allowed. Allowed commands are: {', '.join(allowed_commands)}")
            
            if any(option in cmd_parts for option in disallowed_options):
                raise ValueError(f"Disallowed options detected. The following options are not permitted: {', '.join(disallowed_options)}")
            
            return True
            
        except Exception as e:
            raise ValueError(f"Error validating {tool_name} command: {str(e)}")

    @staticmethod
    def _execute_tool_command(command: str, tool_name: str, allowed_commands: List[str], disallowed_options: List[str], command_index: int, app_config: AppConfig = None) -> Dict[str, Any]:
        try:
            full_command = f"{tool_name} {command}" if not command.strip().startswith(tool_name) else command
            
            sub_commands = ToolExecutor._parse_command(full_command)
            
            for sub_cmd in sub_commands:
                ToolExecutor._validate_tool_command(sub_cmd, tool_name, allowed_commands, disallowed_options, command_index)
            
            return CommandExecutor.execute(command, tool_name, prefix=tool_name, app_config=app_config)
            
        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": f"Error executing {tool_name} command: {str(e)}"}

    @staticmethod
    def aws(command: str, app_config: AppConfig = None) -> Dict[str, Any]:
        allowed_commands = [
            'analyze', 'check', 'describe', 'estimate', 'export',
            'filter', 'generate', 'get', 'help', 'list', 'lookup',
            'ls', 'preview', 'scan', 'search', 'show', 
            'summarize', 'test', 'validate', 'view'
        ]
        disallowed_options = ['--profile']
        return ToolExecutor._execute_tool_command(command, "aws", allowed_commands, disallowed_options, 1, app_config)

    @staticmethod
    def helm(command: str, app_config: AppConfig = None) -> Dict[str, Any]:
        allowed_commands = [
            'dependency', 'env', 'get', 'history', 'inspect', 'lint',
            'list', 'search', 'show', 'status', 'template', 'verify', 'version'
        ]
        disallowed_options = ['--kube-context', '--kubeconfig']
        return ToolExecutor._execute_tool_command(command, "helm", allowed_commands, disallowed_options, 0, app_config)

    @staticmethod
    def kubectl(command: str, app_config: AppConfig = None) -> Dict[str, Any]:
        allowed_commands = [
            'api-resources', 'api-versions', 'cluster-info', 'describe', 
            'explain', 'get', 'logs', 'top', 'version'
        ]
        disallowed_options = ['--kubeconfig', '--as', '--as-group', '--token']
        return ToolExecutor._execute_tool_command(command, "kubectl", allowed_commands, disallowed_options, 0, app_config)

    @staticmethod
    def google_search(query: str) -> Dict[str, Any]:
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
            response = requests.get(search_url, headers=headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            search_results = []
            
            for result in soup.select('div.g')[:5]:
                title_element = result.select_one('h3')
                link_element = result.select_one('a')
                snippet_element = result.select_one('div.VwiC3b')
                
                if title_element and link_element:
                    search_results.append({
                        'title': title_element.get_text(),
                        'link': link_element['href'],
                        'snippet': snippet_element.get_text() if snippet_element else 'No description available'
                    })
            
            return {
                "output": {
                    "organic": search_results
                }
            }
        except Exception as e:
            return {"error": f"Error executing Google search: {str(e)}"} 