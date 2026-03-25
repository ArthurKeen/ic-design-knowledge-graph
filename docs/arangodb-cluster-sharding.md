# ArangoDB cluster sharding: OneShard vs SmartGraph (IC Knowledge Graph)

## What you are seeing

In a **cluster**, each collection is sharded. With `numberOfShards: 1`, every collection still has
**one leader shard**, but **nothing forces those leaders onto the same DB-Server**. The scheduler
places shard leaders across `DBServer0001`, `DBServer0002`, `DBServer0003`, etc.

That is **not** “multi-shard hot spots” — it is **cross-server locality loss**: a single graph
query touches many collections, so coordinators fan out to many DB-Servers and pay network +
merge cost on **every** hop-heavy AQL or traversal.

So the deployment is neither:

- **OneShard** — whole database co-located on one DB-Server leader (plus optional followers), or  
- **SmartGraph** — edges/vertices co-located by a **shard key** so traversals stay local when possible.

It is the intermediate case: one shard per collection, but **leaders splayed**.

---

## Choose a strategy

### Option A — **OneShard database** (usually the right default for this project)

**When**: The full database fits comfortably in **one DB-Server’s** RAM/disk (or you accept one
primary data node for the graph workload).

**Effect**: For a database created with `sharding: "single"`, all collections’ shards are
**placed on the same DB-Server** (replication can still put followers on other DB-Servers for HA).

**Pros**:

- Best fit for **large traversals, joins, graph analytics** on one connected knowledge graph.
- Minimizes cluster-internal chatter for typical IC graph queries (`GRAPH`, multi-collection `FOR`,
  `RESOLVED_TO`, cross-repo edges, etc.).

**Cons**:

- No horizontal **data** scale-out for that database; you scale the DB-Server vertically or add
  replicas for read/HA, not striping.

