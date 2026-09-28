# Offline issue draft

> Copy this file to `.local/issues/<UTC timestamp>-<slug>.md` only when GitHub Issues
> cannot be durably read or written. Files in `.local/issues/` are a gitignored
> temporary outbox, not a source of truth. Do not edit this template's checklist and
> never commit the copy.

## Sync metadata

- Offline-ID: `<stable UUID, kept across retries and handoffs>`
- Repository / branch / base commit:
- Sync owner (only one person writes this draft to GitHub):
- Created: `<YYYY-MM-DDTHH:MM:SSZ>`
- Updated:
- Why GitHub was unavailable: `<network | service | authentication | permission | rate limit | write failure>`
- Issue created or found during reconciliation: `<#number or empty>`
- Proposed type: `<bug | incident | enhancement | tech-debt | documentation | ops>`
- Proposed area: `<area/...>`
- Severity for bug/incident: `<sev1 | sev2 | sev3>`
- Request state: `<not-sent | sent-unconfirmed | confirmed>`
- Intended request: `<create issue | comment/update issue>`

Set `sent-unconfirmed` before sending. If the response is lost, do not resend: search
for the Offline-ID marker and read the content back. An empty search is not proof the
request failed.

## User flow

## Expected vs actual, and impact

## Scope

- In scope:
- Out of scope:

## Technical details

### Confirmed

### Hypotheses to verify

### Paths and safe identifiers

Never record secrets, credentials, signed URLs, or private account/workspace data.

## Checklist

- [ ] ...

## Evidence and closing criteria

- [ ] Local tests/evidence:
- [ ] Live CLI/image/GPU proof, if applicable:
- [ ] Docs to update:

## Local work while offline

- Commits (with `Offline-Issue: <Offline-ID>` trailer while pending):
- Verification run (command, result, source revision/dirty state):
- Open decisions or risks:

## Reconciliation

- [ ] Checked known issue URL, searched exact Offline-ID and open/closed issues
- [ ] Created a new issue or updated the matching one
- [ ] Type, area, severity and proof labels match actual evidence
- [ ] Marker, checklist (including open work), facts, evidence and commit refs read back
- [ ] No write with an unknown outcome remains

After verifying the items above, delete this draft.
