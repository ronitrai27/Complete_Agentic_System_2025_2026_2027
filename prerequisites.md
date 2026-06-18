# Twin AI — Production Prerequisites and Build Roadmap

## Product vision

Twin AI is a continuously learning personal agent that:

- Understands what a user did today, yesterday, and weeks ago
- Learns the user's projects, people, priorities, routines, preferences, and communication style
- Connects browser activity, email, calendar, Slack, Discord, Spotify, documents, and other sources
- Produces morning briefings and daily reflections
- Suggests automations and can execute approved automations on schedule
- Maintains an inspectable personal knowledge graph
- Builds and updates a user-specific `user_skill.md`
- Speaks naturally in the user's preferred tone without pretending to literally be the user

The target experience after one month is:

> "It remembers my work, understands how my priorities changed, knows what I did last week, communicates naturally, and safely completes recurring work without needing my browser open."

This is achievable, but it is primarily a data, memory, security, and evaluation problem—not just a chatbot prompt problem.

---

# 1. Non-negotiable architecture principle

Do not write every captured activity directly into the knowledge graph.

Use five distinct layers:

```text
External sources
    ↓
1. Immutable event ledger
    ↓
2. Normalized episodes
    ↓
3. Memory extraction and consolidation
    ├── Semantic memories
    ├── Temporal knowledge graph
    ├── Preference/style profile
    └── Procedural memories
    ↓
4. Hybrid retrieval and context assembly
    ↓
5. Agent reasoning and safe automation
```

Each layer must be independently inspectable and rebuildable.

The knowledge graph is a derived projection. The immutable event ledger is the source of truth.

---

# 2. Memory model

## 2.1 Working memory

Short-lived information needed for the current task:

- Current conversation
- Current browser tab or selected document
- Active automation run
- Recent tool results

Store in Redis or the workflow state store.

Typical lifetime: minutes to hours.

Do not permanently save every working-memory item.

## 2.2 Episodic memory

Time-bound events the user experienced or performed:

- "Ronit discussed the WeKraft release with Akash at 3:00 PM."
- "The user listened to a focus playlist while editing the PRD."
- "The user approved the Q3 proposal."
- "The user visited the deployment dashboard after receiving an alert."

Every episode should contain:

```yaml
episode_id:
user_id:
source:
source_event_id:
event_type:
occurred_at:
ingested_at:
content_reference:
participants:
objects:
privacy_class:
checksum:
```

Episodes should remain attached to their original evidence.

## 2.3 Semantic memory

Stable or reusable facts:

- The user works on Project WeKraft.
- Akash is a frequent collaborator.
- The user prefers concise technical explanations.
- Project Atlas depends on AWS.

Each fact needs:

```yaml
memory_id:
subject_id:
predicate:
object_id_or_value:
confidence:
valid_from:
valid_to:
observed_at:
source_episode_ids:
status: active | superseded | disputed | deleted
```

Never store an inferred fact without provenance and confidence.

## 2.4 Temporal knowledge graph

The graph models entities, relationships, and how they change.

Example:

```text
(User)-[:WORKS_ON {
  valid_from,
  valid_to,
  confidence,
  source_episode_ids
}]->(Project)
```

You need two kinds of time:

- Valid time: when the fact was true in the user's world
- Transaction time: when Twin AI learned or changed the fact

This enables questions such as:

- What was the user working on one month ago?
- Who became important this week?
- When did Project WeKraft become the main priority?
- What did the system believe yesterday before a correction arrived?

Graphiti is worth evaluating because it is designed for continuously changing, bi-temporal context graphs, episodic ingestion, fact invalidation, and hybrid retrieval. Alternatively, implement the same principles directly in Neo4j.

## 2.5 Procedural memory

How the user prefers tasks to be completed:

- Preferred meeting-summary format
- How invoices are filed
- Which Slack channel receives deployments
- How a weekly report is prepared
- Which steps require approval

Procedural memory must be versioned.

It should not automatically become executable automation. A procedure becomes executable only after validation and permission.

## 2.6 Style and preference memory

Keep style separate from factual memory.

Example dimensions:

```yaml
verbosity: 0.35
directness: 0.85
formality: 0.30
humor: 0.45
emoji_frequency: 0.10
preferred_structure: short_paragraphs
technical_depth: high
challenge_level: direct
disliked_phrases:
  - "As an AI language model"
  - "I hope this finds you well"
```

Learn style from repeated evidence, not one message.

