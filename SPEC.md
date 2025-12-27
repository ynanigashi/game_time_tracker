# Game Time Tracker 仕様書

## 目的
Windows PC で実行中のゲームをウィンドウタイトルから自動検出し、プレイ時間を Google スプレッドシートに記録するツール。

## システム構成
- **[main.py](main.py)** (自動検出・ログ記録)
  - `GameMonitor` がメインループを管理し、ポーリング間隔/最小記録時間を定数または引数で変更可能。
  - `pygetwindow` でアクティブウィンドウのタイトルを取得。
  - ゲーム情報シートから登録されたゲームを読み込み、部分一致で検出。
  - ブラウザタイトルは `is_browser_game=True` のゲームのみ記録対象。
  - 1秒間隔でポーリング。ウィンドウ消失時に終了時刻を確定。
  - 5分以上のプレイのみスプレッドシートへ追記。

- **[gui.py](gui.py)** (PySide6 GUI)
  - ステータスをタイトルバーに表示し、左クリックで表示モード切替（max/mid/min）。
  - ウィンドウ検出は1秒間隔、UI更新は0.1秒間隔。
  - 位置・サイズ・モードを `window_state.txt` に保存/復元。
  - `WindowState` クラス: 静的メソッドのみのシンプルなユーティリティクラス（`load()`/`save()`）。
  - `MainWindow`: ウィジェット参照を `self.w` に統合、タイマー初期化ヘルパー `_start_timer()` で簡潔化。
  - 状態管理の二重化を解消し、約30行のコード削減を実現。
  - **今日プレイしたゲーム一覧表示**（mid/maxモード）:
    - その日にプレイしたゲームとプレイ時間（分数）を表示
    - プレイ時間の長い順にソート
    - スプレッドシートへのアクセスは起動時とゲーム記録時のみ（キャッシュを活用）
    - UI更新時は差分更新により、ちらつきを防止

- **[gui_layout.py](gui_layout.py)**
  - GUI ウィジェットとレイアウトの構築。各ウィジェットのデフォルト高さを保持。
  
- **[log_handler.py](log_handler.py)**
  - サービスアカウント経由でスプレッドシートを操作。
  - ログ行を末尾に追記。
  - ゲーム情報シートから登録されたゲーム一覧を取得。

- **[config_loader.py](config_loader.py)**
  - `config.ini` を読み込み。
  - スプレッドシートキー、ゲーム情報シートの gid、サービスアカウント JSON パスを提供。

## 設定・外部リソース
- **[config.ini](config.ini)**
  ```ini
  [LOGHANDLER]
  json_file_path = service_account.json    ; サービスアカウント JSON のパス
  sheet_key = <スプレッドシートキー>        ; ログシートのキー

  [GAMEINFO]
  sheet_key = <スプレッドシートキー>        ; ゲーム情報シートのキー
  sheet_gid = 1198224769                   ; ゲーム情報シートの gid

  [WINDOW_SCAN]
  browsers = Google Chrome, Microsoft Edge, Mozilla Firefox, Opera, Brave, Vivaldi, Safari
  exclude_titles = Program Manager, Settings, 設定, NVIDIA GeForce Overlay, Windows 入力エクスペリエンス, Microsoft Store, game_time_tracker.bat, Nahimic
  ```

- **スプレッドシート構造**
  - **ログシート (sheet1)**: `index, start_time, end_time, title, play_with_friends`
  - **ゲーム情報シート**: `game_title, window_title, play_with_friends, is_browser_game`
    - 真偽値は `"TRUE"` / `"FALSE"` 文字列として保存。読込時は `parse_bool` で判定。

- **[service_account.json](service_account.json)**
  - Google Cloud サービスアカウント秘密鍵。
  - `.gitignore` で除外管理。

## 自動検出フロー (main.py)
1. 起動時にゲーム情報シートを読み込み、`game_title/window_title/play_with_friends/is_browser_game` をメモリに保持。
2. 1秒間隔（`POLL_INTERVAL_SECONDS = 1`）で以下を実行：
   - 全ウィンドウのタイトルを取得（`pygetwindow.getAllWindows()`）。
   - 除外リスト（Program Manager など）を外す。
   - 各ゲームの `window_title` が部分一致するか判定。
