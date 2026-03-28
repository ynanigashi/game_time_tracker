# Overlay Display Spec (Current)

## 目的
- `today_time_display` が他ウィンドウに隠れて視認できない場合だけ、同じ値をオーバーレイで補完表示する。
- メインウィンドウが前面にあるときはオーバーレイを表示しない。

## 表示内容
- `today_time_display` と同じ文字列を表示する。
- 例: `01:23:45.6`

## 位置とサイズ
- オーバーレイの位置・サイズは `today_time_display` のグローバル座標に同期する。
- 同期は UI tick ごとに実行する。

## 表示条件
次をすべて満たすときだけ表示する。

1. `overtime_alert_enabled == True`
2. メインウィンドウが `isVisible == True`
3. メインウィンドウが `isMinimized == False`
4. 前面ウィンドウが自プロセス外 (`_foreground_rect_if_foreign() is not None`)
5. `today_time_display` の被覆判定が `covered == True`

補足:
- `isActiveWindow` は表示条件に使わない。
- 前面ウィンドウ判定は Win32 ベースで行う。

## 非表示条件
- 表示条件を1つでも満たさない場合は非表示。
- 特に `overtime_alert_enabled == False` の場合、即時で非表示にし、その tick の判定処理を終了する。

## 被覆判定仕様
`_get_today_display_cover_state()` に基づく。

### 入力
- `today_time_display` のグローバル矩形
- 現在の前面ウィンドウ（foreign window）の矩形と root HWND

### 判定フロー
1. `today_time_display` が取れない場合は未被覆。
2. 前面ウィンドウが foreign でない場合は未被覆。
3. `today_time_display` 矩形（native座標）と前面ウィンドウ矩形が交差しない場合は未被覆。
4. サンプル点を評価し、`WindowFromPoint` + `GW_HWNDNEXT` で被覆ウィンドウを探索する。
5. 探索対象は「前面ウィンドウと同じ root HWND」に限定する。
6. 被覆点数がしきい値以上なら被覆とする。

### サンプル点
- 合計5点
- 比率: `(0.5,0.5)`, `(0.25,0.25)`, `(0.75,0.25)`, `(0.25,0.75)`, `(0.75,0.75)`

### 被覆しきい値
- `OVERLAY_COVERED_POINTS_THRESHOLD = 2`
- つまり 5 点中 2 点以上が被覆されているときに表示対象とする。

### Z-order 走査
- `GW_HWNDNEXT` で背面方向へ探索
- 打ち切り回数: `MAX_Z_WALK = 32`

## 判定理由
内部では理由文字列を返す。代表例:
- `overtime_alert_disabled`
- `window_hidden_or_minimized`
- `window_foreground_or_no_foreign`
- `target_missing`
- `target_rect_missing`
- `foreground_not_foreign`
- `foreground_root_missing`
- `covered_native_points`
- `covered_native_points_below_threshold`
- `no_cover_detected`

## ログ仕様
- オーバーレイ可視判定は `INFO` ログに出力する。
- 出力条件:
1. 表示/非表示または理由が変化したとき
2. 変化がなくても 5 秒経過したとき

ログ形式:
- `overlay visibility: show (<reason>)`
- `overlay visibility: hide (<reason>)`

## テスト観点
1. トグル OFF 中は常に非表示。
2. メインウィンドウが前面時は非表示。
3. foreign window が `today_time_display` を 1 点だけ覆う場合は非表示。
4. foreign window が 2 点以上覆う場合は表示。
5. `MAX_Z_WALK` 到達時も無限ループしない。
6. リサイズ/移動時にオーバーレイ位置が追従する。
7. DPI スケーリング環境で判定が破綻しない。
