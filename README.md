# ledgermind-integrations

`ledgermind-integrations` is LedgerMind's open client-side layer for capturing
RawRound payloads. It is not Local and does not contain the closed Core.

## Capture-only runtime

- Integrations observe only data available to the client and assemble one
  immutable completed `RawRound` with `schema_version=2`: messages, tool calls
  and results, round boundaries, and provenance.
- They do not extract semantic fields, create Hypothesis or Atom entities, or
  make knowledge decisions.
- Integrations **never call models** and contain no model provider, inference
  profile, or provider secret. Model processing is performed by Local or by the
  selected cloud service after it accepts the RawRound.

## Delivery endpoint

After validation and canonical digest calculation, an integration can deliver
the RawRound through the public protocol to a user-selected endpoint:

- a local Local endpoint, usually `POST /rounds`;
- a user-selected Cloud endpoint implementing the same public contract.

The installation owner controls the address, authentication, and egress policy.
Delivery may therefore transfer the observed conversation and tool payload
beyond the machine. Integrations makes this boundary explicit and does not send
semantic hypotheses or credentials.

## Durable spool sensitivity

The spool supports bounded retries and restart recovery. Its records may contain
raw conversations, tool arguments and results, source identity, and provenance.
This remains sensitive data even after provider secrets have been removed.

Keep the spool in a directory with private permissions, bound its size and
retention period, do not synchronize it into public directories, and never
commit it to Git. Treat archives and quarantine records as sensitive backup
artifacts and transfer them only through a trusted channel.

## Supported clients

The platform bundle contains first-party adapters for:

- Hermes;
- Codex CLI;
- Claude Code;
- Cursor;
- OpenCode;
- OpenClaw.

All six adapters use the same public `RawRound` and `ContextView` contracts.
Command-hook clients use one local lifecycle bridge; OpenCode and OpenClaw use
small native JavaScript plugins which call that bridge. No adapter contains
knowledge-resolution logic.

The bridge retrieves context before a turn, labels it as untrusted reference
data, captures actual tool calls and results, and submits one completed round.
Transport failures are fail-open for the agent while the validated RawRound is
kept in the private retry spool. A later successful recall clears the stale
transient network diagnostic, so current health reflects the current delivery
path rather than an already recovered outage.

## Hermes plugin package

Installation registers the plugin entrypoint and provides `plugin.yaml`:

```bash
ledgermind-integrations install hermes --destination ~/.hermes/plugins
```

Registration uses the public Hermes hook surface. Hooks only capture observable
events, fail open on transport errors, and never perform model calls or
unbounded retry loops inside callbacks.

## Package boundary

The Integrations wheel must contain only the namespaced
`ledgermind_integrations` runtime, first-party adapter payloads, and the public
hook bridge. Build copies, test databases, `.pyc` files, private keys, and secret
environment files are excluded from release contents. The shared
`ledgermind-protocol` package provides `py.typed`, the RawRound schema,
canonical JSON, and conformance fixtures.
