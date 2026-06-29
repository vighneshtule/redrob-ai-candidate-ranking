import os
import json
import pickle
from sentence_transformers import SentenceTransformer

def build_jd_document(jd_data):
    parts = []
    
    parts.extend(jd_data.get("must_have", []))
    parts.extend(jd_data.get("good_to_have", []))
    
    tech_req = jd_data.get("technical_skills_required", {})
    for k, v in tech_req.items():
        parts.extend(v)
        
    tech_nice = jd_data.get("technical_skills_nice_to_have", {})
    for k, v in tech_nice.items():
        parts.extend(v)
        
    return " ".join(parts)

def build_candidate_document(candidate):
    parts = []
    
    headline = candidate.get("headline", "")
    if headline: parts.append(headline)
        
    summary = candidate.get("summary", "")
    if summary: parts.append(summary)
        
    for ch in candidate.get("career_history", []):
        title = ch.get("title", "")
        if title: parts.append(title)
        desc = ch.get("description", "")
        if desc: parts.append(desc)
            
    for sk in candidate.get("skills", []):
        name = sk.get("name", "")
        if name: parts.append(name)
            
    return " ".join(parts)

def main():
    print("Loading model...")
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    
    print("Loading JD...")
    with open("data/jd_requirements.json", encoding="utf-8") as f:
        jd_data = json.load(f)
    jd_doc = build_jd_document(jd_data)
    jd_embedding = model.encode(jd_doc)
    
    print("Loading candidates...")
    candidates = []
    with open("[PUB] India_runs_data_and_ai_challenge/India_runs_data_and_ai_challenge/candidates.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            candidates.append(json.loads(line))
            
    print(f"Loaded {len(candidates)} candidates.")
    
    cache = {
        "jd_embedding": jd_embedding,
        "candidates": {}
    }
    
    docs = [build_candidate_document(c) for c in candidates]
    print("Encoding candidates...")
    embeddings = model.encode(docs, batch_size=32, show_progress_bar=True)
    
    for c, emb in zip(candidates, embeddings):
        cache["candidates"][c["candidate_id"]] = emb
        
    os.makedirs("data/cache", exist_ok=True)
    with open("data/cache/candidate_embeddings.pkl", "wb") as f:
        pickle.dump(cache, f)
        
    print("Saved embeddings to data/cache/candidate_embeddings.pkl")

if __name__ == "__main__":
    main()
