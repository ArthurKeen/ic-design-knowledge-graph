import os
from dotenv import load_dotenv

# Load .env file from project root
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

# Base paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
RTL_DIR = os.path.join(PROJECT_ROOT, "or1200", "rtl", "verilog")
DOC_FILE = os.path.join(PROJECT_ROOT, "or1200", "doc", "openrisc1200_spec.txt")
GIT_DIR = os.path.join(PROJECT_ROOT, "or1200")

# GraphRAG Configuration
GRAPHRAG_PREFIX = os.getenv("GRAPHRAG_PREFIX", "OR1200_")

# GraphRAG GenAI API Configuration
SERVER_URL = os.getenv("SERVER_URL")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GRAPHRAG_PROJECT_NAME = os.getenv("GRAPHRAG_PROJECT_NAME", "or1200-knowledge-graph")

# GraphRAG Service Configuration
GRAPHRAG_CHAT_MODEL = os.getenv("GRAPHRAG_CHAT_MODEL", "gpt-4o")
GRAPHRAG_EMBEDDING_PROVIDER = os.getenv("GRAPHRAG_EMBEDDING_PROVIDER", "openai")
GRAPHRAG_CHUNK_TOKEN_SIZE = int(os.getenv("GRAPHRAG_CHUNK_TOKEN_SIZE", "1200"))
GRAPHRAG_ENABLE_CHUNK_EMBEDDINGS = os.getenv("GRAPHRAG_ENABLE_CHUNK_EMBEDDINGS", "true").lower() == "true"

# Custom entity types for OR1200 hardware
GRAPHRAG_ENTITY_TYPES = [
    "PROCESSOR_COMPONENT",
    "REGISTER",
    "INSTRUCTION",
    "HARDWARE_INTERFACE",
    "MEMORY_UNIT",
    "SIGNAL",
    "EXCEPTION_TYPE",
    "ARCHITECTURE_FEATURE",
    "CONFIGURATION",
    "MEASUREMENT", 
    "CLOCK_DOMAIN", 
    "STATE_MACHINE", 
    "BUS_PROTOCOL",
    "POWER_DOMAIN",
    "TIMING_CONSTRAINT",
    "PROTOCOL_INTERFACE",
    "VERIFICATION_CONSTRUCT",
    "PROPRIETARY_IP_BLOCK",
]

# Document discovery
def find_documents(doc_dir: str = None, pattern: str = "*.pdf", recursive: bool = True) -> list:
    """
    Dynamically discover documents in a directory
    
    Args:
        doc_dir: Directory to search (default: or1200/doc)
        pattern: Glob pattern for matching files (default: *.pdf)
        recursive: Search subdirectories recursively (default: True)
        
    Returns:
        List of absolute paths to matching documents
    """
    from pathlib import Path
    
    if doc_dir is None:
        doc_dir = os.path.join(PROJECT_ROOT, "or1200", "doc")
    
    search_path = Path(doc_dir)
    if not search_path.exists():
        return []
    
    # Use rglob for recursive, glob for non-recursive
    search_func = search_path.rglob if recursive else search_path.glob
    
    # Find all matching files and return as sorted list of absolute paths
    docs = sorted([str(p.absolute()) for p in search_func(pattern)])
    return docs

# OR1200 documents (dynamically discovered)
OR1200_DOCS = find_documents()

# ArangoDB Schema Constants
GRAPH_NAME = "IC_Knowledge_Graph"
COL_MODULE = "RTL_Module"
COL_PORT = "RTL_Port"
COL_SIGNAL = "RTL_Signal"
COL_LOGIC = "RTL_LogicChunk"
COL_COMMIT = "GitCommit"
COL_DOCS = f"{GRAPHRAG_PREFIX}Documents"
COL_ENTITIES = f"{GRAPHRAG_PREFIX}Golden_Entities"
COL_CHUNKS = f"{GRAPHRAG_PREFIX}Chunks"
COL_COMMUNITIES = f"{GRAPHRAG_PREFIX}Communities"
COL_RELATIONS = f"{GRAPHRAG_PREFIX}Golden_Relations"
COL_RAW_ENTITIES = f"{GRAPHRAG_PREFIX}Entities"
COL_RAW_RELATIONS = f"{GRAPHRAG_PREFIX}Relations"

# FSM Collections
COL_FSM = "FSM_StateMachine"
COL_FSM_STATE = "FSM_State"

# Parameter & Memory Collections
COL_PARAMETER = "RTL_Parameter"
COL_MEMORY = "RTL_Memory"
COL_FUNCTION = "RTL_Function"
COL_ASSIGN = "RTL_Assign"
COL_ASSERTION = "RTL_Assertion"
COL_ALWAYS = "RTL_Always"
COL_CLOCK = "ClockDomain"
COL_BUS = "BusInterface"
COL_MEMORY_PORT = "MemoryPort"
COL_OPERATOR = "Operator"
COL_GENERATE = "GenerateBlock"

