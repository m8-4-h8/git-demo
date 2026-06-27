"""Telegram frontend for the Ironsworn bot.

This layer is intentionally thin: it parses incoming commands, calls into the
``engine`` package for any game logic, and formats the result as a reply. It
must contain no game logic of its own.
"""
