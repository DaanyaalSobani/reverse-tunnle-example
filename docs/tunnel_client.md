# tunnel_client.py — Deep Dive

The tunnel client runs on your laptop. Its job is simple: repeatedly connect
to the relay and bridge each incoming request to the local service.

## `asyncio.open_connection` — The Outbound Dial

```python
tunnel_reader, tunnel_writer = await asyncio.open_connection(
    relay_host, RELAY_PORT
)
```

This is the move that defeats NAT. `open_connection` initiates an outbound
TCP handshake to the VPS. Because the laptop is the initiator, the NAT router
records a mapping for this connection and allows reply packets through — no
port forwarding needed. The resulting `(StreamReader, StreamWriter)` pair is
the tunnel socket, ready to carry the browser's request.

Immediately after opening the tunnel, we open a second connection to the local
service:

```python
local_reader, local_writer = await asyncio.open_connection(
    LOCAL_HOST, LOCAL_PORT
)
```

At this point we have two open sockets. The client's only job is to copy bytes
between them.

## The Session Loop

```python
async def main(relay_host: str) -> None:
    while True:
        try:
            await one_session(relay_host)
        except Exception as err:
            print(f"[client] session error: {err}")
        print("[client] session ended — reconnecting in 1s")
        await asyncio.sleep(1)
```

Each call to `one_session` handles exactly one request-response cycle, then
returns. The `while True` loop immediately reconnects, ensuring there is
always a fresh tunnel connection waiting in the relay's queue for the next
browser request.

`asyncio.sleep(1)` is a fixed backoff. A production client would use
exponential backoff with jitter to avoid thundering-herd reconnects.

## `await w.wait_closed()` — Clean Teardown

```python
for w in (tunnel_writer, local_writer):
    try:
        w.close()
        await w.wait_closed()
    except Exception:
        pass
```

`writer.close()` schedules the close but does not wait for it. `wait_closed()`
suspends until the underlying transport is actually torn down and all buffered
data has been flushed. Without it, the next iteration of the loop could open
new connections before the OS has fully released the old ones, leading to
resource leaks or stale-state bugs in longer-running sessions.

## Why `pipe` is Shared

The same `pipe` function is defined identically in both `relay_server.py` and
`tunnel_client.py`. In the demo they are separate copies to keep each file
self-contained. An obvious refactor is to move `pipe` into a shared
`tunnel_utils.py` module — but it would not change any behaviour.
