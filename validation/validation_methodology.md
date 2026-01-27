# Validation Methodology and Results

**Date:** January 2, 2026 
**Dataset:** Hardware domain (OR1200 processor) 
**Ground Truth:** 15 manually labeled entity pairs

---

## Methodology

### 1. Ground Truth Creation

**Process:**
- Manually labeled 15 entity pairs from OR1200 hardware documentation
- Each pair labeled as "true match" or "false match"
- Conservative labeling: when uncertain, excluded from dataset
- High-confidence labels only (no ambiguous cases)

**Dataset Composition:**
- True matches: 9 pairs (60%)
- True non-matches: 6 pairs (40%)
- Domains covered: Signals, ports, modules, registers

**Label Quality:**
- Single labeler (domain expert)
- High-confidence labels only
- **Limitation:** No inter-rater reliability measurement

### 2. Experimental Design

**Baseline Configuration:**
- Name-only Jaro-Winkler similarity
- Threshold: 0.7
- Basic acronym expansion (clk→clock, rst→reset, etc.)

**Enhanced Configuration:**
- Baseline + Type Compatibility Filter
- Baseline + Hierarchical Context Resolver 
- Baseline + Acronym Expansion Handler
- Threshold: 0.7 (same as baseline)

**Metrics:**
- Precision: Correctness of predicted matches
- Recall: Coverage of true matches
- F1 Score: Harmonic mean of precision and recall

### 3. Reproducibility

**All validation is reproducible:**
```bash
cd /path/to/project
python3 validation/validate_metrics.py
```

---

## Results

### Quantitative Metrics

| Metric | Baseline | Enhanced | Δ | % Change |
|--------|----------|----------|---|----------|
| **Precision** | 0.500 (1/2) | **1.000 (4/4)** | +0.500 | +100% |
| **Recall** | 0.111 (1/9) | **0.444 (4/9)** | +0.333 | +300% |
| **F1 Score** | 0.182 | **0.615** | +0.433 | +238% |

### Confusion Matrices

**Baseline:**
- True Positives: 1
- False Positives: 1 (50% of predictions wrong)
- False Negatives: 8 (missed 89% of true matches)

**Enhanced:**
- True Positives: 4
- False Positives: 0 (100% precision!)
- False Negatives: 5 (still missed 56% of true matches)

---

## Key Findings

### 1. Precision Dramatically Improved [DONE]

**From 50% to 100%** - No false positives with enhanced matching.

**Why?** Type compatibility filtering prevents nonsensical matches (e.g., signal ↔ instruction).

**Example:**
- Baseline incorrectly matched: `add_result` (signal) → `ADD Instruction` (instruction)
- Enhanced correctly rejected: Type incompatible

### 2. Recall Improved But Still Limited

**From 11% to 44%** - Better, but still missing 56% of true matches.

**Why?** 
- Name similarity threshold (0.7) is conservative
- Some matches require deeper semantic understanding
- Acronym dictionary is incomplete

**Examples of Missed Matches:**
- `or1200_mult_mac` → `Multiplier Unit` (score: 0.265, needs better abbreviation handling)
- `if_insn` → `Instruction Fetch Unit` (score: 0.000, type filter too aggressive)

### 3. F1 Significantly Better

**From 0.18 to 0.62** - Strong improvement in balanced performance.

---

## Limitations and Caveats

### 1. Small Dataset
- **Only 15 pairs** - Not statistically robust
- No confidence intervals calculated
- No cross-validation performed
- **Recommendation:** Need 100+ labeled pairs for publication

### 2. Single Domain
- Hardware only - generalization claims unvalidated
- Medical/legal/org examples are demonstrations, not validated
- **Recommendation:** Need ground truth for each claimed domain

### 3. Baseline Could Be Stronger
- Simple Jaro-Winkler implementation
- No tuning of baseline threshold
- ER Library's full capabilities not used in baseline
- **Potential:** Stronger baseline might reduce apparent improvements

### 4. Recall Is Still Low
- 44% recall means missing >50% of true matches
- Not production-ready for high-recall applications
- Threshold tuning not explored (could trade precision for recall)

### 5. No Statistical Testing
- No p-values or significance tests
- No confidence intervals
- Sample size too small for rigorous statistics

### 6. Labeling Quality
- Single labeler (no inter-rater agreement)
- Potential labeler bias
- No third-party validation

---

## Honest Assessment

**What This Validation Shows:**
- Type filtering eliminates false positives (strong evidence)
- Context and acronyms improve recall moderately (moderate evidence)
- F1 improvement is real and substantial (moderate evidence)

**What This Validation Does NOT Show:**
- Domain-agnostic applicability (no non-hardware ground truth)
- Statistical significance (sample size too small)
- Production readiness (recall too low)
- Generalization to other datasets

**Confidence Level:** Medium
- Results are encouraging but not conclusive
- Need larger dataset and cross-domain validation
- Current results are "proof of concept" level

---

## Next Steps for Robust Validation

### Required (Before Publication):
1. **Expand dataset** to 100+ pairs per domain
2. **Add non-hardware domains** with ground truth
3. **Multiple labelers** with inter-rater agreement
4. **Statistical testing** (significance, confidence intervals)
5. **Threshold tuning** exploration
6. **Stronger baseline** using full ER Library capabilities

### Optional (Nice to Have):
- Cross-validation across different hardware projects
- Comparison with other ER systems
- User study with domain experts
- Production deployment case study

---

## Recommendation

**For Outreach:**
- Present these as **preliminary results**
- Be transparent about limitations
- Don't claim generalization without validation
- Emphasize this is a proof-of-concept seeking feedback

**Honest Claim:**
"On a small hardware dataset (15 pairs), our approach achieved perfect precision (1.0) and moderate recall (0.44), improving F1 from 0.18 to 0.62. This is preliminary validation suggesting the approach has merit, but requires larger-scale validation before production use."

---

**This validation provides honest evidence that the approach works, while acknowledging significant limitations that need to be addressed.**
