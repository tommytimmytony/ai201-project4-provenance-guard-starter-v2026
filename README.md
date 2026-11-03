# Provenance Guard

A local, AI-assisted reference implementation of the Unit 7 project.
This is an educational heuristic, **not proof of authorship** and not a tool
for automatically penalizing writers.

All calibration passages and the demonstration criteria were drafted by AI.
They are not the student's original writing or independently chosen criteria.
No human-writing accuracy or false-positive rate has been established.

## Run locally on Windows

Use Python 3.11-3.13. The local `.venv` has been installed.

```powershell
.\.venv\Scripts\python.exe -m unittest test_service -v
$env:AI201_DEBUG = "0"
.\.venv\Scripts\python.exe app.py
```

In another terminal, run `.\.venv\Scripts\python.exe run_demo.py` to record
real HTTP examples. GPT-2 runs locally; its first use downloads model files.
See [RUNNING.md](RUNNING.md) for installation and additional commands.

## What This Does

1. Receive a JSON object containing `text` and `creator_id` at `/submit`.
2. Validate the body, field types, nonblank values, and size limits.
3. Run `detector.py::model_signal` to measure GPT-2 predictability.
4. Run `stylometry.py::style_signal` to measure surface writing patterns.
5. Combine both scores, explicitly treating strong disagreement as uncertainty.
6. Map the combined score to `human`, `unsure`, or `ai` and a full-sentence label.
7. Append the decision to `logs/audit.jsonl`, then return its ID, scores, and label.

### Follow a false positive

Suppose a real writer's predictable, regular prose receives model score 0.82
and style score 0.70. This hypothetical example combines to 0.76 and returns
the AI-pattern label below, with confidence 0.52. It does not establish AI use.
The writer can send the returned ID and their reasoning to `/appeal`.
The service appends an `under_review` event and preserves the initial decision.
This records a review request; it does not automatically overturn the decision
or guarantee that a human has reviewed it.

### Endpoint contracts

Both endpoints require `Content-Type: application/json` and a JSON object.
Requests over 65,536 bytes return 413. Errors use
`{"error": "machine_readable_code", "message": "Explanation."}` and are logged
as rejections rather than decisions.

**POST `/submit`**

| Input field | Requirement |
|---|---|
| `text` | Nonblank string, at least three whitespace-separated words, at most 10,000 characters; must also yield at least three model tokens |
| `creator_id` | Nonblank string, at most 100 characters; surrounding whitespace is removed |

| Output field | Meaning |
|---|---|
| `content_id` | Generated UUID string used for appeals |
| `guess` | `human`, `unsure`, or `ai` |
| `confidence` | `abs(2 * combined_score - 1)`, rounded to four decimals; score extremity, **not an authorship probability** |
| `label` | The exact reader-facing sentence(s) below |
| `model_score` | GPT-2 heuristic, 0-1, higher is more AI-like |
| `style_score` | Surface-pattern heuristic, 0-1, higher is more AI-like |
| `combined_score` | The combined AI-like score, 0-1 |
| `status` | `decided` |

Success returns 200. Invalid fields/JSON return 400; unsupported media returns
415; oversized text/body returns 413; short or unscorable text returns 422;
model loading failure returns 503. Internal failures return 500 rather than
confirming a decision that may not have been recorded.

**POST `/appeal`**

| Input field | Requirement |
|---|---|
| `content_id` | Nonblank string, at most 100 characters, matching an existing decision |
| `reasoning` | Nonblank string, at most 2,000 characters |

Success returns 200 with `content_id`, `status: "under_review"`, and `message`.
Invalid fields return 400, an unknown ID returns 404, unsupported media
returns 415, and an oversized request body returns 413.
Repeated appeals append additional review events; they do not erase history.
The latest event determines the item's current status.

## Signals and Scoring

### Signal one - the model signal

**What it measures:** `detector.py::model_signal` uses GPT-2 perplexity over
the first 400 tokens. It maps perplexity to a score using
`1 / (1 + (perplexity / 45) ** 1.6)`.

**Why that might differ:** Generated text can follow predictable patterns,
but this is a hypothesis about likelihood, not an authorship test.

