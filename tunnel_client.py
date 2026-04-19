"""
The tunnel client. Runs on your laptop (behind NAT).

This is the crucial piece that makes NAT irrelevant. Your laptop
initiates an OUTBOUND TCP connection to the relay on :9000 — exactly
the kind of connection your router happily allows. Bytes arriving on
that connection get piped to a fresh connection to the local service
on :8080.

This plays the same role `hass-nabucasa` plays on a Raspberry Pi:
a tunnel client that forwards traffic to a local web server.

Toy simplification: one HTTP request-response per tunnel session.
After a request finishes, we dial the relay again and wait for the
next one. The real SniTun protocol multiplexes many requests over a
single long-lived tunnel — see the README for notes on how that works.

Run it with:
    python tunnel_client.py <relay-host>
"""

import asyncio
import sys

from config import LOCAL_HOST, LOCAL_PORT, TUNNEL_PORT as RELAY_PORT


async def pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
    """Copy bytes from src to dst until src closes.

    On EOF, signal end-of-stream to dst so the reverse pipe can finish.
    Without this, a half-closed HTTP response leaves the other direction
    blocked forever.
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


async def one_session(relay_host: str) -> None:
    """Open one tunnel session, bridge one request, then return."""
    print(f"[client] connecting to relay at {relay_host}:{RELAY_PORT}...")
    tunnel_reader, tunnel_writer = await asyncio.open_connection(
        relay_host, RELAY_PORT
    )
    print("[client] tunnel open — waiting for traffic")

    print(f"[client] opening local connection to {LOCAL_HOST}:{LOCAL_PORT}")
    local_reader, local_writer = await asyncio.open_connection(
        LOCAL_HOST, LOCAL_PORT
    )

    await asyncio.gather(
        pipe(tunnel_reader, local_writer),
        pipe(local_reader, tunnel_writer),
        return_exceptions=True,
    )

    for w in (tunnel_writer, local_writer):
        try:
            w.close()
            await w.wait_closed()
        except Exception:
            pass


async def main(relay_host: str) -> None:
    while True:
        try:
            await one_session(relay_host)
        except Exception as err:
            print(f"[client] session error: {err}")
        print("[client] session ended — reconnecting in 1s")
        await asyncio.sleep(1)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python tunnel_client.py <relay-host>")
        sys.exit(1)
    try:
        asyncio.run(main(sys.argv[1]))
    except KeyboardInterrupt:
        print("\n[client] bye")
