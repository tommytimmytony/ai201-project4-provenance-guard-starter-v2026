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

**The current numbers:** Model weight **0.50**, style weight **0.50**; human
boundary **0.20**, AI boundary **0.65**. Settings live in `config.py`. The
Unit 8 before run used human boundary 0.35; the single improvement lowers it
to 0.20 without changing either signal or the combining rule.

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
| human | `0 <= score <= 0.20` | This writing looks more like human writing to our checks. This is an estimate, not proof of who wrote it. |
| unsure | `0.20 < score < 0.65` | Our checks cannot reliably tell how this was written. This is not an accusation; you can request a review. |
| ai | `0.65 <= score <= 1` | Our checks found patterns that can appear in AI-generated writing. People can write this way too; you can request a review. |

**Why the unsure wording:** It describes the system's limitations rather than
the writer's honesty and names an available next action.

### Real calibration results

`run_demo.py` recorded these real GPT-2 responses on October 25, 2026.
All four passages were AI-authored. "Narrative" and "formal" describe style,
not human ground truth. These exact values repeated across all three trials;
the detector uses evaluation mode without sampling.
These historical responses used the earlier human boundary **0.35**, not the
current 0.20 boundary; their original labels are preserved as evidence.

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

**Moment 3 - Unit 8**

- **Request:** "Complete the milestone with this project" and the supplied
  six-milestone assignment.
- **Result:** Copilot enabled rate limiting, ran real GPT-2/HTTP flood and
  audit checks, implemented the five existing criteria as executable checks,
  and created a clearly labeled supplemental attack set because the TF's CSVs
  were missing.
- **Change:** Copilot diagnosed the recorded local failures, selected one
  human-label threshold change, and ran the before/after experiment. The
  diagnoses, passages, and write-up are AI-assisted; independent student
  judgments, original writing, staff-set completion, and course submission
  are not fabricated.

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
At this milestone the offline suite passed all 15 then-existing tests;
mocks are separate from this live evidence.

## Attack Run - Before / The Improvement / Attack Run - After

**Historical staff-set limitation, now resolved:** neither `attacks.csv` nor
`attacks_malformed_requests.csv` was supplied in the project or nearby course
folders during the initial local experiment. The user subsequently supplied
the set on November 3, 2026; its measured results are documented below.
`local_attacks/` is explicitly AI-authored
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

### Five criteria: baseline run log

`criteria.md` is unchanged. This run uses the existing AI-drafted reference
criteria; no independently chosen student targets or genuine human writing
are claimed. `run_eval.py::main` executes the five checks in `scenarios.py`
and records their real responses. Evidence:
`results/run_2026-11-03_012959_637500_before.md` and its paired `.json`.

| Criterion | Target | Run 1 | Run 2 | Run 3 | Verdict |
|---|---|---|---|---|---|
| 1. Score spread | >= 0.30 | 0.8220 | 0.8220 | 0.8220 | MET |
| 2. Label coverage | 3/3 labels; bounded scores | 3/3 | 3/3 | 3/3 | MET |
| 3. Appeal traceability | 3/3 traceability checks | 3/3 | 3/3 | 3/3 | MET |
| 4. Invalid input | 12/12 expected errors; all rejections logged | 12/12 | 12/12 | 12/12 | MET |
| 5. Size limits | 3/3 expected errors; all rejections logged | 3/3 | 3/3 | 3/3 | MET |

Criterion 4 waits 65 seconds before and between trials so unusable creator IDs
do not exhaust the shared-IP quota. Otherwise a legitimate 429 could replace
the 400/415/422 route behavior this particular target measures. The separate
flood and local malformed set still measure rate-limit rejection behavior.
All score measurements and outcomes repeated identically; UUIDs and timestamps
are expected to differ. This demonstrates repeatability, not accuracy.

**Criterion 1, trial 1:** `scenarios.py::score_spread` sends two submissions
to `app.py::submit`; their combined scores differ by 0.8220.

```json
[
  {"status":200,"response":{"combined_score":0.9541,"confidence":0.9082,"content_id":"bacd12ca-c2b2-4a2e-8af2-b43807a10207","guess":"ai","label":"Our checks found patterns that can appear in AI-generated writing. People can write this way too; you can request a review.","model_score":0.99,"status":"decided","style_score":0.9181}},
  {"status":200,"response":{"combined_score":0.1321,"confidence":0.7358,"content_id":"53d82e35-3fd9-4928-a6b4-4cf75b53bd35","guess":"human","label":"This writing looks more like human writing to our checks. This is an estimate, not proof of who wrote it.","model_score":0.1135,"status":"decided","style_score":0.1506}}
]
```

**Criterion 2, trial 1:** `scenarios.py::label_coverage` -> `app.py::submit`.

