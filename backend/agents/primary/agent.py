"""
Primary Agent Service

The Primary Agent handles user chat interaction and requirements gathering.
It parses user intent, validates URLs, and generates structured requirements.

Uses ReAct (Reasoning + Acting) combined with Plan and Execute methodology.
"""
import httpx
import json
from typing import List, Dict, Optional, Any
from datetime import datetime
from urllib.parse import urlparse
import urllib.robotparser
import logging
from core.config import settings
logger = logging.getLogger(__name__)

class PrimaryAgent:
    """
    Primary Agent for handling user conversations and scraper requirements
    """

    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.api_base = "https://openrouter.ai/api/v1"
        self.model = settings.PRIMARY_AGENT_MODEL

        # System prompt for the Primary Agent
        self.system_prompt = """You are Cradler's AI assistant, specialized in helping users create custom web scrapers through conversation.

Your role is to gather information and create scrapers for users through a structured conversation:

**Step 1: Understand the Request**
- Listen to what the user wants to scrape
- Identify if they mentioned a website URL

**Step 2: Gather Required Information**
You MUST collect these details before creating a scraper:
1. **Target URL**: The specific page to scrape (e.g., https://example.com/products)
2. **Scraper Name**: A descriptive name (e.g., "Amazon Electronics Scraper")
3. **Data Fields**: What data they want (e.g., product titles, prices, images, reviews, stock status)
4. **Frequency**: How often to scrape (daily, weekly, on-demand)

**Step 3: Validate the URL**
Once you have a URL, use the `validate_url` function to check:
- URL is valid and accessible
- robots.txt allows scraping

**Step 4: Summarize & Confirm**
Present a clear summary of the requirements:
- Target website and URL
- Data fields to extract
- Scraping schedule
- Any special considerations

Ask the user: "Does this look correct? Should I create this scraper?"

**Step 5: Create the Scraper**
When the user confirms, use the `create_scraper` function with all the gathered information.

**Important Guidelines:**
- Be conversational and friendly, not robotic
- Ask one or two questions at a time, don't overwhelm users
- For e-commerce sites, suggest common fields: title, price, images, reviews, availability
- If URL validation shows robots.txt restrictions, inform the user but explain we use ethical scraping practices
- Never create a scraper without explicit user confirmation

**Example Conversation Flow:**
User: "I want to scrape product data from Amazon"
You: "Great! I can help you create a scraper for Amazon. Could you share the specific Amazon page URL you'd like to scrape? For example, a category page or search results page."
User: "https://amazon.com/s?k=laptops"
You: *validate_url* "Perfect! What product information would you like to extract? Common fields include product title, price, ratings, and images."
User: "Title, price, and rating"
You: "Excellent! How often would you like to run this scraper? Options include daily, weekly, or on-demand."
User: "Daily"
You: "Great! Here's what I have:
- Scraper Name: Amazon Laptops Scraper
- Target URL: https://amazon.com/s?k=laptops
- Data Fields: Title, Price, Rating
- Schedule: Daily

Should I create this scraper for you?"
User: "Yes"
You: *create_scraper* "Your scraper has been created successfully! ..."
"""

        # Tool definitions for function calling
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "validate_url",
                    "description": "Validate a target URL and check if it allows scraping via robots.txt",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "The target URL to validate (must include http:// or https://)"
                            }
                        },
                        "required": ["url"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_scraper",
                    "description": "Create a new scraper after gathering all required information and receiving user confirmation",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "A descriptive name for the scraper"
                            },
                            "target_url": {
                                "type": "string",
                                "description": "The URL to scrape"
                            },
                            "data_fields": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of data fields to extract (e.g., ['title', 'price', 'image'])"
                            },
                            "schedule": {
                                "type": "string",
                                "description": "Scraping frequency (e.g., 'daily', 'weekly', 'on-demand')"
                            },
                            "special_requirements": {
                                "type": "string",
                                "description": "Any special requirements (authentication, pagination, etc.)"
                            }
                        },
                        "required": ["name", "target_url", "data_fields", "schedule"]
                    }
                }
            }
        ]

    async def process_message(
        self,
        user_message: str,
        conversation_history: List[Dict[str, str]],
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process a user message and generate a response using OpenRouter with function calling

        Args:
            user_message: The user's message
            conversation_history: List of previous messages [{role, content, timestamp}]
            session_id: Chat session ID for linking scrapers

        Returns:
            Dict containing:
            - message: The AI's response message
            - scraper_created: Optional scraper data if one was created
            - tool_calls: List of tool calls made during processing
        """
        # Build messages array for API call
        messages = []

        # Add conversation history (excluding timestamps for API)
        for msg in conversation_history:
            if msg["role"] in ["user", "assistant", "tool"]:
                message_dict = {
                    "role": msg["role"],
                    "content": msg.get("content", "")
                }
                # Include tool_calls if present (for assistant messages)
                if "tool_calls" in msg:
                    message_dict["tool_calls"] = msg["tool_calls"]
                # Include tool_call_id if present (for tool messages)
                if "tool_call_id" in msg:
                    message_dict["tool_call_id"] = msg["tool_call_id"]
                messages.append(message_dict)

        # Add current user message
        messages.append({
            "role": "user",
            "content": user_message
        })

        scraper_created = None
        tool_calls_made = []
        max_iterations = 5  # Prevent infinite loops

        # Call OpenRouter API with function calling support
        try:
            logger.info(f"[PRIMARY_AGENT] Processing message, history length: {len(conversation_history)}")
            async with httpx.AsyncClient(timeout=60.0) as client:
                for iteration in range(max_iterations):
                    logger.debug(f"[PRIMARY_AGENT] Iteration {iteration + 1}/{max_iterations}")
                    response = await client.post(
                        f"{self.api_base}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                            "HTTP-Referer": "https://cradler.ai",
                            "X-Title": "Cradler"
                        },
                        json={
                            "model": self.model,
                            "messages": [
                                {"role": "system", "content": self.system_prompt},
                                *messages
                            ],
                            "tools": self.tools,
                            "tool_choice": "auto",
                            "temperature": 0.7,
                            "max_tokens": 2000
                        }
                    )

                    response.raise_for_status()
                    data = response.json()

                    assistant_message = data["choices"][0]["message"]

                    # Check if there are tool calls
                    if assistant_message.get("tool_calls"):
                        # Add assistant's message with tool calls to history
                        logger.info(f"[PRIMARY_AGENT] Agent requested {len(assistant_message['tool_calls'])} tool calls")

                        messages.append({
                            "role": "assistant",
                            "content": assistant_message.get("content") or "",
                            "tool_calls": assistant_message["tool_calls"]
                        })


                        # Execute each tool call
                        for tool_call in assistant_message["tool_calls"]:
                            function_name = tool_call["function"]["name"]
                            function_args = json.loads(tool_call["function"]["arguments"])
                            tool_call_id = tool_call["id"]

                            logger.info(f"[PRIMARY_AGENT] Executing tool: {function_name} with args: {function_args}")

                            # Execute the tool
                            if function_name == "validate_url":
                                result = await self.validate_url(function_args["url"])
                                tool_result = json.dumps(result)
                            elif function_name == "create_scraper":
                                # Create scraper and store result
                                result = await self._create_scraper_internal(
                                    function_args,
                                    session_id
                                )
                                logger.info(f"Create scraper result: {result}")

                                scraper_created = result
                                tool_result = json.dumps({
                                    "success": True,
                                    "message": f"Scraper '{result['name']}' has been created and will be generated by the Secondary Agent. The user will receive the scraper ID once it's saved."
                                })
                            else:
                                tool_result = json.dumps({"error": "Unknown function"})

                            # Add tool result to messages
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call_id,
                                "content": tool_result
                            })

                            tool_calls_made.append({
                                "function": function_name,
                                "arguments": function_args,
                                "result": tool_result
                            })

                        # Continue the loop to get the final response
                        continue
                    else:
                        # No tool calls, we have the final response
                        logger.info(f"[PRIMARY_AGENT] Final response generated, scraper_created: {scraper_created is not None}")
                        return {
                            "message": assistant_message.get("content", ""),
                            "scraper_created": scraper_created,
                            "tool_calls": tool_calls_made
                        }

                # If we hit max iterations
                return {
                    "message": "I apologize, but I'm having trouble processing your request. Could you try rephrasing?",
                    "scraper_created": scraper_created,
                    "tool_calls": tool_calls_made
                }

        except httpx.HTTPError as e:
            raise Exception(f"OpenRouter API error: {str(e)}")
        except Exception as e:
            raise Exception(f"Agent processing error: {str(e)}")

    async def validate_url(self, url: str) -> Dict[str, Any]:
        """
        Validate a target URL and check robots.txt compliance

        Args:
            url: The URL to validate

        Returns:
            Dict with validation results: {valid, domain, allows_scraping, message}
        """
        try:
            # Parse URL
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return {
                    "valid": False,
                    "domain": None,
                    "allows_scraping": False,
                    "message": "Invalid URL format. Please provide a complete URL with http:// or https://"
                }

            domain = parsed.netloc

            # Check robots.txt
            robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
            allows_scraping = await self._check_robots_txt(robots_url, url)

            return {
                "valid": True,
                "domain": domain,
                "allows_scraping": allows_scraping,
                "message": "URL is valid" if allows_scraping else "URL is valid but robots.txt may restrict scraping"
            }

        except Exception as e:
            return {
                "valid": False,
                "domain": None,
                "allows_scraping": False,
                "message": f"Error validating URL: {str(e)}"
            }

    async def _check_robots_txt(self, robots_url: str, target_url: str) -> bool:
        """
        Check if robots.txt allows scraping the target URL

        Args:
            robots_url: URL to robots.txt file
            target_url: The target URL to check

        Returns:
            True if scraping is allowed, False otherwise
        """
        try:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(robots_url)

            async with httpx.AsyncClient(timeout=10.0) as client:
                try:
                    response = await client.get(robots_url)
                    if response.status_code == 200:
                        # Parse robots.txt content
                        rp.parse(response.text.splitlines())
                        # Check if our user agent can fetch the target URL
                        return rp.can_fetch("Cradler-Bot", target_url)
                    else:
                        # No robots.txt found, assume allowed
                        return True
                except httpx.HTTPError:
                    # If robots.txt doesn't exist, assume allowed
                    return True

        except Exception:
            # On error, assume allowed (conservative approach)
            return True

    async def _create_scraper_internal(
        self,
        scraper_data: Dict[str, Any],
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Internal method to create a scraper

        This is called by the agent when it uses the create_scraper tool.
        It returns scraper data without creating the actual database record,
        as that will be handled by the chat endpoint.

        Args:
            scraper_data: Scraper configuration from tool call
            session_id: Optional chat session ID

        Returns:
            Dict with scraper information to be created
        """
        # Convert schedule to cron expression
        schedule_map = {
            "daily": "0 0 * * *",
            "weekly": "0 0 * * 0",
            "on-demand": None,
            "hourly": "0 * * * *"
        }

        schedule_cron = schedule_map.get(
            scraper_data["schedule"].lower(),
            None
        )

        # Build scraper configuration
        config = {
            "data_fields": scraper_data["data_fields"],
            "schedule": scraper_data["schedule"],
            "special_requirements": scraper_data.get("special_requirements"),
            "status": "pending_generation",
            "message": "Scraper will be generated by Secondary Agent"
        }

        # Return scraper data to be created
        # The actual database insertion happens in the chat endpoint
        return {
            "name": scraper_data["name"],
            "target_url": scraper_data["target_url"],
            "schedule_cron": schedule_cron,
            "config": config,
            "session_id": session_id
        }

    def extract_requirements(self, conversation_history: List[Dict[str, str]]) -> Optional[Dict]:
        """
        Extract structured requirements from conversation history

        This method is deprecated in favor of function calling.
        The agent now uses the create_scraper tool directly.

        Args:
            conversation_history: Full conversation history

        Returns:
            Dict with extracted requirements or None if insufficient info
        """
        return None