**What it cannot see:** Who wrote the text, drafts, intent, or edits. Plain
human writing can be predictable; unusual AI-generated prose can be surprising.
Text beyond 400 tokens does not affect this signal.

### Signal two - the style signal

**What it measures:** `stylometry.py` computes:

- Sentence-length spread: sample standard deviation divided by mean word count.
  Fewer than two nonempty sentence lengths gives zero spread.
- Type-token ratio: unique lowercase words divided by total words.
- Punctuation density: ASCII punctuation divided by non-whitespace characters.

**Why that might differ:** Regular sentence lengths, repetition, and sparse
punctuation are illustrative features sometimes associated with generated prose.
They are not universal characteristics of AI writing.

**The rule:** Normalize regularity as `1 - min(spread, 1)`, repetition as
`1 - type_token_ratio`, and sparse punctuation as `1 - min(density / 0.1, 1)`.
Combine them with weights **0.5, 0.3, and 0.2**, respectively. Round to four
decimals. Fewer than 20 words or two sentences returns neutral **0.5**.

**What it cannot see:** Meaning or authorship. Editing sentence breaks, adding
punctuation, or changing words can move the score without changing provenance.
Vocabulary diversity depends on length. Tokenization is English-oriented;
non-English writing is not validated. Unlike the model, style measures the
whole accepted text, so long inputs can produce mismatched evidence.

### The combining rule

**The rule:** Average the signals equally. If their absolute difference is
at least **0.50**, return **0.50** instead, explicitly choosing uncertainty.

**The numbers:** Model weight **0.50**, style weight **0.50**; human boundary
**0.35**, AI boundary **0.65**. Settings live in `config.py`.

**Where it lives:** `scoring.py::combine_signals`.

**A case where the signals split:** The formal calibration paragraph scored
**0.2643 model / 0.6493 style**. Their difference is 0.385, so the average
is **0.4568**, yielding `unsure`. More extreme disagreement, such as
0.1 versus 0.9, is forced to 0.5 by the explicit guard.

These are uncalibrated design choices. The unsure band and disagreement rule
reduce some accusations but also allow more AI-authored text to avoid the AI label.

## Label Variants

The starter calls the outer bands "high-confidence"; the labels deliberately
avoid presenting that phrase as measured authorship certainty.

| Label | Combined score range | Exact text |
|---|---|---|
| human | `0 <= score <= 0.35` | This writing looks more like human writing to our checks. This is an estimate, not proof of who wrote it. |
| unsure | `0.35 < score < 0.65` | Our checks cannot reliably tell how this was written. This is not an accusation; you can request a review. |
| ai | `0.65 <= score <= 1` | Our checks found patterns that can appear in AI-generated writing. People can write this way too; you can request a review. |

**Why the unsure wording:** It describes the system's limitations rather than
the writer's honesty and names an available next action.

### Real calibration results

`run_demo.py` recorded these real GPT-2 responses on October 25, 2026.
All four passages were AI-authored. "Narrative" and "formal" describe style,
not human ground truth. These exact values repeated across all three trials;
the detector uses evaluation mode without sampling.

| Calibration passage | Model | Style | Combined | Guess |
|---|---|---|---|---|
| Regular repetitive prose | 0.9900 | 0.9181 | 0.9541 | ai |
| Irregular narrative | 0.1135 | 0.1506 | 0.1321 | human |
| Formal explanation | 0.2643 | 0.6493 | 0.4568 | unsure |
| Edited conversational prose | 0.2661 | 0.3996 | 0.3328 | human |

All three labels are reachable, but **two AI-authored examples received the
human-like label**. This demonstrates evasion/overlap, not detector accuracy.
Genuine human examples are still needed to estimate false accusations.

## Sample Run

Actual requests and responses from the local service. PowerShell pipes JSON
to curl's standard input to avoid native argument-quoting differences.
New submissions return new IDs; use the ID from your response for an appeal.

**A submission**

