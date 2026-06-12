# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

This repository is currently empty. It contains only a `.gitkeep` placeholder and a single initial commit — there is no source code, build tooling, tests, README, or dependency manifest yet.

As a result, there are no build, lint, test, or run commands to document at this time. Once the project is scaffolded, this file should be updated with:

- **Commands**: how to build, lint, run, and test the project (including how to run a single test).
- **Architecture**: the big-picture structure that spans multiple files and isn't obvious from a quick directory listing.

When adding code, prefer to keep this file in sync with the actual tooling and structure as they are introduced.

## Git workflow

- The default branch is `main`.
- Development for AI-assisted changes happens on dedicated feature branches (e.g. `claude/...`); do not commit directly to `main`.
- Push feature branches with `git push -u origin <branch-name>`.
