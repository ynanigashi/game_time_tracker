# Game Time Tracker

Windows PC で起動しているアプリケーションのウィンドウタイトルからゲームプレイを自動検出し、ローカル SQLite にプレイ時間を記録するツールです。Google スプレッドシートは初回ゲーム情報取り込みとプレイログのバックアップに使用できます。

> ⚠️ **Windows 専用**: このツールは `pygetwindow` および `pywin32` を使用しており、Windows 環境でのみ動作します。

## 機能
- **自動検出**: 起動中のウィンドウタイトルからゲームを判定し、プレイ開始・終了を自動で記録。
- **フォアグラウンド検出**: 最前面（フォアグラウンド）のウィンドウのみをアクティブなプレイとして判定。
- **非アクティブ時の自動分割**: ゲームウィンドウが5分以上非アクティブ（バックグラウンド）になると、その時点でセッションを自動記録。再度アクティブになった際は新しいセッションとして計測。
- **ブラウザゲーム対応**: ブラウザ上で実行されるゲームの記録可否を個別に設定可能。
- **ゲーム管理**: ゲームタイトル、検出用ウィンドウタイトル、ブラウザゲーム設定をローカルDBで追加・編集・削除。
- **ローカルDB記録 + スプレッドシートバックアップ**: プレイログは `data/play_logs.sqlite3` に保存し、サービスアカウント経由で Google スプレッドシートへバックアップ。
- **最小記録時間**: 5分未満のプレイは記録対象外（誤検出防止）。
- **日跨ぎ対応**: 深夜0時を跨いでプレイした場合、日付ごとに分割して正確に記録。
- **柔軟な除外設定**: 設定画面など、記録から除外するウィンドウを指定可能。
- **堅牢なエラーハンドリング**: 設定ファイルの検証、ローカル保存失敗時の検知、スプレッドシートバックアップ失敗時の継続処理。

## 動作環境
- **OS**: Windows 11
- **利用者**: Python 不要（配布 EXE を使用）
- **開発者**: Python 3.10 以上

## 利用者向けセットアップ（EXE）

### 1. EXE の入手
- GitHub Releases から `game_time_tracker-windows.zip` をダウンロードして展開します。
- ZIP には `game_time_tracker.exe` / `_internal/` / `config/config.ini.example` / `README.md` が含まれます。`_internal/` は PySide6 などの実行時依存を含むため、EXE と同じ階層に置いてください。

### 2. Google スプレッドシートの準備
1) **Google Cloud でサービスアカウントを作成**
   - Google Cloud Console で新しいプロジェクトを作成。
   - 「Google Sheets API」と「Google Drive API」を有効化。
   - サービスアカウントを作成し、秘密鍵（JSON）をダウンロード。
   - JSON ファイルを `service_account.json` として保存（パスは `config/config.ini` で変更可）。

2) **スプレッドシートを作成**
   - Google Sheets で新規スプレッドシートを作成。
   - サービスアカウントのメールアドレスを共有先に追加（編集可）。

3) **シート構成を設定**
   - **ログシート**: ヘッダー行 `record_id,device_id,index,start_time,end_time,title,play_with_friends` を作成。
     - `record_id` は複数PC同期用の一意ID、`device_id` は記録元PC名です。
     - 末尾に集計用の計算列を追加しても、同期時は上記の列だけを読み取ります。
     - 旧ヘッダーの `No`（index相当）と `with_friends` も取り込み互換のため読み取れます。
   - **ゲーム情報シート**: 初回取り込み用に別シートを用意し、ヘッダー行 `id,game_title,window_title,play_with_friends,is_browser_game` を作成。`id` が空の場合はローカルDB取り込み時に UUID を採番します。

