import { create } from 'zustand';
import type { SortField, SortOrder } from '@/types/candidate';

interface CandidateState {
  // Selection
  selectedCandidateId: string | null;
  setSelectedCandidateId: (id: string | null) => void;
  
  // Compare Mode
  compareMode: boolean;
  setCompareMode: (active: boolean) => void;
  compareCandidateIds: string[];
  toggleCompareCandidate: (id: string) => void;
  clearCompareCandidates: () => void;

  // Table State
  page: number;
  setPage: (page: number) => void;
  pageSize: number;
  setPageSize: (size: number) => void;
  sortField: SortField;
  sortOrder: SortOrder;
  setSort: (field: SortField) => void;
  searchQuery: string;
  setSearchQuery: (query: string) => void;
}

export const useCandidateStore = create<CandidateState>((set) => ({
  selectedCandidateId: null,
  setSelectedCandidateId: (id) => set({ selectedCandidateId: id }),
  
  compareMode: false,
  setCompareMode: (active) => set({ compareMode: active, compareCandidateIds: [] }),
  compareCandidateIds: [],
  toggleCompareCandidate: (id) => set((state) => {
    if (state.compareCandidateIds.includes(id)) {
      return { compareCandidateIds: state.compareCandidateIds.filter(c => c !== id) };
    }
    if (state.compareCandidateIds.length < 2) {
      return { compareCandidateIds: [...state.compareCandidateIds, id] };
    }
    return state; // Max 2
  }),
  clearCompareCandidates: () => set({ compareCandidateIds: [] }),

  page: 1,
  setPage: (page) => set({ page }),
  pageSize: 10,
  setPageSize: (pageSize) => set({ pageSize, page: 1 }),
  sortField: 'final_score',
  sortOrder: 'desc',
  setSort: (field) => set((state) => ({
    sortField: field,
    sortOrder: state.sortField === field && state.sortOrder === 'desc' ? 'asc' : 'desc',
  })),
  searchQuery: '',
  setSearchQuery: (searchQuery) => set({ searchQuery, page: 1 }),
}));
