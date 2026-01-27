"""
Integration tests for GraphRAG orchestration

These tests require a live SERVER_URL and valid credentials.
They are marked as integration tests and can be skipped in CI.

Run with: pytest tests/test_graphrag_integration.py -v --integration
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from etl_graphrag import GraphRAGOrchestrator
from config import SERVER_URL, OPENROUTER_API_KEY


# Skip integration tests by default
pytestmark = pytest.mark.integration


class TestGraphRAGIntegration:
    """Integration tests for complete GraphRAG workflow"""
    
    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator instance"""
        if not SERVER_URL or not OPENROUTER_API_KEY:
            pytest.skip("SERVER_URL or OPENROUTER_API_KEY not configured")
            
        return GraphRAGOrchestrator(force_reimport=False)
        
    def test_authentication(self, orchestrator):
        """Test authentication with live API"""
        result = orchestrator.client.authenticate()
        assert result is True
        assert orchestrator.client.jwt_token is not None
        
    def test_list_services(self, orchestrator):
        """Test listing services"""
        orchestrator.client.authenticate()
        services = orchestrator.client.list_services()
        assert isinstance(services, list)
        
    def test_check_collections(self, orchestrator):
        """Test checking existing collections"""
        status = orchestrator.check_existing_collections()
        assert isinstance(status, dict)
        assert 'chunks' in status
        assert 'entities' in status
        
    @pytest.mark.slow
    def test_full_import_workflow(self, orchestrator):
        """
        Test complete import workflow (slow)
        
        This test:
        1. Starts importer service
        2. Imports documents
        3. Verifies collections
        4. Stops service
        
        WARNING: This is expensive and slow. Only run manually.
        """
        pytest.skip("Expensive test - run manually only")
        
        try:
            # Authenticate
            assert orchestrator.client.authenticate()
            
            # Start importer
            service_id = orchestrator.start_importer()
            assert service_id is not None
            
            # Import documents (this takes several minutes)
            orchestrator.import_documents()
            
            # Verify collections exist
            status = orchestrator.check_existing_collections()
            assert status['chunks']['exists']
            assert status['entities']['exists']
            
        finally:
            # Cleanup
            if orchestrator.importer_service_id:
                orchestrator.cleanup()
                
    @pytest.mark.slow
    def test_query_workflow(self, orchestrator):
        """
        Test query workflow with retriever
        
        Requires existing GraphRAG collections and data.
        """
        pytest.skip("Requires existing data - run manually only")
        
        try:
            # Authenticate
            assert orchestrator.client.authenticate()
            
            # Start retriever
            service_id = orchestrator.start_retriever()
            assert service_id is not None
            
            # Run test query
            response = orchestrator.client.query_graphrag(
                service_id=service_id,
                query="What is the OR1200 processor?",
                query_type=3
            )
            
            assert 'result' in response
            assert len(response['result']) > 0
            
        finally:
            # Cleanup
            if orchestrator.retriever_service_id:
                orchestrator.cleanup()


class TestDocumentConverter:
    """Integration tests for document conversion"""
    
    def test_convert_existing_pdf(self):
        """Test converting an actual OR1200 PDF"""
        from document_converter import DocumentConverter
        from config import OR1200_DOCS
        
        if not OR1200_DOCS or not os.path.exists(OR1200_DOCS[0]):
            pytest.skip("OR1200 PDFs not available")
            
        converter = DocumentConverter(method='pymupdf')
        
        # Convert first PDF
        markdown = converter.convert(OR1200_DOCS[0])
        
        # Verify output
        assert isinstance(markdown, str)
        assert len(markdown) > 1000  # Should have substantial content
        assert 'OR1200' in markdown or 'OpenRISC' in markdown


def pytest_configure(config):
    """Register custom markers"""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires live API)"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow (expensive API calls)"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--integration"])
