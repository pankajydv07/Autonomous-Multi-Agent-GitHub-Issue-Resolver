'use client';

import { useState, useEffect, useRef } from 'react';
import { useQuery, useMutation, useSubscription } from '@apollo/client';
import { GET_RUNS, GET_RUN_DETAILS, START_RUN, AGENT_PROGRESS } from '@/lib/queries';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Play, 
  CheckCircle, 
  XCircle, 
  Clock, 
  Loader2,
  Github,
  ExternalLink,
  Terminal,
  Plus,
  Zap,
  Brain,
  Code,
  FlaskConical,
  GitPullRequest
} from 'lucide-react';
import clsx from 'clsx';

type RunStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';

interface Run {
  id: string;
  issue: string;
  repoUrl: string;
  status: RunStatus;
  error?: string;
  plan?: string;
  patch?: string;
  tests?: string;
  prUrl?: string;
  createdAt: string;
  updatedAt: string;
  logs?: Log[];
}

interface Log {
  id: string;
  agentName: string;
  message: string;
  timestamp: string;
}

interface ProgressEvent {
  runId: string;
  agentName: string;
  eventType: string;
  content: string;
  timestamp: string;
}

const statusConfig: Record<RunStatus, { color: string; bg: string; icon: typeof CheckCircle }> = {
  PENDING: { color: 'text-zinc-400', bg: 'bg-zinc-500/10', icon: Clock },
  RUNNING: { color: 'text-blue-400', bg: 'bg-blue-500/10', icon: Loader2 },
  COMPLETED: { color: 'text-green-400', bg: 'bg-green-500/10', icon: CheckCircle },
  FAILED: { color: 'text-red-400', bg: 'bg-red-500/10', icon: XCircle },
  CANCELLED: { color: 'text-zinc-400', bg: 'bg-zinc-500/10', icon: XCircle },
};

const agentIcons: Record<string, typeof Brain> = {
  code_reader: Brain,
  planner: Zap,
  code_writer: Code,
  test_writer: FlaskConical,
  pr_agent: GitPullRequest,
};

const agentNames: Record<string, string> = {
  code_reader: 'Code Reader',
  planner: 'Planner',
  code_writer: 'Code Writer',
  test_writer: 'Test Writer',
  pr_agent: 'PR Agent',
};

const agents = ['code_reader', 'planner', 'code_writer', 'test_writer', 'pr_agent'];

