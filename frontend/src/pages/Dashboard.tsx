import { useQuery } from '@tanstack/react-query';
import { Users, Clock, Zap, Database, CheckCircle2 } from "lucide-react";
import { MetricCard } from "@/components/dashboard/MetricCard";
import { motion } from "framer-motion";
import { getBenchmarks, getPipelineStatus } from "@/api/rankingApi";

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.1 }
  }
};

const item = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 }
};

export default function Dashboard() {
  const { data: benchmarks } = useQuery({
    queryKey: ['benchmarks'],
    queryFn: () => getBenchmarks(),
    refetchInterval: 5000 // Poll every 5 seconds
  });

  const { data: pipelineStatus } = useQuery({
    queryKey: ['pipelineStatus'],
    queryFn: () => getPipelineStatus(),
    refetchInterval: 5000 // Poll every 5 seconds
  });

  const bData = benchmarks || {
    candidatesProcessed: 0,
    runtimeSeconds: 0,
    heapSize: 0,
    cacheHits: 0,
    memoryMb: 0,
    averageCandidateTimeMs: 0
  };

  const pData = pipelineStatus || { currentStep: 0, isPlaying: false, metrics: {} };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground mt-1">
          Overview of pipeline performance and candidate matching.
        </p>
      </div>

      <motion.div 
        variants={container}
        initial="hidden"
        animate="show"
        className="grid gap-4 md:grid-cols-2 lg:grid-cols-4"
      >
        <motion.div variants={item}>
          <MetricCard
            title="Candidates Processed"
            value={bData.candidatesProcessed.toLocaleString()}
            subtitle="from latest batch"
            icon={<Users className="h-4 w-4" />}
            trend={{ value: 12.5, isUp: true }}
          />
        </motion.div>
        
        <motion.div variants={item}>
          <MetricCard
            title="Top-K Runtime"
            value={`${bData.runtimeSeconds.toFixed(1)}s`}
            subtitle="total execution time"
            icon={<Clock className="h-4 w-4" />}
            trend={{ value: 2.1, isUp: false }}
          />
        </motion.div>

        <motion.div variants={item}>
          <MetricCard
            title="Avg Time/Candidate"
            value={`${bData.averageCandidateTimeMs.toFixed(2)}ms`}
            subtitle="latency per candidate"
            icon={<Zap className="h-4 w-4 text-yellow-500" />}
            trend={{ value: 4.3, isUp: true }}
          />
        </motion.div>

        <motion.div variants={item}>
          <MetricCard
            title="Memory Usage"
            value={`${bData.memoryMb.toFixed(1)} MB`}
            subtitle="last pipeline run"
            icon={<Database className="h-4 w-4" />}
          />
        </motion.div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
        className="mt-8"
      >
        <div className="rounded-xl border border-border bg-card p-6 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold">Pipeline Status</h3>
            <div className={`flex items-center gap-2 text-sm px-3 py-1 rounded-full font-medium ${pData.isPlaying ? 'text-amber-500 bg-amber-500/10' : 'text-green-500 bg-green-500/10'}`}>
              <CheckCircle2 className="w-4 h-4" />
              {pData.isPlaying ? `Running (Step ${pData.currentStep})` : 'All Systems Operational'}
            </div>
          </div>
          
          <div className="grid md:grid-cols-3 gap-6 pt-4 border-t border-border">
            <div>
              <p className="text-sm text-muted-foreground mb-1">Integrity Scorer</p>
              <div className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${pData.currentStep >= 4 ? 'bg-green-500' : 'bg-muted-foreground'}`} />
                <span className="font-medium">{pData.currentStep >= 4 ? 'Online' : 'Waiting'}</span>
              </div>
            </div>
            <div>
              <p className="text-sm text-muted-foreground mb-1">Semantic Layer</p>
              <div className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${pData.currentStep >= 7 ? 'bg-green-500' : 'bg-muted-foreground'}`} />
                <span className="font-medium">{pData.currentStep >= 7 ? `Online (Cache Hit: ${bData.cacheHits}%)` : 'Waiting'}</span>
              </div>
            </div>
            <div>
              <p className="text-sm text-muted-foreground mb-1">Hybrid Ranker</p>
              <div className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${pData.currentStep >= 9 ? 'bg-green-500' : 'bg-muted-foreground'}`} />
                <span className="font-medium">{pData.currentStep >= 9 ? `Online (Heap Size: ${bData.heapSize})` : 'Waiting'}</span>
              </div>
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  );
}

