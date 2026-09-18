export type AgentState =
  | "idle"
  | "listening"
  | "thinking"
  | "executing"
  | "complete"
  | "error";

export type MessageRole = "user" | "agent";

export type Message = {
  id: string;
  role: MessageRole;
  content: string;
  isError?: boolean;
  createdAt: number;
};

export type TaskStatus = "running" | "complete" | "error";

export type Task = {
  id: string;
  title: string;
  status: TaskStatus;
  createdAt: number;
};
