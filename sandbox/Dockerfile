# Minimal, locked-down image for running untrusted agent-generated Python.
# Kept deliberately small: fewer binaries = smaller attack surface.
FROM python:3.11-slim

# Common data/plot libs so generated code can do real work (CSV, charts, math).
RUN pip install --no-cache-dir \
    numpy==2.1.3 \
    pandas==2.2.3 \
    matplotlib==3.9.2

# Non-root user. Even if code escapes the interpreter it has no privileges.
RUN useradd --create-home --uid 10001 runner
USER runner
WORKDIR /home/runner

# The orchestrator passes the script as `-c <code>` at `docker run` time.
# No code is baked in; -I ignores PYTHON* env vars and the user site dir.
ENTRYPOINT ["python", "-I"]
