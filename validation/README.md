# Ground Truth Validation Framework

This directory contains rigorous validation of the IC Enrichment Pack claims using ground truth labeled data.

## Methodology

### 1. Ground Truth Creation
- Manually labeled entity pairs as "match" or "no-match"
- Multiple domains tested
- Conservative labeling (when in doubt, mark as uncertain and exclude)

### 2. Experimental Design
- **Baseline**: Name-only Jaro-Winkler similarity (threshold 0.7)
- **Enhanced**: Baseline + IC Enrichment components
- **Metrics**: Precision, Recall, F1 at various thresholds
- **Statistical Testing**: Confidence intervals, significance tests

### 3. Domains
- Hardware (OR1200 processor - existing data)
- Medical (simulated clinical data)
- Organizational (simulated org chart)

## Results

See `validation_results.md` for detailed findings.