export default function Dashboard() {
  const [selectedRun, setSelectedRun] = useState<Run | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [issue, setIssue] = useState('');
  const [repoUrl, setRepoUrl] = useState('');
  const [liveProgress, setLiveProgress] = useState<Record<string, ProgressEvent[]>>({});
  const [currentAgent, setCurrentAgent] = useState<string>('');
  const progressEndRef = useRef<HTMLDivElement>(null);

  const { data, loading, refetch } = useQuery(GET_RUNS, {
    variables: { limit: 50, offset: 0 },
    pollInterval: 3000,
  });

  const { data: detailsData } = useQuery(GET_RUN_DETAILS, {
    variables: { id: selectedRun?.id },
    skip: !selectedRun,
    pollInterval: selectedRun?.status === 'RUNNING' ? 2000 : 0,
  });

  const { data: progressData } = useSubscription(AGENT_PROGRESS, {
    variables: { runId: selectedRun?.id },
    skip: !selectedRun?.id,
  });

  const [startRun, { loading: starting }] = useMutation(START_RUN, {
    onCompleted: (data) => {
      setShowForm(false);
      setIssue('');
      setRepoUrl('');
      refetch();
      setSelectedRun({
        ...data.startRun,
        logs: [],
        createdAt: data.startRun.createdAt,
        updatedAt: data.startRun.createdAt,
      });
      setLiveProgress({});
      setCurrentAgent('');
    },
  });

  useEffect(() => {
    if (progressData?.agentProgress) {
      const event = progressData.agentProgress as ProgressEvent;
      
      if (event.eventType === 'started') {
        setCurrentAgent(event.agentName);
        setLiveProgress(prev => ({
          ...prev,
          [event.agentName]: [],
        }));
      } else if (event.eventType === 'thinking' || event.eventType === 'writing') {
        setLiveProgress(prev => ({
          ...prev,
          [event.agentName]: [...(prev[event.agentName] || []), event],
        }));
      } else if (event.eventType === 'completed') {
        if (currentAgent && currentAgent !== event.agentName) {
          setCurrentAgent(event.agentName);
        }
      }
    }
  }, [progressData, currentAgent]);

  useEffect(() => {
    if (progressEndRef.current) {
      progressEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [liveProgress]);

  const runs: Run[] = data?.getRuns || [];
  const selectedRunDetails = detailsData?.getRunDetails;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!issue.trim() || !repoUrl.trim()) return;
    startRun({ variables: { issue: issue.trim(), repoUrl: repoUrl.trim() } });
  };

  const formatDate = (date: string) => {
    return new Date(date).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const isAgentCompleted = (agentName: string): boolean => {
    const agentIndex = agents.indexOf(agentName);
    const currentIndex = agents.indexOf(currentAgent);
    return agentIndex < currentIndex;
  };

  const isAgentRunning = (agentName: string): boolean => {
    return agentName === currentAgent;
  };

  return (
    <div className="min-h-screen p-6 md:p-8">
      <div className="max-w-7xl mx-auto">
        <motion.header 
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8"
        >
          <div>
            <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
              <Zap className="w-8 h-8 text-primary" />
              Agent Orchestrator
            </h1>
            <p className="text-textMuted mt-1">Real-time AI agent execution</p>
          </div>
          <button
            onClick={() => setShowForm(true)}
            className="flex items-center gap-2 px-5 py-2.5 bg-primary hover:bg-primaryHover text-background font-medium rounded-lg transition-all duration-200 hover:scale-105"
          >
            <Plus className="w-4 h-4" />
            New Run
          </button>
        </motion.header>

        <div className="grid lg:grid-cols-3 gap-6">
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.1 }}
            className="lg:col-span-1 space-y-4"
          >
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-lg font-semibold">Runs</h2>
              <span className="text-xs text-textMuted bg-surface px-2 py-1 rounded">{runs.length}</span>
            </div>
            
            <div className="space-y-2 max-h-[70vh] overflow-y-auto pr-2">
              <AnimatePresence>
                {loading && runs.length === 0 ? (
                  <div className="flex items-center justify-center py-12">
                    <Loader2 className="w-6 h-6 text-primary animate-spin" />
                  </div>
                ) : runs.length === 0 ? (
                  <div className="text-center py-12 text-textMuted">
                    <Terminal className="w-12 h-12 mx-auto mb-3 opacity-30" />
                    <p>No runs yet</p>
                  </div>
                ) : (
                  runs.map((run, i) => (
                    <motion.button
                      key={run.id}
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.05 }}
                      onClick={() => {
                        setSelectedRun(run);
                        setLiveProgress({});
                        setCurrentAgent('');
                      }}
                      className={clsx(
                        "w-full text-left p-4 rounded-xl border transition-all duration-200",
                        selectedRun?.id === run.id
                          ? "bg-surface border-primary/50 shadow-lg shadow-primary/5"
                          : "bg-surface border-border hover:border-border hover:bg-surfaceHover"
                      )}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <p className="font-medium truncate">{run.issue}</p>
                          <p className="text-xs text-textMuted truncate mt-1 flex items-center gap-1">
                            <Github className="w-3 h-3" />
                            {run.repoUrl.replace('https://github.com/', '')}
                          </p>
                        </div>
                        <StatusBadge status={run.status} />
                      </div>
                      <p className="text-xs text-textMuted mt-2">{formatDate(run.createdAt)}</p>
                    </motion.button>
                  ))
                )}
              </AnimatePresence>
            </div>
          </motion.div>

          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2 }}
            className="lg:col-span-2"
          >
            {selectedRun ? (
              <RunDetails 
                run={selectedRunDetails || selectedRun}
                liveProgress={liveProgress}
                currentAgent={currentAgent}
                progressEndRef={progressEndRef}
                isAgentRunning={isAgentRunning}
                isAgentCompleted={isAgentCompleted}
                onRefresh={() => refetch()}
              />
            ) : (
              <div className="bg-surface border border-border rounded-2xl h-full min-h-[400px] flex items-center justify-center">
                <div className="text-center text-textMuted">
                  <Terminal className="w-16 h-16 mx-auto mb-4 opacity-20" />
                  <p>Select a run to view details</p>
                </div>
              </div>
            )}
          </motion.div>
        </div>

        <AnimatePresence>
          {showForm && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-50"
              onClick={() => setShowForm(false)}
            >
              <motion.div
                initial={{ scale: 0.95, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0.95, opacity: 0 }}
                onClick={(e) => e.stopPropagation()}
                className="bg-surface border border-border rounded-2xl p-6 w-full max-w-md"
              >
                <h3 className="text-xl font-semibold mb-4">Start New Run</h3>
                <form onSubmit={handleSubmit} className="space-y-4">
                  <div>
                    <label className="block text-sm text-textMuted mb-1.5">GitHub Issue</label>
                    <textarea
                      value={issue}
                      onChange={(e) => setIssue(e.target.value)}
                      placeholder="Describe the issue to fix..."
                      className="w-full px-4 py-3 bg-background border border-border rounded-lg resize-none focus:outline-none focus:border-primary/50 transition-colors"
                      rows={3}
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-textMuted mb-1.5">Repository URL</label>
                    <input
                      type="url"
                      value={repoUrl}
                      onChange={(e) => setRepoUrl(e.target.value)}
                      placeholder="https://github.com/owner/repo"
                      className="w-full px-4 py-3 bg-background border border-border rounded-lg focus:outline-none focus:border-primary/50 transition-colors"
                      required
                    />
                  </div>
                  <div className="flex gap-3 pt-2">
                    <button
                      type="button"
                      onClick={() => setShowForm(false)}
                      className="flex-1 px-4 py-2.5 border border-border rounded-lg hover:bg-surfaceHover transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={starting || !issue.trim() || !repoUrl.trim()}
                      className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-primary hover:bg-primaryHover disabled:opacity-50 disabled:cursor-not-allowed text-background font-medium rounded-lg transition-all"
                    >
                      {starting ? (
                        <>
                          <Loader2 className="w-4 h-4 animate-spin" />
                          Starting...
                        </>
                      ) : (
                        <>
                          <Play className="w-4 h-4" />
                          Start Run
                        </>
                      )}
                    </button>
                  </div>
                </form>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: RunStatus }) {
  const config = statusConfig[status];
  const Icon = config.icon;
  
  return (
    <span className={clsx("flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium", config.bg, config.color)}>
      {status === 'RUNNING' ? (
        <Loader2 className="w-3 h-3 animate-spin" />
      ) : (
        <Icon className="w-3 h-3" />
      )}
      {status}
    </span>
  );
}

