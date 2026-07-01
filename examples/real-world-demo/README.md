# Real-World Demo: Arrow ParserError Boundary

This demo is based on a real Arrow issue:

- Project: [`arrow-py/arrow`](https://github.com/arrow-py/arrow)
- Issue: [`arrow.get` raised wrong exception #535](https://github.com/arrow-py/arrow/issues/535)
- Reported behavior: `arrow.get('20171017', ['YYYY.M.D'])` raised a raw
  `ValueError: month must be in 1..12`.
- Expected behavior: parsing failures should raise Arrow's `ParserError`.

Why this bug:

- It is a real open-source Python library with broad usage.
- The reproduction is local and deterministic.
- The fix is small: catch the low-level date construction `ValueError` while
  trying a candidate format and re-raise `ParserError`.
- It tests a useful agent behavior: preserving a public exception boundary
  rather than only making a test pass.

Files in this directory:

- `setup.sh`: installs the broken Arrow version and runs a reproducer test.
- `sac-session-transcript.md`: demonstration transcript of a SafeCode session.
- `fixture.json`: SWE-bench-Lite-shaped task metadata for this demo.

The transcript is a hand-written demonstration transcript, not an automatically
captured session log.
