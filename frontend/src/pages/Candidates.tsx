import { CandidateTable } from "@/components/candidate/CandidateTable";
import { CandidatePreview } from "@/components/candidate/CandidatePreview";
import { useCandidateStore } from "@/store/candidateStore";
import { Button } from "@/components/ui/button";
import { Users2 } from "lucide-react";
import { CompareDialog } from "@/components/candidate/CompareDialog";

export default function Candidates() {
  const { compareMode, setCompareMode, compareCandidateIds } = useCandidateStore();

  return (
    <div className="h-[calc(100vh-6.5rem)] flex flex-col">
      <div className="flex items-center justify-between mb-4 flex-shrink-0">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Candidates Workspace</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Review, filter, and rank the top matching profiles for your JD.
          </p>
        </div>
        
        <Button 
          variant={compareMode ? "secondary" : "outline"}
          onClick={() => setCompareMode(!compareMode)}
          className="gap-2"
        >
          <Users2 className="w-4 h-4" />
          {compareMode ? `Cancel Compare (${compareCandidateIds.length}/2)` : "Compare Mode"}
        </Button>
      </div>

      <div className="flex-1 flex gap-4 min-h-0">
        {/* Left Panel: Table (70%) */}
        <div className="flex-[7] min-w-0">
          <CandidateTable />
        </div>

        {/* Right Panel: Preview (30%) */}
        <div className="flex-[3] min-w-[320px] max-w-[450px]">
          <CandidatePreview />
        </div>
      </div>

      <CompareDialog />
    </div>
  );
}