**Official docs**: [OneShard cluster deployments](https://docs.arangodb.com/stable/deploy/oneshard/)

---

### Option B — **SmartGraph** (or **Disjoint SmartGraph**)

**When**: The dataset is too large for one machine **and** you can define a **stable smart graph
attribute** (shard key) such that most graph traffic stays inside one partition.

**Typical key**: `repo` (or `tenant`, `subsystem`) **if** it is present on **every** vertex document
you need in the graph, and edge definitions are compatible with SmartGraph rules.

**Caveat for this graph**: You have **many cross-repo edges** (`CROSS_REPO_SIMILAR_TO`,
`CROSS_REPO_EVOLVED_FROM`, etc.). Those edges connect documents with **different** shard-key
values, so they are inherently **non-local** unless modeled with Enterprise-specific patterns.
SmartGraph still helps for **within-repo** traversals (RTL, GraphRAG per repo) but **does not**
magically co-locate the whole global graph.

**Disjoint SmartGraph**: Use when you have **several named graphs** that do **not** share vertices
between definitions — not the typical shape of `IC_Temporal_Knowledge_Graph` (one big connected
semantic layer).

**Official docs**:

- [SmartGraphs](https://docs.arangodb.com/stable/graphs/smart-graphs/)
- [Disjoint SmartGraphs](https://docs.arangodb.com/stable/graphs/smart-graphs/Disjoint-SmartGraphs/)

---

## Recommendation for `ic-knowledge-graph-temporal`

1. **Prefer OneShard** for the main workload database if size allows — it matches “one temporal
   knowledge graph, many hops, many collections”.
2. Consider **SmartGraph** only after a sizing exercise and a clear partition story (e.g. heavy
   per-repo isolation with cross-repo edges accepted as expensive).
3. Treat **replicationFactor > 1** separately: followers on other DB-Servers are good for **HA**;
   they do not fix locality for leaders unless you use OneShard/SmartGraph correctly.

> **Licensing**: OneShard and SmartGraph are **ArangoDB Enterprise** capabilities on cluster
> deployments. Confirm your contract matches the chosen option.

---

## Creating a OneShard database (this repo)

**python-arango** (used everywhere in this project):

```python
sys_db.create_database(
    "ic-knowledge-graph-temporal",
    sharding="single",                    # OneShard
    replication_factor=2,               # optional — cluster HA only
    write_concern=2,                    # optional — must be ≤ replication_factor
)
```

Wrappers in `src/db_utils.py`:

| Function | Purpose |
|----------|---------|
| `create_oneshard_database(name, …)` | Strict OneShard create; uses `ARANGO_REPLICATION_FACTOR` / `ARANGO_WRITE_CONCERN` from `.env` when args omitted |
| `create_oneshard_database_or_fallback(name)` | Tries OneShard; on `DatabaseCreateError` falls back to plain `create_database` (e.g. some single-server builds) |

**CLI** (loads `.env` via `config`):

```bash
PYTHONPATH=src python3 scripts/setup/create_oneshard_database.py --name ic-knowledge-graph-temporal
```

Optional **HA on cluster** — set in `.env` (see `env.template`):

```env
ARANGO_REPLICATION_FACTOR=2
ARANGO_WRITE_CONCERN=2
```

**HTTP** (equivalent to the Python call): `POST /_api/database` with body:

```json
{
  "name": "ic-knowledge-graph-temporal",
  "options": { "sharding": "single" }
}
```

(Callers also pass `replicationFactor` / `writeConcern` at database level when using HA — match your ArangoDB version’s API.)

Call sites updated to prefer OneShard:

- `scripts/customer_workflow.py` — `_create_db_if_missing` uses `create_oneshard_database_or_fallback`
- `tests/conftest.py` — test DB created with `sharding="single"` when supported

---

## Migration: dump → drop → OneShard → restore

You **cannot** flip an existing database to OneShard in place. For a **demo** cluster, the usual
path is:

1. **Backup** with `arangodump` (keep the output directory until you have verified restore).
2. **Drop** the database (`arangosh` / Web UI / API).
3. **Create** an empty database with **OneShard** (`create_oneshard_database.py` or Python API above).
4. **Restore** with `arangorestore` into that database (`--create-database false` — the DB already exists).
5. **Validate** in the Web UI → **Shards**: collection leaders for this database should sit on **one**
   DB-Server (replicas may still show on other servers if `replicationFactor > 1`).

**Automated script** (sources `.env`, uses the same credentials as Python tools):

```bash
chmod +x scripts/setup/migrate_to_oneshard.sh
./scripts/setup/migrate_to_oneshard.sh
```

Set `ARANGO_DATABASE` (and `ARANGO_MODE` / endpoints) in `.env` first. The script writes dumps to
`./arangodump_${ARANGO_DATABASE}_oneshard_backup` unless you set `DUMP_DIR`.

**Checklist**

- [ ] ArangoDB client tools version **matches** server major version (`arangodump` / `arangorestore`).
- [ ] **Enterprise** license if you rely on OneShard on a cluster.
- [ ] After restore, re-check **named graphs** (`IC_Temporal_Knowledge_Graph`) and **indexes** if anything was created out-of-band.
- [ ] Update `.env` / MCP `ARANGO_DATABASE` if the database name changed.

### Docker single-server vs Enterprise cluster (why “Shards” looks different)

A **single `arangodb` Docker container** is **not** a multi-DB-Server cluster. There is **no**
`DBServer0001` / `DBServer0002` placement to inspect — the **Web UI “Shards” tab that lists
leaders per DB-Server only applies to a cluster**.

What you **can** verify on Docker:

1. **`arangodump` → drop → `create_oneshard_database.py` → `arangorestore`** completes and data
   reappears (smoke test: document counts / spot-check documents).
2. **`create_oneshard_database.py`** runs without error (`sharding="single"` is accepted for the
   new empty database).

What you **must** verify on your **Enterprise cluster** (where the problem was reported):

1. After restore, open **Shards** for the database: **all collection leaders** for that database
   should sit on **one** DB-Server (followers may still be on others if `replicationFactor > 1`).

**Alternative (cluster-wide policy):** `--cluster.force-one-shard` forces OneShard for **new**
databases only — use only if appropriate for all databases on that cluster.

---

## Operational checks

| Question | OneShard | SmartGraph |
|----------|----------|------------|
| Graph traversals mostly local? | Yes (same leader) | Only within same shard key |
| Cross-repo edges cheap? | Same as single-server path | Still cross-shard |
| HA via replicas? | Yes | Yes |
| Needs schema / key design? | Minimal | Yes — smart attribute on vertices/edges |

---

## References in this repo

- Connection and database name: `env.template`, `src/config.py`, `CURSOR_HANDOFF.md`
- OneShard helpers: `src/db_utils.py`, `scripts/setup/create_oneshard_database.py`, `scripts/setup/migrate_to_oneshard.sh`
- Named graph: `IC_Temporal_Knowledge_Graph` (see temporal / setup scripts under `scripts/temporal/`)

If you adopt OneShard or SmartGraph, add the **exact** `arangosh` / HTTP snippet you used and the
**ArangoDB version** to this file so future restores stay reproducible.
