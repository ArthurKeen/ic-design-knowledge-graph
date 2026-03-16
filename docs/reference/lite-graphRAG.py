"""
ArangoDB implementation for LightRAG
"""

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from arango import ArangoClient
from arango.database import StandardDatabase
from sentence_transformers import SentenceTransformer

from ..base import BaseGraphStorage
from ..utils import logger


# ============================================================================
# WORKSPACE MANAGEMENT HELPER CLASS - NEW
# ============================================================================

class ArangoDBWorkspaceManager:
    """Helper class for managing workspaces (namespaces) across all storage types"""
    
    def __init__(self, host: str, username: str, password: str, db_name: str):
        self.host = host
        self.username = username
        self.password = password
        self.db_name = db_name
        
        self.client = ArangoClient(hosts=self.host)
        self.db = self.client.db(self.db_name, username=self.username, password=self.password)
        
        logger.info(f"Initialized Workspace Manager for {self.db_name}")
    
    def list_workspaces(self) -> Dict[str, List[str]]:
        """
        List all workspaces (namespaces) in the database.
        Returns a dict mapping workspace names to their collection types.
        """
        try:
            collections = self.db.collections()
            workspaces = {}
            
            for coll in collections:
                coll_name = coll['name']
                
                # Skip system collections
                if coll_name.startswith('_'):
                    continue
                
                # Parse namespace from collection name
                if '_nodes' in coll_name:
                    namespace = coll_name.replace('_nodes', '')
                    workspaces.setdefault(namespace, []).append('graph')
                elif '_edges' in coll_name:
                    namespace = coll_name.replace('_edges', '')
                    workspaces.setdefault(namespace, []).append('graph')
                elif '_kv_store' in coll_name:
                    namespace = coll_name.replace('_kv_store', '')
                    workspaces.setdefault(namespace, []).append('kv')
                elif '_vectors' in coll_name:
                    namespace = coll_name.replace('_vectors', '')
                    workspaces.setdefault(namespace, []).append('vector')
                elif '_doc_status' in coll_name:
                    namespace = coll_name.replace('_doc_status', '')
                    workspaces.setdefault(namespace, []).append('doc_status')
            
            # Deduplicate collection types
            for namespace in workspaces:
                workspaces[namespace] = sorted(list(set(workspaces[namespace])))
            
            logger.info(f"Found {len(workspaces)} workspaces")
            return workspaces
            
        except Exception as e:
            logger.error(f"Error listing workspaces: {e}")
            return {}
    
    def get_workspace_stats(self, namespace: str) -> Dict[str, int]:
        """
        Get statistics for a specific workspace.
        Returns counts of documents in each collection type.
        """
        try:
            stats = {}
            
            collection_suffixes = ['_nodes', '_edges', '_kv_store', '_vectors', '_doc_status']
            
            for suffix in collection_suffixes:
                coll_name = f"{namespace}{suffix}"
                if self.db.has_collection(coll_name):
                    collection = self.db.collection(coll_name)
                    stats[suffix.lstrip('_')] = collection.count()
            
            logger.debug(f"Workspace '{namespace}' stats: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Error getting workspace stats: {e}")
            return {}
    
    def delete_workspace(self, namespace: str, confirm: bool = False) -> bool:
        """
        Delete all collections for a workspace.
        Requires confirm=True for safety.
        """
        if not confirm:
            logger.warning(f"Workspace deletion requires confirm=True. Namespace: {namespace}")
            return False
        
        try:
            deleted_collections = []
            collection_suffixes = ['_nodes', '_edges', '_kv_store', '_vectors', '_doc_status']
            
            for suffix in collection_suffixes:
                coll_name = f"{namespace}{suffix}"
                if self.db.has_collection(coll_name):
                    self.db.delete_collection(coll_name)
                    deleted_collections.append(coll_name)
            
            logger.info(f"Deleted workspace '{namespace}': {deleted_collections}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting workspace: {e}")
            return False