The agent may match energy, vocabulary, rhythm, and directness. It should not imitate harassment, threats, manipulation, or unsafe conduct merely because the user used that tone.

---

# 3. Knowledge graph design for continuously updating users

## 3.1 Recommended core nodes

```text
User
Person
Organization
Project
Task
Goal
Decision
Meeting
Message
Document
EmailThread
Channel
Application
Website
Topic
Preference
Routine
Automation
Episode
SourceAccount
```

## 3.2 Recommended relationships

```text
WORKS_ON
OWNS
COLLABORATES_WITH
REPORTS_TO
MENTIONS
DISCUSSED_IN
PARTICIPATED_IN
CREATED
EDITED
VIEWED
DECIDED
BLOCKED_BY
DEPENDS_ON
RELATED_TO
PREFERS
DISLIKES
REPEATS
TRIGGERED
SUPPORTED_BY
DERIVED_FROM
SUPERSEDES
CONTRADICTS
```

Keep relationship vocabulary controlled. Do not create thousands of near-synonyms such as:

```text
WORKS_WITH
WORKED_WITH
COLLABORATES
COLLABORATED
TEAMED_WITH
```

Map these to a canonical relationship such as `COLLABORATES_WITH`.

## 3.3 Stable entity identity

Never merge entities using display name alone.

Use:

```yaml
entity_id: tenant-scoped UUID
canonical_name:
normalized_name:
entity_type:
external_ids:
  gmail_address:
  slack_user_id:
  discord_user_id:
  microsoft_user_id:
aliases:
```

Entity resolution should combine:

- Exact external IDs
- Email addresses
- Source-account identity
- Normalized names
- Embedding similarity
- Shared organization/project context
- User confirmation for uncertain merges

Provide an interface to merge and split entities.

## 3.4 Provenance

Every durable node property and relationship must answer:

> Why does Twin AI believe this?

Store:

- Source connector
- Source account
- Source object ID
- Episode ID
- Extractor version
- Model version
- Extraction timestamp
- Confidence
- Supporting text span or structured fields

Without provenance, corrections and deletion become unreliable.

## 3.5 Contradictions and changing facts

Do not overwrite facts in place.

Example:

```text
Old:
User WORKS_ON Project Atlas
valid_to = 2026-07-01
status = superseded

New:
User WORKS_ON Project WeKraft
valid_from = 2026-07-01
status = active
```

Rules:

- Preserve historical versions
- Mark old edges inactive
- Record which episode caused the change
- Prefer recent direct evidence over old inferred evidence
- Ask the user when two high-confidence sources conflict

## 3.6 Graph indexes and constraints

At minimum:

```cypher
CREATE CONSTRAINT entity_id_unique IF NOT EXISTS
FOR (e:Entity) REQUIRE e.entity_id IS UNIQUE;

CREATE INDEX entity_tenant_name IF NOT EXISTS
FOR (e:Entity) ON (e.tenant_id, e.normalized_name);

CREATE INDEX episode_source_id IF NOT EXISTS
FOR (e:Episode) ON (e.tenant_id, e.source, e.source_event_id);
```

Also consider:

- Full-text indexes for names, aliases, titles, and message summaries
- Vector indexes for entity descriptions and memory text
- Range indexes for timestamps and confidence
- Relationship indexes for frequently filtered temporal properties

Neo4j supports range, text, full-text, token lookup, and vector indexes. Design indexes from actual query plans, not intuition alone.

## 3.7 Graph write rules

Every write must be:

- Tenant-scoped
- Idempotent
- Transactional
- Provenance-aware
- Retriable
- Versioned

Use deterministic event keys:

```text
connector + source_account_id + source_event_id + revision
```

Do not deduplicate unrelated events merely because their text is identical.

---

# 4. Should you use Mem0?

## Good uses for Mem0

Mem0 can accelerate:

- User-scoped semantic memories
- Memory add/search/update/delete APIs
- Filtering by user, agent, app, or run
- Entity-oriented recall
- Prototype memory evaluation

Its current Graph Memory automatically links memories through extracted entities and combines entity connections with vector and keyword ranking.

## Important limitation

Mem0's native graph connections are primarily entity-to-memory/co-occurrence links. Its documentation explicitly distinguishes that from typed relationships such as `MANAGES` between two people.

Your Twin AI needs:

- Typed relationships
- Temporal edge lifecycles
- Provenance
- Contradiction handling
- Point-in-time queries
- Automation and permission state