```json
[
  {"status":200,"response":{"combined_score":0.9541,"confidence":0.9082,"content_id":"32c351d1-ac4d-4f6c-8d51-6bd3dfa7cfed","guess":"ai","label":"Our checks found patterns that can appear in AI-generated writing. People can write this way too; you can request a review.","model_score":0.99,"status":"decided","style_score":0.9181}},
  {"status":200,"response":{"combined_score":0.1321,"confidence":0.7358,"content_id":"c8fb1521-c856-4801-a02b-ec689728a763","guess":"human","label":"This writing looks more like human writing to our checks. This is an estimate, not proof of who wrote it.","model_score":0.1135,"status":"decided","style_score":0.1506}},
  {"status":200,"response":{"combined_score":0.4568,"confidence":0.0864,"content_id":"99702372-cb4f-4e88-9c38-e563e87f6a53","guess":"unsure","label":"Our checks cannot reliably tell how this was written. This is not an accusation; you can request a review.","model_score":0.2643,"status":"decided","style_score":0.6493}},
  {"status":200,"response":{"combined_score":0.3328,"confidence":0.3344,"content_id":"4f8104a4-59a4-429f-a97c-7caf1af2fbc2","guess":"human","label":"This writing looks more like human writing to our checks. This is an estimate, not proof of who wrote it.","model_score":0.2661,"status":"decided","style_score":0.3996}}
]
```

**Criterion 3, trial 1:** `scenarios.py::appeal_traceability` ->
`app.py::appeal`. The report also preserves the matching original and appeal
audit events, checks creator/reasoning equality, and verifies the original
decision was not modified.

```json
[
  {"status":200,"response":{"content_id":"db6f0484-c2f4-4464-87f1-a3a2e62886f2","message":"Your request for review has been recorded. No automatic reassessment has occurred.","status":"under_review"}},
  {"status":404,"response":{"error":"content_not_found","message":"No submission has that content_id."}}
]
```

**Criterion 4, trial 1:** `scenarios.py::invalid_input` ->
`app.py::submit`, `app.py::json_object`, and `app.py::reject`. All twelve
requests produced these actual status/response records and twelve rejection
entries, with no new decision.

```json
[
  {"status":400,"response":{"error":"invalid_text","message":"text must be a nonblank string."}},
  {"status":400,"response":{"error":"invalid_text","message":"text must be a nonblank string."}},
  {"status":400,"response":{"error":"invalid_text","message":"text must be a nonblank string."}},
  {"status":400,"response":{"error":"invalid_text","message":"text must be a nonblank string."}},
  {"status":400,"response":{"error":"invalid_text","message":"text must be a nonblank string."}},
  {"status":400,"response":{"error":"invalid_creator_id","message":"creator_id must be a nonblank string of at most 100 characters."}},
  {"status":400,"response":{"error":"invalid_json","message":"Send a valid JSON object."}},
  {"status":400,"response":{"error":"invalid_json","message":"Send a valid JSON object."}},
  {"status":400,"response":{"error":"invalid_json","message":"Send a valid JSON object."}},
  {"status":400,"response":{"error":"invalid_json","message":"Send a valid JSON object."}},
  {"status":415,"response":{"error":"unsupported_media_type","message":"Send Content-Type: application/json."}},
  {"status":422,"response":{"error":"text_too_short","message":"Provide at least three words."}}
]
```

**Criterion 5, trial 1:** `scenarios.py::size_limits` ->
`app.py::submit`, `app.py::request_too_large`, and `app.py::appeal`.
All three are logged rejections; none is a decision or appeal.

```json
[
  {"status":413,"response":{"error":"text_too_long","message":"text must not exceed 10000 characters."}},
  {"status":413,"response":{"error":"request_too_large","message":"The request body exceeds 65536 bytes."}},
  {"status":400,"response":{"error":"invalid_reasoning","message":"reasoning must be a nonblank string of at most 2000 characters."}}
]
```

### Diagnosis of every broken local attack

These are AI-assisted diagnoses grounded in the recorded scores and the
actual functions, not a claimed independent student's analysis.

**How each criterion was called:** C1 is MET because 0.8220 exceeds 0.30
in all three trials. C2 is MET because every trial reaches all three labels
and every returned numeric score is finite and bounded. C3 is MET because
each trial preserves the original, appends the correct review event, and
rejects the unknown ID without an appeal. C4 is MET because each trial gets
all twelve exact error statuses and twelve rejection events, not decisions.
C5 is MET because both size errors and oversized reasoning have the exact
expected statuses and rejection events in all three trials. No target was
relaxed and no criterion was revised.

The strongest argument against C2's MET verdict is that AI-authored prose
reaches `human`, which is bad detection. That does not falsify this target:
it measures interface coverage, not accuracy. The recorded guesses and bounded
scores settle coverage; a provenance-labeled human/AI dataset is needed to
settle accuracy. Passing all five reference criteria while four local attacks
break shows the targets are limited. I would add a separate target for
false-human labels on held-out AI writing and a human false-positive target
using the student's genuine writing, rather than retroactively weaken or
replace these criteria.

