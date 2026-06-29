import type { Candidate } from '@/types/candidate';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { CheckCircle2, AlertTriangle, ExternalLink, UserPlus, Sparkles, Target, History, MessageSquare, Lightbulb } from 'lucide-react';
import { motion } from 'framer-motion';
import { ResponsiveContainer, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, RadialBarChart, RadialBar, Tooltip as RechartsTooltip } from 'recharts';

interface Props {
  cand: Candidate;
  onClose: () => void;
}

function HighlightedEvidence({ text, keywords }: { text: string, keywords: string[] }) {
  // Simple regex-based highlighting
  const regex = new RegExp(`(${keywords.join('|')})`, 'gi');
  const parts = text.split(regex);

  return (
    <p className="text-sm text-foreground/80 leading-relaxed font-medium">
      {parts.map((part, i) => 
        keywords.some(k => k.toLowerCase() === part.toLowerCase()) ? (
          <span key={i} className="bg-primary/20 text-primary px-1 rounded mx-0.5 border border-primary/30">
            {part}
          </span>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </p>
  );
}

export function AICopilotPanel({ cand, onClose }: Props) {
  const { copilot, scores } = cand;

  const radarData = [
    { subject: 'Career', A: scores.career_score * 100 },
    { subject: 'Skill', A: scores.skill_score * 100 },
    { subject: 'Semantic', A: scores.semantic_score * 100 },
    { subject: 'Behavior', A: scores.behavior_score * 100 },
    { subject: 'Integrity', A: scores.integrity_score * 100 },
    { subject: 'Consistency', A: scores.consistency_score * 100 },
  ];

  const gaugeData = [{
    name: 'Overall Fit',
    value: copilot.jd_match.overall_match_percentage,
    fill: 'var(--theme-primary)'
  }];

  const getRecBadge = (status: string) => {
    switch (status) {
      case 'Strong Hire': return <Badge className="bg-emerald-500 hover:bg-emerald-600 text-white border-transparent text-sm py-1 px-3">Strong Hire</Badge>;
      case 'Hire': return <Badge className="bg-emerald-500/20 text-emerald-600 border-transparent text-sm py-1 px-3">Hire</Badge>;
      case 'Interview Recommended': return <Badge className="bg-amber-500/20 text-amber-600 border-transparent text-sm py-1 px-3">Interview Recommended</Badge>;
      case 'Borderline': return <Badge variant="outline" className="text-muted-foreground text-sm py-1 px-3 border-border">Borderline</Badge>;
      case 'Reject': return <Badge variant="destructive" className="bg-red-500/20 text-red-600 border-transparent text-sm py-1 px-3">Reject</Badge>;
      default: return <Badge>{status}</Badge>;
    }
  };

  return (
    <motion.div 
      initial={{ x: 20, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: 20, opacity: 0 }}
      className="h-full bg-card rounded-lg border border-border shadow-sm flex flex-col overflow-hidden"
    >
      {/* Header Action Bar */}
      <div className="p-3 border-b border-border flex justify-between items-center bg-muted/20">
        <div className="flex items-center gap-2 text-primary font-semibold text-sm">
          <Sparkles className="w-4 h-4" />
          AI Recruiter Copilot
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
          <Button variant="outline" size="sm" className="gap-1"><ExternalLink className="w-4 h-4"/> Profile</Button>
          <Button size="sm" className="gap-1"><UserPlus className="w-4 h-4"/> Shortlist</Button>
        </div>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-5 space-y-8">
          
          {/* Section 1: Summary Header */}
          <div className="flex items-start gap-4">
            {/* Circular Gauge */}
            <div className="w-24 h-24 shrink-0 relative flex flex-col items-center justify-center">
              <ResponsiveContainer width="100%" height="100%">
                <RadialBarChart 
                  cx="50%" cy="50%" 
                  innerRadius="80%" outerRadius="100%" 
                  barSize={10} data={gaugeData} 
                  startAngle={90} endAngle={-270}
                >
                  <RadialBar background dataKey="value" cornerRadius={10} />
                </RadialBarChart>
              </ResponsiveContainer>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-2xl font-bold">{copilot.jd_match.overall_match_percentage}%</span>
                <span className="text-[10px] text-muted-foreground uppercase tracking-wider font-semibold">Fit</span>
              </div>
            </div>

            <div className="flex-1">
              <h2 className="text-2xl font-bold tracking-tight mb-2">{cand.name}</h2>
              <div className="mb-3">{getRecBadge(copilot.recommendation_status)}</div>
              <p className="text-sm text-muted-foreground leading-relaxed">
                {copilot.recommendation_reasoning}
              </p>
            </div>
          </div>

          {/* Tabs for deep dive */}
          <Tabs defaultValue="insights" className="w-full">
            <TabsList className="w-full grid grid-cols-4 mb-4">
              <TabsTrigger value="insights">Insights</TabsTrigger>
              <TabsTrigger value="scores">Scores</TabsTrigger>
              <TabsTrigger value="timeline">Timeline</TabsTrigger>
              <TabsTrigger value="action">Action</TabsTrigger>
            </TabsList>
            
            <TabsContent value="insights" className="space-y-6">
              {/* Pros & Cons Matrix */}
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-xl p-4">
                  <h3 className="text-xs font-bold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4" /> Why Ranked
                  </h3>
                  <ul className="space-y-2">
                    {copilot.why_ranked.map((pro, i) => (
                      <motion.li 
                        key={i}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: i * 0.1 }}
                        className="text-sm font-medium flex items-start gap-2 text-foreground/80"
                      >
                        <span className="text-emerald-500 mt-0.5">•</span>
                        {pro}
                      </motion.li>
                    ))}
                  </ul>
                </div>
                
                <div className="bg-amber-500/5 border border-amber-500/20 rounded-xl p-4">
                  <h3 className="text-xs font-bold text-amber-600 dark:text-amber-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4" /> Potential Risks
                  </h3>
                  {copilot.potential_risks.length > 0 ? (
                    <ul className="space-y-2">
                      {copilot.potential_risks.map((risk, i) => (
                        <motion.li 
                          key={i}
                          initial={{ opacity: 0, x: -10 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: i * 0.1 }}
                          className="text-sm font-medium flex items-start gap-2 text-foreground/80"
                        >
                          <span className="text-amber-500 mt-0.5">•</span>
                          {risk}
                        </motion.li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-muted-foreground italic">No critical risks identified.</p>
                  )}
                </div>
              </div>

              <Separator />

              {/* Semantic Evidence */}
              <div>
                <h3 className="text-sm font-bold flex items-center gap-2 mb-4">
                  <Target className="w-4 h-4 text-primary" />
                  Semantic Evidence
                </h3>
                <div className="space-y-3">
                  {copilot.semantic_evidence.map((ev, i) => (
                    <div key={i} className="bg-muted/30 p-3 rounded-lg border border-border">
                      <HighlightedEvidence text={ev.sentence} keywords={ev.keywords} />
                    </div>
                  ))}
                </div>
              </div>
            </TabsContent>

            <TabsContent value="scores" className="space-y-6">
              {/* Score Radar Chart */}
              <div className="h-[250px] w-full bg-muted/10 rounded-xl border border-border flex items-center justify-center p-4">
                <ResponsiveContainer width="100%" height="100%">
                  <RadarChart cx="50%" cy="50%" outerRadius="70%" data={radarData}>
                    <PolarGrid stroke="hsl(var(--border))" />
                    <PolarAngleAxis dataKey="subject" tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }} />
                    <PolarRadiusAxis angle={30} domain={[0, 100]} tick={false} axisLine={false} />
                    <Radar name="Candidate" dataKey="A" stroke="hsl(var(--primary))" fill="hsl(var(--primary))" fillOpacity={0.3} />
                    <RechartsTooltip 
                      contentStyle={{ backgroundColor: 'hsl(var(--card))', borderColor: 'hsl(var(--border))', borderRadius: '8px' }}
                      itemStyle={{ color: 'hsl(var(--primary))', fontWeight: 'bold' }}
                    />
                  </RadarChart>
                </ResponsiveContainer>
              </div>

              {/* JD Match Breakdown */}
              <div className="space-y-4">
                <h3 className="text-sm font-bold">JD Match Breakdown</h3>
                
                <div className="space-y-2">
                  <span className="text-xs text-muted-foreground font-semibold uppercase">Required Skills</span>
                  <div className="flex flex-wrap gap-1.5">
                    {copilot.jd_match.required_skills_found.map(s => <Badge key={s} variant="secondary" className="bg-emerald-500/10 text-emerald-600">{s}</Badge>)}
                    {copilot.jd_match.missing_skills.map(s => <Badge key={s} variant="outline" className="border-red-500/50 text-red-500 line-through opacity-70">{s}</Badge>)}
                  </div>
                </div>

                <div className="space-y-2">
                  <span className="text-xs text-muted-foreground font-semibold uppercase">Preferred Skills</span>
                  <div className="flex flex-wrap gap-1.5">
                    {copilot.jd_match.preferred_skills_found.map(s => <Badge key={s} variant="secondary">{s}</Badge>)}
                  </div>
                </div>
              </div>
            </TabsContent>

            <TabsContent value="timeline" className="space-y-6">
              <h3 className="text-sm font-bold flex items-center gap-2">
                <History className="w-4 h-4 text-primary" />
                Professional Timeline
              </h3>
              <div className="relative border-l-2 border-border ml-3 mt-4 space-y-6 pb-4">
                {copilot.timeline.map((event, i) => (
                  <motion.div 
                    key={i}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.15 }}
                    className="relative pl-6"
                  >
                    <div className={`absolute -left-[9px] top-1 w-4 h-4 rounded-full border-2 border-card ${event.is_relevant ? 'bg-primary' : 'bg-muted-foreground'}`} />
                    <h4 className="font-bold text-sm">{event.title}</h4>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-xs font-semibold text-foreground/80">{event.company}</span>
                      <span className="text-xs text-muted-foreground">• {event.year}</span>
                    </div>
                  </motion.div>
                ))}
              </div>
            </TabsContent>

            <TabsContent value="action" className="space-y-6">
              <div className="bg-card border border-primary/20 rounded-xl p-5 shadow-sm relative overflow-hidden">
                <div className="absolute top-0 right-0 p-4 opacity-5">
                  <MessageSquare className="w-24 h-24" />
                </div>
                <h3 className="text-sm font-bold flex items-center gap-2 mb-4 text-primary relative z-10">
                  <Lightbulb className="w-4 h-4" />
                  Interview Suggestions
                </h3>
                <p className="text-xs text-muted-foreground mb-4 relative z-10">
                  Automatically generated based on the candidate's semantic evidence and identified skill gaps.
                </p>
                <ul className="space-y-3 relative z-10">
                  {copilot.interview_questions.map((q, i) => (
                    <li key={i} className="text-sm font-medium bg-muted/50 p-3 rounded-lg border border-border/50">
                      <span className="text-primary font-bold mr-2">Q{i+1}.</span>{q}
                    </li>
                  ))}
                </ul>
              </div>
            </TabsContent>
          </Tabs>

        </div>
      </ScrollArea>
    </motion.div>
  );
}
