import type { Candidate } from '@/types/candidate';

const API_BASE = 'http://127.0.0.1:8000/api';

export const rankCandidates = async (jobDescription: string, topK: number = 100): Promise<Candidate[]> => {
  const res = await fetch(`${API_BASE}/rank/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ job_description: jobDescription, top_k: topK })
  });
  if (!res.ok) throw new Error('Ranking failed');
  return res.json();
};

export const getCandidates = async (): Promise<Candidate[]> => {
  const res = await fetch(`${API_BASE}/candidate/`);
  if (!res.ok) throw new Error('Failed to fetch candidates');
  return res.json();
};

export const getCandidate = async (id: string): Promise<Candidate> => {
  const res = await fetch(`${API_BASE}/candidate/${id}`);
  if (!res.ok) throw new Error('Candidate not found');
  return res.json();
};

export const getBenchmarks = async (): Promise<any> => {
  const res = await fetch(`${API_BASE}/benchmarks/`);
  if (!res.ok) throw new Error('Failed to fetch benchmarks');
  return res.json();
};

export const getPipelineStatus = async (): Promise<any> => {
  const res = await fetch(`${API_BASE}/pipeline/status`);
  if (!res.ok) throw new Error('Failed to fetch pipeline status');
  return res.json();
};
