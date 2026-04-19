"""
The relay server. Runs on your VPS (public IP required).

Two listening sockets:
  - Port 9000: where tunnel clients (your laptop) dial in. We keep a
               queue of available tunnel connections.
  - Port 80:   where the public internet (browsers) arrives. For each
               public request, we grab one tunnel connection from the
               queue and shuttle bytes between the browser and that
               tunnel.

The toy simplification: each tunnel connection handles exactly one
public request, then both sides close. The client reconnects
immediately to be ready for the next request. The real SniTun
protocol multiplexes many public requests over a single long-lived
tunnel — see the README.

Run it with (port 80 requires root):
    sudo python relay_server.py
"""

import asyncio


# Queue of available tunnel connections waiting to carry a public request.
# In a real, multi-tenant system this would be a dict keyed by hostname.
tunnel_queue: asyncio.Queue[
    tuple[asyncio.StreamReader, asyncio.StreamWriter]
] = asyncio.Queue()


async def pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
    """Copy bytes from src to dst until src closes.

    When src reaches EOF we signal EOF to dst so the opposite-direction
    pipe can unblock on its next read. Without this, a half-closed
    connection (e.g. HTTP with `Connection: close`) would hang forever.
    """
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


async def handle_tunnel_client(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    """Called when a tunnel client connects on :9000."""
    peer = writer.get_extra_info("peername")
    print(f"[relay] tunnel client ready from {peer}")
    await tunnel_queue.put((reader, writer))


async def handle_public_request(
    public_reader: asyncio.StreamReader, public_writer: asyncio.StreamWriter
) -> None:
    """Called when a browser connects on :80."""
    peer = public_writer.get_extra_info("peername")
    print(f"[relay] public request from {peer}")

    try:
        tunnel_reader, tunnel_writer = await asyncio.wait_for(
            tunnel_queue.get(), timeout=10
        )
    except asyncio.TimeoutError:
        public_writer.write(
            b"HTTP/1.1 502 Bad Gateway\r\n"
            b"Content-Length: 19\r\n"
            b"\r\n"
            b"No tunnel connected"
        )
        await public_writer.drain()
        public_writer.close()
        return

    print("[relay] forwarding through tunnel")
    await asyncio.gather(
        pipe(public_reader, tunnel_writer),
        pipe(tunnel_reader, public_writer),
        return_exceptions=True,
    )

    for w in (public_writer, tunnel_writer):
        try:
            w.close()
        except Exception:
            pass


async def main() -> None:
    tunnel_server = await asyncio.start_server(
        handle_tunnel_client, "0.0.0.0", 9000
    )
    public_server = await asyncio.start_server(
        handle_public_request, "0.0.0.0", 80
    )
    print("[relay] listening on :9000 (tunnel) and :80 (public)")
    async with tunnel_server, public_server:
        await asyncio.gather(
            tunnel_server.serve_forever(),
            public_server.serve_forever(),
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[relay] bye")
