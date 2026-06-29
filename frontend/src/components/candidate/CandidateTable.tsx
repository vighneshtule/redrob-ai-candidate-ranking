import { useQuery } from '@tanstack/react-query';
import { useCandidateStore } from '@/store/candidateStore';
import { getCandidates } from '@/api/rankingApi';
import type { Candidate, SortField } from '@/types/candidate';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { ChevronDown, ChevronUp, Download, Search, Settings2 } from 'lucide-react';
import { Checkbox } from '@/components/ui/checkbox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const COLUMNS = [
  { key: 'name', label: 'Candidate' },
  { key: 'current_title', label: 'Current Role' },
  { key: 'final_score', label: 'Final Score', sortable: true },
  { key: 'career_score', label: 'Career', sortable: true },
  { key: 'skill_score', label: 'Skill', sortable: true },
  { key: 'semantic_score', label: 'Semantic', sortable: true },
  { key: 'behavior_score', label: 'Behavior', sortable: true },
  { key: 'integrity_score', label: 'Integrity', sortable: true },
  { key: 'match_status', label: 'Status' },
];

export function CandidateTable() {
  const { 
    page, pageSize, sortField, sortOrder, searchQuery, 
    setPage, setPageSize, setSort, setSearchQuery,
    selectedCandidateId, setSelectedCandidateId,
    compareMode, compareCandidateIds, toggleCompareCandidate
  } = useCandidateStore();

  const { data: allCandidates = [], isLoading } = useQuery({
    queryKey: ['candidates'],
    queryFn: () => getCandidates(),
  });

  // Client-side sort and pagination
  let dataToRender = [...allCandidates];
  
  if (searchQuery) {
    dataToRender = dataToRender.filter(c => c.name.toLowerCase().includes(searchQuery.toLowerCase()) || c.current_title.toLowerCase().includes(searchQuery.toLowerCase()));
  }
  
  dataToRender.sort((a, b) => {
    let valA = (a.scores as any)?.[sortField] ?? a[sortField as keyof Candidate];
    let valB = (b.scores as any)?.[sortField] ?? b[sortField as keyof Candidate];
    
    if (valA < valB) return sortOrder === 'asc' ? -1 : 1;
    if (valA > valB) return sortOrder === 'asc' ? 1 : -1;
    return 0;
  });
  
  const total = dataToRender.length;
  const paginatedData = dataToRender.slice((page - 1) * pageSize, page * pageSize);

  const data = {
    data: paginatedData,
    total: total
  };

  const handleRowClick = (cand: Candidate) => {
    if (compareMode) {
      toggleCompareCandidate(cand.id);
    } else {
      setSelectedCandidateId(selectedCandidateId === cand.id ? null : cand.id);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'Excellent Match': return <Badge className="bg-emerald-500 hover:bg-emerald-600 text-white border-transparent">Excellent</Badge>;
      case 'Strong Match': return <Badge variant="secondary" className="bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border-transparent">Strong</Badge>;
      case 'Medium Match': return <Badge variant="secondary" className="bg-amber-500/20 text-amber-600 dark:text-amber-400 border-transparent">Medium</Badge>;
      case 'Needs Review': return <Badge variant="outline" className="text-muted-foreground border-border">Review</Badge>;
      case 'Rejected': return <Badge variant="destructive" className="bg-red-500/20 text-red-600 dark:text-red-400 border-transparent">Rejected</Badge>;
      default: return <Badge>{status}</Badge>;
    }
  };

  const renderSortIcon = (field: string) => {
    if (sortField !== field) return null;
    return sortOrder === 'asc' ? <ChevronUp className="w-4 h-4 ml-1" /> : <ChevronDown className="w-4 h-4 ml-1" />;
  };

  return (
    <div className="flex flex-col h-full bg-card rounded-lg border border-border shadow-sm overflow-hidden">
      {/* Toolbar */}
      <div className="p-4 border-b border-border flex items-center justify-between gap-4">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input 
            placeholder="Search candidates..." 
            className="pl-9 bg-background h-9"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" className="h-9">
            <Settings2 className="w-4 h-4 mr-2" />
            Filters
          </Button>
          <Button variant="outline" size="sm" className="h-9">
            <Download className="w-4 h-4 mr-2" />
            Export
          </Button>
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto">
        <Table>
          <TableHeader className="bg-muted/50 sticky top-0 z-10 shadow-sm backdrop-blur">
            <TableRow>
              {compareMode && (
                <TableHead className="w-[50px] text-center">Compare</TableHead>
              )}
              {COLUMNS.map((col) => (
                <TableHead 
                  key={col.key} 
                  className={col.sortable ? "cursor-pointer select-none whitespace-nowrap" : "whitespace-nowrap"}
                  onClick={() => col.sortable && setSort(col.key as SortField)}
                >
                  <div className="flex items-center">
                    {col.label}
                    {col.sortable && renderSortIcon(col.key)}
                  </div>
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: pageSize }).map((_, i) => (
                <TableRow key={i}>
                  {compareMode && <TableCell><Skeleton className="w-4 h-4 rounded" /></TableCell>}
                  <TableCell><Skeleton className="h-5 w-32" /></TableCell>
                  <TableCell><Skeleton className="h-5 w-40" /></TableCell>
                  {Array.from({ length: 7 }).map((_, j) => (
                    <TableCell key={j}><Skeleton className="h-5 w-16" /></TableCell>
                  ))}
                </TableRow>
              ))
            ) : data?.data.length === 0 ? (
              <TableRow>
                <TableCell colSpan={COLUMNS.length + (compareMode ? 1 : 0)} className="h-32 text-center text-muted-foreground">
                  No candidates found matching the criteria.
                </TableCell>
              </TableRow>
            ) : (
              data?.data.map((cand) => (
                <TableRow 
                  key={cand.id}
                  className={`cursor-pointer transition-colors hover:bg-muted/50 ${selectedCandidateId === cand.id && !compareMode ? 'bg-primary/5' : ''}`}
                  onClick={() => handleRowClick(cand)}
                >
                  {compareMode && (
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <Checkbox 
                        checked={compareCandidateIds.includes(cand.id)}
                        onCheckedChange={() => toggleCompareCandidate(cand.id)}
                        disabled={!compareCandidateIds.includes(cand.id) && compareCandidateIds.length >= 2}
                      />
                    </TableCell>
                  )}
                  <TableCell>
                    <div className="font-medium text-foreground">{cand.name}</div>
                    <div className="text-xs text-muted-foreground">{cand.id}</div>
                  </TableCell>
                  <TableCell>
                    <div className="text-sm">{cand.current_title}</div>
                    <div className="text-xs text-muted-foreground">{cand.company} • {cand.location}</div>
                  </TableCell>
                  <TableCell className="font-semibold text-primary">
                    {(cand.scores.final_score * 100).toFixed(1)}
                  </TableCell>
                  <TableCell>{(cand.scores.career_score * 100).toFixed(1)}</TableCell>
                  <TableCell>{(cand.scores.skill_score * 100).toFixed(1)}</TableCell>
                  <TableCell>{(cand.scores.semantic_score * 100).toFixed(1)}</TableCell>
                  <TableCell>{(cand.scores.behavior_score * 100).toFixed(1)}</TableCell>
                  <TableCell>{(cand.scores.integrity_score * 100).toFixed(1)}</TableCell>
                  <TableCell>{getStatusBadge(cand.match_status)}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Pagination Footer */}
      <div className="p-3 border-t border-border flex items-center justify-between bg-muted/20">
        <div className="text-sm text-muted-foreground">
          Showing {((page - 1) * pageSize) + 1} to {Math.min(page * pageSize, data?.total || 0)} of {data?.total || 0}
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">Rows</span>
            <Select value={pageSize.toString()} onValueChange={(v) => setPageSize(Number(v))}>
              <SelectTrigger className="h-8 w-[70px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {[10, 25, 50, 100].map(size => (
                  <SelectItem key={size} value={size.toString()}>{size}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-1">
            <Button variant="outline" size="sm" className="h-8" disabled={page === 1} onClick={() => setPage(page - 1)}>Prev</Button>
            <Button variant="outline" size="sm" className="h-8" disabled={!data || page * pageSize >= data.total} onClick={() => setPage(page + 1)}>Next</Button>
          </div>
        </div>
      </div>
    </div>
  );
}
