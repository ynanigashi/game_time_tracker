1. ログ取得機能_V1
    1. プレイ時間を取得
        1. ユーザーによる操作で開始時刻を取得
        1. ユーザーによる操作で終了時刻を取得
    1. プレイ時間保存
        1. その日にプレイした時間をローカルファイルに保存
    1. プレイ時間読み込み
        1. その日にプレイした時間をローカルファイルから読み込む
1. 画面表示機能_V1
    1. タイマー表示機能
        1. ローカルファイルからその日プレイした時間を取得しカウンダウンタイマーを表示
        1. ユーザーによるプレイ開始操作にてカウントダウンを開始
        1. ユーザ―によるプレイ終了操作にてカウントダウンを停止
    1. プレイ時間表示
        1. ユーザーによるプレイ終了操作後に以下を表示
            - 前回のプレイ時間
            - 本日の総プレイ時間
            - 本日の残りプレイ時間
    1. アラート機能
        1. タイマーが15minを切った場合、画面上にアラートを表示
        1. タイマーが0を切った場合その旨を表示

1. ログ取得機能_V2
    1. プレイ時間を取得
        1. ユーザーによる操作で開始時刻を取得
        1. ユーザーによる操作で終了時刻を取得
        1. プレイ時間を表示
    1. プレイ時間保存
        1. その日にプレイした時間をローカルファイルに保存
    1. プレイ時間読み込み
        1. その日にプレイした時間をローカルファイルから読み込む
    1. プレイタイトルを取得
        1. ローカルファイルからのプレイするゲームのタイトルを取得
        1. ユーザーがプレイタイトルを選択
    1. ログを保存
        1. Google Spreadsheetへ以下情報を保存
            - プレイ開始時刻
            - プレイ終了時刻
            - プレイタイトル
1. ログ取得機能_V3
    1. プレイ時間を取得
        1. 起動しているアプリケーションなどから判断し、プレイ開始時刻を取得
        1. アプリケーションなどから判断し、プレイ終了時刻を取得
        1. プレイ時間を表示
    1. プレイタイトルを取得
        1. 外部ファイルからのプレイするゲームのタイトル、ウィンドウタイトルなどを取得（なにで判断するか未定）
        1. アプリケーションがプレイタイトルを自動判別
    1. ログを保存
        1. Google Spreadsheetへ以下情報を保存
            - プレイ開始時刻
            - プレイ終了時刻
            - プレイタイトル