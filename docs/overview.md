# How the Reverse Tunnel Works

## The Core Problem

Your laptop is behind a home router doing NAT (Network Address Translation).
NAT means the router has one public IP, many devices share it, and the router
only forwards *replies* to outbound connections — it drops unsolicited inbound
packets. Nothing on the internet can knock on your laptop's door directly.

## The Insight

**TCP connections are bidirectional once open.** NAT only blocks the initial
handshake of an inbound connection. If your laptop dials out first, the
resulting socket carries data in both directions for its lifetime.

So instead of waiting for the internet to reach us, we flip the model:

1. The laptop opens an outbound TCP connection to a VPS (which has a real public IP).
2. We hold that connection open as a "tunnel."
3. When a browser hits the VPS, the VPS feeds the request *down* the already-open
   tunnel to the laptop, and reads the response back up the same socket.

The browser never knows it's talking to a laptop. The router never blocks anything,
because from its perspective the laptop just made an outbound connection long ago.

## Traffic Flow

```
[Browser]
    │  HTTP request
    ▼
[VPS :80]  ←── public internet
    │  dequeue one waiting tunnel connection
    ▼
[VPS :9000] ←── outbound dial made by laptop (passes through NAT freely)
    │  bytes forwarded down the tunnel socket
    ▼
[Laptop tunnel_client.py]
    │  pipes bytes to local service
    ▼
[localhost:8080  my_service.py]
    │  HTTP response travels the same path in reverse
    ▼
[Browser receives response]
```

## The Three Files

| File | Runs on | Role |
|---|---|---|
| `my_service.py` | Laptop | The local web server being exposed |
| `relay_server.py` | VPS | Bridges public traffic to tunnel connections |
| `tunnel_client.py` | Laptop | Dials relay, bridges tunnel to local service |
| `config.py` | Both | Shared port/host constants |

## Toy Simplification vs. Real Systems

This demo handles **one HTTP request per tunnel session**, then reconnects.
Real tunnels (ngrok, Cloudflare Tunnel, Home Assistant Nabu Casa / SniTun) add:

- **Multiplexing** — many concurrent requests over one long-lived connection,
  each tagged with a channel ID (like HTTP/2 streams).
- **Hostname routing** — one relay serving many tunnels, picking the right one
  from the TLS SNI field or `Host:` header.
- **Authentication** — signed tokens so only authorised clients can open a tunnel.
- **End-to-end TLS** — TLS terminated on the laptop; the relay forwards ciphertext
  it cannot read.
- **Exponential backoff** — smarter reconnection than "sleep 1 second."
