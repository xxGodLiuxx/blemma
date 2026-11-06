普段は `python blemma.py` で足ります。 / Normally, just run `python blemma.py`.

設定を手で渡したい時 / To pass the settings by hand:

1. この JSON 2 本を任意の場所へ写します。 / Copy both JSON templates anywhere.
2. `<BLEMMA>` を repo の絶対路、`<PY>` を `python -c "import sys; print(sys.executable)"` の出力 (絶対路) に置換します。mac / Linux は `python3 -c …`、Windows は `py -c …` でも構いません (Windows は `.exe`・JSON の路は `/` か `\\` を使う)。`args` の頭の `-I` は消さないでください (環境変数 `PYTHONPATH` の影響で hook が落ちるのを防ぎます)。 / Replace `<BLEMMA>` with the absolute repo path and `<PY>` with the absolute path that command prints (`python3 -c …` on macOS and Linux; `py -c …` also works on Windows. Windows: `.exe`; use `/` or `\\` in JSON paths).
3. repo で `python board/server.py` を起こします (頁が開きます)。別の端末で、自分の作業のフォルダーから `claude --settings <写した先>/settings.blemma.json --mcp-config <写した先>/mcp.blemma.json --permission-mode default` を実行します (デモは `--setting-sources project,local --strict-mcp-config` を追加)。 / Start the board from the repo (it opens the page). In another terminal, from your own project folder, run that Claude command with the paths of your copies (for demos, add those two flags).
