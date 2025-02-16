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

# ロギングの設定を詳細化
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 環境変数の読み込み
def load_environment_variables():
    required_vars = {
        'GROQ_API_KEY': None,
        'GOOGLE_CLIENT_ID': None,
        'GOOGLE_CLIENT_SECRET': None,
        'FIREBASE_PRIVATE_KEY': None,
        'FIREBASE_CLIENT_EMAIL': None,
        'GEMINI_API_KEY': None,
        'JWT_SECRET_KEY': None,
        'FRONTEND_URL': 'http://localhost:8000'  # デフォルト値を設定
    }

    env_values = {}
    for var, default in required_vars.items():
        value = os.getenv(var, default)
        if value is None:
            # 開発環境の場合はエラーを出さずに警告を表示
            if os.getenv('ENVIRONMENT') != 'production':
                logger.warning(f"Environment variable {var} is not set")
                value = 'dummy_value_for_development'
            else:
                raise ValueError(f"Required environment variable {var} is not set in production")
        env_values[var] = value

    return env_values

# FastAPIアプリケーションの設定
app = FastAPI(
    title="Goal Achievement Assistant API",
    description="An API for goal setting and achievement planning",
    version="1.0.0"
)

# フロントエンドのオリジンを設定
ALLOWED_ORIGINS = [
    # ローカル開発環境用
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    # Firebase Hosting本番環境用
    "https://planner0219.web.app",
    "https://planner0219.firebaseapp.com"
]

# CORSミドルウェアの設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],  # 必要なHTTPメソッドのみを許可
    allow_headers=["*"],
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

class PeriodPrediction(BaseModel):
    months: int
    confidence: float
    source_text: str
    prediction_reason: str

class ApprovalDecision(BaseModel):
    is_approved: bool
    confidence: float
    reasoning: str
    extracted_intent: str

class ReminderOverride(BaseModel):
    method: str  # "popup" or "email"
    minutes: int

class EventReminders(BaseModel):
    useDefault: bool = False
    overrides: list[ReminderOverride]

class EventPriority(str, Enum):
    LOW = "1"      # ラベンダー
    MEDIUM = "6"   # みかん
    HIGH = "11"    # トマト

class CalendarEvent(BaseModel):
    title: str
    description: str
    start_date: str
    end_date: str
    priority: EventPriority
    reminders: EventReminders

class CalendarSchedule(BaseModel):
    events: list[CalendarEvent]
    timezone: str = "Asia/Tokyo"

class GoalAnalysis(BaseModel):
    extracted_goal: str
    confidence: float
    suggestions: list[str]
    next_steps: list[str]

class PlanningAdvice(BaseModel):
    main_steps: list[str]
    required_resources: list[str]
    potential_challenges: list[str]
    mitigation_strategies: list[str]

class PeriodAnalysis(BaseModel):
    period_months: int
    confidence: float
    reasoning: str
    milestones: list[str]

class SchedulePlan(BaseModel):
    milestones: list[dict[str, str]]  # { "title": str, "deadline": str }
    monthly_goals: list[dict[str, str]]  # { "month": str, "goals": str }
    weekly_tasks: list[dict[str, list[str]]]  # { "week": str, "tasks": list[str] }
    time_estimates: dict[str, str]  # task_name: estimated_time
    review_points: list[dict[str, str]]  # { "timing": str, "focus": str }

class StageTransitionResult(BaseModel):
    can_proceed: bool
    confidence: float
    required_info: list[str] | None = None
    next_stage: ConversationStage
    reason: str

class ConversationContext(BaseModel):
    current_stage: ConversationStage
    extracted_goal: str | None
    target_date: str | None
    schedule_data: SchedulePlan | None = None
    calendar_data: CalendarSchedule | None = None

async def extract_period_with_gemini(message: str, client: genai.Client) -> int | None:
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=f"ユーザーの入力から目標達成の期間を抽出してください。入力: {message}",
            config={
                'response_mime_type': 'application/json',
                'response_schema': PeriodPrediction,
            }
        )
        
        result: PeriodPrediction = response.parsed
        if result and result.confidence >= 0.6:
            return result.months
        return None
    except Exception as e:
        logger.error(f"Error extracting period with Gemini: {e}")
        return None

async def analyze_user_approval(message: str, client: genai.Client) -> bool:
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=f"ユーザーの回答からスケジュールの承認状態を判断してください。入力: {message}",
            config={
                'response_mime_type': 'application/json',
                'response_schema': ApprovalDecision,
            }
        )
        
        result: ApprovalDecision = response.parsed
        return result.is_approved if result and result.confidence >= 0.6 else False
    except Exception as e:
        logger.error(f"Error analyzing user approval: {e}")
        return False

