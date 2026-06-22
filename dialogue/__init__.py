"""
dialogue - coordination system for peer Claude Code instances.

Event-driven evolution of board.sh: same storage philosophy (one file = one message,
append-only, no lock), listening via filesystem events (watchdog/FSEvents) instead of
polling, plus identities (registration/registry), an inbox for the autonomous-owner
pattern, and an observability dashboard for the human.

See the README for setup and usage.
"""

__version__ = "0.1.0"
