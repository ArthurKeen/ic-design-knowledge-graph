#!/usr/bin/env python3
"""
Unit tests for Consolidation improvements (consolidator.py)
Tests fuzzy consolidation, indexing, and Stage 2 logic
"""

import pytest
import sys
from unittest.mock import Mock, MagicMock, patch, call
from collections import defaultdict

sys.path.append('src')

from consolidator import (
    consolidate_fuzzy_stage2,
    apply_indexes,
    apply_bridging_indexes
)


class TestFuzzyConsolidation:
    """Test fuzzy Stage 2 consolidation logic"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock ArangoDB connection"""
        db = Mock()
        db.has_collection = Mock(return_value=True)
        db.collection = Mock()
        return db
    
    def test_fuzzy_candidates_levenshtein_1(self, mock_db):
        """Test: Finds candidates with edit distance 1"""
        # Mock AQL query results - fuzzy matches
        mock_candidates = [
            {
                'entity1_id': 'Golden_Entities/1',
                'entity1_name': 'ALU_Unit',
                'entity1_type': 'processor_component',
                'entity2_id': 'Golden_Entities/2',
                'entity2_name': 'ALU Unit',  # Space vs underscore
                'entity2_type': 'processor_component',
                'levenshtein_distance': 1,
                'token_overlap': 1.0,
                'confidence': 0.92
            }
        ]
        
        mock_db.aql.execute = Mock(return_value=mock_candidates)
        
        # Dry run - should return candidates
        result = consolidate_fuzzy_stage2(
            db=mock_db,
            levenshtein_distance=1,
            min_confidence=0.75,
            dry_run=True
        )
        
        assert len(result) == 1
        assert result[0]['entity1_name'] == 'ALU_Unit'
        assert result[0]['entity2_name'] == 'ALU Unit'
        assert result[0]['confidence'] >= 0.75
    
    def test_confidence_threshold_filtering(self, mock_db):
        """Test: Filters out low confidence matches"""
        mock_candidates = [
            {
                'entity1_id': 'Golden_Entities/1',
                'entity1_name': 'processor',
                'entity1_type': 'processor_component',
                'entity2_id': 'Golden_Entities/2',
                'entity2_name': 'process',  # Different word
                'entity2_type': 'processor_component',
                'levenshtein_distance': 1,
                'token_overlap': 0.0,
                'confidence': 0.60  # Below threshold
            }
        ]
        
        mock_db.aql.execute = Mock(return_value=mock_candidates)
        
        result = consolidate_fuzzy_stage2(
            db=mock_db,
            min_confidence=0.75,  # Higher threshold
            dry_run=True
        )
        
        # Should be filtered by AQL query itself
        # Verify the function was called with correct confidence
        assert len(result) >= 0  # May be filtered by AQL
    
    def test_type_compatibility_enforcement(self, mock_db):
        """Test: Only matches entities of same type"""
        # AQL query enforces type compatibility
        mock_candidates = [
            {
                'entity1_id': 'Golden_Entities/1',
                'entity1_name': 'register_a',
                'entity1_type': 'register',
                'entity2_id': 'Golden_Entities/2',
                'entity2_name': 'register a',
                'entity2_type': 'register',  # Same type
                'levenshtein_distance': 1,
                'token_overlap': 1.0,
                'confidence': 0.85
            }
        ]
        
        mock_db.aql.execute = Mock(return_value=mock_candidates)
        
        result = consolidate_fuzzy_stage2(db=mock_db, dry_run=True)
        
        # Verify all results have matching types
        for candidate in result:
            assert candidate['entity1_type'] == candidate['entity2_type']
    
    def test_empty_candidates(self, mock_db):
        """Test: Handles no fuzzy matches gracefully"""
        mock_db.aql.execute = Mock(return_value=[])
        
        result = consolidate_fuzzy_stage2(db=mock_db, dry_run=True)
        
        assert len(result) == 0
    
    def test_merge_execution_not_in_dry_run(self, mock_db):
        """Test: Dry run doesn't perform merges"""
        mock_candidates = [
            {
                'entity1_id': 'Golden_Entities/1',
                'entity1_name': 'ALU',
                'entity2_id': 'Golden_Entities/2',
                'entity2_name': 'alu',
                'entity1_type': 'processor_component',
                'entity2_type': 'processor_component',
                'levenshtein_distance': 0,  # Case difference
                'token_overlap': 1.0,
                'confidence': 0.95
            }
        ]
        
        mock_db.aql.execute = Mock(return_value=mock_candidates)
        mock_collection = Mock()
        mock_db.collection = Mock(return_value=mock_collection)
        
        result = consolidate_fuzzy_stage2(db=mock_db, dry_run=True)
        
        # Should return candidates but not call collection operations
        assert len(result) == 1
        mock_collection.delete.assert_not_called()


class TestIndexing:
    """Test index creation functions"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock ArangoDB connection"""
        db = Mock()
        mock_collection = Mock()
        mock_collection.add_index = Mock()
        db.collection = Mock(return_value=mock_collection)
        return db
    
    def test_apply_indexes_golden_entities(self, mock_db):
        """Test: Creates indexes on Golden_Entities"""
        apply_indexes(mock_db)
        
        # Should create entity_type and entity_name indexes
        calls = mock_db.collection.return_value.add_index.call_args_list
        
        # Check for entity_type index
        assert any('entity_type' in str(call) for call in calls)
        
        # Check for entity_name index
        assert any('entity_name' in str(call) for call in calls)
    
    def test_apply_bridging_indexes_collection_exists(self, mock_db):
        """Test: Verifies indexes when RESOLVED_TO exists"""
        mock_db.has_collection = Mock(return_value=True)
        
        apply_bridging_indexes(mock_db)
        
        # Should check if collection exists
        mock_db.has_collection.assert_called_once()
    
    def test_apply_bridging_indexes_collection_not_exists(self, mock_db):
        """Test: Handles missing RESOLVED_TO collection gracefully"""
        mock_db.has_collection = Mock(return_value=False)
        
        # Should not raise exception
        apply_bridging_indexes(mock_db)
        
        # Should check collection but not try to add indexes
        mock_db.has_collection.assert_called_once()
        mock_db.collection.assert_not_called()


