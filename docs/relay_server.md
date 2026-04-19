# relay_server.py — Deep Dive

The relay runs on your VPS. It owns two listening sockets and a queue that
connects them.

## The Queue Architecture

```python
tunnel_queue: asyncio.Queue[
    tuple[asyncio.StreamReader, asyncio.StreamWriter]
] = asyncio.Queue()
```

This is the heart of the whole system. When a tunnel client connects, its
socket is placed in the queue. When a browser connects, one socket is taken
out. The queue decouples the two servers: tunnel connections arrive whenever
the laptop reconnects, public requests arrive whenever a browser hits the VPS,
and the queue holds the surplus either way.

In a real multi-tenant relay this would be `dict[str, asyncio.Queue]`, keyed
by hostname or SNI, so each tunnel owner gets their own slot.

## `asyncio.start_server` — Two Servers in One Process

```python
tunnel_server = await asyncio.start_server(
    handle_tunnel_client, "0.0.0.0", TUNNEL_PORT
)
public_server = await asyncio.start_server(
    handle_public_request, "0.0.0.0", PUBLIC_PORT
)
async with tunnel_server, public_server:
    await asyncio.gather(
        tunnel_server.serve_forever(),
        public_server.serve_forever(),
    )
```

`asyncio.start_server` registers an *accept callback* on the event loop.
Every time a new TCP connection arrives on that port, the event loop calls
the callback as a new coroutine — no threads, no forking. Both servers run
concurrently inside the same single-threaded event loop via `asyncio.gather`.

The `async with` block ensures both servers call `.close()` and drain
outstanding connections even on `KeyboardInterrupt`.

## `pipe` — Bidirectional Byte Relay

```python
async def pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
    try:
        while True:
            data = await src.read(4096)
            if not data:
                break
            dst.write(data)
            await dst.drain()
    except Exception:
        pass
    try:
        if dst.can_write_eof():
            dst.write_eof()
    except Exception:
        pass
```

`src.read(4096)` returns `b""` on EOF — that is the signal that the remote
side closed the write half of its socket. We break the loop and then call
`dst.write_eof()` to propagate the closure downstream.

**Why `write_eof` matters:** HTTP/1.1 with `Connection: close` signals the end
of a response body by closing the write half of the socket (a TCP FIN). Without
forwarding that FIN, the reader on the other end of `dst` waits forever for
more bytes that will never come. `write_eof()` sends the FIN.

**Why `can_write_eof()`:** Not all transports support half-close (TLS streams
don't). The guard prevents a crash on transports that would raise if you called
`write_eof` on them.

Two `pipe` coroutines are launched with `asyncio.gather` — one in each
direction — so the relay is fully bidirectional and neither direction blocks
the other.

## `asyncio.wait_for` — Timeout on Queue Get

```python
tunnel_reader, tunnel_writer = await asyncio.wait_for(
    tunnel_queue.get(), timeout=10
)
```

`tunnel_queue.get()` suspends if the queue is empty — i.e., no tunnel
connection is waiting. `asyncio.wait_for` wraps it with a deadline: if no
tunnel appears within 10 seconds, it raises `asyncio.TimeoutError` and we
return a 502 to the browser instead of hanging indefinitely.

## `asyncio.gather` with `return_exceptions=True`

```python
await asyncio.gather(
    pipe(public_reader, tunnel_writer),
    pipe(tunnel_reader, public_writer),
    return_exceptions=True,
)
```

`return_exceptions=True` tells `gather` not to cancel the other coroutine
if one raises. Without it, an exception in one `pipe` direction would
immediately cancel the other, potentially cutting off data mid-stream. With
it, both directions run to natural completion and exceptions are returned as
values rather than re-raised.
