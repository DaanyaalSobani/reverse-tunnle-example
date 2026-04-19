# reverse-tunnel-demo

A minimal, educational reverse tunnel in ~200 lines of Python. Demonstrates
how tools like Home Assistant's Nabu Casa, Cloudflare Tunnel, ngrok, and
Tailscale Funnel expose a service behind NAT to the public internet without
port forwarding.

## The idea

Your laptop is behind a home router (NAT). Nothing on the internet can
reach it directly. But your laptop can make outbound connections freely.
So we set up a VPS with a public IP, have the laptop dial out to the VPS
and hold that connection open, and then route public traffic down the
already-open tunnel.

```
   [Browser] ──HTTP──▶ [VPS :80]                         [Laptop]
                          │                                  ▲
                          │  bytes travel down an            │
                          │  already-open TCP connection     │
                          ▼                                  │
                     [VPS :9000] ◀──── outbound dial ────────┘
                                       (made by laptop)
                                                             │
                                                             ▼
                                                    [localhost:8080]
                                                     (my_service.py)
```

## The three files

| File | Runs on | Role |
|------|---------|------|
| `my_service.py` | Laptop | The web server we want to expose (listens on `127.0.0.1:8080`). |
| `relay_server.py` | VPS | Accepts tunnel dial-ins on `:9000` and public traffic on `:80`, shuttles bytes between them. |
| `tunnel_client.py` | Laptop | Dials the relay, then bridges the tunnel to the local service. |

## Running it

You need a VPS with a public IP. A $4/month DigitalOcean droplet is plenty.

**1. On your VPS**, clone this repo and start the relay:

```bash
git clone https://github.com/DaanyaalSobani/reverse-tunnle-example.git
cd reverse-tunnel-demo
sudo python3 relay_server.py
```

(Sudo is required because port 80 is privileged. Also make sure your
VPS firewall allows inbound on ports 80 and 9000.)

**2. On your laptop**, start the local service:

```bash
python3 my_service.py
```

**3. On your laptop** (new terminal), start the tunnel client:

```bash
python3 tunnel_client.py <your-vps-ip>
```

**4. From anywhere** (your phone on cellular, a friend's computer):

```bash
curl http://<your-vps-ip>/
```

You should see `Hello from my laptop!` — served by your laptop, even
though no port on your home network was ever opened inbound.

## What's deliberately missing

This is a teaching toy, not a production tunnel. Real systems like SniTun
(Home Assistant's tunnel) add:

- **Multiplexing** — many concurrent public requests over one long-lived
  tunnel, each tagged with a channel ID. This toy handles one request per
  tunnel session and reconnects between requests. It works but is inefficient
  and serializes traffic.
- **Hostname routing** — one relay serving many different tunnels, picking
  the right one based on the `Host:` header or TLS SNI field.
- **Authentication** — right now anyone who knows the relay's IP can open
  a tunnel and start intercepting traffic. Real systems use signed tokens.
- **End-to-end TLS** — your traffic is currently plaintext. Real systems
  terminate TLS on the laptop and pass encrypted bytes through the relay
  untouched, so the relay can't read your data.
- **Smarter reconnection** — production clients use exponential backoff and
  health checks. This one just retries every second.

Each of these is a well-scoped extension if you want to keep learning.

## Why this works

TCP connections are bidirectional once established. NAT only blocks
*unsolicited inbound* connections — once your laptop has opened an
outbound TCP connection to the VPS, data can flow in either direction
over that same connection. We exploit this by having the laptop dial
out once and then treating the resulting socket as a backchannel for
inbound traffic.

## License

MIT.
