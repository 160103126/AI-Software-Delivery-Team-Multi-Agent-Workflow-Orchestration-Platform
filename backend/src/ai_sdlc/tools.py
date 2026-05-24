import logging
import subprocess
from pathlib import Path
from typing import List, Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _enforce_workspace(workspace_dir: str, target_path: str) -> Path:
    """Resolve target_path against workspace_dir and ensure it does not escape the workspace."""
    workspace = Path(workspace_dir).resolve()
    safe_target = target_path.lstrip("/\\")
    resolved = (workspace / safe_target).resolve()

    if not str(resolved).startswith(str(workspace)):
        raise PermissionError(f"Access denied: path '{target_path}' resolves outside workspace '{workspace_dir}'")
    
    return resolved


def get_workspace_tools(workspace_dir: str) -> List[Any]:
    """Return a list of Langchain tools bound to the given workspace directory."""
    
    @tool
    def write_file(file_path: str, content: str) -> str:
        """Write content to a file.
        
        Args:
            file_path: The relative path to the file you want to write.
            content: The text content to write into the file.
        """
        try:
            path = _enforce_workspace(workspace_dir, file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            logger.info(f"Wrote file: {path}")
            return f"Successfully wrote to {file_path}"
        except Exception as e:
            logger.error(f"Failed to write file {file_path}: {e}")
            return f"Error writing file: {e}"

    @tool
    def read_file(file_path: str) -> str:
        """Read content from a file.
        
        Args:
            file_path: The relative path to the file you want to read.
        """
        try:
            path = _enforce_workspace(workspace_dir, file_path)
            if not path.exists():
                return f"Error: File {file_path} does not exist."
            return path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to read file {file_path}: {e}")
            return f"Error reading file: {e}"

    @tool
    def list_directory(dir_path: str = ".") -> str:
        """List files and directories in a given path.
        
        Args:
            dir_path: The relative path to the directory you want to list. Defaults to the root of the workspace.
        """
        try:
            path = _enforce_workspace(workspace_dir, dir_path)
            if not path.exists():
                return f"Error: Directory {dir_path} does not exist."
            if not path.is_dir():
                return f"Error: {dir_path} is not a directory."
            
            items = list(path.iterdir())
            if not items:
                return "Directory is empty."
            
            return "\n".join(f"{'[DIR]' if item.is_dir() else '[FILE]'} {item.name}" for item in items)
        except Exception as e:
            logger.error(f"Failed to list directory {dir_path}: {e}")
            return f"Error listing directory: {e}"

    @tool
    def run_command(command: str) -> str:
        """Run a shell command inside the workspace directory.
        
        Args:
            command: The shell command to run (e.g., 'pytest', 'python main.py').
        """
        import os
        import sys
        try:
            workspace = Path(workspace_dir).resolve()
            logger.info(f"Running command in {workspace}: {command}")
            
            # Ensure a venv exists for isolation
            venv_dir = workspace / ".venv"
            if not venv_dir.exists():
                subprocess.run([sys.executable, "-m", "venv", str(venv_dir), "--system-site-packages"], check=True)
                
            # Prepare environment variables with venv activated
            env = os.environ.copy()
            if os.name == "nt":
                env["PATH"] = f"{venv_dir / 'Scripts'};{env.get('PATH', '')}"
                env["VIRTUAL_ENV"] = str(venv_dir)
            else:
                env["PATH"] = f"{venv_dir / 'bin'}:{env.get('PATH', '')}"
                env["VIRTUAL_ENV"] = str(venv_dir)
            
            result = subprocess.run(
                command,
                cwd=str(workspace),
                shell=True,
                capture_output=True,
                text=True,
                env=env,
                timeout=30
            )
            
            output = []
            if result.stdout:
                output.append(f"STDOUT:\n{result.stdout}")
            if result.stderr:
                output.append(f"STDERR:\n{result.stderr}")
                
            if not output:
                output.append("Command executed successfully with no output.")
                
            output.insert(0, f"Exit code: {result.returncode}")
            return "\n".join(output)
        except subprocess.TimeoutExpired:
            return "Error: Command timed out after 30 seconds."
        except Exception as e:
            logger.error(f"Failed to run command '{command}': {e}")
            return f"Error running command: {e}"

    return [write_file, read_file, list_directory, run_command]
