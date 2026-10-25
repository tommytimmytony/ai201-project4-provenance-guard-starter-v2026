#!/usr/bin/env python3
"""
Provenance Guard — the web service.

    python app.py

Then, in another terminal:

    curl -X POST http://127.0.0.1:5000/ping \
      -H "Content-Type: application/json" \
      -d '{"message": "hello"}'

That's the example route. It works right now, before you've written anything.
**Leave it alone** — it's your control. When something breaks later, check that
`/ping` still answers: if it does, the problem is in your handler; if it
doesn't, it's the service itself.

Routes:

    POST /ping        the worked example. Already works. Don't edit it
    POST /submit      validate, score, label, and record a submission
    POST /appeal      append an under_review event for a known submission
    GET  /log         the audit log. Already works
    GET  /health      is the service up, and is the model loaded
"""

import uuid

from flask import Flask, jsonify, request

import audit
import config
import detector
import scoring
import stylometry

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = config.MAX_REQUEST_BYTES


def reject(reason, message, status=400, payload=None):
    creator = payload.get("creator_id") if isinstance(payload, dict) else None
    creator = creator.strip() if isinstance(creator, str) else "unknown"
    audit.log_rejection(
        creator_id=creator[:config.MAX_CREATOR_ID_CHARS],
        reason=reason,
        route=request.path,
    )
    return jsonify({"error": reason, "message": message}), status


def json_object():
    if not request.is_json:
        return None, reject("unsupported_media_type", "Send Content-Type: application/json.", 415)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return None, reject("invalid_json", "Send a valid JSON object.")
    return payload, None


@app.errorhandler(413)
def request_too_large(exc):
    return reject("request_too_large", "The request body exceeds 65536 bytes.", 413)


@app.errorhandler(500)
def internal_error(exc):
    return jsonify({
        "error": "internal_error",
        "message": "The request could not be completed. No successful decision is confirmed.",
    }), 500


# ── Rate limiting — UNIT 8 ────────────────────────────────────────────────────
# Off until you turn it on. In unit 8, Milestone 1:
#
#   1. Set RATE_LIMITING_ENABLED = True in config.py (or AI201_RATE_LIMITS=1)
#   2. Choose your numbers there
#   The @limiter.limit(...) line on /submit is already enabled.
#
# While limiting is off, the decorator is a no-op. It produces no 429
# responses until limiting is enabled.
#
# The storage backend is preconfigured, which stops Flask-Limiter printing a
# warning on every start. In-memory is right for one laptop and wrong for
# anything real — a restart forgets every count.

class _LimiterOff:
    """
    Stands in for the real limiter while rate limiting is off.

    It makes @limiter.limit(...) a decorator that returns the route
    untouched, so uncommenting the line before you flip the setting is
    harmless instead of a crash on startup.
    """

    def limit(self, *args, **kwargs):
        return lambda view: view


limiter = _LimiterOff()
if config.RATE_LIMITING_ENABLED:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address

    def rate_limit_key():
        """
        Who a request counts against.

        Falling back to the caller's address is the easy version. Unit 8's
        stretch asks about per-creator limits instead — and the difference
        matters: one script can look like a thousand callers, and one household
        can look like one.
        """
        payload = request.get_json(silent=True)
        # A body that parses as JSON but isn't an object — a bare list or
        # string — has no .get. Without this guard the key function raises
        # BEFORE the route runs, and a malformed request becomes a 500 that
        # looks like your handler crashed when your handler never ran.
        if not isinstance(payload, dict):
            return get_remote_address()
        creator = payload.get("creator_id")
        return creator.strip() if isinstance(creator, str) and creator.strip() else get_remote_address()

    limiter = Limiter(
        key_func=rate_limit_key,
        app=app,
        storage_uri=config.RATE_LIMIT_STORAGE,
        default_limits=[],
    )

    @app.errorhandler(429)
    def rate_limited(exc):
        """
        A rejected request still leaves a trace.

        ⚠️ An attack that shows up only as an absence is one you'll never find.
        """
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            payload = {}
        audit.log_rejection(
            creator_id=payload.get("creator_id", "unknown"),
            reason="rate_limited",
            limit=str(exc.description),
        )
        return jsonify({
            "error": "rate_limited",
            "message": "Too many submissions. Try again shortly.",
            "limit": str(exc.description),
        }), 429


# ── The worked example. Already works. Don't edit. ────────────────────────────

@app.post("/ping")
def ping():
    """
    Everything a route needs, in six lines.

    JSON arrives as a dict. You pull things out of it. You return a dict and
    the framework turns it into a response. That's the whole idea.
    """
    payload = request.get_json(silent=True) or {}
    return jsonify({
        "ok": True,
        "you_sent": payload.get("message"),
        "service": "provenance-guard",
    })


