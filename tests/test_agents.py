import pytest
from unittest.mock import patch, MagicMock

# Let's define a simple mock agent workflow function to test.
# In a real app, this would be imported from `src.agents.graph` or similar.
def run_agent_workflow(prompt: str) -> str:
    """
    A simple example function that uses configuration and calls OpenAI.
    """
    from src.config import settings
    import requests # or openai/langchain

    if not settings.openai_api_key:
        raise ValueError("OpenAI API key must be configured!")

    # In a real environment, we would invoke OpenAI API:
    # response = client.chat.completions.create(model="gpt-4o", messages=[...])
    
    # For demonstration, we simulate an API call using requests:
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers=headers,
        json={
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": prompt}]
        }
    )
    
    if response.status_code == 200:
        return response.json()["choices"][0]["message"]["content"]
    else:
        return "Error calling LLM"


# -- Test Cases --

@patch("requests.post")
def test_run_agent_workflow_success(mock_post):
    """
    Verifies that run_agent_workflow parses a successful API response correctly
    without actually calling the live OpenAI endpoints.
    """
    # 1. Setup the mock response payload
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "This is a mocked response from GPT-4o!"
                }
            }
        ]
    }
    mock_post.return_value = mock_response

    # 2. Mock the configuration settings so we don't rely on the real .env file
    with patch("src.config.settings.openai_api_key", "mock-secret-key-123"):
        result = run_agent_workflow("Verify the agent can respond.")
        
        # 3. Assertions
        assert result == "This is a mocked response from GPT-4o!"
        
        # Verify the mock API was called once with correct parameters
        mock_post.assert_called_once()
        called_args, called_kwargs = mock_post.call_args
        
        assert called_kwargs["headers"]["Authorization"] == "Bearer mock-secret-key-123"
        assert called_kwargs["json"]["model"] == "gpt-4o"
