"""
file_embedder.py — 파일 텍스트 추출 → 청킹 → 임베딩 → Neo4j 저장
===================================================================
지원 파일 형식: PDF, DOCX, TXT, HWP(텍스트 추출 한계로 plaintext fallback)

파이프라인:
  1. extract_text(file_path)  → 원문 텍스트
  2. chunk_text(text)         → 청크 리스트 (token 기반, overlap 포함)
  3. embed_chunks(chunks)     → OpenAI text-embedding-3-small 벡터 리스트
  4. neo4j_sync.sync_document_chunk() → Neo4j DocumentChunk 노드 + VectorIndex
"""

from __future__ import annotations
import asyncio
import hashlib
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from neo4j_sync import sync_document_chunk, sync_document
from r2_storage import is_r2_url, url_to_key, download_bytes as r2_download_bytes

logger = logging.getLogger(__name__)

_openai: AsyncOpenAI | None = None

def _get_openai() -> AsyncOpenAI:
    """Lazy initialization — .env 로드 후 최초 호출 시 클라이언트 생성."""
    global _openai
    if _openai is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
        _openai = AsyncOpenAI(api_key=api_key)
    return _openai

# 청킹 설정 (token 수 기준)
CHUNK_TOKENS   = int(os.getenv("EMBED_CHUNK_TOKENS",   "400"))
CHUNK_OVERLAP  = int(os.getenv("EMBED_CHUNK_OVERLAP",  "80"))
EMBED_MODEL    = os.getenv("EMBED_MODEL", "text-embedding-3-small")
EMBED_DIM      = 1536  # text-embedding-3-small 차원


# ─── 텍스트 추출 ─────────────────────────────────────────────────────────────

def _download_to_tempfile(r2_url: str, suffix: str) -> str:
    """R2 URL에서 파일을 다운로드하여 임시 파일 경로를 반환합니다."""
    data = r2_download_bytes(url_to_key(r2_url))
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(data)
        tmp.flush()
        return tmp.name
    finally:
        tmp.close()


def extract_text(file_path: str) -> str:
    """파일 경로 또는 R2 URL에서 텍스트를 추출합니다."""
    if is_r2_url(file_path):
        suffix = Path(file_path.split("?")[0]).suffix.lower() or ".bin"
        tmp_path = _download_to_tempfile(file_path, suffix)
        try:
            return extract_text(tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return _extract_pdf(file_path)
    elif suffix in (".docx", ".doc"):
        return _extract_docx(file_path)
    elif suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="replace")
    elif suffix == ".hwp":
        return _extract_hwp(file_path)
    else:
        # 알 수 없는 형식: 바이트를 UTF-8로 디코딩 시도
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"[Embedder] 알 수 없는 형식 {suffix}: {e}")
            return ""


def _extract_pdf(file_path: str) -> str:
    try:
        import pypdf
        reader = pypdf.PdfReader(file_path)
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages)
    except ImportError:
        logger.error("[Embedder] pypdf 미설치. pip install pypdf")
        return ""
    except Exception as e:
        logger.error(f"[Embedder] PDF 추출 실패: {e}")
        return ""


def _extract_docx(file_path: str) -> str:
    try:
        import docx
        doc = docx.Document(file_path)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except ImportError:
        logger.error("[Embedder] python-docx 미설치. pip install python-docx")
        return ""
    except Exception as e:
        logger.error(f"[Embedder] DOCX 추출 실패: {e}")
        return ""


def _extract_hwp(file_path: str) -> str:
    """HWP는 olefile 기반 텍스트 추출 (간이 지원)."""
    try:
        import olefile
        with olefile.OleFileIO(file_path) as f:
            if f.exists("PrvText"):
                raw = f.openstream("PrvText").read()
                return raw.decode("utf-16-le", errors="replace")
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"[Embedder] HWP 추출 실패: {e}")
    return ""


# ─── 청킹 (토큰 기반) ────────────────────────────────────────────────────────

