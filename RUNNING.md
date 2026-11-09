# Running Provenance Guard

Everything about how the starter works.

## Completed local implementation

From PowerShell in this project directory:

```powershell
.\.venv\Scripts\python.exe -m unittest test_service -v
$env:AI201_DEBUG = "0"
$env:AI201_RATE_LIMITS = "0"  # The Unit 7 run_demo.py sequence assumes limiting is off.
.\.venv\Scripts\python.exe app.py
```

In a second terminal:

```powershell
.\.venv\Scripts\python.exe run_demo.py
.\.venv\Scripts\python.exe run_eval.py --label local
```

`run_demo.py` is the earlier Unit 7 demonstration and assumes rate limiting
is off (`AI201_RATE_LIMITS=0` on its server). For the current limiter-enabled
milestones, use `run_eval.py` below instead.
`run_demo.py` exercises real GPT-2 inference, all three labels, appeals, and
invalid/oversized requests across three trials. It records JSON evidence in
`results`. Its AI-authored passages are calibration cases, not an accuracy
dataset. `test_service.py` is the offline regression suite and mocks inference.
See the README for the endpoint contracts and scoring rule.

## Unit 8 evaluation

The limiter is now enabled by default at 10/minute and 200/day. Start the
service with debug off; the evidence in this repository used loopback port
5018 so it could not interfere with another project on port 5000:

```powershell
$env:AI201_DEBUG = "0"
$env:AI201_RATE_LIMITS = "1"
$env:PORT = "5018"
.\.venv\Scripts\python.exe app.py
```

In another terminal:

```powershell
.\.venv\Scripts\python.exe -m unittest test_service test_evaluation -v
.\.venv\Scripts\python.exe -c "import requests; r=requests.post('http://127.0.0.1:5018/submit',json={'text':'three valid words','creator_id':'model_warmup'},timeout=300); r.raise_for_status()"
.\.venv\Scripts\python.exe run_attacks.py --flood 15 --creator fresh_flood --url http://127.0.0.1:5018 --timeout 300
.\.venv\Scripts\python.exe run_attacks.py --set staff_attacks --label staff_after --url http://127.0.0.1:5018 --timeout 300
.\.venv\Scripts\python.exe run_eval.py --label staff_after --url http://127.0.0.1:5018 --timeout 300
```

The current human threshold is 0.20. To reproduce the retained before
configuration, temporarily set `HUMAN_THRESHOLD = 0.35` in `config.py`,
restart and warm the server, then run with `--label staff_before`. Restore 0.20
and restart before the after run. `--label` names evidence files; it does
not change the detector configuration. Use a new flood creator on each
repeat or restart to reset its quota.

`staff_attacks` holds the supplied course CSVs copied unchanged from
`Downloads\attack_set\attack_set`. Their hashes and fixed judgment rules are
recorded in that folder; `.gitattributes` prevents newline conversion.
`local_attacks` remains the earlier AI-authored supplemental set, not the
staff set. Staff false-positive judgments use the family's intended ground
truth; they do not establish independently verified real-world accuracy.

`scenarios.py` executes all five unchanged reference criteria, including
appeals, all invalid-input variants, and both size limits. It waits 65 seconds
before and between invalid-input trials so anonymous requests do not exhaust
their shared IP quota and replace the route statuses being measured. Do not
send other requests to the same service during an evaluation; the log checks
compare the exact entries appended during each trial.

Runners produce paired Markdown and JSON evidence with unique timestamps.
For a controlled after run, restart the service to reset its in-memory
limiter, warm GPT-2 with a separate creator, then run the identical commands
with `--label staff_after`. Do not clear the append-only audit history.

This is a **web service**. It runs on your machine and you talk to it with
`curl` from another terminal. If you've not built a backend before, that's
assumed — the starter ships one that already answers.

---

## Before your first class

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python test.py
```

**You're ready when `python test.py` passes.**

You'll see `[WARN] Detector model — not downloaded yet`:

```bash
python detector.py
```

That downloads about 550 MB and scores a sample.

> **No API key for this pair.** Nothing here calls a hosted service. The model
> that reads your text runs on your own laptop.

---

## Your first five minutes

Two terminals. In the first:

```bash
python app.py
```

In the second:

```bash
curl -X POST http://127.0.0.1:5000/ping \
  -H "Content-Type: application/json" \
  -d '{"message": "hello"}'