4) **config/config.ini を設定**
   - スプレッドシート URL から以下を確認：
     - `<sheet_key>`: URL内の `https://docs.google.com/spreadsheets/d/<sheet_key>/edit#gid=0` から取得。
     - `sheet_gid`: 対象シートの gid（URL末尾の `#gid=<gid>`）。ログシート、ゲーム情報シートそれぞれで指定できます。
   - `config/config.ini.example` を `config/config.ini` にコピーして設定を記入：
     ```ini
     [LOGHANDLER]
     json_file_path = service_account.json
     backup_mode = spreadsheet
     sheet_key = <ログシートのキー>
     sheet_gid = <ログシートの gid>
     sync_conflict_policy = overwrite

     [GAMEINFO]
     sheet_key = <ゲーム情報シートのキー>
     sheet_gid = <ゲーム情報シートの gid>
     ```

5) **接続確認（任意）**
  - 初回起動時にエラーが出ないことをもって接続確認とするのが簡単です。
  - 開発者がPythonで検証したい場合は、後述の「開発向け」を参照してください。

### 3. ゲーム情報の登録
ゲーム情報は `data/game_catalog.sqlite3` に保存され、右クリックメニューの `ゲーム管理` から追加・編集・削除できます。

初回または手動同期でスプレッドシートから取り込む場合は、ゲーム情報シートにプレイするゲームの情報を登録します：

| id | game_title | window_title | play_with_friends | is_browser_game |
|----|------------|-------------|------------------|-----------------|
| 1 | Terraria | Terraria | FALSE | FALSE |
| 2 | Elden Ring | ELDEN RING | FALSE | FALSE |
| 3 | ゲーム1 | GameSite - Google Chrome | TRUE | TRUE |

- **id**: ローカルDBとスプレッドシート同期で使うゲームID。空の場合はローカル取り込み時にUUIDを採番します。
- **game_title**: プレイログに記録されるゲーム名。
- **window_title**: 監視するウィンドウタイトルの一部（部分一致判定）。
- **play_with_friends**: `"TRUE"` の場合、フレンドとのプレイ（記録対象）。
- **is_browser_game**: `"TRUE"` の場合、ブラウザ上のプレイも記録対象。`"FALSE"` の場合はブラウザを除外。

## 使い方

### GUI での起動（メイン機能）

#### EXE で起動（推奨）
- `game_time_tracker.exe` を起動します。
- プレイ中のゲームと経過時間、現在のウィンドウタイトルを一覧表示します。
- maxモードの「現在のウィンドウタイトル」一覧は、行をクリックするとそのタイトル文字列をクリップボードにコピーできます。
- ローカルDBへの記録タイミングや検出ロジックは自動です。
- 表示モードは左クリックでトグル：
  - **max**: 全表示（今日のプレイ時間、セッション時間、プレイ中のゲーム、今日プレイしたゲーム一覧、ウィンドウタイトル）
  - **mid**: 今日のプレイ時間、セッション時間、プレイ中のゲーム、今日プレイしたゲーム一覧（ウィンドウタイトルは非表示）
  - **min**: 今日のプレイ時間のみ
- 画面最下部に `時間超過防止アラート` スイッチを表示（`max/mid/min` 全モード）。
  - 左詰め配置（ラベルの右にスイッチ）
  - ノブが左右に移動する小型スライドスイッチ
  - OFF時はアラート音を停止し、時間オーバーレイ表示も無効化
- **今日プレイしたゲーム一覧**（mid/max モードで表示）:
  - その日にプレイしたゲームとそれぞれのプレイ時間（分数）を表示
  - プレイ時間の長い順にソート
  - 現在プレイ中のゲームの時間も含めてリアルタイムに更新（**5分以上のセッションのみ**）
  - 日跨ぎセッションは当日0:00以降の分のみカウント
