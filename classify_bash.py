#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "anthropic[bedrock]>=0.83,<0.84",
# ]
# ///
"""
PreToolUse hook: LLM-based Bash command safety classifier.

Reads the Bash command from stdin, asks Claude to classify it as
'auto_approve' (read-only, non-mutating) or 'escalate' (modifies
state/files/remotes). Auto-approved commands run immediately; escalated
ones fall through to the normal permission system for the human to decide.

Uses tool use (structured output) so the model is forced to return a
valid enum value rather than free text — no accidental substring matches.

Logs all decisions to /tmp/bash_classifier_log.log — tail -f that file to debug.
"""
import json
import sys
import os
from datetime import datetime
from pathlib import Path


LOG_FILE = "/tmp/bash_classifier_log.log"
PROMPT_FILE = Path(__file__).parent / "classify_bash_prompt.md"


def _build_tool() -> dict:
    prompt = PROMPT_FILE.read_text()
    return {
        "name": "classify",
        "description": prompt,
        "input_schema": {
            "type": "object",
            "properties": {
                "decision": {
                    "type": "string",
                    "enum": ["auto_approve", "escalate"],
                },
            },
            "required": ["decision"],
        },
    }


CLASSIFY_TOOL = _build_tool()


def log(command: str, decision: str, raw_response: str | None = None, error: str | None = None):
    timestamp = datetime.now().strftime("%H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {decision}\n")
        f.write(f"  cmd: {command[:120]}\n")
        if raw_response is not None:
            f.write(f"  model: {raw_response!r}\n")
        if error is not None:
            f.write(f"  error: {error}\n")


def main():
    data = json.load(sys.stdin)
    command = data.get("tool_input", {}).get("command", "")

    timestamp = datetime.now().strftime("%H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] CALLED: {command[:120]}\n")

    try:
        import anthropic

        if os.environ.get("CLAUDE_CODE_USE_BEDROCK"):
            client = anthropic.AnthropicBedrock()
        else:
            client = anthropic.Anthropic()
        model = os.environ.get("BASH_CLASSIFIER_MODEL", "claude-opus-4-5")

        response = client.messages.create(
            model=model,
            max_tokens=64,
            tools=[CLASSIFY_TOOL],
            tool_choice={"type": "tool", "name": "classify"},
            messages=[{"role": "user", "content": command}],
        )

        tool_use = next(b for b in response.content if b.type == "tool_use")
        decision = tool_use.input["decision"]

        if decision == "auto_approve":
            log(command, "ALLOW", raw_response=json.dumps(tool_use.input))
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                }
            }))
        else:
            log(command, "ESCALATE", raw_response=json.dumps(tool_use.input))
            # No output → falls through to normal permission system

    except Exception as e:
        # On any error (network, auth, timeout), fall through to default behavior.
        # Never auto-approve on failure.
        log(command, "ERROR", error=str(e))


if __name__ == "__main__":
    main()
