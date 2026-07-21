# 이항모형 가치평가 엔진 — 컨테이너 배포 (Render / HF Docker 등 공용)
FROM python:3.11-slim

# PDF 보고서용 chromium + 한글 폰트
RUN apt-get update && apt-get install -y --no-install-recommends \
        chromium \
        fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

# 비루트 사용자 (HF Spaces는 UID 1000으로 실행)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR $HOME/app

# 의존성 먼저 (레이어 캐시)
COPY --chown=user requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# 앱 소스
COPY --chown=user . .

# Render는 $PORT를 주입, HF는 7860. 미설정 시 7860 기본.
# (exec 배열이 아닌 셸 형식이라 ${PORT} 치환됨)
CMD streamlit run app.py --server.port ${PORT:-7860} --server.address 0.0.0.0
