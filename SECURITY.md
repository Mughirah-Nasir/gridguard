# Security policy

## Scope: GridGuard is a local tool

GridGuard is intended to run on your own machine, guarding your own
commands. It is **not** hardened for multi-user or public deployment.

## The dashboard must stay local

The web dashboard (`gridguard serve`) has **no authentication** and exposes
your outage schedule and your recent command history to anyone who can reach
it.

* It binds to `127.0.0.1` by default. Keep it that way.
* Do **not** run it with `--host 0.0.0.0` on a machine reachable from other
  hosts, and do not port-forward it to the internet.
* The provided `docker-compose.yml` publishes the port as
  `127.0.0.1:8087:8087` (localhost only) on purpose.

## The history database contains your raw commands

To estimate durations, GridGuard records every guarded run into a local
SQLite database, including the **full raw command line** -- arguments,
paths, project names, anything you typed after `--`.

* Do not paste secrets (tokens, passwords, connection strings) into command
  lines you run through `gridguard run`. This is good practice anyway --
  command lines also leak via shell history and process lists.
* Treat the database file (default: a path under your home directory,
  configurable via `database = ...`) like any other private file. Delete it
  any time; GridGuard will simply fall back to its default estimates.

## What GridGuard does and does not do

* It runs exactly the command you give it, with your privileges. It does not
  sandbox, escalate, or modify the command.
* It reads only the schedule file and config file you point it at.
* It makes **no network calls**. Schedules are entered manually; nothing is
  fetched, scraped, or uploaded.

## Reporting a vulnerability

Please report security issues privately by email to
**mnasir.bee25seecs@seecs.edu.pk** rather than opening a public issue.
You should get a reply within a few days. After a fix is released you are
welcome to disclose publicly.
