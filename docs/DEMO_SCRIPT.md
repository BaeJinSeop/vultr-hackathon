# Demo video script (≈2–3 min)

The judges want to see a **containment moment**. Here's a tight script that hits every judging criterion (Application of Technology, Presentation, Business Value, Originality).

## 0:00 — Hook (15s)
> "Every AI coding agent runs code. The question is: where? We run it where it can't hurt you. This is **Blast Radius Zero**."

Show the UI header with the live limits badges (net: disabled, mem: 256m, timeout: 15s…). These prove the containment story up front.

## 0:15 — The happy path + self-healing (45s)
1. Click the **"Fix broken code (self-heal)"** example → Run.
2. Narrate as the timeline streams:
   - Attempt 1 runs, hits a `SyntaxError` (missing colon) → red verdict.
   - Diagnosis line appears ("missing colon in for-loop") → patching.
   - Attempt 2 runs → green ✓, prints the sum.
> "The agent read its own traceback, patched itself, and retried — all inside the sandbox. The loop is the product."

## 1:00 — Real work (30s)
1. Click **"Chart a sine wave"** → Run.
2. Show it generating matplotlib code and succeeding, printing `/tmp/plot.png`.
> "This isn't a chatbot. It executed real code and produced a real artifact — contained."

## 1:30 — The containment moment (45s) ⭐
1. Click **"😈 Containment: rm -rf /"** → Run.
2. Let it execute. The sandbox absorbs it (read-only FS + non-root → the command fails harmlessly or deletes nothing that matters; container is destroyed either way).
3. Then click **"😈 Containment: infinite loop"** → Run.
4. Show the ⏱ timeout verdict: "Killed after 15s timeout. Host untouched."
5. **Cut to a terminal on the VM** running `ls /` and `docker ps` — host filesystem intact, no leftover containers.
> "A hostile task is just another handled failure. The host never flinched. Blast radius: zero."

## 2:15 — Architecture + Vultr (20s)
Show the architecture diagram. Say the three Vultr pieces out loud:
> "Backend on a **Vultr VM**. Every LLM call through **Vultr Serverless Inference**. Every execution in a throwaway **Vultr sandbox**. Containers are created and destroyed per task, hold no secrets, and have no network."

## 2:35 — Close (10s)
> "Give an agent hands, but keep them in a glovebox. Blast Radius Zero."

Show the public demo URL on screen.

---

### Shot list / checklist
- [ ] Limits badges visible in header
- [ ] A real self-heal (fail → diagnose → pass) on camera
- [ ] A real artifact produced (chart)
- [ ] `rm -rf /` attempt absorbed
- [ ] infinite loop timed out
- [ ] VM terminal showing host intact after the hostile runs
- [ ] Public demo URL shown
- [ ] GitHub repo URL shown
