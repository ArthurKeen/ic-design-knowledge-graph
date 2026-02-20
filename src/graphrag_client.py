"""
ArangoDB GraphRAG GenAI API Client

Provides Python interface to ArangoDB's hosted GraphRAG services
(Importer and Retriever) via the GenAI API.

Usage:
    from graphrag_client import GraphRAGClient
    
    client = GraphRAGClient(server_url, username, password)
    client.authenticate()
    
    # Start importer
    importer_id = client.start_service("arangodb-graphrag-importer", params)
    
    # Import documents
    client.import_document(importer_id, pdf_path, partition_id, entity_types)
    
    # Query
    retriever_id = client.start_service("arangodb-graphrag-retriever", params)
    result = client.query_graphrag(retriever_id, "What is the OR1200?")
"""

import requests
import json
import base64
import time
import logging
import warnings
from typing import Dict, Optional, List
from pathlib import Path

# Suppress SSL warnings for internal services
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

class GraphRAGClient:
    """Client for ArangoDB GraphRAG GenAI API services"""
    
    def __init__(self, server_url: str, username: str, password: str):
        """
        Initialize GraphRAG client
        
        Args:
            server_url: Base URL of the GenAI API server (e.g., https://your-instance.arango.ai)
            username: Database username
            password: Database password
        """
        self.server_url = server_url.rstrip('/')
        self.username = username
        self.password = password
        self.jwt_token = None
        self.logger = logging.getLogger(__name__)
        
    def authenticate(self) -> bool:
        """
        Authenticate and retrieve JWT token
        
        Returns:
            True if authentication successful, False otherwise
        """
        auth_url = f"{self.server_url}/_open/auth"
        payload = {
            "username": self.username,
            "password": self.password
        }
        
        try:
            self.logger.info("Authenticating with GenAI API...")
            response = requests.post(auth_url, json=payload, verify=False)
            response.raise_for_status()
            self.jwt_token = response.json().get("jwt")
            
            if not self.jwt_token:
                raise ValueError("Authentication response does not contain a JWT token")
                
            self.logger.info("✓ Authentication successful")
            return True
            
        except Exception as e:
            self.logger.error(f"✗ Authentication failed: {e}")
            return False
            
    def create_project(self, project_name: str, db_name: str, 
                      project_type: str = "Graph",
                      description: str = "GraphRAG Project") -> Optional[Dict]:
        """
        Create a GenAI project
        
        Args:
            project_name: Name of the project
            db_name: Database name
            project_type: Type of project (default: "Graph")
            description: Project description
            
        Returns:
            Project info or None on error
        """
        if not self.jwt_token:
            self.logger.warning("No JWT token, attempting authentication...")
            if not self.authenticate():
                raise RuntimeError("Authentication required but failed")
        
        payload = {
            "project_name": project_name,
            "project_db_name": db_name,
            "project_type": project_type,
            "project_description": description
        }
        
        headers = {
            "Authorization": f"Bearer {self.jwt_token}",
            "Content-Type": "application/json"
        }
        url = f"{self.server_url}/gen-ai/v1/project"
        
        try:
            self.logger.info(f"Creating project '{project_name}' in database '{db_name}'...")
            response = requests.post(url, json=payload, headers=headers, verify=False)
            
            # Check if project already exists (don't fail)
            if response.status_code == 400:
                try:
                    error_detail = response.json()
                    if "already exists" in error_detail.get("message", "").lower():
                        self.logger.info(f"Project '{project_name}' already exists. Continuing...")
                        return {"projectName": project_name, "projectDbName": db_name}
                except:
                    pass
            
            # Raise for other errors
            response.raise_for_status()
            self.logger.info(f"✓ Project '{project_name}' created successfully")
            return response.json()
            
        except Exception as e:
            self.logger.error(f"Failed to create project: {e}")
            raise
            
    def _send_request(self, suffix: str, payload: Dict, method: str = "POST") -> Optional[Dict]:
        """
        Send authenticated HTTP request to GenAI API
        
        Args:
            suffix: API endpoint suffix (e.g., "/gen-ai/v1/service")
            payload: Request body
            method: HTTP method (POST, GET, PUT, DELETE)
            
        Returns:
            Response JSON or None on error
        """
        if not self.jwt_token:
            self.logger.warning("No JWT token, attempting authentication...")
            if not self.authenticate():
                raise RuntimeError("Authentication required but failed")
                
        headers = {
            "Authorization": f"Bearer {self.jwt_token}",
            "Content-Type": "application/json"
        }
        url = f"{self.server_url}{suffix}"
        
        try:
            self.logger.debug(f"Sending {method} request to {suffix}")
            response = requests.request(method, url, json=payload, headers=headers, verify=False)
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request to {url} failed: {e}")
            try:
                error_detail = response.json() if response.content else {}
                self.logger.error(f"Error details: {error_detail}")
            except Exception:
                pass
            raise
            
    def start_service(self, service_name: str, startup_params: Dict) -> Optional[str]:
        """
        Start a GenAI service and return service ID
        
        Args:
            service_name: Name of service (e.g., "arangodb-graphrag-importer")
            startup_params: Service configuration parameters
            
        Returns:
            Service ID (short form without service name prefix) or None on error
        """
        body = {
            "service_name": service_name,
            "env": startup_params
        }
        
        try:
            self.logger.info(f"Starting service: {service_name}...")
            response = self._send_request("/gen-ai/v1/service", body, "POST")
            self.logger.debug(f"start_service raw response: {response}")

            # Extract service ID from response (check both possible locations)
            service_id = response.get("service_id")
            if not service_id and "serviceInfo" in response:
                full_service_id = response["serviceInfo"].get("serviceId")
                if full_service_id:
                    # Strip the known service name prefix to get the unique suffix.
                    # e.g., "arangodb-graphrag-importer-abc123" -> "abc123"
                    # Handles UUID-style suffixes like "abc1-2345-6789" correctly
                    # (unlike split("-")[-1] which would only capture "6789").
                    prefix = f"{service_name}-"
                    if full_service_id.startswith(prefix):
                        service_id = full_service_id[len(prefix):]
                    else:
                        service_id = full_service_id
                        self.logger.warning(
                            f"Service ID '{full_service_id}' does not start with expected "
                            f"prefix '{prefix}'. Using full ID."
                        )

            if not service_id:
                raise ValueError(f"Service start response missing service_id: {response}")

            self.logger.info(f"✓ Service started: {service_id}")
            return service_id
            
        except Exception as e:
            self.logger.error(f"Failed to start service {service_name}: {e}")
            return None
            
    def stop_service(self, service_id: str) -> bool:
        """
        Stop a running service
        
        Args:
            service_id: Full service ID (e.g., "arangodb-graphrag-importer-abc123")
            
        Returns:
            True if stopped successfully, False otherwise
        """
        body = {"service_id": service_id}
        
        try:
            self.logger.info(f"Stopping service: {service_id}...")
            response = self._send_request(f"/gen-ai/v1/service/{service_id}", body, "DELETE")
            self.logger.info(f"✓ Service stopped: {service_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to stop service {service_id}: {e}")
            return False
            
    def list_services(self) -> List[Dict]:
        """
        List all running services
        
        Returns:
            List of service dictionaries with details
        """
        try:
            response = self._send_request("/gen-ai/v1/list_services", {}, "POST")
            services = response.get("services", [])
            
            # Normalize keys for backwards compatibility
            for s in services:
                if 'serviceId' in s:
                    s['service_id'] = s['serviceId']
                if 'genaiProjectName' in s:
                    s['service_name'] = s['genaiProjectName']
                elif 'serviceMeta' in s and 'serviceType' in s['serviceMeta']:
                    s['service_name'] = s['serviceMeta']['serviceType']
                    
            self.logger.info(f"Found {len(services)} running services")
            return services
            
        except Exception as e:
            self.logger.error(f"Failed to list services: {e}")
            return []
            
    def update_service(self, service_id: str, params: Dict) -> bool:
        """
        Update service parameters
        
        Args:
            service_id: Full service ID
            params: Updated parameters
            
        Returns:
            True if updated successfully, False otherwise
        """
        body = {"env": params}
        
        try:
            self.logger.info(f"Updating service: {service_id}...")
            response = self._send_request(f"/gen-ai/v1/service/{service_id}", body, "PUT")
            self.logger.info(f"✓ Service updated: {service_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update service {service_id}: {e}")
            return False
            
    def encode_file_base64(self, file_path: str) -> Optional[str]:
        """
        Encode file content to base64
        
        Args:
            file_path: Path to file
            
        Returns:
            Base64 encoded content or None on error
        """
        try:
            with open(file_path, "rb") as file:
                encoded_content = base64.b64encode(file.read()).decode("utf-8")
                self.logger.debug(f"✓ Encoded file: {file_path}")
                return encoded_content
                
        except FileNotFoundError:
            self.logger.error(f"✗ File not found: {file_path}")
            return None
        except Exception as e:
            self.logger.error(f"✗ Error encoding file {file_path}: {e}")
            return None
            
    def import_document(self, 
                       service_id: str, 
                       file_path: str, 
                       partition_id: str, 
                       entity_types: List[str],
                       chunk_size: int = 1200,
                       enable_embeddings: bool = True) -> Dict:
        """
        Import a document via the Importer service
        
        Args:
            service_id: Importer service ID (short form)
            file_path: Path to document file (will be base64 encoded)
            partition_id: Partition identifier for this document
            entity_types: List of custom entity types to extract
            chunk_size: Maximum tokens per text chunk
            enable_embeddings: Generate embeddings for chunks
            
        Returns:
            Import response dictionary
        """
        # Encode file content
        file_content = self.encode_file_base64(file_path)
        if not file_content:
            raise ValueError(f"Failed to encode file: {file_path}")
            
        file_name = Path(file_path).name
        
        import_body = {
            "file_name": file_name,
            "file_content": file_content,
            "chunk_token_size": chunk_size,
            "enable_chunk_embeddings": enable_embeddings,
            "entity_types": entity_types,
            "partition_id": partition_id
        }
        
        try:
            self.logger.info(f"Importing document: {file_name} (partition: {partition_id})...")
            response = self._send_request(
                f"/graphrag/importer/{service_id}/v1/import",
                import_body,
                "POST"
            )
            self.logger.info(f"✓ Document imported: {file_name}")
            return response
            
        except Exception as e:
            self.logger.error(f"Failed to import document {file_name}: {e}")
            raise
            
    def query_graphrag(self, 
                      service_id: str, 
                      query: str, 
                      query_type: int = 3) -> Dict:
        """
        Query the Retriever service
        
        Args:
            service_id: Retriever service ID (short form)
            query: Question to ask the knowledge graph
            query_type: Query type (1=global, 2=local/deep-search, 3=instant)
            
        Returns:
            Query response dictionary with 'result' field
        """
        query_body = {
            "query": query,
            "query_type": query_type
        }
        
        # Construct full service ID for logging/checking
        full_service_id = f"arangodb-graphrag-retriever-{service_id}"
        
        max_retries = 5
        retry_delay = 10
        
        for attempt in range(max_retries):
            try:
                self.logger.debug(f"Querying GraphRAG (attempt {attempt+1}/{max_retries}): {query[:100]}...")
                response = self._send_request(
                    f"/graphrag/retriever/{service_id}/v1/graphrag-query",
                    query_body,
                    "POST"
                )
                return response
                
            except Exception as e:
                error_msg = str(e)
                if "404" in error_msg and attempt < max_retries - 1:
                    self.logger.warning(f"Retriever {service_id} not ready yet (404). Waiting {retry_delay}s...")
                    time.sleep(retry_delay)
                else:
                    self.logger.error(f"Query failed: {e}")
                    raise