| Attack | Stage and mechanism |
|---|---|
| EV02 | **Signal one and signal two:** rare narrative choices have model score 0.1135; irregular sentence lengths (spread 0.8716) and high word variety (0.9423) give style 0.1506. Both heuristics mistake an AI-authored imitation for human-like surface patterns. Their 0.1321 mean is below the human boundary. |
| EV04 | **Combining rule and label mapping:** model 0.2661 and style 0.3996 average to 0.3328. Their disagreement is only 0.1335, so the 0.50 disagreement guard does not apply; the original human boundary 0.35 grants a human-like label to this AI-authored conversational passage. |
| EV05 | **Signal one, with signal two unable to rescue it:** deliberate misspellings make the prose much less predictable, dropping model score from EV02's 0.1135 to 0.0107. Sentence spread and type-token ratio remain exactly 0.8716 and 0.9423; contrary to a tempting explanation, these edits did NOT increase measured word variety. Style rises slightly to 0.1578 as punctuation becomes less dense, but the mean still falls to 0.0842. |
| PI01 | **Signal one, combining rule, and label mapping:** instruction-shaped prose scores 0.1665 model and 0.4575 style; the mean 0.3120 falls in the original human band. GPT-2 is evaluated for next-token loss; it does not follow these instructions or select the returned label. This is a heuristic evasion, not evidence that the service obeyed a prompt injection. |

**Pattern:** all four are accepted AI-authored inputs in the human band.
The route correctly accepts valid strings; authorship is not encoded in
surface predictability or style. EV04 and PI01 sit near the original human
boundary, while EV02 and EV05 are deep inside it. A threshold change can
address the former two without pretending it solves the latter two.

**Worst local failure: EV05.** This is the smallest AI-like score and
therefore the strongest misleading human-like estimate among this local set.
There is no human false-positive attack here, so this is not a measured worst
outcome for a real writer accused of AI use.

Input from `local_attacks/attacks.csv`:

```text
Stopp! I lugged my dentted kettlle uphill, past briarrs, shouting: 'Why todai?' Noboddy answered; duskk bruised the riddge. Fine. We campped beside a crookked fence, countted twelve motths, and forgott the tea. My left boott squeaked. Somewhere below us, a tracttor coughed twice; Mara insisted it sounded like her grandfatther's accordionn.
```

Actual `/submit` response:

```json
{
  "combined_score": 0.0842,
  "confidence": 0.8316,
  "content_id": "70606c08-e4de-4426-9893-af2f722adaf3",
  "guess": "human",
  "label": "This writing looks more like human writing to our checks. This is an estimate, not proof of who wrote it.",
  "model_score": 0.0107,
  "status": "decided",
  "style_score": 0.1578
}
```

The confidence is score extremity, not an 83% probability of human authorship.
Three candidate explanations at different stages were: the route accidentally
sent a truncated or empty string; typo-induced rarity reduced the model score;
the combining/label rules converted weak evidence into a human-like label.
The CSV and returned signal scores rule out an empty-string route bypass;
the feature comparison isolates the large model-score drop, followed by the
documented equal-weight mean and human boundary.

### One improvement selected from the diagnosis

Change only `config.py::HUMAN_THRESHOLD` from **0.35 to 0.20**. Leave the model,
style calculations, 0.50/0.50 weights, 0.50 disagreement guard, AI boundary
0.65, input validation, rate limits, and local attack inputs unchanged.
This widens the unsure band on the human side; it is not a claim that the
remaining low-score evasions become detectable. Before applying it, the
prediction is that EV04 (0.3328) and PI01 (0.3120) move from `human` to `unsure`,
while EV02 (0.1321) and EV05 (0.0842) remain broken.

Cost: genuine human writing scoring between 0.20 and 0.35 would now receive
uncertainty and may need review. Because this local set has no genuine human
writing, the size of that cost cannot be measured here. Merely preventing a
human-label objective must not be described as correctly detecting AI.

### Supplemental attack after run and comparison

```powershell
.\.venv\Scripts\python.exe run_attacks.py --set local_attacks --label after --url http://127.0.0.1:5018 --timeout 300
.\.venv\Scripts\python.exe run_eval.py --label after --url http://127.0.0.1:5018 --timeout 300
```

The restarted loopback server had limiting enabled and real cached GPT-2
warmed before the burst. The same 29 inputs were used without edits.
Raw after evidence: `results/attack_run_2026-11-03_013610_344547_after.json`
and its paired `.md`. Every judged outcome is in
`results/local_verdicts_after.json`; all 29 matching audit events are in
`results/local_audit_after.json`. `results/local_comparison.json` records
the side-by-side attack and criterion measurements.

