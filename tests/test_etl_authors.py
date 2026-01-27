#!/usr/bin/env python3
"""
Unit tests for Author ETL Pipeline (etl_authors.py)
"""

import pytest
import sys
from datetime import datetime, timedelta
sys.path.append('src')

from etl_authors import (
    parse_git_author,
    normalize_email,
    is_active,
    calculate_maintenance_score
)


class TestParseGitAuthor:
    """Test parsing of various git author string formats"""
    
    def test_full_format(self):
        """Test: Name <email>"""
        result = parse_git_author("Alice Smith <alice.smith@example.com>")
        assert result['name'] == "Alice Smith"
        assert result['email'] == "alice.smith@example.com"
    
    def test_email_only(self):
        """Test: email only"""
        result = parse_git_author("bob@example.com")
        assert result['email'] == "bob@example.com"
        assert result['name'] == "Bob"  # Derived from email
    
    def test_name_only(self):
        """Test: name only"""
        result = parse_git_author("Charlie")
        assert result['name'] == "Charlie"
        assert result['email'] == "charlie@unknown"
    
    def test_with_extra_spaces(self):
        """Test: extra whitespace"""
        result = parse_git_author("  Alice Smith  <  alice@example.com  >  ")
        assert result['name'] == "Alice Smith"
        assert result['email'] == "alice@example.com"
    
    def test_complex_email(self):
        """Test: complex email addresses"""
        result = parse_git_author("John Doe <john.doe+work@example.co.uk>")
        assert result['name'] == "John Doe"
        assert result['email'] == "john.doe+work@example.co.uk"


class TestNormalizeEmail:
    """Test email normalization for consistent keys"""
    
    def test_basic_email(self):
        """Test: simple email"""
        assert normalize_email("alice@example.com") == "alice"
    
    def test_email_with_dots(self):
        """Test: email with dots in username"""
        assert normalize_email("alice.smith@example.com") == "alice_smith"
    
    def test_email_with_special_chars(self):
        """Test: email with special characters"""
        assert normalize_email("alice+test@example.com") == "alice_test"
    
    def test_email_with_numbers(self):
        """Test: email with numbers"""
        assert normalize_email("alice123@example.com") == "alice123"
    
    def test_consecutive_special_chars(self):
        """Test: multiple consecutive special chars become single underscore"""
        assert normalize_email("alice..smith@example.com") == "alice_smith"
    
    def test_leading_trailing_special_chars(self):
        """Test: leading/trailing special chars are removed"""
        assert normalize_email(".alice.@example.com") == "alice"


class TestIsActive:
    """Test author activity detection"""
    
    def test_recent_activity(self):
        """Test: author with recent activity"""
        # 30 days ago
        recent = (datetime.now() - timedelta(days=30)).isoformat() + 'Z'
        assert is_active(recent, threshold_days=180) is True
    
    def test_borderline_activity(self):
        """Test: author at threshold boundary"""
        # Exactly 180 days ago
        borderline = (datetime.now() - timedelta(days=180)).isoformat() + 'Z'
        assert is_active(borderline, threshold_days=180) is True
    
    def test_inactive(self):
        """Test: inactive author"""
        # 1 year ago
        old = (datetime.now() - timedelta(days=365)).isoformat() + 'Z'
        assert is_active(old, threshold_days=180) is False
    
    def test_no_timestamp(self):
        """Test: missing timestamp"""
        assert is_active(None) is False
        assert is_active("") is False
    
    def test_custom_threshold(self):
        """Test: custom activity threshold"""
        # 100 days ago
        timestamp = (datetime.now() - timedelta(days=100)).isoformat() + 'Z'
        assert is_active(timestamp, threshold_days=90) is False
        assert is_active(timestamp, threshold_days=120) is True


