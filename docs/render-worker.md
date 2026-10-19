# Render worker protocol

`video/scripts/render-worker.ts` is the only way the agent renders. Run it as
`node node_modules/tsx/dist/cli.mjs video/scripts/render-worker.ts` (no shell — the repo path may
contain spaces), write ONE JSON request to stdin, read JSON lines from stdout. Logs go to stderr.

## Requests

```jsonc
// layout check only (same fitText/BOXES as the templates)
{"cmd": "check", "spec": {...}, "limits": {"minTotalS": 30}}

// render
{
  "cmd": "render",
  "spec": {...},                 // VideoSpec (agent/schemas/video_spec.py)
  "preset": "preview",           // preview: 540x960 @ 15 fps, final: 1080x1920 @ 30 fps
  "out_dir": "C:/.../versions/v3/preview",
  "media_root": "C:/.../project", // relative audio.src paths resolve here (served over local http)
  "concurrency": 8,              // default min(8, cpus - 1)
  "timeout_s": 600,              // hard timeout -> error "timeout", exit 3
  "name": "video",               // output basename
  "limits": {}                   // optional duration-limit overrides (tests)
}
```

## Events

| type | fields |
|---|---|
| `progress` | `stage` (`validate`, `bundle`, `render`, `encode`, `post`), `elapsedMs`, and for render/encode `renderedFrames`, `encodedFrames`, `totalFrames`, `stageMs`; bundle has `percent` |
| `check` | `ok`, `issues[]` (`scene_id`, `field`, `index?`, `code`, `message`) |
| `done` | `mp4`, `srt`, `vtt`, `quiz`, `meta`, `durationMs`, `totalFrames`, `stages` (`validate_ms`, `bundle_ms`, `render_ms`, `encode_ms`, `post_ms`), `probe`, `checks[]`, `cacheHits.bundle` |
| `error` | `code` (`bad_request`, `invalid_spec`, `layout_check_failed`, `timeout`, `render_failed`), `message`, `issues?` |

Exit codes: 0 ok, 1 render failed or a post-render check failed, 2 bad request/spec, 3 timeout.

## Measured speed (dev laptop: i5-13450HX, 16 threads, 16 GB; `npm run bench -w video`)

| preset | video | frames | wall | render fps | realtime |
|---|---|---|---|---|---|
| preview 540x960 @ 15 | 56.5 s | 848 | 19–22 s (bundle cache hit / miss) | ~98 | ×2.6 |
| final 1080x1920 @ 30 | 56.5 s | 1695 | 47.9 s | ~59 | ×1.2 |

Remotion only encodes in parallel with rendering when free RAM exceeds its estimate + 2 GB; with
~4 GB free (typical here) the final encode runs after rendering. More RAM → faster finals.
