"""Legacy shell help text and slash-command metadata."""

from __future__ import annotations


SHELL_HELP = """\
Slash commands
==============

Start here:
  /status           workspace dashboard and next safe step
  /continue         take one safe step, or explain the blocker

Work:
  Type a request    ask, inspect, edit, or fix using natural language
  /apply            apply pending patch (shows diff and asks first)
  /commit           commit current task locally (asks first)
  /undo             roll back the most recent write-tool checkpoint

Inspect:
  /task             show current task card
  /timeline         show latest high-signal agent timeline
  /sessions         show recent shell and agent sessions
  /history          show recent shell turns
  /debug            show last failure debug info

Configure:
  /ready            check provider/model/network/memory readiness
  /ready --live     opt-in live provider smoke
  /model            show current model, aliases, and readiness
  /model <alias>    switch model: /model flash  /model pro
  /provider status  show provider profile status

Memory:
  /memory           show what will enter context
  /memory review    review pending learned facts
  /memory teach <text>
                    add a non-secret project note
  /memory prune     remove stale workspace memory

Advanced:
  /demo             show a safe first-run demo path
  /smoke live       run the live-provider smoke (opt-in network)
  /tools            list native tools and approval flags
  /cost             show session token/cost estimate
  /mode plan|build  switch agentic shell mode
  /clear            reset shell context and agent session history
  /exit             exit the shell

Model changes via /model are persisted globally (saved to user config).
Natural language input uses the unified AgentLoop runtime. The intent router
below remains only for compatibility with direct legacy callers.
Mutation actions (apply, commit) always require explicit confirmation.
"""


SLASH_COMMANDS = [
    "/status", "/continue", "/timeline", "/sessions", "/resume", "/task", "/overview", "/model", "/provider",
    "/memory", "/ready", "/doctor", "/demo", "/smoke",
    "/apply", "/commit", "/debug", "/clear", "/undo", "/history", "/tools",
    "/cost", "/mode", "/help", "/exit", "/quit",
]