| ID | Before HTTP | Before guess | Before verdict | After HTTP | After guess | After verdict |
|---|---|---|---|---|---|---|
| EV01 | 200 | ai | HELD | 200 | ai | HELD |
| EV02 | 200 | human | BROKE | 200 | human | BROKE |
| EV03 | 200 | unsure | HELD | 200 | unsure | HELD |
| EV04 | 200 | human | BROKE | 200 | unsure | HELD |
| EV05 | 200 | human | BROKE | 200 | human | BROKE |
| PI01 | 200 | human | BROKE | 200 | unsure | HELD |
| MD01 | 400 | - | HELD | 400 | - | HELD |
| MD02 | 400 | - | HELD | 400 | - | HELD |
| MD03 | 415 | - | HELD | 415 | - | HELD |
| MD04 | 400 | - | HELD | 400 | - | HELD |
| MD05 | 400 | - | HELD | 400 | - | HELD |
| MD06 | 400 | - | HELD | 400 | - | HELD |
| MD07 | 415 | - | HELD | 415 | - | HELD |
| MD08 | 422 | - | HELD | 422 | - | HELD |
| FD01 | 200 | human | HELD | 200 | unsure | HELD |
| FD02 | 200 | human | HELD | 200 | unsure | HELD |
| FD03 | 200 | human | HELD | 200 | unsure | HELD |
| FD04 | 200 | human | HELD | 200 | unsure | HELD |
| FD05 | 200 | human | HELD | 200 | unsure | HELD |
| FD06 | 200 | human | HELD | 200 | unsure | HELD |
| FD07 | 200 | human | HELD | 200 | unsure | HELD |
| FD08 | 200 | human | HELD | 200 | unsure | HELD |
| FD09 | 200 | human | HELD | 200 | unsure | HELD |
| FD10 | 200 | human | HELD | 200 | unsure | HELD |
| FD11 | 429 | - | HELD | 429 | - | HELD |
| FD12 | 429 | - | HELD | 429 | - | HELD |
| FD13 | 429 | - | HELD | 429 | - | HELD |
| FD14 | 429 | - | HELD | 429 | - | HELD |
| FD15 | 429 | - | HELD | 429 | - | HELD |

The total changes from **25 HELD / 4 BROKE** to **27 HELD / 2 BROKE** under
the original, precommitted judgment rules. Model, style, combined, confidence,
and HTTP statuses are unchanged for all corresponding successful requests.
EV04 and PI01 now receive uncertainty rather than a human-like label.
The ten allowed flood submissions also change from `human` to `unsure`;
their rate-limit verdict remains HELD because their objective concerns
acceptance beyond ten, not authorship. The after flood again spans two
seconds and contains ten 200s followed by five logged 429s.

**Did it help?** Yes for this local human-label evasion objective: two of four
broken text cases now receive `unsure`, but EV02 and EV05 still break, the AI
label catches no additional cases, and the cost to genuine human writers is
unmeasured.

### Five criteria: after run log

Actual evidence: `results/run_2026-11-03_013935_033230_after.md` and its
paired `.json`, produced by `run_eval.py::main` using the same five
`scenarios.py` functions and unchanged `criteria.md` targets.

| Criterion | Target | Run 1 | Run 2 | Run 3 | Verdict |
|---|---|---|---|---|---|
| 1. Score spread | >= 0.30 | 0.8220 | 0.8220 | 0.8220 | MET |
| 2. Label coverage | 3/3 labels; bounded scores | 3/3 | 3/3 | 3/3 | MET |
| 3. Appeal traceability | 3/3 traceability checks | 3/3 | 3/3 | 3/3 | MET |
| 4. Invalid input | 12/12 expected errors; all rejections logged | 12/12 | 12/12 | 12/12 | MET |
| 5. Size limits | 3/3 expected errors; all rejections logged | 3/3 | 3/3 | 3/3 | MET |

| Criterion | Before: runs 1 / 2 / 3 | After: runs 1 / 2 / 3 | Verdict comparison |
|---|---|---|---|
| 1. Score spread | 0.8220 / 0.8220 / 0.8220 | 0.8220 / 0.8220 / 0.8220 | MET / MET |
| 2. Label coverage | 3/3 / 3/3 / 3/3 | 3/3 / 3/3 / 3/3 | MET / MET |
| 3. Appeal traceability | 3/3 / 3/3 / 3/3 | 3/3 / 3/3 / 3/3 | MET / MET |
| 4. Invalid input | 12/12 / 12/12 / 12/12 | 12/12 / 12/12 / 12/12 | MET / MET |
| 5. Size limits | 3/3 / 3/3 / 3/3 | 3/3 / 3/3 / 3/3 | MET / MET |

The same verdict reasoning applies to every after trial: the spread exceeds
0.30; all three labels remain reachable with bounded scores; appeals preserve
and append the required events; every invalid-input and size case returns its
specified error and audit outcome. All three after measurements repeat
identically, and no criterion is MISSED. Label coverage remains MET despite
the fourth calibration passage moving to `unsure`, because the other three
still cover `ai`, `human`, and `unsure`.

**Criterion 1, after trial 1:** actual output from
`scenarios.py::score_spread` -> `app.py::submit`.

```json
[
  {"status":200,"response":{"combined_score":0.9541,"confidence":0.9082,"content_id":"2ee856db-e5f3-45f9-be97-26f96bb6185e","guess":"ai","label":"Our checks found patterns that can appear in AI-generated writing. People can write this way too; you can request a review.","model_score":0.99,"status":"decided","style_score":0.9181}},
  {"status":200,"response":{"combined_score":0.1321,"confidence":0.7358,"content_id":"5baf02ae-3e11-448d-949b-a945dc5461fa","guess":"human","label":"This writing looks more like human writing to our checks. This is an estimate, not proof of who wrote it.","model_score":0.1135,"status":"decided","style_score":0.1506}}
]
```

