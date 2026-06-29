import re
from pathlib import Path

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent
CANDIDATES_JSONL = REPO_ROOT / "data" / "candidates.jsonl"
OUTPUTS_DIR = REPO_ROOT / "outputs"
OUTPUTS_DEBUG_DIR = OUTPUTS_DIR / "debug"

# Ranker config
STUFFING_PENALTY_THRESHOLD = 0.5

# Loader config
CANDIDATE_ID_PATTERN = re.compile(r"^CAND_\d+$")
LOADER_DEFAULT_ENCODING = "utf-8"
LOADER_LOG_INTERVAL = 10000

# Submission
SUBMISSION_EXPECTED_ROWS = 100
SUBMISSION_MAX_RANK = 100
SUBMISSION_MIN_RANK = 1
SUBMISSION_REQUIRED_COLUMNS = ["candidate_id", "rank", "score", "reasoning"]
