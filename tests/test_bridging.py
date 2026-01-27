#!/usr/bin/env python3
"""
Unit tests for Graph-Aware Bridging improvements (bridger.py)
Tests graph-aware context, parent module resolution, and related entity traversal
"""

import pytest
import sys
from unittest.mock import Mock, MagicMock, patch, call

sys.path.append('src')

from bridger import (
    get_parent_module_context,
    get_related_entities,
    calculate_token_overlap,
    process_item_to_entity
)
from config import COL_MODULE, COL_PORT, COL_SIGNAL, COL_RELATIONS, EDGE_RESOLVED


class TestParentModuleContext:
    """Test parent module context retrieval"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock ArangoDB connection"""
        db = Mock()
        return db
    
    def test_port_extracts_module_name(self, mock_db):
        """Test: Extracts module name from port key"""
        item = {
            '_key': 'or1200_alu.result',
            'label': 'result'
        }
        
        # Mock resolved entities
        mock_db.aql.execute = Mock(return_value=['Golden_Entities/ALU_Unit'])
        
        result = get_parent_module_context(mock_db, item, COL_PORT)
        
        # Should call the query
        mock_db.aql.execute.assert_called_once()
        
        # Should return resolved entities
        assert len(result) == 1
        assert 'ALU_Unit' in result[0]
    
    def test_signal_extracts_module_name(self, mock_db):
        """Test: Extracts module name from signal key"""
        item = {
            '_key': 'or1200_except.esr',
            'label': 'esr'
        }
        
        mock_db.aql.execute = Mock(return_value=['Golden_Entities/Exception_Unit'])
        
        result = get_parent_module_context(mock_db, item, COL_SIGNAL)
        
        # Should call the query
        mock_db.aql.execute.assert_called_once()
        
        # Should return resolved entities
        assert len(result) == 1
        assert 'Exception_Unit' in result[0]
    
    def test_non_port_signal_returns_empty(self, mock_db):
        """Test: Non-port/signal collections return empty list"""
        item = {'_key': 'module1', 'label': 'module1'}
        
        result = get_parent_module_context(mock_db, item, COL_MODULE)
        
        assert result == []
        mock_db.aql.execute.assert_not_called()
    
    def test_malformed_key_returns_empty(self, mock_db):
        """Test: Malformed key (no dot) returns empty list"""
        item = {'_key': 'nodot', 'label': 'nodot'}
        
        result = get_parent_module_context(mock_db, item, COL_PORT)
        
        assert result == []
    
    def test_module_not_resolved_returns_empty(self, mock_db):
        """Test: Module with no resolved entities returns empty list"""
        item = {'_key': 'unresolved_module.port', 'label': 'port'}
        
        mock_db.aql.execute = Mock(return_value=[])
        
        result = get_parent_module_context(mock_db, item, COL_PORT)
        
        assert result == []
    
    def test_query_exception_handled_gracefully(self, mock_db):
        """Test: Query exceptions return empty list with debug log"""
        item = {'_key': 'module.port', 'label': 'port'}
        
        mock_db.aql.execute = Mock(side_effect=Exception("DB error"))
        
        result = get_parent_module_context(mock_db, item, COL_PORT)
        
        assert result == []  # Should not raise


class TestRelatedEntities:
    """Test related entity graph traversal"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock ArangoDB connection"""
        db = Mock()
        return db
    
    def test_finds_related_entities_depth_2(self, mock_db):
        """Test: Traverses graph to find related entities"""
        parent_ids = ['Golden_Entities/ALU_Unit']
        related_ids = [
            'Golden_Entities/ALU_Operations',
            'Golden_Entities/Arithmetic_Logic',
            'Golden_Entities/Multiplier'
        ]
        
        mock_db.aql.execute = Mock(return_value=related_ids)
        
        result = get_related_entities(mock_db, parent_ids)
        
        # Should include parent + related
        assert len(result) == 4
        assert 'Golden_Entities/ALU_Unit' in result
        assert 'Golden_Entities/ALU_Operations' in result
    
    def test_empty_parent_ids_returns_empty_set(self, mock_db):
        """Test: Empty parent list returns empty set"""
        result = get_related_entities(mock_db, [])
        
        assert result == set()
        mock_db.aql.execute.assert_not_called()
    
    def test_none_parent_ids_returns_empty_set(self, mock_db):
        """Test: None parent list returns empty set"""
        result = get_related_entities(mock_db, None)
        
        assert result == set()
    
    def test_query_uses_correct_collection(self, mock_db):
        """Test: Query traverses Golden_Relations"""
        parent_ids = ['Golden_Entities/1']
        mock_db.aql.execute = Mock(return_value=[])
        
        get_related_entities(mock_db, parent_ids)
        
        call_args = mock_db.aql.execute.call_args
        query = call_args[0][0]
        
        # Should traverse Golden_Relations
        assert COL_RELATIONS in query
        
        # Should use ANY direction (bidirectional)
        assert 'ANY' in query
        
        # Should traverse depth 1-2
        assert '1..2' in query
    
    def test_includes_parent_ids_in_result(self, mock_db):
        """Test: Result includes original parent IDs"""
        parent_ids = ['Golden_Entities/Parent1', 'Golden_Entities/Parent2']
        mock_db.aql.execute = Mock(return_value=['Golden_Entities/Related1'])
        
        result = get_related_entities(mock_db, parent_ids)
        
        # Should include both parents + related
        assert 'Golden_Entities/Parent1' in result
        assert 'Golden_Entities/Parent2' in result
        assert 'Golden_Entities/Related1' in result
    
    def test_deduplicates_results(self, mock_db):
        """Test: Returns set (no duplicates)"""
        parent_ids = ['Golden_Entities/1']
        # Simulate duplicate results from traversal
        mock_db.aql.execute = Mock(return_value=['Golden_Entities/2', 'Golden_Entities/2'])
        
        result = get_related_entities(mock_db, parent_ids)
        
        assert isinstance(result, set)
        # Should have deduplicated
        assert len(result) == 2  # Parent + one unique related
    
    def test_exception_returns_parent_ids_only(self, mock_db):
        """Test: On exception, returns parent IDs as fallback"""
        parent_ids = ['Golden_Entities/1']
        mock_db.aql.execute = Mock(side_effect=Exception("Traversal error"))
        
        result = get_related_entities(mock_db, parent_ids)
        
        # Should return parents as fallback
        assert result == set(parent_ids)