- メインウィンドウを右クリックすると、`レポート` / `ゲーム管理` / `設定` / `終了` のメニューを表示します。
- `レポート` の `ログ` タブではプレイログ一覧を確認でき、`スプシ同期` からプレイログシートを手動同期できます。スプレッドシート側のログを取り込み、未バックアップのローカルログを送信します。
- `ゲーム管理` ではゲーム名、検出用ウィンドウタイトル、フレンドプレイ、ブラウザゲームの設定を追加・編集・削除できます。変更は `data/game_catalog.sqlite3` に保存され、保存後に監視対象を再読み込みします。
- `ゲーム管理` の `スプシから取得` はゲーム情報シートを手動取得し、`id` をキーにローカルDBへ反映します。シートにない既存IDは無効化され、一覧の二重表示を避けます。
- `設定` では認証JSON、プレイログ保存モード、シート key、sheet_gid、対象ブラウザ、除外タイトルを編集できます。認証JSONはファイル選択で指定できます。
- プレイログ保存モードは `ローカルのみで運用` / `スプレッドシートにバックアップ` から選択できます。`ローカルのみで運用` の場合、ログシート key / sheet_gid は不要です。
- `ID重複時` は `スプシを上書き` / `別IDで追加` から選択できます。複数PC同期で同じ `record_id` が見つかった場合の処理です。
- 設定画面で保存した内容は `data/settings.sqlite3` へ保存されます。`config/config.ini` は設定画面の `設定Export` / `設定Import` で手動入出力できます。
- モード・位置・サイズは `data/settings.sqlite3` に保存/復元されます。
- ウィンドウ検出は 1 秒間隔、UI 更新は 0.1 秒間隔です。
- **ローカルDB優先の記録処理**:
  - プレイログは `data/play_logs.sqlite3` に保存し、起動時にメモリ上へキャッシュ（`List[dict]`形式）
  - UI更新時はキャッシュから取得（Spreadsheet APIを呼び出さない）
  - ゲーム記録時はローカルDBを先に更新し、スプレッドシートへバックアップ
  - バックアップ有効時は起動時とゲーム記録時にスプレッドシートのログをローカルDBへ同期
  - バックアップできなかったレコードは次回起動時に再バックアップ
  - スプレッドシート取得に失敗した場合は、その回のバックアップ送信を止め、未バックアップ状態のまま次回に再試行します。
  - 複数PCからの記録は `record_id` で識別し、`device_id` で記録元PCを残します。
  - `record_id` がスプレッドシート側に既にある場合は、設定に応じて既存行を上書きするか、別IDを採番して新規行として追加します。

#### 設定ファイルの配置（EXE）
- 通常起動時の設定は `data/settings.sqlite3` から読み込まれます。
- `data/settings.sqlite3` に有効な設定がなく `config/config.ini` がある場合は、初回移行として `config/config.ini` を SQLite へ取り込みます。
- 旧配置の `config.ini` が残っている場合は、初回起動時に `config/config.ini` へ移動します。
- `service_account.json` は EXE と同じフォルダに置く運用を推奨します（`config/config.ini` 側で相対パス指定可能）。
- `config/config.ini` も SQLite も未設定の場合は、起動時に設定画面を表示します。
- ログは `logs/game_time_tracker.log` に出力され、1MB + 3世代までローテートします。
- ゲーム情報は `data/game_catalog.sqlite3` に保存されます。
- プレイログは `data/play_logs.sqlite3` に保存されます。
- ウィンドウ状態は `data/settings.sqlite3` に保存されます。旧 `data/window_state.txt` は初回起動時に SQLite へ取り込まれます。
- 旧配置の `game_time_tracker.log` / `window_state.txt` が残っている場合は、初回起動時にそれぞれ `logs/` / `data/` へ移動してから必要に応じて SQLite に取り込みます。

#### 実行時の動作
起動すると、1秒間隔（`POLL_INTERVAL_SECONDS = 1`）で起動中のウィンドウをスキャンします：
- ウィンドウタイトルが登録されたゲームと一致し、かつフォアグラウンド（最前面）ならプレイ中として計測。
- ゲームウィンドウがバックグラウンドになると「ゲーム名 - 停止中」と表示。
- バックグラウンド状態が5分未満で復帰した場合、セッションは継続（停止時間も含む）。
- バックグラウンド状態が5分以上続くと、その時点でセッションを自動記録。次にフォアグラウンドになった際は新しいセッションとして計測。
- ウィンドウが消失したら、プレイ終了として記録。
- 5分以上（`MIN_PLAY_MINUTES`）のプレイのみローカルDBに記録し、スプレッドシートへバックアップ。
- タイトルバーにステータスを表示、記録時のメッセージは標準出力に表示。