@app.get("/health")
def health():
    """Is the service up, and has the model been downloaded yet?"""
    import detector

    loaded = detector._model is not None
    return jsonify({
        "ok": True,
        "detector_model": config.DETECTOR_MODEL,
        "detector_loaded": loaded,
        "rate_limiting": config.RATE_LIMITING_ENABLED,
        "log_entries": len(audit.read_entries()),
    })


# ── Submission and appeal ────────────────────────────────────────────────────

@app.post("/submit")
@limiter.limit(f"{config.RATE_LIMIT_PER_MINUTE}/minute;{config.RATE_LIMIT_PER_DAY}/day")
def submit():
    """Validate, run both signals, and persist the decision before confirming it."""
    payload, error = json_object()
    if error is not None:
        return error
    text = payload.get("text")
    creator_id = payload.get("creator_id")
    if not isinstance(text, str) or not text.strip():
        return reject("invalid_text", "text must be a nonblank string.", payload=payload)
    if len(text) > config.MAX_TEXT_CHARS:
        return reject("text_too_long", "text must not exceed 10000 characters.", 413, payload)
    if len(text.split()) < 3:
        return reject("text_too_short", "Provide at least three words.", 422, payload)
    if (
        not isinstance(creator_id, str)
        or not creator_id.strip()
        or len(creator_id) > config.MAX_CREATOR_ID_CHARS
    ):
        return reject(
            "invalid_creator_id", "creator_id must be a nonblank string of at most 100 characters.",
            payload=payload,
        )
    try:
        model_score = detector.model_signal(text)
    except detector.DetectorUnavailable:
        app.logger.exception("The local detector could not be loaded.")
        return reject(
            "detector_unavailable", "The local model is unavailable. Check the server log and retry.",
            503, payload,
        )
    except ValueError as exc:
        return reject("unscorable_text", str(exc), 422, payload)
    style_score = stylometry.style_signal(text)
    combined_score = scoring.combine_signals(model_score, style_score)
    guess, label = scoring.score_to_label(combined_score)
    content_id = str(uuid.uuid4())
    confidence = round(abs(2 * combined_score - 1), 4)
    audit.log_decision(
        content_id=content_id,
        creator_id=creator_id.strip(),
        guess=guess,
        model_score=model_score,
        style_score=style_score,
        combined_score=combined_score,
        label=label,
        confidence=confidence,
    )
    return jsonify({
        "content_id": content_id,
        "guess": guess,
        "confidence": confidence,
        "label": label,
        "model_score": model_score,
        "style_score": style_score,
        "combined_score": combined_score,
        "status": "decided",
    })


@app.post("/appeal")
def appeal():
    """Append a review request without overwriting or reassessing the decision."""
    payload, error = json_object()
    if error is not None:
        return error
    content_id = payload.get("content_id")
    reasoning = payload.get("reasoning")
    if not isinstance(content_id, str) or not content_id.strip() or len(content_id) > 100:
        return reject("invalid_content_id", "content_id must be a nonblank string of at most 100 characters.")
    if (
        not isinstance(reasoning, str)
        or not reasoning.strip()
        or len(reasoning) > config.MAX_REASONING_CHARS
    ):
        return reject("invalid_reasoning", "reasoning must be a nonblank string of at most 2000 characters.")
    content_id = content_id.strip()
    decisions = [entry for entry in audit.entries_for(content_id) if entry.get("status") == "decided"]
    if not decisions:
        return reject("content_not_found", "No submission has that content_id.", 404)
    audit.log_appeal(content_id, decisions[0]["creator_id"], reasoning.strip())
    return jsonify({
        "content_id": content_id,
        "status": "under_review",
        "message": "Your request for review has been recorded. No automatic reassessment has occurred.",
    })


# ── Already works ─────────────────────────────────────────────────────────────

@app.get("/log")
def get_log():
    """
    The audit log, most recent last.

        curl "http://127.0.0.1:5000/log?limit=10"

    You need this in unit 8 to paste entries into your README, and you need it
    now to see whether your logging is actually working.
    """
    limit = request.args.get("limit", type=int)
    entries = audit.read_entries(limit=limit)
    return jsonify({"count": len(entries), "entries": entries})


def main():
    print(f"Provenance Guard on http://{config.HOST}:{config.PORT}")
    print(f"  detector model:  {config.DETECTOR_MODEL}")
    print(f"  rate limiting:   {'ON' if config.RATE_LIMITING_ENABLED else 'off (unit 8)'}")
    print(f"  audit log:       {config.AUDIT_LOG}")
    print()
    print("Check it's alive:")
    print(f'  curl -X POST http://{config.HOST}:{config.PORT}/ping \\')
    print('    -H "Content-Type: application/json" \\')
    print("    -d '{\"message\": \"hello\"}'")
    print()
    # debug=True hands out an interactive debugger, so it's local-only — see config.py
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)


if __name__ == "__main__":
    main()
