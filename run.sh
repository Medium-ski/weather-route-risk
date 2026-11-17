#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
if ! .venv/bin/python -c 'import fastapi, uvicorn, httpx, yaml' >/dev/null 2>&1; then
  echo '首次启动：正在安装 Python 依赖（需要联网）...'
  .venv/bin/python -m pip install -r requirements.txt
fi
printf '请在浏览器打开 http://localhost:8000\n'
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
