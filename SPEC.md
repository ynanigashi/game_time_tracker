# Game Time Tracker 仕様書

## 目的
- PC でのゲームプレイ開始/終了を記録し、日毎の累積時間を管理する。
- プレイログを Google スプレッドシートへ送信して履歴を残す。
- 手動操作 (タイマー開始/停止) とウィンドウタイトルからの自動検出の両方を提供する。

## システム構成
- `main.py` (手動記録)
  - `ConfigLoader` で設定を読み込み。
  - `LogHandler` でログシートを操作 (利用可否は `use_spreadsheet` で制御)。
  - `GameTimer` で時間計測と残り時間表示を実行。
  - `jp_prompts.json` の文言を使って CLI を表示し、矢印キー/`Ctrl+Space` でゲーム選択と開始/終了を受け付ける。
- `auto_detect_game.py` (自動検出)
  - `pygetwindow` で表示中ウィンドウのタイトルを取得し、ゲーム情報シートの `window_title` と部分一致したものをプレイ中と判定。
  - ブラウザタイトルは `is_browser_game=True` のゲームのみ記録対象。それ以外はブラウザ上の実行を除外。
  - ウィンドウが消失した時点で終了時刻を確定し、5分以上のプレイのみスプレッドシートへ追記。
  - 10秒間隔でポーリングし、除外タイトル (`Program Manager` など) は無視。
- `game_timer.py`
  - 1日の上限時間 (`limit_minutes`) から残り時間を算出し表示。
  - 日付が変わった場合は `state.json` を初期化。
  - 残り時間が半分/0 を切った際に tkinter の警告ダイアログを表示。
  - `Ctrl+Space` でタイマーを停止し、友人とプレイする場合は累積時間に加算しない。
- `log_handler.py`
  - サービスアカウント経由でスプレッドシートを読み書き。
  - ログ行を末尾に追記し、全レコードから直近のタイトルを集計してゲーム選択に利用。
- `config_loader.py`
  - `config.ini` を読み込み、各機能で使う設定 (時間上限、ファイルパス、シートキーなど) を dict にして提供。

## 設定・外部リソース
- `config.ini`
  - `APPLICATIONMANAGER.use_spreadsheet`: スプレッドシート連携のオン/オフ。
  - `GAMETIMER.limit_minutes`: 1日のプレイ上限 (分)。
  - `GAMETIMER.json_file_path`: 累積時間保存ファイル (`state.json`) のパス。
  - `LOGHANDLER.json_file_path`: サービスアカウント JSON のパス。
  - `LOGHANDLER.sheet_key`: ログシートのキー (sheet1 を使用)。
  - `GAMEINFO.sheet_key` / `GAMEINFO.sheet_gid`: ゲーム情報シートのキーと gid。
- スプレッドシート構造
  - **ログシート (sheet1)**: `index,start_time,end_time,title,play_with_friends`
  - **ゲーム情報シート**: `game_title,window_title,play_with_friends,is_browser_game`
    - 真偽値は `"TRUE"` / `"FALSE"` を想定。
- `state.json` (日次ステート)
  ```json
  {
    "start_time": "2024-02-27T21:06:47.741741",
    "elasped_seconds": 1484.108375,
    "half_msg_flag": false,
    "end_msg_flag": false
  }
  ```
  - 日付が変わると初期値に戻る。

## 手動記録フロー (main.py)
1. 起動時に設定とプロンプト文を読み込む。`use_spreadsheet=True` の場合はログシートに接続。
2. Enter で開始案内を表示し、直近のプレイタイトル10件 (+新規追加) から矢印キーで選択。`Ctrl+Space` で決定。
3. 友人とプレイするかを `y/n` で入力。`y` の場合、累積時間に加算せず警告も出さない。
4. Enter でタイマー開始。コンソール上で残り時間/総経過時間を 0.05 秒間隔で更新表示。
5. `Ctrl+Space` が押されると終了時刻を確定。開始・終了時刻をスプレッドシート形式 (`YYYY/MM/DD HH:MM:SS`) に整形し、ログシートへ追記 (use_spreadsheet=True の場合)。
6. プレイ時間や警告フラグを `state.json` に保存して終了。

## 自動検出フロー (auto_detect_game.py)
1. 起動時にゲーム情報シートを読み込み、`game_title/window_title/play_with_friends/is_browser_game` をメモリに保持。
2. 10秒間隔で全ウィンドウのタイトルを取得し、除外リストを外した上で各ゲームの `window_title` が部分一致するか判定。
3. 一致したゲームは `is_playing=True` とし、初回一致時に開始時刻を記録。
4. 一致がなくなった瞬間に終了時刻を記録し、(終了-開始) が5分以上なら `[index, start, end, game_title, play_with_friends]` をログシートへ追記。短い場合は破棄。
5. ブラウザ上のウィンドウは `is_browser_game` が真のゲームのみ記録対象。そうでないゲームはブラウザタイトルを無視。

## 非機能要件・制約
- 想定 OS は Windows (tkinter/keyboard/pygetwindow の挙動に依存)。
- 時刻はローカルタイムで算出し、タイムゾーン変換は行わない。
- キー操作は `Ctrl+Space` 固定。入力が取得できない場合は管理者権限での実行が必要になることがある。
- 自動検出はウィンドウタイトルの部分一致に依存するため、タイトルが頻繁に変化するゲームでは共通する文字列を登録する必要がある。

## 起動エントリ
- 手動計測: `python main.py`
- 自動検出: `python auto_detect_game.py` または `game_time_tracker.bat`