function AgentProgressStepper({ 
  currentAgent, 
  isAgentRunning, 
  isAgentCompleted 
}: { 
  currentAgent: string;
  isAgentRunning: (name: string) => boolean;
  isAgentCompleted: (name: string) => boolean;
}) {
  return (
    <div className="flex items-center justify-between mb-6">
      {agents.map((agent, index) => {
        const Icon = agentIcons[agent];
        const running = isAgentRunning(agent);
        const completed = isAgentCompleted(agent);
        
        return (
          <div key={agent} className="flex items-center">
            <div className="flex flex-col items-center">
              <div className={clsx(
                "w-10 h-10 rounded-full flex items-center justify-center transition-all duration-300",
                completed ? "bg-primary/20 text-primary" :
                running ? "bg-blue-500/20 text-blue-400 animate-pulse" :
                "bg-surface border border-border text-textMuted"
              )}>
                <Icon className="w-5 h-5" />
              </div>
              <span className={clsx(
                "text-xs mt-1 font-medium",
                running ? "text-blue-400" : 
                completed ? "text-primary" : 
                "text-textMuted"
              )}>
                {agentNames[agent]}
              </span>
            </div>
            {index < agents.length - 1 && (
              <div className={clsx(
                "w-8 h-0.5 mx-1 mt-[-20px] transition-colors",
                completed ? "bg-primary" : "bg-border"
              )} />
            )}
          </div>
        );
      })}
    </div>
  );
}

