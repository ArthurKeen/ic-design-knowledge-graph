#!/bin/bash

# OR1200 Project: Migration to entity_resolution.enrichments
# Estimated time: 5 minutes

set -e

echo "=========================================="
echo "Migrating project to entity_resolution.enrichments"
echo "=========================================="
echo ""

# Step 1: Check if arango-entity-resolution has enrichments
echo "[1/5] Checking arango-entity-resolution installation..."
cd ~/code/arango-entity-resolution
if [ -d "src/entity_resolution/enrichments" ]; then
    echo "✓ Enrichments found in library"
else
    echo "✗ Enrichments not found. Please pull latest:"
    echo "  cd ~/code/arango-entity-resolution && git pull"
    exit 1
fi

# Step 2: Check if library is accessible via Python path
echo ""
echo "[2/5] Verifying library is accessible..."
python3 -c "
import sys
sys.path.insert(0, '/Users/arthurkeen/code/arango-entity-resolution/src')
from entity_resolution.enrichments import TypeCompatibilityFilter
print('✓ Library is accessible via sys.path')
"

# Step 3: Update imports in project
echo ""
echo "[3/5] Updating imports in project..."
cd ~/project

# Backup first
echo "  Creating backup of validation scripts..."
cp validation/validate_metrics.py validation/validate_metrics.py.bak

# Update validation script
echo "  Updating validation/validate_metrics.py..."
sed -i.tmp 's/from ic_enrichment import/from entity_resolution.enrichments import/g' validation/validate_metrics.py
rm validation/validate_metrics.py.tmp

echo "✓ Imports updated"

# Step 4: Test the migration
echo ""
echo "[4/5] Testing migration..."
python3 -c "
from entity_resolution.enrichments import (
    HierarchicalContextResolver,
    TypeCompatibilityFilter,
    AcronymExpansionHandler,
    RelationshipProvenanceSweeper
)
print('✓ All imports successful')
"

# Run validation to ensure everything works
echo "  Running hardware validation..."
python3 validation/validate_metrics.py --domain hardware > /tmp/migration_test.txt 2>&1
if grep -q "22 passed" /tmp/migration_test.txt || grep -q "VALIDATION COMPLETE" /tmp/migration_test.txt; then
    echo "✓ Validation test passed"
else
    echo "✗ Validation test failed - check /tmp/migration_test.txt"
    exit 1
fi

# Step 5: Archive local ic_enrichment
echo ""
echo "[5/5] Archiving local ic_enrichment directory..."
if [ -d "ic_enrichment" ]; then
    # Create archive
    tar -czf ic_enrichment_archive_$(date +%Y%m%d).tar.gz ic_enrichment/
    echo "✓ Archived to ic_enrichment_archive_$(date +%Y%m%d).tar.gz"
    
    # Remove directory
    rm -rf ic_enrichment/
    echo "✓ Removed local ic_enrichment/ directory"
else
    echo "  (ic_enrichment already removed)"
fi

# Cleanup
rm -f validation/validate_metrics.py.bak

echo ""
echo "=========================================="
echo "✅ MIGRATION COMPLETE!"
echo "=========================================="
echo ""
echo "Changes made:"
echo "  1. Updated imports in validation/validate_metrics.py"
echo "  2. Removed local ic_enrichment/ directory"
echo "  3. Created archive: ic_enrichment_archive_$(date +%Y%m%d).tar.gz"
echo ""
echo "Next steps:"
echo "  - Documentation still references ic_enrichment (docs/*.md)"
echo "  - These are for reference only and don't need updating"
echo "  - Run your production code to verify everything works"
echo ""
echo "To test: python3 validation/validate_metrics.py --domain hardware"
echo ""

