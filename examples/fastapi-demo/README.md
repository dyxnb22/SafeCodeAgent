# FastAPI Demo

This demo shows the local SafeCodeAgent edit, approval, audit, and rollback loop
on a small FastAPI project.

Run from this directory:

```bash
cd examples/fastapi-demo
sac ask "这个项目的入口文件在哪里？"
sac edit "给这个 FastAPI 项目添加 /health 接口"
sac apply
sac history
sac rollback --last
```

Expected behavior:

- `sac edit` previews a patch for `app/main.py` and saves `.sac/pending_patch.json`.
- `sac apply` asks for confirmation before writing.
- `sac history` shows the audit log.
- `sac rollback --last` restores the file from the latest checkpoint.