Therefore:

```text
Mem0 = optional semantic-memory service
Neo4j/Graphiti = temporal personal context graph
Event store = immutable truth
```

Do not make Mem0 the only memory database.

Recommended evaluation:

1. Implement a memory-service interface.
2. Build one adapter for your own vector/SQL storage.
3. Build one Mem0 adapter.
4. Run the same LongMemEval-style test suite against both.
5. Choose based on accuracy, deletion behavior, latency, cost, and control.

---

# 5. Connector ingestion architecture

## 5.1 Connector service

Create one connector adapter per source:

```python
class Connector:
    authorize()
    initial_sync()
    incremental_sync(cursor)
    handle_webhook(event)
    normalize(raw_event)
    revoke()
    delete_user_data()
```

Every connector writes normalized events into the event ledger. Connector code should never write directly to the final knowledge graph.

## 5.2 Prefer push plus reconciliation

Use:

```text
Webhook/change notification
    ↓
Fast event ingestion

Scheduled incremental reconciliation
    ↓
Recover missed or delayed events
```

Examples:

- Slack Events API pushes subscribed events and retries failed deliveries.
- Microsoft Graph change notifications can trigger synchronization; delta queries retrieve only changes since the previous state token.
- Gmail should use push notifications plus history-based synchronization where available.

Store connector cursors/delta tokens securely. Handle:

- Token expiration
- Replay
- Pagination
- Deletions
- Out-of-order delivery
- Full-resync fallback
- Rate limiting

## 5.3 Browser extension

Do not begin by recording "all browser activity."

Start with explicit, useful signals:

- Active tab URL and title after a dwell threshold
- User-approved page capture
- Search queries with domain allow/deny controls
- Bookmarks or "remember this" actions
- Tab groups and task sessions
- Optional local page summarization

Never capture by default:

- Password fields
- Payment pages
- Authentication codes
- Health portals
- Private/incognito browsing
- Raw keystrokes
- Form contents
- Clipboard contents
- Full page bodies from every site

Chrome recommends optional permissions when possible so users retain informed runtime control. Request host access only when a feature needs it.

Browser event example:

```yaml
source: chrome_extension
event_type: page_session
url_origin: github.com
page_title: "AI Flow pull request"
started_at:
ended_at:
dwell_seconds:
task_context:
content_summary:
capture_level: metadata | summary | explicit_full_capture
```

Perform sensitive-data classification and redaction locally before upload when feasible.

## 5.4 Connector priority

Build in this order:

1. Calendar
2. Gmail or Outlook
3. Slack
4. Browser extension with explicit capture
5. Documents and cloud drives
6. Task managers
7. Spotify
8. Discord and other social/community sources

Calendar, email, and work chat provide much more useful action context than passive browsing history.

---

# 6. Background jobs and scheduling

Use different systems for different jobs.

## Airflow

Use Airflow for data pipelines:

- Initial connector backfills
- Hourly incremental synchronization
- Nightly memory consolidation
- Daily briefing preparation
- Daily reflection generation
- Weekly entity resolution
- Graph quality checks
- Re-embedding after model changes
- Retention and deletion jobs
- Reprocessing failed episodes

Example DAG:

```text
sync_connectors
    ↓
normalize_events
    ↓
deduplicate
    ↓
extract_episodes
    ↓
extract_entities_and_facts
    ↓
resolve_entities
    ↓
update_temporal_graph
    ↓
update_vector_memory
    ↓
quality_checks
```

Airflow tasks should be idempotent and should communicate through durable storage, not local files. Its official best-practice guidance emphasizes deterministic task behavior, partitioned reads/writes, avoiding expensive top-level DAG code, and using external storage for inter-task data.

## Durable automation engine

Do not use Airflow as the only user-automation runtime.

For actions such as:

- Send a scheduled Slack message
- Create a calendar event
- Follow up after an email
- Wait three days, then check for a reply
- Retry a multi-step workflow
- Pause for user approval

Use a durable workflow engine such as Temporal, or a queue-based worker architecture with persistent workflow state.

Recommended split:

```text
Airflow:
data ingestion, consolidation, batch analysis, reports

Temporal/queue workers:
user-facing automations, timers, retries, approvals, long-running actions

Cron/cloud scheduler:
small stateless triggers only
```

The user's browser must not be required. Automations run in your backend using authorized APIs.

---

# 7. Dynamic personality and prompt assembly

