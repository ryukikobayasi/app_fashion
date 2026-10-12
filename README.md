# FITTING — 手持ちアイテムからコーデ提案

服やファッション小物の写真を画像対応AIで読み取り、アップロードしたアイテムを使った5つのコーデを提案するStreamlitアプリです。

## 起動方法

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
streamlit run app.py
```

`.env` を開き、`OPENAI_API_KEY=...` の右側を自分のAPIキーに置き換えて保存してください。アプリ起動時に `.env` を読み込みます。`.env` は `.gitignore` に登録済みなので、GitHubへpushしないでください。Renderでは `.env` をアップロードせず、Renderの環境変数に `OPENAI_API_KEY` を登録してください。環境変数が `.env` の値より優先されます。任意で `OPENAI_VISION_MODEL` を指定でき、既定の画像対応モデルは `gpt-4.1-mini` です。

## Renderへのデプロイ

リポジトリをGitHubにpushしてRenderでBlueprintとして作成すると、ルートの `render.yaml` の設定でデプロイできます。Renderのサービス設定で `OPENAI_API_KEY` にOpenAI APIキーを登録してください。Blueprintでは `sync: false` を指定しており、キーの値をソース管理へ登録しません。環境変数を登録すると、アプリはサーバー側のAPIキーを使い、アプリ内のAPIキー入力欄は表示しません。認証は設定していないため、RenderのURLを知っている人は誰でも利用でき、提案の実行でAPI利用料が発生する可能性があります。

無料プランは一定時間アクセスがないと休止し、次のアクセス時に起動待ちが発生する場合があります。

## できること

- JPEG、PNG、WebPのアイテム写真（最大10MB）をアップロード
- ブラウザーのカメラを起動し、その場で撮影した写真から提案
- 写真を読み取って、主役アイテム、種類、見える色を説明
- 写真のアイテムを使ったコーデを5案提案
- 各コーデのボタンから、選んだ案のAIイメージ画像を個別に生成
- メンズ、レディース、ユニセックス、好みのテイストとカラーを選択
- オプションで日本の主要都市の天気をコーデに反映
- 2026年秋冬の海外ストリート／ランウェイ記事を参考に、配色やレイヤードを提案

## データとおすすめについて

画像はファイル選択またはブラウザーのカメラで撮影できます。カメラを使う場合は、ブラウザーのカメラ使用を許可してください。Renderなどにデプロイしたアプリでカメラを使うにはHTTPS接続が必要です。画像解析はOpenAI Chat Completions API、イメージ画像はOpenAI Images APIを利用します。提案ボタンを押すと、10MB以下の写真を長辺1280pxに縮小しJPEGに変換してOpenAIへ送信します。提案カードの「このコーデのイメージ画像を生成」を押したときだけ、その案の説明文をもとに画像を1枚生成します。画像生成ごとにAPI利用料が発生する場合があります。生成した画像はセッション中だけ保持し、アプリはファイルに保存しません。任意で `OPENAI_IMAGE_MODEL` を指定でき、既定は `gpt-image-1` です。APIの利用料金・データ取り扱いはOpenAIの契約と設定に従います。

天気はAPIキー不要の[Open-Meteo Forecast API](https://open-meteo.com/en/docs)を使い、任意で提案に含められます。トレンドは出典を確認した編集テーマで、リアルタイムの検索・売上ランキングではありません。

海外トレンドの参照先: [Fashionista — Fall 2026 street style](https://fashionista.com/2026/03/street-style-trends-fall-2026)、[British Vogue — Autumn/Winter 2026](https://www.vogue.co.uk/autumn-winter-2026)。トレンドスナップショットは2026年10月12日更新です。

## テスト

```powershell
python -m unittest discover -s tests
```
