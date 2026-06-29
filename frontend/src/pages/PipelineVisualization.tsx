import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getPipelineStatus, rankCandidates } from '@/api/rankingApi';
import { motion, AnimatePresence } from 'framer-motion';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Play, Pause, RotateCcw, Activity, Server, Cpu, Database, ChevronRight, CheckCircle2, ShieldCheck, Search, Zap, Code2, Sparkles } from 'lucide-react';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';

// --- SUB-COMPONENTS FOR EACH STEP ---

function Step1JDInput() {
  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }} className="flex flex-col items-center justify-center h-full max-w-2xl mx-auto text-center space-y-6">
      <div className="bg-muted/30 p-4 rounded-xl border border-border w-full text-left font-mono text-sm overflow-hidden h-[300px] relative">
        <div className="absolute inset-0 bg-gradient-to-b from-transparent to-background" />
        <p className="text-muted-foreground">{"{"}</p>
        <p className="pl-4 text-primary">"title": "Senior ML Engineer",</p>
        <p className="pl-4 text-emerald-500">"required_skills": ["Python", "PyTorch", "FastAPI"],</p>
        <p className="pl-4 text-emerald-500">"preferred_skills": ["Pinecone", "LLMs", "Retrieval"],</p>
        <p className="pl-4 text-blue-400">"experience_years": 5,</p>
        <p className="pl-4 text-amber-500">"location": "San Francisco / Remote"</p>
        <p className="text-muted-foreground">{"}"}</p>
      </div>
      <h2 className="text-2xl font-bold tracking-tight">1. JD Ingestion & Parsing</h2>
      <p className="text-muted-foreground">The system ingests the raw job description and uses an LLM parser to extract strictly structured semantic requirements.</p>
    </motion.div>
  );
}

function Step3Loading() {
  const [count, setCount] = useState(0);
  useEffect(() => {
    let current = 0;
    const interval = setInterval(() => {
      current += 4000;
      if (current >= 100000) {
        current = 100000;
        clearInterval(interval);
      }
      setCount(current);
    }, 50);
    return () => clearInterval(interval);
  }, []);

  return (
    <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} className="flex flex-col items-center justify-center h-full space-y-8">
      <Database className="w-24 h-24 text-primary animate-pulse" />
      <div className="text-center space-y-2">
        <h2 className="text-5xl font-black font-mono tracking-tighter text-foreground">
          {count.toLocaleString()}
        </h2>
        <p className="text-xl font-medium text-muted-foreground uppercase tracking-widest">Candidates Loaded</p>
      </div>
    </motion.div>
  );
}

function Step4Integrity() {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col items-center justify-center h-full max-w-3xl mx-auto space-y-8">
      <h2 className="text-2xl font-bold tracking-tight mb-4 flex items-center gap-3">
        <ShieldCheck className="w-8 h-8 text-emerald-500" />
        Integrity Analysis (Funnel)
      </h2>
      <div className="w-full flex justify-between items-center bg-muted/20 p-6 rounded-xl border border-border">
        <div className="text-center">
          <p className="text-3xl font-bold">100,000</p>
          <p className="text-sm text-muted-foreground">Input</p>
        </div>
        <div className="flex-1 px-8 relative">
          <div className="h-2 bg-gradient-to-r from-muted to-emerald-500/50 rounded-full w-full overflow-hidden">
            <motion.div initial={{ x: '-100%' }} animate={{ x: '100%' }} transition={{ repeat: Infinity, duration: 1.5, ease: 'linear' }} className="h-full w-1/3 bg-emerald-500" />
          </div>
          <div className="absolute top-6 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2">
            <Badge variant="destructive" className="animate-bounce">⚠ 2,401 Fraud Detected</Badge>
            <Badge variant="outline" className="border-amber-500 text-amber-500">14,291 Keyword Stuffing</Badge>
          </div>
        </div>
        <div className="text-center">
          <p className="text-3xl font-bold text-emerald-500">83,308</p>
          <p className="text-sm text-muted-foreground">Valid</p>
        </div>
      </div>
    </motion.div>
  );
}

