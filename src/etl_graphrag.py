"""
GraphRAG ETL Pipeline

Orchestrates ArangoDB GraphRAG services to:
1. Start Importer service
2. Convert OR1200 PDFs to markdown
3. Import documents with custom entity types
4. Start Retriever service
5. Test with sample queries
6. Optionally stop services

Usage:
    # Full pipeline with cleanup
    python src/etl_graphrag.py --import --test --cleanup
    
    # Import only (keep services running)
    python src/etl_graphrag.py --import
    
    # Test with existing services
    python src/etl_graphrag.py --test --importer-id <id> --retriever-id <id>
    
    # Force reimport (clear collections first)
    python src/etl_graphrag.py --import --force-reimport
    
    # List running services
    python src/etl_graphrag.py --list-services
"""

import argparse
import logging
import sys
import os
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.getcwd(), 'src'))

from config import (
    SERVER_URL, ARANGO_USERNAME, ARANGO_PASSWORD, ARANGO_DATABASE,
    OPENROUTER_API_KEY, OPENAI_API_KEY, GRAPHRAG_PROJECT_NAME, GRAPHRAG_PREFIX,
    GRAPHRAG_ENTITY_TYPES, OR1200_DOCS, GRAPHRAG_CHAT_MODEL,
    GRAPHRAG_CHUNK_TOKEN_SIZE, GRAPHRAG_ENABLE_CHUNK_EMBEDDINGS,
    GRAPHRAG_EMBEDDING_PROVIDER
)
from graphrag_client import GraphRAGClient
from document_converter import DocumentConverter
from db_utils import get_db

logger = logging.getLogger(__name__)