3. 一致したゲーム：
   - `is_playing=True` とし、初回一致時に `start_time` を記録。
   - ブラウザゲーム判定：
     - `is_browser_game=True` の場合、ブラウザタイトルでも記録対象。
     - `is_browser_game=False` の場合、ブラウザウィンドウを除外（ブラウザ名で判定）。
4. 一致がなくなった瞬間：
   - `is_playing=False` とし、`end_time` を記録。
   - プレイ時間計算: `(end_time - start_time).total_seconds() / 60` (分単位)。
   - **5分以上のプレイのみ** `[index, start, end, game_title, play_with_friends]` をログシートへ追記。
   - 5分未満の場合は破棄。
   - 開始・終了時刻は `YYYY/MM/DD HH:MM:SS` 形式に整形。
5. ステート出力：
   - ゲーム実行中: `{game_title}をプレイ中`
   - ゲーム終了時（5分以上）: `{game_title}のプレイ時間を記録しました`
   - ゲーム終了時（5分未満）: `{game_title}のプレイ時間が5分未満のため、記録されませんでした`

## ウィンドウタイトル判定アルゴリズム

```python
# 各ゲームについて
for game in games:
    detected = any(
        game.matches_window(title, self.browsers)
        for title in window_titles
    )
    
    if detected and not game.is_playing:
        game.start_session()
    elif not detected and game.is_playing:
        self.recorder.record(game)
```

### GameEntry.matches_window()
```python
def matches_window(self, window_title: str, browsers: Sequence[str]) -> bool:
    if self.window_title not in window_title:
        return False

    is_browser = any(browser in window_title for browser in browsers)

    # ブラウザゲームの場合は常にマッチ
    if self.is_browser_game:
        return True

    # 通常ゲームの場合はブラウザ以外でマッチ
    return not is_browser
```

## GUI 表示モード

### max モード（全表示）
- 今日のプレイ時間（HH:MM:SS.F形式）
- 現在のセッション時間
- プレイ中のゲーム
- 今日プレイしたゲーム一覧（ゲーム名: XX分）
- 現在のウィンドウタイトル一覧

### mid モード
- 今日のプレイ時間（HH:MM:SS.F形式）
- 現在のセッション時間
- プレイ中のゲーム
- 今日プレイしたゲーム一覧（ゲーム名: XX分）

### min モード（最小表示）
- 今日のプレイ時間のみ

## 非機能要件・制約
- **OS**: Windows（`tkinter` 不要、`pygetwindow/keyboard` に依存）。
- **時刻**: ローカルタイムで算出、タイムゾーン変換なし。
- **スキャン間隔**: 1秒固定（`POLL_INTERVAL_SECONDS = 1`）。
- **最小記録時間**: 5分以上（`MIN_PLAY_MINUTES = 5`）。
- **部分一致**: ウィンドウタイトルの部分一致に依存。共通する文字列を登録する必要がある（例: Terraria）。
- **スプレッドシートアクセス**: GUI版では起動時とゲーム記録時のみアクセス（UI更新時はキャッシュを使用）。

## 起動エントリ
```powershell
python main.py
```

## TODO の進捗
- ✅ ログ取得機能_V1 (手動操作での取得は削除)
- ✅ ログ取得機能_V3 (自動検出実装)
  - ウィンドウタイトルから自動判別
  - Google スプレッドシートへ自動保存

## 開発
- テスト: `python -m unittest`
- ポーリング間隔・最小記録時間: `main.py` の `POLL_INTERVAL_SECONDS`, `MIN_PLAY_MINUTES` で調整。
- 対応ブラウザ・除外ウィンドウ: `config.ini` の `[WINDOW_SCAN]` または `config_loader.DEFAULT_BROWSERS/DEFAULT_EXCLUDED_TITLES` で設定。
