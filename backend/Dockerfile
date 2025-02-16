# ビルドステージ
FROM python:3.11-slim AS builder

WORKDIR /app

# 基本的なビルドツールのインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# requirements.txtをコピー
COPY requirements.txt .

# 依存関係のインストール（パスを指定してインストール）
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt --target=/app/packages

# アプリケーションコードのコピー
COPY . .

# 実行ステージ - Distrolessを使用
FROM gcr.io/distroless/python3-debian12:nonroot

WORKDIR /app

# アプリケーションコードとパッケージをコピー
COPY --from=builder /app/packages /app/packages
COPY --from=builder /app/*.py /app/

# 環境変数の設定
ENV PORT=8080
ENV PYTHONPATH=/app/packages
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

# pythonコマンドのフルパスを指定
CMD ["-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--log-level", "debug"]