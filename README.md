# MeetmA!te

> **Team No.00** | 팀 프로젝트 깃허브

---

## 목차

1. [프로젝트 소개](#프로젝트-소개)
2. [팀원 소개](#팀원-소개)
3. [GitHub 기본 개념](#github-기본-개념)
4. [Git 설치 및 초기 설정](#git-설치-및-초기-설정)
5. [작업 흐름 (워크플로우)](#작업-흐름-워크플로우)
6. [자주 쓰는 명령어 모음](#자주-쓰는-명령어-모음)
7. [주의사항](#주의사항)

---

## 프로젝트 소개

**MeetmA!te**는 팀 No.00의 프로젝트입니다.

> (서비스 설명은 여기에 추가해 주세요)

---

## 팀원 소개

| 역할 | 이름 | GitHub |
|------|------|--------|
| PM  | 안민혁 | [als7928](https://github.com/als7928) |
| Infra | 김세림 | [serim0906](https://github.com/serim0906) |
| Front-end | (이름) | - |
| Back-end | 이한결 | [hg020121](https://github.com/hg020121) |
| Back-end | 윤세준 | [SejunYOON-ai](https://github.com/SejunYOON-ai) |
| Front-end | 안상연 | [ahnup](https://github.com/ahnup) |
| Back-end | (이름) | - |
| Infra | 이다예 | [pucomaru](https://github.com/pucomaru)|


> 팀원 정보를 직접 채워주세요.

---

## GitHub 기본 개념

GitHub를 처음 쓰는 분들을 위해 핵심 개념만 간단히 정리했습니다.

### Repository (저장소)
코드와 파일이 저장되는 공간입니다. 지금 보고 있는 이 페이지가 저장소입니다.

### Branch (브랜치)
작업을 분리하는 가지입니다.
- `main` — 완성된 코드만 올라오는 메인 브랜치 (함부로 직접 수정 금지)
- 각자의 작업 브랜치 — 내 작업용으로 따로 만들어 사용

### Commit (커밋)
변경 내용을 저장하는 단위입니다. "저장 + 메모" 라고 생각하면 됩니다.

### Push / Pull
- **Push** — 내 컴퓨터의 변경 내용을 GitHub에 올리기
- **Pull** — GitHub의 최신 내용을 내 컴퓨터로 가져오기

### Pull Request (PR)
내 브랜치의 작업을 `main`에 합치자고 요청하는 것입니다. 팀장이 검토 후 승인합니다.

---

## Git 설치 및 초기 설정

### 1. 이름 & 이메일 등록 (최초 1회)

```bash
git config --global user.name "홍길동"
git config --global user.email "your@email.com"
```

> GitHub 계정 이메일과 동일하게 설정하세요.

### 2. 저장소 복사 (최초 1회)

```bash
git clone https://github.com/als7928/meetmaite.git
cd meetmaite
```

---

## 작업 흐름 (워크플로우)

매번 작업할 때 아래 순서를 따라주세요.

### 1단계 — 최신 코드 받아오기

작업 시작 전에 항상 먼저 실행하세요.

```bash
git pull origin main
```

### 2단계 — 내 작업 브랜치 만들기

```bash
git checkout -b feature/내작업이름
# 예시: git checkout -b feature/login-page
```

> 브랜치 이름은 `feature/기능명` 형식으로 통일합니다.

### 3단계 — 코드 작성

평소처럼 파일을 수정하세요.

### 4단계 — 변경 내용 저장 (커밋)

```bash
git add .
git commit -m "작업 내용을 간단히 설명"
# 예시: git commit -m "로그인 페이지 UI 구현"
```

### 5단계 — GitHub에 올리기 (푸시)

```bash
git push origin feature/내작업이름
```

### 6단계 — Pull Request 생성

1. GitHub 저장소 페이지로 이동
2. 상단에 표시되는 **"Compare & pull request"** 버튼 클릭
3. 제목과 설명 작성 후 **"Create pull request"** 클릭
4. 팀장의 리뷰 및 승인 대기

### 7단계 — 머지 후 정리

PR이 승인되어 `main`에 합쳐지면:

```bash
git checkout main
git pull origin main
```

---

## 자주 쓰는 명령어 모음

```bash
# 현재 상태 확인
git status

# 변경된 내용 확인
git diff

# 브랜치 목록 확인
git branch

# 브랜치 이동
git checkout 브랜치이름

# 커밋 내역 확인
git log --oneline
```

---

## 주의사항

- `main` 브랜치에 직접 Push하지 마세요. 반드시 PR을 통해 합칩니다.
- 작업 시작 전 `git pull`로 최신 코드를 먼저 받아오세요.
- 커밋 메시지는 알아보기 쉽게 한국어로 작성해도 됩니다.
- 충돌(Conflict)이 발생하면 혼자 해결하려 하지 말고 PM에게 먼저 알려주세요.

---

> 궁금한 점은 팀 슬랙에 언제든지 물어보세요!