Do not maintain one giant static system prompt.

Build the prompt for every request from controlled modules:

```text
1. Product and safety constitution
2. User communication profile
3. Current task mode
4. Relevant stable preferences
5. Recent conversational context
6. Retrieved episodic memories
7. Retrieved semantic/graph facts
8. Tool permissions and automation policy
9. Response contract
```

Example:

```python
prompt = assemble(
    constitution=global_policy,
    style_profile=get_style_profile(user_id),
    task_mode=classify_task(request),
    preferences=retrieve_preferences(request),
    memories=retrieve_hybrid_context(request),
    permissions=get_action_policy(user_id),
)
```

## Prevent robotic responses

Measure and learn:

- Average sentence length
- Directness
- Vocabulary complexity
- Use of fragments
- Humor frequency
- Preferred greetings and sign-offs
- Markdown preferences
- Degree of challenge/disagreement
- Typical emotional intensity

Then generate a compact style card:

```yaml
voice:
  direct: true
  concise: true
  warmth: medium
  humor: dry_and_occasional
  sentence_style: conversational_fragments_allowed
  disagreement: candid_but_constructive
  avoid:
    - corporate filler
    - repeated disclaimers
    - exaggerated praise
```

Do not paste large samples of private messages into every prompt.

Use examples only after:

- Redacting third-party data
- Selecting short representative snippets
- Confirming that they represent stable style
- Separating work style from private/social style

The user should be able to select modes:

- Work
- Personal
- Deep focus
- Coach
- Friend
- Executive assistant

Tone should be contextual, not one global imitation.

---

# 8. `user_skill.md`

Treat `user_skill.md` as a human-readable compiled profile, not the primary database.

Suggested structure:

```markdown
# User Skill

## Identity and roles
## Active projects
## Important people
## Communication preferences
## Decision-making style
## Work routines
## Tools and workflows
## Recurring responsibilities
## Automation preferences
## Approval boundaries
## Current priorities
## Known dislikes
## Confidence and evidence summary
## Last updated
```

Rules:

- Generate it from structured memories
- Version every update
- Keep evidence references internally
- Allow the user to edit, pin, reject, or lock sections
- Never include passwords, tokens, private message bodies, or raw browsing history
- Separate observed behavior from explicit user statements
- Mark uncertain inferences
- Preserve previous versions for rollback

Update flow:

```text
New episodes
    ↓
Candidate profile changes
    ↓
Confidence threshold
    ↓
Conflict check
    ↓
Update structured profile
    ↓
Regenerate user_skill.md diff
    ↓
User can inspect or correct
```

---

# 9. Morning briefing

Do not generate a briefing from a generic prompt over all memory.

Build structured briefing inputs:

```yaml
calendar:
urgent_messages:
open_commitments:
deadlines:
blocked_projects:
people_waiting_on_user:
user_waiting_on_people:
recent_decisions:
automation_results:
unusual_activity:
energy_or_focus_pattern:
```

Briefing sections:

1. What matters today
2. Calendar and preparation
3. Messages requiring action
4. Commitments at risk
5. Suggested automations
6. Optional personal context

Every action item should link back to evidence.

---

# 10. Daily reflection

Generate reflection from episodes and outcomes:

- What the user spent time on
- Progress against goals
- Decisions made
- Commitments created
- Context switching
- Repeated blockers
- People interacted with
- Work that was planned but not completed
- Suggested adjustment for tomorrow

Avoid judging productivity solely from browser duration.

Activity is not equivalent to meaningful work.

---

# 11. Automation safety

Create action-risk levels:

## Level 0 — Read only

- Search memory
- Summarize messages
- Prepare drafts

No confirmation required after source authorization.

## Level 1 — Reversible internal changes

- Create a draft
- Add a personal task
- Apply a private label

May be auto-approved by user policy.

## Level 2 — External communication

- Send email
- Post Slack message
- Invite attendees

Require confirmation by default.

## Level 3 — High impact

- Delete data
- Change permissions
- Spend money
- Publish publicly
- Execute code against production

Require explicit action-time confirmation and stronger controls.

Every automation needs:

```yaml
automation_id:
owner_user_id:
trigger:
conditions:
actions:
required_scopes:
risk_level:
approval_policy:
max_runs:
rate_limit:
budget:
idempotency_key:
timeout:
rollback_strategy:
audit_log:
enabled:
```

Provide:

