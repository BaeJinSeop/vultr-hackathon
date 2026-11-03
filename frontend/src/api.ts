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
    // FastAPI validation errors (e.g. task too long) come back as 422 JSON.
    const detail = await resp
      .json()
      .then((j) => (typeof j?.detail === "string" ? j.detail : null))
      .catch(() => null);
    if (resp.status === 429) {
      throw new Error("Too many runs from your network — wait a minute and retry.");
    }
    throw new Error(detail ?? `Server error: ${resp.status}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const emit = (chunk: string) => {
    const line = chunk.split("\n").find((l) => l.startsWith("data:"));
    if (!line) return;
    try {
      onEvent(JSON.parse(line.slice(5).trim()) as AgentEvent);
    } catch {
      /* ignore malformed */
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    chunks.forEach(emit);
  }
  // A final event without a trailing blank line would otherwise be dropped.
  buffer += decoder.decode();
  if (buffer.trim()) emit(buffer);
}

export async function getHealth(): Promise<any> {
  const r = await fetch("/api/health");
  return r.json();
}