async def generate_calendar_events(goal: str, target_date: str, client: genai.Client) -> CalendarSchedule:
    current_date = datetime.now()
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=f"""
                目標「{goal}」のためのカレンダーイベントを生成します。
                開始日: {current_date.strftime('%Y-%m-%d')}
                終了日: {target_date}

                目標を達成するために必要なマイルストーンとタスクを作成してください。
                イベントの重要度は以下から選択してください：
                - LOW (1, ラベンダー): 通常のタスク
                - MEDIUM (6, みかん): 重要なマイルストーン
                - HIGH (11, トマト): 重要な締め切りや目標達成に不可欠なタスク
            """,
            config={
                'response_mime_type': 'application/json',
                'response_schema': CalendarSchedule,
            }
        )
        
        return response.parsed
    except Exception as e:
        logger.error(f"Error generating calendar events: {e}")
        raise

async def validate_stage_transition(
    current_stage: ConversationStage,
    message: str,
    context: ConversationContext,
    client: genai.Client
) -> StageTransitionResult:
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=f"""
            現在のステージ: {current_stage}
            目標: {context.extracted_goal or "未設定"}
            期間: {context.target_date or "未設定"}
            ユーザーの入力: {message}

            現在のステージから次のステージに進めるか判断してください。
            必要な情報が不足している場合は、required_infoに必要な情報を列挙してください。
            """,
            config={
                'response_mime_type': 'application/json',
                'response_schema': StageTransitionResult,
            }
        )
        return response.parsed
    except Exception as e:
        logger.error(f"Error validating stage transition: {e}")
        return StageTransitionResult(
            can_proceed=False,
            confidence=0.0,
            next_stage=current_stage,
            reason=f"エラーが発生しました: {str(e)}"
        )

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        # 会話コンテキストの作成
        context = ConversationContext(
            current_stage=request.stage,
            extracted_goal=request.extractedGoal,
            target_date=request.targetDate
        )

        # ステージ遷移の検証
        transition = await validate_stage_transition(
            request.stage,
            request.message,
            context,
            client
        )

        if not transition.can_proceed and transition.required_info:
            required_info_list = '\n'.join(f"- {info}" for info in transition.required_info)
            return ChatResponse(
                response=f"次のステージに進むには、以下の情報が必要です：\n{required_info_list}",
                stage=request.stage,
                extractedGoal=context.extracted_goal,
                targetDate=context.target_date
            )

        # 既存の各ステージの処理を続ける...
        if request.stage == ConversationStage.INITIAL:
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=f"ユーザーの入力から具体的な目標を抽出し、分析してください。入力: {request.message}",
                config={
                    'response_mime_type': 'application/json',
                    'response_schema': GoalAnalysis,
                }
            )
            result: GoalAnalysis = response.parsed
            
            suggestions_list = '\n'.join(f"- {s}" for s in result.suggestions)
            next_steps_list = '\n'.join(f"- {s}" for s in result.next_steps)
            response_text = f"""抽出した目標: {result.extracted_goal}

提案:
{suggestions_list}

次のステップ:
{next_steps_list}"""
            next_stage = ConversationStage.GOAL_EXTRACTED
            extracted_goal = result.extracted_goal

        elif request.stage == ConversationStage.GOAL_EXTRACTED:
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=f"""
目標: {extracted_goal}
ユーザーの入力: {request.message}

目標達成のための具体的な実行プランを分析してください。
""",
                config={
                    'response_mime_type': 'application/json',
                    'response_schema': PlanningAdvice,
                }
            )
            result: PlanningAdvice = response.parsed
            
            main_steps_list = '\n'.join(f"- {s}" for s in result.main_steps)
            resources_list = '\n'.join(f"- {s}" for s in result.required_resources)
            challenges_list = '\n'.join(f"- {s}" for s in result.potential_challenges)
            strategies_list = '\n'.join(f"- {s}" for s in result.mitigation_strategies)
            
            response_text = f"""実行プラン:

主要なステップ:
{main_steps_list}

必要なリソース:
{resources_list}

予想される課題:
{challenges_list}

対策:
{strategies_list}

このプランについて、ご意見やさらに詳しく知りたい点はありますか？"""
            next_stage = ConversationStage.PLANNING

        elif request.stage == ConversationStage.PLANNING:
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=f"""
                目標: {extracted_goal}
                ユーザーの入力: {request.message}
                
                ユーザーの回答から目標達成に必要な期間を分析し、主要なマイルストーンを提案してください。
                """,
                config={
                    'response_mime_type': 'application/json',
                    'response_schema': PeriodAnalysis,
                }
            )
            result: PeriodAnalysis = response.parsed
            
            if result.confidence >= 0.6:
                target_date = (current_date + timedelta(days=30.44 * result.period_months)).strftime('%Y-%m-%d')
                milestones_list = '\n'.join(f"- {m}" for m in result.milestones)
                response_text = f"""目標達成までの期間を{result.period_months}ヶ月と設定しました。

判断理由:
{result.reasoning}

主要なマイルストーン:
{milestones_list}

この期間設定で具体的なスケジュールを作成していきましょう。"""
                next_stage = ConversationStage.SCHEDULING
            else:
                response_text = "目標達成までの具体的な期間を教えていただけますか？（例：3ヶ月、半年、1年など）"
                next_stage = ConversationStage.PLANNING

        elif request.stage == ConversationStage.SCHEDULING:
            current_date = datetime.now()
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=f"""
                目標: {extracted_goal}
                期間: {current_date.strftime('%Y-%m-%d')} から {target_date} まで
                ユーザーの入力: {request.message}
                
                詳細なスケジュールと実行計画を作成してください。
                """,
                config={
                    'response_mime_type': 'application/json',
                    'response_schema': SchedulePlan,
                }
            )
            result: SchedulePlan = response.parsed
            
            milestones_text = '\n'.join(f"- {m['title']}: {m['deadline']}" for m in result.milestones)
            monthly_goals_text = '\n'.join(f"- {g['month']}: {g['goals']}" for g in result.monthly_goals)
            weekly_tasks_text = '\n'.join(f"【{w['week']}】\n" + '\n'.join(f"- {t}" for t in w['tasks']) for w in result.weekly_tasks)
            time_estimates_text = '\n'.join(f"- {task}: {time}" for task, time in result.time_estimates.items())
            review_points_text = '\n'.join(f"- {r['timing']}: {r['focus']}" for r in result.review_points)

            response_text = f"""スケジュール案を作成しました。

主要なマイルストーン:
{milestones_text}

月別の目標:
{monthly_goals_text}

週別のタスク:
{weekly_tasks_text}

タスクの所要時間目安:
{time_estimates_text}

進捗確認のポイント:
{review_points_text}

このスケジュールをカレンダーに登録しますか？"""
            next_stage = ConversationStage.CONFIRM_SCHEDULE

        elif request.stage == ConversationStage.CONFIRM_SCHEDULE:
            # ユーザーの承認を解析
            is_approved = await analyze_user_approval(request.message, client)
            
            if is_approved:
                # カレンダーイベントを生成
                calendar_schedule = await generate_calendar_events(
                    extracted_goal,
                    target_date,
                    client
                )
                
                # レスポンスにカレンダーデータを含める
                response_text = f"""
                カレンダーのイベントを生成しました。以下の内容で登録を進めます：

                {len(calendar_schedule.events)}件のイベントを作成
                期間: {calendar_schedule.events[0].start_date} から {calendar_schedule.events[-1].end_date}

                カレンダー連携の準備が整いました。続けてもよろしいですか？
                """
                # カレンダーデータをログに記録（デバッグ用）
                logger.info(f"Generated calendar events: {calendar_schedule.json()}")
            else:
                response_text = "承知しました。他に質問や確認したいことはありますか？"

            response = genai.types.Content(text=response_text)

        return ChatResponse(
            response=response_text if 'response_text' in locals() else response.text,
            stage=transition.next_stage if transition.can_proceed else request.stage,
            extractedGoal=context.extracted_goal,
            targetDate=context.target_date
        )
    
    except Exception as e:
        logger.error(f"Error processing chat request: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.on_event("startup")
async def startup_event():
    """アプリケーション起動時の初期化処理"""
    logger.info("Application starting up")
    try:
        # 環境変数の読み込みと検証
        env_values = load_environment_variables()
        logger.info("Environment variables loaded successfully")
        
        # Gemini APIの初期化
        global client
        client = genai.Client(api_key=env_values["GEMINI_API_KEY"])
        logger.info("Gemini API client initialized successfully")
        
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise

@app.get("/health")
async def health_check():
    """詳細なヘルスチェックエンドポイント"""
    try:
        # Gemini APIの接続テスト
        response = client.models.list()
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "environment": "Cloud Run" if os.getenv("K_SERVICE") else "Local",
            "api_status": "connected"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Service unhealthy: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="debug")