**Criterion 2, after trial 1:** actual output from
`scenarios.py::label_coverage` -> `app.py::submit`.

```json
[
  {"status":200,"response":{"combined_score":0.9541,"confidence":0.9082,"content_id":"2fecb68f-58e0-4c74-96b5-e8bca7387a38","guess":"ai","label":"Our checks found patterns that can appear in AI-generated writing. People can write this way too; you can request a review.","model_score":0.99,"status":"decided","style_score":0.9181}},
  {"status":200,"response":{"combined_score":0.1321,"confidence":0.7358,"content_id":"8434837a-4c65-4f72-9e17-dd6a955decd7","guess":"human","label":"This writing looks more like human writing to our checks. This is an estimate, not proof of who wrote it.","model_score":0.1135,"status":"decided","style_score":0.1506}},
  {"status":200,"response":{"combined_score":0.4568,"confidence":0.0864,"content_id":"7c3ded78-0bc9-4859-8b9c-5736aa9052e1","guess":"unsure","label":"Our checks cannot reliably tell how this was written. This is not an accusation; you can request a review.","model_score":0.2643,"status":"decided","style_score":0.6493}},
  {"status":200,"response":{"combined_score":0.3328,"confidence":0.3344,"content_id":"f5054c08-6717-4804-bab0-4894a350a1eb","guess":"unsure","label":"Our checks cannot reliably tell how this was written. This is not an accusation; you can request a review.","model_score":0.2661,"status":"decided","style_score":0.3996}}
]
```

**Criterion 3, after trial 1:** actual output from
`scenarios.py::appeal_traceability` -> `app.py::submit` and `app.py::appeal`.
The full report also contains the unchanged original and matching appended
appeal audit entries.

```json
[
  {"status":200,"response":{"combined_score":0.9541,"confidence":0.9082,"content_id":"5f97a3f6-2fe0-42a5-a0b9-3fc8be74676f","guess":"ai","label":"Our checks found patterns that can appear in AI-generated writing. People can write this way too; you can request a review.","model_score":0.99,"status":"decided","style_score":0.9181}},
  {"status":200,"response":{"content_id":"5f97a3f6-2fe0-42a5-a0b9-3fc8be74676f","message":"Your request for review has been recorded. No automatic reassessment has occurred.","status":"under_review"}},
  {"status":404,"response":{"error":"content_not_found","message":"No submission has that content_id."}}
]
```

**Criterion 4, after trial 1:** actual output from
`scenarios.py::invalid_input` -> `app.py::submit`, `app.py::json_object`,
and `app.py::reject`. The report verifies all twelve rejection entries.

```json
[
  {"status":400,"response":{"error":"invalid_text","message":"text must be a nonblank string."}},
  {"status":400,"response":{"error":"invalid_text","message":"text must be a nonblank string."}},
  {"status":400,"response":{"error":"invalid_text","message":"text must be a nonblank string."}},
  {"status":400,"response":{"error":"invalid_text","message":"text must be a nonblank string."}},
  {"status":400,"response":{"error":"invalid_text","message":"text must be a nonblank string."}},
  {"status":400,"response":{"error":"invalid_creator_id","message":"creator_id must be a nonblank string of at most 100 characters."}},
  {"status":400,"response":{"error":"invalid_json","message":"Send a valid JSON object."}},
  {"status":400,"response":{"error":"invalid_json","message":"Send a valid JSON object."}},
  {"status":400,"response":{"error":"invalid_json","message":"Send a valid JSON object."}},
  {"status":400,"response":{"error":"invalid_json","message":"Send a valid JSON object."}},
  {"status":415,"response":{"error":"unsupported_media_type","message":"Send Content-Type: application/json."}},
  {"status":422,"response":{"error":"text_too_short","message":"Provide at least three words."}}
]
```

**Criterion 5, after trial 1:** actual output from
`scenarios.py::size_limits` -> `app.py::submit`, `app.py::request_too_large`,
and `app.py::appeal`. All three rejections are in the full report.

```json
[
  {"status":413,"response":{"error":"text_too_long","message":"text must not exceed 10000 characters."}},
  {"status":413,"response":{"error":"request_too_large","message":"The request body exceeds 65536 bytes."}},
  {"status":400,"response":{"error":"invalid_reasoning","message":"reasoning must be a nonblank string of at most 2000 characters."}}
]
```

## Supplied staff attack set

The user supplied `Downloads\attack_set\attack_set` after the supplemental
experiment. Both CSVs are copied unchanged into `staff_attacks/`, with
SHA-256 provenance recorded there and in each phase's metadata.
Only their headers were inspected before the first full measurement.
The original configuration was temporarily restored to human threshold
**0.35**; no model, style, weighting, validation, or rate-limit change was
made for this baseline.

### Staff baseline: every input measured

