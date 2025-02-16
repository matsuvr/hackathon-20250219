document.addEventListener('DOMContentLoaded', () => {
    const messageContainer = document.getElementById('messageContainer');
    const messageBox = document.getElementById('messageBox');
    const sendButton = document.getElementById('sendButton');
    const loadingIndicator = document.getElementById('loadingIndicator');

    // Marked.jsの設定をカスタマイズ
    marked.setOptions({
        gfm: true, // GitHub Flavored Markdownを有効化
        breaks: true, // 改行を反映
        headerIds: false, // ヘッダーIDを無効化
        mangle: false, // リンクを変更しない
        smartLists: true, // スマートリストを有効化
        highlight: function(code, lang) {
            if (lang && hljs.getLanguage(lang)) {
                try {
                    return hljs.highlight(code, { language: lang }).value;
                } catch (e) {
                    console.error(e);
                }
            }
            return code; // 言語が指定されていない場合はそのまま返す
        }
    });

    // 会話の状態を管理
    let conversationState = {
        currentStage: 'INITIAL',
        extractedGoal: null
    };

    // APIのベースURL
    const baseUrl = 'https://goal-achievement-chat-818237534030.asia-northeast1.run.app';

    function showLoading() {
        loadingIndicator.classList.remove('hidden');
        messageBox.disabled = true;
        sendButton.disabled = true;
    }

    function hideLoading() {
        loadingIndicator.classList.add('hidden');
        messageBox.disabled = false;
        sendButton.disabled = false;
        messageBox.focus();
    }

    // メッセージを表示する関数
    function appendMessage(content, isUser) {
        const messageDiv = document.createElement('div');
        messageDiv.className = isUser ? 'user-message' : 'assistant-message';
        
        if (isUser) {
            messageDiv.textContent = content;
        } else {
            // アシスタントのメッセージはMarkdownとしてレンダリング
            messageDiv.innerHTML = marked.parse(content);
            // コードブロックのシンタックスハイライトを適用
            messageDiv.querySelectorAll('pre code').forEach((block) => {
                hljs.highlightElement(block);
            });
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

            // カレンダーデータが含まれている場合は保存
            if (data.calendarData) {
                conversationState.calendarData = data.calendarData;
            }

            // プレースホルダーを更新
            updatePlaceholder(conversationState.currentStage);

            return data.response;
        } catch (error) {
            console.error('Error:', error);
            return 'エラーが発生しました。もう一度お試しください。';
        } finally {
            hideLoading();
        }
    }

    function updatePlaceholder(stage) {
        const placeholders = {
            INITIAL: 'あなたの目標を教えてください',
            GOAL_EXTRACTED: 'AIの提案を受けて、現在の状況や深めたい内容を教えてください',
            PLANNING: '目標達成までの期間を教えてください',
            SCHEDULING: 'スケジュールについて確認したい点を教えてください',
            CONFIRM_SCHEDULE: 'カレンダーへの登録についてお答えください'
        };
        messageBox.placeholder = placeholders[stage] || placeholders.INITIAL;
        
        // 点滅アニメーションを適用
        messageBox.classList.add('blink-animation');
        setTimeout(() => {
            messageBox.classList.remove('blink-animation');
        }, 2000); // 2秒後に点滅を停止
    }

    // 送信ボタンのクリックハンドラー
    sendButton.addEventListener('click', async () => {
        const message = messageBox.value.trim();
        if (!message) return;

        appendMessage(message, true);
        messageBox.value = '';
        updatePlaceholder(conversationState.currentStage);

        const response = await sendMessage(message);
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