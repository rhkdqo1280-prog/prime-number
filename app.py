import hmac
import random
import secrets
import unicodedata
from math import isqrt

import streamlit as st
from postgrest.exceptions import APIError
from supabase import create_client


st.set_page_config(page_title="소수 찾기", page_icon="🔢")

CLASSES = [f"1학년 {number}반" for number in range(1, 6)]


@st.cache_resource
def connect(url, key):
    return create_client(url, key)


def normalize(value):
    return " ".join(unicodedata.normalize("NFKC", value).split())


def make_board():
    odds = range(11, 76, 2)
    primes = [n for n in odds if all(n % d for d in range(2, isqrt(n) + 1))]
    composites = [n for n in odds if n not in primes]
    answer = random.sample(primes, 9)
    board = answer + random.sample(composites, 16)
    random.shuffle(board)
    return board, answer


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
            .select("student,correct")
            .eq("code", code)
            .order("id")
            .execute()
            .data
        )
    except APIError:
        st.error("순위를 불러오지 못했어요. 잠시 후 자동으로 다시 확인해요.")
        return

    ranked = [row["student"] for row in attempts if row["correct"]]
    st.caption(f"전체 제출 {len(attempts)}명 / 모두 정답 {len(ranked)}명")

    if ranked:
        st.table([
            {"순위": rank, "이름": name}
            for rank, name in enumerate(ranked, start=1)
        ])
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
        names = load_roster(db, classroom)
        if not names:
            st.warning("먼저 이 반의 명단을 저장해 주세요.")
        else:
            board, answer = make_board()
            code = secrets.token_hex(4).upper()
            db.table("prime_rounds").insert({
                "code": code,
                "classroom": classroom,
                "names": names,
                "board": board,
                "answer": answer,
            }).execute()
            st.session_state[results_key] = code
            st.success(f"{classroom} 수업을 열었어요. 학생은 이름만 입력하면 돼요.")

    st.caption("학생은 가장 최근에 연 수업으로 입장해요. 순위 조회에서 과거 수업을 선택해도 입장 대상은 바뀌지 않아요.")

    rounds = (
        db.table("prime_rounds")
        .select("code")
        .eq("classroom", classroom)
        .order("created_at", desc=True)
        .order("code", desc=True)
        .limit(50)
        .execute()
        .data
    )

    if rounds:
        code = st.selectbox(
            "순위를 볼 수업",
            [row["code"] for row in rounds],
            key=results_key,
        )
        show_results(db, code)


def show_outcome(result):
    status = result["status"]

    if status == "correct":
        st.success(f"9개 모두 정답! {result['rank']}위예요.")
    elif status == "wrong":
        st.error("오답이 포함되어 순위에서 제외됐어요. 제출 기회를 사용했어요.")
    elif status == "denied":
        st.error("수업 명단에 등록된 이름을 확인해 주세요.")
    else:
        st.error("숫자판에서 서로 다른 숫자 9개를 선택해 주세요.")


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

        rounds = (
            db.table("prime_rounds")
            .select("code,classroom,names,board")
            .order("created_at", desc=True)
            .order("code", desc=True)
            .limit(1)
            .execute()
            .data
        )

        if not rounds:
            st.info("선생님이 수업을 열면 입장할 수 있어요.")
            return

        game = rounds[0]
        if name not in game["names"]:
            st.error("지금 열린 수업의 명단에 없는 이름이에요.")
            return

        st.session_state.entry = (
            game["code"], name, game["classroom"], game["board"]
        )
        st.rerun()

    code, name, classroom, board = entry
    confirmation_key = f"confirm_{code}_{name}"
    st.caption(f"{classroom} / {name}")

    if st.button("입장 화면으로"):
        for key in ("entry", "outcome", "picks", confirmation_key):
            st.session_state.pop(key, None)
        st.rerun()

    if "outcome" in st.session_state:
        show_outcome(st.session_state.outcome)
        return

    previous = (
        db.table("prime_attempts")
        .select("id,correct")
        .eq("code", code)
        .eq("student", name)
        .execute()
        .data
    )

    if previous:
        attempt = previous[0]
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
        return

    st.write("홀수 25개에서 소수 9개를 고르세요. 한 번만 제출할 수 있고, 하나라도 틀리면 순위에서 제외돼요.")

    if "picks" not in st.session_state:
        st.session_state.picks = set()

    picks = st.session_state.picks

    for start in range(0, len(board), 5):
        columns = st.columns(5)
        for column, number in zip(columns, board[start:start + 5]):
            selected = number in picks
            clicked = column.button(
                str(number),
                key=f"tile_{code}_{number}",
                width="stretch",
                type="primary" if selected else "secondary",
                disabled=len(picks) == 9 and not selected,
            )
            if clicked:
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
            st.session_state.outcome = result
            st.rerun()

        show_outcome(result)


st.title("소수 찾기")
mode = st.sidebar.radio("화면 선택", ["학생", "교사"])

try:
    config = st.secrets.get("app")
    if config is None:
        config = st.secrets
except FileNotFoundError:
    st.error("Streamlit Cloud에서 이 앱에 저장된 Secrets를 찾지 못했어요.")
    st.stop()

if not hasattr(config, "get"):
    st.error("Secrets에서 app이 섹션으로 설정되어 있는지 확인해 주세요.")
    st.stop()

fields = ("supabase_url", "supabase_service_role_key", "teacher_password")
values = {field: config.get(field) for field in fields}
invalid = [
    field for field, value in values.items()
    if not isinstance(value, str) or not value.strip()
]

if invalid:
    st.error("Secrets에서 확인할 항목 — " + ", ".join(invalid))
    st.stop()

try:
    database = connect(
        values["supabase_url"].strip(),
        values["supabase_service_role_key"].strip(),
    )
except (ValueError, TypeError):
    st.error("Supabase URL과 키의 형식을 확인해 주세요.")
    st.stop()

try:
    if mode == "교사":
        teacher_page(database, values["teacher_password"])
    else:
        student_page(database)
except APIError:
    st.error("데이터베이스 요청에 실패했어요. Supabase 설정을 확인해 주세요.")