```powershell
'{"text":"A review procedure should preserve the original decision and record subsequent objections separately. The resulting history allows a reviewer to distinguish an initial estimate from a later challenge. Such a record does not establish who wrote the underlying document; it establishes what the service did.","creator_id":"sample_writer"}' | curl.exe -X POST http://127.0.0.1:5000/submit -H 'Content-Type: application/json' --data-binary '@-'
```

```json
{
  "combined_score": 0.4568,
  "confidence": 0.0864,
  "content_id": "16db2360-94fc-47cd-b2ed-4a1e28759828",
  "guess": "unsure",
  "label": "Our checks cannot reliably tell how this was written. This is not an accusation; you can request a review.",
  "model_score": 0.2643,
  "status": "decided",
  "style_score": 0.6493
}
```

**An appeal**

```powershell
'{"content_id":"16db2360-94fc-47cd-b2ed-4a1e28759828","reasoning":"Please review this estimate rather than treating it as proof of authorship."}' | curl.exe -X POST http://127.0.0.1:5000/appeal -H 'Content-Type: application/json' --data-binary '@-'
```

```json
{
  "content_id": "16db2360-94fc-47cd-b2ed-4a1e28759828",
  "message": "Your request for review has been recorded. No automatic reassessment has occurred.",
  "status": "under_review"
}
```

**What the log showed immediately afterwards**

```powershell
curl.exe "http://127.0.0.1:5000/log?limit=2"
```

```json
{
  "count": 2,
  "entries": [
    {
      "combined_score": 0.4568,
      "confidence": 0.0864,
      "content_id": "16db2360-94fc-47cd-b2ed-4a1e28759828",
      "creator_id": "sample_writer",
      "guess": "unsure",
      "label": "Our checks cannot reliably tell how this was written. This is not an accusation; you can request a review.",
      "model_score": 0.2643,
      "status": "decided",
      "style_score": 0.6493,
      "timestamp": "2026-10-25T07:56:23+00:00"
    },
    {
      "content_id": "16db2360-94fc-47cd-b2ed-4a1e28759828",
      "creator_id": "sample_writer",
      "event": "appeal",
      "reasoning": "Please review this estimate rather than treating it as proof of authorship.",
      "status": "under_review",
      "timestamp": "2026-10-25T07:56:23+00:00"
    }
  ]
}
```

## How I Used AI

This is an implementation record, not an invented account of independent
student work.

**Moment 1**

- **Request:** "Please finished the project in my local first."
- **Result:** Copilot implemented submission/appeal validation and logging,
  style measures, signal combination, labels, and offline regression tests.
- **Change:** Copilot replaced the starter's stubs. No independent student
  redesign is claimed.

**Moment 2**

- **Request/context:** The same completion request included milestone
  requirements for endpoint evidence, signal diagnostics, and a write-up.
- **Result:** Copilot created AI-authored calibration passages and demonstration
  criteria, then ran the real local model and HTTP requests.
- **Change:** The write-up records actual scores and explicitly identifies
  AI-written examples that were labeled human-like. It does not substitute
  these examples for genuine human writing or a measured false-positive rate.

## Run Log and Verdicts

Evidence: `results/local_demo_20261025T075541Z.json`, generated by
`run_demo.py::main`, and `results/run_2026-10-25_0056_local.md`, generated by
`run_eval.py::main`. The latter covers text/body scenarios; the demo also
exercises appeals, malformed JSON, media types, and raw body limits.

| Demonstration criterion | Trial 1 | Trial 2 | Trial 3 | Verdict |
|---|---|---|---|---|
| 1. Combined score spread >= 0.30 | 0.8220 | 0.8220 | 0.8220 | MET on these synthetic inputs |
| 2. All three labels and bounded numeric scores | All three | All three | All three | MET |
| 3. Appeal recorded; original preserved; unknown ID rejected | Passed | Passed | Passed | MET |
| 4. Invalid requests rejected and recorded | Passed | Passed | Passed | MET |
| 5. Size limits rejected and recorded | Passed | Passed | Passed | MET |

These results are reference checks, not a claim that the separately assigned
Unit 8 attack exercise is complete.

## Rate Limiting