```

You should get JSON back. That's the whole idea of a web service — something
sent it data, it sent something back.

> **On Windows, use `curl.exe` and keep it on one line.**
>
> In PowerShell, `curl` is an alias for a different tool and the command above
> fails with `Cannot bind parameter 'Headers'` before it ever reaches your
> service. The `\` line breaks don't work there either. This does:
>
> ```powershell
> curl.exe -X POST http://127.0.0.1:5000/ping -H "Content-Type: application/json" -d '{\"message\": \"hello\"}'
> ```
>
> Every `curl` command in this file and in the brief works the same way: swap
> `curl` for `curl.exe` and put it on one line. Git Bash needs no change.

**Leave `/ping` alone.** It's your control. When something breaks later, check
`/ping` still answers: if it does, the problem is in your handler; if it
doesn't, it's the service itself, and that's a help-channel question.

Then try the route you're going to build:

```bash
curl -X POST http://127.0.0.1:5000/submit \
  -H "Content-Type: application/json" \
  -d '{"text": "some writing to score", "creator_id": "me"}'
```

The completed implementation returns a scored decision for valid input.
Use at least three words and a nonblank `creator_id`; the first request may
take longer while GPT-2 downloads and loads.

---

## The routes

| Route | State | What it does |
|---|---|---|
| `POST /ping` | **works** | The example. Don't edit it |
| `GET /health` | **works** | Is the service up, is the model loaded |
| `GET /log` | **works** | The audit log, as JSON |
| `POST /submit` | **works** | Validate, score, label, and log |
| `POST /appeal` | **works** | Record review of a known submission |

---

## Every command

| Command | What it does |
|---|---|
| `python test.py` | Checks your environment |
| `python app.py` | Runs the service |
| `python detector.py` | Downloads the model and scores a sample — **run before class** |
| `python detector.py "some text"` | Score one piece of text from the terminal |
| `python stylometry.py "some text"` | Style measures, on one piece of text |
| `python -m unittest test_service -v` | Offline regression tests; inference mocked |
| `python run_demo.py` | Real HTTP calibration and appeal/validation evidence |
| `python run_attacks.py --set <folder>` | The attack set — **unit 8** |
| `python run_attacks.py --flood 15` | Push past your rate limit and print the status codes — **unit 8** |
| `python run_eval.py --label before` | Your five criteria, three trials — **unit 8** |

---

## Which piece goes with which milestone

### Unit 7 — the build

| Milestone | What you're doing | Where |
|---|---|---|
| 1 | Trace a submission on paper | Nothing to run |
| 2 | Write your criteria | `criteria.md` — all five are yours |
| 3 | The route, one signal, the log | `app.py::submit`, `detector.py`, `audit.py` |
| 4 | Second signal, combine, score | `stylometry.py`, `scoring.py::combine_signals` |
| 5 | Labels and the appeal path | `scoring.py::score_to_label`, `app.py::appeal` |
| 6 | Write it up | `README.md` |

### Unit 8 — the test

| Milestone | What you're doing | Where |
|---|---|---|
| 1 | Rate limiting and the full log | `config.py`, the decorator in `app.py` |
| 2 | Run the attack set | `run_attacks.py` |
| 3 | Run your own criteria | `scenarios.py`, `run_eval.py` |
| 4 | Verdicts and diagnoses | `README.md` |
| 5 | Fix one thing, re-run | `run_attacks.py --label after` |
| 6 | What's still broken | `README.md` |

---

## Building `/submit` in three passes

The ordering is deliberate. It's how you tell a broken route from a broken
signal.

**Milestone 3.** Return a hardcoded response. Confirm `curl` gets it back
**before** you add any logic. Then pull `text` and `creator_id` out. Then call
one signal. Then log it.

**Milestone 4.** Add the second signal. Combine them. Log both scores.

**Milestone 5.** Turn the score into a label.

> Test each signal from a terminal on its own before wiring it in. If you skip
> that you'll spend an hour not knowing whether the route or the signal is
> lying to you.

---

## Turning on rate limiting (unit 8)

Three steps:

1. In `config.py`, set `RATE_LIMITING_ENABLED = True` — or run with
   `AI201_RATE_LIMITS=1`.
2. Choose your numbers there.
3. The `@limiter.limit(...)` decorator is already enabled in `app.py`.

Then push past your limit and watch for `429`:

```bash
python run_attacks.py --flood 15
```

That sends 15 submissions from one `creator_id` and prints the run of status
codes — `200 200 200 ... 429 429` — which is exactly what your README's **Rate
Limiting** section asks you to paste. It also writes `results/flood_<date>.md`.

Most supplied attack rows use distinct `creator_id` values and therefore do
not exercise one caller's quota. The `flood_same_creator` rows are the
exception: the supplied file contains twelve shared-creator submissions,
which produced ten 200s and two logged 429s in each measured phase. Keep the
separate 15-request flood as the Rate Limiting section's explicit check.

No `429` at all? Either your limit is above 15 a minute, or rate limiting is
still off. `GET /health` reports which.

Rejections are logged for you. **An attack that shows up only as an absence is
one you'll never find** — a thousand requests that got a `429` and left no
trace look exactly like a quiet afternoon.

---

## Capstone Path A — hosted container

The capstone uses a Linux container because the service needs both PyTorch and
the roughly 550 MB GPT-2 model. The course's 512 MB free tier is too small;
choose a host with at least 2 GB of memory and confirm the actual peak after a
real submission. The model is downloaded while the image is built so an
ephemeral instance does not download it every time it starts.

The current deployment is:

- URL: `https://ca-provenance-guard.wonderfulground-5f32bf09.westus2.azurecontainerapps.io`
- Subscription: `Visual Studio Enterprise Subscription`
- Resource group: `rg-ai201-provenance-guard`
- Registry: `pgacr77fa7a25.azurecr.io`
- Container Apps environment: `cae-ai201-provenance`
- Container App: `ca-provenance-guard`
- Allocation: 1 vCPU, 2 GiB memory, zero to one replica