- Dry-run mode
- Kill switch
- Per-automation pause
- Global automation pause
- Run history
- Reason for every action
- Exact data sent externally
- Replay protection
- Compensation/rollback where possible

---

# 12. Privacy and security prerequisites

This product handles unusually sensitive data.

Security is part of the product, not a later compliance task.

Minimum requirements:

- Explicit per-source consent
- Least-privilege OAuth scopes
- Optional browser host permissions
- Per-user tenant isolation everywhere
- Encryption in transit and at rest
- Separate encryption keys where practical
- Secrets stored in a secret manager
- Token rotation and revocation
- Audit logs
- Data export
- Source-specific deletion
- Complete account deletion
- Retention controls
- Incognito excluded by default
- Domain and app exclusion lists
- Sensitive-field redaction
- Prompt-injection filtering for captured pages/messages
- Third-party data handling policy
- Backup encryption and deletion propagation
- No model training on user data without separate explicit consent

The browser, emails, Slack messages, and documents are untrusted inputs. Text inside them must never be allowed to rewrite system instructions or authorize actions.

Build privacy controls before broad capture.

---

# 13. Retrieval architecture

Use hybrid retrieval:

```text
Query understanding
    ↓
Time filter
    ↓
Source and permission filter
    ↓
Parallel retrieval
    ├── Recent episodes
    ├── Vector semantic memories
    ├── BM25 exact matches
    ├── Temporal graph traversal
    ├── Current tasks/commitments
    └── User profile/preferences
    ↓
Deduplicate and rerank
    ↓
Evidence-backed context packet
```

Rank using:

- Semantic similarity
- Keyword match
- Entity match
- Graph distance
- Recency
- Temporal validity
- Source reliability
- Confidence
- User importance
- Task relevance

Never retrieve memories across users.

---

# 14. Memory consolidation

Run scheduled consolidation:

## Hourly

- Normalize new events
- Extract candidate entities and episodes
- Resolve obvious entities
- Update active tasks and commitments

## Nightly

- Merge duplicate semantic memories
- Detect contradictions
- Expire stale low-confidence facts
- Generate daily summary
- Update relationship strength
- Update style statistics
- Propose `user_skill.md` changes

## Weekly

- Re-run uncertain entity resolution
- Generate project and relationship summaries
- Review memory quality
- Archive low-value episodes according to retention policy
- Recalculate user routines

Do not make consolidation destructive. Keep history and provenance.

---

# 15. Evaluation: how to know it is actually good

There is no permanent "10/10" graph.

Define measurable quality:

## Extraction

- Entity precision and recall
- Relationship precision and recall
- Entity-linking accuracy
- Duplicate rate
- Provenance coverage

## Temporal memory

- Point-in-time answer accuracy
- Contradiction-resolution accuracy
- Stale-fact rate
- Correct deletion propagation

## Retrieval

- Recall@K
- Precision@K
- NDCG
- Multi-hop answer accuracy
- Evidence citation accuracy
- Cross-user leakage rate: must be zero

## Personalization

- User preference acceptance rate
- Style-match human rating
- Correction frequency
- Unwanted imitation rate
- Mode-selection accuracy

## Automation

- Successful-run rate
- Duplicate-action rate
- Incorrect-action rate
- Confirmation rate
- Rollback success
- Mean time to detect failures

Create a golden evaluation set for each test user:

- What was I doing yesterday?
- What changed since last week?
- Who am I waiting on?
- What did I promise Akash?
- What was my priority before WeKraft?
- Draft this in my work tone.
- Which automation should run, and why?

Run evaluations before every extractor, embedding, graph-schema, and prompt change.

---

# 16. Observability

Track:

- Connector lag
- Events ingested per source
- Duplicate/replay counts
- Extraction failures
- Entity merge/split counts
- Graph write latency
- Retrieval latency
- Prompt token usage
- Automation retries
- OAuth failures
- Data deletion status
- Cost per active user

Every response should have an internal trace:

```text
request
→ retrieved memories
→ graph paths
→ prompt modules
→ model version
→ tool calls
→ final action
```

---

# 17. Recommended technology split

One reasonable starting stack:

```text
API: FastAPI
Primary relational store: PostgreSQL
Event ledger: PostgreSQL initially; Kafka/Redpanda later if required
Temporal graph: Neo4j with temporal/provenance schema, or Graphiti
Vector store: pgvector or managed vector database
Keyword search: PostgreSQL full text/OpenSearch
Working state/cache: Redis
Batch pipelines: Airflow
Durable automations: Temporal or persistent queue workers
Object storage: S3-compatible storage
Secrets: cloud secret manager
Observability: OpenTelemetry + metrics/log platform
```