Enabled by default: **10/minute and 200/day** on `/submit`. A writer can submit
a draft and several revisions without being blocked; a thousand same-creator
threshold probes cannot all be accepted. The day limit also bounds sustained
probing. The key uses trimmed `creator_id` with an IP fallback; it is not
authenticated and can be rotated. Storage is in memory, so restarts erase
counts and multiple processes do not share them. `AI201_RATE_LIMITS=0` is an
explicit opt-out for a local demo, not the tested configuration.

**Milestone 1, November 3, 2026:** real GPT-2 HTTP flood on loopback port 5018:

```powershell
.\.venv\Scripts\python.exe run_attacks.py --flood 15 --creator flood_milestone1_warm --url http://127.0.0.1:5018 --timeout 300
```

```text
200 200 200 200 200 200 200 200 200 200 429 429 429 429 429
```

Evidence: `results/flood_2026-11-03_0122.md` and
`results/milestone1_audit.json`. The first, cold-model attempt admitted eleven
requests because model loading crossed a fixed-window expiry; it still produced
four 429s. The warm run above admitted ten and logged all five rejections.
This is a per-window limit, not a promise of exactly ten successes in every
fifteen-request run regardless of elapsed time.

Three additional submissions were read back through `GET /log` and matched
their returned IDs, labels, status, and both signal and combined scores.
Every decision contains `timestamp`, `content_id`, `creator_id`, `guess`,
`model_score`, `style_score`, `combined_score`, `label`, and `status`.
A missing-text request returned 400 and left an `invalid_text` rejection.
The offline suite also passes all 15 tests; mocks are separate from this live
evidence.

## Attack Run - Before / The Improvement / Attack Run - After

**Staff-set blocker:** neither `attacks.csv` nor
`attacks_malformed_requests.csv` was supplied in the project or nearby course
folders, and no relevant download archive was found. The staff attack exercise
cannot be claimed complete. `local_attacks/` is explicitly AI-authored
supplemental testing, not a renamed or reconstructed staff set. It contains
29 cases and no genuine human-authored false-positive examples.

### Supplemental attack baseline

```powershell
.\.venv\Scripts\python.exe run_attacks.py --set local_attacks --label before --url http://127.0.0.1:5018 --timeout 300
```

Raw evidence: `results/attack_run_2026-11-03_012447_091516_before.json`.
Judged outcomes for **every** input: `results/local_verdicts_before.json`.
Whole-run audit: `results/local_audit_before.json`, also present in the
append-only `logs/audit.jsonl`.

| ID | Objective | Model | Style | Combined | Guess | Verdict |
|---|---|---|---|---|---|---|
| EV01 | AI-authored text receives human label | 0.9919 | 0.9181 | 0.9550 | ai | HELD |
| EV02 | AI-authored narrative receives human label | 0.1135 | 0.1506 | 0.1321 | human | BROKE |
| EV03 | AI-authored formal text receives human label | 0.2643 | 0.6493 | 0.4568 | unsure | HELD |
| EV04 | AI-authored conversational text receives human label | 0.2661 | 0.3996 | 0.3328 | human | BROKE |
| EV05 | Typo-edited AI narrative receives human label | 0.0107 | 0.1578 | 0.0842 | human | BROKE |
| PI01 | Instructions make text receive human label | 0.1665 | 0.4575 | 0.3120 | human | BROKE |

Total: **25 HELD, 4 BROKE**. MD01-MD08 were rejected and logged; FD01-FD10
used the allowed ten requests and FD11-FD15 returned logged 429s. All 29
requests have an outcome and a judgment in the verdict file. The flood's
audit timestamps span two seconds. A normal allowed flood request is not a
bypass; the objective was acceptance beyond the configured allowance.
MD03's `json=None` is sent by Requests without a JSON body/content type, so
it exercised a 415 media rejection rather than literal JSON null. The
criterion runner separately sends literal `null` and checks 400.

### Ten real baseline audit entries

These include all four broken attacks, contrasting successful decisions,
route rejections, and two limiter rejections. Decision timestamps are UTC
as stored, not local display time. Rejections intentionally have fewer fields.

