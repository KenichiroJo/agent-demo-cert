# 小売・EC売上需要予測 AIエージェント 立ち上げ手順書

## 前提条件

### 必要なアカウント・権限
- DataRobotアカウント（エンタープライズライセンス）
- API トークン発行済み
- 以下の権限:
  - AI Catalog へのデータアップロード
  - AutoPilot プロジェクト作成
  - カスタムモデル作成・デプロイ
  - VectorDatabase 作成
  - Codespace アクセス（デプロイ時）

### ローカル環境
- Python 3.11+
- Jupyter Notebook / JupyterLab
- `datarobot` Python SDK (`pip install datarobot`)
- `pandas`, `numpy`

---

## Step 1: リポジトリの準備

```bash
# リポジトリをクローンまたはダウンロード
cd datarobot-agent-application-main2

# .envファイルを作成
cp .env.template .env

# 最低限の設定を記入
# .env ファイルを開き以下を設定:
# DATAROBOT_API_TOKEN=<あなたのAPIトークン>
# DATAROBOT_ENDPOINT=https://app.datarobot.com/api/v2
# SESSION_SECRET_KEY=<ランダムな文字列>
```

---

## Step 2: Phase 0 Notebookの実行

setup/ ディレクトリのNotebookを**順番に**実行します。
各Notebookの最後に出力されるIDを`.env`ファイルに記録してください。

### 2-1. データセット作成

```bash
jupyter notebook setup/01_create_dataset.ipynb
```

**実行内容**: 小売売上の時系列データを生成し、AI Catalogにアップロード

**出力されるID**:
- `TRAINING_DATASET_ID` — 後続のNotebookで使用

**期待される結果**:
- `data/retail_sales_dataset.csv` が生成される（660行）
- DataRobot AI Catalogにデータセットが表示される

**トラブルシューティング**:
- `dr.Client()` エラー → `.env`の`DATAROBOT_API_TOKEN`を確認
- アップロードエラー → ネットワーク接続とAPI権限を確認

### 2-2. 時系列モデル構築

```bash
jupyter notebook setup/02_build_timeseries_model.ipynb
```

**実行内容**: DataRobot AutoTSでモデル構築 → ベストモデルをデプロイ

**出力されるID**:
- `FORECAST_DEPLOYMENT_ID` → `.env`に記入
- `SCORING_DATASET_ID` → `.env`に記入

**期待される結果**:
- DataRobotにAutoTSプロジェクトが作成される
- ベストモデルがデプロイされ、予測可能な状態になる

**所要時間**: AutoPilot実行に15〜30分程度

**トラブルシューティング**:
- Autopilotが失敗 → データセットのカラム名・型を確認
- デプロイエラー → Prediction Environmentの可用性を確認

### 2-3. VDB (ベクターDB) 作成

```bash
jupyter notebook setup/03_create_vdb.ipynb
```

**実行内容**: PDF文献をチャンキング → エンベディング → VDBデプロイ

**事前準備**: `documents/` ディレクトリにPDFファイルを配置
- 経済産業省「電子商取引に関する市場調査」PDF
- ダウンロード先: https://www.meti.go.jp/policy/it_policy/statistics/outlook/ie_outlook.html

**出力されるID**:
- `VDB_DEPLOYMENT_ID` → `.env`に記入

**期待される結果**:
- VDBデプロイメントが作成され、テキスト検索可能な状態になる

**所要時間**: VDBビルド・デプロイに10〜20分程度

**トラブルシューティング**:
- VDBビルド失敗 → PDFファイルのサイズ制限（100MB以下推奨）を確認
- チャンキングエラー → PDFが文字ベース（スキャン画像でない）であることを確認

### 2-4. プロンプト・MCP設定

```bash
jupyter notebook setup/04_setup_prompt_and_mcp.ipynb
```

**実行内容**: Prompt Template作成、MCP接続確認、環境変数の最終確認

**出力されるID**:
- `PROMPT_TEMPLATE_ID` → `.env`に記入
- `MCP_DEPLOYMENT_ID` → `.env`に記入（デプロイ後に自動設定される場合もあり）

**期待される結果**:
- 全環境変数が揃い、エージェント起動の準備が完了

---

## Step 3: .envファイルの最終確認

Notebook実行後、`.env`ファイルに以下が全て設定されていることを確認:

