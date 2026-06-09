"""
file_embedder.py — 파일 텍스트 추출 → 청킹 → 임베딩 유틸리티
==============================================================
지원 파일 형식: PDF, DOCX, TXT, HWP(텍스트 추출 한계로 plaintext fallback)
"""

from __future__ import annotations
import logging
import os
import tempfile
from pathlib import Path

from openai import AsyncOpenAI

from r2_storage import is_r2_url, url_to_key, download_bytes as r2_download_bytes

logger = logging.getLogger(__name__)

_openai: AsyncOpenAI | None = None

def _get_openai() -> AsyncOpenAI:
    """Lazy initialization — .env 로드 후 최초 호출 시 클라이언트 생성."""
    global _openai
    if _openai is None:
        _openai = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _openai

# 청킹 설정 (token 수 기준)
CHUNK_TOKENS   = int(os.environ["EMBED_CHUNK_TOKENS"])
CHUNK_OVERLAP  = int(os.environ["EMBED_CHUNK_OVERLAP"])
EMBED_MODEL    = os.environ["EMBED_MODEL"]
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


# ─── 파일 → 청킹 → 임베딩 → Neo4j 저장 ─────────────────────────────────────

async def embed_and_store(
    file_path_or_url: str,
    filename: str,
    context_type: str = "document",
    meeting_id: int | None = None,
    source_id: str | None = None,
) -> int:
    """파일에서 텍스트 추출 → 청킹 → 임베딩 → Neo4j 저장.

    context_type에 따라 노드 레이블이 결정됩니다:
      report            → ReportChunk
      minutes           → MinutesChunk
      agenda / archive  → AgendaChunk
      knowledge / 기타  → KnowledgeChunk
    """
    from neo4j_client import run_cypher

    text = extract_text(file_path_or_url)
    if not text.strip():
        logger.warning(f"[Embedder] 텍스트 추출 결과 없음: {filename}")
        return 0

    chunks = chunk_text(text)
    if not chunks:
        return 0

    embeddings = await embed_chunks(chunks)
    base_id = (source_id or filename).replace(" ", "_")
    mg_id   = f"mg-{meeting_id}" if meeting_id else None

    if context_type == "report":
        node_label = "ReportChunk"
    elif context_type == "minutes":
        node_label = "MinutesChunk"
    elif context_type in ("agenda", "archive"):
        node_label = "AgendaChunk"
    else:
        node_label = "KnowledgeChunk"

    stored = 0
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        chunk_id = f"{base_id}-{i}"
        cypher = f"""
MERGE (c:{node_label} {{id: $id}})
SET c.content     = $content,
    c.source      = $source,
    c.meeting_id  = $meeting_id,
    c.chunk_index = $chunk_index
WITH c
CALL db.create.setNodeVectorProperty(c, 'embedding', $embedding)
"""
        params: dict = {
            "id": chunk_id,
            "content": chunk[:500],
            "source": filename,
            "meeting_id": meeting_id,
            "chunk_index": i,
            "embedding": embedding,
        }
        if mg_id:
            cypher += """
WITH c
OPTIONAL MATCH (mg:Meetings {id: $mg_id})
FOREACH (_ IN CASE WHEN mg IS NOT NULL THEN [1] ELSE [] END |
    MERGE (c)-[:BELONGS_TO]->(mg)
)"""
            params["mg_id"] = mg_id

        try:
            await run_cypher(cypher, params)
            stored += 1
        except Exception as e:
            logger.error(f"[Embedder] 청크 저장 실패 (id={chunk_id}): {e}")

    logger.info(f"[Embedder] {node_label} {stored}/{len(chunks)}청크 저장 완료: {filename} (context_type={context_type})")
    return stored


