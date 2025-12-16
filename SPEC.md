# Game Time Tracker 仕様書

## 目的
Windows PC で実行中のゲームをウィンドウタイトルから自動検出し、プレイ時間を Google スプレッドシートに記録するツール。

## システム構成
- **[main.py](main.py)** (自動検出・ログ記録)
  - `pygetwindow` でアクティブウィンドウのタイトルを取得。
  - ゲーム情報シートから登録されたゲームを読み込み。
  - ウィンドウタイトルの部分一致判定でゲーム検出。
  - ブラウザタイトルは `is_browser_game=True` のゲームのみ記録対象。
  - 10秒間隔でポーリング。ウィンドウ消失時に終了時刻を確定。
  - 5分以上のプレイのみスプレッドシートへ追記。
  
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
  ```

- **スプレッドシート構造**
  - **ログシート (sheet1)**: `index, start_time, end_time, title, play_with_friends`
  - **ゲーム情報シート**: `game_title, window_title, play_with_friends, is_browser_game`
    - 真偽値は `"TRUE"` / `"FALSE"` 文字列として保存。

- **[service_account.json](service_account.json)**
  - Google Cloud サービスアカウント秘密鍵。
  - `.gitignore` で除外管理。

## 自動検出フロー (main.py)
1. 起動時にゲーム情報シートを読み込み、`game_title/window_title/play_with_friends/is_browser_game` をメモリに保持。
2. 10秒間隔で以下を実行：
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
    game_in_window_titles = False
    for title in window_titles:
        # ブラウザ判定
        is_browser = any(browser in title for browser in BROWSERS)
        
        # ウィンドウタイトルがゲームの window_title を含むか（部分一致）
        if game['window_title'] in title:
            if game['is_browser_game']:
                # ブラウザゲーム：ブラウザでの実行を許可
                game_in_window_titles = True
                break
            elif not is_browser:
                # 通常ゲーム：ブラウザでの実行を除外
                game_in_window_titles = True
                break
    
    game['is_playing'] = game_in_window_titles
```

## 非機能要件・制約
- **OS**: Windows（`tkinter` 不要、`pygetwindow/keyboard` に依存）。
- **時刻**: ローカルタイムで算出、タイムゾーン変換なし。
- **スキャン間隔**: 10秒固定。
- **最小記録時間**: 5分以上。
- **部分一致**: ウィンドウタイトルの部分一致に依存。共通する文字列を登録する必要がある（例: Terraria）。

## 起動エントリ
```powershell
python main.py
```

## TODO の進捗
- ✅ ログ取得機能_V1 (手動操作での取得は削除)
- ✅ ログ取得機能_V3 (自動検出実装)
  - ウィンドウタイトルから自動判別
  - Google スプレッドシートへ自動保存