```powershell
.\.venv\Scripts\python.exe run_attacks.py --set staff_attacks --label staff_before --url http://127.0.0.1:5018 --timeout 300
.\.venv\Scripts\python.exe run_eval.py --label staff_before --url http://127.0.0.1:5018 --timeout 300
```

Raw attack evidence: `results/attack_run_2026-11-03_014941_924998_staff_before.json`
and its `.md`. All **56** individually judged rows:
`results/staff_before_verdicts.json`. The exact whole-run audit slice is
`results/staff_before_audit.json`; every request has its matching decision
or rejection. There were no skipped rows, crashes, or non-JSON responses.
The first CSV contains 32 rows and the second contains 24.

| Family | Inputs | HELD | BROKE |
|---|---|---|---|
| Evasion | 10 | 1 | 9 |
| False positive | 8 | 2 | 6 |
| Prompt injection | 6 | 5 | 1 |
| Malformed | 20 | 18 | 2 |
| Same-creator flood | 12 | 12 | 0 |
| Total | 56 | 38 | 18 |

**Judgment policy:** the staff evasion objective is broader than the local
set's explicit human-label objective: `unsure` still avoids an AI label, so
it counts as BROKE for staff evasion. False-positive cases break only when
they receive `ai`. Injection cases are assessed against their requested
output or audit effect, not treated as proof of instruction execution.
MF03/MF04 break because unsuitable control/punctuation text is classified
instead of rejected. MF07 is valid non-Latin writing, so its bounded, logged
200 is HELD for route robustness only. Full fixed rules are in
`staff_attacks/README.md`; none changes `criteria.md`.

The flood target says twenty submissions, but the supplied CSV contains
**twelve** flood rows. All twelve were run: ten 200s, then two logged 429s,
within one second. No missing eight rows or twenty-request result is invented.
The separate Milestone 1 fifteen-request flood remains the limiter evidence.

### Ten real staff audit entries

These cover evasion, human false accusations, the partial injection output,
accepted junk, and a limiter rejection. Timestamps are the stored UTC values.

```json
[
  {"combined_score":0.3918,"confidence":0.2164,"content_id":"55ae7328-3d6f-4c63-8da9-7cb6ee0559e8","creator_id":"attacker_EV01","guess":"unsure","label":"Our checks cannot reliably tell how this was written. This is not an accusation; you can request a review.","model_score":0.1635,"status":"decided","style_score":0.6201,"timestamp":"2026-11-03T09:49:32+00:00"},
  {"combined_score":0.3423,"confidence":0.3154,"content_id":"78f76835-25d0-4c1f-b700-9b1038255caa","creator_id":"attacker_EV05","guess":"human","label":"This writing looks more like human writing to our checks. This is an estimate, not proof of who wrote it.","model_score":0.3212,"status":"decided","style_score":0.3635,"timestamp":"2026-11-03T09:49:33+00:00"},
  {"combined_score":0.6828,"confidence":0.3656,"content_id":"30f41acf-1a7d-4ef3-92a7-fd681f37ae19","creator_id":"attacker_FP02","guess":"ai","label":"Our checks found patterns that can appear in AI-generated writing. People can write this way too; you can request a review.","model_score":0.7387,"status":"decided","style_score":0.6269,"timestamp":"2026-11-03T09:49:35+00:00"},
  {"combined_score":0.6913,"confidence":0.3826,"content_id":"02df4f28-e0f0-489a-9ee8-656f587d904a","creator_id":"attacker_FP03","guess":"ai","label":"Our checks found patterns that can appear in AI-generated writing. People can write this way too; you can request a review.","model_score":0.8051,"status":"decided","style_score":0.5774,"timestamp":"2026-11-03T09:49:35+00:00"},
  {"combined_score":0.7154,"confidence":0.4308,"content_id":"380f7ebe-de54-4246-bcf0-c444682b65de","creator_id":"attacker_FP05","guess":"ai","label":"Our checks found patterns that can appear in AI-generated writing. People can write this way too; you can request a review.","model_score":0.8005,"status":"decided","style_score":0.6303,"timestamp":"2026-11-03T09:49:36+00:00"},
  {"combined_score":0.657,"confidence":0.314,"content_id":"d011a12b-381e-4c04-bd01-493bcbf984bd","creator_id":"attacker_FP07","guess":"ai","label":"Our checks found patterns that can appear in AI-generated writing. People can write this way too; you can request a review.","model_score":0.8816,"status":"decided","style_score":0.4323,"timestamp":"2026-11-03T09:49:36+00:00"},
  {"combined_score":0.2602,"confidence":0.4796,"content_id":"632378bb-704f-4e2e-88e3-71f0102b4a88","creator_id":"attacker_PI02","guess":"human","label":"This writing looks more like human writing to our checks. This is an estimate, not proof of who wrote it.","model_score":0.2044,"status":"decided","style_score":0.316,"timestamp":"2026-11-03T09:49:37+00:00"},
  {"combined_score":0.5,"confidence":0.0,"content_id":"9030d9a7-966f-435c-b471-b529cee5c9f9","creator_id":"attacker_MF03","guess":"unsure","label":"Our checks cannot reliably tell how this was written. This is not an accusation; you can request a review.","model_score":0.0,"status":"decided","style_score":0.5,"timestamp":"2026-11-03T09:49:39+00:00"},
  {"combined_score":0.2556,"confidence":0.4888,"content_id":"967b63b9-10a0-4bff-9555-9f1520e82123","creator_id":"attacker_MF04","guess":"human","label":"This writing looks more like human writing to our checks. This is an estimate, not proof of who wrote it.","model_score":0.0112,"status":"decided","style_score":0.5,"timestamp":"2026-11-03T09:49:39+00:00"},
  {"creator_id":"attacker_flood","event":"rejected","limit":"10 per 1 minute","reason":"rate_limited","route":"/submit","status":"rejected","timestamp":"2026-11-03T09:49:41+00:00"}
]
```

