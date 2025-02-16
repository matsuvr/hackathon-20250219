<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" class="logo" width="120"/>

# Firebaseを活用したGoogleカレンダー連携プロトタイプの設計と実装

---

## 要約

本設計は、Firebase Authenticationを用いたGoogle認証基盤とGemini AI連携による自然言語処理機能を統合したカレンダー管理システムのプロトタイプ実装を示す。フロントエンドはFirebase Hosting、バックエンドはCloud Run上のFastAPIを採用し、最小限のセキュリティ対策を施した短期利用向けアーキテクチャを構築する。主要コンポーネント間の連携フローを明確化し、実用的なコードサンプルを提示する[^1][^4]。

## システムアーキテクチャ設計

### 全体構成図

```
[ユーザー]
  │
  ↓ HTTPS
[Firebase Hosting (HTML/JS)]
  │  ▲
  │  │ Firebase Auth
  ↓  │ Google Calendar API
[Cloud Run (FastAPI)]
  │  ▲
  │  │ Gemini API
  ↓  │
[Google Cloud Services]
```


### 認証フロー設計

1. クライアント側Google認証（Firebase Auth SDK）
2. IDトークンのバックエンド検証
3. カレンダーAPIアクセストークンの取得
4. Gemini API連携処理
5. カレンダーイベント生成[^2][^4]

## フロントエンド実装

### Firebase初期化設定

```html
<!-- index.html -->
<script type="module">
  import { initializeApp } from "https://www.gstatic.com/firebasejs/10.4.0/firebase-app.js";
  import { getAuth, GoogleAuthProvider, signInWithPopup } from "https://www.gstatic.com/firebasejs/10.4.0/firebase-auth.js";

  const firebaseConfig = {
    apiKey: "YOUR_API_KEY",
    authDomain: "your-project.firebaseapp.com",
    projectId: "your-project",
    storageBucket: "your-project.appspot.com",
    messagingSenderId: "YOUR_SENDER_ID",
    appId: "YOUR_APP_ID"
  };

  const app = initializeApp(firebaseConfig);
  const auth = getAuth(app);
  
  // カレンダースコープ追加
  const provider = new GoogleAuthProvider();
  provider.addScope('https://www.googleapis.com/auth/calendar.events');
</script>
```


### 認証UIコンポーネント

```javascript
// ログインハンドラ
async function handleLogin() {
  try {
    const result = await signInWithPopup(auth, provider);
    const credential = GoogleAuthProvider.credentialFromResult(result);
    const calendarToken = credential.accessToken;
    
    localStorage.setItem('calendarToken', calendarToken);
    localStorage.setItem('userId', result.user.uid);
    
  } catch (error) {
    console.error('Authentication failed:', error);
  }
}

// イベント作成フォーム
document.getElementById('eventForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const textInput = document.getElementById('eventText').value;
  
  const response = await fetch('https://your-cloud-run-url/parse-event', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${await auth.currentUser.getIdToken()}`
    },
    body: JSON.stringify({
      text: textInput,
      calendarToken: localStorage.getItem('calendarToken')
    })
  });
  
  const result = await response.json();
  if(result.success) {
    alert('イベント作成成功');
  }
});
```


## バックエンド実装（FastAPI）

### 依存関係設定

```python
# requirements.txt
fastapi>=0.68.0
uvicorn>=0.15.0
google-generativeai>=0.3.0
firebase-admin>=6.0.0
python-dotenv>=0.19.0
httpx>=0.23.0
```


### Firebase認証検証

```python
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer
from firebase_admin import auth, credentials
import google.generativeai as genai

security = HTTPBearer()
cred = credentials.Certificate("path/to/serviceAccountKey.json")
firebase_admin.initialize_app(cred)

async def verify_token(token: str = Depends(security)):
    try:
        decoded_token = auth.verify_id_token(token.credentials)
        return decoded_token
    except Exception as e:
        raise HTTPException(status_code=403, detail="Invalid token")
```


### Gemini連携処理

```python
# Gemini設定
genai.configure(api_key="YOUR_GEMINI_KEY")
model = genai.GenerativeModel('gemini-pro')