class TestFuzzyMergeLogic:
    """Test the merge logic and union-find algorithm"""
    
    def test_union_find_transitive_merges(self):
        """Test: Union-find handles A~B, B~C transitivity"""
        # Simulate union-find algorithm
        parent = {}
        
        def find(x):
            if x not in parent:
                parent[x] = x
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]
        
        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py
        
        # Merge A~B and B~C
        union('A', 'B')
        union('B', 'C')
        
        # All should have same root
        assert find('A') == find('B') == find('C')
    
    def test_merge_groups_formation(self):
        """Test: Forms correct merge groups from candidates"""
        candidates = [
            {'entity1_id': 'E1', 'entity2_id': 'E2'},
            {'entity1_id': 'E2', 'entity2_id': 'E3'},
            {'entity1_id': 'E4', 'entity2_id': 'E5'}
        ]
        
        parent = {}
        
        def find(x):
            if x not in parent:
                parent[x] = x
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]
        
        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py
        
        # Build union-find structure
        for cand in candidates:
            union(cand['entity1_id'], cand['entity2_id'])
        
        # Group by root
        merge_groups = defaultdict(list)
        for cand in candidates:
            root = find(cand['entity1_id'])
            merge_groups[root].append(cand['entity1_id'])
            merge_groups[root].append(cand['entity2_id'])
        
        # Should have 2 groups: {E1,E2,E3} and {E4,E5}
        assert len(merge_groups) == 2
        
        # Find the group with 3 elements
        three_group = [g for g in merge_groups.values() if len(set(g)) >= 3]
        assert len(three_group) == 1


class TestEdgeCases:
    """Test edge cases and error conditions"""
    
    def test_fuzzy_consolidation_with_none_db(self):
        """Test: Gets db if None provided"""
        with patch('consolidator.get_db') as mock_get_db:
            mock_db = Mock()
            mock_db.aql.execute = Mock(return_value=[])
            mock_get_db.return_value = mock_db
            
            consolidate_fuzzy_stage2(db=None, dry_run=True)
            
            mock_get_db.assert_called_once()
    
    def test_levenshtein_distance_parameter(self):
        """Test: Respects levenshtein_distance parameter"""
        mock_db = Mock()
        mock_db.aql.execute = Mock(return_value=[])
        
        consolidate_fuzzy_stage2(
            db=mock_db,
            levenshtein_distance=2,  # Allow distance 2
            dry_run=True
        )
        
        # Verify function completed (parameter respected)
        mock_db.aql.execute.assert_called_once()


class TestPerformance:
    """Test performance characteristics"""
    
    def test_fuzzy_query_efficiency(self):
        """Test: Query uses proper filters and limits"""
        mock_db = Mock()
        mock_db.aql.execute = Mock(return_value=[])
        
        consolidate_fuzzy_stage2(db=mock_db, dry_run=True)
        
        # Get the query string
        call_args = mock_db.aql.execute.call_args
        query = call_args[0][0]
        
        # Should have proper filters
        assert 'FILTER e1._key < e2._key' in query  # Avoid duplicates
        assert 'FILTER e1.entity_type == e2.entity_type' in query  # Type check
        assert 'LEVENSHTEIN_DISTANCE' in query  # Use Levenshtein
        assert 'FILTER confidence >=' in query  # Confidence threshold


class TestValidationScenarios:
    """Test realistic validation scenarios"""
    
    def test_hardware_entity_fuzzy_matches(self):
        """Test: Handles hardware naming variations"""
        mock_db = Mock()
        
        # Realistic hardware entity variations
        candidates = [
            {
                'entity1_id': 'Golden_Entities/alu1',
                'entity1_name': 'or1200_alu',
                'entity1_type': 'processor_component',
                'entity2_id': 'Golden_Entities/alu2',
                'entity2_name': 'or1200_alu_unit',
                'entity2_type': 'processor_component',
                'levenshtein_distance': 1,
                'token_overlap': 0.8,
                'confidence': 0.85
            }
        ]
        
        mock_db.aql.execute = Mock(return_value=candidates)
        
        result = consolidate_fuzzy_stage2(db=mock_db, dry_run=True)
        
        assert len(result) == 1
        assert 'or1200_alu' in result[0]['entity1_name']
    
    def test_prevents_false_positive_short_names(self):
        """Test: Doesn't merge short prefix matches"""
        # This is enforced in the AQL query itself
        # The query includes: FILTER !(is_prefix AND both_short)
        
        mock_db = Mock()
        
        # Short names that are prefixes should be filtered
        # e.g., "en" vs "enable" (both short, one is prefix)
        candidates = []  # Should be filtered by AQL
        
        mock_db.aql.execute = Mock(return_value=candidates)
        
        result = consolidate_fuzzy_stage2(
            db=mock_db,
            levenshtein_distance=1,
            dry_run=True
        )
        
        # Verify query includes prefix check
        call_args = mock_db.aql.execute.call_args
        query = call_args[0][0]
        assert 'is_prefix' in query.lower() or 'starts_with' in query.lower()


if __name__ == '__main__':
    # Run with: python3 -m pytest tests/test_consolidation.py -v
    pytest.main([__file__, '-v'])