Avoid introducing Kafka, Kubernetes, multiple vector databases, and microservices before load requires them.

Start as a modular monolith with strict service boundaries.

---

# 18. Build phases

## Phase 0 — Product and privacy contract

Focus:

- Define what is captured
- Define what is never captured
- Define user controls
- Define automation risk levels
- Threat model
- Data deletion design

Exit criteria:

- Consent screens designed
- Per-source permissions documented
- User can inspect/export/delete memory

## Phase 1 — Memory foundation

Focus:

- Event ledger
- Episodes
- Provenance
- Temporal graph schema
- Hybrid retrieval
- Evaluation suite

Sources:

- Manual notes
- Uploaded documents
- Chat conversations

Exit criteria:

- Answers "yesterday" and "last week" correctly
- Every fact has evidence
- Corrections update future answers without deleting history

## Phase 2 — Work connectors

Focus:

- Calendar
- Gmail/Outlook
- Slack
- Incremental sync and webhooks

Exit criteria:

- Reliable replay-safe synchronization
- Morning briefing has useful evidence-linked actions

## Phase 3 — Browser context

Focus:

- Explicit capture
- Dwell/session detection
- Domain exclusions
- Local redaction

Exit criteria:

- Browser context improves task recall without collecting secrets or irrelevant page content

## Phase 4 — Personalization

Focus:

- Style profile
- Contextual modes
- `user_skill.md`
- User correction UI

Exit criteria:

- Users consistently prefer Twin AI's tone over a generic baseline
- Style does not leak between work and personal modes

## Phase 5 — Suggested automations

Focus:

- Detect repeated procedures
- Draft automation plans
- Dry runs
- Approval policies

Exit criteria:

- Suggestions are useful
- No duplicate or unauthorized external actions

## Phase 6 — Autonomous scheduled automations

Focus:

- Durable workflow execution
- Policy engine
- Monitoring
- Rollback and kill switches

Exit criteria:

- Safe unattended operation with complete auditability

---

# 19. What to focus on now

Priority order:

1. Replace name-only graph identity with tenant-scoped canonical entity IDs.
2. Add `Episode` and `Source` provenance to every fact.
3. Add valid-time and transaction-time fields.
4. Build contradiction and supersession handling.
5. Create a fixed graph/retrieval evaluation dataset.
6. Build Calendar plus one email connector with incremental synchronization.
7. Use Airflow for ingestion, consolidation, and brief-generation pipelines.
8. Build user-facing memory inspection and correction.
9. Add style profiling only after factual memory is reliable.
10. Add automation execution last.

Do not start with:

- Capturing every browser page
- Fully autonomous email sending
- A huge dynamic prompt
- Dozens of connectors
- Storing every observation forever
- Treating a vector database as the entire memory system

---

# 20. Definition of production-ready

Twin AI is ready for a controlled production beta when:

- Every memory is tenant-scoped
- Every fact has provenance
- Temporal changes are preserved
- Entity merges can be corrected
- Incremental connector sync is replay-safe
- User deletion propagates through raw events, graph, vector, summaries, and backups according to policy
- Prompt injection from captured content is contained
- Automation actions are risk-classified
- External actions have audit logs and approval controls
- Retrieval and temporal-memory evaluations meet defined thresholds
- Cross-user leakage tests are consistently zero
- Users can inspect why the agent believes something
- Users can pause capture and automations instantly

That foundation is what makes the agent feel genuinely personal over time. Tone alone will make it sound familiar; durable evidence-backed memory and safe action will make it useful.

---

# Official references

- Neo4j index configuration: https://neo4j.com/docs/operations-manual/current/performance/index-configuration/
- Mem0 Graph Memory: https://docs.mem0.ai/platform/features/graph-memory
- Graphiti temporal context graphs: https://help.getzep.com/graphiti/getting-started/overview
- Apache Airflow best practices: https://airflow.apache.org/docs/apache-airflow/3.1.0/best-practices.html
- Microsoft Graph delta queries: https://learn.microsoft.com/en-us/graph/delta-query-overview
- Slack Events API: https://docs.slack.dev/apis/events-api/
- Chrome extension permissions: https://developer.chrome.com/docs/extensions/develop/concepts/declare-permissions