## ファイル構成

### アプリケーションコード
- [src/app/main.py](src/app/main.py) : PySide6 GUI（`MainWindow` クラス）。イベント処理とUI更新のみを担当。
- [src/core/models.py](src/core/models.py) : データモデル（`GameEntry`, `ParsedRecord`）とパース関数。
- [src/core/services.py](src/core/services.py) : ビジネスロジック（`GameInfoLoader`, `WindowScanner`, `SessionRecorder`, `DailyStatsTracker`）。
- [src/core/window_state.py](src/core/window_state.py) : ウィンドウ状態の保存/読み込み（`WindowState`）。
- [src/ui/gui_layout.py](src/ui/gui_layout.py) : UIレイアウト構築。
- [src/ui/game_catalog_dialog.py](src/ui/game_catalog_dialog.py) : ローカルゲーム情報の追加・編集・削除画面。
- [src/infra/log_handler.py](src/infra/log_handler.py) : プレイログの読み書き窓口。ローカルDBを主保存先にし、スプレッドシートへのバックアップとキャッシュ更新を担当。
- [src/infra/play_log_store.py](src/infra/play_log_store.py) : `data/play_logs.sqlite3` へのプレイログ保存・読み込み・バックアップ状態管理。
- [src/infra/game_catalog_store.py](src/infra/game_catalog_store.py) : `data/game_catalog.sqlite3` へのゲーム情報保存・読み込み・論理削除。
- [src/infra/config_loader.py](src/infra/config_loader.py) : SQLite 設定の読み込みと `config/config.ini` 初回移行。ブラウザ判定/除外タイトルはここで定義。
- [src/infra/settings_store.py](src/infra/settings_store.py) : `data/settings.sqlite3` への設定値・ウィンドウ状態の保存。

### 設定・その他
- [game_time_tracker.bat](game_time_tracker.bat) : 開発者向けのWindowsバッチファイル。仮想環境を有効化して main.py を実行。
- `config/config.ini` : 設定画面の Import/Export 用 INI。SQLite 未設定時の初回移行にも使用。
- [service_account.json](service_account.json) : Google Cloud サービスアカウント秘密鍵（.gitignore で除外）。
- [.github/workflows/release-exe.yml](.github/workflows/release-exe.yml) : GitHub Releases 公開時に Windows EXE を自動ビルドして添付。

## 設定ファイル（config/config.ini）
```ini
[LOGHANDLER]
json_file_path = service_account.json      ; サービスアカウント JSON のパス
backup_mode = spreadsheet                  ; spreadsheet または local_only
sheet_key = <スプレッドシートキー>         ; ログシートのキー
sheet_gid = 0                              ; ログシートの gid（省略時は sheet1）
sync_conflict_policy = overwrite           ; overwrite または new_id

[GAMEINFO]
sheet_key = <スプレッドシートキー>         ; ゲーム情報シートのキー
sheet_gid = 1198224769                     ; ゲーム情報シートの gid

[WINDOW_SCAN]
browsers = Google Chrome, Microsoft Edge, Mozilla Firefox, Opera, Brave, Vivaldi, Safari  ; ブラウザ名（部分一致）
exclude_titles = Program Manager, Settings, 設定, NVIDIA GeForce Overlay, Windows 入力エクスペリエンス, Microsoft Store, game_time_tracker.bat, Nahimic
```

## 注意・トラブルシューティング

### ウィンドウタイトルが認識されない
- `config/config.ini` の `[WINDOW_SCAN]` セクションで `exclude_titles` を確認・編集してください（未設定時は `config_loader.py` のデフォルト値を使用）。
- ゲーム情報シートの `window_title` が、実際のウィンドウタイトル（の一部）と一致しているか確認してください。
- 実際のウィンドウタイトルはGUIウィンドウの「現在のウィンドウタイトル」リスト（maxモード）で確認できます。
- 「現在のウィンドウタイトル」リストはクリックでコピーできるため、ゲーム追加時に `window_title` へ貼り付けて使えます。

