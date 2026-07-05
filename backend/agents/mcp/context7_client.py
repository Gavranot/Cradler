"""
Context7 MCP Client

Connects to Context7 MCP server for up-to-date library documentation.
No API key required - Context7 is free and open source.

Implements proper MCP HTTP transport protocol with session management.
"""
import httpx
import json
import logging
from typing import Dict, Any, Optional
from core.config import settings

logger = logging.getLogger(__name__)


class Context7Client:
    """
    Client for Context7 MCP documentation service

    Context7 fetches up-to-date documentation from official sources,
    eliminating the problem of AI agents using outdated APIs.

    This client implements the MCP HTTP transport protocol specification.
    """

    MCP_PROTOCOL_VERSION = "2025-06-18"

    def __init__(self, host: Optional[str] = None):
        """
        Initialize Context7 client

        Args:
            host: Context7 server host (defaults to settings.CONTEXT7_HOST)
        """
        self.host = host or settings.CONTEXT7_HOST
        self.base_url = f"http://{self.host}/mcp"
        self.session_id: Optional[str] = None
        self._request_id = 0
        logger.info(f"Context7 client initialized with host: {self.host}")

    def _get_next_request_id(self) -> int:
        """Generate unique request ID for JSON-RPC"""
        self._request_id += 1
        return self._request_id

    def _get_headers(self) -> Dict[str, str]:
        """Get HTTP headers for MCP protocol"""
        headers = {
            "MCP-Protocol-Version": self.MCP_PROTOCOL_VERSION,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }

        # Include session ID if we have one
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id

        return headers

    @staticmethod
    def _parse_mcp_response(response) -> Dict[str, Any]:
        """Parse an MCP HTTP response that may be plain JSON or SSE-framed.

        With `Accept: application/json, text/event-stream` (required to avoid
        406), the server is free to answer either way — Context7 2.3.0 streams
        SSE (`event: message\\ndata: {...}`) at least for `initialize`, which
        made a bare response.json() raise mid-handshake. Take the last `data:`
        payload of an SSE body; fall through to .json() otherwise.
        """
        content_type = response.headers.get("content-type", "")
        body = response.text
        if "text/event-stream" in content_type or body.lstrip().startswith(("event:", "data:")):
            last_data = None
            for line in body.splitlines():
                if line.startswith("data:"):
                    last_data = line[len("data:"):].strip()
            if last_data:
                import json as _json
                return _json.loads(last_data)
            raise ValueError("SSE response contained no data frames")
        return response.json()

    async def _ensure_initialized(self) -> None:
        """Ensure MCP session is initialized"""
        if self.session_id is None:
            await self._initialize()

    async def _initialize(self) -> Dict[str, Any]:
        """
        Initialize MCP connection and establish session

        Returns:
            Initialization result from server
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                payload = {
                    "jsonrpc": "2.0",
                    "id": self._get_next_request_id(),
                    "method": "initialize",
                    "params": {
                        "protocolVersion": self.MCP_PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": {
                            "name": "cradler-context7-client",
                            "version": "1.0.0"
                        }
                    }
                }

                logger.info(f"Initializing MCP session with {self.base_url}")
                response = await client.post(
                    self.base_url,
                    json=payload,
                    headers=self._get_headers()
                )

                # Extract session ID from headers
                session_id = response.headers.get("Mcp-Session-Id")
                if session_id:
                    self.session_id = session_id
                    logger.info(f"MCP session established: {session_id}")

                response.raise_for_status()
                result = self._parse_mcp_response(response)

                logger.info(f"Context7 server capabilities: {result.get('result', {}).get('capabilities', {})}")
                return result

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            logger.error(f"MCP initialization failed: {error_msg}")
            raise Exception(error_msg)
        except httpx.ConnectError:
            error_msg = f"Cannot connect to Context7 service at {self.base_url}"
            logger.error(error_msg)
            raise Exception(error_msg)
        except Exception as e:
            logger.error(f"MCP initialization error: {e}")
            raise

    async def _call_mcp_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Call an MCP tool using proper JSON-RPC 2.0 format

        Args:
            tool_name: Name of the MCP tool
            arguments: Tool arguments

        Returns:
            Tool result dictionary
        """
        try:
            # Ensure we have a session
            await self._ensure_initialized()

            async with httpx.AsyncClient(timeout=60.0) as client:
                # JSON-RPC 2.0 tool call format
                payload = {
                    "jsonrpc": "2.0",
                    "id": self._get_next_request_id(),
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": arguments
                    }
                }

                logger.info(f"Calling MCP tool: {tool_name} with args: {arguments}")
                response = await client.post(
                    self.base_url,
                    json=payload,
                    headers=self._get_headers()
                )

                # Handle HTTP errors
                if response.status_code == 404:
                    # Session expired or invalid
                    logger.warning("Session expired (404), reinitializing...")
                    self.session_id = None
                    await self._ensure_initialized()
                    # Retry the call
                    return await self._call_mcp_tool(tool_name, arguments)

                response.raise_for_status()
                result = self._parse_mcp_response(response)

                # Extract result from JSON-RPC response
                if "error" in result:
                    error = result["error"]
                    logger.error(f"MCP tool error: {error}")
                    return {
                        "success": False,
                        "message": f"Tool error: {error.get('message', 'Unknown error')}"
                    }

                # Return the tool result
                tool_result = result.get("result", {})
                logger.info(f"Tool {tool_name} executed successfully")
                return tool_result

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            logger.error(f"Tool call failed: {error_msg}")
            return {
                "success": False,
                "message": error_msg
            }
        except httpx.ConnectError:
            error_msg = f"Cannot connect to Context7 service at {self.base_url}"
            logger.error(error_msg)
            return {
                "success": False,
                "message": error_msg
            }
        except Exception as e:
            logger.error(f"Tool call error: {e}")
            return {
                "success": False,
                "message": f"Unexpected error: {str(e)}"
            }

    async def resolve_library_id(self, library_name: str) -> Dict[str, Any]:
        """
        Resolve a library name to Context7-compatible library ID

        Args:
            library_name: Name of the library (e.g., "Botasaurus", "BeautifulSoup")

        Returns:
            {
                "success": bool,
                "library_id": str,  # e.g., "/omkarcloud/botasaurus"
                "matches": list,     # All matching libraries
                "message": str       # Error message if failed
            }
        """
        logger.info(f"Resolving library ID for: {library_name}")

        result = await self._call_mcp_tool(
            "resolve-library-id",
            {"libraryName": library_name}
        )

        # Transform result to expected format
        if result.get("content"):
            # MCP tools return results in content array
            content = result["content"][0]
            if content.get("type") == "text":
                text = content["text"]

                # Context7 returns formatted text, not JSON
                # Extract library ID from the first match
                # Format: "- Context7-compatible library ID: /org/project"
                import re
                match = re.search(r'Context7-compatible library ID:\s*(/[\w-]+/[\w-]+)', text)

                if match:
                    library_id = match.group(1)
                    logger.info(f"Resolved {library_name} to {library_id}")

                    # Extract all matches for reference
                    matches = re.findall(
                        r'-\s*Title:\s*(.+?)\n-\s*Context7-compatible library ID:\s*(/[\w/-]+)',
                        text,
                        re.MULTILINE
                    )

                    return {
                        "success": True,
                        "library_id": library_id,
                        "matches": [{"title": m[0], "id": m[1]} for m in matches],
                    }
                else:
                    logger.error(f"Could not find library ID in response: {text[:200]}...")
                    return {
                        "success": False,
                        "message": "Library not found in Context7"
                    }

        return result

    async def get_library_docs(
        self,
        library_id: str,
        topic: Optional[str] = None,
        tokens: int = 8000
    ) -> Dict[str, Any]:
        """
        Fetch up-to-date documentation for a library

        Args:
            library_id: Context7 library ID (e.g., "/omkarcloud/botasaurus")
            topic: Optional specific topic to focus on
            tokens: Maximum tokens of documentation to retrieve

        Returns:
            {
                "success": bool,
                "documentation": str,
                "library_id": str,
                "message": str  # Error message if failed
            }
        """
        logger.info(f"Fetching docs for {library_id} (topic: {topic}, tokens: {tokens})")

        arguments = {
            "context7CompatibleLibraryID": library_id,
            "tokens": tokens
        }

        if topic:
            arguments["topic"] = topic

        result = await self._call_mcp_tool("get-library-docs", arguments)

        # Transform result to expected format
        if result.get("content"):
            content = result["content"][0]
            if content.get("type") == "text":
                doc_text = content["text"]
                logger.info(f"Retrieved {len(doc_text)} characters of documentation for {library_id}")
                return {
                    "success": True,
                    "documentation": doc_text,
                    "library_id": library_id
                }

        logger.error(f"No content in get-library-docs response: {result}")
        return {
            "success": False,
            "message": "No documentation returned from Context7"
        }

    async def get_botasaurus_docs(
        self,
        topic: Optional[str] = None,
        tokens: int = 10000
    ) -> Dict[str, Any]:
        """
        Convenience method to fetch Botasaurus documentation

        Args:
            topic: Optional specific topic (e.g., "decorators", "driver methods")
            tokens: Maximum tokens of documentation to retrieve

        Returns:
            {
                "success": bool,
                "documentation": str,
                "library_id": str,
                "message": str  # Error message if failed
            }
        """
        logger.info(f"Fetching Botasaurus docs (topic: {topic})")

        # First resolve the library ID
        resolution = await self.resolve_library_id("Botasaurus")

        if not resolution.get("success"):
            logger.error(f"Failed to resolve Botasaurus: {resolution.get('message')}")
            return {
                "success": False,
                "message": f"Failed to resolve Botasaurus library ID: {resolution.get('message')}"
            }

        library_id = resolution.get("library_id")
        if not library_id:
            return {
                "success": False,
                "message": "Botasaurus library ID not found"
            }

        logger.info(f"Resolved Botasaurus to: {library_id}")

        # Fetch the documentation
        return await self.get_library_docs(
            library_id=library_id,
            topic=topic,
            tokens=tokens
        )

    async def health_check(self) -> bool:
        """
        Check if Context7 service is reachable

        Returns:
            True if service is healthy, False otherwise
        """
        try:
            await self._initialize()
            return self.session_id is not None
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
