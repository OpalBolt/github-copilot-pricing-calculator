# Fetch prices only from each seller's own live sources

Every price on the site comes from the seller's own published API or pricing docs, fetched live in the daily build — never from a third-party aggregate. A seller without a publicly fetchable catalog or pricing docs gets no row, and rows self-prune when the seller's catalog drops a model. This trades breadth for trust: the site can never be staler than one build day behind the seller itself. One sanctioned exception exists: OpenCode Zen (ADR 0003).
