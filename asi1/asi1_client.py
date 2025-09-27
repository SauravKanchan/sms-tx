"""ASI1 AI API client for converting human language to structured JSON."""
import json
import uuid
import os
import requests
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ASI1Client:
    """Client for interacting with ASI1 AI API."""

    def __init__(self):
        """Initialize ASI1 client with API key from environment."""
        self.api_key = os.getenv('ASI_ONE_API_KEY')
        if not self.api_key:
            raise ValueError("ASI_ONE_API_KEY environment variable is required")

        self.base_url = "https://api.asi1.ai/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def extract_intent(self, user_message: str, system_prompt: str) -> Dict[str, Any]:
        """
        Extract structured intent from user message using ASI1 AI.

        Args:
            user_message: The human language message to parse
            system_prompt: The system prompt with parsing instructions

        Returns:
            Dict containing the parsed intent or error information
        """
        try:
            # Generate unique session ID
            session_id = str(uuid.uuid4())

            # Prepare headers with session ID
            headers = self.headers.copy()
            headers["x-session-id"] = session_id

            # Prepare request payload
            payload = {
                "model": "asi1-mini",
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": user_message
                    }
                ],
                "temperature": 0,
                "web_search": False,
                "stream": False
            }

            logger.info(f"Sending request to ASI1 API with session {session_id}")

            # Make API request
            response = requests.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=30
            )

            # Check response status
            if response.status_code != 200:
                logger.error(f"ASI1 API returned status {response.status_code}: {response.text}")
                return {
                    "success": False,
                    "error": f"ASI1 API error: {response.status_code}"
                }

            # Parse response
            response_data = response.json()

            # Extract content from response
            if "choices" not in response_data or not response_data["choices"]:
                logger.error("Invalid response format from ASI1 API")
                return {
                    "success": False,
                    "error": "Invalid response format from ASI1 API"
                }

            content = response_data["choices"][0]["message"]["content"]

            # Parse the JSON content
            try:
                parsed_intent = json.loads(content)
                logger.info(f"Successfully parsed intent: {parsed_intent}")
                return {
                    "success": True,
                    "intent": parsed_intent
                }
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON from ASI1 response: {content}")
                return {
                    "success": False,
                    "error": f"Invalid JSON in ASI1 response: {str(e)}"
                }

        except requests.exceptions.Timeout:
            logger.error("ASI1 API request timed out")
            return {
                "success": False,
                "error": "ASI1 API request timed out"
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"ASI1 API request failed: {str(e)}")
            return {
                "success": False,
                "error": f"ASI1 API request failed: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Unexpected error in ASI1 client: {str(e)}")
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}"
            }

def load_prompt_template() -> str:
    """Load the system prompt template from asi1/prompt.json."""
    try:
        prompt_path = os.path.join(os.path.dirname(__file__), 'prompt.json')
        with open(prompt_path, 'r') as f:
            prompt_data = json.load(f)

        # Extract system message content
        for message in prompt_data["messages"]:
            if message["role"] == "system":
                return message["content"]

        raise ValueError("System message not found in prompt.json")
    except Exception as e:
        logger.error(f"Failed to load prompt template: {str(e)}")
        raise