# 소수 찾기

## 배포 순서

1. Supabase 프로젝트에서 **SQL Editor → New query**를 열고 `schema.sql` 전체를 붙여넣어 한 번 실행합니다.
2. 이 압축 파일을 풀고 `app.py`, `requirements.txt`, `schema.sql`, `README.md`, `.gitignore`를 GitHub 저장소의 최상단에 올립니다.
3. Streamlit Community Cloud에서 GitHub 저장소를 연결하고 실행 파일을 `app.py`로 지정합니다.
4. 배포 설정의 **Secrets**에 아래 값을 넣습니다. Supabase의 프로젝트 URL과 레거시 `service_role` 키를 사용합니다. 실제 키와 교사 비밀번호는 Streamlit Secrets에만 입력합니다.

```toml
[app]
supabase_url = "https://YOUR_PROJECT.supabase.co"
supabase_service_role_key = "YOUR_SERVICE_ROLE_KEY"
teacher_password = "직접 정한 교사 비밀번호"
```

5. 학생이 자기 기기에서 접근할 수 있도록 Streamlit 앱의 공유 범위를 설정합니다. 배포 후 교사와 학생 화면을 서로 다른 브라우저에서 시험해 봅니다.

## 수업 진행

- 교사 화면에서 1학년 1~5반을 선택하고 이름을 한 줄에 한 명씩 붙여넣어 저장합니다. 같은 반의 동명이인만 `07 김민준`처럼 서로 다른 번호를 붙이고 학생에게 정확한 입력값을 알려 줍니다.
- **새 수업 만들기**를 누르고 학생에게 앱 주소와 수업 코드를 알려 줍니다. 개설된 수업은 당시 명단과 숫자판을 사용합니다. 수정된 명단을 쓰려면 새 수업을 엽니다.
- 학생은 코드와 등록된 이름으로 입장합니다. 11~75 사이 홀수 25개 중 9개를 고르고 최종 제출합니다. 제출 전에는 선택을 바꿀 수 있습니다.
- 첫 제출을 이름별로 한 번만 기록합니다. 9개를 모두 맞힌 학생만 서버 접수 순서대로 순위에 표시되며, 교사 화면은 3초마다 갱신됩니다.
- 입장에 사용하는 이름은 명단 대조용입니다. 수업 코드와 등록된 이름을 아는 학생은 해당 이름으로 입장할 수 있으므로 수업 중 본인 이름 사용을 안내합니다.
