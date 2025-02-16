from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai
from dotenv import load_dotenv
import os
import logging
from enum import Enum
from datetime import datetime, timedelta
import re

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
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is not set in environment variables or .env file")

try:
    # 新しいSDKの使用方法に更新
    client = genai.Client(api_key=GEMINI_API_KEY)
except Exception as e:
    logger.error(f"Failed to configure Gemini API: {e}")
    raise

app = FastAPI()

# WSL2環境でのアクセスを考慮したCORS設定
ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:5000",
    "http://127.0.0.1:5000",
    "http://localhost:3000",  # React開発サーバー用
    "http://127.0.0.1:3000",
    # WSL2のIPアドレス範囲からのアクセスを許可
    "http://172.16.0.0:8000",
    "http://172.17.0.0:8000",
    "http://172.18.0.0:8000",
    "http://172.19.0.0:8000",
    "http://172.20.0.0:8000",
    "http://172.21.0.0:8000",
    "http://172.22.0.0:8000",
    "http://172.23.0.0:8000",
    "http://172.24.0.0:8000",
    "http://172.25.0.0:8000"
]

# より寛容なCORSミドルウェアの設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # すべてのオリジンを許可
    allow_credentials=True,
    allow_methods=["*"],  # すべてのHTTPメソッドを許可
    allow_headers=["*"],  # すべてのヘッダーを許可
)

class ConversationStage(str, Enum):
    INITIAL = "INITIAL"
    GOAL_EXTRACTED = "GOAL_EXTRACTED"
    PLANNING = "PLANNING"
    SCHEDULING = "SCHEDULING"
    CONFIRM_SCHEDULE = "CONFIRM_SCHEDULE"

class ChatRequest(BaseModel):
    message: str
    stage: ConversationStage = ConversationStage.INITIAL
    extractedGoal: str | None = None
    targetDate: str | None = None

class ChatResponse(BaseModel):
    response: str
    stage: ConversationStage
    extractedGoal: str | None = None
    targetDate: str | None = None

class PeriodExtraction(BaseModel):
    months: int
    confidence: float
    explanation: str

async def extract_period_with_gemini(message: str, client: genai.Client) -> int | None:
    prompt = f"""
    ユーザーの入力から目標達成の期間を抽出してください。
    入力: {message}

    以下の形式のJSONで返答してください：
    - months: 月数（年の場合は12を掛けて月数に変換）
    - confidence: 抽出の確信度（0.0から1.0）
    - explanation: 抽出理由の説明

    例:
    "1年後までに" → {{"months": 12, "confidence": 0.9, "explanation": "明確に1年と指定されている"}}
    "来年の夏まで" → {{"months": 12, "confidence": 0.7, "explanation": "おおよそ1年として解釈"}}
    """

    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
            config={
                'response_mime_type': 'application/json',
                'response_schema': PeriodExtraction,
            }
        )
        
        result: PeriodExtraction = response.parsed
        if result.confidence >= 0.6:  # 確信度が60%以上の場合のみ採用
            return result.months
        return None
    except Exception as e:
        logger.error(f"Error extracting period with Gemini: {e}")
        return None

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        stage = request.stage
        next_stage = stage
        extracted_goal = request.extractedGoal
        target_date = request.targetDate
        current_date = datetime.now()

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
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt
            )
            next_stage = ConversationStage.GOAL_EXTRACTED
            extracted_goal = response.text

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
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt
            )
            next_stage = ConversationStage.PLANNING

        elif stage == ConversationStage.PLANNING:
            prompt = f"""
            目標: {extracted_goal}
            今日の日付: {current_date.strftime('%Y年%m月%d日')}
            
            この目標をどれくらいの期間で達成したいか、具体的な期間を確認してください。
            ユーザーの回答から期間が明確でない場合は、以下のように質問してください：
            「具体的な目標期間を教えていただけますか？（例：3ヶ月、半年、1年など）」
            
            ユーザーの入力: {request.message}
            """
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt
            )
            
            # Geminiを使用した期間抽出
            period_months = await extract_period_with_gemini(request.message, client)
            if period_months:
                target_date = (current_date + timedelta(days=30.44 * period_months)).strftime('%Y-%m-%d')
                next_stage = ConversationStage.SCHEDULING
            else:
                next_stage = ConversationStage.PLANNING

        elif stage == ConversationStage.SCHEDULING:
            if not target_date:
                target_date = (current_date + timedelta(days=365)).strftime('%Y-%m-%d')
            
            prompt = f"""
            目標: {extracted_goal}
            期間: {current_date.strftime('%Y年%m月%d日')} から {datetime.strptime(target_date, '%Y-%m-%d').strftime('%Y年%m月%d日')} まで
            
            具体的なスケジュールと実行計画を作成します。
            以下の要素を必ず含めて、箇条書きで明確に回答してください：

            1. 全体スケジュール
            - 主要なマイルストーンと期限
            - 月単位の達成目標
            
            2. 詳細なタスク
            - 週単位でのタスク一覧
            - 各タスクの所要時間の目安
            
            3. 進捗管理方法
            - 定期的な振り返りのタイミング
            - 進捗測定の具体的な方法
            
            回答の最後に「このスケジュールをカレンダーに登録しますか？」と付け加えてください。
            
            ユーザーの入力: {request.message}
            """
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt
            )
            next_stage = ConversationStage.CONFIRM_SCHEDULE

        elif stage == ConversationStage.CONFIRM_SCHEDULE:
            prompt = f"""
            ユーザーがスケジュールのカレンダー登録について返答しました。
            
            もしユーザーが登録を希望する場合:
            「カレンダー連携の準備が整いました。続けてもよろしいですか？」と返答してください。
            
            もしユーザーが登録を希望しない場合:
            「承知しました。他に質問や確認したいことはありますか？」と返答してください。
            
            ユーザーの入力: {request.message}
            """
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt
            )

        return ChatResponse(
            response=response.text,
            stage=next_stage,
            extractedGoal=extracted_goal,
            targetDate=target_date
        )
    
    except Exception as e:
        logger.error(f"Error processing chat request: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """ヘルスチェックエンドポイント"""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="debug")