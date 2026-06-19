"""실시간 요약 (refine-chunk) 테스트 스크립트.

사용법:
  python scripts/test_realtime_summary.py --token <JWT토큰> --session <세션ID>

토큰 가져오는 법:
  브라우저 개발자도구 → Application → Session Storage → token 값 복사
"""

import argparse
import requests

# ─── 테스트용 가짜 STT 발화 텍스트 ───────────────────────────────────────────
SAMPLE_TRANSCRIPTS = [
    {
        "label": "예산 논의",
        "text": """
화자01: 어 이번 분기 예산안 검토 좀 해야할 것 같아서요.
화자02: 네 맞아요 지난번에 말씀하신 그 R&D 비용 쪽이 좀 문제가 있었죠.
화자01: 음 그래서 제가 보니까 전체 예산에서 한 15% 정도를 줄여야 할 것 같은데.
화자03: 아 근데 그러면 인력 쪽에서 영향이 있지 않을까요? 신규 채용이 좀 어렵지 않겠어요?
화자02: 그 부분은 어 내년 상반기로 미루는 방향으로 논의해보면 어떨까요.
화자01: 네 그렇게 하죠. 그러면 이번 분기는 기존 인력으로 운영하는 방향으로.
""",
    },
    {
        "label": "기술 스펙 결정",
        "text": """
화자01: 자 그러면 이제 반도체 공정 기술 스펙 얘기 해볼까요.
화자02: 어 지난번에 14나노 vs 7나노 얘기가 있었는데 결론이 어떻게 됐죠?
화자03: 아 그게 아직 결정이 안 났어요. 비용 때문에 좀 의견이 갈렸거든요.
화자01: 음 7나노로 가면 성능은 좋은데 단가가 한 30% 올라가잖아요.
화자02: 맞아요 근데 요즘 경쟁사들이 다 7나노 이하로 가고 있어서.
화자01: 그러면 일단 7나노로 방향 잡고 비용 절감 방법을 찾아보는 게 어떨까요?
화자03: 저도 그게 맞을 것 같습니다. 단가 협상 여지도 있고요.
""",
    },
    {
        "label": "일정 조율",
        "text": """
화자01: 어 다음 미팅 일정 좀 잡아야 할 것 같은데요.
화자02: 저는 다음 주 화요일 오후가 괜찮습니다.
화자03: 음 저는 화요일은 좀 어렵고 수요일이나 목요일이 좋겠어요.
화자01: 그러면 수요일 오후 2시로 하면 어떨까요?
화자02: 네 좋습니다.
화자03: 저도 괜찮아요. 수요일 2시로 확정하죠.
화자01: 좋아요 그러면 수요일 오후 2시에 같은 회의실에서 만나요.
""",
    },
]


def test_refine_chunk(base_url: str, token: str, session_id: int, sample_idx: int = 0):
    sample = SAMPLE_TRANSCRIPTS[sample_idx % len(SAMPLE_TRANSCRIPTS)]
    print(f"\n{'=' * 60}")
    print(f"테스트: [{sample['label']}]")
    print(f"session_id: {session_id}")
    print(f"{'=' * 60}")
    print(f"입력 텍스트:\n{sample['text'].strip()}\n")

    payload = {
        "session_id": session_id,
        "text": sample["text"].strip(),
        "context": "반도체 공정 위원회 정기 회의",
        "recording_start_sec": sample_idx * 300.0,
        "recording_end_sec": sample_idx * 300.0 + 120.0,
    }

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    resp = requests.post(
        f"{base_url}/api/ai/sessions/refine-chunk",
        headers=headers,
        json=payload,  # type: ignore[arg-type]
        timeout=30,
    )

    if resp.status_code != 200:
        print(f"❌ 에러 {resp.status_code}: {resp.text}")
        return

    result = resp.json()
    print("✅ 결과:")
    print(f"  제목: {result.get('title', '없음')}")
    bullets = result.get("bullets", [])
    for b in bullets:
        print(f"  {b}")


def main():
    parser = argparse.ArgumentParser(description="실시간 요약 테스트")
    parser.add_argument(
        "--token", required=True, help="JWT 토큰 (브라우저 sessionStorage에서 복사)"
    )
    parser.add_argument("--session", required=True, type=int, help="세션 ID")
    parser.add_argument(
        "--url", default="http://localhost:8000", help="FastAPI 서버 주소"
    )
    parser.add_argument("--all", action="store_true", help="샘플 3개 전부 테스트")
    parser.add_argument("--idx", type=int, default=0, help="샘플 번호 (0/1/2)")
    args = parser.parse_args()

    if args.all:
        for i in range(len(SAMPLE_TRANSCRIPTS)):
            test_refine_chunk(args.url, args.token, args.session, i)
    else:
        test_refine_chunk(args.url, args.token, args.session, args.idx)


if __name__ == "__main__":
    main()
