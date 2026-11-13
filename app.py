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
    rows = db.table("prime_rosters").select("names").eq("classroom", classroom).execute().data
    return rows[0]["names"] if rows else []


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
            "한 줄에 한 명씩 붙여넣으세요. 동명이인은 번호와 이름을 함께 등록하세요.",
            value="\n".join(load_roster(db, classroom)),
            height=210,
            key=f"roster_text_{classroom}",
        )
        save = st.form_submit_button("이 반 명단 저장")
    if save:
        names = [name for line in roster_text.splitlines() if (name := normalize(line))]
        if not names or len(names) > 100 or any(len(name) > 40 for name in names):
            st.error("1~100명까지 등록할 수 있어요. 각 이름은 40자 이내로 입력해 주세요.")
        elif len(set(names)) != len(names):
            st.error("같은 이름이 두 번 들어 있어요. 동명이인만 번호를 붙여 주세요.")
        else:
            db.table("prime_rosters").upsert({"classroom": classroom, "names": names}).execute()
            st.success(f"{classroom} 명단 {len(names)}명을 저장했어요.")

    st.subheader("수업 열기")
    if st.button("새 수업 만들기", type="primary"):
        names = load_roster(db, classroom)
        if not names:
            st.warning("먼저 이 반의 명단을 저장해 주세요.")
        else:
            board, answer = make_board()
            code = secrets.token_hex(4).upper()
            db.table("prime_rounds").insert({
                "code": code, "classroom": classroom, "names": names,
                "board": board, "answer": answer,
            }).execute()
            st.session_state[f"results_{classroom}"] = code

    rounds = db.table("prime_rounds").select("code").eq(
        "classroom", classroom
    ).order("created_at", desc=True).limit(50).execute().data
    if rounds:
        code = st.selectbox("순위를 볼 수업 코드", [row["code"] for row in rounds],
                            key=f"results_{classroom}")
        st.code(code)
        st.caption("학생에게 앱 주소와 수업 코드를 알려 주세요. 새 수업에는 개설 시점의 명단이 적용돼요.")
        show_results(db, code)


@st.fragment(run_every="3s")
def show_results(db, code):
    attempts = db.table("prime_attempts").select("student,correct").eq(
        "code", code
    ).order("id").execute().data
    ranked = [row["student"] for row in attempts if row["correct"]]
    st.caption(f"전체 제출 {len(attempts)}명 / 모두 정답 {len(ranked)}명")
    if ranked:
        st.table([{"순위": i, "이름": name} for i, name in enumerate(ranked, 1)])
    else:
        st.info("아직 모든 소수를 맞힌 학생이 없어요.")


def show_outcome(result):
    status = result["status"]
    if status == "correct":
        st.success(f"9개 모두 정답! {result['rank']}위예요.")
    elif status == "wrong":
        st.error("오답이 포함되어 순위에서 제외됐어요. 제출 기회를 사용했어요.")
    elif status == "denied":
        st.error("수업 코드와 등록된 이름을 확인해 주세요.")
    else:
        st.error("숫자판에서 서로 다른 숫자 9개를 선택해 주세요.")


def student_page(db):
    entry = st.session_state.get("entry")
    if not entry:
        with st.form("join"):
            code = st.text_input("수업 코드", max_chars=8).strip().upper()
            name = normalize(st.text_input("등록된 이름", max_chars=40))
            join = st.form_submit_button("입장", type="primary")
        if join and code and name:
            rows = db.table("prime_rounds").select("classroom,names,board").eq(
                "code", code
            ).execute().data
            if not rows or name not in rows[0]["names"]:
                st.error("수업 코드와 등록된 이름을 확인해 주세요.")
                return
            game = rows[0]
            st.session_state.entry = (code, name, game["classroom"], game["board"])
            st.rerun()
        elif join:
            st.error("수업 코드와 이름을 모두 입력해 주세요.")
        return

    code, name, classroom, board = entry
    st.caption(f"{classroom} / {name} / 수업 코드 {code}")
    if st.button("입장 화면으로"):
        for key in ("entry", "outcome", "picks"):
            st.session_state.pop(key, None)
        st.rerun()
    if "outcome" in st.session_state:
        show_outcome(st.session_state.outcome)
        return

    previous = db.table("prime_attempts").select("id,correct").eq(
        "code", code
    ).eq("student", name).execute().data
    if previous:
        if previous[0]["correct"]:
            rank = db.table("prime_attempts").select("id", count="exact").eq(
                "code", code
            ).eq("correct", True).lte("id", previous[0]["id"]).execute().count
            show_outcome({"status": "correct", "rank": rank})
        else:
            show_outcome({"status": "wrong"})
        return

    st.write("홀수 25개에서 소수 9개를 고르세요. 제출은 한 번이며, 하나라도 틀리면 순위에서 제외돼요.")
    if "picks" not in st.session_state:
        st.session_state.picks = set()
    picks = st.session_state.picks
    confirmation_key = f"confirm_{code}_{name}"
    for start in range(0, len(board), 5):
        for column, number in zip(st.columns(5), board[start:start + 5]):
            selected = number in picks
            if column.button(str(number), key=f"tile_{number}", width="stretch",
                             type="primary" if selected else "secondary",
                             disabled=len(picks) == 9 and not selected):
                if selected:
                    picks.remove(number)
                else:
                    picks.add(number)
                st.session_state.pop(confirmation_key, None)
                st.rerun()

    st.write(f"선택한 숫자 {len(picks)} / 9")
    confirmed = st.checkbox("선택한 9개를 최종 제출할게요.", key=confirmation_key)
    if st.button("최종 제출", type="primary", disabled=len(picks) != 9 or not confirmed):
        result = db.rpc("prime_submit", {
            "p_code": code, "p_student": name, "p_picks": sorted(picks),
        }).execute().data
        if result["status"] in {"correct", "wrong"}:
            st.session_state.outcome = result
            st.rerun()
        show_outcome(result)


st.title("소수 찾기")
mode = st.sidebar.radio("화면 선택", ["학생", "교사"])
try:
    config = st.secrets["app"]
    database = connect(config["supabase_url"], config["supabase_service_role_key"])
    if mode == "교사":
        teacher_page(database, config["teacher_password"])
    else:
        student_page(database)
except (KeyError, FileNotFoundError):
    st.error("Streamlit의 Secrets에 [app] 설정을 입력해 주세요.")
except APIError:
    st.error("데이터베이스 요청에 실패했어요. 잠시 후 다시 시도하거나 Supabase 설정을 확인해 주세요.")
