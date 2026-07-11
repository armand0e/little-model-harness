---
name: system-design-basics
description: Use for designing or discussing systems and architecture - scaling, caching, databases, queues, reliability, "how would you build X for N users" - and for any tradeoff-driven design conversation. Provides the vocabulary, the standard building blocks, and the numbers.
category: software
hint: scalability, caching, queues, tradeoffs
---
# System Design Basics

Every architecture answer is a TRADEOFF, not a component list. The method: clarify requirements → establish scale numbers → start with the simplest thing that meets them → identify the bottleneck → address ONLY that → repeat.

## Requirements first

- Functional: what must it do? Non-functional: how fast (latency), how much (throughput), how reliable (availability), how consistent, how big (storage growth)?
- Scale estimate before designing (see fermi-estimation): users → requests/sec (daily actives × actions/day ÷ 86,400, ×5–10 for peak), storage/year, read:write ratio. Designs for 100 req/s and 100k req/s are different animals; most systems are the small animal — a single Postgres box and one app server handle a startling amount of traffic. **Do not design for imaginary scale.**

## Numbers every designer knows (orders of magnitude)

Memory reference ~100 ns; SSD random read ~100 µs; disk seek ~10 ms; same-datacenter round trip ~0.5 ms; cross-continent RTT ~70–150 ms. Read 1 GB sequentially: memory ~10 ms, SSD ~1 s. A modern server: hundreds of GB RAM, ~10⁴–10⁵ simple queries/s from one Postgres, ~10⁵+ req/s from one cache node. Rule: memory is 1000× disk; same-DC network is fast; cross-region network is slow and failure-prone.

## The standard building blocks (and when each earns its place)

- **Load balancer**: >1 app server, or zero-downtime deploys. Round-robin is fine to start.
- **Cache** (Redis/memcached/CDN): read-heavy, tolerates slight staleness. Cache-aside is the default pattern. The two hard problems: invalidation (prefer TTLs + explicit invalidation on write) and stampede (lock or jittered TTLs). Never cache what you can't afford to serve stale for one TTL.
- **Relational DB** (default choice): transactions, joins, ad-hoc queries, correctness. Scale reads with replicas (accepting replication lag), writes with... first, better queries and indexes — an index turns O(n) scans into O(log n); missing indexes cause 90% of "we need to scale the DB" conversations.
- **NoSQL/KV/document**: chosen for a specific access pattern at large scale (key lookups, huge write volume), not for fashion. You trade joins/transactions for horizontal scale.
- **Queue** (SQS/Kafka/RabbitMQ): decouples producer from consumer speed; makes work async (email, thumbnails, webhooks); absorbs spikes. Consequence: eventual completion, need for retries + **idempotent consumers** (messages WILL be delivered twice) + a dead-letter queue.
- **Sharding**: last resort for write scale; pick the partition key by the dominant query (queries crossing shards become expensive), beware hot keys (celebrity problem).

## Reliability vocabulary

- Availability: 99.9% = ~8.8 h down/yr; 99.99% = ~53 min. Each nine multiplies cost.
- No single point of failure = every tier has ≥2 nodes and the failure of any one is survivable. Test by asking "what dies if THIS box dies?" for every box.
- Timeouts on every network call; retries with exponential backoff + jitter; circuit breakers so a dead dependency fails fast instead of exhausting your threads. Graceful degradation: core path works even when the recommendation service is down.
- **CAP in practice**: during a network partition, choose consistency (refuse some requests) or availability (serve possibly-stale data). Banks pick C; social feeds pick A. Most apps: strong consistency within one Postgres, eventual consistency across caches/replicas — know which data can be stale and for how long.

## Design-discussion etiquette

State the simplest viable design first, name its breaking point ("this holds to ~5k req/s; past that, the DB write path saturates"), then show the next increment. Reciting microservices/Kafka/Kubernetes for a 100-user app signals inexperience, not sophistication. Monolith-first is the professional default; split a service out when a specific team/scaling pain demands it.