class TestCalculateMaintenanceScore:
    """Test maintenance score calculation"""
    
    def test_high_frequency_recent(self):
        """Test: high commit frequency + recent activity = high score"""
        score = calculate_maintenance_score(
            commit_count=10,
            total_commits=10,
            days_since_last=0
        )
        assert score == 1.0
    
    def test_high_frequency_old(self):
        """Test: high frequency but old commits = medium score"""
        score = calculate_maintenance_score(
            commit_count=10,
            total_commits=10,
            days_since_last=365
        )
        # 60% frequency (1.0) + 40% recency (0.1) = 0.64
        assert score == 0.64
    
    def test_low_frequency_recent(self):
        """Test: low frequency but recent = medium score"""
        score = calculate_maintenance_score(
            commit_count=1,
            total_commits=10,
            days_since_last=0
        )
        # 60% frequency (0.1) + 40% recency (1.0) = 0.46
        assert score == 0.46
    
    def test_medium_activity(self):
        """Test: medium frequency and recency"""
        score = calculate_maintenance_score(
            commit_count=5,
            total_commits=10,
            days_since_last=180
        )
        # 60% frequency (0.5) + 40% recency (~0.5) = ~0.5
        assert 0.4 < score < 0.6
    
    def test_zero_commits(self):
        """Test: zero commits"""
        score = calculate_maintenance_score(
            commit_count=0,
            total_commits=10,
            days_since_last=0
        )
        # Frequency is 0, recency is 1.0 = 0.4
        assert score == 0.4
    
    def test_zero_total_commits(self):
        """Test: edge case - zero total commits"""
        score = calculate_maintenance_score(
            commit_count=5,
            total_commits=0,
            days_since_last=0
        )
        # Should handle division by zero gracefully
        assert score == 1.0
    
    def test_recency_decay(self):
        """Test: recency component decays over time"""
        # Score should decrease as days_since_last increases
        score_0 = calculate_maintenance_score(5, 10, 0)
        score_90 = calculate_maintenance_score(5, 10, 90)
        score_180 = calculate_maintenance_score(5, 10, 180)
        score_365 = calculate_maintenance_score(5, 10, 365)
        
        assert score_0 > score_90 > score_180 > score_365


class TestEdgeCases:
    """Test edge cases and error conditions"""
    
    def test_parse_empty_string(self):
        """Test: empty author string"""
        result = parse_git_author("")
        assert result['name'] == ""
        assert result['email'] == "@unknown"
    
    def test_normalize_email_no_at(self):
        """Test: normalize string without @"""
        # Should still work by treating whole string as username
        result = normalize_email("justusername")
        assert result == "justusername"
    
    def test_parse_unicode_names(self):
        """Test: unicode characters in names"""
        result = parse_git_author("François Müller <francois@example.com>")
        assert result['name'] == "François Müller"
        assert result['email'] == "francois@example.com"
    
    def test_maintenance_score_negative_days(self):
        """Test: negative days (future timestamp - shouldn't happen but handle gracefully)"""
        score = calculate_maintenance_score(5, 10, -10)
        # Should treat as recent (score = 1.0 for recency)
        assert score >= 0.4


class TestIntegrationScenarios:
    """Test realistic integration scenarios"""
    
    def test_multiple_email_variations_same_author(self):
        """Test: same author with different email formats"""
        variations = [
            "Alice Smith <alice.smith@example.com>",
            "alice.smith@example.com",
            "Alice Smith <alice@example.com>",
        ]
        
        # Different variations should be parseable
        results = [parse_git_author(v) for v in variations]
        assert all('name' in r and 'email' in r for r in results)
        
        # First two should normalize to same key
        key1 = normalize_email(results[0]['email'])
        key2 = normalize_email(results[1]['email'])
        assert key1 == key2 == "alice_smith"
    
    def test_real_world_git_authors(self):
        """Test: real-world examples from OR1200 project"""
        authors = [
            "julius",
            "marcus.erlandsson",
            "unneback"
        ]
        
        for author in authors:
            result = parse_git_author(author)
            assert result['name'] is not None
            assert result['email'] is not None
            
            # Should be normalizable
            key = normalize_email(result['email'])
            assert len(key) > 0
            assert ' ' not in key
            assert '.' not in key
    
    def test_maintenance_qualification_logic(self):
        """Test: maintenance edge qualification criteria"""
        # Scenario 1: >= 3 commits (absolute)
        score1 = calculate_maintenance_score(3, 100, 30)
        assert score1 > 0  # Qualifies
        
        # Scenario 2: >= 20% of commits (relative)
        score2 = calculate_maintenance_score(2, 10, 30)  # 20%
        assert score2 > 0  # Qualifies
        
        # Scenario 3: < 3 commits AND < 20%
        score3 = calculate_maintenance_score(1, 10, 30)  # 10%
        assert score3 > 0  # Still gets a score, but would be filtered by AQL query


# Performance and Validation Tests
class TestPerformance:
    """Test performance characteristics"""
    
    def test_normalize_email_performance(self):
        """Test: email normalization is fast"""
        import time
        start = time.time()
        for _ in range(10000):
            normalize_email("alice.smith+test@example.com")
        elapsed = time.time() - start
        assert elapsed < 1.0  # Should be subsecond for 10k normalizations
    
    def test_maintenance_score_performance(self):
        """Test: score calculation is fast"""
        import time
        start = time.time()
        for _ in range(10000):
            calculate_maintenance_score(5, 10, 180)
        elapsed = time.time() - start
        assert elapsed < 1.0  # Should be subsecond for 10k calculations


if __name__ == '__main__':
    # Run with: python3 -m pytest tests/test_etl_authors.py -v
    pytest.main([__file__, '-v'])

