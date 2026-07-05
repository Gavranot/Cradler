"""
Scraper Executor Service

Executes generated Botasaurus scraping scripts and handles output storage.
"""
import asyncio
import subprocess
import json
import logging
import traceback
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
from uuid import UUID

from core.config import settings
from core.storage import minio_client

logger = logging.getLogger(__name__)


class ExecutionResult:
    """
    Result of scraper execution

    Contains execution metadata, scraped data, and error information.
    """

    def __init__(
        self,
        success: bool,
        records_scraped: int = 0,
        output_url: Optional[str] = None,
        error_message: Optional[str] = None,
        execution_time: float = 0.0,
        stdout: str = "",
        stderr: str = ""
    ):
        self.success = success
        self.records_scraped = records_scraped
        self.output_url = output_url
        self.error_message = error_message
        self.execution_time = execution_time
        self.stdout = stdout
        self.stderr = stderr

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/debugging"""
        return {
            "success": self.success,
            "records_scraped": self.records_scraped,
            "output_url": self.output_url,
            "error_message": self.error_message,
            "execution_time": self.execution_time
        }


class ScraperExecutor:
    """
    Executes generated scraping scripts in isolated subprocesses

    Features:
    - Subprocess isolation with timeout
    - JSON output parsing
    - MinIO storage integration
    - Comprehensive error handling
    - Execution metadata tracking
    """

    def __init__(self, base_scrapers_dir: str = "scrapers"):
        self.base_scrapers_dir = Path(base_scrapers_dir)
        self.timeout = settings.MAX_SCRAPER_EXECUTION_TIME

    def _get_scraper_path(self, user_id: str, scraper_id: str) -> Path:
        """
        Get path to scraper script

        Args:
            user_id: User UUID
            scraper_id: Scraper UUID

        Returns:
            Path to scraper.py file
        """
        return self.base_scrapers_dir / str(user_id) / str(scraper_id) / "scraper.py"

    def _validate_scraper_exists(self, script_path: Path) -> bool:
        """
        Validate that scraper script exists and is readable

        Args:
            script_path: Path to scraper script

        Returns:
            True if valid, False otherwise
        """
        if not script_path.exists():
            logger.error(f"[EXECUTOR] Scraper script not found: {script_path}")
            return False

        if not script_path.is_file():
            logger.error(f"[EXECUTOR] Path is not a file: {script_path}")
            return False

        return True

    def _execute_script(self, script_path: Path) -> tuple[int, str, str, float]:
        """
        Execute scraper script in subprocess

        Args:
            script_path: Path to Python script

        Returns:
            Tuple of (returncode, stdout, stderr, execution_time)

        Raises:
            subprocess.TimeoutExpired: If execution exceeds timeout
        """
        start_time = datetime.utcnow()

        logger.info(f"[EXECUTOR] Executing: python {script_path}")
        logger.info(f"[EXECUTOR] Working directory: {script_path.parent}")
        logger.info(f"[EXECUTOR] Timeout: {self.timeout}s")

        try:
            result = subprocess.run(
                ["python", script_path.name],  # Use just filename since cwd is set to parent dir
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(script_path.parent)
            )

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            logger.info(f"[EXECUTOR] Execution completed in {execution_time:.2f}s")
            logger.info(f"[EXECUTOR] Return code: {result.returncode}")

            return result.returncode, result.stdout, result.stderr, execution_time

        except subprocess.TimeoutExpired as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.error(f"[EXECUTOR] Timeout after {execution_time:.2f}s")

            # Try to get partial output
            stdout = e.stdout.decode('utf-8') if e.stdout else ""
            stderr = e.stderr.decode('utf-8') if e.stderr else ""

            raise subprocess.TimeoutExpired(
                cmd=e.cmd,
                timeout=e.timeout,
                output=stdout,
                stderr=stderr
            )

    def _parse_json_output(self, stdout: str) -> Optional[list]:
        """
        Parse JSON output from scraper stdout

        The generated scrapers print JSON array to stdout.
        This method extracts and parses that JSON.

        Args:
            stdout: Raw stdout from scraper execution

        Returns:
            Parsed list of records, or None if parsing fails
        """
        try:
            # Try to parse entire stdout as JSON
            data = json.loads(stdout)

            if not isinstance(data, list):
                logger.warning(f"[EXECUTOR] JSON output is not a list: {type(data)}")
                # Try to wrap in list
                data = [data]

            return data

        except json.JSONDecodeError as e:
            logger.error(f"[EXECUTOR] JSON parse error: {e}")

            # Try to find JSON in stdout (in case there's other output)
            import re
            json_pattern = r'\[\s*\{.*\}\s*\]'
            match = re.search(json_pattern, stdout, re.DOTALL)

            if match:
                try:
                    data = json.loads(match.group(0))
                    logger.info("[EXECUTOR] Extracted JSON from mixed output")
                    return data
                except json.JSONDecodeError:
                    pass

            logger.error(f"[EXECUTOR] Could not parse JSON from stdout")
            logger.debug(f"[EXECUTOR] Stdout preview: {stdout[:500]}")
            return None

    async def test_scraper(
        self,
        user_id: UUID,
        scraper_id: UUID,
        sample_size: int = 5
    ) -> Dict[str, Any]:
        """
        Execute a scraper once WITHOUT persisting results

        Same subprocess execution as execute_scraper, but no ScrapingRun record
        and no MinIO upload — returns up to sample_size records inline so the
        caller can eyeball output quality.

        Returns:
            Dict matching ScraperTestResponse: success, records_scraped,
            sample_data, errors, execution_time
        """
        logger.info(f"[EXECUTOR] Test run for scraper {scraper_id} (user {user_id})")

        script_path = self._get_scraper_path(str(user_id), str(scraper_id))

        if not self._validate_scraper_exists(script_path):
            return {
                "success": False,
                "records_scraped": 0,
                "sample_data": [],
                "errors": [f"Scraper script not found: {script_path}"],
                "execution_time": 0.0
            }

        try:
            returncode, stdout, stderr, execution_time = await asyncio.to_thread(
                self._execute_script, script_path)
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "records_scraped": 0,
                "sample_data": [],
                "errors": [f"Execution timeout after {self.timeout} seconds"],
                "execution_time": float(self.timeout)
            }
        except Exception as e:
            logger.error(f"[EXECUTOR] Test run failed: {e}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "records_scraped": 0,
                "sample_data": [],
                "errors": [f"Execution failed: {str(e)}"],
                "execution_time": 0.0
            }

        if returncode != 0:
            errors = [f"Scraper exited with code {returncode}"]
            if stderr:
                errors.append(stderr[:500])
            return {
                "success": False,
                "records_scraped": 0,
                "sample_data": [],
                "errors": errors,
                "execution_time": execution_time
            }

        data = self._parse_json_output(stdout)
        if data is None:
            return {
                "success": False,
                "records_scraped": 0,
                "sample_data": [],
                "errors": ["Failed to parse JSON output from scraper"],
                "execution_time": execution_time
            }

        return {
            "success": True,
            "records_scraped": len(data),
            "sample_data": data[:sample_size],
            "errors": [],
            "execution_time": execution_time
        }

    async def execute_scraper(
        self,
        user_id: UUID,
        scraper_id: UUID,
        run_id: UUID
    ) -> ExecutionResult:
        """
        Execute a scraper and store results

        Main execution flow:
        1. Validate scraper script exists
        2. Execute in subprocess with timeout
        3. Parse JSON output
        4. Upload to MinIO
        5. Return execution results

        Args:
            user_id: User UUID
            scraper_id: Scraper UUID
            run_id: ScrapingRun UUID

        Returns:
            ExecutionResult with success status and metadata
        """
        logger.info(f"[EXECUTOR] Starting execution for run {run_id}")
        logger.info(f"[EXECUTOR] User: {user_id}, Scraper: {scraper_id}")

        script_path = self._get_scraper_path(str(user_id), str(scraper_id))

        # Validate script exists
        if not self._validate_scraper_exists(script_path):
            return ExecutionResult(
                success=False,
                error_message=f"Scraper script not found: {script_path}"
            )

        # Execute script off the event loop — subprocess.run blocks for up to
        # self.timeout, and this coroutine runs on uvicorn's loop via
        # BackgroundTasks; calling it inline froze the whole API during a run.
        try:
            returncode, stdout, stderr, execution_time = await asyncio.to_thread(
                self._execute_script, script_path)

            logger.debug(f"[EXECUTOR] Stdout length: {len(stdout)} chars")
            logger.debug(f"[EXECUTOR] Stderr length: {len(stderr)} chars")

            # Check for execution errors
            if returncode != 0:
                error_msg = f"Scraper exited with code {returncode}"
                if stderr:
                    error_msg += f": {stderr[:500]}"

                logger.error(f"[EXECUTOR] {error_msg}")

                return ExecutionResult(
                    success=False,
                    error_message=error_msg,
                    execution_time=execution_time,
                    stdout=stdout[:1000],
                    stderr=stderr[:1000]
                )

            # Parse JSON output
            data = self._parse_json_output(stdout)

            if data is None:
                return ExecutionResult(
                    success=False,
                    error_message="Failed to parse JSON output from scraper",
                    execution_time=execution_time,
                    stdout=stdout[:1000],
                    stderr=stderr[:1000]
                )

            records_count = len(data)
            logger.info(f"[EXECUTOR] Scraped {records_count} records")

            # Upload to MinIO
            try:
                object_name = minio_client.upload_json(
                    run_id=str(run_id),
                    data=data,
                    metadata={
                        "user_id": str(user_id),
                        "scraper_id": str(scraper_id),
                        "execution_time": str(execution_time)
                    }
                )

                # Generate presigned URL
                output_url = minio_client.get_file_url(object_name)

                logger.info(f"[EXECUTOR] Uploaded results to MinIO: {object_name}")

                return ExecutionResult(
                    success=True,
                    records_scraped=records_count,
                    output_url=output_url,
                    execution_time=execution_time,
                    stdout=stdout[:1000],
                    stderr=stderr[:1000]
                )

            except Exception as upload_error:
                logger.error(f"[EXECUTOR] MinIO upload failed: {upload_error}")
                logger.error(traceback.format_exc())

                return ExecutionResult(
                    success=False,
                    error_message=f"Storage upload failed: {str(upload_error)}",
                    execution_time=execution_time,
                    records_scraped=records_count,  # We still got the data
                    stdout=stdout[:1000],
                    stderr=stderr[:1000]
                )

        except subprocess.TimeoutExpired as timeout_error:
            logger.error(f"[EXECUTOR] Execution timeout after {self.timeout}s")

            return ExecutionResult(
                success=False,
                error_message=f"Execution timeout after {self.timeout} seconds",
                execution_time=self.timeout,
                stdout=timeout_error.output[:1000] if timeout_error.output else "",
                stderr=timeout_error.stderr[:1000] if timeout_error.stderr else ""
            )

        except Exception as e:
            logger.error(f"[EXECUTOR] Unexpected error: {e}")
            logger.error(traceback.format_exc())

            return ExecutionResult(
                success=False,
                error_message=f"Execution failed: {str(e)}"
            )


# Global executor instance
scraper_executor = ScraperExecutor()