```json
[
  {"timestamp":"2026-11-03T09:24:44+00:00","content_id":"4ce40d8e-ba05-4444-b8f2-e40e0d8ffd28","creator_id":"attacker_EV01","guess":"ai","model_score":0.9919,"style_score":0.9181,"combined_score":0.955,"label":"Our checks found patterns that can appear in AI-generated writing. People can write this way too; you can request a review.","status":"decided","confidence":0.91},
  {"timestamp":"2026-11-03T09:24:44+00:00","content_id":"144e1be2-8774-471a-b68c-1eb59559d1cf","creator_id":"attacker_EV02","guess":"human","model_score":0.1135,"style_score":0.1506,"combined_score":0.1321,"label":"This writing looks more like human writing to our checks. This is an estimate, not proof of who wrote it.","status":"decided","confidence":0.7358},
  {"timestamp":"2026-11-03T09:24:44+00:00","content_id":"7ab9d5dc-2995-4da2-a408-44adcb0e97ce","creator_id":"attacker_EV03","guess":"unsure","model_score":0.2643,"style_score":0.6493,"combined_score":0.4568,"label":"Our checks cannot reliably tell how this was written. This is not an accusation; you can request a review.","status":"decided","confidence":0.0864},
  {"timestamp":"2026-11-03T09:24:44+00:00","content_id":"8adf1156-d872-4056-b3fc-be55a0612f90","creator_id":"attacker_EV04","guess":"human","model_score":0.2661,"style_score":0.3996,"combined_score":0.3328,"label":"This writing looks more like human writing to our checks. This is an estimate, not proof of who wrote it.","status":"decided","confidence":0.3344},
  {"timestamp":"2026-11-03T09:24:45+00:00","content_id":"70606c08-e4de-4426-9893-af2f722adaf3","creator_id":"attacker_EV05","guess":"human","model_score":0.0107,"style_score":0.1578,"combined_score":0.0842,"label":"This writing looks more like human writing to our checks. This is an estimate, not proof of who wrote it.","status":"decided","confidence":0.8316},
  {"timestamp":"2026-11-03T09:24:45+00:00","content_id":"9ee4186d-c882-4a96-bdad-27148979bfd1","creator_id":"attacker_PI01","guess":"human","model_score":0.1665,"style_score":0.4575,"combined_score":0.312,"label":"This writing looks more like human writing to our checks. This is an estimate, not proof of who wrote it.","status":"decided","confidence":0.376},
  {"timestamp":"2026-11-03T09:24:45+00:00","creator_id":"local_missing","event":"rejected","status":"rejected","reason":"invalid_text","route":"/submit"},
  {"timestamp":"2026-11-03T09:24:45+00:00","creator_id":"local_short","event":"rejected","status":"rejected","reason":"text_too_short","route":"/submit"},
  {"timestamp":"2026-11-03T09:24:46+00:00","creator_id":"local_flood_creator","event":"rejected","status":"rejected","reason":"rate_limited","route":"/submit","limit":"10 per 1 minute"},
  {"timestamp":"2026-11-03T09:24:47+00:00","creator_id":"local_flood_creator","event":"rejected","status":"rejected","reason":"rate_limited","route":"/submit","limit":"10 per 1 minute"}
]
```

## What's Still Broken

AI can imitate irregular writing, while people can write predictable prose.
The live synthetic examples already show AI-authored text receiving a
human-like label. Real human false positives remain unmeasured. Thresholds
and style normalization are not statistically calibrated.

The local demo has no authentication, ownership checks, reviewer interface,
or automated review worker. `/log` exposes audit metadata and appeal reasoning
to anyone who can access the service. Keep it on loopback and do not use
sensitive text or identifying creator IDs. Model failures and slow inference
also require operational handling before any real deployment.

**The production trade:** Favor uncertainty and human review over automatic
accusations. This lets more AI-written text through, but avoids making a
writer bear the cost of an unsupported automated verdict.

## Submission status

The local Unit 7 implementation, environment, examples, and write-up are
present. Changes are uncommitted; no milestone history or remote submission
has been fabricated. For a student's own submission, replace the reference
criteria with independently defended targets, supply genuine original writing,
and disclose AI assistance. Unit 8 attack work is separate.