@dataclass
class ArangoDBStorage(BaseGraphStorage):
    """ArangoDB storage backend"""
    
    def __init__(self, namespace, global_config, embedding_func, workspace=None):
        super().__init__(
            namespace=namespace,
            global_config=global_config,
            embedding_func=embedding_func,
            workspace=workspace,
        )
        self.host = os.environ.get("ARANGO_HOST", "http://localhost:8529")
        self.username = os.environ.get("ARANGO_USERNAME", "root")
        self.password = os.environ.get("ARANGO_PASSWORD", "")
        self.db_name = os.environ.get("ARANGO_DATABASE", "_system")
        
        logger.info(f"Initializing ArangoDB at {self.host}")
        
        if embedding_func is None:
            logger.info("Loading embedding model...")
            self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        else:
            self.embedding_model = embedding_func
        
        self.client = ArangoClient(hosts=self.host)
        
        try:
            self.db = self.client.db(
                self.db_name, 
                username=self.username, 
                password=self.password
            )
            self.db.version()
            logger.info("Connected to ArangoDB")
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            raise
        
        self._setup_collections()
    
    def _setup_collections(self):
        nodes_name = f"{self.namespace}_nodes"
        edges_name = f"{self.namespace}_edges"
        
        if not self.db.has_collection(nodes_name):
            self.nodes_collection = self.db.create_collection(nodes_name)
            logger.info(f"Created {nodes_name}")
        else:
            self.nodes_collection = self.db.collection(nodes_name)
        
        if not self.db.has_collection(edges_name):
            self.edges_collection = self.db.create_collection(edges_name, edge=True)
            logger.info(f"Created {edges_name}")
        else:
            self.edges_collection = self.db.collection(edges_name)
        
        self.nodes_name = nodes_name
        self.edges_name = edges_name
        
        try:
            self.nodes_collection.add_hash_index(fields=["label"], unique=False)
        except:
            pass
    
    def _node_key(self, node_id: str) -> str:
        clean_id = re.sub(r'[^a-zA-Z0-9_]', '_', node_id.strip('"'))
        if clean_id and not (clean_id[0].isalpha() or clean_id[0] == '_'):
            clean_id = f"n_{clean_id}"
        return clean_id
    
    async def close(self):
        pass
    
    async def __aexit__(self, exc_type, exc, tb):
        await self.close()
    
    async def index_done_callback(self) -> None:
        pass
    
    async def has_node(self, node_id: str) -> bool:
        try:
            key = self._node_key(node_id)
            return self.nodes_collection.has(key)
        except:
            return False
    
    async def has_edge(self, source_node_id: str, target_node_id: str) -> bool:
        try:
            source_key = self._node_key(source_node_id)
            target_key = self._node_key(target_node_id)
            
            from_ref = f"{self.nodes_name}/{source_key}"
            to_ref = f"{self.nodes_name}/{target_key}"
            
            aql = f"""
            FOR edge IN {self.edges_name}
                FILTER edge._from == @from_ref AND edge._to == @to_ref
                LIMIT 1
                RETURN edge
            """
            cursor = self.db.aql.execute(
                aql,
                bind_vars={"from_ref": from_ref, "to_ref": to_ref}
            )
            return cursor.count() > 0
        except:
            return False
    
    async def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        try:
            key = self._node_key(node_id)
            if self.nodes_collection.has(key):
                node = self.nodes_collection.get(key)
                if node:
                    node.pop("_id", None)
                    node.pop("_key", None)
                    node.pop("_rev", None)
                return node
            return None
        except:
            return None
    
    async def node_degree(self, node_id: str) -> int:
        try:
            key = self._node_key(node_id)
            node_ref = f"{self.nodes_name}/{key}"
            
            aql = f"""
            LET outgoing = (FOR edge IN {self.edges_name} FILTER edge._from == @node RETURN 1)
            LET incoming = (FOR edge IN {self.edges_name} FILTER edge._to == @node RETURN 1)
            RETURN LENGTH(outgoing) + LENGTH(incoming)
            """
            cursor = self.db.aql.execute(aql, bind_vars={"node": node_ref})
            result = list(cursor)
            return result[0] if result else 0
        except:
            return 0
    
    async def edge_degree(self, src_id: str, tgt_id: str) -> int:
        src_degree = await self.node_degree(src_id)
        tgt_degree = await self.node_degree(tgt_id)
        return src_degree + tgt_degree
    
    async def get_edge(self, source_node_id: str, target_node_id: str) -> Optional[Dict[str, Any]]:
        try:
            source_key = self._node_key(source_node_id)
            target_key = self._node_key(target_node_id)
            
            from_ref = f"{self.nodes_name}/{source_key}"
            to_ref = f"{self.nodes_name}/{target_key}"
            
            aql = f"""
            FOR edge IN {self.edges_name}
                FILTER edge._from == @from_ref AND edge._to == @to_ref
                LIMIT 1
                RETURN edge
            """
            cursor = self.db.aql.execute(
                aql,
                bind_vars={"from_ref": from_ref, "to_ref": to_ref}
            )
            
            edges = list(cursor)
            if edges:
                edge = edges[0]
                edge.pop("_id", None)
                edge.pop("_key", None)
                edge.pop("_rev", None)
                edge.pop("_from", None)
                edge.pop("_to", None)
                
                edge.setdefault("weight", 0.0)
                edge.setdefault("source_id", source_node_id)
                edge.setdefault("description", None)
                edge.setdefault("keywords", None)
                
                return edge
            
            return {
                "weight": 0.0,
                "description": None,
                "keywords": None,
                "source_id": None,
            }
        except:
            return {
                "weight": 0.0,
                "description": None,
                "keywords": None,
                "source_id": None,
            }
    
    async def get_node_edges(self, source_node_id: str) -> Optional[List[Tuple[str, str]]]:
        try:
            key = self._node_key(source_node_id)
            node_ref = f"{self.nodes_name}/{key}"
            
            aql = f"""
            FOR edge IN {self.edges_name}
                FILTER edge._from == @node OR edge._to == @node
                LET from_node = DOCUMENT(edge._from)
                LET to_node = DOCUMENT(edge._to)
                RETURN {{from_label: from_node.label, to_label: to_node.label}}
            """
            cursor = self.db.aql.execute(aql, bind_vars={"node": node_ref})
            
            edges = []
            for edge in cursor:
                if edge["from_label"] and edge["to_label"]:
                    edges.append((edge["from_label"], edge["to_label"]))
            
            return edges
        except:
            return []
    
    async def upsert_node(self, node_id: str, node_data: Dict[str, Any]) -> None:
        try:
            key = self._node_key(node_id)
            node_doc = {**node_data, "label": node_id}
            
            self.nodes_collection.insert(
                {"_key": key, **node_doc},
                overwrite=True
            )
            logger.debug(f"Upserted node: {node_id}")
        except Exception as e:
            logger.error(f"Error upserting node: {e}")
            raise
    
    async def upsert_edge(self, source_node_id: str, target_node_id: str, edge_data: Dict[str, Any]) -> None:
        try:
            source_key = self._node_key(source_node_id)
            target_key = self._node_key(target_node_id)
            
            if not self.nodes_collection.has(source_key):
                await self.upsert_node(source_node_id, {})
            if not self.nodes_collection.has(target_key):
                await self.upsert_node(target_node_id, {})
            
            from_ref = f"{self.nodes_name}/{source_key}"
            to_ref = f"{self.nodes_name}/{target_key}"
            
            aql = f"""
            FOR edge IN {self.edges_name}
                FILTER edge._from == @from_ref AND edge._to == @to_ref
                RETURN edge
            """
            cursor = self.db.aql.execute(
                aql,
                bind_vars={"from_ref": from_ref, "to_ref": to_ref}
            )
            
            existing_edges = list(cursor)
            
            edge_doc = {"_from": from_ref, "_to": to_ref, **edge_data}
            
            if existing_edges:
                edge_key = existing_edges[0]["_key"]
                self.edges_collection.update({"_key": edge_key, **edge_doc})
            else:
                self.edges_collection.insert(edge_doc)
            
            logger.debug(f"Upserted edge: {source_node_id} -> {target_node_id}")
        except Exception as e:
            logger.error(f"Error upserting edge: {e}")
            raise
    
    async def get_knowledge_graph(self, node_label: str, max_depth: int = 5):
        try:
            from ..types import KnowledgeGraph, KnowledgeGraphNode, KnowledgeGraphEdge
            result = KnowledgeGraph()
            
            if node_label == "*":
                aql = f"""
                LET nodes = (FOR node IN {self.nodes_name} LIMIT 1000 RETURN node)
                LET edges = (FOR edge IN {self.edges_name} RETURN edge)
                RETURN {{nodes: nodes, edges: edges}}
                """
                cursor = self.db.aql.execute(aql)
            else:
                clean_label = node_label.strip('"')
                aql = f"""
                FOR start IN {self.nodes_name}
                    FILTER start.label LIKE @pattern
                    FOR v, e, p IN 0..@depth ANY start {self.edges_name}
                        RETURN DISTINCT {{node: v, edge: e}}
                """
                cursor = self.db.aql.execute(
                    aql,
                    bind_vars={"pattern": f"%{clean_label}%", "depth": max_depth}
                )
            
            seen_nodes = set()
            seen_edges = set()
            
            for item in cursor:
                if isinstance(item, dict) and "nodes" in item:
                    for node in item["nodes"]:
                        node_key = node["_key"]
                        if node_key not in seen_nodes:
                            result.nodes.append(
                                KnowledgeGraphNode(
                                    id=node_key,
                                    labels=[node.get("label", "")],
                                    properties=dict(node)
                                )
                            )
                            seen_nodes.add(node_key)
                    for edge in item["edges"]:
                        edge_key = edge["_key"]
                        if edge_key not in seen_edges:
                            result.edges.append(
                                KnowledgeGraphEdge(
                                    id=edge_key,
                                    type=edge.get("relationship", "RELATED"),
                                    source=edge["_from"].split("/")[1],
                                    target=edge["_to"].split("/")[1],
                                    properties=dict(edge)
                                )
                            )
                            seen_edges.add(edge_key)
                else:
                    if item.get("node"):
                        node = item["node"]
                        node_key = node["_key"]
                        if node_key not in seen_nodes:
                            result.nodes.append(
                                KnowledgeGraphNode(
                                    id=node_key,
                                    labels=[node.get("label", "")],
                                    properties=dict(node)
                                )
                            )
                            seen_nodes.add(node_key)
                    
                    if item.get("edge") and item["edge"]:
                        edge = item["edge"]
                        edge_key = edge["_key"]
                        if edge_key not in seen_edges:
                            result.edges.append(
                                KnowledgeGraphEdge(
                                    id=edge_key,
                                    type=edge.get("relationship", "RELATED"),
                                    source=edge["_from"].split("/")[1],
                                    target=edge["_to"].split("/")[1],
                                    properties=dict(edge)
                                )
                            )
                            seen_edges.add(edge_key)
            
            logger.info(f"Retrieved graph: {len(result.nodes)} nodes, {len(result.edges)} edges")
            return result
        except:
            from ..types import KnowledgeGraph
            return KnowledgeGraph()
    
    async def get_all_labels(self) -> List[str]:
        try:
            aql = f"""
            FOR node IN {self.nodes_name}
                RETURN DISTINCT node.label
            """
            cursor = self.db.aql.execute(aql)
            return sorted([label for label in cursor if label])
        except:
            return []

    async def delete_node(self, node_id: str) -> None:
        """Delete a node by ID"""
        try:
            key = self._node_key(node_id)
            if self.nodes_collection.has(key):
                # Delete all edges connected to this node first
                node_ref = f"{self.nodes_name}/{key}"
                
                aql = f"""
                FOR edge IN {self.edges_name}
                    FILTER edge._from == @node OR edge._to == @node
                    REMOVE edge IN {self.edges_name}
                """
                self.db.aql.execute(aql, bind_vars={"node": node_ref})
                
                # Delete the node
                self.nodes_collection.delete(key)
                logger.debug(f"Deleted node: {node_id}")
        except Exception as e:
            logger.error(f"Error deleting node {node_id}: {e}")
            raise
    
    async def drop(self) -> None:
        """Drop all collections"""
        try:
            for collection_name in [self.nodes_name, self.edges_name]:
                if self.db.has_collection(collection_name):
                    self.db.delete_collection(collection_name)
                    logger.info(f"Dropped collection: {collection_name}")
        except Exception as e:
            logger.error(f"Error dropping collections: {e}")
            raise

    async def get_all_nodes(self) -> List[Dict[str, Any]]:
        """Get all nodes from the graph"""
        try:
            aql = f"FOR node IN {self.nodes_name} RETURN node"
            cursor = self.db.aql.execute(aql)
            nodes = []
            for node in cursor:
                node.pop("_id", None)
                node.pop("_key", None)
                node.pop("_rev", None)
                nodes.append(node)
            return nodes
        except Exception as e:
            logger.error(f"Error getting all nodes: {e}")
            return []

    async def get_all_edges(self) -> List[Dict[str, Any]]:
        """Get all edges from the graph"""
        try:
            aql = f"FOR edge IN {self.edges_name} RETURN edge"
            cursor = self.db.aql.execute(aql)
            edges = []
            for edge in cursor:
                edge.pop("_id", None)
                edge.pop("_key", None)
                edge.pop("_rev", None)
                edges.append(edge)
            return edges
        except Exception as e:
            logger.error(f"Error getting all edges: {e}")
            return []

    async def remove_nodes(self, node_ids: List[str]) -> None:
        """Remove multiple nodes by their IDs"""
        try:
            for node_id in node_ids:
                await self.delete_node(node_id)
        except Exception as e:
            logger.error(f"Error removing nodes: {e}")
            raise

    async def remove_edges(self, edge_ids: List[Tuple[str, str]]) -> None:
        """Remove multiple edges by their source-target pairs"""
        try:
            for source_id, target_id in edge_ids:
                source_key = self._node_key(source_id)
                target_key = self._node_key(target_id)
                
                from_ref = f"{self.nodes_name}/{source_key}"
                to_ref = f"{self.nodes_name}/{target_key}"
                
                aql = f"""
                FOR edge IN {self.edges_name}
                    FILTER edge._from == @from_ref AND edge._to == @to_ref
                    REMOVE edge IN {self.edges_name}
                """
                self.db.aql.execute(aql, bind_vars={"from_ref": from_ref, "to_ref": to_ref})
        except Exception as e:
            logger.error(f"Error removing edges: {e}")
            raise

    async def get_popular_labels(self, top_k: int = 10) -> List[Tuple[str, int]]:
        """Get the most popular node labels (most connected nodes)"""
        try:
            aql = f"""
            FOR node IN {self.nodes_name}
                LET inbound = LENGTH(FOR v IN 1..1 INBOUND node {self.edges_name} RETURN v)
                LET outbound = LENGTH(FOR v IN 1..1 OUTBOUND node {self.edges_name} RETURN v)
                LET total = inbound + outbound
                SORT total DESC
                LIMIT @top_k
                RETURN {{label: node.label, count: total}}
            """
            cursor = self.db.aql.execute(aql, bind_vars={"top_k": top_k})
            return [(doc["label"], doc["count"]) for doc in cursor if doc.get("label")]
        except Exception as e:
            logger.error(f"Error getting popular labels: {e}")
            return []

    async def search_labels(self, query: str, top_k: int = 10) -> List[str]:
        """Search for node labels matching a query"""
        try:
            # Simple substring search on labels
            aql = f"""
            FOR node IN {self.nodes_name}
                FILTER CONTAINS(LOWER(node.label), LOWER(@query))
                LIMIT @top_k
                RETURN DISTINCT node.label
            """
            cursor = self.db.aql.execute(aql, bind_vars={"query": query, "top_k": top_k})
            return [label for label in cursor if label]
        except Exception as e:
            logger.error(f"Error searching labels: {e}")
            return []
    
    # ========================================================================
    # WORKSPACE MANAGEMENT METHODS - NEW
    # ========================================================================
    
    async def get_current_workspace(self) -> str:
        """Get the current workspace (namespace) name"""
        return self.namespace
    
    async def list_all_workspaces(self) -> Dict[str, List[str]]:
        """List all available workspaces in the database"""
        try:
            manager = ArangoDBWorkspaceManager(
                self.host, self.username, self.password, self.db_name
            )
            return manager.list_workspaces()
        except Exception as e:
            logger.error(f"Error listing workspaces: {e}")
            return {}
    
    async def get_workspace_stats(self) -> Dict[str, int]:
        """Get statistics for the current workspace"""
        try:
            manager = ArangoDBWorkspaceManager(
                self.host, self.username, self.password, self.db_name
            )
            return manager.get_workspace_stats(self.namespace)
        except Exception as e:
            logger.error(f"Error getting workspace stats: {e}")
            return {}



