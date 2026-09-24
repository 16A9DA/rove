"use client";

import { useState } from "react";
import { Chat } from "@/components/Chat";
import { Settings } from "@/components/Settings";
import { Sidebar } from "@/components/Sidebar";
import { ROVE_API_BASE } from "@/lib/roveApi";
import type { AgentState, Message, Task } from "@/types/task";

type View = "chat" | "settings";

// ponytail: agent loop is simulated with timeouts, no backend wired yet.
// Real loop (Groq + tools + controller) lands in Phase 9.
function simulateAgentRun(
  text: string,
  onExecuting: () => void,
  onDone: (message: Message, status: Task["status"]) => void,
) {
  const isError = /error/i.test(text);

  const executingTimer = setTimeout(onExecuting, 700);
  const doneTimer = setTimeout(() => {
    onDone(
      {
        id: crypto.randomUUID(),
        role: "agent",
        content: isError
          ? "Ran into a problem completing that task. The target application did not respond."
          : "Done. Task completed.",
        isError,
        createdAt: Date.now(),
      },
      isError ? "error" : "complete",
    );
  }, 1600);

  return () => {
    clearTimeout(executingTimer);
    clearTimeout(doneTimer);
  };
}

export function AppShell() {
  const [view, setView] = useState<View>("chat");
  const [messages, setMessages] = useState<Message[]>([]);
  const [agentState, setAgentState] = useState<AgentState>("idle");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [pausedBackendTaskId, setPausedBackendTaskId] = useState<string | null>(null);

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

  const handleSend = (text: string) => {
    if (agentState === "thinking" || agentState === "executing") return;

    const taskId = beginTurn(text);
    simulateAgentRun(
      text,
      () => setAgentState("executing"),
      (agentMessage, status) => finishTurn(taskId, agentMessage, status),
    );
  };

  // Voice commands skip the simulated loop and hit the real orchestrator —
  // Phase 14 connects Moonshine's transcript straight through to the agent
  // running on the real computer, unlike typed messages (still simulated
  // until the rest of the chat loop is wired up).
  // Shared by the initial run and a resume — both just POST to a different
  // endpoint and land the same way: paused (mouse/keyboard touched mid-run,
  // resumable), done, or errored.
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
      const isError = !response.ok || (!isPaused && !responseBody.success);
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

    const taskId = beginTurn(text);
    await runAgent(taskId, "/api/agent/run", { goal: text });
  };

  const handleResume = async () => {
    if (!pausedBackendTaskId || !activeTaskId) return;
    setTasks((prev) => prev.map((t) => (t.id === activeTaskId ? { ...t, status: "running" } : t)));
    await runAgent(activeTaskId, "/api/agent/resume", { task_id: pausedBackendTaskId });
  };

  const handleNewTask = () => {
    setMessages([]);
    setActiveTaskId(null);
    setAgentState("idle");
    setView("chat");
  };

  const handleSelectTask = (id: string) => {
    // ponytail: task transcripts aren't persisted yet (Phase 23), so
    // reopening a task starts a fresh conversation scoped to it.
    setActiveTaskId(id);
    setMessages([]);
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
          <Chat messages={messages} agentState={agentState} onSend={handleSend} onVoiceCommand={handleVoiceCommand} onResume={handleResume} />
        ) : (
          <Settings onClose={() => setView("chat")} />
        )}
      </main>
    </div>
  );
}