function Step568Nodes({ title, icon: Icon, nodes }: { title: string, icon: any, nodes: string[] }) {
  return (
    <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="flex flex-col items-center justify-center h-full space-y-12 max-w-4xl mx-auto">
      <h2 className="text-3xl font-bold flex items-center gap-3">
        <Icon className="w-10 h-10 text-primary" />
        {title}
      </h2>
      <div className="flex flex-wrap justify-center gap-6">
        {nodes.map((node, i) => (
          <motion.div 
            key={node}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.15 }}
            className="bg-card border border-border shadow-lg rounded-2xl p-6 flex flex-col items-center gap-4 min-w-[160px]"
          >
            <CheckCircle2 className="w-8 h-8 text-emerald-500" />
            <span className="font-semibold text-center">{node}</span>
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
}

function Step7Semantic() {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col items-center justify-center h-full space-y-12">
      <h2 className="text-3xl font-bold flex items-center gap-3 text-purple-400">
        <Sparkles className="w-8 h-8" />
        Semantic Intelligence
      </h2>
      <div className="flex items-center gap-12 w-full max-w-4xl justify-center">
        <div className="flex flex-col items-center space-y-4 flex-1">
          <Badge variant="outline" className="text-xs">JD Embedding Vector</Badge>
          <div className="w-full h-32 bg-purple-500/10 border border-purple-500/30 rounded-xl flex items-center justify-center overflow-hidden relative">
             <motion.div animate={{ opacity: [0.5, 1, 0.5] }} transition={{ repeat: Infinity, duration: 2 }} className="absolute inset-0 bg-gradient-to-r from-transparent via-purple-500/20 to-transparent" />
             <span className="font-mono text-xs text-purple-300 opacity-70">[0.12, -0.44, ... 1536d]</span>
          </div>
        </div>
        
        <div className="flex flex-col items-center justify-center">
          <motion.div animate={{ scale: [1, 1.1, 1] }} transition={{ repeat: Infinity, duration: 1 }}>
            <Zap className="w-12 h-12 text-yellow-500" />
          </motion.div>
          <span className="text-xs font-bold mt-2 text-muted-foreground uppercase tracking-wider">Cosine Sim</span>
        </div>

        <div className="flex flex-col items-center space-y-4 flex-1">
          <Badge variant="outline" className="text-xs">Candidate Embedding</Badge>
          <div className="w-full h-32 bg-blue-500/10 border border-blue-500/30 rounded-xl flex items-center justify-center overflow-hidden relative">
             <motion.div animate={{ opacity: [0.5, 1, 0.5] }} transition={{ repeat: Infinity, duration: 2, delay: 0.5 }} className="absolute inset-0 bg-gradient-to-r from-transparent via-blue-500/20 to-transparent" />
             <span className="font-mono text-xs text-blue-300 opacity-70">[0.14, -0.41, ... 1536d]</span>
          </div>
        </div>
      </div>
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 1 }} className="bg-muted/40 p-4 rounded-xl border border-border">
        <p className="text-sm font-medium">Confidence Score: <span className="text-emerald-500 font-bold">0.924</span></p>
      </motion.div>
    </motion.div>
  );
}

function Step9Formula() {
  return (
    <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} className="flex flex-col items-center justify-center h-full space-y-16 w-full max-w-5xl mx-auto">
      <h2 className="text-4xl font-black tracking-tight bg-gradient-to-r from-primary to-emerald-500 bg-clip-text text-transparent">Hybrid Ranking Formula</h2>
      
      <div className="flex items-center justify-center gap-4 text-2xl font-bold w-full">
        <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.1 }} className="flex flex-col items-center bg-card p-4 rounded-xl border border-border shadow-sm flex-1"><span className="text-blue-500">Career</span><span className="text-sm text-muted-foreground font-normal">w=0.2</span></motion.div>
        <span>+</span>
        <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.2 }} className="flex flex-col items-center bg-card p-4 rounded-xl border border-border shadow-sm flex-1"><span className="text-emerald-500">Skill</span><span className="text-sm text-muted-foreground font-normal">w=0.3</span></motion.div>
        <span>+</span>
        <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.3 }} className="flex flex-col items-center bg-card p-4 rounded-xl border border-border shadow-sm flex-1"><span className="text-amber-500">Behavior</span><span className="text-sm text-muted-foreground font-normal">w=0.15</span></motion.div>
        <span>+</span>
        <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.4 }} className="flex flex-col items-center bg-card p-4 rounded-xl border border-border shadow-sm flex-1"><span className="text-purple-500">Semantic</span><span className="text-sm text-muted-foreground font-normal">w=0.35</span></motion.div>
      </div>

      <motion.div initial={{ scale: 0, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ delay: 0.8, type: 'spring' }} className="flex flex-col items-center">
        <div className="w-1 h-8 bg-border mb-2" />
        <div className="bg-primary text-primary-foreground px-12 py-6 rounded-2xl shadow-2xl flex flex-col items-center">
          <span className="text-lg opacity-80 uppercase tracking-widest font-semibold mb-1">Final Score</span>
          <span className="text-5xl font-black">Top-K Min-Heap</span>
        </div>
      </motion.div>
    </motion.div>
  );
}


