"""
Browser Control MCP Tool

Provides browser automation capabilities using Botasaurus Driver.
Handles browser lifecycle, navigation, and provides environment for other tools.
"""
from typing import Optional, Dict, Any
from botasaurus_driver import Driver
import asyncio
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class BrowserControlTool:
    """
    MCP Tool for browser control and automation

    Uses Botasaurus Driver for anti-detection and stealth capabilities.
    """

    def __init__(self):
        self.active_sessions: Dict[str, Driver] = {}
        self.session_metadata: Dict[str, Dict[str, Any]] = {}

    async def create_session(
        self,
        session_id: str,
        headless: bool = True,
        user_agent: Optional[str] = None,
        proxy: Optional[str] = None,
        block_images: bool = False
    ) -> Dict[str, Any]:
        """
        Create a new browser session

        Args:
            session_id: Unique identifier for the session
            headless: Run browser without UI
            user_agent: Custom user agent string
            proxy: Proxy configuration
            block_images: Block image loading for speed

        Returns:
            Session information with status and capabilities
        """
        if session_id in self.active_sessions:
            return {
                "success": False,
                "message": f"Session {session_id} already exists"
            }

        try:
            logger.info(f"[BROWSER] Creating session: {session_id}")
            logger.info(f"[BROWSER] Config: headless={headless}, block_images={block_images}")

            # Create Botasaurus Driver instance with correct API
            driver = Driver(
                headless=headless,
                user_agent=user_agent,  # Can be None or string
                proxy=proxy,
                block_images=block_images,
                beep=False,  # Disable beep on completion
            )

            self.active_sessions[session_id] = driver
            self.session_metadata[session_id] = {
                "headless": headless,
                "user_agent": user_agent or "default",
                "proxy": proxy,
                "block_images": block_images,
                "created_at": datetime.utcnow().isoformat()
            }

            logger.info(f"[BROWSER] Session created successfully: {session_id}")

            return {
                "success": True,
                "session_id": session_id,
                "message": "Browser session created",
                "config": self.session_metadata[session_id]
            }

        except Exception as e:
            logger.error(f"[BROWSER] Failed to create session: {str(e)}")
            return {
                "success": False,
                "message": f"Failed to create session: {str(e)}"
            }

    async def navigate(
        self,
        session_id: str,
        url: str,
        wait_for_load: bool = True,
        bypass_cloudflare: bool = False
    ) -> Dict[str, Any]:
        """
        Navigate to a URL in the browser session

        Args:
            session_id: Session identifier
            url: Target URL to navigate to
            wait_for_load: Wait for page load to complete
            bypass_cloudflare: Use Cloudflare bypass techniques

        Returns:
            Navigation result with page title and final URL
        """
        if session_id not in self.active_sessions:
            return {
                "success": False,
                "message": f"Session {session_id} not found"
            }

        try:
            driver = self.active_sessions[session_id]
            logger.info(f"[BROWSER] Navigating to: {url}")

            if bypass_cloudflare:
                logger.info(f"[BROWSER] Using Cloudflare bypass")
                driver.google_get(url, bypass_cloudflare=True)
            else:
                driver.get(url)

            # Brief sleep to ensure page starts loading
            if wait_for_load:
                driver.short_random_sleep()

            logger.info(f"[BROWSER] Navigation complete: {driver.current_url}")

            return {
                "success": True,
                "session_id": session_id,
                "url": driver.current_url,
                "title": driver.title,
                "message": "Navigation successful"
            }

        except Exception as e:
            logger.error(f"[BROWSER] Navigation failed: {str(e)}")
            return {
                "success": False,
                "message": f"Navigation failed: {str(e)}"
            }

    async def screenshot(
        self,
        session_id: str,
        output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Capture screenshot of current page

        Args:
            session_id: Session identifier
            output_path: Optional custom output path

        Returns:
            Screenshot path and metadata
        """
        if session_id not in self.active_sessions:
            return {
                "success": False,
                "message": f"Session {session_id} not found"
            }

        try:
            driver = self.active_sessions[session_id]

            # Save screenshot (Botasaurus saves to output/ by default)
            driver.save_screenshot()

            default_path = f"output/screenshot_{session_id}_{int(datetime.utcnow().timestamp())}.png"

            logger.info(f"[BROWSER] Screenshot saved: {default_path}")

            return {
                "success": True,
                "session_id": session_id,
                "screenshot_path": output_path or default_path,
                "message": "Screenshot captured"
            }

        except Exception as e:
            logger.error(f"[BROWSER] Screenshot failed: {str(e)}")
            return {
                "success": False,
                "message": f"Screenshot failed: {str(e)}"
            }

    async def get_page_source(
        self,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Get HTML source of current page

        Args:
            session_id: Session identifier

        Returns:
            Page HTML source
        """
        if session_id not in self.active_sessions:
            return {
                "success": False,
                "message": f"Session {session_id} not found"
            }

        try:
            driver = self.active_sessions[session_id]
            html = driver.page_html

            logger.info(f"[BROWSER] Retrieved page source: {len(html)} characters")

            return {
                "success": True,
                "session_id": session_id,
                "html": html,
                "url": driver.current_url,
                "title": driver.title,
                "message": "Page source retrieved"
            }

        except Exception as e:
            logger.error(f"[BROWSER] Failed to get page source: {str(e)}")
            return {
                "success": False,
                "message": f"Failed to get page source: {str(e)}"
            }

    async def execute_script(
        self,
        session_id: str,
        script: str
    ) -> Dict[str, Any]:
        """
        Execute JavaScript in browser context

        Args:
            session_id: Session identifier
            script: JavaScript code to execute

        Returns:
            Script execution result
        """
        if session_id not in self.active_sessions:
            return {
                "success": False,
                "message": f"Session {session_id} not found"
            }

        try:
            driver = self.active_sessions[session_id]
            result = driver.run_js(script)

            logger.info(f"[BROWSER] JavaScript executed successfully")

            return {
                "success": True,
                "session_id": session_id,
                "result": result,
                "message": "Script executed"
            }

        except Exception as e:
            logger.error(f"[BROWSER] Script execution failed: {str(e)}")
            return {
                "success": False,
                "message": f"Script execution failed: {str(e)}"
            }

    async def close_session(
        self,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Close and cleanup browser session

        Args:
            session_id: Session identifier

        Returns:
            Cleanup status
        """
        if session_id not in self.active_sessions:
            return {
                "success": False,
                "message": f"Session {session_id} not found"
            }

        try:
            driver = self.active_sessions[session_id]
            driver.close()

            # Cleanup
            del self.active_sessions[session_id]
            del self.session_metadata[session_id]

            logger.info(f"[BROWSER] Session closed: {session_id}")

            return {
                "success": True,
                "session_id": session_id,
                "message": "Browser session closed"
            }

        except Exception as e:
            logger.error(f"[BROWSER] Failed to close session: {str(e)}")
            return {
                "success": False,
                "message": f"Failed to close session: {str(e)}"
            }

    async def check_bot_detection(
        self,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Check if bot detection is present on current page

        Uses Botasaurus built-in detection methods.

        Args:
            session_id: Session identifier

        Returns:
            Detection status and details
        """
        if session_id not in self.active_sessions:
            return {
                "success": False,
                "message": f"Session {session_id} not found"
            }

        try:
            driver = self.active_sessions[session_id]

            # Check for common bot detection indicators
            is_detected = driver.is_bot_detected()

            logger.info(f"[BROWSER] Bot detection check: {is_detected}")

            return {
                "success": True,
                "session_id": session_id,
                "is_detected": is_detected,
                "message": "Bot detection checked"
            }

        except Exception as e:
            logger.error(f"[BROWSER] Bot detection check failed: {str(e)}")
            return {
                "success": False,
                "message": f"Bot detection check failed: {str(e)}"
            }