def chunk_text(text: str, chunk_tokens: int = CHUNK_TOKENS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    텍스트를 토큰 기준으로 청크로 분할합니다.
    tiktoken이 없으면 글자 수(4자 ≈ 1토큰) 근사값을 사용합니다.
    """
    if not text.strip():
        return []
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        tokens = enc.encode(text)
        chunks = []
        start = 0
        while start < len(tokens):
            end = min(start + chunk_tokens, len(tokens))
            chunk_tokens_slice = tokens[start:end]
            chunks.append(enc.decode(chunk_tokens_slice))
            if end == len(tokens):
                break
            start += chunk_tokens - overlap
        return [c for c in chunks if c.strip()]
    except ImportError:
        # 문자 수 기반 fallback (4자 ≈ 1토큰)
        char_size    = chunk_tokens * 4
        char_overlap = overlap * 4
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + char_size, len(text))
            chunks.append(text[start:end])
            if end == len(text):
                break
            start += char_size - char_overlap
        return [c for c in chunks if c.strip()]


# ─── 임베딩 ──────────────────────────────────────────────────────────────────

async def embed_chunks(chunks: list[str], batch_size: int = 20) -> list[list[float]]:
    """OpenAI text-embedding-3-small으로 배치 임베딩합니다."""
    embeddings: list[list[float]] = []
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        try:
            resp = await _get_openai().embeddings.create(
                model=EMBED_MODEL,
                input=batch,
            )
            for item in resp.data:
                embeddings.append(item.embedding)
        except Exception as e:
            logger.error(f"[Embedder] 임베딩 실패 (배치 {i}~{i+batch_size}): {e}")
            # 실패한 배치는 zero 벡터로 채워 인덱스 불일치 방지
            embeddings.extend([[0.0] * EMBED_DIM] * len(batch))
    return embeddings


# ─── 단일 쿼리 임베딩 ────────────────────────────────────────────────────────

async def embed_query(text: str) -> list[float]:
    """검색 쿼리 한 건을 임베딩합니다."""
    try:
        resp = await _get_openai().embeddings.create(model=EMBED_MODEL, input=[text])
        return resp.data[0].embedding
    except Exception as e:
        logger.error(f"[Embedder] 쿼리 임베딩 실패: {e}")
        return [0.0] * EMBED_DIM


# ─── 통합 파이프라인 ──────────────────────────────────────────────────────────

async def process_and_embed_file(
    file_path: str,
    file_name: str,
    meeting_id: int | None = None,
    session_id: int | None = None,
    extra_meta: dict | None = None,
    agenda_neo4j_id: str | None = None,
    agenda_content: str | None = None,
    file_label: str | None = None,
    doc_type: str = "보고자료",
    mg_id: str | None = None,
) -> dict:
    """
    파일 전체 파이프라인을 실행합니다.
    Returns:
        {
            "file_name": str,
            "chunk_count": int,
            "embedded": int,       # 성공한 청크 수
            "failed": int,         # Neo4j 저장 실패 수 (agent_logs에 기록됨)
        }
    """
    logger.info(f"[Embedder] 파일 처리 시작: {file_name}")

    # 1. 텍스트 추출
    text = extract_text(file_path)
    if not text.strip():
        logger.warning(f"[Embedder] {file_name}: 추출된 텍스트 없음")
        return {"file_name": file_name, "chunk_count": 0, "embedded": 0, "failed": 0}

    # 2. 청킹
    chunks = chunk_text(text)
    if not chunks:
        return {"file_name": file_name, "chunk_count": 0, "embedded": 0, "failed": 0}

    # 3. 임베딩
    embeddings = await embed_chunks(chunks)

    # 4. Neo4j 저장
    embedded = 0
    failed = 0
    file_hash = hashlib.md5(file_name.encode()).hexdigest()[:8]

    # source_file에 R2 URL을 저장해 retry 시 재다운로드 가능하게 함
    source_ref = file_path if is_r2_url(file_path) else file_name

    tasks = []
    for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        chunk_id = f"{file_hash}-{meeting_id or 'g'}-{session_id or 's'}-{idx}"
        tasks.append(
            sync_document_chunk(
                chunk_id=chunk_id,
                source_file=source_ref,
                meeting_id=meeting_id,
                session_id=session_id,
                chunk_index=idx,
                text=chunk,
                embedding=emb,
                metadata={**(extra_meta or {}), "total_chunks": len(chunks)},
            )
        )

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Exception):
            failed += 1
        else:
            embedded += 1

    # 5. Document 노드 upsert (파일 전체를 대표하는 노드)
    doc_id = f"doc-{file_hash}-{meeting_id or 'g'}"
    uploader_id = (extra_meta or {}).get("uploader_id")
    await sync_document(
        doc_id=doc_id,
        file_name=file_name,
        title=file_label or file_name,
        doc_type=doc_type,
        meeting_id=meeting_id,
        mg_id=mg_id,
        agenda_neo4j_id=agenda_neo4j_id,
        agenda_content=agenda_content,
        uploader_id=uploader_id,
    )

    logger.info(
        f"[Embedder] {file_name} 완료 — "
        f"청크: {len(chunks)}, 임베딩 성공: {embedded}, 실패: {failed}"
    )
    return {
        "file_name": file_name,
        "chunk_count": len(chunks),
        "embedded": embedded,
        "failed": failed,
    }
