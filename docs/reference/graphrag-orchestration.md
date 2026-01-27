# GraphRAG Service Orchestration Guide

Complete guide to using the GraphRAG service orchestration system for importing OR1200 documentation into the knowledge graph.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Setup](#setup)
4. [Usage](#usage)
5. [API Reference](#api-reference)
6. [Troubleshooting](#troubleshooting)
7. [Advanced Topics](#advanced-topics)

---

## Overview

The GraphRAG orchestration system provides Python-based management of ArangoDB's hosted GraphRAG services (Importer and Retriever) for processing unstructured documentation.

### What It Does

1. **Document Conversion**: Converts PDF documents to Markdown using Docling or pymupdf4llm
2. **Service Management**: Starts/stops GraphRAG Importer and Retriever services via GenAI API
3. **Document Import**: Submits documents with custom entity types for extraction
4. **Entity Extraction**: LLM-powered extraction of hardware-specific entities
5. **Knowledge Querying**: Tests the knowledge graph with sample queries

### Key Features

- **Standalone Script**: Run complete workflows from command line
- **Pipeline Integration**: Optionally run as part of ETL pipeline
- **Configurable**: All settings via environment variables
- **Force Reimport**: Option to clear and reimport collections
- **Service Reuse**: Can attach to existing running services

---

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────┐
│                 GraphRAG Orchestration                   │
│                                                           │
│  ┌──────────────┐  ┌─────────────┐  ┌─────────────────┐ │
│  │etl_graphrag.py│ │graphrag_    │  │document_       │ │
│  │(Orchestrator) │→│client.py    │  │converter.py    │ │
│  └──────────────┘  └─────────────┘  └─────────────────┘ │
│         │                  │                │            │
└─────────┼──────────────────┼────────────────┼────────────┘
          │                  │                │
          ↓                  ↓                ↓
    ┌──────────┐      ┌────────────┐   ┌──────────┐
    │ .env     │      │GenAI API   │   │OR1200    │
    │ config   │      │Services    │   │PDFs      │
    └──────────┘      └────────────┘   └──────────┘
                            │
                            ↓
                      ┌──────────────┐
                      │ArangoDB      │
                      │Collections   │
                      └──────────────┘
```

### Collections Created

The GraphRAG importer creates these collections:

| Collection | Description |
|------------|-------------|
| `OR1200_Documents` | Source PDF metadata |
| `OR1200_Chunks` | Text chunks (1200 tokens) |
| `OR1200_Entities` | Raw extracted entities |
| `OR1200_Golden_Entities` | Consolidated entities |
| `OR1200_Relations` | Raw relationships |
| `OR1200_Golden_Relations` | Consolidated relationships |
| `OR1200_Communities` | Entity clusters (Leiden) |

---

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

Required packages:
- `docling==2.26.0` - PDF conversion (accurate)
- `pymupdf4llm` - PDF conversion (fast)
- `aiohttp` - Async HTTP for streaming
- `requests` - HTTP client
- `markdownify` - HTML to Markdown

### 2. Configure Environment

Edit `.env` file with your credentials:

```bash
# GraphRAG GenAI API Configuration
SERVER_URL=https://your-instance.arango.ai
OPENROUTER_API_KEY=your_openrouter_api_key
GRAPHRAG_PROJECT_NAME=or1200-knowledge-graph

# ArangoDB Connection (for checking collections)
ARANGO_MODE=REMOTE
ARANGO_ENDPOINT=https://your-instance.arango.ai
ARANGO_USERNAME=root
ARANGO_PASSWORD=your_password
ARANGO_DATABASE=ic-knowledge-graph

# GraphRAG Service Configuration
GRAPHRAG_CHAT_MODEL=gpt-4o
GRAPHRAG_EMBEDDING_PROVIDER=openai
GRAPHRAG_CHUNK_TOKEN_SIZE=1200
GRAPHRAG_ENABLE_CHUNK_EMBEDDINGS=true
GRAPHRAG_PREFIX=OR1200_

# Pipeline Integration
RUN_GRAPHRAG=false  # Set to true to run in ETL pipeline
```

### 3. Verify PDFs

Ensure OR1200 documentation PDFs exist:

```bash
ls -lh or1200/doc/*.pdf
```

Expected files:
- `openrisc1200_spec.pdf`
- `openrisc1200_spec_0.7_jp.pdf`
- `openrisc1200_supplementary_prm.pdf`

---

## Usage

### Basic Commands

#### Check Collections Status

```bash
python src/etl_graphrag.py --check-collections
```

Output shows which GraphRAG collections exist and their document counts.

#### List Running Services

```bash
python src/etl_graphrag.py --list-services
```

Shows all GenAI services currently running.

#### Import Documents (Full Workflow)

```bash
# Import with automatic cleanup
python src/etl_graphrag.py --import --cleanup

# Import and keep services running
python src/etl_graphrag.py --import

# Force reimport (clear existing data)
python src/etl_graphrag.py --import --force-reimport --cleanup
```

#### Test Queries

```bash
# Start retriever and test
python src/etl_graphrag.py --test --cleanup

# Use existing retriever service
python src/etl_graphrag.py --test --retriever-id abc123
```

#### Complete Pipeline

```bash
# Import documents + test queries + cleanup
python src/etl_graphrag.py --import --test --cleanup
```

### Advanced Usage

#### Use Docling Instead of pymupdf

```bash
python src/etl_graphrag.py --import --conversion-method docling
```

Docling is more accurate but slower than pymupdf.

#### Attach to Existing Services

If services are already running:

```bash
# Get service IDs
python src/etl_graphrag.py --list-services

# Use existing services
python src/etl_graphrag.py --import --importer-id xyz789
python src/etl_graphrag.py --test --retriever-id abc123
```

#### Verbose Logging

```bash
python src/etl_graphrag.py --import --test --verbose
```

#### Integration with ETL Pipeline

Enable in `.env`:

```bash
RUN_GRAPHRAG=true
```

Then run the full pipeline:

```bash
cd src
./import_all.sh
```

This will:
1. Import RTL data
2. Import Git data
3. Run consolidation and bridging
4. **Import GraphRAG documents** (if `RUN_GRAPHRAG=true`)

---

## API Reference

### GraphRAGClient

Python client for GenAI API services.

```python
from graphrag_client import GraphRAGClient

# Initialize
client = GraphRAGClient(
    server_url="https://your-instance.arango.ai",
    username="root",
    password="your_password"
)

# Authenticate
client.authenticate()

# Start importer
importer_id = client.start_service("arangodb-graphrag-importer", {
    "db_name": "ic-knowledge-graph",
    "username": "root",
    "password": "password",
    "chat_model": "gpt-4o",
    "chat_api_provider": "openai",
    "embedding_api_provider": "openai",
    "chat_api_key": "your_openai_key",
    "embedding_api_key": "your_openai_key",
    "genai_project_name": "or1200-knowledge-graph"
})

# Import document
response = client.import_document(
    service_id=importer_id,
    file_path="or1200/doc/openrisc1200_spec.pdf",
    partition_id="or1200_1",
    entity_types=["PROCESSOR_COMPONENT", "REGISTER", "INSTRUCTION"],
    chunk_size=1200,
    enable_embeddings=True
)

# Start retriever
retriever_id = client.start_service("arangodb-graphrag-retriever", params)

# Query
result = client.query_graphrag(
    service_id=retriever_id,
    query="What is the OR1200 processor?",
    query_type=3  # 1=global, 2=local, 3=instant
)

# Stop services
client.stop_service(f"arangodb-graphrag-importer-{importer_id}")
client.stop_service(f"arangodb-graphrag-retriever-{retriever_id}")
```

### DocumentConverter

PDF to Markdown conversion.

```python
from document_converter import DocumentConverter

# Use pymupdf (fast)
converter = DocumentConverter(method='pymupdf')
markdown = converter.convert('document.pdf')

# Use docling (accurate)
converter = DocumentConverter(method='docling')
markdown = converter.convert('document.pdf', output_path='output.md')

# Convert directory
output_files = converter.convert_directory(
    input_dir='or1200/doc',
    output_dir='markdown_output',
    pattern='*.pdf'
)
```

### GraphRAGOrchestrator

High-level orchestration.

```python
from etl_graphrag import GraphRAGOrchestrator

# Initialize
orchestrator = GraphRAGOrchestrator(
    force_reimport=False,
    conversion_method='pymupdf'
)

# Check what exists
status = orchestrator.check_existing_collections()

# Import workflow
orchestrator.start_importer()
orchestrator.import_documents()

# Test workflow
orchestrator.start_retriever()
orchestrator.test_queries()

# Cleanup
orchestrator.cleanup()
```

---

## Troubleshooting

### Common Issues

#### 1. Authentication Fails

**Error**: `Authentication failed`

**Solutions**:
- Verify `SERVER_URL` in `.env` is correct
- Check `ARANGO_USERNAME` and `ARANGO_PASSWORD`
- Ensure no trailing slashes in `SERVER_URL`
- Test credentials in ArangoDB web UI first

#### 2. Service Start Fails

**Error**: `Failed to start service`

**Solutions**:
- Check API key is valid (`OPENROUTER_API_KEY`)
- Verify database exists (`ARANGO_DATABASE`)
- Check service quota/limits on your account
- List existing services: may have hit limit

#### 3. Import Fails

**Error**: `Failed to import document`

**Solutions**:
- Verify PDF files exist in `or1200/doc/`
- Check file permissions (must be readable)
- Try with `--verbose` flag for details
- Ensure importer service is running
- Check importer service logs

#### 4. Collections Not Created

**Issue**: Import succeeds but collections missing

**Solutions**:
- Wait 30-60 seconds after import (processing time)
- Check `GRAPHRAG_PREFIX` matches expected (`OR1200_`)
- Verify database name is correct
- Run `--check-collections` to confirm

#### 5. Query Returns Empty

**Issue**: Query runs but no results

**Solutions**:
- Ensure documents were imported successfully
- Check entity extraction completed
- Verify retriever has correct project name
- Try different query types (1, 2, or 3)
- Check collections have data: `--check-collections`

### Debugging Tips

#### Enable Verbose Logging

```bash
python src/etl_graphrag.py --import --test --verbose
```

#### Check Service Status

```python
from graphrag_client import GraphRAGClient

client = GraphRAGClient(SERVER_URL, USERNAME, PASSWORD)
client.authenticate()
services = client.list_services()

for service in services:
    print(f"{service['service_name']}: {service['status']}")
```

#### Verify Collections

```bash
python src/etl_graphrag.py --check-collections
```

#### Manual Query Test

```python
from graphrag_client import GraphRAGClient

client = GraphRAGClient(SERVER_URL, USERNAME, PASSWORD)
client.authenticate()

# Use your retriever ID
result = client.query_graphrag(
    service_id="your-retriever-id",
    query="Test query",
    query_type=3
)
print(result)
```

---

## Advanced Topics

### Custom Entity Types

Modify in `src/config.py`:

```python
GRAPHRAG_ENTITY_TYPES = [
    "PROCESSOR_COMPONENT",
    "REGISTER",
    "INSTRUCTION",
    # Add your own:
    "CUSTOM_ENTITY_TYPE",
]
```

### Changing Collection Prefix

To use a different prefix than `OR1200_`:

```bash
# In .env
GRAPHRAG_PREFIX=MyProject_
```

All collections will be named `MyProject_Entities`, `MyProject_Chunks`, etc.

### Chunk Size Tuning

Adjust chunk size for different documents:

```bash
# In .env
GRAPHRAG_CHUNK_TOKEN_SIZE=1500  # Larger chunks
```

Larger chunks preserve more context but may reduce precision.

### Service Configuration

Advanced service parameters can be set in orchestrator:

```python
params = {
    "db_name": ARANGO_DATABASE,
    "username": ARANGO_USERNAME,
    "password": ARANGO_PASSWORD,
    "chat_model": "gpt-4-turbo",  # Different model
    "chat_api_provider": "openai",
    "embedding_api_provider": "openai",
    "chat_api_key": OPENROUTER_API_KEY,
    "embedding_api_key": OPENROUTER_API_KEY,
    "genai_project_name": GRAPHRAG_PROJECT_NAME,
    "profiles": "memory-16gi-cpu-4",  # More resources
}
```

### Batch Processing

To process multiple document sets:

```python
from etl_graphrag import GraphRAGOrchestrator

orchestrator = GraphRAGOrchestrator()
orchestrator.client.authenticate()
orchestrator.start_importer()

# Process multiple batches
document_sets = [
    ("or1200/doc/openrisc1200_spec.pdf", "or1200_1"),
    ("other/docs/manual.pdf", "manual_1"),
    # ...
]

for pdf_path, partition_id in document_sets:
    orchestrator.client.import_document(
        service_id=orchestrator.importer_service_id,
        file_path=pdf_path,
        partition_id=partition_id,
        entity_types=GRAPHRAG_ENTITY_TYPES
    )

orchestrator.cleanup()
```

### Integration with Bridging

After GraphRAG import, run semantic bridging:

```bash
# 1. Import GraphRAG
python src/etl_graphrag.py --import --cleanup

# 2. Run consolidation
python src/consolidator.py

# 3. Run bridging
python src/bridger.py
```

This creates `RESOLVED_TO` edges linking RTL code to documentation entities.

---

## Performance Considerations

### Import Times

Typical import times for OR1200 (3 PDFs):

- **Document conversion**: 10-30 seconds
- **GraphRAG processing**: 5-10 minutes per PDF
- **Total**: ~15-30 minutes for full import

### Resource Usage

GenAI services consume:
- **Memory**: 2-8 GB per service
- **API calls**: ~100-500 OpenAI requests per PDF
- **Cost**: Estimated $1-5 per PDF (varies by model)

### Optimization Tips

1. **Use pymupdf** instead of docling (3x faster conversion)
2. **Batch imports**: Start service once, import multiple documents
3. **Skip embeddings** for testing: `GRAPHRAG_ENABLE_CHUNK_EMBEDDINGS=false`
4. **Reuse services**: Don't use `--cleanup` flag during development
5. **Increase chunk size**: Reduces total chunks and processing time

---

## Testing

### Run Unit Tests

```bash
# All tests
pytest tests/test_graphrag_client.py -v

# Specific test
pytest tests/test_graphrag_client.py::TestGraphRAGClient::test_authentication_success -v
```

### Run Integration Tests

```bash
# Requires live credentials
pytest tests/test_graphrag_integration.py -v --integration

# Skip slow tests
pytest tests/test_graphrag_integration.py -v --integration -m "not slow"
```

---

## Migration Notes

### From Notebook to Production

This system replaces the Jupyter notebook workflow with:

✅ **Better**: Modular Python modules  
✅ **Better**: CLI interface with options  
✅ **Better**: Error handling and logging  
✅ **Better**: Configuration via environment  
✅ **Better**: Reusable client library  
✅ **Better**: Integration with ETL pipeline  
✅ **Better**: Automated testing  

### Backwards Compatibility

The system is compatible with existing:
- GraphRAG collections in database
- Consolidation and bridging scripts
- ETL pipeline structure
- Documentation and schema

---

## Support

### Documentation

- Main README: `/path/to/project/README.md`
- Schema reference: `/path/to/project/docs/project/SCHEMA.md`
- Bridging guide: `/path/to/project/docs/project/CONSOLIDATION_BRIDGING_IMPROVEMENTS.md`

### Source Code

- Client: `src/graphrag_client.py`
- Converter: `src/document_converter.py`
- Orchestrator: `src/etl_graphrag.py`
- Config: `src/config.py`

### Contact

For issues or questions:
1. Check troubleshooting section above
2. Review source code comments
3. Check ArangoDB GraphRAG documentation
4. Contact repository maintainer

---

**Last Updated**: January 2026  
**Version**: 1.0.0  
**Status**: Production Ready
