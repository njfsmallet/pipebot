import shlex
from typing import Any, Dict, List
from pipebot.tools.executor import CommandExecutor
from pipebot.config import AppConfig
import urllib.parse
import requests
from bs4 import BeautifulSoup
import os
import json
import re

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
        disallowed_options = []
        return ToolExecutor._execute_tool_command(command, "aws", allowed_commands, disallowed_options, 1, app_config)

    @staticmethod
    def hcloud(command: str, app_config: AppConfig = None) -> Dict[str, Any]:
        allowed_commands = [
            'List', 'Show'
        ]
        disallowed_options = []
        return ToolExecutor._execute_tool_command(command, "hcloud", allowed_commands, disallowed_options, 1, app_config)

    @staticmethod
    def helm(command: str, app_config: AppConfig = None) -> Dict[str, Any]:
        allowed_commands = [
            'dependency', 'env', 'get', 'history', 'inspect', 'lint',
            'list', 'search', 'show', 'status', 'template', 'verify', 'version'
        ]
        disallowed_options = ['--kubeconfig']
        return ToolExecutor._execute_tool_command(command, "helm", allowed_commands, disallowed_options, 0, app_config)

    @staticmethod
    def kubectl(command: str, app_config: AppConfig = None) -> Dict[str, Any]:
        allowed_commands = [
            'api-resources', 'api-versions', 'cluster-info', 'describe', 
            'explain', 'get', 'logs', 'top', 'version', 'config'
        ]
        disallowed_options = ['--kubeconfig', '--as', '--as-group', '--token']
        return ToolExecutor._execute_tool_command(command, "kubectl", allowed_commands, disallowed_options, 0, app_config)

    @staticmethod
    def serper(query: str, app_config: AppConfig = None) -> Dict[str, Any]:
        try:
            api_key = os.getenv('SERPER_API_KEY')
            if not api_key:
                return {"error": "SERPER_API_KEY environment variable is not set"}

            headers = {
                'X-API-KEY': api_key,
                'Content-Type': 'application/json'
            }
            
            payload = {
                "q": query
            }
            
            response = requests.post(
                "https://google.serper.dev/search",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            
            search_results = []
            if 'organic' in data:
                for result in data['organic'][:5]:
                    search_results.append({
                        'title': result.get('title', 'No title'),
                        'link': result.get('link', ''),
                        'snippet': result.get('snippet', 'No description available')
                    })
            
            return {
                "output": {
                    "organic": search_results
                }
            }
        except Exception as e:
            return {"error": f"Error executing Serper search: {str(e)}"}

    @staticmethod
    def python_exec(code: str) -> Dict[str, Any]:
        try:
            # Define allowed modules
            ALLOWED_MODULES = {
                'array': 'array',
                'base64': 'base64',
                'binascii': 'binascii',
                'bisect': 'bisect',
                'boto3': 'boto3',
                'bson': 'bson',
                'calendar': 'calendar',
                'cmath': 'cmath',
                'codecs': 'codecs',
                'collections': 'collections',
                'datetime': 'datetime',
                'dateutil': 'dateutil',
                'difflib': 'difflib',
                'enum': 'enum',
                'fractions': 'fractions',
                'functools': 'functools',
                'gzip': 'gzip',
                'hashlib': 'hashlib',
                'heapq': 'heapq',
                'itertools': 'itertools',
                'json': 'json',
                'kubernetes': 'kubernetes',
                'math': 'math',
                'matplotlib': 'matplotlib',
                'mpmath': 'mpmath',
                'numpy': 'np',
                'operator': 'operator',
                'pandas': 'pd',
                'prometheus_client': 'prometheus_client',
                'prometheus_api_client': 'prometheus_api_client',
                'pymongo': 'pymongo',
                're': 're',
                'random': 'random',
                'sklearn': 'sklearn',
                'secrets': 'secrets',
                'scipy.special': 'scipy_special',
                'statistics': 'statistics',
                'string': 'string',
                'sympy': 'sympy',
                'textwrap': 'textwrap',
                'time': 'time',
                'timeit': 'timeit',
                'unicodedata': 'unicodedata',
                'uuid': 'uuid',
                'zlib': 'zlib'
            }

            # Create a restricted globals dictionary with a safe __import__
            def safe_import(name, *args, **kwargs):
                base_module = name.split('.')[0]
                if base_module not in ALLOWED_MODULES:
                    raise ImportError(f"Import of '{base_module}' is not allowed. Allowed modules are: {', '.join(ALLOWED_MODULES.keys())}")
                return __import__(name, *args, **kwargs)

            # Create a restricted globals dictionary
            restricted_globals = {
                '__builtins__': {
                    'abs': abs, 'all': all, 'any': any, 'ascii': ascii,
                    'bin': bin, 'bool': bool, 'bytearray': bytearray,
                    'bytes': bytes, 'chr': chr, 'complex': complex,
                    'dict': dict, 'divmod': divmod, 'enumerate': enumerate,
                    'filter': filter, 'float': float, 'format': format,
                    'frozenset': frozenset, 'hash': hash, 'hex': hex,
                    'int': int, 'isinstance': isinstance, 'issubclass': issubclass,
                    'iter': iter, 'len': len, 'list': list, 'map': map,
                    'max': max, 'min': min, 'next': next, 'oct': oct,
                    'ord': ord, 'pow': pow, 'print': print, 'range': range,
                    'repr': repr, 'reversed': reversed, 'round': round,
                    'set': set, 'slice': slice, 'sorted': sorted, 'str': str,
                    'sum': sum, 'tuple': tuple, 'type': type, 'zip': zip,
                    '__import__': safe_import  # Add safe_import function
                }
            }

            # Pre-import allowed modules
            for module_name, alias in ALLOWED_MODULES.items():
                try:
                    module = __import__(module_name)
                    restricted_globals[alias] = module
                except ImportError:
                    pass  # Skip if module is not installed

            # Create a string buffer to capture output
            from io import StringIO
            import sys
            output_buffer = StringIO()
            original_stdout = sys.stdout
            sys.stdout = output_buffer

            try:
                # Execute the code in the restricted environment
                exec(code, restricted_globals, {})
                output = output_buffer.getvalue()
                return {"output": output if output.strip() else "Code executed successfully with no output."}
            finally:
                sys.stdout = original_stdout

        except Exception as e:
            return {"error": f"Error executing Python code: {str(e)}"}

    @staticmethod
    def switch_context(command: str, app_config: AppConfig = None) -> Dict[str, Any]:
        """Search for AWS profile, Huawei Cloud profile, and kubectl context matching the given command."""
        try:
            # Get AWS profiles
            profiles_result = ToolExecutor.aws("configure list-profiles", app_config)
            if 'error' in profiles_result:
                return {"error": f"Failed to get AWS profiles: {profiles_result['error']}"}
            
            profiles = [p.strip() for p in profiles_result['output'].strip().split('\n') if p.strip()]
            
            # Initialize aws_profiles with all profiles, but only get region for matching profile
            aws_profiles = {profile: None for profile in profiles}
            matching_profile = command.strip() if command else None
            
            if matching_profile:
                # Find matching profile case-insensitively
                matching_profile_lower = matching_profile.lower()
                for profile in profiles:
                    if profile.lower() == matching_profile_lower:
                        region_cmd = f"configure get region --profile {profile}"
                        region_result = ToolExecutor.aws(region_cmd, app_config)
                        if 'output' in region_result:
                            aws_profiles[profile] = region_result['output'].strip()
                        break
            
            # Get Huawei Cloud profiles
            hcloud_profiles = {}
            hcloud_result = ToolExecutor.hcloud("configure List --cli-output=json", app_config)
            
            if 'error' not in hcloud_result and 'output' in hcloud_result:
                try:
                    hcloud_data = json.loads(hcloud_result['output'])
                    for profile in hcloud_data.get('profiles', []):
                        profile_name = profile.get('name')
                        if profile_name:
                            hcloud_profiles[profile_name] = profile.get('region')
                except json.JSONDecodeError:
                    # Handle JSON parsing error silently
                    pass
            
            # Get kubectl contexts
            kubectl_cmd = "config get-contexts"
            kubectl_result = ToolExecutor.kubectl(kubectl_cmd, app_config)
            if 'error' in kubectl_result:
                return {"error": f"Failed to get kubectl contexts: {kubectl_result['error']}"}
            
            # Parse kubectl contexts output
            contexts = []
            for line in kubectl_result['output'].strip().split('\n')[1:]:  # Skip header line
                # Look for AWS EKS context pattern
                match = re.search(r'arn:aws[^:]*:eks:[^:]+:[^:]+:cluster/[^/]+-[^-]+(?:\s|$)', line)
                if match:
                    context_name = match.group(0).strip()  # Strip any trailing whitespace
                    contexts.append(context_name)
            
            return {
                "output": {
                    "aws_profiles": aws_profiles,
                    "hcloud_profiles": hcloud_profiles,
                    "kubectl_contexts": contexts
                }
            }

        except Exception as e:
            return {"error": f"Error getting profiles and contexts: {str(e)}"}

    @staticmethod
    def think(command: str) -> Dict[str, Any]:
        """Process a thought and return it as output. This is used for complex reasoning or caching thoughts."""
        try:
            return {"output": command}
        except Exception as e:
            return {"error": f"Error processing thought: {str(e)}"}
