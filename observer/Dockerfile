# The observer uses the portable /proc telemetry backend by default.  When
# deployed with hostPID + hostNetwork it can inspect the Arena node without
# needing a Python BCC package inside this container.  Install BCC on the
# Arena host separately only if kernel-level syscall tracepoints are needed.
FROM python:3.12-slim

WORKDIR /app
COPY observer/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY observer /app/observer

ENV PYTHONUNBUFFERED=1
CMD ["python", "/app/observer/probes/observer.py"]
