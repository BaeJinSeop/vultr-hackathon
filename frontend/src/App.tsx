import { useEffect, useRef, useState } from "react";
import { AgentEvent, getHealth, runAgent } from "./api";

const EXAMPLES: { label: string; task: string }[] = [
  {
    label: "Compute the 1000th prime",
    task: "Compute and print the 1000th prime number.",
  },
  {
    label: "Fix broken code (self-heal)",
    task:
      "Fix this code so it prints the sum of 1..100. The code has a bug.\n\n" +
      "total = 0\nfor i in range(1, 100)\n    total += i\nprint('sum', total)",
  },
  {
    label: "Chart a sine wave",
    task:
      "Plot y = sin(x) for x in [0, 2*pi] with matplotlib, save it to /tmp/plot.png, and print the path.",
  },
  {
    label: "😈 Containment: rm -rf /",
    task:
      "Run this exact Python and report what happened:\n\n" +
      "import subprocess\nsubprocess.run(['rm','-rf','/'], check=False)\nprint('tried to delete everything')",
  },
  {
    label: "😈 Containment: infinite loop",
    task: "Run `while True: pass` and tell me the result.",
  },
];

interface Attempt {
  n: number;
  code?: string;
  result?: AgentEvent["result"];
  verdict?: string;
  diagnosis?: string;
}

export default function App() {
  const [task, setTask] = useState(EXAMPLES[0].task);
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState("");
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [final, setFinal] = useState<AgentEvent | null>(null);
  const [limits, setLimits] = useState<any>(null);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    getHealth().then(setLimits).catch(() => setLimits(null));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [attempts, status, final]);

  function upsert(n: number, patch: Partial<Attempt>) {
    setAttempts((prev) => {
      const i = prev.findIndex((a) => a.n === n);
      if (i === -1) return [...prev, { n, ...patch }];
      const next = [...prev];
      next[i] = { ...next[i], ...patch };
      return next;
    });
  }

  async function start() {
    setRunning(true);
    setStatus("Starting…");
    setAttempts([]);
    setFinal(null);
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    try {
      await runAgent(task, undefined, (e) => {
        switch (e.type) {
          case "status":
            setStatus(e.message);
            break;
          case "code":
            upsert(e.attempt, { code: e.code ?? "" });
            setStatus(e.message);
            break;
          case "exec":
            upsert(e.attempt, { result: e.result, verdict: e.message });
            break;
          case "diagnosis":
            upsert(e.attempt, { diagnosis: e.message });
            break;
          case "done":
            setFinal(e);
            setStatus("");
            break;
          case "error":
            setStatus("");
            setFinal(e);
            break;
        }
      }, ctrl.signal);
    } catch (err: any) {
      setFinal({ type: "error", attempt: 0, message: String(err?.message || err) });
    } finally {
      setRunning(false);
    }
  }

  function stop() {
    abortRef.current?.abort();
    setRunning(false);
    setStatus("Stopped.");
  }

  return (
    <div className="wrap">
      <header>
        <h1>
          Blast Radius&nbsp;<span className="zero">Zero</span>
        </h1>
        <p className="sub">
          Self-healing code agent — every line runs in a throwaway Vultr sandbox.
        </p>
        {limits?.limits && (
          <div className="limits">
            <span>model: {limits.model}</span>
            <span>net: {limits.limits.network}</span>
            <span>mem: {limits.limits.memory}</span>
            <span>cpu: {limits.limits.cpus}</span>
            <span>timeout: {limits.limits.timeout_s}s</span>
            <span>pids: {limits.limits.pids}</span>
          </div>
        )}
      </header>

      <section className="panel">
        <label>Task</label>
        <textarea
          value={task}
          onChange={(e) => setTask(e.target.value)}
          rows={6}
          disabled={running}
        />
        <div className="examples">
          {EXAMPLES.map((ex) => (
            <button
              key={ex.label}
              className="chip"
              disabled={running}
              onClick={() => setTask(ex.task)}
            >
              {ex.label}
            </button>
          ))}
        </div>
        <div className="actions">
          {!running ? (
            <button className="run" onClick={start} disabled={!task.trim()}>
              ▶ Run in sandbox
            </button>
          ) : (
            <button className="stop" onClick={stop}>
              ■ Stop
            </button>
          )}
          {status && <span className="statusline">{status}</span>}
        </div>
      </section>

      <section className="timeline">
        {attempts.map((a) => (
          <div className="attempt" key={a.n}>
            <div className="attempt-head">
              <span className="badge">Attempt {a.n}</span>
              {a.verdict && (
                <span
                  className={
                    "verdict " +
                    (a.result?.exit_code === 0 &&
                    !a.result?.timed_out &&
                    !a.result?.killed_oom
                      ? "ok"
                      : "bad")
                  }
                >
                  {a.verdict}
                </span>
              )}
            </div>
            {a.code && (
              <pre className="code">
                <code>{a.code}</code>
              </pre>
            )}
            {a.result && (
              <div className="io">
                {a.result.stdout && (
                  <pre className="stdout">
                    <span className="io-label">stdout</span>
                    {a.result.stdout}
                  </pre>
                )}
                {a.result.stderr && (
                  <pre className="stderr">
                    <span className="io-label">stderr</span>
                    {a.result.stderr}
                  </pre>
                )}
              </div>
            )}
            {a.diagnosis && (
              <div className="diagnosis">
                <strong>Diagnosis:</strong> {a.diagnosis} → patching &amp; retrying…
              </div>
            )}
          </div>
        ))}

        {final && (
          <div
            className={
              "final " +
              (final.type === "error"
                ? "err"
                : final.success
                ? "success"
                : "fail")
            }
          >
            {final.type === "error"
              ? `⚠ ${final.message}`
              : final.success
              ? `✅ ${final.message}`
              : `❌ ${final.message}`}
          </div>
        )}
        <div ref={bottomRef} />
      </section>

      <footer>
        LLM via Vultr Serverless Inference · sandbox via Docker on a Vultr VM ·
        no network, no secrets, destroyed after every run.
      </footer>
    </div>
  );
}
