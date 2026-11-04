普段は `python blemma.py` で足ります。 / Normally, just run `python blemma.py`.

1. この JSON 2 本を任意の作業用ディレクトリへ写します。 / Copy both JSON templates to a working directory.
2. `<BLEMMA>` を repo の絶対路、`<PY>` を `python -c "import sys; print(sys.executable)"` の出力に置換します (Windows は `.exe`・JSON の路は `/` か `\\` を使う)。 / Replace `<BLEMMA>` with the absolute repo path and `<PY>` with that command's output (Windows: `.exe`; use `/` or `\\` in JSON paths).
3. repo で `python board/server.py` を起こし、別の端末でコピー先の `claude --settings settings.blemma.json --mcp-config mcp.blemma.json --permission-mode default` を実行します (デモは `--setting-sources project,local --strict-mcp-config` を追加)。 / Start the board from the repo, then run that Claude command from the copies' directory in another terminal (for demos, add those two flags).