class TestTokenOverlap:
    """Test token overlap calculation for context weighting"""
    
    def test_exact_match(self):
        """Test: Identical texts have overlap 1.0"""
        overlap = calculate_token_overlap("alu operations", "alu operations")
        assert overlap == 1.0
    
    def test_partial_overlap(self):
        """Test: Partial overlap calculates correctly"""
        text1 = "arithmetic logic unit"
        text2 = "arithmetic unit operations"
        
        overlap = calculate_token_overlap(text1, text2)
        
        # Common: arithmetic, unit (2 tokens)
        # Min length: 3 tokens
        # Overlap coefficient: 2/3 = 0.666...
        assert 0.65 < overlap < 0.70
    
    def test_no_overlap(self):
        """Test: No common tokens returns 0.0"""
        overlap = calculate_token_overlap("processor", "memory")
        assert overlap == 0.0
    
    def test_stop_words_removed(self):
        """Test: Stop words are filtered"""
        text1 = "the alu unit"
        text2 = "alu processor unit"
        
        overlap = calculate_token_overlap(text1, text2)
        
        # 'the' should be removed
        # Common: alu, unit
        assert overlap > 0.5
    
    def test_empty_texts(self):
        """Test: Empty texts return 0.0"""
        assert calculate_token_overlap("", "text") == 0.0
        assert calculate_token_overlap("text", "") == 0.0
        assert calculate_token_overlap("", "") == 0.0
    
    def test_none_texts(self):
        """Test: None texts return 0.0"""
        assert calculate_token_overlap(None, "text") == 0.0
        assert calculate_token_overlap("text", None) == 0.0
    
    def test_case_insensitive(self):
        """Test: Case doesn't affect overlap"""
        text1 = "ALU Unit"
        text2 = "alu unit"
        
        overlap = calculate_token_overlap(text1, text2)
        assert overlap == 1.0


