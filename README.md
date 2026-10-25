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

Optional, off by default for Unit 7. Set `$env:AI201_RATE_LIMITS = "1"` before
starting the server to enable **10/minute and 200/day** on `/submit`.
These demonstration limits allow occasional drafting while throttling repeated
probing from one claimed creator. The key uses trimmed `creator_id` with an
IP fallback; it is not authenticated and can be rotated. Storage is in memory.

The offline regression test checks 10 successful requests followed by five
429 responses and matching rejection entries. A live Unit 8 flood run has not
been recorded; do not present the mocked test as that evidence.

## Attack Run - Before / The Improvement / Attack Run - After

The course attack set was not supplied. No full attack run or before/after
improvement experiment is claimed. The implementation and runners are ready
for that separate Unit 8 exercise.

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