function RunDetails({ 
  run, 
  liveProgress, 
  currentAgent,
  progressEndRef,
  isAgentRunning,
  isAgentCompleted,
  onRefresh 
}: { 
  run: Run;
  liveProgress: Record<string, ProgressEvent[]>;
  currentAgent: string;
  progressEndRef: React.RefObject<HTMLDivElement>;
  isAgentRunning: (name: string) => boolean;
  isAgentCompleted: (name: string) => boolean;
  onRefresh: () => void;
}) {
  const formatDate = (date: string) => {
    return new Date(date).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  const currentAgentProgress = currentAgent ? (liveProgress[currentAgent] || []) : [];

  return (
    <div className="bg-surface border border-border rounded-2xl overflow-hidden">
      <div className="p-6 border-b border-border">
        <AgentProgressStepper 
          currentAgent={currentAgent}
          isAgentRunning={isAgentRunning}
          isAgentCompleted={isAgentCompleted}
        />
        
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <StatusBadge status={run.status} />
              <span className="text-xs text-textMuted">{formatDate(run.createdAt)}</span>
            </div>
            <h3 className="text-xl font-semibold">{run.issue}</h3>
            <p className="text-sm text-textMuted flex items-center gap-1 mt-1">
              <Github className="w-4 h-4" />
              {run.repoUrl.replace('https://github.com/', '')}
            </p>
          </div>
          {run.prUrl && (
            <a
              href={run.prUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-4 py-2 bg-primary/10 text-primary hover:bg-primary/20 rounded-lg transition-colors text-sm font-medium"
            >
              <ExternalLink className="w-4 h-4" />
              View PR
            </a>
          )}
        </div>
        {run.error && (
          <div className="mt-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
            <p className="text-sm text-red-400 font-medium">Error</p>
            <p className="text-sm text-red-300/80 mt-1">{run.error}</p>
          </div>
        )}
      </div>

      <div className="p-6">
        <h4 className="text-sm font-semibold text-textMuted uppercase tracking-wider mb-4 flex items-center gap-2">
          <Terminal className="w-4 h-4" />
          Live Progress
          {run.status === 'RUNNING' && (
            <span className="flex items-center gap-1 text-xs text-blue-400 ml-auto">
              <span className="w-2 h-2 bg-blue-400 rounded-full animate-pulse" />
              Streaming
            </span>
          )}
        </h4>
        
        <div className="space-y-4 max-h-[500px] overflow-y-auto pr-2">
          {currentAgentProgress.length > 0 ? (
            <div className="space-y-3">
              {currentAgentProgress.map((event, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={clsx(
                    "p-3 rounded-lg border font-mono text-sm",
                    event.eventType === 'thinking' 
                      ? "bg-blue-500/5 border-blue-500/20 text-blue-300" 
                      : "bg-background/50 border-border"
                  )}
                >
                  <span className="text-xs text-textMuted uppercase tracking-wider">
                    {event.eventType === 'thinking' ? 'Thinking' : 'Output'}
                  </span>
                  <p className="mt-1 whitespace-pre-wrap">{event.content}</p>
                </motion.div>
              ))}
              <div ref={progressEndRef} />
            </div>
          ) : run.logs && run.logs.length > 0 ? (
            run.logs.map((log, i) => (
              <motion.div
                key={log.id || i}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.03 }}
                className="flex gap-3 p-3 bg-background/50 rounded-lg border border-border/50"
              >
                <div className="w-20 flex-shrink-0">
                  <span className="text-xs font-medium text-primary">{log.agentName}</span>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm">{log.message}</p>
                  <p className="text-xs text-textMuted mt-1">{formatDate(log.timestamp)}</p>
                </div>
              </motion.div>
            ))
          ) : (
            <p className="text-center text-textMuted py-8">
              {run.status === 'RUNNING' ? 'Waiting for agent to start...' : 'No progress available'}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