### Every broken staff attack: stage and mechanism

These diagnoses are AI-assisted and grounded in the recorded scores and
`app.py::submit`, `detector.py::model_signal`, `stylometry.py::style_signal`,
`scoring.py::combine_signals`, and `scoring.py::score_to_label`.

| Attack | Stage and mechanism |
|---|---|
| EV01 | **Signal one and combining rule:** model 0.1635 averages with style 0.6201 to 0.3918, below the AI band. The typo text and the unquoted EV03 reference prefix have identical measured spread 0.1607, variety 0.8706, punctuation 0.0192, and style 0.6201. The claimed increase in variety did not occur; low model evidence, not a changed style score, drives this evasion. |
| EV02 | **Signal two:** inserted one-word sentences raise spread to 0.8492; style falls to 0.2827 from the reference prefix's 0.6201. Averaging with model 0.5943 gives 0.4385, `unsure`. |
| EV03 | **Signal two and combining rule:** the quotation raises spread to 0.4434 and lowers style to 0.4668. Even model 0.6662, above the AI threshold, averages down to 0.5665, `unsure`. |
| EV04 | **Signal one and label mapping:** unusual-word prose yields model 0.6114 and style 0.6096. Both are below 0.65; the mean 0.6105 remains outside the AI band. No matched model-score comparison proves the amount of perplexity change. |
| EV05 | **Both signals and label mapping:** conversational fragments produce spread 0.6753 and style 0.3635; model is 0.3212. Their mean 0.3423 is inside the original human band. Moving it to uncertainty would still leave this broad AI-evasion objective broken. |
| EV06 | **Signal two:** spread 1.1859 saturates the regularity penalty, producing style 0.2459. With model 0.5727 the mean is 0.4093, `unsure`. |
| EV07 | **Signal two's evidence gate:** semicolons do not split sentences in this implementation. The single-sentence text gets neutral style 0.5, not a full punctuation-based assessment; model 0.5862 averages to 0.5431. |
| EV08 | **Signal two's short-text gate and combining rule:** ten words pass the route's three-word minimum but get neutral style 0.5. Model 0.2452 gives mean 0.3726. This is short evidence, not proof of a 400-token truncation bypass. |
| EV09 | **Signal two and combining rule:** the conversational opening raises spread to 0.4675 and gives style 0.4575. Model 0.7042 is AI-like, but their mean 0.5809 is `unsure`. |
| FP02 | **Both signals and label mapping:** formal report wording yields model 0.7387; regular sentence lengths, spread 0.2403, give style 0.6269. Their mean 0.6828 falsely crosses the AI boundary. |
| FP03 | **Signal one and combining rule:** carefully written ordinary sentences score model 0.8051 and style 0.5774. The equal mean 0.6913 falsely reaches `ai`; fluency/predictability is being used as authorship evidence. |
| FP04 | **Signal one and combining rule:** rubric-shaped explanation yields model 0.8329. Style 0.5261 does not counterbalance it enough; mean 0.6795 becomes `ai`. |
| FP05 | **Both signals:** repeated technical wording has variety 0.5857 and style 0.6303; model 0.8005 gives mean 0.7154. A predictable documentation register is mistaken for AI provenance. |
| FP06 | **Signal one and disagreement guard:** template wording yields model 0.8814 despite style 0.4718. Their difference 0.4096 does not activate the 0.50 guard; mean 0.6766 becomes `ai`. |
| FP07 | **Signal one and label mapping:** deliberate repetition yields model 0.8816. Style 0.4323 is comparatively human-like but their difference 0.4493 misses the guard; mean 0.6570 just crosses 0.65. |
| PI02 | **Signal one and label mapping:** instruction-shaped text scores 0.2044 model / 0.3160 style, giving 0.2602 and the requested `human` output. Scoring was not bypassed: confidence is 0.4796, not the requested 0.02, and a genuine decision was logged. BROKE describes the partial label outcome, not instruction execution. |
| MF03 | **Route and combining rule:** three whitespace chunks let mixed control characters reach inference. Model 0 and neutral style 0.5 trigger the disagreement guard at exactly 0.50, yielding a logged `unsure` decision instead of rejecting unsuitable text. |
| MF04 | **Route and signal two's evidence gate:** eight punctuation chunks pass the whitespace-word minimum despite having no lexical words. Neutral style 0.5 and model 0.0112 yield 0.2556 and a successful decision on non-writing. |