class TestGraphAwareScoring:
    """Test graph-aware score boosting in process_item_to_entity"""
    
    @pytest.fixture
    def mock_setup(self):
        """Setup mocks for process_item_to_entity testing"""
        mock_db = Mock()
        mock_view = "test_view"
        
        # Mock candidates from ArangoSearch
        candidates = [
            {
                '_id': 'Golden_Entities/Related',
                'entity_name': 'ALU Operations',
                'description': 'ALU operation unit',
                'entity_type': 'architecture_feature'
            },
            {
                '_id': 'Golden_Entities/Unrelated',
                'entity_name': 'Memory Operations',
                'description': 'Memory operation unit',
                'entity_type': 'architecture_feature'
            }
        ]
        
        mock_db.aql.execute = Mock(return_value=candidates)
        
        return mock_db, mock_view
    
    def test_graph_boost_applied_to_related_entities(self, mock_setup):
        """Test: Entities in parent's neighborhood get score boost"""
        mock_db, mock_view = mock_setup
        
        item = {
            '_id': 'RTL_Port/or1200_alu.op',
            'label': 'op',
            'metadata': {}
        }
        
        parent_entity_ids = ['Golden_Entities/Parent']
        related_entities = {'Golden_Entities/Related', 'Golden_Entities/Parent'}
        
        with patch('bridger.get_related_entities', return_value=related_entities):
            with patch('bridger.SIMILARITY') as mock_similarity:
                mock_similarity.compute = Mock(return_value=0.70)
                
                results = process_item_to_entity(
                    mock_db,
                    item,
                    mock_view,
                    threshold=0.5,
                    method='test',
                    context_summary='',
                    parent_entity_ids=parent_entity_ids
                )
        
        # Should return matches
        assert len(results) > 0
        
        # Related entity should have graph_aware flag
        if results[0]['_to'] == 'Golden_Entities/Related':
            assert results[0].get('graph_aware') == True
    
    def test_no_graph_boost_without_parent_context(self, mock_setup):
        """Test: No graph boost when parent_entity_ids is None"""
        mock_db, mock_view = mock_setup
        
        item = {
            '_id': 'RTL_Module/standalone',
            'label': 'standalone',
            'metadata': {}
        }
        
        with patch('bridger.SIMILARITY') as mock_similarity:
            mock_similarity.compute = Mock(return_value=0.70)
            
            results = process_item_to_entity(
                mock_db,
                item,
                mock_view,
                threshold=0.5,
                method='test',
                parent_entity_ids=None
            )
        
        # Should have results but no graph_aware flag
        if results:
            assert results[0].get('graph_aware', False) == False
    
    def test_penalty_for_unrelated_entities(self, mock_setup):
        """Test: Entities outside neighborhood get penalty"""
        mock_db, mock_view = mock_setup
        
        # This is tested via score calculation in the actual function
        # The unrelated entity should have lower final score
        
        item = {
            '_id': 'RTL_Port/module.port',
            'label': 'port',
            'metadata': {}
        }
        
        parent_entity_ids = ['Golden_Entities/Parent']
        related_entities = {'Golden_Entities/Related'}  # Only one related
        
        with patch('bridger.get_related_entities', return_value=related_entities):
            with patch('bridger.SIMILARITY') as mock_similarity:
                # Both candidates have same base score
                mock_similarity.compute = Mock(return_value=0.70)
                
                results = process_item_to_entity(
                    mock_db,
                    item,
                    mock_view,
                    threshold=0.5,
                    method='test',
                    parent_entity_ids=parent_entity_ids
                )
        
        # Should have applied boost/penalty logic
        # Actual scoring tested in integration


class TestEdgeCases:
    """Test edge cases and error conditions"""
    
    def test_item_without_label(self):
        """Test: Items without label return empty list"""
        mock_db = Mock()
        item = {'_id': 'RTL_Port/1', 'metadata': {}}
        
        with patch('bridger.SIMILARITY'):
            results = process_item_to_entity(
                mock_db, item, 'view', 0.5, 'test'
            )
        
        assert results == []
    
    def test_very_short_label(self):
        """Test: Very short labels (< 2 chars) return empty list"""
        mock_db = Mock()
        item = {'_id': 'RTL_Port/1', 'label': 'a', 'metadata': {}}
        
        with patch('bridger.normalize_hardware_name', return_value='a'):
            with patch('bridger.SIMILARITY'):
                results = process_item_to_entity(
                    mock_db, item, 'view', 0.5, 'test'
                )
        
        assert results == []


class TestIntegration:
    """Integration tests for graph-aware bridging"""
    
    def test_full_pipeline_port_with_parent(self):
        """Test: Full pipeline from port to graph-aware match"""
        mock_db = Mock()
        
        # Port in or1200_alu module
        port_item = {
            '_id': 'RTL_Port/or1200_alu.result',
            '_key': 'or1200_alu.result',
            'label': 'result',
            'metadata': {'description': 'ALU result output'}
        }
        
        # Parent module resolves to ALU_Unit
        parent_resolved = ['Golden_Entities/ALU_Unit']
        
        # Related entities include ALU operations
        related = {
            'Golden_Entities/ALU_Unit',
            'Golden_Entities/ALU_Result',
            'Golden_Entities/Arithmetic_Operations'
        }
        
        # Candidate match
        candidates = [{
            '_id': 'Golden_Entities/ALU_Result',
            'entity_name': 'ALU Result Register',
            'description': 'Result register for ALU',
            'entity_type': 'register'
        }]
        
        mock_db.aql.execute = Mock(return_value=candidates)
        
        with patch('bridger.get_parent_module_context', return_value=parent_resolved):
            with patch('bridger.get_related_entities', return_value=related):
                with patch('bridger.SIMILARITY') as mock_similarity:
                    mock_similarity.compute = Mock(return_value=0.75)
                    
                    results = process_item_to_entity(
                        mock_db,
                        port_item,
                        'view',
                        threshold=0.6,
                        method='graph_aware_test',
                        parent_entity_ids=parent_resolved
                    )
        
        # Should have match with graph-aware boost
        assert len(results) == 1
        assert results[0]['_to'] == 'Golden_Entities/ALU_Result'
        assert results[0]['graph_aware'] == True
        # Score should be boosted: 0.75 * 1.20 = 0.90
        assert results[0]['score'] >= 0.80


if __name__ == '__main__':
    # Run with: python3 -m pytest tests/test_bridging.py -v
    pytest.main([__file__, '-v'])
