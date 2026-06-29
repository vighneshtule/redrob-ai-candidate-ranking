import { create } from 'zustand';

export type PipelineStep = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10; // 10 is 'complete' redirect

interface PipelineState {
  currentStep: PipelineStep;
  isPlaying: boolean;
  metrics: {
    candidatesProcessed: number;
    runtimeSeconds: number;
    heapSize: number;
    cacheHits: number;
    memoryMb: number;
  };
  
  setStep: (step: PipelineStep) => void;
  nextStep: () => void;
  togglePlay: () => void;
  updateMetrics: (partial: Partial<PipelineState['metrics']>) => void;
  reset: () => void;
}

export const usePipelineStore = create<PipelineState>((set) => ({
  currentStep: 1,
  isPlaying: false,
  metrics: {
    candidatesProcessed: 0,
    runtimeSeconds: 0,
    heapSize: 0,
    cacheHits: 0,
    memoryMb: 120,
  },
  
  setStep: (step) => set({ currentStep: step }),
  
  nextStep: () => set((state) => ({ 
    currentStep: Math.min(state.currentStep + 1, 10) as PipelineStep 
  })),
  
  togglePlay: () => set((state) => ({ isPlaying: !state.isPlaying })),
  
  updateMetrics: (partial) => set((state) => ({
    metrics: { ...state.metrics, ...partial }
  })),

  reset: () => set({
    currentStep: 1,
    isPlaying: false,
    metrics: {
      candidatesProcessed: 0,
      runtimeSeconds: 0,
      heapSize: 0,
      cacheHits: 0,
      memoryMb: 120,
    }
  })
}));
