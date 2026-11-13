import hmac
import random
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from math import isqrt

import streamlit as st
from httpx import RequestError
from postgrest.exceptions import APIError
from supabase import create_client


st.set_page_config(page_title="소수 찾기", page_icon="🔢")

CLASSES = [f"1학년 {number}반" for number in range(1, 6)]
KOREA_TIME = timezone(timedelta(hours=9))
DATABASE_ERRORS = (APIError, RequestError)


def apply_style():
    st.markdown(
        """
        <style>
        .stApp {
            background: radial-gradient(
                ellipse at 50% 0%, #1a304b 0%, #101c30 44%, #0b1322 85%
            );
            color: #eef4ff;
        }
        [data-testid="stHeader"] { background: transparent; }
        [data-testid="stSidebar"] { background: #101c30; }
        .block-container { max-width: 820px; padding-top: 3rem; }
        .stApp h1, .stApp h2, .stApp h3, .stApp label, .stApp p {
            color: #eef4ff;
        }
        .prime-hero {
            margin-bottom: 1.35rem;
            padding: clamp(1.35rem, 5vw, 2.4rem);
            border: 1px solid #38536f;
            border-radius: 1.25rem;
            background: linear-gradient(135deg, #203a52, #142237);
        }
        .prime-hero h1 {
            padding: 0;
            margin: 0 0 .5rem;
            font-size: clamp(2.1rem, 8vw, 3.4rem);
            letter-spacing: -.055em;
        }
        .prime-hero p { margin: 0; color: #c4d4e8; }
        .prime-ready {
            margin: .65rem 0 1rem;
            padding: 1.3rem;
            border: 1px solid #38536f;
            border-radius: 1rem;
            background: #172840;
        }
        .prime-ready h2 { margin: 0 0 .4rem; padding: 0; }
        .prime-ready p { margin: 0; color: #c4d4e8; }
        [data-testid="stMetric"] {
            padding: .75rem 1rem;
            border: 1px solid #38536f;
            border-radius: .9rem;
            background: #172840;
        }
        [data-testid="stMetricValue"] {
            color: #81efd5;
            font-variant-numeric: tabular-nums;
        }
        .stButton button, .stFormSubmitButton button {
            min-height: 2.85rem;
            border-radius: .7rem;
            font-weight: 700;
        }
        button[kind="primary"], button[kind="primaryFormSubmit"] {
            background: #81efd5;
            border-color: #81efd5;
            color: #102721;
        }
        button[kind="primary"] p, button[kind="primaryFormSubmit"] p {
            color: #102721;
        }
        button[kind="secondary"] {
            background: #1a2e49;
            border-color: #496581;
            color: #eef4ff;
        }
        .stButton button:focus-visible, .stFormSubmitButton button:focus-visible {
            outline: 2px solid #81efd5;
            outline-offset: 2px;
        }
        .st-key-prime_board [data-testid="stHorizontalBlock"] {
            flex-wrap: nowrap;
            gap: .35rem;
        }
        .st-key-prime_board [data-testid="stColumn"] {
            flex: 1 1 0 !important;
            min-width: 0 !important;
            width: 0 !important;
        }
        .st-key-prime_board button {
            padding: .2rem;
            min-height: clamp(2.7rem, 9vw, 4rem);
        }
        .st-key-prime_board button p {
            font-size: clamp(1rem, 4vw, 1.4rem);
            font-variant-numeric: tabular-nums;
        }
        </style>
        <div class="prime-hero">
            <h1>소수 찾기</h1>
            <p>홀수 25개 중 숨어 있는 소수 9개를 찾아보세요.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


@st.cache_resource
def connect(url, key):
    return create_client(url, key)


def normalize(value):
    return " ".join(unicodedata.normalize("NFKC", value).split())


def make_board():
    odds = range(11, 76, 2)
    primes = [
        number for number in odds
        if all(number % divisor for divisor in range(2, isqrt(number) + 1))
    ]
    composites = [number for number in odds if number not in primes]
    answer = random.sample(primes, 9)
    board = answer + random.sample(composites, 16)
    random.shuffle(board)
    return board, answer


def clock_text(timestamp):
    if not timestamp:
        return "—"
    return datetime.fromisoformat(timestamp).astimezone(KOREA_TIME).strftime("%H:%M:%S")


def elapsed_text(started_at, ended_at):
    if not started_at or not ended_at:
        return "—"

    start = datetime.fromisoformat(started_at)
    end = datetime.fromisoformat(ended_at)
    seconds = max(0, int((end - start).total_seconds()))
    minutes, seconds = divmod(seconds, 60)

    if minutes:
        return f"{minutes}분 {seconds:02d}초"
    return f"{seconds}초"


def database_error(error):
    if isinstance(error, APIError):
        st.error(f"Supabase 요청에 실패했어요. 오류 코드 {error.code or '없음'}")
    else:
        st.error("Supabase에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.")


def load_roster(db, classroom):
    rows = (
        db.table("prime_rosters")
        .select("names")
        .eq("classroom", classroom)
        .execute()
        .data
    )
    return rows[0]["names"] if rows else []


def active_lesson(db):
    rows = (
        db.table("prime_rounds")
        .select("code,classroom,names")
        .eq("accepting_entries", True)
        .limit(1)
        .execute()
        .data
    )
    return rows[0] if rows else None


@st.fragment(run_every="3s")
def show_ranking(db, code, teacher=False):
    try:
        attempts = (
            db.table("prime_attempts")
            .select("student,correct,submitted_at")
            .eq("code", code)
            .order("id")
            .execute()
            .data
        )
        entries = (
            db.table("prime_entries")
            .select("student,joined_at")
            .eq("code", code)
            .execute()
            .data
        )
    except DATABASE_ERRORS as error:
        database_error(error)
        return

    started_by_name = {entry["student"]: entry["joined_at"] for entry in entries}
    ranked = []

    for attempt in attempts:
        if not attempt["correct"]:
            continue

        name = attempt["student"]
        started_at = started_by_name.get(name)
        submitted_at = attempt["submitted_at"]
        row = {"순위": len(ranked) + 1, "이름": name}

        if teacher:
            row["시작 시각"] = clock_text(started_at)
            row["제출 시각"] = clock_text(submitted_at)

        row["풀이 시간"] = elapsed_text(started_at, submitted_at)
        ranked.append(row)

    if teacher:
        st.caption(
            f"시작 {len(entries)}명 / 제출 {len(attempts)}명 / 모두 정답 {len(ranked)}명"
        )
    else:
        st.subheader("우리 반 순위")
        st.caption("소수 9개를 모두 맞힌 학생을 제출 순서대로 보여줘요.")

    if ranked:
        st.dataframe(ranked, hide_index=True, width="stretch")
    else:
        st.info("아직 소수 9개를 모두 맞힌 학생이 없어요.")


def teacher_page(db, password):
    if not st.session_state.get("teacher"):
        with st.form("teacher_login"):
            entered = st.text_input("교사 비밀번호", type="password")
            login = st.form_submit_button("로그인", type="primary")

        if login:
            if hmac.compare_digest(entered.encode(), password.encode()):
                st.session_state.teacher = True
                st.rerun()
            st.error("교사 비밀번호를 확인해 주세요.")
        return

    if st.button("교사 로그아웃"):
        st.session_state.teacher = False
        st.rerun()

    notice = st.session_state.pop("teacher_notice", None)
    if notice:
        st.success(notice)

    classroom = st.selectbox("반 선택", CLASSES)
    st.subheader("학생 명단")

    with st.form(f"roster_{classroom}"):
        roster_text = st.text_area(
            "한 줄에 한 명씩 입력하세요. 같은 반의 동명이인은 번호와 이름을 함께 등록하세요.",
            value="\n".join(load_roster(db, classroom)),
            height=210,
            key=f"roster_text_{classroom}",
        )
        save = st.form_submit_button("이 반 명단 저장")

    if save:
        names = [
            name for line in roster_text.splitlines()
            if (name := normalize(line))
        ]
        if not names or len(names) > 100 or any(len(name) > 40 for name in names):
            st.error("1~100명까지 등록할 수 있어요. 각 이름은 40자 이내로 입력해 주세요.")
        elif len(set(names)) != len(names):
            st.error("같은 이름이 두 번 들어 있어요. 동명이인만 번호를 붙여 주세요.")
        else:
            db.table("prime_rosters").upsert({
                "classroom": classroom,
                "names": names,
            }).execute()
            st.success(f"{classroom} 명단 {len(names)}명을 저장했어요.")

    st.subheader("수업 열기")
    results_key = f"results_{classroom}"

    if st.button("새 수업 만들기", type="primary"):
        board, answer = make_board()
        code = secrets.token_hex(4).upper()
        opened = db.rpc("prime_open_round", {
            "p_code": code,
            "p_classroom": classroom,
            "p_board": board,
            "p_answer": answer,
        }).execute().data

        if opened:
            st.session_state[results_key] = code
            st.success(f"{classroom} 수업을 열었어요. 학생은 이름만 입력하면 돼요.")
        else:
            st.warning("먼저 이 반의 명단을 저장해 주세요.")

    active = active_lesson(db)
    if active:
        st.caption(f"현재 입장 가능한 수업은 {active['classroom']}이에요.")
    else:
        st.caption("현재 입장 가능한 수업이 없어요.")

    rounds = (
        db.table("prime_rounds")
        .select("code,created_at,accepting_entries")
        .eq("classroom", classroom)
        .order("created_at", desc=True)
        .order("code", desc=True)
        .limit(50)
        .execute()
        .data
    )
    if not rounds:
        return

    by_code = {lesson["code"]: lesson for lesson in rounds}
    if st.session_state.get(results_key) not in by_code:
        st.session_state[results_key] = rounds[0]["code"]

    def round_label(code):
        lesson = by_code[code]
        opened_at = datetime.fromisoformat(lesson["created_at"]).astimezone(KOREA_TIME)
        state = " · 입장 가능" if lesson["accepting_entries"] else ""
        return f"{opened_at:%m월 %d일 %H:%M:%S} · {code}{state}"

    st.subheader("수업 기록")
    code = st.selectbox(
        "순위를 볼 수업",
        list(by_code),
        format_func=round_label,
        key=results_key,
    )
    show_ranking(db, code, teacher=True)

    with st.expander("이 수업 기록 삭제"):
        st.warning(
            "선택한 수업의 숫자판, 시작 기록, 제출 기록과 순위를 삭제해요. "
            "반별 학생 명단은 유지돼요."
        )
        confirmed = st.checkbox(
            "선택한 수업의 기록을 삭제할게요.",
            key=f"delete_confirm_{code}",
        )

        if st.button(
            "이 수업 영구 삭제",
            disabled=not confirmed,
            key=f"delete_round_{code}",
        ):
            (
                db.table("prime_rounds")
                .delete()
                .eq("code", code)
                .eq("classroom", classroom)
                .execute()
            )
            st.session_state.pop(results_key, None)
            st.session_state.teacher_notice = "선택한 수업 기록을 삭제했어요."
            st.rerun()


def show_outcome(result):
    status = result["status"]

    if status == "correct":
        st.success(f"9개 모두 정답! {result['rank']}위예요.")
    elif status == "wrong":
        st.error("오답이 포함되어 순위에서 제외됐어요. 제출 기회를 사용했어요.")
    elif status == "denied":
        st.error("수업이 삭제됐거나 제출할 수 없는 상태예요.")
    else:
        st.error("숫자판에서 서로 다른 숫자 9개를 선택해 주세요.")


def show_previous_attempt(db, code, name, started_at):
    rows = (
        db.table("prime_attempts")
        .select("id,correct,submitted_at")
        .eq("code", code)
        .eq("student", name)
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        return False

    attempt = rows[0]
    if attempt["correct"]:
        rank = (
            db.table("prime_attempts")
            .select("id", count="exact")
            .eq("code", code)
            .eq("correct", True)
            .lte("id", attempt["id"])
            .execute()
            .count
        )
        show_outcome({"status": "correct", "rank": rank})
    else:
        show_outcome({"status": "wrong"})

    submitted_at = attempt["submitted_at"]
    st.caption(
        f"제출 시각 {clock_text(submitted_at)} / "
        f"풀이 시간 {elapsed_text(started_at, submitted_at)}"
    )
    return True


@st.fragment(run_every="1s")
def show_timer(started_at):
    now = datetime.now(timezone.utc).isoformat()
    st.metric("풀이 시간", elapsed_text(started_at, now))


def student_page(db):
    login = st.session_state.get("prime_login")
    started = st.session_state.get("prime_started")

    if not login:
        with st.form("student_login"):
            name = normalize(st.text_input("이름", max_chars=40))
            enter = st.form_submit_button("입장", type="primary", width="stretch")

        if not enter:
            return
        if not name:
            st.error("이름을 입력해 주세요.")
            return

        lesson = active_lesson(db)
        if not lesson:
            st.info("선생님이 수업을 열면 입장할 수 있어요.")
            return
        if name not in lesson["names"]:
            st.error("지금 열린 수업의 명단에 없는 이름이에요.")
            return

        st.session_state.prime_login = {
            "code": lesson["code"],
            "classroom": lesson["classroom"],
            "name": name,
        }
        st.rerun()

    code = login["code"]
    name = login["name"]
    confirm_key = f"prime_confirm_{code}"
    st.caption(f"{login['classroom']} / {name}")

    if st.button("입장 화면으로"):
        for key in ("prime_login", "prime_started", "prime_picks", confirm_key):
            st.session_state.pop(key, None)
        st.rerun()

    if not started:
        st.markdown(
            """
            <div class="prime-ready">
                <h2>준비됐나요?</h2>
                <p>시작을 누르면 숫자판이 열리고 풀이 시간이 흐르기 시작해요.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.write("소수 9개를 모두 고르세요. 제출 기회는 한 번이에요.")

        if st.button("시작", type="primary", width="stretch"):
            current = active_lesson(db)
            if not current or current["code"] != code:
                st.warning("열린 수업이 바뀌었어요. 입장 화면으로 돌아가 다시 입장해 주세요.")
                return

            result = db.rpc(
                "prime_join_round", {"p_student": name}
            ).execute().data

            if result["status"] != "joined" or result.get("code") != code:
                st.warning("수업을 시작할 수 없어요. 입장 화면으로 돌아가 다시 입장해 주세요.")
                return

            st.session_state.prime_started = result
            st.session_state.prime_picks = set()
            st.rerun()
        return

    board = started["board"]
    started_at = started["joined_at"]

    lesson_exists = (
        db.table("prime_rounds")
        .select("code")
        .eq("code", code)
        .limit(1)
        .execute()
        .data
    )
    if not lesson_exists:
        st.info("이 수업이 삭제됐어요. 입장 화면으로 돌아가 주세요.")
        return

    if show_previous_attempt(db, code, name, started_at):
        show_ranking(db, code)
        return

    show_timer(started_at)
    st.subheader("소수 9개 찾기")

    picks = st.session_state.prime_picks
    st.progress(len(picks) / 9, text=f"선택한 숫자 {len(picks)} / 9")

    with st.container(key="prime_board"):
        for start in range(0, len(board), 5):
            for column, number in zip(st.columns(5), board[start:start + 5]):
                selected = number in picks
                if column.button(
                    str(number),
                    key=f"prime_tile_{code}_{number}",
                    width="stretch",
                    type="primary" if selected else "secondary",
                    disabled=len(picks) >= 9 and not selected,
                ):
                    if selected:
                        picks.remove(number)
                    else:
                        picks.add(number)
                    st.session_state.pop(confirm_key, None)
                    st.rerun()

    confirmed = st.checkbox("선택한 9개를 최종 제출할게요.", key=confirm_key)
    if st.button(
        "최종 제출",
        type="primary",
        width="stretch",
        disabled=len(picks) != 9 or not confirmed,
    ):
        result = db.rpc("prime_submit", {
            "p_code": code,
            "p_student": name,
            "p_picks": sorted(picks),
        }).execute().data

        if result["status"] in {"correct", "wrong"}:
            st.rerun()

        show_outcome(result)


def main():
    apply_style()
    mode = st.sidebar.radio("화면 선택", ["학생", "교사"])

    try:
        config = st.secrets.get("app", st.secrets)
    except FileNotFoundError:
        st.error("Streamlit Cloud에서 이 앱의 Secrets를 찾지 못했어요.")
        return

    if not hasattr(config, "get"):
        st.error("Secrets의 [app] 섹션을 확인해 주세요.")
        return

    fields = ("supabase_url", "supabase_service_role_key", "teacher_password")
    values = {field: config.get(field) for field in fields}
    invalid = [
        field for field, value in values.items()
        if not isinstance(value, str) or not value.strip()
    ]
    if invalid:
        st.error("Secrets에서 확인할 항목 — " + ", ".join(invalid))
        return

    try:
        database = connect(
            values["supabase_url"].strip(),
            values["supabase_service_role_key"].strip(),
        )
    except (ValueError, TypeError):
        st.error("Supabase URL과 키의 형식을 확인해 주세요.")
        return

    try:
        if mode == "교사":
            teacher_page(database, values["teacher_password"])
        else:
            student_page(database)
    except DATABASE_ERRORS as error:
        database_error(error)


main()
