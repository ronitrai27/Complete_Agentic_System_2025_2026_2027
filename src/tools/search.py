# TAVILY + SERPAPI (2 TOOLS )
import os
import requests
from langchain_core.tools import tool
from serpapi import GoogleSearch


@tool
def search_web(query: str) -> str:
    """
    Search the web for general information, news, details, or answers using Google Search.

    Args:
        query: The search query string (e.g. 'latest AI news', 'who is CEO of OpenAI').

    Returns:
        Formatted string of organic web search results including title, link, and snippet.
    """
    print(f"\n[TOOL CALL] 'search_web' was invoked with query: '{query}'")
    try:
        params = {
            "engine": "google",
            "q": query,
            "api_key": os.environ["SERPAPI_API_KEY"],
            "num": 5,
            "hl": "en",
        }
        search = GoogleSearch(params)
        results = search.get_dict()
        
        organic_results = results.get("organic_results", [])
        if not organic_results:
            return f"No general web search results found for: '{query}'."

        output_lines = [f"Google Web Search Results for '{query}':\n"]
        for i, res in enumerate(organic_results[:5], 1):
            title = res.get("title", "No Title")
            link = res.get("link", "No Link")
            snippet = res.get("snippet", "No snippet available.")
            
            output_lines.append(
                f"{i}. {title}\n"
                f"   🔗 {link}\n"
                f"   {snippet}\n"
            )
            
        return "\n".join(output_lines)
    except Exception as e:
        return f"SerpAPI general search failed: {str(e)}"


@tool
def search_web_tavily(query: str, topic: str = "general") -> str:
    """
    Search the web for news, jobs, articles, or general information using Tavily API.

    Args:
        query: The search query string (e.g., 'React developer jobs in Bangalore', 'latest AI news').
        topic: The search category. Choose 'news' for current news/articles, or 'general' for general info, jobs, and web content. Defaults to 'general'.

    Returns:
        A formatted string of search results including title, URL, and content snippet.
    """
    print(f"\n[TOOL CALL] 'search_web_tavily' was invoked with query: '{query}' (topic: '{topic}')")
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return "Error: TAVILY_API_KEY environment variable is not set."

    url = "https://api.tavily.com/search"
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "basic",
        "topic": topic,
        "max_results": 5,
        "include_answer": False,
        "include_images": False,
        "include_raw_content": False
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        results = data.get("results", [])
        if not results:
            return f"No results found on Tavily for: '{query}'"

        output_lines = [f"Tavily Search Results for '{query}' (topic: {topic}):\n"]
        for i, res in enumerate(results, 1):
            title = res.get("title", "No Title")
            link = res.get("url", "No URL")
            content = res.get("content", "No content snippet available.")
            score = res.get("score", 0.0)
            
            output_lines.append(
                f"{i}. {title}\n"
                f"   🔗 {link} (Relevance: {score:.2f})\n"
                f"   {content}\n"
            )
            
        return "\n".join(output_lines)

    except requests.exceptions.RequestException as e:
        return f"Tavily search API request failed: {str(e)}"
    except Exception as e:
        return f"An unexpected error occurred during Tavily search: {str(e)}"
