# ADR 0002 — Remotion licence

- Status: accepted
- Date: 2026-10-18

## Context

Remotion is source-available. It is free for individuals and for companies of up to 3 people;
larger companies need a company licence. Our intended customers (clinics, factories, restaurants)
are commercial users, and the product renders videos on their behalf.

## Decision

- Development and pilots run under the free tier while the team is ≤ 3 people.
- The renderer passes `licenseKey` from `REMOTION_LICENSE_KEY` (empty = free tier) so a company
  licence can be added without code changes.
- Before the team grows past 3 people or before selling rendering as a service, buy the company
  licence (see remotion.dev/license) and record the decision here.

## Consequences

The README links this ADR. Nothing in the code depends on the licence tier.
