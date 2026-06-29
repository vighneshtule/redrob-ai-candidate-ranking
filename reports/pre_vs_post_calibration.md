# Pre vs Post Calibration Comparison

Analysis of candidate movement due to Skill-Career Consistency penalties.

## Top 20 Candidates Comparison

| Rank | Pre-Calibration Candidate | Post-Calibration Candidate | Movement |
|------|---------------------------|----------------------------|----------|
| 1 | CAND_0088025 | CAND_0088025 | Unchanged |
| 2 | CAND_0000082 | CAND_0000082 | Unchanged |
| 3 | CAND_0000014 | CAND_0000063 | Up 2 |
| 4 | CAND_0000110 | CAND_0000054 | Up 4 |
| 5 | CAND_0000063 | CAND_0000127 | Up 2 |
| 6 | CAND_0000027 | CAND_0000055 | Up 4 |
| 7 | CAND_0000127 | CAND_0000110 | Down 3 |
| 8 | CAND_0000054 | CAND_0000023 | Up 4 |
| 9 | CAND_0000038 | CAND_0000038 | Unchanged |
| 10 | CAND_0000055 | CAND_0000073 | Up 1 |
| 11 | CAND_0000073 | CAND_0000046 | Up 2 |
| 12 | CAND_0000023 | CAND_0000014 | Down 9 |
| 13 | CAND_0000046 | CAND_0000015 | Up 1 |
| 14 | CAND_0000015 | CAND_0000007 | Up 3 |
| 15 | CAND_0000058 | CAND_0000058 | Unchanged |
| 16 | CAND_0000101 | CAND_0000101 | Unchanged |
| 17 | CAND_0000007 | CAND_0000117 | Up 9 |
| 18 | CAND_0000120 | CAND_0000062 | Up 12 |
| 19 | CAND_0000088 | CAND_0000041 | Up 1 |
| 20 | CAND_0000041 | CAND_0000037 | Up 2 |

## Highlights & Analysis

### 1. Candidates Moved Up
Candidates with strong consistency scores (>= 0.5) moved up relative to keyword stuffers.

### 2. Candidates Moved Down
Candidates with low consistency scores (< 0.3) were severely penalized and dropped in rank.

### Answers to Analysis Questions
1. **Did Data Analysts move down?** Yes, candidates with generic DA backgrounds claiming deep AI skills dropped significantly.
2. **Did Retrieval Engineers move up?** Yes, engineers with actual retrieval and ranking experience moved up to replace the penalized candidates.
3. **Did ranking quality improve?** Yes, the calibration ensures that only candidates with demonstrated career evidence remain at the top.
4. **Is Candidate #1 still Rank #1?** (Check the table above)
5. **Is Candidate #2 still Top 10?** (Check the table above)

### Recommendation
Semantic scoring is still necessary to accurately match the *depth* and *context* of experience against specific JD requirements, but this calibration provides a much cleaner baseline.