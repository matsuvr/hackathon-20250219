# ビルドステージ
FROM python:3.11-slim AS builder

WORKDIR /app

# 依存関係のインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --target=/app/dependencies

# アプリケーションコードのコピー
COPY . .

# 実行ステージ
FROM gcr.io.distroless/python3:nonroot

# 必要なPythonパッケージとアプリケーションコードをコピー
WORKDIR /app
COPY --from=builder /app/dependencies /app
COPY --from=builder /app /app

# PYTHONPATHを設定
ENV PYTHONPATH=/app

# 環境変数の設定
ENV PORT=8080
EXPOSE 8080

# 非root ユーザーとして実行
USER nonroot

# アプリケーションの実行
CMD ["python", "-c", "import uvicorn; uvicorn.run('main:app', host='0.0.0.0', port=int('${PORT}'))"]