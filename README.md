# claude-bash-classifier

A [Claude Code](https://claude.ai/code) `PreToolUse` hook that uses an LLM to classify Bash commands as
**auto-approve** (read-only, safe) or **escalate** (potentially destructive, prompts the human).

Solves approval fatigue: instead of maintaining a long allow-list of patterns that Claude inevitably
works around with complex pipelines, the model reads the actual command and decides.

```
[14:32:01] ALLOW   cmd: git log --oneline -20         model: '{"decision": "auto_approve"}'
[14:32:08] ALLOW   cmd: cat file.json | jq '.[] | ...'  model: '{"decision": "auto_approve"}'
[14:32:15] ESCALATE cmd: rm -rf /tmp/old_build         model: '{"decision": "escalate"}'
```

## How it works

- Fires before every `Bash` tool call via the `PreToolUse` hook
- Sends the command to an LLM using a structured tool call (enum output, no substring parsing)
- `auto_approve` → returns `permissionDecision: allow` to Claude Code, command runs immediately
- `escalate` → returns nothing, falls through to Claude Code's normal permission system
- All decisions are logged to `/tmp/claude_hook.log` for debugging (`tail -f` it live)

The prompt lives in `classify_bash_prompt.md` — edit it to tune the classifier's judgment.

## Installation

### 1. Copy the files

Place `classify_bash.py` and `classify_bash_prompt.md` somewhere stable, e.g. `.claude/hooks/`.

### 2. Add the hook to `.claude/settings.json`

#### With `uv` (recommended — handles the dependency automatically)

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "uv run \"$CLAUDE_PROJECT_DIR/.claude/hooks/classify_bash.py\"",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

#### Without `uv`

Install the dependency once:

```sh
pip install 'anthropic[bedrock]>=0.83,<0.84'
```

Then reference the script directly:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python \"$CLAUDE_PROJECT_DIR/.claude/hooks/classify_bash.py\"",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

## Configuration

All configuration is through environment variables, set in the `env` block of `.claude/settings.json`:

| Variable | Default | Description |
|---|---|---|
| `BASH_CLASSIFIER_MODEL` | `claude-opus-4-5` | Model used for classification |
| `CLAUDE_CODE_USE_BEDROCK` | _(unset)_ | Set to `"1"` to use AWS Bedrock instead of the direct API |
| `AWS_REGION` | _(unset)_ | Required when using Bedrock |

Example for Bedrock users:

```json
{
  "env": {
    "CLAUDE_CODE_USE_BEDROCK": "1",
    "AWS_REGION": "us-west-2",
    "BASH_CLASSIFIER_MODEL": "us.anthropic.claude-opus-4-6-v1"
  }
}
```

For the direct API, just set `ANTHROPIC_API_KEY` in your environment — no extra config needed.

## Debugging

Watch decisions in real time:

```sh
tail -f /tmp/claude_hook.log
```

Each entry shows the timestamp, decision, command (truncated to 120 chars), and raw model output.
