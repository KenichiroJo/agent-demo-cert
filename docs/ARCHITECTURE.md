# 小売・EC売上需要予測 AIエージェント アーキテクチャ

## 概要

本プロジェクトは、DataRobot上で動作する**小売・EC売上需要予測AIエージェント**です。
経済産業省「商業動態統計」をベースとした時系列データと、EC市場調査レポート等のPDF文献を活用し、
データ分析・売上予測・市場トレンド調査を自然言語で行えるエージェントを提供します。

## アーキテクチャ方針

- **エージェントフレームワーク**: LangGraph (`LangGraphAgent`継承)
- **フロントサーバー**: FastAPI + NAT対応 (`NATAGUIAgent` / `enable_nat_server`トグル)
- **dragentモード**: `ENABLE_DRAGENT_SERVER=true` でDataRobot Agent Runtime (dragent) モードに切替可能
  - `agent/agent/register.py` + `agent/agent/workflow.yaml` でNAT登録
  - `@register_function` デコレータでLangGraphワークフローをdragentに統合
  - LLMインスタンスはNATビルダーから `llm` パラメータ経由で注入
- **ツール連携**: MCP (Model Context Protocol) 経由
- **デプロイ先**: DataRobot Codespace / Serverless Deployment
- **IaC**: Pulumi

## システム構成図

```
┌─────────────────────────────────────────────────────┐
│                    Frontend (React)                   │
│                   frontend_web/                       │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP
┌──────────────────────▼──────────────────────────────┐
│              FastAPI Server (NAT対応)                 │
│              fastapi_server/                          │
│  ┌─────────────────────────────────────────────┐    │
│  │  NATAGUIAgent / DataRobotAGUIAgent          │    │
│  └──────────────────┬──────────────────────────┘    │
└──────────────────────┬──────────────────────────────┘
                       │ AG-UI / Chat Completions
┌──────────────────────▼──────────────────────────────┐
│            LangGraph Agent (MyAgent)                  │
│            agent/agent/myagent.py                     │
│                                                       │
│  ┌────────────────────────────────────────────┐     │
│  │  assistant_node (ReAct Agent)               │     │
│  │  - システムプロンプト: prompt_manager.py    │     │
│  │  - LLM: DataRobot LLM Gateway              │     │
│  │  - ツール: MCP経由で3種のツールにアクセス   │     │
│  └────────────────┬───────────────────────────┘     │
└────────────────────┬────────────────────────────────┘
                     │ MCP Protocol
┌────────────────────▼────────────────────────────────┐
│              MCP Server (FastMCP)                     │
│              mcp_server/                              │
│                                                       │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐│
│  │ user_tools   │ │forecast_tools│ │document_tools ││
│  │ データスキーマ│ │ 需要予測     │ │ 文書検索(RAG)││
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘│
└─────────┼────────────────┼────────────────┼─────────┘
          │                │                │
          ▼                ▼                ▼
  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
  │ DARIA        │ │ AutoTS       │ │ Vector DB    │
  │ (データクエリ)│ │ Deployment   │ │ Deployment   │
  │              │ │ (時系列予測)  │ │ (PDF RAG)    │
  └──────────────┘ └──────────────┘ └──────────────┘
       DataRobot Platform Deployments
```

## エージェントの3つの能力

| 能力 | MCPツール | DataRobotリソース | ユースケース |
|---|---|---|---|
| **データ分析** | `get_retail_data_schema` + DARIA | DARIAデプロイメント | 過去の売上データ照会・集計 |
| **需要予測** | `run_retail_forecast` | AutoTSデプロイメント | 将来の売上予測 |
| **文書検索** | `search_ec_market_documents` | VDBデプロイメント | EC市場トレンド・レポート検索 |

## データセット設計

### 時系列データ (retail_sales_dataset.csv)

