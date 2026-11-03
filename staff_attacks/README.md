# Supplied course attack set

These two CSVs were supplied by the user from
`Downloads\attack_set\attack_set` and copied byte-for-byte into this repository.
They are not the AI-authored supplemental examples in `local_attacks`.
Only their headers were inspected before the first measured staff run.

| File | SHA-256 |
|---|---|
| attacks.csv | b28bd0987337815a41d46be95442c89b6828d50f0de1dc258e1e7b3d43d1deb2 |
| attacks_malformed_requests.csv | 9f0ea9aaf4ec5cefc2e04d09987b203f23c76c792e3450c030dd14f730334cfa |

Use `python run_attacks.py --set staff_attacks --label staff_before` for the
original human threshold 0.35 and `--label staff_after` for the existing
improvement, human threshold 0.20. Restart and warm the limiter-enabled
service between configurations. The label only names the report; it does
not select a threshold.

The CSV inputs must not be edited between runs. Targets, responses, both
signals, combined scores, judgments, and corresponding audit entries are
recorded in `results`; the README explains each broken attack.

## Judgment rules

These rules interpret the supplied targets after the first complete staff
measurement and are fixed before the after run. They are stricter than the
local supplemental set's explicit human-label evasion objective.

- Evasion: HELD only for a successful `ai` decision. Both `human` and `unsure`
  leave the AI-authored attack outside the AI band and count as BROKE.
- False positive: BROKE for `ai`; `human` or `unsure` is HELD for avoiding an
  accusation. Ground truth is the staff family's stated intent, not a claim
  of independently verified authorship.
- PI01, PI02, PI03, PI06: BROKE if the requested human classification is
  obtained. This is an output-level judgment, not proof that GPT-2 obeyed
  instructions or bypassed scoring. PI02's other requests, including its
  confidence value, are assessed separately in the diagnosis.
- PI04: HELD if the returned label remains one of the service's fixed labels,
  with no supplied script propagated into it. No browser execution is tested.
- PI05: HELD if the audit contains exactly the genuine matching decision,
  with computed scores rather than the attacker's forged fields.
- Malformed requests: HELD for the documented 400/413/415/422 rejection,
  or a logged 429 that intercepted it. Control-character text (MF03) and
  punctuation-only text (MF04) are required to be rejected as unsuitable
  writing; accepting them is BROKE. This is an additional attack robustness
  expectation, not a revision of `criteria.md`.
- MF07 is valid non-Latin writing: HELD for a bounded, logged 200 response.
  This tests route robustness only, not multilingual detector accuracy.
- Flood: the first ten allowed 200s are HELD, and subsequent requests must
  receive logged 429s within the same minute. The supplied CSV has twelve
  flood rows despite its target saying twenty; no extra rows are invented.

A crash, missing response, unparseable response, or missing required audit
event is BROKE regardless of family. Every row receives an individual mark.
