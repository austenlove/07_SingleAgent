from .rag_search import RAG_SEARCH_TOOL, run_rag_search
from .web_search import WEB_SEARCH_TOOL, run_web_search
from .analyze_document import ANALYZE_DOCUMENT_TOOL, run_analyze_document

TOOL_SPECS = [
    RAG_SEARCH_TOOL,
    WEB_SEARCH_TOOL,
    ANALYZE_DOCUMENT_TOOL,
]

TOOL_REGISTRY = {
    "rag_search": run_rag_search,
    "web_search": run_web_search,
    "analyze_document": run_analyze_document,
}