- **ソース**: 経済産業省「商業動態統計」ベース
- **期間**: 2015年1月〜2025年12月 (132ヶ月)
- **業態**: 百貨店、スーパー、コンビニ、ドラッグストア、EC
- **ターゲット**: `sales_billion_yen` (月次販売額、十億円)
- **特徴量**: 季節フラグ(ボーナス月、GW、年末)、消費者態度指数、CPI、気温、失業率、祝日数

### PDF文献 (VDB用)

- 経済産業省「電子商取引に関する市場調査」
- 総務省「家計調査」概要

## ディレクトリ構成

```
datarobot-agent-application-main2/
├── setup/                          # Phase 0: プラットフォーム準備Notebook
│   ├── 01_create_dataset.ipynb     # データセット生成・アップロード
│   ├── 02_build_timeseries_model.ipynb  # AutoTSモデル構築・デプロイ
│   ├── 03_create_vdb.ipynb         # PDF → VDB作成・デプロイ
│   └── 04_setup_prompt_and_mcp.ipynb    # プロンプト・MCP設定
├── data/                           # 生成データ
│   └── retail_sales_dataset.csv
├── documents/                      # PDF文献
│   └── (PDFファイル)
├── agent/                          # エージェント実装
│   └── agent/
│       ├── myagent.py              # メインエージェント (LangGraph)
│       ├── config.py               # 設定クラス
│       ├── prompt_manager.py       # プロンプト管理
│       ├── register.py             # NAT/dragent登録 (@register_function)
│       └── workflow.yaml           # dragentワークフロー定義
├── mcp_server/                     # MCPサーバー
│   └── app/
│       ├── tools/
│       │   ├── user_tools.py       # データスキーマツール
│       │   ├── forecast_tools.py   # 需要予測ツール
│       │   └── document_tools.py   # 文書検索ツール
│       └── core/
│           └── user_config.py      # MCP設定
├── fastapi_server/                 # FastAPIバックエンド
├── frontend_web/                   # Reactフロントエンド
├── infra/                          # Pulumiインフラ
│   └── infra/
│       ├── agent.py                # エージェントデプロイ設定
│       └── mcp_server_user_params.py  # MCPパラメータ
├── docs/                           # ドキュメント
│   ├── ARCHITECTURE.md             # 本ドキュメント
│   └── STARTUP_GUIDE.md            # 立ち上げ手順書
└── .env.template                   # 環境変数テンプレート
```

## 環境変数一覧

| 変数名 | 用途 | 設定タイミング |
|---|---|---|
| `DATAROBOT_API_TOKEN` | DataRobot API認証 | 初期設定 |
| `DATAROBOT_ENDPOINT` | DataRobot APIエンドポイント | 初期設定 |
| `PROMPT_TEMPLATE_ID` | バージョン管理プロンプトID | Notebook 04実行後 |
| `FORECAST_DEPLOYMENT_ID` | 時系列予測デプロイメントID | Notebook 02実行後 |
| `SCORING_DATASET_ID` | スコアリングデータセットID | Notebook 02実行後 |
| `VDB_DEPLOYMENT_ID` | ベクターDBデプロイメントID | Notebook 03実行後 |
| `MCP_DEPLOYMENT_ID` | MCPサーバーデプロイメントID | デプロイ後自動設定 |
| `COMPANY_NAME` | エージェント表示名 | 任意 |
| `ENABLE_DRAGENT_SERVER` | dragentモード有効化 (`true`/`false`) | 任意（デフォルト: `false`） |

## テーマ変更ガイド

本エージェントはドメイン非依存設計です。テーマ変更時の影響範囲：

| 変更対象 | 変更内容 |
|---|---|
| `data/retail_sales_dataset.csv` | データ再生成 |
| `setup/01_create_dataset.ipynb` | カラム・トレンド修正 |
| `mcp_server/app/tools/` | ツール名・説明文の調整 |
| Prompt Template (DataRobot) | システムプロンプト更新 |
| `docs/` | ドキュメント更新 |

**変更不要なファイル**: `agent/agent/myagent.py`, `agent/agent/config.py`, `agent/agent/prompt_manager.py`
（エージェントのコアロジックはドメインに依存しません）
