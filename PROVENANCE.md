# Provenance

**Project:** GridGuard v1.0.0
**Author / Director:** Mughirah Nasir (<mnasir.bee25seecs@seecs.edu.pk>)
**GitHub:** [@Mughirah-Nasir](https://github.com/Mughirah-Nasir)
**Designed:** May 2026 (project B2 of my summer build plan)
**This implementation:** June 2026, in focused build sessions

## What this document is

A plain statement of where this project came from and how to verify it,
written *before* anyone asked.

## Origin of the idea

GridGuard exists because of a lived problem: scheduled load-shedding in
Pakistan killing long local jobs (Docker builds, DB migrations, big Git
operations) part-way through. The idea — wrap commands in a guard that
consults the published outage rota and a learned duration estimate — came out
of my own portfolio planning for summer 2026, where it appears as project
**B2 "Grid-Aware CI/CD Scheduler"** in my build plan. The concept is local
and specific by design: it is hard to copy from a tutorial because the
problem barely exists where most tutorials are written.

## How it was built (honestly)

I design and direct these projects and build them in openly-disclosed
pair-programming sessions with **Claude (Anthropic)**. Concretely:

* The problem selection, the exit-code-87 contract, the choice of p90 with a
  safety factor for estimates, the pure-`plan_guard` testing architecture,
  the outages-not-uptime schedule model, and the scope of v1.0.0 are my
  decisions, and I can explain every one of them without notes.
* Implementation was AI-assisted. I treat that the way the industry treats
  it in 2026: as a velocity tool, disclosed in the README, with my
  understanding — not my typing speed — as the thing being evidenced.
* The implementation was built rapidly in focused sessions (the commit
  timestamps are honest — I'd rather show fast, well-tested work than
  fake a slower timeline), with AI doing the typing and me doing the
  deciding.
* The test-suite caught two genuine bugs during this build (stale
  previous-day windows leaking from `Schedule.expand()`, and the command
  signature normaliser mis-reading `git -C /repo status`). Both fixes are in
  the commit history with their failing-test context. Real bugs, found and
  fixed, are part of the evidence that this was *developed*, not pasted.

## How to verify authorship

1. **Git history (on GitHub).** Every commit is authored as
   `Mughirah Nasir <mnasir.bee25seecs@seecs.edu.pk>` with honest,
   same-day timestamps from the June 2026 build sessions, small
   Conventional-Commit steps, and a narrative matching the real order
   the code grew — including two failing-test → fix sequences. This public
   zip ships without the `.git` folder; the full history is visible on the
   GitHub repository after the first push.
2. **GitHub push timestamp.** The push date on
   `github.com/Mughirah-Nasir/gridguard` is recorded by GitHub's servers and
   is not editable by me.
3. **Source-tree fingerprint.** `CERTIFICATE.html` in this repository embeds
   a SHA-256 hash over a sorted manifest of the source files. Anyone can
   recompute it (the exact command is in the certificate) and confirm the
   tree they're reading is the tree that was fingerprinted.
4. **(Optional) Blockchain anchor.** The hash can be anchored in the Bitcoin
   blockchain via [OpenTimestamps](https://opentimestamps.org)
   (`ots stamp PROVENANCE.md`), which proves the file existed no later than
   the anchored block's time, with no trust in me required.

## What I do *not* claim

* I do not claim every line was typed by hand without AI assistance.
* I do not claim this is the only tool of its kind ever conceived.

I claim the thing that actually matters: this is **my project** — my problem,
my decisions, my understanding — and the evidence above is checkable.

— Mughirah Nasir, June 2026