# Edge Collections
EDGE_CONTAINS = "CONTAINS"
EDGE_WIRED_TO = "WIRED_TO"
EDGE_HAS_PORT = "HAS_PORT"
EDGE_HAS_SIGNAL = "HAS_SIGNAL"
EDGE_MODIFIED = "MODIFIED"
EDGE_RESOLVED = "RESOLVED_TO"
EDGE_REFERENCES = "REFERENCES"
EDGE_DEPENDS_ON = "DEPENDS_ON"  # Module instantiation dependencies
EDGE_OVERRIDES = "OVERRIDES" # Module instantiation → Parameter

# FSM Edge Collections
EDGE_HAS_FSM = "HAS_FSM"  # Module → FSM
EDGE_HAS_STATE = "HAS_STATE"  # FSM → State
EDGE_TRANSITIONS_TO = "TRANSITIONS_TO"  # State → State
EDGE_STATE_REGISTER = "STATE_REGISTER"  # FSM → Signal (which signal holds state)
EDGE_IMPLEMENTED_BY = "IMPLEMENTED_BY"  # FSM → LogicChunk (which always block)

# Parameter & Memory Edge Collections
EDGE_HAS_PARAMETER = "HAS_PARAMETER"  # Module → Parameter
EDGE_USES_PARAMETER = "USES_PARAMETER"  # Signal/Port/Memory → Parameter (width, size, etc.)
EDGE_HAS_MEMORY = "HAS_MEMORY"  # Module → Memory
EDGE_MEMORY_PORT = "MEMORY_PORT"  # Memory → Port (memory interface)
EDGE_STORED_IN = "STORED_IN"  # Signal → Memory (which memory stores this signal)

# Function Edge Collections
EDGE_HAS_FUNCTION = "HAS_FUNCTION"  # Module → Function
EDGE_CALLS_FUNCTION = "CALLS_FUNCTION"  # Logic/Function → Function (function calls)
EDGE_FUNCTION_INPUT = "FUNCTION_INPUT"  # Function → Signal (function inputs)
EDGE_FUNCTION_OUTPUT = "FUNCTION_OUTPUT"  # Function → Signal (function return type)

# Assign Edge Collections (Dataflow)
EDGE_HAS_ASSIGN = "HAS_ASSIGN"  # Module → Assign
EDGE_DRIVES = "DRIVES"  # Assign → Signal (what the assign drives/writes to)
EDGE_READS_FROM = "READS_FROM"  # Assign → Signal (dependencies - what it reads)

# Assertion/Constraint Edge Collections
EDGE_HAS_ASSERTION = "HAS_ASSERTION"  # Module → Assertion
EDGE_CHECKS_SIGNAL = "CHECKS_SIGNAL"  # Assertion → Signal (what signal is being checked)

# Always Block Edge Collections
EDGE_HAS_ALWAYS = "HAS_ALWAYS"  # Module → Always
EDGE_SENSITIVE_TO = "SENSITIVE_TO"  # Always → Signal (sensitivity list)
EDGE_CLOCKED_BY = "CLOCKED_BY"  # Always → Signal (clock signal)
EDGE_RESET_BY = "RESET_BY"  # Always → Signal (reset signal)

# New Component Edge Collections
EDGE_CROSSES_DOMAIN = "CROSSES_DOMAIN" # Signal → ClockDomain
EDGE_IMPLEMENTS = "IMPLEMENTS" # Module → BusInterface
EDGE_PART_OF_BUS = "PART_OF_BUS" # Port/Signal → BusInterface/MemoryPort
EDGE_ACCESSES = "ACCESSES" # LogicChunk → Memory
EDGE_CALLS = "CALLS" # Logic/Function → Function
EDGE_HAS_OPERATOR = "HAS_OPERATOR" # Module → Operator
EDGE_USES_OPERATOR = "USES_OPERATOR" # Logic/Signal → Operator

# ArangoDB Configuration
ARANGO_MODE = os.getenv("ARANGO_MODE", "LOCAL")

if ARANGO_MODE == "REMOTE":
    ARANGO_ENDPOINT = os.getenv("ARANGO_ENDPOINT")
    ARANGO_USERNAME = os.getenv("ARANGO_USERNAME", "root")
    ARANGO_PASSWORD = os.getenv("ARANGO_PASSWORD")
    ARANGO_DATABASE = os.getenv("ARANGO_DATABASE", "ic-knowledge-graph")
else:
    # Local Docker
    ARANGO_ENDPOINT = os.getenv("LOCAL_ARANGO_ENDPOINT", "http://localhost:8530")
    ARANGO_USERNAME = os.getenv("LOCAL_ARANGO_USERNAME", "root")
    ARANGO_PASSWORD = os.getenv("LOCAL_ARANGO_PASSWORD", "")
    ARANGO_DATABASE = os.getenv("LOCAL_ARANGO_DATABASE", "ic-knowledge-graph")

# Output files
RTL_NODES_FILE = os.path.join(DATA_DIR, "rtl_nodes.json")
RTL_EDGES_FILE = os.path.join(DATA_DIR, "rtl_edges.json")
DOC_NODES_FILE = os.path.join(DATA_DIR, "doc_nodes.json")
GIT_NODES_FILE = os.path.join(DATA_DIR, "git_nodes.json")
GIT_EDGES_FILE = os.path.join(DATA_DIR, "git_edges.json")
SEMANTIC_EDGES_FILE = os.path.join(DATA_DIR, "semantic_edges.json")
