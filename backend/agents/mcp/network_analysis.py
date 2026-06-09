"""
Network Analysis MCP Tool

Monitors network traffic during page loads using Chrome DevTools Protocol (CDP).
Captures API calls, detects cryptography, and exports HAR data.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
import json


class NetworkAnalysisTool:
    """
    MCP Tool for network traffic analysis

    Uses CDP to monitor HTTP requests, responses, and detect API patterns.
    """

    def __init__(self):
        self.network_logs: Dict[str, List[Dict[str, Any]]] = {}
        self.active_monitors: Dict[str, bool] = {}

    async def start_monitoring(
        self,
        session_id: str,
        filter_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Start monitoring network traffic for a session

        Args:
            session_id: Browser session identifier
            filter_types: Optional list of resource types to capture
                         (e.g., ["xhr", "fetch", "document"])

        Returns:
            Monitoring status
        """
        self.network_logs[session_id] = []
        self.active_monitors[session_id] = True

        return {
            "success": True,
            "session_id": session_id,
            "filter_types": filter_types or ["all"],
            "message": "Network monitoring started"
        }

    async def stop_monitoring(
        self,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Stop monitoring network traffic

        Args:
            session_id: Browser session identifier

        Returns:
            Summary of captured traffic
        """
        if session_id not in self.active_monitors:
            return {
                "success": False,
                "message": f"No active monitoring for session {session_id}"
            }

        self.active_monitors[session_id] = False
        captured_count = len(self.network_logs.get(session_id, []))

        return {
            "success": True,
            "session_id": session_id,
            "captured_requests": captured_count,
            "message": "Network monitoring stopped"
        }

    async def get_api_calls(
        self,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Extract API calls (XHR/Fetch) from captured traffic

        Args:
            session_id: Browser session identifier

        Returns:
            List of API calls with URLs, methods, and responses
        """
        if session_id not in self.network_logs:
            return {
                "success": False,
                "message": f"No network logs for session {session_id}"
            }

        # Filter for XHR and Fetch requests
        api_calls = [
            log for log in self.network_logs[session_id]
            if log.get("type") in ["xhr", "fetch"]
        ]

        return {
            "success": True,
            "session_id": session_id,
            "api_calls": api_calls,
            "count": len(api_calls)
        }

    async def detect_data_endpoints(
        self,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Analyze network traffic to detect potential data endpoints

        Looks for JSON responses and structured data patterns.

        Args:
            session_id: Browser session identifier

        Returns:
            List of detected data endpoints with analysis
        """
        if session_id not in self.network_logs:
            return {
                "success": False,
                "message": f"No network logs for session {session_id}"
            }

        data_endpoints = []

        for log in self.network_logs[session_id]:
            # Check if response appears to be JSON
            content_type = log.get("response_headers", {}).get("content-type", "")
            if "application/json" in content_type:
                data_endpoints.append({
                    "url": log.get("url"),
                    "method": log.get("method"),
                    "status": log.get("status"),
                    "response_type": "json",
                    "size": log.get("response_size", 0)
                })

        return {
            "success": True,
            "session_id": session_id,
            "data_endpoints": data_endpoints,
            "count": len(data_endpoints)
        }

    async def export_har(
        self,
        session_id: str,
        output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Export network logs as HAR (HTTP Archive) format

        Args:
            session_id: Browser session identifier
            output_path: Optional custom output path

        Returns:
            HAR file path and summary
        """
        if session_id not in self.network_logs:
            return {
                "success": False,
                "message": f"No network logs for session {session_id}"
            }

        # Build HAR structure
        har = {
            "log": {
                "version": "1.2",
                "creator": {
                    "name": "Cradler Network Analyzer",
                    "version": "1.0"
                },
                "entries": self.network_logs[session_id]
            }
        }

        default_path = f"output/network_{session_id}_{int(datetime.utcnow().timestamp())}.har"
        path = output_path or default_path

        return {
            "success": True,
            "session_id": session_id,
            "har_path": path,
            "entry_count": len(self.network_logs[session_id]),
            "har_data": har
        }

    async def detect_pagination(
        self,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Analyze network traffic to detect pagination patterns

        Looks for page/offset parameters and sequential API calls.

        Args:
            session_id: Browser session identifier

        Returns:
            Detected pagination patterns
        """
        if session_id not in self.network_logs:
            return {
                "success": False,
                "message": f"No network logs for session {session_id}"
            }

        pagination_patterns = []

        # Look for common pagination parameters
        pagination_params = ["page", "offset", "limit", "cursor", "next", "start"]

        for log in self.network_logs[session_id]:
            url = log.get("url", "")
            for param in pagination_params:
                if f"{param}=" in url.lower():
                    pagination_patterns.append({
                        "url": url,
                        "parameter": param,
                        "method": log.get("method")
                    })
                    break

        return {
            "success": True,
            "session_id": session_id,
            "pagination_detected": len(pagination_patterns) > 0,
            "patterns": pagination_patterns
        }

    async def log_request(
        self,
        session_id: str,
        request_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Log a network request (called by CDP event handler)

        Args:
            session_id: Browser session identifier
            request_data: Request information from CDP

        Returns:
            Logging status
        """
        if session_id not in self.network_logs:
            self.network_logs[session_id] = []

        self.network_logs[session_id].append({
            "timestamp": datetime.utcnow().isoformat(),
            **request_data
        })

        return {
            "success": True,
            "session_id": session_id,
            "logged": True
        }

    async def clear_logs(
        self,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Clear network logs for a session

        Args:
            session_id: Browser session identifier

        Returns:
            Clear status
        """
        if session_id in self.network_logs:
            del self.network_logs[session_id]

        if session_id in self.active_monitors:
            del self.active_monitors[session_id]

        return {
            "success": True,
            "session_id": session_id,
            "message": "Network logs cleared"
        }