// --- MAIN COMPONENT ---

export default function PipelineVisualization() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: pStatus } = useQuery({
    queryKey: ['pipelineStatus'],
    queryFn: () => getPipelineStatus(),
    refetchInterval: 1000 // Poll every second
  });

  const mutation = useMutation({
    mutationFn: () => rankCandidates("Senior ML Engineer", 100),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['candidates'] });
      setTimeout(() => navigate('/candidates'), 3000);
    }
  });

  const isPlaying = pStatus?.isPlaying || mutation.isPending;
  const currentStep = pStatus?.currentStep || 1;
  const metrics = pStatus?.metrics || {
    candidatesProcessed: 0,
    runtimeSeconds: 0,
    heapSize: 0,
    cacheHits: 0,
    memoryMb: 150,
  };

  const handleTogglePlay = () => {
    if (!isPlaying) {
      mutation.mutate();
    }
  };

  const renderStep = () => {
    switch (currentStep) {
      case 1: return <Step1JDInput />;
      case 2: return <Step1JDInput />; // Keep same visual but maybe add parsed highlight, keeping simple
      case 3: return <Step3Loading />;
      case 4: return <Step4Integrity />;
      case 5: return <Step568Nodes title="Career Trajectory Analysis" icon={Search} nodes={['Title Match', 'Experience Progression', 'Product Company Tier']} />;
      case 6: return <Step568Nodes title="Skill Extraction & Scoring" icon={Code2} nodes={['Tier A Skills', 'Coverage %', 'Skill Consistency']} />;
      case 7: return <Step7Semantic />;
      case 8: return <Step568Nodes title="Behavioral Signals" icon={Activity} nodes={['Response Rate', 'Notice Period', 'Passive Activity']} />;
      case 9: return <Step9Formula />;
      default: return null;
    }
  };

  const stepsList = [
    { num: 1, name: 'Parse JD' },
    { num: 3, name: 'Load 100k' },
    { num: 4, name: 'Integrity' },
    { num: 5, name: 'Career' },
    { num: 6, name: 'Skills' },
    { num: 7, name: 'Semantic' },
    { num: 8, name: 'Behavior' },
    { num: 9, name: 'Rank Heap' },
  ];

  return (
    <div className="h-[calc(100vh-6.5rem)] flex gap-4">
      
      {/* LEFT PANEL: MAIN VISUALIZATION (flex-1) */}
      <div className="flex-1 bg-[#0a0a0a] rounded-2xl border border-border/50 shadow-2xl overflow-hidden relative flex flex-col">
        {/* Top Progress Bar */}
        <div className="absolute top-0 left-0 right-0 h-1.5 bg-muted/20">
          <motion.div 
            className="h-full bg-primary"
            initial={{ width: '0%' }}
            animate={{ width: `${(currentStep / 9) * 100}%` }}
            transition={{ duration: 0.5 }}
          />
        </div>

        {/* Step Indicator */}
        <div className="p-6 flex items-center gap-2">
          {stepsList.map((s, i) => (
            <div key={s.num} className="flex items-center">
              <div className={`text-xs font-semibold px-2 py-1 rounded-full transition-colors ${currentStep >= s.num ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'}`}>
                {s.name}
              </div>
              {i < stepsList.length - 1 && <ChevronRight className="w-3 h-3 mx-1 text-muted-foreground opacity-50" />}
            </div>
          ))}
        </div>

        {/* Canvas Area */}
        <div className="flex-1 relative overflow-hidden">
          {/* Subtle grid background */}
          <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px]" />
          
          <AnimatePresence mode="wait">
            <motion.div 
              key={currentStep} 
              initial={{ opacity: 0 }} 
              animate={{ opacity: 1 }} 
              exit={{ opacity: 0 }}
              transition={{ duration: 0.3 }}
              className="absolute inset-0 z-10 p-8"
            >
              {renderStep()}
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Playback Controls */}
        <div className="p-4 border-t border-border/50 flex justify-center gap-4 bg-background/50 backdrop-blur">
          <Button variant="outline" size="icon" disabled>
            <RotateCcw className="w-4 h-4" />
          </Button>
          <Button size="lg" className="px-8 font-bold" onClick={handleTogglePlay} disabled={isPlaying}>
            {isPlaying ? <><Pause className="w-4 h-4 mr-2" /> Processing...</> : <><Play className="w-4 h-4 mr-2" /> Start Processing</>}
          </Button>
          <Button variant="outline" size="icon" onClick={() => navigate('/candidates')}>
            <ChevronRight className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* RIGHT PANEL: BENCHMARK / SYSTEM STATUS (w-80) */}
      <div className="w-80 flex flex-col gap-4 shrink-0">
        <Card className="p-5 bg-card/50 backdrop-blur border-border/50">
          <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2 mb-4">
            <Activity className="w-4 h-4" /> Live Metrics
          </h3>
          <div className="space-y-5">
            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-muted-foreground">Candidates Processed</span>
                <span className="font-mono font-medium">{metrics.candidatesProcessed.toLocaleString()}/100k</span>
              </div>
              <Progress value={(metrics.candidatesProcessed / 100000) * 100} className="h-1.5" />
            </div>
            
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-muted/30 p-3 rounded-lg border border-border">
                <p className="text-xs text-muted-foreground mb-1">Runtime</p>
                <p className="text-xl font-mono font-bold text-foreground">{metrics.runtimeSeconds.toFixed(1)}s</p>
              </div>
              <div className="bg-muted/30 p-3 rounded-lg border border-border">
                <p className="text-xs text-muted-foreground mb-1">Memory</p>
                <p className="text-xl font-mono font-bold text-foreground">{metrics.memoryMb}MB</p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="bg-muted/30 p-3 rounded-lg border border-border">
                <p className="text-xs text-muted-foreground mb-1">Min-Heap</p>
                <p className="text-xl font-mono font-bold text-primary">{metrics.heapSize}</p>
              </div>
              <div className="bg-muted/30 p-3 rounded-lg border border-border">
                <p className="text-xs text-muted-foreground mb-1">Cache Hit</p>
                <p className="text-xl font-mono font-bold text-emerald-500">{metrics.cacheHits}%</p>
              </div>
            </div>
          </div>
        </Card>

        <Card className="p-5 bg-card/50 backdrop-blur border-border/50 flex-1">
          <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2 mb-4">
            <Server className="w-4 h-4" /> Modules
          </h3>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium flex items-center gap-2"><Database className="w-3.5 h-3.5 text-blue-500"/> SQLite Loader</span>
              {currentStep > 3 ? <Badge variant="outline" className="text-emerald-500 border-emerald-500/20">Done</Badge> : <Badge className="animate-pulse">Active</Badge>}
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium flex items-center gap-2"><ShieldCheck className="w-3.5 h-3.5 text-amber-500"/> Integrity Scorer</span>
              {currentStep > 4 ? <Badge variant="outline" className="text-emerald-500 border-emerald-500/20">Done</Badge> : currentStep === 4 ? <Badge className="animate-pulse">Active</Badge> : <Badge variant="secondary">Wait</Badge>}
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium flex items-center gap-2"><Cpu className="w-3.5 h-3.5 text-purple-500"/> Semantic Layer</span>
              {currentStep > 7 ? <Badge variant="outline" className="text-emerald-500 border-emerald-500/20">Done</Badge> : (currentStep >= 5 && currentStep <= 7) ? <Badge className="animate-pulse">Active</Badge> : <Badge variant="secondary">Wait</Badge>}
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium flex items-center gap-2"><Zap className="w-3.5 h-3.5 text-primary"/> Ranker Engine</span>
              {currentStep > 9 ? <Badge variant="outline" className="text-emerald-500 border-emerald-500/20">Done</Badge> : currentStep >= 8 ? <Badge className="animate-pulse">Active</Badge> : <Badge variant="secondary">Wait</Badge>}
            </div>
          </div>
        </Card>
      </div>

    </div>
  );
}