class GraphRAGOrchestrator:
    """Orchestrates GraphRAG service lifecycle"""
    
    def __init__(self, force_reimport: bool = False, conversion_method: str = 'pymupdf'):
        """
        Initialize orchestrator
        
        Args:
            force_reimport: If True, clear existing collections before import
            conversion_method: PDF conversion method ('pymupdf' or 'docling')
        """
        # Validate configuration
        if not SERVER_URL:
            raise ValueError("SERVER_URL not configured. Set in .env file.")
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not configured. Set in .env file.")
            
        self.client = GraphRAGClient(SERVER_URL, ARANGO_USERNAME, ARANGO_PASSWORD)
        self.converter = DocumentConverter(method=conversion_method)
        self.force_reimport = force_reimport
        self.importer_service_id = None
        self.retriever_service_id = None
        
    def check_existing_collections(self) -> dict:
        """
        Check if GraphRAG collections already exist
        
        Returns:
            Dictionary with collection names and existence status
        """
        try:
            db = get_db()
            collections = {
                'chunks': f"{GRAPHRAG_PREFIX}Chunks",
                'entities': f"{GRAPHRAG_PREFIX}Entities",
                'golden_entities': f"{GRAPHRAG_PREFIX}Golden_Entities",
                'relations': f"{GRAPHRAG_PREFIX}Relations",
                'golden_relations': f"{GRAPHRAG_PREFIX}Golden_Relations",
                'communities': f"{GRAPHRAG_PREFIX}Communities",
                'documents': f"{GRAPHRAG_PREFIX}Documents"
            }
            
            status = {}
            for key, col_name in collections.items():
                exists = db.has_collection(col_name)
                status[key] = {'name': col_name, 'exists': exists}
                if exists:
                    count = db.collection(col_name).count()
                    status[key]['count'] = count
                    
            return status
            
        except Exception as e:
            logger.error(f"Failed to check collections: {e}")
            return {}
            
    def clear_graphrag_collections(self):
        """Clear existing GraphRAG collections if force reimport"""
        if not self.force_reimport:
            return
            
        logger.info("Force reimport: Clearing existing GraphRAG collections...")
        
        try:
            db = get_db()
            collection_suffixes = [
                'Chunks', 'Entities', 'Golden_Entities', 
                'Relations', 'Golden_Relations', 'Communities', 'Documents'
            ]
            
            for suffix in collection_suffixes:
                col_name = f"{GRAPHRAG_PREFIX}{suffix}"
                if db.has_collection(col_name):
                    col = db.collection(col_name)
                    count = col.count()
                    col.truncate()
                    logger.info(f"  ✓ Cleared {col_name} ({count} documents)")
                    
            logger.info("✓ All collections cleared")
            
        except Exception as e:
            logger.error(f"Failed to clear collections: {e}")
            raise
            
    def ensure_project_exists(self):
        """Ensure GraphRAG project exists in the database"""
        try:
            self.client.create_project(
                project_name=GRAPHRAG_PROJECT_NAME,
                db_name=ARANGO_DATABASE,
                project_type="Graph",
                description="OR1200 GraphRAG Knowledge Graph"
            )
        except Exception as e:
            error_str = str(e).lower()
            if "already exists" not in error_str:
                raise

    def _wait_for_service_ready(
        self,
        service_name: str,
        service_id_suffix: str,
        timeout_s: int = 120,
        poll_interval_s: int = 5,
    ) -> None:
        """
        Best-effort readiness wait using list_services().

        The GenAI services may take time to become visible / ready; during rollout
        transient 404/503s can occur. This method avoids a fixed sleep and instead
        polls for the service to appear.
        """
        full_id = f"{service_name}-{service_id_suffix}"
        deadline = time.time() + timeout_s

        logger.info(f"Waiting for service to be ready: {full_id} (timeout {timeout_s}s)...")

        while time.time() < deadline:
            try:
                services = self.client.list_services()
                for s in services:
                    sid = s.get("service_id") or s.get("serviceId")
                    if sid == full_id:
                        status = (s.get("status") or "").lower()
                        # Status values vary; treat missing/unknown as ready once visible.
                        if not status or status in {"running", "ready", "healthy"}:
                            logger.info(f"✓ Service is ready: {full_id} (status={status or 'unknown'})")
                            return
                        logger.debug(f"Service visible but not ready yet: {full_id} (status={status})")
                # not found yet
            except Exception as e:
                logger.debug(f"Readiness poll error (will retry): {e}")

            time.sleep(poll_interval_s)

        logger.warning(f"Timed out waiting for service readiness: {full_id}. Continuing anyway.")
    
    def start_importer(self) -> str:
        """
        Start the GraphRAG Importer service
        
        Returns:
            Service ID (short form)
        """
        # Ensure project exists first
        self.ensure_project_exists()
        
        logger.info("Starting GraphRAG Importer service...")
        
        params = {
            "db_name": ARANGO_DATABASE,
            "username": ARANGO_USERNAME,
            "password": ARANGO_PASSWORD,
            "chat_model": GRAPHRAG_CHAT_MODEL,
            "chat_api_provider": "openai",
            "embedding_api_provider": GRAPHRAG_EMBEDDING_PROVIDER,
            "chat_api_key": OPENAI_API_KEY,
            "embedding_api_key": OPENAI_API_KEY,
            "genai_project_name": GRAPHRAG_PROJECT_NAME,
        }
        
        service_id = self.client.start_service("arangodb-graphrag-importer", params)
        if not service_id:
            raise RuntimeError("Failed to start importer service")
            
        self.importer_service_id = service_id
        logger.info(f"✓ Importer started with ID: {service_id}")

        self._wait_for_service_ready("arangodb-graphrag-importer", service_id)
        
        return service_id
        
    def import_documents(self):
        """Import all OR1200 documents (PDF → Markdown → Import)"""
        if not self.importer_service_id:
            raise RuntimeError("Importer service not started. Call start_importer() first.")
            
        logger.info(f"Processing {len(OR1200_DOCS)} OR1200 documents...")
        logger.info("=" * 70)
        
        # Step 1: Convert PDFs to Markdown (UTF-8 encoded)
        logger.info("\nStep 1: Converting PDFs to Markdown...")
        markdown_dir = os.path.join(os.getcwd(), "markdown_output")
        os.makedirs(markdown_dir, exist_ok=True)
        
        markdown_files = []
        for pdf_path in OR1200_DOCS:
            if not os.path.exists(pdf_path):
                logger.warning(f"  ⚠ PDF not found: {pdf_path}")
                continue
                
            filename = os.path.basename(pdf_path)
            md_filename = filename.replace('.pdf', '.md')
            md_path = os.path.join(markdown_dir, md_filename)
            
            logger.info(f"  Converting: {filename}")
            try:
                # Converter uses UTF-8 encoding by default
                md_content = self.converter.convert(pdf_path, md_path)
                markdown_files.append(md_path)
                logger.info(f"    ✓ Generated {len(md_content):,} characters (UTF-8)")
            except Exception as e:
                logger.error(f"    ✗ Conversion failed: {e}")
                continue
        
        logger.info(f"\n✓ Converted {len(markdown_files)}/{len(OR1200_DOCS)} documents to Markdown")
        logger.info("=" * 70)
        
        # Step 2: Import Markdown files to GraphRAG
        logger.info("\nStep 2: Importing Markdown files to GraphRAG...")
        
        successful = 0
        failed = 0
        
        for idx, md_path in enumerate(markdown_files, start=1):
            doc_name = Path(md_path).stem
            
            try:
                logger.info(f"[{idx}/{len(markdown_files)}] Importing {doc_name}...")
                
                # Import Markdown file (UTF-8 encoded)
                response = self.client.import_document(
                    service_id=self.importer_service_id,
                    file_path=md_path,
                    partition_id=f"or1200_{idx}",
                    entity_types=GRAPHRAG_ENTITY_TYPES,
                    chunk_size=GRAPHRAG_CHUNK_TOKEN_SIZE,
                    enable_embeddings=GRAPHRAG_ENABLE_CHUNK_EMBEDDINGS
                )
                
                message = response.get('message', 'Imported successfully')
                logger.info(f"  ✓ {message}")
                successful += 1
                
            except Exception as e:
                logger.error(f"  ✗ Failed to import {doc_name}: {e}")
                failed += 1
                continue
        
        logger.info("=" * 70)
        logger.info(f"\n✓ Import complete: {successful} successful, {failed} failed")
        
    def start_retriever(self) -> str:
        """
        Start the GraphRAG Retriever service
        
        Returns:
            Service ID (short form)
        """
        # Ensure project exists first
        self.ensure_project_exists()
        
        logger.info("Starting GraphRAG Retriever service...")
        
        params = {
            "db_name": ARANGO_DATABASE,
            "username": ARANGO_USERNAME,
            "password": ARANGO_PASSWORD,
            "chat_model": GRAPHRAG_CHAT_MODEL,
            "chat_api_provider": "openai",
            "embedding_api_provider": GRAPHRAG_EMBEDDING_PROVIDER,
            "chat_api_key": OPENAI_API_KEY,
            "embedding_api_key": OPENAI_API_KEY,
            "genai_project_name": GRAPHRAG_PROJECT_NAME,
        }
        
        service_id = self.client.start_service("arangodb-graphrag-retriever", params)
        if not service_id:
            raise RuntimeError("Failed to start retriever service")
            
        self.retriever_service_id = service_id
        logger.info(f"✓ Retriever started with ID: {service_id}")

        self._wait_for_service_ready("arangodb-graphrag-retriever", service_id)
        
        return service_id
        
    def test_queries(self):
        """Run test queries against the knowledge graph"""
        if not self.retriever_service_id:
            raise RuntimeError("Retriever service not started. Call start_retriever() first.")
            
        test_queries = [
            "What are the main components of the OR1200 processor?",
            "How does the instruction cache work in OR1200?",
            "Explain the exception handling mechanism in OR1200"
        ]
        
        logger.info("\nTesting knowledge graph with sample queries...")
        logger.info("=" * 70)
        
        for i, query in enumerate(test_queries, 1):
            logger.info(f"\n[Query {i}/{len(test_queries)}]")
            logger.info(f"Q: {query}")
            
            try:
                response = self.client.query_graphrag(
                    service_id=self.retriever_service_id,
                    query=query,
                    query_type=3  # Instant search
                )
                
                answer = response.get('result', 'N/A')
                logger.info(f"A: {answer[:300]}{'...' if len(answer) > 300 else ''}")
                
            except Exception as e:
                logger.error(f"Query failed: {e}")
                
        logger.info("\n" + "=" * 70)
        logger.info("✓ Test queries complete")
        
    def list_services(self):
        """List all running services"""
        logger.info("Listing all running services...")
        
        services = self.client.list_services()
        
        if not services:
            logger.info("No services currently running")
            return
            
        logger.info(f"\nFound {len(services)} running service(s):")
        logger.info("-" * 70)
        
        for service in services:
            service_id = service.get('service_id', 'N/A')
            service_name = service.get('service_name', 'N/A')
            status = service.get('status', 'N/A')
            logger.info(f"  {service_name}")
            logger.info(f"    ID: {service_id}")
            logger.info(f"    Status: {status}")
            
        logger.info("-" * 70)
        
    def cleanup(self):
        """Stop all running services"""
        logger.info("\nCleaning up services...")
        
        stopped = 0
        
        if self.importer_service_id:
            full_id = f"arangodb-graphrag-importer-{self.importer_service_id}"
            if self.client.stop_service(full_id):
                stopped += 1
                
        if self.retriever_service_id:
            full_id = f"arangodb-graphrag-retriever-{self.retriever_service_id}"
            if self.client.stop_service(full_id):
                stopped += 1
                
        logger.info(f"✓ Stopped {stopped} service(s)")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="GraphRAG ETL Pipeline for OR1200 Documentation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full pipeline with cleanup
  python src/etl_graphrag.py --import --test --cleanup
  
  # Import documents only
  python src/etl_graphrag.py --import
  
  # Test with existing services
  python src/etl_graphrag.py --test --importer-id abc123 --retriever-id def456
  
  # Force reimport (clear and reimport)
  python src/etl_graphrag.py --import --force-reimport
  
  # Check collections and list services
  python src/etl_graphrag.py --check-collections --list-services
        """
    )
    
    # Actions
    parser.add_argument("--import", dest="do_import", action="store_true",
                       help="Import OR1200 documents")
    parser.add_argument("--test", action="store_true",
                       help="Test with sample queries")
    parser.add_argument("--cleanup", action="store_true",
                       help="Stop services after completion")
    parser.add_argument("--list-services", action="store_true",
                       help="List all running services")
    parser.add_argument("--check-collections", action="store_true",
                       help="Check existing GraphRAG collections")
    
    # Options
    parser.add_argument("--force-reimport", action="store_true",
                       help="Clear existing collections before import")
    parser.add_argument("--importer-id", help="Use existing importer service ID")
    parser.add_argument("--retriever-id", help="Use existing retriever service ID")
    parser.add_argument("--conversion-method", choices=['pymupdf', 'docling'],
                       default='pymupdf', help="PDF conversion method")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Create orchestrator
    try:
        orchestrator = GraphRAGOrchestrator(
            force_reimport=args.force_reimport,
            conversion_method=args.conversion_method
        )
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        logger.error("Please check your .env file and ensure all required variables are set.")
        sys.exit(1)
        
    try:
        # Authentication
        logger.info("Authenticating with GenAI API...")
        if not orchestrator.client.authenticate():
            logger.error("Authentication failed")
            sys.exit(1)
            
        # Check collections
        if args.check_collections:
            logger.info("\nChecking existing GraphRAG collections...")
            logger.info("-" * 70)
            status = orchestrator.check_existing_collections()
            
            for key, info in status.items():
                exists_str = "✓ EXISTS" if info['exists'] else "✗ MISSING"
                count_str = f" ({info.get('count', 0)} docs)" if info['exists'] else ""
                logger.info(f"  {info['name']}: {exists_str}{count_str}")
            logger.info("-" * 70)
            
        # List services
        if args.list_services:
            orchestrator.list_services()
            
        # Import workflow
        if args.do_import:
            logger.info("\n" + "=" * 70)
            logger.info("STARTING IMPORT WORKFLOW")
            logger.info("=" * 70)
            
            # Start or use existing importer
            if not args.importer_id:
                orchestrator.start_importer()
            else:
                orchestrator.importer_service_id = args.importer_id
                logger.info(f"Using existing importer: {args.importer_id}")
                
            # Clear collections if requested
            if args.force_reimport:
                orchestrator.clear_graphrag_collections()
                
            # Import documents
            orchestrator.import_documents()
            
        # Test workflow
        if args.test:
            logger.info("\n" + "=" * 70)
            logger.info("STARTING TEST WORKFLOW")
            logger.info("=" * 70)
            
            # Start or use existing retriever
            if not args.retriever_id:
                orchestrator.start_retriever()
            else:
                orchestrator.retriever_service_id = args.retriever_id
                logger.info(f"Using existing retriever: {args.retriever_id}")
                
            # Run test queries
            orchestrator.test_queries()
            
        # Cleanup
        if args.cleanup:
            orchestrator.cleanup()
        else:
            if orchestrator.importer_service_id or orchestrator.retriever_service_id:
                logger.info("\n" + "-" * 70)
                logger.info("Services left running (use --cleanup to stop):")
                if orchestrator.importer_service_id:
                    logger.info(f"  Importer: {orchestrator.importer_service_id}")
                if orchestrator.retriever_service_id:
                    logger.info(f"  Retriever: {orchestrator.retriever_service_id}")
                logger.info("-" * 70)
                
        logger.info("\n✓ Pipeline complete!")
        
    except KeyboardInterrupt:
        logger.info("\n\nInterrupted by user")
        if args.cleanup:
            logger.info("Cleaning up...")
            orchestrator.cleanup()
        sys.exit(1)
        
    except Exception as e:
        logger.error(f"\n✗ Pipeline failed: {e}", exc_info=args.verbose)
        if args.cleanup:
            logger.info("Attempting cleanup...")
            try:
                orchestrator.cleanup()
            except Exception as cleanup_err:
                logger.warning(f"Cleanup failed (services may still be running): {cleanup_err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
