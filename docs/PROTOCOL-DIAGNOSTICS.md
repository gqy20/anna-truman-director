# Local protocol tracing

Use this only to diagnose the installed Agent path, not as proof that release
acceptance has passed. No additional platform grants are required.

1. Build a diagnostic binary from this source, preserving the installed binary
   for rollback. Do not upload it as an immutable release under an existing tag.
2. Set `TRUMAN_TRACE_DIR` to an absolute local directory in the process launching
   Anna, then restart Anna normally. Do not redirect the Windows Anna launcher
   stdout/stderr: beta.34 has failed at startup with a GBK encoding error in that
   configuration.
3. Confirm `protocol-<pid>.jsonl` contains `ready` and handshake entries from the
   actual Anna child process. Without this positive check, absence of invoke
   entries is inconclusive.
4. Through the installed App, invoke the read-only `list_scenarios` control and
   `get_snapshot`. Record platform RPC IDs and times separately; the plugin's
   stdio request IDs are hashed and may differ from platform IDs.
5. Interpret stages: `stdin_received` proves bytes reached the plugin;
   `invoke_enter` proves its coroutine started; `response_*_flushed` proves the
   response was flushed into the host pipe, not that the host consumed it;
   `invoke_exit` records elapsed time. `stdin_received` without a method can be
   a reverse-RPC response. No payloads or credentials are written.
6. Restore the preserved binary, unset `TRUMAN_TRACE_DIR`, and restart Anna when
   finished. Logs are local only and not automatically deleted or uploaded.

Each process uses a separate UTF-8 file, rotating at 1 MB with two backups.
Actions/methods are allow-listed; unknown names are recorded as `other`.
