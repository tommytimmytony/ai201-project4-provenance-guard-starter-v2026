# Supplemental local attack set

These 29 cases were authored by Copilot on November 3, 2026. They are **not**
the staff-provided Unit 8 attack set and do not replace that required exercise.
No genuine human writing or measured human false-positive rate is claimed.
EV01-EV04 reuse the existing AI-authored calibration; EV05 adds typos; PI01
adds imperative text. The remaining cases check malformed inputs and a burst.

Judgment rules, fixed before running:

- Evasion/instructions: BROKE only if HTTP 200 returns `human`. An `unsure`
  result prevents this specific human-label objective, but is not evidence of
  reliable AI detection.
- Malformed requests: HELD only for the documented 400, 415, or 422 rejection,
  or a logged 429 before the route. A successful decision or server failure
  is BROKE.
- Flood: the first ten 200s consume the permitted allowance, not a bypass.
  FD01-FD10 are HELD if accepted; FD11-FD15 are HELD only if 429. The burst
  must finish within one minute; a crossed fixed window needs a new run.

Use a warm model and fresh limiter state for each before/after run:

```powershell
.\.venv\Scripts\python.exe run_attacks.py --set local_attacks --label before --url http://127.0.0.1:5018
```