def parse_event_text(text: str):
    prompt = f"""
    以下のテキストからカレンダーイベントを抽出し、JSON形式で返してください。
    フォーマット:
    {{
      "summary": "イベントタイトル",
      "description": "詳細説明",
      "start": {{"dateTime": "ISO形式"}},
      "end": {{"dateTime": "ISO形式"}}
    }}
    
    テキスト: {text}
    """
    
    try:
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except Exception as e:
        raise HTTPException(status_code=400, detail="解析失敗")
```


### カレンダーAPI連携

```python
from httpx import AsyncClient

async def create_calendar_event(event_data: dict, calendar_token: str):
    async with AsyncClient() as client:
        response = await client.post(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            headers={
                "Authorization": f"Bearer {calendar_token}",
                "Content-Type": "application/json"
            },
            json=event_data
        )
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=response.json()
            )
        return response.json()
```


## デプロイ設定

### Dockerfile

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```


### Cloud Runデプロイコマンド

```bash
gcloud run deploy calendar-service \
  --source . \
  --platform managed \
  --region asia-northeast1 \
  --allow-unauthenticated
```


## セキュリティ対策（最小構成）

### 必須対策項目

1. HTTPS強制（Firebase Hosting設定）
2. CORS制限（FastAPIミドルウェア）
3. APIキー環境変数管理
4. トークン有効期限検証（1時間）
5. 入力値サニタイズ（Geminiプロンプト）
```python
# CORS設定例
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-firebase-app.web.app"],
    allow_methods=["POST"],
    allow_headers=["Authorization"]
)
```


## プロトタイプ検証フロー

### テストシナリオ

1. フロントエンド認証成功 → カレンダートークン取得確認
2. 自然言語入力例 → 「来週月曜15時から1時間ミーティング」
3. Geminiレスポンス検証 → ISOフォーマット変換確認
4. カレンダー登録結果確認 → GoogleカレンダーUIチェック

### デバッグ手法

```javascript
// フロントエンドデバッグ
console.log('Calendar Token:', calendarToken);
// レスポンス詳細表示
.then(response => {
  console.log('API Response:', response);
  return response.json();
})
```


## 拡張可能な設計ポイント

### 今後の拡張性

1. 複数カレンダー対応（カレンダーIDパラメータ追加）
2. リマインダー設定（Geminiプロンプト拡張）
3. イベントテンプレート機能
4. チームメンバー招待機能

### パフォーマンス改善案

```python
# Geminiキャッシュ実装例
from functools import lru_cache

@lru_cache(maxsize=100)
def cached_gemini_query(prompt: str):
    return model.generate_content(prompt)
```


## 障害対応ガイド

### 想定エラーケース

1. カレンダートークン失効 → 再認証フロー誘導
2. Gemini解析失敗 → 代替入力フォーム表示
3. APIレートリミット → エラーハンドリング実装
```javascript
// トークンリフレッシュハンドラ
async function refreshToken() {
  const user = auth.currentUser;
  if (user) {
    const newToken = await user.getIdToken(true);
    localStorage.setItem('calendarToken', newToken);
  }
}
```


## 結論

本設計はFirebaseエコシステムを中核に据え、短期開発向けに最適化したカレンダー連携プロトタイプの実現可能性を実証した。ハッカソンイベント向けに重要な迅速な開発サイクルを実現しつつ、拡張性を維持するアーキテクチャ設計が特徴的である[^3][^4]。今後の展開として、実際のユースケースに即した追加機能の実装と、エラーハンドリングの強化が期待される。

<div style="text-align: center">⁂</div>

[^1]: https://qiita.com/567000/items/1fc9857a36fae34f574e

[^2]: https://www.topgate.co.jp/blog/google-service/6884

[^3]: https://qiita.com/rf_p/items/809da9cc7cae607ef632

[^4]: https://zenn.dev/tatsuyasusukida/articles/firebase-auth-google

[^5]: https://firebase.google.com/docs/auth/web/start?hl=ja

[^6]: https://firebase.google.com/docs/hosting/reserved-urls?hl=ja

[^7]: https://zenn.dev/tatsuyasusukida/articles/firebase-auth-email

[^8]: https://tech.adseed.co.jp/firebase deploy Hands-on

[^9]: https://www.topgate.co.jp/blog/google-service/6587

[^10]: https://www.tsone.co.jp/tech-blog/archives/1342

