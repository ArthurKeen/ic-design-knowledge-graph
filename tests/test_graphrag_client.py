"""
Unit tests for GraphRAG client

Tests authentication, service management, and document import functionality.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from graphrag_client import GraphRAGClient


class TestGraphRAGClient:
    """Test suite for GraphRAGClient"""
    
    @pytest.fixture
    def client(self):
        """Create a test client"""
        return GraphRAGClient(
            server_url="https://test.arango.ai",
            username="test_user",
            password="test_pass"
        )
        
    @patch('graphrag_client.requests.post')
    def test_authentication_success(self, mock_post, client):
        """Test successful authentication"""
        # Mock successful auth response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"jwt": "test_token_123"}
        mock_post.return_value = mock_response
        
        # Authenticate
        result = client.authenticate()
        
        # Verify
        assert result is True
        assert client.jwt_token == "test_token_123"
        mock_post.assert_called_once()
        
    @patch('graphrag_client.requests.post')
    def test_authentication_failure(self, mock_post, client):
        """Test authentication failure"""
        # Mock failed auth response
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = Exception("Unauthorized")
        mock_post.return_value = mock_response
        
        # Authenticate
        result = client.authenticate()
        
        # Verify
        assert result is False
        assert client.jwt_token is None
        
    @patch('graphrag_client.requests.post')
    def test_start_service(self, mock_post, client):
        """Test starting a service"""
        # Mock auth
        auth_response = Mock()
        auth_response.status_code = 200
        auth_response.json.return_value = {"jwt": "test_token"}
        
        # Mock service start
        service_response = Mock()
        service_response.status_code = 200
        service_response.json.return_value = {"service_id": "importer-abc123"}
        
        mock_post.side_effect = [auth_response, service_response]
        
        # Start service
        service_id = client.start_service("arangodb-graphrag-importer", {
            "db_name": "test-db",
            "username": "root"
        })
        
        # Verify
        assert service_id == "importer-abc123"
        assert mock_post.call_count == 2
        
    @patch('graphrag_client.requests.request')
    def test_stop_service(self, mock_request, client):
        """Test stopping a service"""
        # Set token
        client.jwt_token = "test_token"
        
        # Mock stop response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "stopped"}
        mock_request.return_value = mock_response
        
        # Stop service
        result = client.stop_service("arangodb-graphrag-importer-abc123")
        
        # Verify
        assert result is True
        mock_request.assert_called_once()
        
    @patch('graphrag_client.requests.request')
    def test_list_services(self, mock_request, client):
        """Test listing services"""
        # Set token
        client.jwt_token = "test_token"
        
        # Mock list response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "services": [
                {"service_id": "importer-123", "service_name": "arangodb-graphrag-importer"},
                {"service_id": "retriever-456", "service_name": "arangodb-graphrag-retriever"}
            ]
        }
        mock_request.return_value = mock_response
        
        # List services
        services = client.list_services()
        
        # Verify
        assert len(services) == 2
        assert services[0]["service_id"] == "importer-123"
        
    @patch('builtins.open', create=True)
    @patch('graphrag_client.base64.b64encode')
    def test_encode_file_base64(self, mock_b64, mock_open, client):
        """Test file encoding"""
        # Mock file read
        mock_file = MagicMock()
        mock_file.read.return_value = b"test content"
        mock_open.return_value.__enter__.return_value = mock_file
        
        # Mock base64 encoding
        mock_b64.return_value.decode.return_value = "dGVzdCBjb250ZW50"
        
        # Encode file
        encoded = client.encode_file_base64("test.pdf")
        
        # Verify
        assert encoded == "dGVzdCBjb250ZW50"
        mock_open.assert_called_once_with("test.pdf", "rb")
        
    @patch('graphrag_client.requests.request')
    @patch('builtins.open', create=True)
    @patch('graphrag_client.base64.b64encode')
    def test_import_document(self, mock_b64, mock_open, mock_request, client):
        """Test document import"""
        # Set token
        client.jwt_token = "test_token"
        
        # Mock file encoding
        mock_file = MagicMock()
        mock_file.read.return_value = b"test content"
        mock_open.return_value.__enter__.return_value = mock_file
        mock_b64.return_value.decode.return_value = "dGVzdCBjb250ZW50"
        
        # Mock import response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "document_id": "doc-123"}
        mock_request.return_value = mock_response
        
        # Import document
        response = client.import_document(
            service_id="importer-123",
            file_path="test.pdf",
            partition_id="partition-1",
            entity_types=["PROCESSOR_COMPONENT"]
        )
        
        # Verify
        assert response["status"] == "success"
        assert response["document_id"] == "doc-123"
        
    @patch('graphrag_client.requests.request')
    def test_query_graphrag(self, mock_request, client):
        """Test GraphRAG query"""
        # Set token
        client.jwt_token = "test_token"
        
        # Mock query response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": "The OR1200 is an OpenRISC processor...",
            "query_type": 3
        }
        mock_request.return_value = mock_response
        
        # Query
        response = client.query_graphrag(
            service_id="retriever-456",
            query="What is the OR1200?",
            query_type=3
        )
        
        # Verify
        assert "result" in response
        assert "OR1200" in response["result"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
