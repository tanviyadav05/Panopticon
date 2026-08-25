# infra/

Every cross-laptop call in this repo today is plain HTTP/JSON (see
`docs/api_documentation.md`) — no message broker, no RPC framework. That's
a deliberate choice for a 5-node lab: HTTP is debuggable with `curl`, and
nothing here is latency-sensitive enough to need anything fancier.

This directory is reserved for the day that stops being true — e.g. if you
add more Red/Blue replicas and want pub/sub fan-out instead of point-to-
point calls, or want Observer's publisher to survive the Referee being down
longer than its in-memory retry queue can buffer (see
`observer/pipeline/publisher.py`).

If/when you do that, a message broker like NATS or Redis Streams is the
natural fit — both are a single static binary or container, which matches
this project's "five plain laptops" deployment model better than something
like Kafka would. `example.nats-server.conf` below is a starting point, not
something anything currently reads.