# ============================================================================
# KV STORAGE IMPLEMENTATION
# ============================================================================

from ..base import BaseKVStorage

@dataclass
class ArangoDBKVStorage(BaseKVStorage):
    """ArangoDB Key-Value storage for document chunks and metadata"""
    
    def __init__(self, namespace, global_config, embedding_func, workspace=None):
        super().__init__(
            namespace=namespace,
            global_config=global_config,
            embedding_func=embedding_func,
            workspace=workspace,
        )
        self.host = os.environ.get("ARANGO_HOST", "http://localhost:8529")
        self.username = os.environ.get("ARANGO_USERNAME", "root")
        self.password = os.environ.get("ARANGO_PASSWORD", "")
        self.db_name = os.environ.get("ARANGO_DATABASE", "_system")
        
        logger.info(f"Initializing ArangoDB KV Storage at {self.host}")
        
        self.client = ArangoClient(hosts=self.host)
        
        try:
            self.db = self.client.db(
                self.db_name,
                username=self.username,
                password=self.password
            )
            logger.info("Connected to ArangoDB for KV Storage")
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            raise
        
        self._setup_kv_collection()
    
    def _setup_kv_collection(self):
        """Setup KV collection for document storage"""
        kv_name = f"{self.namespace}_kv_store"
        
        if not self.db.has_collection(kv_name):
            self.kv_collection = self.db.create_collection(kv_name)
            logger.info(f"Created {kv_name}")
        else:
            self.kv_collection = self.db.collection(kv_name)
        
        self.kv_name = kv_name
        
        try:
            self.kv_collection.add_hash_index(fields=["id"], unique=True)
        except:
            pass
    
    def _sanitize_key(self, key: str) -> str:
        """Sanitize key to be ArangoDB-compatible"""
        clean_key = re.sub(r'[^a-zA-Z0-9_\-:.]', '_', str(key))
        if clean_key and not (clean_key[0].isalpha() or clean_key[0] == '_'):
            clean_key = f"kv_{clean_key}"
        return clean_key
    
    async def get_by_id(self, id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a document by ID"""
        try:
            key = self._sanitize_key(id)
            if self.kv_collection.has(key):
                doc = self.kv_collection.get(key)
                if doc:
                    doc.pop("_id", None)
                    doc.pop("_key", None)
                    doc.pop("_rev", None)
                return doc
            return None
        except Exception as e:
            logger.error(f"Error getting document by id {id}: {e}")
            return None
    
    async def get_by_ids(self, ids: List[str]) -> List[Optional[Dict[str, Any]]]:
        """Retrieve multiple documents by IDs"""
        results = []
        for id in ids:
            doc = await self.get_by_id(id)
            results.append(doc)
        return results
    
    async def filter_keys(self, filter_func) -> List[str]:
        """Filter keys based on a filter function"""
        try:
            aql = f"""
            FOR doc IN {self.kv_name}
                RETURN doc
            """
            cursor = self.db.aql.execute(aql)
            
            filtered_keys = []
            for doc in cursor:
                if filter_func(doc.get("id", doc.get("_key"))):
                    filtered_keys.append(doc.get("id", doc.get("_key")))
            
            return filtered_keys
        except Exception as e:
            logger.error(f"Error filtering keys: {e}")
            return []
    
    async def upsert(self, data: Dict[str, Any]) -> None:
        """Insert or update document(s)"""
        try:
            if "id" in data:
                # Single document case
                id = data["id"]
                key = self._sanitize_key(id)
                doc = {"_key": key, **data}
                self.kv_collection.insert(doc, overwrite=True)
                logger.debug(f"Upserted KV document: {id}")
            else:
                # Batch upsert case - data is dict of {id: {content, ...}}
                for doc_id, doc_data in data.items():
                    key = self._sanitize_key(doc_id)
                    # Add the id field to the document data
                    doc = {"_key": key, "id": doc_id, **doc_data}
                    self.kv_collection.insert(doc, overwrite=True)
                    logger.debug(f"Upserted KV document: {doc_id}")
        except Exception as e:
            logger.error(f"Error upserting document: {e}")
            raise
    
    async def index_done_callback(self) -> None:
        """Callback after indexing is done"""
        pass
    
    async def drop(self) -> None:
        """Drop the KV collection"""
        try:
            if self.db.has_collection(self.kv_name):
                self.db.delete_collection(self.kv_name)
                logger.info(f"Dropped collection: {self.kv_name}")
        except Exception as e:
            logger.error(f"Error dropping collection: {e}")
            raise
    
    async def delete(self, key: str) -> None:
        """Delete a document by key"""
        try:
            doc_key = self._sanitize_key(key)
            if self.kv_collection.has(doc_key):
                self.kv_collection.delete(doc_key)
                logger.debug(f"Deleted document: {key}")
        except Exception as e:
            logger.error(f"Error deleting document {key}: {e}")
            raise
    
    async def is_empty(self) -> bool:
        """Check if the collection is empty"""
        try:
            return self.kv_collection.count() == 0
        except Exception as e:
            logger.error(f"Error checking if collection is empty: {e}")
            return True
    
    # ========================================================================
    # WORKSPACE MANAGEMENT METHODS - NEW
    # ========================================================================
    
    async def get_current_workspace(self) -> str:
        """Get the current workspace (namespace) name"""
        return self.namespace
    
    async def list_all_workspaces(self) -> Dict[str, List[str]]:
        """List all available workspaces in the database"""
        try:
            manager = ArangoDBWorkspaceManager(
                self.host, self.username, self.password, self.db_name
            )
            return manager.list_workspaces()
        except Exception as e:
            logger.error(f"Error listing workspaces: {e}")
            return {}
    
    # ========================================================================
    # METADATA FILTERING METHODS - NEW
    # ========================================================================
    
    async def filter_by_metadata(
        self, 
        metadata_filters: Dict[str, Any],
        return_fields: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Filter documents by metadata fields with support for:
        - Exact match: {"user_id": "123", "department": "engineering"}
        - List membership: {"authorized_users": ["user1", "user2"]} - checks if user is IN list
        - Multiple conditions: Combined with AND logic
        
        Args:
            metadata_filters: Dict of field:value pairs to filter by
            return_fields: Optional list of fields to return. If None, returns all fields.
        
        Returns:
            List of documents matching ALL filter criteria (AND logic)
        """
        try:
            if not metadata_filters:
                logger.warning("No metadata filters provided")
                return []
            
            # Build AQL filter conditions
            filter_conditions = []
            bind_vars = {}
            
            for idx, (field, value) in enumerate(metadata_filters.items()):
                var_name = f"val_{idx}"
                
                if isinstance(value, list):
                    filter_conditions.append(
                        f"("
                        f"  (IS_ARRAY(doc.{field}) AND LENGTH(INTERSECTION(@{var_name}, doc.{field})) > 0) OR "
                        f"  (NOT IS_ARRAY(doc.{field}) AND doc.{field} IN @{var_name}) OR "
                        f"  (IS_ARRAY(doc.metadata.{field}) AND LENGTH(INTERSECTION(@{var_name}, doc.metadata.{field})) > 0) OR "
                        f"  (NOT IS_ARRAY(doc.metadata.{field}) AND doc.metadata.{field} IN @{var_name})"
                        f")"
                    )
                    bind_vars[var_name] = value
                else:
                    # Exact match - check both top-level and nested metadata
                    filter_conditions.append(f"(doc.{field} == @{var_name} OR doc.metadata.{field} == @{var_name})")
                    bind_vars[var_name] = value
            
            # Combine conditions with AND
            filter_clause = " AND ".join(filter_conditions)
            
            # Build RETURN clause
            if return_fields:
                return_fields_str = ", ".join([f'"{f}":doc.{f}' for f in return_fields])
                return_clause = f"{{ {return_fields_str} }}"
            else:
                return_clause = "doc"
            
            # Execute query
            aql = f"""
            FOR doc IN {self.kv_name}
                FILTER {filter_clause}
                RETURN {return_clause}
            """
            
            logger.debug(f"Metadata filter AQL: {aql}")
            logger.debug(f"Bind vars: {bind_vars}")
            
            cursor = self.db.aql.execute(aql, bind_vars=bind_vars)
            results = []
            
            for doc in cursor:
                if not return_fields:
                    # Clean up system fields
                    doc.pop("_id", None)
                    doc.pop("_key", None)
                    doc.pop("_rev", None)
                results.append(doc)
            
            logger.info(f"Metadata filter returned {len(results)} documents")
            return results
            
        except Exception as e:
            logger.error(f"Error filtering by metadata: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    async def get_with_metadata(self, ids: List[str]) -> List[Dict[str, Any]]:
        """
        Get documents by IDs with ALL metadata preserved for citations.
        
        Args:
            ids: List of document IDs to retrieve
        
        Returns:
            List of documents with complete metadata
        """
        try:
            results = []
            for doc_id in ids:
                doc = await self.get_by_id(doc_id)
                if doc:
                    results.append(doc)
            
            logger.debug(f"Retrieved {len(results)} documents with metadata")
            return results
            
        except Exception as e:
            logger.error(f"Error getting documents with metadata: {e}")
            return []
    
    
    async def drop(self) -> None:
        """Drop the entire KV collection"""
        try:
            if self.db.has_collection(self.kv_name):
                self.db.delete_collection(self.kv_name)
                logger.info(f"Dropped collection: {self.kv_name}")
        except Exception as e:
            logger.error(f"Error dropping collection: {e}")
            raise


# ============================================================================
# VECTOR STORAGE IMPLEMENTATION
# ============================================================================

from ..base import BaseVectorStorage

@dataclass
class ArangoDBVectorStorage(BaseVectorStorage):
    """ArangoDB Vector storage for embeddings and similarity search"""
    
    def __init__(self, namespace, global_config, embedding_func, meta_fields=None, workspace=None):
        super().__init__(
            namespace=namespace,
            global_config=global_config,
            embedding_func=embedding_func,
            meta_fields=meta_fields or {},
            workspace=workspace,
        )
        self.host = os.environ.get("ARANGO_HOST", "http://localhost:8529")
        self.username = os.environ.get("ARANGO_USERNAME", "root")
        self.password = os.environ.get("ARANGO_PASSWORD", "")
        self.db_name = os.environ.get("ARANGO_DATABASE", "_system")
        
        logger.info(f"Initializing ArangoDB Vector Storage at {self.host}")
        
        if embedding_func is None:
            logger.info("Loading embedding model for vector storage...")
            self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        else:
            self.embedding_model = embedding_func
        
        self.client = ArangoClient(hosts=self.host)
        
        try:
            self.db = self.client.db(
                self.db_name,
                username=self.username,
                password=self.password
            )
            logger.info("Connected to ArangoDB for Vector Storage")
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            raise
        
        self._setup_vector_collection()
    
    def _setup_vector_collection(self):
        """Setup vector collection for embeddings"""
        vector_name = f"{self.namespace}_vectors"
        
        if not self.db.has_collection(vector_name):
            self.vector_collection = self.db.create_collection(vector_name)
            logger.info(f"Created {vector_name}")
        else:
            self.vector_collection = self.db.collection(vector_name)
        
        self.vector_name = vector_name
        
        try:
            self.vector_collection.add_hash_index(fields=["id"], unique=True)
        except:
            pass
    
    def _sanitize_key(self, key: str) -> str:
        """Sanitize key to be ArangoDB-compatible"""
        clean_key = re.sub(r'[^a-zA-Z0-9_\-:.]', '_', str(key))
        if clean_key and not (clean_key[0].isalpha() or clean_key[0] == '_'):
            clean_key = f"vec_{clean_key}"
        return clean_key
    
    async def upsert(self, data: Dict[str, Any]) -> None:
        """Insert or update vector embedding(s)"""
        try:
            # Ensure we have SentenceTransformer
            if not isinstance(self.embedding_model, SentenceTransformer):
                logger.warning("Falling back to SentenceTransformer")
                self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            
            if "id" in data:
                # Single document case
                id = data["id"]
                key = self._sanitize_key(id)
                
                if "embedding" not in data or data["embedding"] is None:
                    content = data.get("content", "") or data.get("entity_name", "") or data.get("text", "")
                    if content:
                        # ALWAYS use SentenceTransformer directly
                        embedding = self.embedding_model.encode(content)
                        # embedding is numpy array, shape (384,) or (1536,)
                        data["embedding"] = embedding.tolist()
                        logger.info(f"✅ Generated embedding size {len(embedding)} for {id}")
                else:
                    # Convert existing embedding to list if it's a numpy array
                    if isinstance(data["embedding"], np.ndarray):
                        data["embedding"] = data["embedding"].tolist()
                
                doc = {"_key": key, **data}
                self.vector_collection.insert(doc, overwrite=True)
            else:
                # Batch upsert case
                for vec_id, vec_data in data.items():
                    key = self._sanitize_key(vec_id)
                    
                    if "embedding" not in vec_data or vec_data["embedding"] is None:
                        content = vec_data.get("content", "") or vec_data.get("entity_name", "") or vec_data.get("text", "")
                        if content:
                            # ALWAYS use SentenceTransformer directly
                            embedding = self.embedding_model.encode(content)
                            # embedding is numpy array, shape (384,) or (1536,)
                            vec_data["embedding"] = embedding.tolist()
                            logger.info(f"✅ Generated embedding size {len(embedding)} for {vec_id}")
                    else:
                        # Convert existing embedding to list if it's a numpy array
                        if isinstance(vec_data["embedding"], np.ndarray):
                            vec_data["embedding"] = vec_data["embedding"].tolist()
                    
                    doc = {"_key": key, "id": vec_id, **vec_data}
                    self.vector_collection.insert(doc, overwrite=True)
        except Exception as e:
            logger.error(f"Error upserting vector: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise
    
    async def query(self, query: str, top_k: int = 10, query_embedding: Optional[np.ndarray] = None) -> List[Dict[str, Any]]:
        """Query vectors by similarity to query text or embedding"""
        try:
            # Use provided embedding or generate from query text
            if query_embedding is not None:
                # Handle different input shapes
                if isinstance(query_embedding, np.ndarray):
                    # Flatten to 1D if needed
                    if query_embedding.ndim > 1:
                        query_embedding = query_embedding.flatten()
                    query_embedding_list = query_embedding.tolist()
                elif isinstance(query_embedding, list):
                    # If it's a list of lists, take the first element (not concatenate!)
                    if query_embedding and isinstance(query_embedding[0], list):
                        query_embedding_list = query_embedding[0]  # Take first embedding, not flatten all
                    else:
                        query_embedding_list = query_embedding
                else:
                    query_embedding_list = query_embedding
            else:
                # Generate embedding from query text
                if isinstance(self.embedding_model, SentenceTransformer):
                    query_embedding = self.embedding_model.encode(query)
                else:
                    query_embedding = await self.embedding_model(query)
                
                if isinstance(query_embedding, np.ndarray):
                    # Flatten to 1D if needed
                    if query_embedding.ndim > 1:
                        query_embedding = query_embedding.flatten()
                    query_embedding_list = query_embedding.tolist()
                else:
                    query_embedding_list = query_embedding
            
            # Fetch ALL vectors from collection
            aql = f"""
            FOR doc IN {self.vector_name}
                RETURN doc
            """
            cursor = self.db.aql.execute(aql)
            
            results = []
            query_vec = np.array(query_embedding_list).flatten()  # Ensure 1D
            
            for doc in cursor:
                if "embedding" in doc and doc["embedding"]:
                    doc_embedding = np.array(doc["embedding"]).flatten()  # Ensure 1D
                    
                    # Now both are guaranteed to be 1D arrays
                    similarity = np.dot(query_vec, doc_embedding) / (
                        np.linalg.norm(query_vec) * np.linalg.norm(doc_embedding) + 1e-10
                    )
                    
                    doc["similarity"] = float(similarity)
                    doc.pop("_id", None)
                    doc.pop("_key", None)
                    doc.pop("_rev", None)
                    results.append(doc)
            
            # Sort by similarity (highest first) and return top_k
            results.sort(key=lambda x: x.get("similarity", 0), reverse=True)
            
            # Debug logging
            if results:
                logger.info(f"✅ Vector query found {len(results)} results, top similarity: {results[0].get('similarity', 0):.4f}")
            else:
                logger.warning(f"⚠️ Vector query found NO results")
            
            return results[:top_k]
            
        except Exception as e:
            logger.error(f"Error querying vectors: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    async def index_done_callback(self) -> None:
        """Callback after indexing is done"""
        pass

    async def drop(self) -> None:
        """Drop the vector collection"""
        try:
            if self.db.has_collection(self.vector_name):
                self.db.delete_collection(self.vector_name)
                logger.info(f"Dropped collection: {self.vector_name}")
        except Exception as e:
            logger.error(f"Error dropping collection: {e}")
            raise
    
    async def delete(self, key: str) -> None:
        """Delete a vector by key"""
        try:
            doc_key = self._sanitize_key(key)
            if self.vector_collection.has(doc_key):
                self.vector_collection.delete(doc_key)
                logger.debug(f"Deleted vector: {key}")
        except Exception as e:
            logger.error(f"Error deleting vector {key}: {e}")
            raise
    
    async def is_empty(self) -> bool:
        """Check if the collection is empty"""
        try:
            return self.vector_collection.count() == 0
        except Exception as e:
            logger.error(f"Error checking if collection is empty: {e}")
            return True
    
    async def get_by_id(self, id: str) -> Optional[Dict[str, Any]]:
        """Get a vector document by ID"""
        try:
            key = self._sanitize_key(id)
            if self.vector_collection.has(key):
                doc = self.vector_collection.get(key)
                if doc:
                    doc.pop("_id", None)
                    doc.pop("_key", None)
                    doc.pop("_rev", None)
                    return doc
            return None
        except Exception as e:
            logger.error(f"Error getting vector by id {id}: {e}")
            return None
    
    async def get_by_ids(self, ids: List[str]) -> List[Optional[Dict[str, Any]]]:
        """Get multiple vector documents by IDs"""
        results = []
        for id in ids:
            doc = await self.get_by_id(id)
            results.append(doc)
        return results
    
    async def get_vectors_by_ids(self, ids: List[str]) -> List[Optional[np.ndarray]]:
        """Get vector embeddings by IDs"""
        vectors = []
        for id in ids:
            doc = await self.get_by_id(id)
            if doc and "embedding" in doc:
                embedding = doc["embedding"]
                if isinstance(embedding, list):
                    vectors.append(np.array(embedding, dtype=np.float32))
                else:
                    vectors.append(embedding)
            else:
                vectors.append(None)
        return vectors
    
    # ========================================================================
    # WORKSPACE MANAGEMENT METHODS - NEW
    # ========================================================================
    
    async def get_current_workspace(self) -> str:
        """Get the current workspace (namespace) name"""
        return self.namespace
    
    async def list_all_workspaces(self) -> Dict[str, List[str]]:
        """List all available workspaces in the database"""
        try:
            manager = ArangoDBWorkspaceManager(
                self.host, self.username, self.password, self.db_name
            )
            return manager.list_workspaces()
        except Exception as e:
            logger.error(f"Error listing workspaces: {e}")
            return {}
    
    async def get_workspace_stats(self) -> Dict[str, int]:
        """Get statistics for the current workspace"""
        try:
            manager = ArangoDBWorkspaceManager(
                self.host, self.username, self.password, self.db_name
            )
            return manager.get_workspace_stats(self.namespace)
        except Exception as e:
            logger.error(f"Error getting workspace stats: {e}")
            return {}
    
    # ========================================================================
    # METADATA FILTERING METHODS - NEW
    # ========================================================================
    
    async def filter_by_metadata(
        self,
        metadata_filters: Dict[str, Any],
        return_fields: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Filter vector documents by metadata fields with support for:
        - Exact match: {"user_id": "123", "department": "engineering"}
        - List membership: {"authorized_users": ["user1", "user2"]} - checks if value is IN list
        - Multiple conditions: Combined with AND logic
        
        Args:
            metadata_filters: Dict of field:value pairs to filter by
            return_fields: Optional list of fields to return. If None, returns all fields.
        
        Returns:
            List of vector documents matching ALL filter criteria (AND logic)
        """
        try:
            if not metadata_filters:
                logger.warning("No metadata filters provided")
                return []
            
            # Build AQL filter conditions
            filter_conditions = []
            bind_vars = {}
            
            for idx, (field, value) in enumerate(metadata_filters.items()):
                var_name = f"val_{idx}"
                
                if isinstance(value, list):
                    # List membership check
                    filter_conditions.append(f"doc.{field} IN @{var_name}")
                    bind_vars[var_name] = value
                else:
                    # Exact match
                    filter_conditions.append(f"doc.{field} == @{var_name}")
                    bind_vars[var_name] = value
            
            filter_clause = " AND ".join(filter_conditions)
            
            # Build RETURN clause
            if return_fields:
                return_fields_str = ", ".join([f'\"{ f}\":doc.{f}' for f in return_fields])
                return_clause = f"{{ {return_fields_str} }}"
            else:
                return_clause = "doc"
            
            aql = f"""
            FOR doc IN {self.vector_name}
                FILTER {filter_clause}
                RETURN {return_clause}
            """
            
            logger.debug(f"Vector metadata filter AQL: {aql}")
            logger.debug(f"Bind vars: {bind_vars}")
            
            cursor = self.db.aql.execute(aql, bind_vars=bind_vars)
            results = []
            
            for doc in cursor:
                if not return_fields:
                    doc.pop("_id", None)
                    doc.pop("_key", None)
                    doc.pop("_rev", None)
                results.append(doc)
            
            logger.info(f"Vector metadata filter returned {len(results)} documents")
            return results
            
        except Exception as e:
            logger.error(f"Error filtering vectors by metadata: {e}")
            return []
    
    async def query_with_metadata_filter(
        self,
        query: str,
        metadata_filters: Dict[str, Any],
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Query vectors by similarity AND metadata filters.
        First filters by metadata, then performs similarity search on filtered results.
        
        Args:
            query: Query text for similarity search
            metadata_filters: Metadata filters to apply before similarity search
            top_k: Number of top results to return
        
        Returns:
            List of documents sorted by similarity, filtered by metadata
        """
        try:
            # Generate query embedding
            if isinstance(self.embedding_model, SentenceTransformer):
                query_embedding = self.embedding_model.encode(query)
            else:
                query_embedding = await self.embedding_model(query)
            
            if isinstance(query_embedding, np.ndarray):
                query_embedding = query_embedding.tolist()
            
            # Build metadata filter conditions
            filter_conditions = []
            bind_vars = {"query_emb": query_embedding}
            
            for idx, (field, value) in enumerate(metadata_filters.items()):
                var_name = f"val_{idx}"
                
                if isinstance(value, list):
                    filter_conditions.append(f"doc.{field} IN @{var_name}")
                    bind_vars[var_name] = value
                else:
                    filter_conditions.append(f"doc.{field} == @{var_name}")
                    bind_vars[var_name] = value
            
            filter_clause = " AND ".join(filter_conditions) if filter_conditions else "true"
            
            # Query with metadata filtering
            aql = f"""
            FOR doc IN {self.vector_name}
                FILTER {filter_clause}
                RETURN doc
            """
            
            logger.debug(f"Query with metadata filter: {aql}")
            cursor = self.db.aql.execute(aql, bind_vars=bind_vars)
            
            # Calculate similarities
            results = []
            query_vec = np.array(query_embedding)
            
            for doc in cursor:
                if "embedding" in doc:
                    doc_embedding = np.array(doc["embedding"])
                    
                    similarity = np.dot(query_vec, doc_embedding) / (
                        np.linalg.norm(query_vec) * np.linalg.norm(doc_embedding)
                    )
                    
                    doc["similarity"] = float(similarity)
                    doc.pop("_id", None)
                    doc.pop("_key", None)
                    doc.pop("_rev", None)
                    results.append(doc)
            
            # Sort by similarity and return top_k
            results.sort(key=lambda x: x.get("similarity", 0), reverse=True)
            top_results = results[:top_k]
            
            logger.info(f"Query with filters returned {len(top_results)} results from {len(results)} filtered documents")
            return top_results
            
        except Exception as e:
            logger.error(f"Error querying with metadata filter: {e}")
            return []
    
    
    async def delete_entity(self, entity_name: str) -> None:
        """Delete an entity from vector storage"""
        try:
            key = self._sanitize_key(entity_name)
            if self.vector_collection.has(key):
                self.vector_collection.delete(key)
                logger.debug(f"Deleted vector entity: {entity_name}")
        except Exception as e:
            logger.error(f"Error deleting entity: {e}")
            raise
    
    async def delete_entity_relation(self, entity_name: str, relation_name: str) -> None:
        """Delete an entity relation from vector storage"""
        try:
            relation_key = f"{entity_name}_{relation_name}"
            key = self._sanitize_key(relation_key)
            if self.vector_collection.has(key):
                self.vector_collection.delete(key)
                logger.debug(f"Deleted vector relation: {relation_key}")
        except Exception as e:
            logger.error(f"Error deleting entity relation: {e}")
            raise
    
    async def drop(self) -> None:
        """Drop the entire vector collection"""
        try:
            if self.db.has_collection(self.vector_name):
                self.db.delete_collection(self.vector_name)
                logger.info(f"Dropped collection: {self.vector_name}")
        except Exception as e:
            logger.error(f"Error dropping collection: {e}")
            raise


# ============================================================================
# DOCUMENT STATUS STORAGE IMPLEMENTATION
# ============================================================================

from ..base import DocStatus, DocProcessingStatus, DocStatusStorage

@dataclass
class ArangoDBDocStatusStorage(DocStatusStorage):
    """ArangoDB Document Status storage for tracking processed documents"""
    
    def __init__(self, namespace, global_config, embedding_func=None, workspace=None):
        super().__init__(
            namespace=namespace,
            global_config=global_config,
            embedding_func=embedding_func,
            workspace=workspace,
        ) 
        self.host = os.environ.get("ARANGO_HOST", "http://localhost:8529")
        self.username = os.environ.get("ARANGO_USERNAME", "root")
        self.password = os.environ.get("ARANGO_PASSWORD", "")
        self.db_name = os.environ.get("ARANGO_DATABASE", "_system")
        
        logger.info(f"Initializing ArangoDB Doc Status Storage at {self.host}")
        
        self.client = ArangoClient(hosts=self.host)
        
        try:
            self.db = self.client.db(
                self.db_name,
                username=self.username,
                password=self.password
            )
            logger.info("Connected to ArangoDB for Doc Status Storage")
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            raise
        
        self._setup_doc_status_collection()
    
    def _setup_doc_status_collection(self):
        """Setup doc status collection"""
        status_name = f"{self.namespace}_doc_status"
        
        if not self.db.has_collection(status_name):
            self.status_collection = self.db.create_collection(status_name)
            logger.info(f"Created {status_name}")
        else:
            self.status_collection = self.db.collection(status_name)
        
        self.status_name = status_name
        
        try:
            self.status_collection.add_hash_index(fields=["doc_id"], unique=True)
            self.status_collection.add_hash_index(fields=["status"], unique=False)
        except:
            pass
    
    def _sanitize_key(self, key: str) -> str:
        """Sanitize key to be ArangoDB-compatible"""
        clean_key = re.sub(r'[^a-zA-Z0-9_\-:.]', '_', str(key))
        if clean_key and not (clean_key[0].isalpha() or clean_key[0] == '_'):
            clean_key = f"doc_{clean_key}"
        return clean_key
    
    async def get_docs_by_status(self, status: DocStatus) -> dict[str, DocProcessingStatus]:
        """Get all document IDs with a specific status"""
        try:
            # Handle both DocStatus enum and string
            status_value = status.value if hasattr(status, 'value') else status
            
            aql = f"""
            FOR doc IN {self.status_name}
                FILTER doc.status == @status
                RETURN doc
            """
            cursor = self.db.aql.execute(aql, bind_vars={"status": status_value})
            result = {}
            for doc in cursor:
                try:
                    doc_id = doc.get("doc_id")
                    if doc_id:
                        # Create DocProcessingStatus from the metadata
                        metadata = doc.get("metadata", {})
                        
                        # Remove fields that aren't part of DocProcessingStatus
                        metadata.pop('content', None)
                        
                        # Ensure required fields are present
                        if "status" not in metadata:
                            metadata["status"] = doc.get("status", status_value)
                        
                        # Ensure file_path is present (required field)
                        if "file_path" not in metadata:
                            metadata["file_path"] = metadata.get("source", doc_id)  # Use source or doc_id as fallback
                        
                        result[doc_id] = DocProcessingStatus(**metadata)
                except Exception as e:
                    logger.error(f"Error creating DocProcessingStatus for {doc.get('doc_id')}: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
            return result
        except Exception as e:
            logger.error(f"Error getting docs by status: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {}
    
    async def upsert_doc_status(self, doc_id: str, status: str, metadata: Dict[str, Any] = None) -> None:
        """Update or insert document status"""
        try:
            key = self._sanitize_key(doc_id)
            
            doc = {
                "_key": key,
                "doc_id": doc_id,
                "status": status,
                "metadata": metadata or {},
                "updated_at": __import__('datetime').datetime.utcnow().isoformat(),
            }
            
            self.status_collection.insert(doc, overwrite=True)
            logger.debug(f"Upserted doc status: {doc_id} -> {status}")
        except Exception as e:
            logger.error(f"Error upserting doc status: {e}")
            raise
    
    async def get_doc_status(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific document"""
        try:
            key = self._sanitize_key(doc_id)
            if self.status_collection.has(key):
                doc = self.status_collection.get(key)
                if doc:
                    doc.pop("_id", None)
                    doc.pop("_key", None)
                    doc.pop("_rev", None)
                return doc
            return None
        except Exception as e:
            logger.error(f"Error getting doc status: {e}")
            return None
    
    async def get_by_id(self, id: str) -> Optional[Dict[str, Any]]:
        """Get document by ID (required by BaseKVStorage)"""
        return await self.get_doc_status(id)
    
    async def get_by_ids(self, ids: List[str]) -> List[Optional[Dict[str, Any]]]:
        """Get multiple documents by IDs"""
        results = []
        for id in ids:
            doc = await self.get_doc_status(id)
            results.append(doc)
        return results
    
    async def filter_keys(self, keys: set[str]) -> set[str]:
        """Return keys that are not in storage"""
        try:
            existing_keys = set()
            for key in keys:
                if await self.get_doc_status(key):
                    existing_keys.add(key)
            return keys - existing_keys
        except Exception as e:
            logger.error(f"Error filtering keys: {e}")
            return keys
    
    async def get_status_counts(self) -> Dict[str, int]:
        """Get counts of documents in each status"""
        try:
            from ..base import DocStatus
            counts = {status.value: 0 for status in DocStatus}
            
            aql = f"""
            FOR doc IN {self.status_name}
                COLLECT status = doc.status WITH COUNT INTO count
                RETURN {{status: status, count: count}}
            """
            cursor = self.db.aql.execute(aql)
            
            for item in cursor:
                counts[item["status"]] = item["count"]
            
            return counts
        except Exception as e:
            logger.error(f"Error getting status counts: {e}")
            return {}
    
    async def upsert(self, data: Dict[str, Dict[str, Any]]) -> None:
        """Upsert multiple documents (required by BaseKVStorage)"""
        try:
            for doc_id, doc_data in data.items():
                status = doc_data.get("status", "pending")
                metadata = {k: v for k, v in doc_data.items() if k != "status"}
                await self.upsert_doc_status(doc_id, status, metadata)
        except Exception as e:
            logger.error(f"Error upserting documents: {e}")
            raise
    
    async def index_done_callback(self) -> None:
        """Callback after indexing is done"""
        pass

    async def index_done_callback(self) -> None:
        """Callback after indexing is done"""
        pass
    
    async def drop(self) -> None:
        """Drop the doc status collection"""
        try:
            if self.db.has_collection(self.status_name):
                self.db.delete_collection(self.status_name)
                logger.info(f"Dropped collection: {self.status_name}")
        except Exception as e:
            logger.error(f"Error dropping collection: {e}")
            raise
    
    async def delete(self, key: str) -> None:
        """Delete a document status by key"""
        try:
            doc_key = self._sanitize_key(key)
            if self.status_collection.has(doc_key):
                self.status_collection.delete(doc_key)
                logger.debug(f"Deleted doc status: {key}")
        except Exception as e:
            logger.error(f"Error deleting doc status {key}: {e}")
            raise
    
    async def is_empty(self) -> bool:
        """Check if the collection is empty"""
        try:
            return self.status_collection.count() == 0
        except Exception as e:
            logger.error(f"Error checking if collection is empty: {e}")
            return True

    async def get_all_status_counts(self) -> Dict[str, int]:
        """Get counts of all document statuses"""
        return await self.get_status_counts()
    
    async def get_doc_by_file_path(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Get document status by file path"""
        try:
            aql = f"""
            FOR doc IN {self.status_name}
                FILTER doc.metadata.file_path == @file_path
                RETURN doc
            """
            cursor = self.db.aql.execute(aql, bind_vars={"file_path": file_path})
            
            for doc in cursor:
                doc.pop("_id", None)
                doc.pop("_key", None)
                doc.pop("_rev", None)
                return doc
            return None
        except Exception as e:
            logger.error(f"Error getting doc by file path: {e}")
            return None
    
    async def get_docs_by_track_id(self, track_id: str) -> List[Dict[str, Any]]:
        """Get all documents with a specific track_id"""
        try:
            aql = f"""
            FOR doc IN {self.status_name}
                FILTER doc.metadata.track_id == @track_id
                RETURN doc
            """
            cursor = self.db.aql.execute(aql, bind_vars={"track_id": track_id})
            
            results = []
            for doc in cursor:
                doc.pop("_id", None)
                doc.pop("_key", None)
                doc.pop("_rev", None)
                results.append(doc)
            return results
        except Exception as e:
            logger.error(f"Error getting docs by track_id: {e}")
            return []
    
    async def get_docs_paginated(
        self, 
        offset: int = 0, 
        limit: int = 100, 
        status: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get documents with pagination"""
        try:
            # Build query with optional status filter
            if status:
                aql = f"""
                LET total = LENGTH(
                    FOR doc IN {self.status_name}
                        FILTER doc.status == @status
                        RETURN 1
                )
                LET docs = (
                    FOR doc IN {self.status_name}
                        FILTER doc.status == @status
                        SORT doc.updated_at DESC
                        LIMIT @offset, @limit
                        RETURN doc
                )
                RETURN {{docs: docs, total: total}}
                """
                bind_vars = {"status": status, "offset": offset, "limit": limit}
            else:
                aql = f"""
                LET total = LENGTH(FOR doc IN {self.status_name} RETURN 1)
                LET docs = (
                    FOR doc IN {self.status_name}
                        SORT doc.updated_at DESC
                        LIMIT @offset, @limit
                        RETURN doc
                )
                RETURN {{docs: docs, total: total}}
                """
                bind_vars = {"offset": offset, "limit": limit}
            
            cursor = self.db.aql.execute(aql, bind_vars=bind_vars)
            result = next(cursor, {"docs": [], "total": 0})
            
            docs = []
            for doc in result.get("docs", []):
                doc.pop("_id", None)
                doc.pop("_key", None)
                doc.pop("_rev", None)
                docs.append(doc)
            
            return docs, result.get("total", 0)
        except Exception as e:
            logger.error(f"Error getting paginated docs: {e}")
            return [], 0
    
    # ========================================================================
    # WORKSPACE MANAGEMENT METHODS - NEW
    # ========================================================================
    
    async def get_current_workspace(self) -> str:
        """Get the current workspace (namespace) name"""
        return self.namespace
    
    async def list_all_workspaces(self) -> Dict[str, List[str]]:
        """List all available workspaces in the database"""
        try:
            manager = ArangoDBWorkspaceManager(
                self.host, self.username, self.password, self.db_name
            )
            return manager.list_workspaces()
        except Exception as e:
            logger.error(f"Error listing workspaces: {e}")
            return {}
    
    async def get_workspace_stats(self) -> Dict[str, int]:
        """Get statistics for the current workspace"""
        try:
            manager = ArangoDBWorkspaceManager(
                self.host, self.username, self.password, self.db_name
            )
            return manager.get_workspace_stats(self.namespace)
        except Exception as e:
            logger.error(f"Error getting workspace stats: {e}")
            return {}
    
    
    async def drop(self) -> None:
        """Drop the entire doc status collection"""
        try:
            if self.db.has_collection(self.status_name):
                self.db.delete_collection(self.status_name)
                logger.info(f"Dropped collection: {self.status_name}")
        except Exception as e:
            logger.error(f"Error dropping collection: {e}")
            raise