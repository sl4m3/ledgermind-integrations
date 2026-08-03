# ledgermind-integrations

Client integrations for the language-independent LedgerMind RawRound protocol.

The Python package is intentionally independent from `ledgermind-core` and
`ledgermind-local`. It captures only data observable by the client, computes the
canonical RawRound digest, queues delivery, retrieves context, and sends
`POST /v1/rounds` to either Local or Cloud.

```text
ledgermind-integrations install hermes --destination ~/.hermes/plugins
```

The client never generates a hypothesis and never sends semantic fields such as
`title`, `statement`, `rationale`, `phase`, or `confidence`.