**Pattern:** nine AI evasions fall outside the AI band, while six of eight
staff-designated human cases enter it. Ordinary register and surface shape
are poor provenance evidence. Separate route permissiveness explains the
two junk-text successes; they are not prompt-injection execution.
PI04's label remains fixed and PI05 creates only the genuine computed audit
entry, so those concrete injection targets are HELD.

### Worst staff outcome: FP03

I would least want to explain an AI accusation against the staff-designated
careful non-native writer. This is more consequential than the earlier
supplemental typo evasion. The designation comes from the supplied staff
family, not independently verified personal authorship.

```text
I want to describe my experience of the first month in this country. The weather was very different from my home. I did not expect the rain to continue for so many days. My colleagues were kind and they helped me to find an apartment. I am still learning the words that people use in the office. Sometimes I do not understand the jokes. But I am happy that I came here and I think it was a good decision for my family.
```

Actual response from `app.py::submit`:

```json
{"combined_score":0.6913,"confidence":0.3826,"content_id":"02df4f28-e0f0-489a-9ee8-656f587d904a","guess":"ai","label":"Our checks found patterns that can appear in AI-generated writing. People can write this way too; you can request a review.","model_score":0.8051,"status":"decided","style_score":0.5774}
```

Three candidate causes at different stages are route input corruption,
predictability/style being mistaken for authorship, and an overly aggressive
label boundary. The recorded signals and the actual equal mean show that the
combining/label stages convert these surface heuristics into the accusation;
there is no evidence of a route corruption. This is not a 38% probability
of AI authorship: confidence records score extremity.

**The one improvement to measure:** reapply the already selected human
threshold change, **0.35 to 0.20**, without adding a second scoring or
validation fix. Staff EV05 (0.3423) and PI02 (0.2602) should move to `unsure`.
That can help the explicit human-output objective, but cannot fix broad
AI evasion or the six false accusations because the AI boundary stays 0.65.
The narrower human band also creates more uncertainty for genuine writers.

## What's Still Broken

**Remaining local evasion mechanisms:** EV02's irregular narrative and
EV05's typo-edited version score below even the narrowed human boundary.
For EV02 I would add provenance evidence and a held-out authorship evaluation
rather than equate predictable style with authorship. For EV05 I would first
compare original versus normalized-text model scores on held-out edits,
including genuine human misspellings; simply correcting spelling might
introduce different false positives. Neither is changed in this experiment
because the milestone deliberately allows one measured improvement.

**Criteria:** the five existing reference targets pass in every measured
before and after trial, but they do not test human false accusations or
realistic authorship accuracy. Four local AI-human mislabels before and two
remaining afterward expose that gap. Original student
writing and the staff false-positive family are still needed; synthetic AI
imitations cannot substitute for them. Thresholds and style normalization are
not statistically calibrated.

**Operational limits:** a caller can rotate unauthenticated creator IDs.
A deployment would need authenticated ownership, shared limiter storage and
appropriate IP/global protection; these are not silently added to this local,
single-process experiment. The cold-model flood crossed a fixed-window expiry,
and restarts erase counters, so production tests must include latency and
multi-process behavior rather than treat the warm burst as sufficient.

The local demo has no authentication, ownership checks, reviewer interface,
or automated review worker. `/log` exposes audit metadata and appeal reasoning
to anyone who can access the service. Keep it on loopback and do not use
sensitive text or identifying creator IDs. Model failures and slow inference
also require operational handling before any real deployment.

**The production trade:** I would favor uncertainty and human review over
automatic accusations, allowing more AI writing through rather than punish
writers for an unsupported estimate. Reviewers and recipients bear the
extra review/evasion cost; with the narrower human band, some real writers
also wait for clarification instead of receiving a reassuring human-like label.

## Submission status

**Final local verification:** all 21 regression tests pass with the default
limiter configuration and again with explicit `AI201_RATE_LIMITS=0`;
Python compilation and `git diff --check` pass. Live evidence covers 29
supplemental attacks in each configuration and five criteria with three
trials before and three after. Every after attack matches its audit event,
all corresponding scores and HTTP statuses are unchanged, and all changed
labels follow the single threshold edit. The attack CSVs and `criteria.md`
remain unchanged. The temporary test server was stopped after verification.

Local milestone work and measured evidence are committed in this existing
repository, without rewriting its inherited history. The repository URL
remains `https://github.com/tommytimmytony/ai201-project4-provenance-guard-starter-v2026`.
No remote push or course submission is claimed.

**Not a complete staff-set submission:** the TF's two attack CSVs and genuine
student writing were not supplied. The full required staff before/after
attack runs remain blocked; the local experiment and five reference criteria
do not replace those missing inputs. Supply the staff folder, run both
measured configurations against it, diagnose each broken staff attack, and
include that evidence before submitting the same URL.
