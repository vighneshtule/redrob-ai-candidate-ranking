export type MatchStatus = 'Excellent Match' | 'Strong Match' | 'Medium Match' | 'Needs Review' | 'Rejected';

export interface CandidateScores {
  final_score: number;
  career_score: number;
  skill_score: number;
  behavior_score: number;
  integrity_score: number;
  semantic_score: number;
  consistency_score: number;
}

export interface SkillDetails {
  supported: string[];
  unsupported: string[];
}

export interface SemanticEvidence {
  sentence: string;
  keywords: string[];
}

export interface JdMatch {
  required_skills_found: string[];
  missing_skills: string[];
  preferred_skills_found: string[];
  experience_match: boolean;
  location_match: boolean;
  overall_match_percentage: number;
}

export interface TimelineEvent {
  year: string;
  title: string;
  company: string;
  is_relevant: boolean;
}

export interface CopilotData {
  why_ranked: string[];
  potential_risks: string[];
  semantic_evidence: SemanticEvidence[];
  jd_match: JdMatch;
  timeline: TimelineEvent[];
  recommendation_status: 'Strong Hire' | 'Hire' | 'Interview Recommended' | 'Borderline' | 'Reject';
  recommendation_reasoning: string;
  interview_questions: string[];
}

export interface Candidate {
  id: string;
  name: string;
  avatar_url?: string;
  headline: string;
  current_title: string;
  company: string;
  location: string;
  years_of_experience: number;
  open_to_work: boolean;
  relocation: boolean;
  notice_period?: string;
  
  scores: CandidateScores;
  match_status: MatchStatus;
  
  // Preview specific details
  skills: SkillDetails;
  career_summary: string;
  behavior_signals: string[];
  integrity_flags: string[];
  recruiter_explanation: string;
  
  // Phase 8.3 Copilot
  copilot: CopilotData;
}

export type SortField = 
  | 'final_score' 
  | 'career_score' 
  | 'skill_score' 
  | 'semantic_score' 
  | 'behavior_score' 
  | 'integrity_score' 
  | 'years_of_experience';

export type SortOrder = 'asc' | 'desc';
