"""
File System MCP Tool

Handles scraper script creation and management with directory isolation (Level 3).
Ensures agents can only operate within designated scraper directories.
"""
from typing import Dict, Any, Optional
from pathlib import Path
import os
import subprocess
import uuid


class FileSystemTool:
    """
    MCP Tool for file system operations with security isolation

    Implements Level 3 directory isolation - agents can only access
    files within their designated scraper project directories.
    """

    def __init__(self, base_scrapers_dir: str = "scrapers"):
        self.base_dir = Path(base_scrapers_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_scraper_dir(self, user_id: str, scraper_id: str) -> Path:
        """Get isolated directory path for a scraper"""
        return self.base_dir / user_id / scraper_id

    def _validate_path(self, path: Path, allowed_dir: Path) -> bool:
        """Validate that path is within allowed directory"""
        try:
            path_resolved = path.resolve()
            allowed_resolved = allowed_dir.resolve()
            return str(path_resolved).startswith(str(allowed_resolved))
        except Exception:
            return False

    async def create_scraper_directory(
        self,
        user_id: str,
        scraper_id: str
    ) -> Dict[str, Any]:
        """
        Create isolated directory for a scraper

        Args:
            user_id: User identifier
            scraper_id: Scraper identifier

        Returns:
            Directory creation status and path
        """
        try:
            scraper_dir = self._get_scraper_dir(user_id, scraper_id)
            scraper_dir.mkdir(parents=True, exist_ok=True)

            # Create subdirectories
            (scraper_dir / "output").mkdir(exist_ok=True)
            (scraper_dir / "logs").mkdir(exist_ok=True)

            return {
                "success": True,
                "scraper_id": scraper_id,
                "directory": str(scraper_dir),
                "message": "Scraper directory created"
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to create directory: {str(e)}"
            }

    async def write_scraper_script(
        self,
        user_id: str,
        scraper_id: str,
        script_name: str,
        script_content: str
    ) -> Dict[str, Any]:
        """
        Write scraper script to isolated directory

        Args:
            user_id: User identifier
            scraper_id: Scraper identifier
            script_name: Name of the script file
            script_content: Python code content

        Returns:
            Write status and file path
        """
        scraper_dir = self._get_scraper_dir(user_id, scraper_id)

        # Ensure scraper_dir exists
        if not scraper_dir.exists():
            await self.create_scraper_directory(user_id, scraper_id)

        # Validate file name (prevent directory traversal)
        if ".." in script_name or "/" in script_name or "\\" in script_name:
            return {
                "success": False,
                "message": "Invalid script name"
            }

        script_path = scraper_dir / script_name

        # Validate path is within allowed directory
        if not self._validate_path(script_path, scraper_dir):
            return {
                "success": False,
                "message": "Path traversal detected"
            }

        try:
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(script_content)

            return {
                "success": True,
                "scraper_id": scraper_id,
                "file_path": str(script_path),
                "file_size": len(script_content),
                "message": "Script written successfully"
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to write script: {str(e)}"
            }

    async def read_scraper_script(
        self,
        user_id: str,
        scraper_id: str,
        script_name: str
    ) -> Dict[str, Any]:
        """
        Read scraper script from isolated directory

        Args:
            user_id: User identifier
            scraper_id: Scraper identifier
            script_name: Name of the script file

        Returns:
            Script content
        """
        scraper_dir = self._get_scraper_dir(user_id, scraper_id)
        script_path = scraper_dir / script_name

        # Validate path
        if not self._validate_path(script_path, scraper_dir):
            return {
                "success": False,
                "message": "Path traversal detected"
            }

        if not script_path.exists():
            return {
                "success": False,
                "message": f"Script {script_name} not found"
            }

        try:
            with open(script_path, 'r', encoding='utf-8') as f:
                content = f.read()

            return {
                "success": True,
                "scraper_id": scraper_id,
                "file_path": str(script_path),
                "content": content,
                "file_size": len(content)
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to read script: {str(e)}"
            }

    async def execute_scraper(
        self,
        user_id: str,
        scraper_id: str,
        script_name: str,
        timeout: int = 300
    ) -> Dict[str, Any]:
        """
        Execute scraper script in isolated environment

        Args:
            user_id: User identifier
            scraper_id: Scraper identifier
            script_name: Name of the script file
            timeout: Execution timeout in seconds

        Returns:
            Execution results (stdout, stderr, return code)
        """
        scraper_dir = self._get_scraper_dir(user_id, scraper_id)
        script_path = scraper_dir / script_name

        # Validate path
        if not self._validate_path(script_path, scraper_dir):
            return {
                "success": False,
                "message": "Path traversal detected"
            }

        if not script_path.exists():
            return {
                "success": False,
                "message": f"Script {script_name} not found"
            }

        try:
            # Execute with timeout and capture output
            result = subprocess.run(
                ["python", str(script_path)],
                cwd=str(scraper_dir),
                capture_output=True,
                text=True,
                timeout=timeout
            )

            return {
                "success": result.returncode == 0,
                "scraper_id": scraper_id,
                "script_name": script_name,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.returncode,
                "message": "Execution completed" if result.returncode == 0 else "Execution failed"
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "message": f"Execution timeout after {timeout} seconds"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Execution error: {str(e)}"
            }

    async def list_files(
        self,
        user_id: str,
        scraper_id: str,
        subdirectory: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List files in scraper directory

        Args:
            user_id: User identifier
            scraper_id: Scraper identifier
            subdirectory: Optional subdirectory to list

        Returns:
            List of files with metadata
        """
        scraper_dir = self._get_scraper_dir(user_id, scraper_id)

        if subdirectory:
            target_dir = scraper_dir / subdirectory
        else:
            target_dir = scraper_dir

        # Validate path
        if not self._validate_path(target_dir, scraper_dir):
            return {
                "success": False,
                "message": "Path traversal detected"
            }

        if not target_dir.exists():
            return {
                "success": False,
                "message": "Directory not found"
            }

        try:
            files = []
            for item in target_dir.iterdir():
                files.append({
                    "name": item.name,
                    "type": "directory" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else 0,
                    "modified": item.stat().st_mtime
                })

            return {
                "success": True,
                "scraper_id": scraper_id,
                "directory": str(target_dir),
                "files": files,
                "count": len(files)
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to list files: {str(e)}"
            }

    async def delete_scraper_directory(
        self,
        user_id: str,
        scraper_id: str
    ) -> Dict[str, Any]:
        """
        Delete entire scraper directory

        Args:
            user_id: User identifier
            scraper_id: Scraper identifier

        Returns:
            Deletion status
        """
        scraper_dir = self._get_scraper_dir(user_id, scraper_id)

        if not scraper_dir.exists():
            return {
                "success": True,
                "message": "Directory already deleted or doesn't exist"
            }

        try:
            import shutil
            shutil.rmtree(scraper_dir)

            return {
                "success": True,
                "scraper_id": scraper_id,
                "message": "Scraper directory deleted"
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to delete directory: {str(e)}"
            }
