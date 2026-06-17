"""
Thread-safe event bus for streaming agent progress to the UI.

Nodes in rag_agent.py call emit() to push status events.
The Streamlit UI drains get_all() on each render cycle.
"""
import queue
import threading
from typing import Any, Dict, List

_lock = threading.Lock()
_queue: queue.Queue = queue.Queue()

def emit(message: str, kind: str = "step") -> None:
    """
    Push an event. kind can be:
      step       — a processing step (search, graph, chunk...)
      success    — step finished OK
      warning    — non-fatal issue
      answer     — final answer token (for streaming)
    """
    _queue.put({"kind": kind, "message": message})

def get_all() -> List[Dict[str, Any]]:
    """Drain and return all pending events (non-blocking)."""
    events = []
    while True:
        try:
            events.append(_queue.get_nowait())
        except queue.Empty:
            break
    return events

def clear() -> None:
    """Flush queue (call at start of each new turn)."""
    with _lock:
        while not _queue.empty():
            try:
                _queue.get_nowait()
            except queue.Empty:
                break
