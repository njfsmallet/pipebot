import subprocess
from typing import Any, Dict
from pipebot.config import AppConfig

class CommandExecutor:
    @staticmethod
    def execute(command: str, tool: str, prefix: str = "", app_config: AppConfig = None) -> Dict[str, Any]:
        try:
            process = subprocess.Popen(f"{prefix} {command}", 
                                       shell=True, 
                                       stdout=subprocess.PIPE, 
                                       stderr=subprocess.PIPE, 
                                       text=True)

            output, error = process.communicate()

            if process.returncode != 0 and not error.strip():
                return {"output": "Command executed successfully but returned no output."}

            if process.returncode != 0:
                return {"error": f"Error running {tool} command: {error}"}

            return {"output": output}
        except Exception as e:
            return {"error": f"Error executing command: {str(e)}"}