### ブラウザゲームが記録されない
- ゲーム情報シートの `is_browser_game` が `"TRUE"` に設定されているか確認。
- ウィンドウタイトルにブラウザ名（Chrome、Edge等）が含まれている場合、`window_title` にはゲーム固有の文字列を含める必要があります。

### スプレッドシートへの接続エラー
- `service_account.json` のパスが正しいか確認。
- サービスアカウントのメールアドレスがスプレッドシートで共有されているか確認。
- API キーが有効か確認（Google Cloud Console で確認）。
- プレイログのローカル保存は継続されます。バックアップできなかったレコードは次回起動時に再バックアップされます。

### EXE 起動時にグラフが表示されない
- `game_time_tracker.exe` と同じ階層に `_internal/` フォルダがあるか確認してください。PySide6.QtCharts などの依存モジュールは `_internal/` 側に含まれます。

### 設定のエラー
- `data/settings.sqlite3` と `config/config.ini` のどちらにも必須項目（`[LOGHANDLER]` の `json_file_path` 、`[GAMEINFO]` の `sheet_key`, `sheet_gid`）がない場合は、起動時に設定画面を表示します。`[LOGHANDLER] sheet_key` は `backup_mode = spreadsheet` の場合のみ必須です。
- 認証JSONファイルが見つからない場合は、警告を表示して設定画面を開きます。
- `sheet_gid` は整数値で指定してください（例: `sheet_gid = 1198224769`）。

## 開発向け
- テスト実行: `python -m unittest`
- 監視間隔は `src/app/main.py` 冒頭の定数で変更できます：
  - `POLL_INTERVAL_SECONDS = 1`（デフォルト: 1秒）
- 最小記録時間は `src/core/services_domain.py` の定数で変更できます：
  - `MIN_PLAY_MINUTES = 5`（デフォルト: 5分）
- 監視対象ブラウザ・除外ウィンドウは設定画面で変更できます（未設定時は `config_loader.py` のデフォルト値）。
- モジュール構成:
  - `src/core`: ドメイン層（`models.py`, `services.py`, `services_domain.py`, `time_utils.py`, `window_state.py`）
  - `src/infra`: 外部連携・保存層（`config_loader.py`, `gspread_service.py`, `log_handler.py`, `play_log_store.py`）
  - `src/ui`: UIレイアウト（`gui_layout.py`）
  - `src/app`: エントリーポイント/UI制御（`main.py`, `main_components.py`）
  - ルートの `main.py` は実行エントリです。実装は `src/` 配下にあります。

## 開発ガイド
- 仮想環境: `python -m venv .venv && .\.venv\Scripts\activate && pip install -r requirements.txt`
- 実行: `python main.py`（ローカルDBへの書き込みと Google Sheets へのバックアップが発生するため必要なら別シートで検証）
- 設定: 初回起動時の設定画面でプレイログ保存モード、ログシート・ゲーム情報シートのキーと gid、サービスアカウント JSON のパスを指定
- テスト: 依存をスタブ化した単体テストを `python -m unittest` で実行（`tests/` 配下）
- 拡張例:
  - ポーリング間隔の変更は `src/app/main.py` の `POLL_INTERVAL_SECONDS`
  - 最小記録時間の変更は `src/core/services_domain.py` の `MIN_PLAY_MINUTES`
  - 対応ブラウザや除外ウィンドウの追加は設定画面（未設定時は `config_loader.py` のデフォルト値）
  - 新しいデータモデルは `src/core/models.py` に追加
  - 新しいビジネスロジックは `src/core/services.py` / `src/core/services_domain.py` に追加
  - UIの拡張は `src/app/main.py` の `MainWindow` を拡張

### クラス/メソッドの関係図（Mermaid）
```mermaid
flowchart LR
    subgraph Config
        C[config/config.ini] --> CL[ConfigLoader]
    end
    subgraph Models
        GE[GameEntry<br/>matches_window / start_session / end_session]
    end
    subgraph Services
        GIL[GameInfoLoader.load] --> GE
        WS[WindowScanner.get_titles]
        SR[SessionRecorder.record]
        DS[DailyStatsTracker]
    end
    subgraph GUI
        MW[MainWindow._scan_tick/_ui_tick]
        GST[GameStateTracker.scan]
    end

    MW --> WS
    MW --> GST
    GST --> GE
    GST --> SR
    GST --> DS
    SR --> LH[LogHandler<br/>format_datetime_to_gss_style<br/>get_and_increment_index<br/>save_record]

    CL --> MW
    CL --> GIL
    CL --> WS
    MW --> GIL
```

