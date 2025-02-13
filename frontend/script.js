document.addEventListener('DOMContentLoaded', () => {
    const messageContainer = document.getElementById('messageContainer');
    const messageBox = document.getElementById('messageBox');
    const sendButton = document.getElementById('sendButton');
    const goalInput = document.getElementById('goalInput');
    const loadingIndicator = document.getElementById('loadingIndicator');

    // 会話の状態を管理
    let conversationState = {
        currentStage: 'INITIAL', // INITIAL, GOAL_EXTRACTED, PLANNING, SCHEDULING
        extractedGoal: null
    };

    // APIのベースURLを環境に応じて設定
    const baseUrl = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
        ? 'http://localhost:8000'
        : 'https://your-cloud-run-url.a.run.app';

    // Marked.jsの設定
    marked.setOptions({
        gfm: true,                // GitHub Flavored Markdown
        breaks: true,             // 改行を <br> として扱う
        pedantic: false,          // markdown.plに準拠しない
        sanitize: false,          // HTML入力を許可
        smartLists: true,         // よりスマートなリスト出力
        smartypants: true,        // 引用符や句読点の変換
        xhtml: false,             // XHTML出力を無効化
        highlight: function(code, lang) {
            if (lang && hljs.getLanguage(lang)) {
                try {
                    return hljs.highlight(code, { language: lang }).value;
                } catch (__) {}
            }
            return code;
        }
    });

    function showLoading() {
        loadingIndicator.classList.remove('hidden');
        messageBox.disabled = true;
        sendButton.disabled = true;
    }

    function hideLoading() {
        loadingIndicator.classList.add('hidden');
        messageBox.disabled = false;
        sendButton.disabled = false;
    }

    // メッセージを表示する関数
    function appendMessage(content, isUser) {
        const messageDiv = document.createElement('div');
        messageDiv.className = isUser ? 'user-message' : 'assistant-message';
        
        if (isUser) {
            messageDiv.textContent = content;
        } else {
            try {
                // Markdownをパースして装飾を適用
                const htmlContent = marked.parse(content.trim());
                messageDiv.innerHTML = htmlContent;

                // コードブロックにシンタックスハイライトを適用
                messageDiv.querySelectorAll('pre code').forEach((block) => {
                    hljs.highlightElement(block);
                });

                // リンクに target="_blank" を追加
                messageDiv.querySelectorAll('a').forEach(link => {
                    link.setAttribute('target', '_blank');
                    link.setAttribute('rel', 'noopener noreferrer');
                });
            } catch (error) {
                console.error('Markdown parsing error:', error);
                messageDiv.textContent = content; // エラー時は通常テキストとして表示
            }
        }
        
        messageContainer.appendChild(messageDiv);
        messageContainer.scrollTop = messageContainer.scrollHeight;
    }

    // バックエンドにメッセージを送信する関数
    async function sendMessage(message) {
        try {
            showLoading();
            const response = await fetch(`${baseUrl}/api/chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: message,
                    stage: conversationState.currentStage,
                    extractedGoal: conversationState.extractedGoal
                })
            });

            if (!response.ok) {
                throw new Error('API request failed');
            }

            const data = await response.json();
            
            // 会話の状態を更新
            if (data.stage) {
                conversationState.currentStage = data.stage;
            }
            if (data.extractedGoal) {
                conversationState.extractedGoal = data.extractedGoal;
            }

            // 次のステージに応じてプレースホルダーを更新
            updatePlaceholder();

            return data.response;
        } catch (error) {
            console.error('Error:', error);
            return 'エラーが発生しました。もう一度お試しください。';
        } finally {
            hideLoading();
        }
    }

    function updatePlaceholder() {
        const placeholders = {
            'INITIAL': 'あなたの目標を教えてください',
            'GOAL_EXTRACTED': '目標達成に向けて、現在の状況を教えてください',
            'PLANNING': '提案された計画について、より詳しく知りたい点はありますか？',
            'SCHEDULING': 'いつまでに達成したい目標ですか？'
        };
        messageBox.placeholder = placeholders[conversationState.currentStage] || 'メッセージを入力してください';
    }

    // 送信ボタンのクリックハンドラー
    sendButton.addEventListener('click', async () => {
        const message = messageBox.value.trim();
        const goal = goalInput.value.trim();
        
        if (!message) return;
        
        // ユーザーメッセージを表示
        appendMessage(message, true);
        
        // 入力欄をクリア
        messageBox.value = '';
        
        // バックエンドにメッセージを送信
        const response = await sendMessage(message);
        
        // アシスタントの返答を表示
        appendMessage(response, false);
    });

    // Enterキーでメッセージを送信
    messageBox.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendButton.click();
        }
    });
});