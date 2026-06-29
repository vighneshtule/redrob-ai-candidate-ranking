import { useCandidateStore } from '@/store/candidateStore';
import { useQuery } from '@tanstack/react-query';
import { getCandidates } from '@/api/rankingApi';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Progress } from '@/components/ui/progress';

export function CompareDialog() {
  const { compareMode, compareCandidateIds } = useCandidateStore();
  
  const { data: allCandidates } = useQuery({
    queryKey: ['candidates'],
    queryFn: () => getCandidates()
  });

  const c1 = allCandidates?.find(c => c.id === compareCandidateIds[0]);
  const c2 = allCandidates?.find(c => c.id === compareCandidateIds[1]);

  const isOpen = compareMode && compareCandidateIds.length === 2 && !!c1 && !!c2;

  const handleClose = () => {
    // Keep compare mode active, but close dialog by unselecting
    useCandidateStore.getState().toggleCompareCandidate(compareCandidateIds[1]);
  };

  if (!c1 || !c2) return null;

  const compareRow = (label: string, val1: number, val2: number, colorClass: string) => {
    const v1 = (val1 * 100).toFixed(1);
    const v2 = (val2 * 100).toFixed(1);
    
    return (
      <div className="py-3 border-b border-border last:border-0">
        <div className="flex justify-between text-sm mb-1.5 font-medium">
          <span className="w-16 text-left">{v1}</span>
          <span className="text-muted-foreground">{label}</span>
          <span className="w-16 text-right">{v2}</span>
        </div>
        <div className="flex gap-4 items-center">
          <Progress value={val1 * 100} className={`h-1.5 flex-1 rotate-180 ${colorClass}`} />
          <Progress value={val2 * 100} className={`h-1.5 flex-1 ${colorClass}`} />
        </div>
      </div>
    );
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && handleClose()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Compare Candidates</DialogTitle>
        </DialogHeader>
        
        <div className="grid grid-cols-2 gap-8 mt-4">
          {/* Heads */}
          <div className="flex flex-col items-center text-center">
            <Avatar className="w-20 h-20 mb-3 border-2 border-border shadow-sm">
              <AvatarImage src={c1.avatar_url} />
              <AvatarFallback>{c1.name.substring(0,2)}</AvatarFallback>
            </Avatar>
            <h3 className="text-lg font-bold">{c1.name}</h3>
            <p className="text-sm text-muted-foreground">{c1.current_title}</p>
            <p className="text-xs text-muted-foreground mt-1">{c1.company} • {c1.years_of_experience} yrs</p>
          </div>
          
          <div className="flex flex-col items-center text-center">
            <Avatar className="w-20 h-20 mb-3 border-2 border-border shadow-sm">
              <AvatarImage src={c2.avatar_url} />
              <AvatarFallback>{c2.name.substring(0,2)}</AvatarFallback>
            </Avatar>
            <h3 className="text-lg font-bold">{c2.name}</h3>
            <p className="text-sm text-muted-foreground">{c2.current_title}</p>
            <p className="text-xs text-muted-foreground mt-1">{c2.company} • {c2.years_of_experience} yrs</p>
          </div>
        </div>

        <div className="mt-6 bg-muted/20 rounded-lg p-4 border border-border">
          {compareRow("Final Score", c1.scores.final_score, c2.scores.final_score, "[&>div]:bg-primary")}
          {compareRow("Career Match", c1.scores.career_score, c2.scores.career_score, "[&>div]:bg-blue-500")}
          {compareRow("Skill Fit", c1.scores.skill_score, c2.scores.skill_score, "[&>div]:bg-emerald-500")}
          {compareRow("Semantic", c1.scores.semantic_score, c2.scores.semantic_score, "[&>div]:bg-purple-500")}
          {compareRow("Behavior", c1.scores.behavior_score, c2.scores.behavior_score, "[&>div]:bg-amber-500")}
          {compareRow("Integrity", c1.scores.integrity_score, c2.scores.integrity_score, "[&>div]:bg-red-500")}
        </div>
      </DialogContent>
    </Dialog>
  );
}
