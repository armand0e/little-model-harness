---
name: system-design-basics
description: Use for designing or discussing systems and architecture - scaling, caching, databases, queues, reliability, "how would you build X for N users" - and for any tradeoff-driven design conversation. Provides the vocabulary, the standard building blocks, and the numbers.
---

# System Design Basics

Every architecture answer is a tradeoff, not a component list. Clarify requirements, establish scale, start with the simplest design that meets them, then address measured bottlenecks and non-negotiable security, privacy, durability, and compliance risks.

## Reliable workflow

1. Define users, core operations, data sensitivity, latency/availability/durability targets, consistency needs, regions, retention, and cost constraints. Rank them; they cannot all be maximized.
2. Estimate average and peak read/write rates, payload sizes, storage growth, fan-out, and hot-key risk. Show assumptions and ranges.
3. Define the data model, ownership, access patterns, invariants, and idempotency boundaries before drawing services.
4. Start with the smallest end-to-end design. Walk read, write, retry, duplicate, partial failure, recovery, and deploy paths through it.
5. Identify the first measured or estimated bottleneck. Add one component only when it addresses that bottleneck and state the new failure mode it introduces.
6. Cover security, authorization, privacy, observability, backpressure, backups, restore testing, and capacity alarms.
7. Summarize tradeoffs, scaling trigger, and what remains intentionally simple.

Return assumptions and back-of-the-envelope math with the diagram. A component list without request flows and failure behavior is not a design.

## Requirements first

- Functional: what must it do? Non-functional: how fast (latency), how much (throughput), how reliable (availability), how consistent, how big (storage growth)?
- Scale estimate before designing (see fermi-estimation): users → requests/sec (daily actives × actions/day ÷ 86,400, ×5–10 for peak), storage/year, read:write ratio. Designs for 100 req/s and 100k req/s are different animals; most systems are the small animal — a single Postgres box and one app server handle a startling amount of traffic. **Do not design for imaginary scale.**

## Numbers every designer knows (orders of magnitude)

Use only order-of-magnitude anchors: memory access is typically nanoseconds, local SSD access microseconds to low milliseconds, same-datacenter calls often sub-millisecond to a few milliseconds, and cross-continent calls tens to hundreds of milliseconds. Real database, cache, and server throughput varies by query shape, durability, hardware, connection model, and tail-latency target; benchmark the actual workload instead of quoting a universal requests-per-second number.

## The standard building blocks (and when each earns its place)

- **Load balancer**: >1 app server, or zero-downtime deploys. Round-robin is fine to start.
- **Cache** (Redis/memcached/CDN): read-heavy, tolerates slight staleness. Cache-aside is the default pattern. The two hard problems: invalidation (prefer TTLs + explicit invalidation on write) and stampede (lock or jittered TTLs). Never cache what you can't afford to serve stale for one TTL.
- **Relational DB** (default choice): transactions, joins, ad-hoc queries, correctness. Scale reads with replicas (accepting replication lag), writes with... first, better queries and indexes — an index turns O(n) scans into O(log n); missing indexes cause 90% of "we need to scale the DB" conversations.
- **NoSQL/KV/document**: chosen for a specific access pattern at large scale (key lookups, huge write volume), not for fashion. You trade joins/transactions for horizontal scale.
- **Queue** (SQS/Kafka/RabbitMQ): decouples producer from consumer speed; makes work async (email, thumbnails, webhooks); absorbs spikes. Consequence: eventual completion, retries, poison-message handling, and **idempotent consumers** because a message can be delivered or processed more than once.
- **Sharding**: last resort for write scale; pick the partition key by the dominant query (queries crossing shards become expensive), beware hot keys (celebrity problem).

## Reliability vocabulary

- Availability: 99.9% = ~8.8 h down/yr; 99.99% = ~53 min. Each nine multiplies cost.
- No single point of failure = every tier has ≥2 nodes and the failure of any one is survivable. Test by asking "what dies if THIS box dies?" for every box.
- Timeouts on every network call; retries with exponential backoff + jitter; circuit breakers so a dead dependency fails fast instead of exhausting your threads. Graceful degradation: core path works even when the recommendation service is down.
- **CAP in practice**: during a partition, a distributed operation cannot guarantee both linearizable consistency and a successful response from every partition. Make the choice per operation and invariant; real financial and social systems mix strategies. State exactly which data may be stale, rejected, or reconciled and for how long.

## Design-discussion etiquette

State the simplest viable design first, name its breaking point ("this holds to ~5k req/s; past that, the DB write path saturates"), then show the next increment. Reciting microservices/Kafka/Kubernetes for a 100-user app signals inexperience, not sophistication. Monolith-first is the professional default; split a service out when a specific team/scaling pain demands it.
