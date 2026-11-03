# Sentinel IDS portal for Hugging Face Spaces (Docker SDK, CPU).
# Built from the folder that scripts/build_space.py assembles (build/space).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN useradd -m -u 1000 user
WORKDIR /app

# CPU-only PyTorch first (much smaller than the CUDA build), then the rest.
COPY requirements.txt pyproject.toml ./
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch \
 && pip install -r requirements.txt

COPY --chown=user . .
RUN pip install --no-deps -e . && chown -R user /app

USER user
# Warehouse tab starts hidden; the admin can switch it on in Administration -> Overview.
ENV IDS_WAREHOUSE=0
EXPOSE 7860
CMD ["python", "-m", "uvicorn", "ids.api.main:app", "--host", "0.0.0.0", "--port", "7860"]