```bash
# 基本設定
DATAROBOT_API_TOKEN=<設定済み>
DATAROBOT_ENDPOINT=https://app.datarobot.com/api/v2
SESSION_SECRET_KEY=<設定済み>

# 小売EC需要予測エージェント設定
PROMPT_TEMPLATE_ID=<Notebook 04で取得>
FORECAST_DEPLOYMENT_ID=<Notebook 02で取得>
SCORING_DATASET_ID=<Notebook 02で取得>
VDB_DEPLOYMENT_ID=<Notebook 03で取得>
COMPANY_NAME=小売EC需要予測デモ

# MCP設定
MCP_SERVER_PORT=9000
```

---

## Step 4: エージェントの起動

### ローカル開発モード

```bash
# 全サービスを起動（フロントエンド + バックエンド + エージェント + MCPサーバー）
dr run dev
```

個別に起動する場合:
```bash
# MCPサーバーを先に起動
task mcp:start

# エージェントを起動
task agent:start

# フロントエンドを起動
task frontend:start
```

### dragentモードでの起動

`.env` で `ENABLE_DRAGENT_SERVER=true` を設定すると、DataRobot Agent Runtime (dragent) モードで起動します。
このモードでは `register.py` + `workflow.yaml` による NAT統合が有効になり、
LLMインスタンスはDataRobotプラットフォームから自動注入されます。

```bash
# .envで有効化
echo "ENABLE_DRAGENT_SERVER=true" >> .env

# 起動（dragentモード）
dr run dev
```

### Codespace上での起動

```bash
# Codespaceで初期設定
dr start

# 全サービスを起動
dr run dev
```

---

## Step 5: 動作確認

ブラウザで `http://localhost:5173`（または Codespace URL）にアクセスし、
以下のテストクエリを順番に試してください。

### テスト1: データスキーマ確認
```
このデータセットにはどんなカラムがありますか？
```
**期待結果**: `get_retail_data_schema` ツールが呼ばれ、カラム一覧が表示される

### テスト2: データクエリ (DARIA)
```
2024年のコンビニの月別売上を教えてください。
```
**期待結果**: DARIAツールがデータをクエリし、数値付きで回答

### テスト3: 需要予測
```
2026年4月のスーパーの売上を予測してください。
```
**期待結果**: `run_retail_forecast` ツールが呼ばれ、予測値が返される

### テスト4: 文書検索 (RAG)
```
日本のEC市場の成長率はどのくらいですか？
```
**期待結果**: `search_ec_market_documents` ツールがVDBを検索し、PDF引用付きで回答

### テスト5: 複合質問
```
百貨店の過去3年の売上推移と、来月の予測を比較して分析してください。
```
**期待結果**: DARIAツール + 予測ツールが併用される

---

## Step 6: デプロイ（本番環境）

```bash
# Pulumiでデプロイ
dr run deploy

# または
task infra:deploy
```

デプロイ後、DataRobot UIの「Agentic Playground」からエージェントにアクセスできます。

---

## よくあるエラーと対処法

| エラー | 原因 | 対処法 |
|---|---|---|
| `DataRobot client initialization failed` | APIトークンが無効 | `.env`の`DATAROBOT_API_TOKEN`を再確認 |
| `MCP tools not found` | MCPサーバー未起動 | `task mcp:start` を先に実行 |
| `Forecast deployment not configured` | デプロイメントID未設定 | `.env`の`FORECAST_DEPLOYMENT_ID`を確認 |
| `VDB deployment not configured` | VDB未デプロイ | Notebook 03を再実行 |
| `Prompt template not found` | テンプレートID不正 | Notebook 04でID再確認、またはデフォルトプロンプトにフォールバック |
| `Model prediction timeout` | デプロイメントがスリープ中 | DataRobot UIでデプロイメントのステータスを確認、ウォームアップ待ち |
| `Port already in use` | ポート競合 | `lsof -i :8842` で確認、既存プロセスを停止 |

---

## 補足: テーマ変更手順

デモテーマを変更する場合（例: 小売 → 電力、観光等）:

1. `setup/01_create_dataset.ipynb` を修正してデータ再生成
2. Notebook 02〜04 を再実行して新しいIDを取得
3. `mcp_server/app/tools/` のツール名・説明文を調整
4. DataRobot上のPrompt Templateを更新
5. `.env` を新しいIDで更新

**注意**: `agent/agent/myagent.py` や `agent/agent/config.py` は変更不要です（ドメイン非依存設計）。
