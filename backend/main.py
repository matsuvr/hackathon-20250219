from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import google.generativeai as genai
from dotenv import load_dotenv
import os
import logging
from enum import Enum

# ロギングの設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 環境変数の読み込み
# .envファイルが存在しない場合は環境変数から直接読み込む
if os.path.exists(".env"):
    logger.info("Loading .env file")
    try:
        load_dotenv(encoding='utf-8')  # エンコーディングを明示的に指定
    except UnicodeDecodeError:
        # UTF-8で読めない場合はcp932（Shift-JIS）で試行
        logger.info("Retrying with cp932 encoding")
        load_dotenv(encoding='cp932')
    except Exception as e:
        logger.error(f"Error loading .env file: {e}")
        raise
else:
    logger.info(".env file not found, using environment variables")

# Gemini APIの設定
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY is not set in environment variables or .env file")

try:
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash')
except Exception as e:
    logger.error(f"Failed to configure Gemini API: {e}")
    raise

app = FastAPI()

# 許可するオリジン
ALLOWED_ORIGINS = [
    "https://YOUR-PROJECT-ID.web.app",  # Firebase Hostingのドメイン（デプロイ後に実際のドメインに置き換え）
    "https://YOUR-PROJECT-ID.firebaseapp.com",  # Firebase Hostingの代替ドメイン
    "http://localhost:8000",  # ローカル開発用
    "http://localhost:5000"   # Firebase エミュレータ用
]

# CORSミドルウェアの設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["POST"],
    allow_headers=["*"],
)

class ConversationStage(str, Enum):
    INITIAL = "INITIAL"
    GOAL_EXTRACTED = "GOAL_EXTRACTED"
    PLANNING = "PLANNING"
    SCHEDULING = "SCHEDULING"

class ChatRequest(BaseModel):
    message: str
    stage: ConversationStage = ConversationStage.INITIAL
    extractedGoal: str | None = None

class ChatResponse(BaseModel):
    response: str
    stage: ConversationStage
    extractedGoal: str | None = None

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        stage = request.stage
        next_stage = stage
        extracted_goal = request.extractedGoal

        # ステージに応じたプロンプトの作成
        if stage == ConversationStage.INITIAL:
            prompt = f"""
            ユーザーの入力から具体的な目標を抽出してください。
            以下の点に注意してください：
            - 目標が曖昧な場合は、より具体的な目標を提案してください
            - 目標は測定可能で達成可能なものにしてください
            - 抽出した目標を最初に明確に示し、その後でアドバイスを提供してください

            ユーザーの入力: {request.message}
            """
            response = model.generate_content(prompt)
            # 最初の応答から目標を抽出した後は次のステージへ
            next_stage = ConversationStage.GOAL_EXTRACTED
            # 目標を抽出（実際のプロジェクトではより洗練された抽出ロジックを実装する）
            extracted_goal = request.message

        elif stage == ConversationStage.GOAL_EXTRACTED:
            prompt = f"""
            目標: {extracted_goal}
            
            ユーザーの現状を踏まえて、目標達成のための具体的な実行プランを提案してください。
            以下の点を含めてアドバイスしてください：
            - 目標達成のための主要なステップ
            - 必要なリソースや準備
            - 予想される課題と対処方法
            
            ユーザーの入力: {request.message}
            """
            response = model.generate_content(prompt)
            next_stage = ConversationStage.PLANNING

        elif stage == ConversationStage.PLANNING:
            prompt = f"""
            目標: {extracted_goal}
            
            ユーザーの質問や懸念に対して、より詳細な実践的アドバイスを提供してください。
            具体的なスケジューリングのために、以下の情報を収集することを意識してください：
            - 目標達成の期限
            - 週単位でどのように時間を確保するか
            - 進捗の測定方法
            
            ユーザーの入力: {request.message}
            """
            response = model.generate_content(prompt)
            next_stage = ConversationStage.SCHEDULING

        elif stage == ConversationStage.SCHEDULING:
            prompt = f"""
            目標: {extracted_goal}
            
            具体的なスケジュールと実行計画を作成します。
            以下の要素を含めて回答してください：
            - 週単位のタスク分解
            - 具体的なマイルストーン
            - 進捗確認のタイミング
            - モチベーション維持のためのアドバイス
            
            ユーザーの入力: {request.message}
            """
            response = model.generate_content(prompt)
            # スケジューリング後も同じステージを維持
            next_stage = ConversationStage.SCHEDULING

        return ChatResponse(
            response=response.text,
            stage=next_stage,
            extractedGoal=extracted_goal
        )
    
    except Exception as e:
        logger.error(f"Error processing chat request: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """ヘルスチェックエンドポイント"""
    return {"status": "healthy"}