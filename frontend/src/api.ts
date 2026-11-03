export interface ExecResult {
  exit_code: number;
  stdout: string;
  stderr: string;
  timed_out: boolean;
  killed_oom: boolean;
  duration_ms: number;
}

export type EventType =
  | "status"
  | "code"
  | "exec"
  | "diagnosis"
  | "done"
  | "error";

export interface AgentEvent {
  type: EventType;
  attempt: number;
  message: string;
  code?: string | null;
  result?: ExecResult | null;
  success?: boolean | null;
}

/**
 * POST /api/run and consume the SSE stream, invoking `onEvent` per event.
 * Uses fetch + a ReadableStream reader (EventSource can't POST a body).
 */
export async function runAgent(
  task: string,
  startingCode: string | undefined,
  onEvent: (e: AgentEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const resp = await fetch("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task, starting_code: startingCode || null }),
    signal,
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`Server error: ${resp.status}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const line = chunk.split("\n").find((l) => l.startsWith("data:"));
      if (!line) continue;
      try {
        onEvent(JSON.parse(line.slice(5).trim()) as AgentEvent);
      } catch {
        /* ignore partial */
      }
    }
  }
}

export async function getHealth(): Promise<any> {
  const r = await fetch("/api/health");
  return r.json();
}
