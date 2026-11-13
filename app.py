import hmac
import random
import secrets
import unicodedata
from datetime import datetime, timezone
from math import isqrt

import streamlit as st
from httpx import RequestError
from postgrest.exceptions import APIError
from supabase import create_client


st.set_page_config(page_title="소수 찾기", page_icon="🔢")

CLASSES = [f"1학년 {number}반" for number in range(1, 6)]
KOREA_TIME = timezone.utc
# 한국 표준시 UTC+09:00
from datetime import timedelta

KOREA_TIME = timezone(timedelta(hours=9))


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


@st.fragment(run_every="3s")
def show_results(db, code):
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
    except (APIError, RequestError) as error:
        database_error(error)
        return

    joined_at_by_student = {
        entry["student"]: entry["joined_at"] for entry in entries
    }

    ranked = []
    for attempt in attempts:
        if not attempt["correct"]:
            continue

        name = attempt["student"]
        joined_at = joined_at_by_student.get(name)
        submitted_at = attempt["submitted_at"]
        ranked.append({
            "순위": len(ranked) + 1,
            "이름": name,
            "입장 시각": clock_text(joined_at),
            "제출 시각": clock_text(submitted_at),
            "풀이 시간": elapsed_text(joined_at, submitted_at),
        })

    st.caption(
        f"입장 {len(entries)}명 / 제출 {len(attempts)}명 / 모두 정답 {len(ranked)}명"
    )

    if ranked:
        st.dataframe(ranked, hide_index=True, width="stretch")
    else:
        st.info("아직 소수 9개를 모두 맞힌 학생이 없어요.")


def teacher_page(db, password):
    if not st.session_state.get("teacher"):
        with st.form("teacher_login"):
            entered = st.text_input("교사 비밀번호", type="password")
            login = st.form_submit_button("로그인")

        if login:
            if hmac.compare_digest(entered.encode(), password.encode()):
                st.session_state.teacher = True
                st.rerun()
            st.error("교사 비밀번호를 확인해 주세요.")
        return

    if st.button("교사 로그아웃"):
        st.session_state.teacher = False
        st.rerun()

    if notice := st.session_state.pop("teacher_notice", None):
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

    active = (
        db.table("prime_rounds")
        .select("classroom")
        .eq("accepting_entries", True)
        .limit(1)
        .execute()
        .data
    )
    if active:
        st.caption(f"현재 입장 가능한 수업은 {active[0]['classroom']}이에요.")
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

    st.subheader("순위")
    code = st.selectbox(
        "순위를 볼 수업",
        list(by_code),
        format_func=round_label,
        key=results_key,
    )
    show_results(db, code)

    with st.expander("이 수업 기록 삭제"):
        st.warning(
            "선택한 수업의 숫자판, 입장 기록, 제출 기록과 순위를 삭제합니다. "
            "반별 학생 명단은 유지됩니다."
        )
        confirm_delete = st.checkbox(
            "선택한 수업의 기록을 삭제할게요.",
            key=f"delete_confirm_{code}",
        )
        if st.button(
            "이 수업 영구 삭제",
            disabled=not confirm_delete,
            key=f"delete_round_{code}",
        ):
            db.table("prime_rounds").delete().eq("code", code).execute()
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


def show_previous_attempt(db, code, name, joined_at):
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
        f"풀이 시간 {elapsed_text(joined_at, submitted_at)}"
    )
    return True


@st.fragment(run_every="1s")
def show_timer(joined_at):
    now = datetime.now(timezone.utc).isoformat()
    st.metric("입장 후 경과 시간", elapsed_text(joined_at, now))


def student_page(db):
    entry = st.session_state.get("entry")

    if not entry:
        with st.form("join"):
            name = normalize(st.text_input("이름", max_chars=40))
            join = st.form_submit_button("입장", type="primary")

        if not join:
            return
        if not name:
            st.error("이름을 입력해 주세요.")
            return

        result = db.rpc("prime_join_round", {"p_student": name}).execute().data
        if result["status"] == "closed":
            st.info("선생님이 수업을 열면 입장할 수 있어요.")
            return
        if result["status"] == "denied":
            st.error("지금 열린 수업의 명단에 없는 이름이에요.")
            return

        st.session_state.entry = {**result, "student": name}
        st.rerun()

    code = entry["code"]
    name = entry["student"]
    board = entry["board"]
    joined_at = entry["joined_at"]
    confirmation_key = f"confirm_{code}_{name}"

    st.caption(f"{entry['classroom']} / {name}")

    if st.button("입장 화면으로"):
        for key in ("entry", "picks", confirmation_key):
            st.session_state.pop(key, None)
        st.rerun()

    if show_previous_attempt(db, code, name, joined_at):
        return

    lesson = (
        db.table("prime_rounds")
        .select("code")
        .eq("code", code)
        .limit(1)
        .execute()
        .data
    )
    if not lesson:
        st.info("이 수업 기록이 삭제됐어요. 입장 화면으로 돌아가 주세요.")
        return

    show_timer(joined_at)
    st.write("홀수 25개에서 소수 9개를 고르세요. 한 번만 제출할 수 있어요.")

    if "picks" not in st.session_state:
        st.session_state.picks = set()
    picks = st.session_state.picks

    for start in range(0, len(board), 5):
        for column, number in zip(st.columns(5), board[start:start + 5]):
            selected = number in picks
            if column.button(
                str(number),
                key=f"tile_{code}_{number}",
                width="stretch",
                type="primary" if selected else "secondary",
                disabled=len(picks) >= 9 and not selected,
            ):
                if selected:
                    picks.remove(number)
                else:
                    picks.add(number)
                st.session_state.pop(confirmation_key, None)
                st.rerun()

    st.write(f"선택한 숫자 {len(picks)} / 9")
    confirmed = st.checkbox(
        "선택한 9개를 최종 제출할게요.",
        key=confirmation_key,
    )

    if st.button(
        "최종 제출",
        type="primary",
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
    st.title("소수 찾기")
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
    except (APIError, RequestError) as error:
        database_error(error)


main()