Use the isolated Azure CLI profile whenever inspecting or updating it:

```powershell
$env:AZURE_CONFIG_DIR = "$HOME\.azure-capstone"
az account set --subscription "Visual Studio Enterprise Subscription"
az containerapp show `
  --name ca-provenance-guard `
  --resource-group rg-ai201-provenance-guard `
  --query "{url:properties.configuration.ingress.fqdn,state:properties.runningStatus}"
```

The deployed image was built from this repository without local Docker:

```powershell
az acr build `
  --registry pgacr77fa7a25 `
  --image provenance-guard:capstone-a69c610 `
  --file Dockerfile `
  .
```

The hosted log token is generated randomly, stored outside the repository, and
configured as the Container App secret `log-access-token`. Never paste its
value into this file or commit it.

The container has one start command:

```bash
gunicorn --config gunicorn.conf.py app:app
```

The supplied `Dockerfile` runs that command automatically. A local container
smoke test, on a machine with Docker, is:

```powershell
docker build -t provenance-guard .
docker run --rm -p 8000:8000 `
  -e PORT=8000 `
  -e AI201_LOG_ACCESS_TOKEN=replace-with-a-random-secret `
  provenance-guard
```

Then check the public-safe route:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Every host must set these values:

| Variable | Required value | Purpose |
|---|---|---|
| `PORT` | The port assigned by the host | Gunicorn listens on the expected port |
| `HOST` | `0.0.0.0` | Marks the service as hosted and turns off debug mode |
| `AI201_LOG_ACCESS_TOKEN` | A random secret | Protects `/log` and `/operations` |
| `AI201_LOG_STDOUT` | `1` | Copies structured request records to platform logs |

`/operations` returns the same privacy-preserving request records written to
`logs/requests.jsonl`. It requires the bearer token:

```powershell
$headers = @{ Authorization = "Bearer $env:AI201_LOG_ACCESS_TOKEN" }
Invoke-RestMethod "https://YOUR-HOST/operations?limit=10" -Headers $headers
```

Do not submit private writing or identifying creator IDs. The request log
stores field names, character/word counts, outcome, status code, model-load
state, and duration; it deliberately does not store submitted text or appeal
reasoning.

### Host evidence still required

After choosing and authorizing a host, replace `https://YOUR-HOST` with the
real URL and record:

1. The hosting platform and memory tier.
2. A successful `/health` response.
3. At least ten `/operations` entries from synthetic requests.
4. The measured hosting charge and/or request compute seconds.
5. Whether each latency measurement is a cold or warm request.

Run all five committed capstone criteria with:

```powershell
$env:CAPSTONE_BASE_URL = "https://YOUR-HOST"
$env:CAPSTONE_LOG_TOKEN = $env:AI201_LOG_ACCESS_TOKEN
.\.venv\Scripts\python.exe run_capstone.py
```

The runner executes three trials per criterion and writes a timestamped
Markdown record under `results\`. Its first HTTP request is the first latency
trial, so the criterion includes the host's initial response as written.

---

## Where everything lives

| File | What it does |
|---|---|
| `config.py` | Every setting: thresholds, weights, rate limits, the model |
| `app.py` | The service. `/ping` and `/log` work; `/submit` and `/appeal` are yours |
| `detector.py` | Signal one — the local model. Given to you |
| `stylometry.py` | Signal two. **Stubs — you build these** |
| `scoring.py` | Combining and labelling. **Stubs — you build these** |
| `audit.py` | The audit log writer. Given to you |
| `run_attacks.py` | Runs the attack set — **unit 8** |
| `run_eval.py` | Runs your criteria three times — **unit 8** |
| `scenarios.py` | What your test runs. **You fill this in** |
| `criteria.md` | Your five criteria. **You write all five** |
| `logs/audit.jsonl` | Your audit log. **Commit it** |
| `results/` | Attack runs and run logs. **Commit them** |

---

## The two blind spots, up front

Both signals have one, and unit 8's attack set is built out of them. You have
to name them yourself in Milestone 1 — but knowing they exist now saves you
from being surprised.

**Signal one** measures how *predictable* your text is. Predictability isn't
authorship. What it really rewards is common words in short, ordinary
sentences — someone writing in a second language and staying with vocabulary
they're sure of, a younger writer, anyone writing plainly on purpose. Writing
like that scores about as machine-like as machine writing does. (Dense, ornate
prose often goes the other way and reads as human, because rare words are what
a language model fails to predict.) So the writers this signal is most likely
to accuse are the ones with the least room to argue back. That is the false
positive the whole project is about, and it's structural rather than a bug.

**Signal two** cannot read. It has no idea what the text says. Anything that
changes the shape without changing the substance moves it — typos, broken-up
sentences, a pasted quotation. That is very cheap to do on purpose.

---

## When something goes wrong

| What you see | What it means |
|---|---|
| `501 not_implemented` | Correct at the start — that's the TODO in `app.py` |
| `404` from curl | Is the server running? Is the path exactly what you typed? |
| `Cannot bind parameter 'Headers'` | You're in PowerShell, where `curl` is a different tool. Use `curl.exe`, on one line |
| Request body arrives empty | curl needs `-H "Content-Type: application/json"` |
| `Address already in use` | A server left running from an earlier attempt. Kill it, don't debug it |
| The first submission takes 10+ seconds | Signal one is loading the model into memory. Later ones take a second or two |
| *Every* submission takes 10+ seconds | Something is reloading the model each call. `GET /health` shows `detector_loaded` — if it goes back to `false`, look for a reload in your handler |
| `DetectorUnavailable` | Run `python detector.py` once to download the model |
| `/appeal` seems to do nothing | Does the `content_id` you sent actually exist in the log? A typo there fails silently |
| Every request gets through, no `429` ever | The decorator is uncommented but limiting is still off. Set `RATE_LIMITING_ENABLED` in `config.py` |
| Flask-Limiter warns about storage | Shouldn't happen — `storage_uri` is preconfigured. If you changed it, put it back |
| All three of your labels never appear | Your ranges have a gap. `scoring.label_ranges()` prints them |

If the route won't respond, go back to `/ping`. If that answers, the problem is
in your handler.

---

## A note on committing

At least four new commits in unit 7, four more in unit 8.

`logs/` and `results/` are deliberately **not** in `.gitignore`. Your audit log
is evidence, and the entries you paste into your README are what unit 8 grades.

**Do not delete and recreate this repository.** You submit the same URL both
units.
