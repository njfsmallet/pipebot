#!/usr/bin/env python3
"""
FastMCP Server for PipeBot Tools

This server exposes PipeBot's existing tools as MCP tools using the FastMCP interface,
which provides a simpler and more robust way to create MCP servers.
"""

import asyncio
import os
import shlex
import subprocess
from typing import Any, Dict, List
import urllib.parse
import requests
from bs4 import BeautifulSoup
import json
import re
from io import StringIO
import sys
import logging
from pathlib import Path
import tempfile
import shutil
import hashlib

from mcp.server.fastmcp import FastMCP

# Configure logging to suppress FastMCP server logs
logging.getLogger("mcp.server.fastmcp").setLevel(logging.WARNING)
logging.getLogger("mcp.server").setLevel(logging.WARNING)
logging.getLogger("git").setLevel(logging.WARNING)

# Load environment variables from .env file if it exists
def load_env_file():
    """Load environment variables from .env file"""
    # Try to load from the project root .env file first
    root_env_file = Path(__file__).parent.parent / '.env'
    if root_env_file.exists():
        with open(root_env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()
    
    # Also try to load from the pipebot directory .env file
    env_file = Path(__file__).parent / '.env'
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

# Load environment variables
load_env_file()

# Configure proxy settings for HTTP requests
def configure_proxy_session():
    """Configure a requests session with proxy settings from environment variables"""
    session = requests.Session()
    
    # Get proxy settings from environment variables
    http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
    https_proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
    no_proxy = os.environ.get('NO_PROXY') or os.environ.get('no_proxy')
    
    if http_proxy or https_proxy:
        proxies = {}
        if http_proxy:
            proxies['http'] = http_proxy
        if https_proxy:
            proxies['https'] = https_proxy
        
        session.proxies.update(proxies)
        
        # Configure no_proxy if specified
        if no_proxy:
            session.trust_env = False  # Don't use environment variables for proxy
            session.proxies['no'] = no_proxy
    
    return session

# Create an MCP server
mcp = FastMCP("PipeBot Tools")


class ImprovedToolExecutor:
    """Improved tool executor with advanced features from legacy ToolExecutor"""
    
    @staticmethod
    def _parse_command(command: str) -> List[str]:
        """Parse command with operators like |, &&, ||, ;"""
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
        """Validate tool command with advanced parsing"""
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
    def _execute_tool_command(command: str, tool_name: str, allowed_commands: List[str], disallowed_options: List[str], command_index: int) -> Dict[str, Any]:
        """Execute tool command with advanced validation"""
        try:
            full_command = f"{tool_name} {command}" if not command.strip().startswith(tool_name) else command
            
            sub_commands = ImprovedToolExecutor._parse_command(full_command)
            
            for sub_cmd in sub_commands:
                ImprovedToolExecutor._validate_tool_command(sub_cmd, tool_name, allowed_commands, disallowed_options, command_index)
            
            # Execute with improved subprocess handling
            try:
                process = subprocess.Popen(full_command, 
                                           shell=True, 
                                           stdout=subprocess.PIPE, 
                                           stderr=subprocess.PIPE, 
                                           text=True)

                output, error = process.communicate()

                if process.returncode != 0 and not error.strip():
                    return {"output": "Command executed successfully but returned no output."}

                if process.returncode != 0:
                    return {"error": f"Error running {tool_name} command: {error}"}

                return {"output": output}
            except Exception as e:
                return {"error": f"Error executing command: {str(e)}"}
            
        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": f"Error executing {tool_name} command: {str(e)}"}

    @staticmethod
    def execute_aws(command: str) -> Dict[str, Any]:
        """Execute AWS CLI command with advanced validation"""
        allowed_commands = [
            'analyze', 'check', 'describe', 'estimate', 'export',
            'filter', 'generate', 'get', 'help', 'list', 'lookup',
            'ls', 'preview', 'scan', 'search', 'show', 
            'summarize', 'test', 'validate', 'view'
        ]
        disallowed_options = []
        return ImprovedToolExecutor._execute_tool_command(command, "aws", allowed_commands, disallowed_options, 1)

    @staticmethod
    def execute_hcloud(command: str) -> Dict[str, Any]:
        """Execute Huawei Cloud CLI command with advanced validation"""
        allowed_commands = ['List', 'Show']
        disallowed_options = []
        return ImprovedToolExecutor._execute_tool_command(command, "hcloud", allowed_commands, disallowed_options, 1)

    @staticmethod
    def execute_helm(command: str) -> Dict[str, Any]:
        """Execute Helm command with advanced validation"""
        allowed_commands = [
            'dependency', 'env', 'get', 'history', 'inspect', 'lint',
            'list', 'search', 'show', 'status', 'template', 'verify', 'version'
        ]
        disallowed_options = ['--kubeconfig']
        return ImprovedToolExecutor._execute_tool_command(command, "helm", allowed_commands, disallowed_options, 0)

    @staticmethod
    def execute_kubectl(command: str) -> Dict[str, Any]:
        """Execute kubectl command with advanced validation"""
        allowed_commands = [
            'api-resources', 'api-versions', 'cluster-info', 'describe', 
            'explain', 'get', 'logs', 'top', 'version', 'config'
        ]
        disallowed_options = ['--kubeconfig', '--as', '--as-group', '--token']
        return ImprovedToolExecutor._execute_tool_command(command, "kubectl", allowed_commands, disallowed_options, 0)

    @staticmethod
    def execute_serper(query: str) -> Dict[str, Any]:
        """Execute Serper search with improved error handling and proxy support"""
        try:
            # Try multiple sources for the API key
            api_key = os.environ.get('SERPER_API_KEY')
            
            if not api_key:
                # Check if there's a .env file in the current directory
                current_env_file = Path.cwd() / '.env'
                if current_env_file.exists():
                    with open(current_env_file, 'r') as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith('SERPER_API_KEY='):
                                api_key = line.split('=', 1)[1].strip()
                                break
            
            if not api_key:
                return {
                    "error": "SERPER_API_KEY not found. Please set it in one of the following ways:\n"
                    "1. Environment variable: export SERPER_API_KEY='your_api_key'\n"
                    "2. .env file in the pipebot directory: SERPER_API_KEY=your_api_key\n"
                    "3. .env file in the current working directory: SERPER_API_KEY=your_api_key"
                }

            headers = {
                'X-API-KEY': api_key,
                'Content-Type': 'application/json'
            }
            
            payload = {"q": query}
            
            # Use proxy-configured session for the request
            session = configure_proxy_session()
            
            response = session.post(
                "https://google.serper.dev/search",
                headers=headers,
                json=payload,
                timeout=30
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
            
            return {"output": {"organic": search_results}}
        except requests.exceptions.Timeout:
            return {"error": "Request timeout: The search request took too long to complete"}
        except requests.exceptions.RequestException as e:
            return {"error": f"Network error during Serper search: {str(e)}"}
        except json.JSONDecodeError:
            return {"error": "Invalid JSON response from Serper API"}
        except Exception as e:
            return {"error": f"Error executing Serper search: {str(e)}"}

    @staticmethod
    def execute_python_exec(code: str) -> Dict[str, Any]:
        """Execute Python code with improved security and module handling"""
        try:
            # Define allowed modules with aliases
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
                'dataclasses': 'dataclasses',
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
                'os': 'os',
                'pandas': 'pd',
                'prometheus_client': 'prometheus_client',
                'prometheus_api_client': 'prometheus_api_client',
                'pymongo': 'pymongo',
                're': 're',
                'random': 'random',
                'requests': 'requests',
                'sklearn': 'sklearn',
                'secrets': 'secrets',
                'scipy.special': 'scipy_special',
                'socket': 'socket',
                'statistics': 'statistics',
                'string': 'string',
                'sympy': 'sympy',
                'textwrap': 'textwrap',
                'threading': 'threading',
                'time': 'time',
                'timeit': 'timeit',
                'typing': 'typing',
                'unicodedata': 'unicodedata',
                'urllib3': 'urllib3',
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
                    '__import__': safe_import
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
    def execute_switch_context(command: str) -> Dict[str, Any]:
        """Execute switch context with improved profile detection"""
        try:
            # Get AWS profiles
            profiles_result = ImprovedToolExecutor.execute_aws("configure list-profiles")
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
                        region_result = ImprovedToolExecutor.execute_aws(region_cmd)
                        if 'output' in region_result:
                            aws_profiles[profile] = region_result['output'].strip()
                        break
            
            # Get Huawei Cloud profiles
            hcloud_profiles = {}
            hcloud_result = ImprovedToolExecutor.execute_hcloud("configure List --cli-output=json")
            
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
            kubectl_result = ImprovedToolExecutor.execute_kubectl(kubectl_cmd)
            if 'error' in kubectl_result:
                return {"error": f"Failed to get kubectl contexts: {kubectl_result['error']}"}
            
            # Parse kubectl contexts output
            contexts = []
            for line in kubectl_result['output'].strip().split('\n')[1:]:  # Skip header line
                # Look for AWS EKS context pattern
                match = re.search(r'arn:aws[^:]*:eks:[^:]+:[^:]+:cluster/[^/]+-[^-]+(?:\s|$)', line)
                if match:
                    context_name = match.group(0).strip()
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


# Context Switch Tool
@mcp.tool()
def switch_context(command: str) -> str:
    """Search for matching AWS profile, Huawei Cloud profile, and kubectl context based on a search term. This tool helps identify the appropriate profiles and context to use for subsequent commands. It searches through available AWS profiles, Huawei Cloud profiles, and kubectl contexts to find matches containing the search term. Examples: 'switch_context k-nine-npr' to find profiles/contexts for the k-nine-npr cluster, 'switch_context 123456789012' to find profiles/contexts for a specific account."""
    result = ImprovedToolExecutor.execute_switch_context(command)
    if 'error' in result:
        return result['error']
    return str(result['output'])


# AWS CLI Tool
@mcp.tool()
def aws(command: str) -> str:
    """Execute a read-only AWS CLI command for any AWS service. Allowed actions include commands starting with: analyze, check, describe, estimate, export, filter, generate, get, help, list, lookup, ls, preview, scan, search, show, summarize, test, validate, and view. You must specify the AWS profile using the --profile option to ensure the command runs with the correct credentials."""
    if not command:
        return "No AWS command provided"
    
    # Validate that --profile is specified
    if "--profile" not in command:
        return "Error: The --profile option is required to specify which AWS profile to use. Format: '<service> <action> [parameters] --profile <profile_name>'"
    
    result = ImprovedToolExecutor.execute_aws(command)
    if 'error' in result:
        return result['error']
    return result['output']


# Huawei Cloud CLI Tool
@mcp.tool()
def hcloud(command: str) -> str:
    """Execute a read-only Huawei Cloud CLI command. Allowed operations include commands starting with: List, Show. This tool allows you to query Huawei Cloud resources in a read-only manner. You must specify the Huawei Cloud profile using the --cli-profile option to ensure the command runs with the correct credentials."""
    if not command:
        return "No Huawei Cloud command provided"
    
    # Validate that --cli-profile is specified
    if "--cli-profile=" not in command:
        return "Error: The --cli-profile option is required to specify which Huawei Cloud profile to use. Format: '<service> <operation> [--param1=paramValue1 --param2=paramValue2 ...] --cli-profile=<profile_name>'"
    
    result = ImprovedToolExecutor.execute_hcloud(command)
    if 'error' in result:
        return result['error']
    return result['output']


# kubectl Tool
@mcp.tool()
def kubectl(command: str) -> str:
    """Execute a read-only kubectl command. Allowed actions include: api-resources, api-versions, cluster-info, describe, explain, get, logs, top, and version. You must specify the kubectl context using the --context option to ensure the command runs with the correct cluster configuration."""
    if not command:
        return "No kubectl command provided"
    
    # Validate that --context is specified
    if "--context" not in command:
        return "Error: The --context option is required to specify which cluster to use. Format: '<command> [parameters] --context <context_name>'"
    
    result = ImprovedToolExecutor.execute_kubectl(command)
    if 'error' in result:
        return result['error']
    return result['output']


# Helm Tool
@mcp.tool()
def helm(command: str) -> str:
    """Execute a read-only Helm command. Allowed actions include: dependency, env, get, history, inspect, lint, list, search, show, status, template, verify, and version. You must specify the kubectl context using the --kube-context option to ensure the command runs with the correct cluster configuration."""
    if not command:
        return "No Helm command provided"
    
    # Validate that --kube-context is specified
    if "--kube-context" not in command:
        return "Error: The --kube-context option is required to specify which cluster to use. Format: '<command> [parameters] --kube-context <context_name>'"
    
    result = ImprovedToolExecutor.execute_helm(command)
    if 'error' in result:
        return result['error']
    return result['output']


# Web Search Tool (Serper)
@mcp.tool()
def serper(command: str) -> str:
    """Search the web using Serper, a Google Search API that returns search results. This tool provides search results including organic results, knowledge graphs, and related searches. IMPORTANT: This tool does NOT fetch or parse specific web pages - it only returns search results. NEVER use URLs as input - ONLY use keywords and search terms. Use this tool to find current information, documentation, examples, solutions to technical problems, verify technical details, check current best practices, and fact-check information. The results will include titles, snippets, and links to relevant pages."""
    if not command:
        return "No search query provided"
    
    # Validate that no URLs are provided
    if command.startswith('http://') or command.startswith('https://') or '://' in command:
        return "Error: URLs are not allowed as input. Please use keywords and search terms only. Examples: 'github karpenter-provider issues 7629' or 'kubernetes pod scheduling error'"
    
    result = ImprovedToolExecutor.execute_serper(command)
    if 'error' in result:
        return result['error']
    
    # Format the results for display
    output = result['output']
    if 'organic' in output:
        formatted_results = []
        for result_item in output['organic']:
            formatted_results.append(f"Title: {result_item['title']}")
            formatted_results.append(f"URL: {result_item['link']}")
            formatted_results.append(f"Snippet: {result_item['snippet']}")
            formatted_results.append("---")
        return "\n".join(formatted_results)
    
    return "No results found"


# Python Execution Tool
@mcp.tool()
def python_exec(command: str) -> str:
    """Execute Python code in a secure sandbox environment. The code runs with restricted access to Python's built-in functions for safety. Available Modules: array, base64, binascii, bisect, boto3, bson, calendar, cmath, codecs, collections, datetime, dateutil, difflib, enum, fractions, functools, gzip, hashlib, heapq, itertools, json, kubernetes, math, matplotlib, mpmath, numpy, operator, os, pandas, prometheus_client, prometheus-api-client, pymongo, re, random, requests, secrets, scipy.special, sklearn, statistics, string, sympy, textwrap, time, timeit, unicodedata, uuid, zlib. Modules can be imported directly. Example: import math, import numpy as np, from datetime import datetime, import kubernetes, import boto3, import prometheus_client, import os, import requests. Only safe, read-only operations are allowed."""
    result = ImprovedToolExecutor.execute_python_exec(command)
    if 'error' in result:
        return result['error']
    return result['output']


# Git Repository Tools
def clone_repo(repo_url: str) -> str:
    """Clone a repository and return the path. If repository is already cloned in temp directory, reuse it."""
    try:
        # Dynamically import git to avoid dependency issues if not installed
        import git
        
        # Create a deterministic directory name based on repo URL
        repo_hash = hashlib.sha256(repo_url.encode()).hexdigest()[:12]
        temp_dir = os.path.join(tempfile.gettempdir(), f"pipebot_git_{repo_hash}")
        
        # If directory exists and is a valid git repo, return it
        if os.path.exists(temp_dir):
            try:
                repo = git.Repo(temp_dir)
                if not repo.bare and any(remote.url == repo_url for remote in repo.remotes):
                    # Pull latest changes
                    repo.git.pull()
                    return temp_dir
            except Exception:
                # If there's any error with existing repo, clean it up
                shutil.rmtree(temp_dir, ignore_errors=True)
        
        # Create directory and clone repository
        os.makedirs(temp_dir, exist_ok=True)
        try:
            git.Repo.clone_from(repo_url, temp_dir)
            return temp_dir
        except Exception as e:
            # Clean up on error
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise Exception(f"Failed to clone repository: {str(e)}")
    except ImportError:
        raise Exception("GitPython is not installed. Please install it using 'pip install gitpython'")


def get_directory_tree(path: str, prefix: str = "") -> str:
    """Generate a tree-like directory structure string"""
    output = ""
    entries = sorted(os.listdir(path))
    
    for i, entry in enumerate(entries):
        if entry.startswith('.git'):
            continue
            
        is_last = i == len(entries) - 1
        current_prefix = "└── " if is_last else "├── "
        next_prefix = "    " if is_last else "│   "
        
        entry_path = os.path.join(path, entry)
        output += prefix + current_prefix + entry + "\n"
        
        if os.path.isdir(entry_path):
            output += get_directory_tree(entry_path, prefix + next_prefix)
            
    return output


@mcp.tool()
def git_directory_structure(repo_url: str) -> str:
    """Clone a Git repository and return its directory structure in a tree format. Args: repo_url: The URL of the Git repository. Returns: A string representation of the repository's directory structure."""
    try:
        # Clone the repository
        repo_path = clone_repo(repo_url)
        
        # Generate the directory tree
        tree = get_directory_tree(repo_path)
        return tree
            
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def git_read_important_files(repo_url: str, file_paths: list) -> str:
    """Read the contents of specified files in a given git repository. Args: repo_url: The URL of the Git repository, file_paths: List of file paths to read (relative to repository root). Returns: A dictionary mapping file paths to their contents."""
    try:
        # Clone the repository
        repo_path = clone_repo(repo_url)
        results = {}
        
        for file_path in file_paths:
            full_path = os.path.join(repo_path, file_path)
            
            # Check if file exists
            if not os.path.isfile(full_path):
                results[file_path] = f"Error: File not found"
                continue
                
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    results[file_path] = f.read()
            except UnicodeDecodeError:
                try:
                    # Try binary mode if text mode fails
                    with open(full_path, 'rb') as f:
                        results[file_path] = f"Binary file, size: {os.path.getsize(full_path)} bytes"
                except Exception as e:
                    results[file_path] = f"Error reading file: {str(e)}"
            except Exception as e:
                results[file_path] = f"Error reading file: {str(e)}"
        
        return str(results)
            
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def git_commit_history(repo_url: str, max_commits: int = 10) -> str:
    """Get the commit history of a Git repository. Args: repo_url: The URL of the Git repository, max_commits: Maximum number of commits to retrieve (default: 10). Returns: A string representation of the commit history."""
    try:
        import git
        
        # Clone the repository
        repo_path = clone_repo(repo_url)
        repo = git.Repo(repo_path)
        
        # Get commit history
        commits = list(repo.iter_commits('HEAD', max_count=max_commits))
        
        # Format commit history
        result = []
        for commit in commits:
            commit_info = {
                "hash": commit.hexsha[:8],
                "author": f"{commit.author.name} <{commit.author.email}>",
                "date": commit.committed_datetime.strftime("%Y-%m-%d %H:%M:%S"),
                "message": commit.message.strip()
            }
            result.append(commit_info)
        
        # Format the output
        output = "Commit History:\n\n"
        for i, commit in enumerate(result):
            output += f"[{commit['hash']}] {commit['date']} by {commit['author']}\n"
            output += f"Message: {commit['message']}\n"
            if i < len(result) - 1:
                output += "\n" + "-" * 40 + "\n\n"
        
        return output
        
    except ImportError:
        return "Error: GitPython is not installed. Please install it using 'pip install gitpython'"
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def git_repo_stats(repo_url: str) -> str:
    """Analyze a Git repository and return statistics. Args: repo_url: The URL of the Git repository. Returns: A string representation of the repository statistics."""
    try:
        import git
        from collections import Counter
        
        # Clone the repository
        repo_path = clone_repo(repo_url)
        repo = git.Repo(repo_path)
        
        # Get basic statistics
        commits_count = sum(1 for _ in repo.iter_commits())
        branches_count = len(repo.branches)
        tags_count = len(repo.tags)
        
        # Get file extensions and counts
        file_extensions = []
        file_count = 0
        for root, _, files in os.walk(repo_path):
            if '.git' in root:
                continue
            for file in files:
                file_count += 1
                _, ext = os.path.splitext(file)
                if ext:
                    file_extensions.append(ext.lower())
        
        # Count extensions
        extension_counts = Counter(file_extensions)
        top_extensions = extension_counts.most_common(5)
        
        # Get contributor statistics (limited to avoid performance issues)
        authors = {}
        for commit in repo.iter_commits(max_count=500):
            name = commit.author.name
            email = commit.author.email
            key = f"{name} <{email}>"
            authors[key] = authors.get(key, 0) + 1
        
        top_contributors = sorted(authors.items(), key=lambda x: x[1], reverse=True)[:5]
        
        # Format the output
        output = "Repository Statistics:\n\n"
        output += f"Repository: {repo_url}\n"
        output += f"Total Commits: {commits_count}\n"
        output += f"Branches: {branches_count}\n"
        output += f"Tags: {tags_count}\n"
        output += f"Total Files: {file_count}\n\n"
        
        output += "Top 5 File Extensions:\n"
        for ext, count in top_extensions:
            output += f"{ext}: {count} files\n"
        output += "\n"
        
        output += "Top 5 Contributors:\n"
        for author, count in top_contributors:
            output += f"{author}: {count} commits\n"
        
        return output
        
    except ImportError:
        return "Error: GitPython is not installed. Please install it using 'pip install gitpython'"
    except Exception as e:
        return f"Error: {str(e)}"


if __name__ == "__main__":
    # Run the server
    mcp.run() 