## ライセンス
MIT License

## ドキュメント追記（2026-03）
- タイトル判定は正規化前提に変更:
  - `GameStateTracker.scan()` で `window_titles` / `foreground_title` を 1 回だけ正規化してから判定します。
  - `GameEntry.matches_window()` は正規化済み入力を受け取り、`window_title` の正規化結果を内部キャッシュして比較します。
- 正規化の仕様:
  - 大文字/小文字を吸収（`casefold`）
  - ダッシュ記号バリエーションを `-` に統一
  - 余分な空白を正規化
- 追加モジュール:
  - `text_utils.py` に `normalize_title()` を追加
- `GameStateTracker` の内部リファクタ:
  - `_check_window_exists()` / `_check_is_foreground()` は `browsers` 引数を廃止し、内部キャッシュ `self._normalized_browsers` を直接参照。
  - 記録後の `DailyStatsTracker` 更新処理を `_apply_recorded_seconds()` に集約し、`_handle_window_closed()` と `_handle_inactive_timeout()` の重複を解消。
  - `set_browsers()` で空の正規化結果を除外してキャッシュを保持。
  - `WindowMatchState` を導入し、`scan()` での「存在判定/フォアグラウンド判定」の受け渡しを明示化。
  - `LoadTodayMinutes` 型エイリアスで、コールバック型を1箇所に集約。
- `MainWindow` の内部リファクタ:
  - 初期化エラー処理を `_disable_with_status()` と `_create_log_handler()` に分離し、`_init_components()` の責務を整理。
  - プレイ中ゲームの統合取得を `_all_playing_games()` に集約し、UI更新系メソッドの重複を削減。
  - 初期化フローを `_load_config_and_games()` / `_build_scanner()` / `_initialize_tracking_services()` / `_load_today_stats_cache()` に分割。
  - スキャンフローを `_scan_games()` / `_apply_scan_result()` / `_update_scan_status()` に分割し、`_scan_tick()` をオーケストレーション専用に整理。
  - UI更新ロジックを `MainWindowUiController` に分離し、`MainWindow` はイベント駆動と状態遷移のオーケストレーションに集中。
  - 表示モード切替ロジックを `MainWindowDisplayController` に分離し、`_apply_display_mode()` / `_apply_mode_geometry()` / `_cycle_display_mode()` を薄い委譲メソッド化。
  - ウィンドウ状態の保存・復元ロジックを `MainWindowStateController` に分離し、`_save_window_state()` / `resizeEvent()` / 初期ロードを委譲化。
  - 初期化依存構築を `MainWindowBootstrapper` に分離し、`_init_components()` は「エラー処理 + 反映」に限定。
  - タイマー起動と tick 実行フローを `MainWindowLoopController` に分離し、`_start_timer()` / `_scan_tick()` / `_ui_tick()` を委譲化。
  - 初期化エラーのドメイン例外として `MainWindowBootstrapError` を導入し、`_init_components()` の例外境界を単純化。
  - コントローラー/ブートストラッパー取得の重複ロジックを `_resolve_dependency()` に集約し、各 `_get_*` メソッドを「依存定義 + 再生成条件」だけに整理。
  - `__init__` の起動手順を `_initialize_window_state()` / `_initialize_runtime_state()` / `_warmup_dependencies()` / `_start_background_timers()` / `_run_initial_refresh()` に分割し、起動フローを段階的に把握しやすく整理。
  - UIイベント処理を小メソッドに分割し、`closeEvent()` / `mousePressEvent()` / `resizeEvent()` をオーケストレーションに限定（`_record_playing_games_before_close()` / `_should_cycle_display_mode()` / `_record_current_mode_size()`）。
