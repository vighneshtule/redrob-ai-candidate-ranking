import { useQuery } from '@tanstack/react-query';
import { useCandidateStore } from '@/store/candidateStore';
import { getCandidates } from '@/api/rankingApi';
import { AICopilotPanel } from '@/components/candidate/AICopilotPanel';
import { UserPlus } from 'lucide-react';
import { AnimatePresence } from 'framer-motion';

export function CandidatePreview() {
  const { selectedCandidateId, setSelectedCandidateId } = useCandidateStore();
  
  const { data: allCandidates } = useQuery({
    queryKey: ['candidates'],
    queryFn: () => getCandidates()
  });

  const cand = allCandidates?.find(c => c.id === selectedCandidateId);

  return (
    <AnimatePresence mode="wait">
      {cand ? (
        <AICopilotPanel 
          key={cand.id} 
          cand={cand} 
          onClose={() => setSelectedCandidateId(null)} 
        />
      ) : (
        <div className="h-full bg-card rounded-lg border border-border shadow-sm flex items-center justify-center text-muted-foreground p-6 text-center">
          <div>
            <UserPlus className="w-12 h-12 mx-auto mb-3 opacity-20" />
            <p className="text-sm">Select a candidate from the table to view AI Copilot insights.</p>
          </div>
        </div>
      )}
    </AnimatePresence>
  );
}
