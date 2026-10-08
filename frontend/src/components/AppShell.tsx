"use client";

import { useRef, useState } from "react";
import { Chat } from "@/components/Chat";
import { Settings } from "@/components/Settings";
import { Sidebar } from "@/components/Sidebar";
import { ROVE_API_BASE } from "@/lib/roveApi";
import type { ActivityStep, AgentState, Message, PreviewFrame, Task } from "@/types/task";

type View = "chat" | "settings";

export function AppShell() {
  const [view, setView] = useState<View>("chat");
  const [messages, setMessages] = useState<Message[]>([]);
  const [agentState, setAgentState] = useState<AgentState>("idle");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [pausedBackendTaskId, setPausedBackendTaskId] = useState<string | null>(null);
  const [steps, setSteps] = useState<ActivityStep[]>([]);
  const [preview, setPreview] = useState<PreviewFrame | null>(null);
  const stream = useRef<EventSource | null>(null);
  const lastSeq = useRef(0);
  const runningBackendId = useRef<string | null>(null);

  const beginTurn = (text: string): string => {
    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
      createdAt: Date.now(),
    };
    setMessages((prev) => [...prev, userMessage]);

    let taskId = activeTaskId;
    if (!taskId) {
      taskId = crypto.randomUUID();
      const newTask: Task = {
        id: taskId,
        title: text.length > 40 ? `${text.slice(0, 40)}…` : text,
        status: "running",
        createdAt: Date.now(),
      };
      setTasks((prev) => [newTask, ...prev]);
      setActiveTaskId(taskId);
    } else {
      setTasks((prev) => prev.map((t) => (t.id === taskId ? { ...t, status: "running" } : t)));
    }

    setAgentState("thinking");
    return taskId;
  };

  const finishTurn = (taskId: string, agentMessage: Message, status: Task["status"]) => {
    setMessages((prev) => [...prev, agentMessage]);
    setAgentState(status === "error" ? "error" : status === "paused" ? "paused" : "complete");
    setTasks((prev) => prev.map((t) => (t.id === taskId ? { ...t, status } : t)));
  };

  // Live steps arrive over SSE while the run's POST is still blocking; a resume
  // reconnects with the last seen seq so earlier steps aren't replayed.
  const openStream = (backendTaskId: string, fresh: boolean) => {
    stream.current?.close();
    if (fresh) {
      lastSeq.current = 0;
      setSteps([]);
      setPreview(null);
    }
    runningBackendId.current = backendTaskId;
    const source = new EventSource(`${ROVE_API_BASE}/api/agent/${backendTaskId}/events?after=${lastSeq.current}`);
    source.onmessage = (message) => {
      const event = JSON.parse(message.data);
      lastSeq.current = event.seq;
      if (event.type === "step") {
        setSteps((prev) => {
          const next: ActivityStep = { id: event.id, agent: event.agent, label: event.label, status: event.status };
          return prev.some((s) => s.id === event.id) ? prev.map((s) => (s.id === event.id ? next : s)) : [...prev, next];
        });
      } else if (event.type === "frame") {
        setPreview({ src: `${ROVE_API_BASE}/api/agent/${backendTaskId}/frame?n=${event.n}`, url: event.url, app: event.app });
      } else if (event.type === "run_finished") {
        source.close();
      }
    };
    source.onerror = () => source.close();
    stream.current = source;
  };

  const startRun = async (text: string) => {
    const taskId = beginTurn(text);
    const backendTaskId = crypto.randomUUID();
    openStream(backendTaskId, true);
    await runAgent(taskId, "/api/agent/run", { goal: text, task_id: backendTaskId });
  };

  const handleSend = async (text: string) => {
    if (agentState === "thinking" || agentState === "executing") return;
    await startRun(text);
  };

  const handleStop = async () => {
    if (!runningBackendId.current) return;
    await fetch(`${ROVE_API_BASE}/api/agent/${runningBackendId.current}/stop`, { method: "POST" }).catch(() => undefined);
  };

  // Shared by the initial run and a resume — both just POST to a different
  // endpoint and land the same way: paused (mouse/keyboard touched mid-run,
  // resumable), stopped, done, or errored.
  const runAgent = async (taskId: string, path: string, body: Record<string, unknown>) => {
    setAgentState("executing");

    try {
      const response = await fetch(`${ROVE_API_BASE}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const responseBody = await response.json();
      const isPaused = response.ok && responseBody.error === "paused";
      const isCancelled = response.ok && responseBody.error === "cancelled";
      const isError = !response.ok || (!isPaused && !isCancelled && !responseBody.success);
      setPausedBackendTaskId(isPaused ? responseBody.task_id : null);
      finishTurn(
        taskId,
        {
          id: crypto.randomUUID(),
          role: "agent",
          content: isPaused
            ? responseBody.question
              ? `Paused — needs your help: ${responseBody.question}`
              : "Paused — mouse or keyboard touched. Press Continue to resume."
            : isCancelled
              ? "Stopped."
              : isError
              ? (responseBody.detail ?? responseBody.error ?? "Ran into a problem completing that task.")
              : (responseBody.final_message ?? "Done."),
          isError,
          createdAt: Date.now(),
        },
        isPaused ? "paused" : isError ? "error" : "complete",
      );
    } catch (error) {
      setPausedBackendTaskId(null);
      finishTurn(
        taskId,
        {
          id: crypto.randomUUID(),
          role: "agent",
          content: error instanceof Error ? error.message : "Could not reach Rove backend.",
          isError: true,
          createdAt: Date.now(),
        },
        "error",
      );
    }
  };

  const handleVoiceCommand = async (text: string) => {
    if (agentState === "thinking" || agentState === "executing") return;
    await startRun(text);
  };

  const handleResume = async () => {
    if (!pausedBackendTaskId || !activeTaskId) return;
    setTasks((prev) => prev.map((t) => (t.id === activeTaskId ? { ...t, status: "running" } : t)));
    openStream(pausedBackendTaskId, false);
    await runAgent(activeTaskId, "/api/agent/resume", { task_id: pausedBackendTaskId });
  };

  const handleNewTask = () => {
    setMessages([]);
    setSteps([]);
    setPreview(null);
    setActiveTaskId(null);
    setAgentState("idle");
    setView("chat");
  };

  const handleSelectTask = (id: string) => {
    // ponytail: task transcripts aren't persisted yet (Phase 23), so
    // reopening a task starts a fresh conversation scoped to it.
    setActiveTaskId(id);
    setMessages([]);
    setSteps([]);
    setPreview(null);
    setAgentState("idle");
    setView("chat");
  };

  return (
    <div className="flex h-full">
      <Sidebar
        tasks={tasks}
        activeTaskId={activeTaskId}
        onSelectTask={handleSelectTask}
        onNewTask={handleNewTask}
        onOpenSettings={() => setView("settings")}
      />

      <main className="flex-1 overflow-hidden">
        {view === "chat" ? (
          <Chat
            messages={messages}
            agentState={agentState}
            steps={steps}
            preview={preview}
            onSend={handleSend}
            onVoiceCommand={handleVoiceCommand}
            onResume={handleResume}
            onStop={handleStop}
          />
        ) : (
          <Settings onClose={() => setView("chat")} />
        )}
      </main>
    </div>
  );
}
