import importlib.util
import os
import uuid
from pathlib import Path
from typing import Any, Optional

import streamlit as st
from dotenv import load_dotenv
from supabase import Client, create_client


def _load_ref_module() -> Any:
    """
    기존 `multi-session-ref.py`를 코드 복붙 없이 재사용하기 위해 동적 로드합니다.
    """
    ref_path = Path(__file__).resolve().parent / "multi-session-ref.py"
    spec = importlib.util.spec_from_file_location("multi_session_ref", ref_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load ref module: {ref_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ref = _load_ref_module()


def render_header() -> None:
    # ref.py 렌더링 스타일을 유지하되, 챗봇명을 프롬프트 값으로 교체합니다.
    c1, c2, c3 = st.columns([1.2, 3.6, 1.2], vertical_alignment="center")
    with c1:
        logo_candidates: list[Path] = []
        try:
            repo_root = Path(__file__).resolve().parents[2]
            logo_candidates.append(repo_root / "대전광역시.png")
        except Exception:
            pass
        logo_candidates.append(Path(__file__).resolve().parent / "대전광역시.png")

        logo_path: Optional[Path] = next((p for p in logo_candidates if p.exists()), None)
        if logo_path is not None:
            st.image(str(logo_path), width=180)
        else:
            st.markdown("<div style='font-size:3rem'>📚</div>", unsafe_allow_html=True)

    with c2:
        st.markdown(
            """
<div style="text-align:center; font-size:3.2rem !important; font-weight:800; line-height:1.05;">
  <span style="color:#1f77b4;">PDF 기반</span>
  <span style="color:#ffd700;">멀티유저</span>
  <span style="color:#1f77b4;">멀티세션</span>
  <span style="color:#ffd700;">RAG</span>
  <span style="color:#1f77b4;">챗봇</span>
</div>
""",
            unsafe_allow_html=True,
        )

    with c3:
        st.write("")


def _get_supabase_anon_client() -> Client:
    url = os.getenv("SUPABASE_URL")
    anon_key = os.getenv("SUPABASE_ANON_KEY")
    if not url or not anon_key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_ANON_KEY 환경 변수가 필요합니다.")
    return create_client(url, anon_key)


def _get_supabase_db_client_from_state() -> Client:
    """
    RLS를 사용하기 때문에, 로그인 성공 후 발급받은 access/refresh token으로 authed client를 생성합니다.
    """
    client = _get_supabase_anon_client()
    access_token = st.session_state.get("sb_access_token")
    refresh_token = st.session_state.get("sb_refresh_token")
    if access_token and refresh_token:
        client.auth.set_session(access_token, refresh_token)
    return client


def _handle_supabase_login(email: str, password: str) -> None:
    anon = _get_supabase_anon_client()
    res = anon.auth.sign_in_with_password({"email": email, "password": password})
    if getattr(res, "session", None) is None:
        raise RuntimeError("로그인 실패: 세션 정보가 없습니다.")

    st.session_state.sb_access_token = res.session.access_token
    st.session_state.sb_refresh_token = res.session.refresh_token
    st.session_state.sb_user_email = email
    # supabase_auth.helpers.User 모델
    st.session_state.sb_user_id = getattr(getattr(res, "user", None), "id", None)


def _handle_supabase_signup(email: str, password: str) -> None:
    anon = _get_supabase_anon_client()
    # email_confirm을 켜둔 경우 사용자가 이메일 확인을 해야 할 수 있습니다.
    anon.auth.sign_up({"email": email, "password": password})


def _is_logged_in() -> bool:
    return bool(st.session_state.get("sb_access_token") and st.session_state.get("sb_refresh_token"))


def _set_llm_keys_from_sidebar() -> None:
    """
    프롬프트 요구사항:
    - .env 없이 Streamlit 사이드바에서 API key를 입력받습니다.
    - 입력받은 값은 os.getenv로 바로 읽히도록 os.environ에 주입합니다.
    """
    openai_key = st.text_input("OpenAI API Key", type="password", key="openai_api_key_input")
    anthropic_key = st.text_input("Anthropic API Key", type="password", key="anthropic_api_key_input")
    gemini_key = st.text_input("Gemini API Key", type="password", key="gemini_api_key_input")

    if openai_key:
        os.environ["OPENAI_API_KEY"] = openai_key
    if anthropic_key:
        os.environ["ANTHROPIC_API_KEY"] = anthropic_key
    if gemini_key:
        os.environ["GEMINI_API_KEY"] = gemini_key


def main() -> None:
    load_dotenv()

    st.set_page_config(
        page_title="PDF 기반 멀티유저 멀티세션 RAG 챗봇",
        page_icon="📚",
        layout="wide",
    )
    ref.inject_css()
    ref.init_state()
    render_header()

    supabase: Optional[Client] = None
    model_name: Optional[str] = None
    selected_session_id: Optional[str] = None

    with st.sidebar:
        # 1) LLM key 입력
        st.subheader("API Keys")
        _set_llm_keys_from_sidebar()

        # 2) Supabase auth (login/signup)
        st.subheader("Supabase 로그인/회원가입")
        if _is_logged_in():
            st.success(f"로그인됨: {st.session_state.get('sb_user_email') or 'user'}")
            if st.button("로그아웃", use_container_width=True):
                for k in ["sb_access_token", "sb_refresh_token", "sb_user_id", "sb_user_email"]:
                    st.session_state.pop(k, None)
                st.rerun()
        else:
            login_email = st.text_input("Login ID (email)", key="sb_login_email")
            login_password = st.text_input("Password", type="password", key="sb_login_password")

            c1, c2 = st.columns(2)
            with c1:
                if st.button("회원가입", use_container_width=True):
                    if not login_email or not login_password:
                        st.error("이메일과 비밀번호를 입력해 주세요.")
                    else:
                        try:
                            _handle_supabase_signup(login_email, login_password)
                            st.success("회원가입 요청 완료. (이메일 확인 필요할 수 있습니다.)")
                        except Exception as e:
                            st.error(f"회원가입 실패: {e}")
            with c2:
                if st.button("로그인", use_container_width=True):
                    if not login_email or not login_password:
                        st.error("이메일과 비밀번호를 입력해 주세요.")
                    else:
                        try:
                            _handle_supabase_login(login_email, login_password)
                            st.rerun()
                        except Exception as e:
                            st.error(f"로그인 실패: {e}")

        # 로그인 전에는 채팅/세션 UI를 제공하지 않습니다.
        if not _is_logged_in():
            st.info("Supabase 로그인을 먼저 해 주세요.")
        else:
            # OPENAI_API_KEY 체크(사이드바 입력값을 os.environ에 주입한 뒤 확인)
            if not os.getenv("OPENAI_API_KEY"):
                st.error("OPENAI_API_KEY가 필요합니다. 사이드바에서 입력해 주세요.")
            else:
                # supabase authed client 생성 (RLS 기반)
                try:
                    supabase = _get_supabase_db_client_from_state()
                except Exception as e:
                    st.error(str(e))
                    return

                # 세션 목록은 자주 바뀌지 않으니 렌더 시작 시 캐시 갱신
                if not st.session_state.sessions_cache:
                    try:
                        ref.refresh_sessions_cache(supabase)
                    except Exception as e:
                        ref.LOGGER.warning("fetch sessions failed: %s", e)

                # 3) 세션 관리 UI + 파일 처리 UI
                st.subheader("LLM 모델 선택")
                model_name = st.radio("모델", ["gpt-4o-mini"], index=0, label_visibility="collapsed")

                st.subheader("세션 관리")
                sessions = st.session_state.sessions_cache or []
                options = ref.session_options_for_ui(sessions)
                selected_options = st.multiselect(
                    "세션 선택",
                    options=options,
                    default=[],
                    max_selections=1,
                    label_visibility="collapsed",
                )
                selected_session_id = ref.option_to_session_id(selected_options[0]) if selected_options else None

                if st.button("세션 로드", use_container_width=True, disabled=not selected_session_id):
                    if selected_session_id:
                        try:
                            chat_history, title = ref.load_session_from_db(supabase, selected_session_id)
                            ref.replace_state_with_loaded_session(chat_history, title)
                            st.session_state.active_session_id = selected_session_id
                            st.session_state.last_loaded_session_id = selected_session_id
                            ref.refresh_sessions_cache(supabase)
                            st.rerun()
                        except Exception as e:
                            st.error(f"세션 로드 실패: {e}")

                if st.button("세션 저장", use_container_width=True):
                    try:
                        llm_for_title = ref.get_llm(model_name, temperature=0.3)
                        ref.snapshot_save_current_session(supabase, llm_for_title)
                        ref.refresh_sessions_cache(supabase)
                        st.success("세션 저장 완료")
                    except Exception as e:
                        st.error(f"세션 저장 실패: {e}")

                if st.button("세션 삭제", use_container_width=True, disabled=not sessions):
                    target_id = selected_session_id or st.session_state.active_session_id
                    try:
                        ref.delete_session(supabase, target_id)
                        ref.refresh_sessions_cache(supabase)
                        st.session_state.active_session_id = str(uuid.uuid4())
                        st.session_state.active_session_title = "새 세션"
                        st.session_state.title_generated = False
                        st.session_state.last_loaded_session_id = None
                        st.session_state.chat_history = []
                        st.session_state.conversation_memory = []
                        st.rerun()
                    except Exception as e:
                        st.error(f"세션 삭제 실패: {e}")

                if st.button("화면 초기화", use_container_width=True):
                    st.session_state.active_session_id = str(uuid.uuid4())
                    st.session_state.active_session_title = "새 세션"
                    st.session_state.title_generated = False
                    st.session_state.last_loaded_session_id = None
                    st.session_state.chat_history = []
                    st.session_state.conversation_memory = []
                    st.rerun()

                st.subheader("문서/벡터DB")
                uploaded = st.file_uploader(
                    "PDF 업로드",
                    type=["pdf"],
                    accept_multiple_files=True,
                    label_visibility="collapsed",
                )
                if st.button("파일 처리하기", use_container_width=True):
                    files = uploaded or []
                    if not files:
                        st.warning("PDF 파일을 업로드해 주세요.")
                    else:
                        try:
                            embeddings = ref.OpenAIEmbeddings(model=ref.EMBEDDING_MODEL)
                            for f in files:
                                ref.embed_and_store_pdf(
                                    supabase=supabase,
                                    embeddings=embeddings,
                                    pdf_file=f,
                                    session_id=st.session_state.active_session_id,
                                )
                            ref.auto_save_current_session(
                                supabase,
                                llm_for_title=ref.get_llm(model_name, temperature=0.3),
                            )
                            st.success("파일 처리 및 세션 자동 저장 완료")
                            ref.refresh_sessions_cache(supabase)
                        except Exception as e:
                            ref.LOGGER.warning("file process failed: %s", e)
                            st.error(f"파일 처리 실패: {e}")

                if st.button("vectordb", use_container_width=True):
                    try:
                        resp = (
                            supabase.table("session_files")
                            .select("file_name")
                            .eq("session_id", st.session_state.active_session_id)
                            .execute()
                        )
                        files = [r.get("file_name") for r in getattr(resp, "data", []) or [] if r.get("file_name")]
                        uniq = sorted(set(files))
                        if not uniq:
                            st.info("현재 세션에 연결된 파일이 없습니다.")
                        else:
                            st.write("현재 vectordb 파일 목록")
                            for name in uniq:
                                st.text(f"- {name}")
                    except Exception as e:
                        st.error(f"vectordb 조회 실패: {e}")

                st.subheader("현재 설정")
                st.text(f"모델: {model_name}")
                st.text(f"활성 세션: {st.session_state.active_session_title}")

    # 로그인/환경 설정이 완료되지 않으면 아래 채팅 로직을 실행하지 않습니다.
    if supabase is None or model_name is None:
        st.stop()

    # 메인: 채팅 기록 렌더링
    for msg in st.session_state.chat_history:
        role = msg.get("role", "assistant")
        content = msg.get("content", "")
        bubble_class = "chat-user" if role == "user" else "chat-assistant"
        who = "사용자" if role == "user" else "assistant"
        with st.chat_message(who):
            st.markdown(f"<div class='chat-bubble {bubble_class}'>{content}</div>", unsafe_allow_html=True)

    # 세션 자동 로드(멀티선택 변경 시 자동으로 반영)
    if selected_session_id and selected_session_id != st.session_state.last_loaded_session_id:
        try:
            chat_history, title = ref.load_session_from_db(supabase, selected_session_id)
            ref.replace_state_with_loaded_session(chat_history, title)
            st.session_state.active_session_id = selected_session_id
            st.session_state.last_loaded_session_id = selected_session_id
            st.rerun()
        except Exception:
            pass

    user_input = st.chat_input("질문을 입력해 주세요.")
    if not user_input:
        return
    if not os.getenv("OPENAI_API_KEY"):
        st.error("OPENAI_API_KEY 환경 변수가 필요합니다.")
        return

    ref.add_message("user", user_input)

    try:
        llm = ref.get_llm(model_name, temperature=0.7)
        embeddings = ref.OpenAIEmbeddings(model=ref.EMBEDDING_MODEL)
    except Exception as e:
        st.error(f"초기화 실패: {e}")
        return

    with st.chat_message("assistant"):
        placeholder = st.empty()
        buf: list[str] = []
        final_answer = ""

        try:
            # active session에 연결된 문서가 없으면 direct answer로 fallback합니다.
            mapped_files_resp = (
                supabase.table("session_files")
                .select("file_hash")
                .eq("session_id", st.session_state.active_session_id)
                .limit(1)
                .execute()
            )
            has_docs = bool(getattr(mapped_files_resp, "data", None))

            if has_docs:
                stream = ref.rag_answer_stream(
                    llm=llm,
                    supabase=supabase,
                    embeddings=embeddings,
                    session_id=st.session_state.active_session_id,
                    question=user_input,
                    memory=st.session_state.conversation_memory,
                )
            else:
                stream = ref.direct_answer_stream(
                    llm=llm,
                    question=user_input,
                    memory=st.session_state.conversation_memory,
                )

            for piece in stream:
                buf.append(piece)
                final_answer = ref.remove_separators("".join(buf))
                placeholder.markdown(final_answer)
        except Exception as e:
            ref.LOGGER.warning("answer generation failed: %s", e)
            st.error("답변 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.")
            return

        try:
            followups = ref.generate_followup_questions(ref.get_llm(model_name, temperature=0.3), final_answer)
        except Exception as e:
            ref.LOGGER.warning("followups failed: %s", e)
            followups = (
                "1. 더 자세히 알고 싶은 부분은 무엇인가요?\n"
                "2. 절차를 단계별로 설명해 주실 수 있나요?\n"
                "3. 관련 주의사항을 알려주실 수 있나요?"
            )

        final_answer = ref.remove_separators(final_answer).strip()
        final_answer = (
            f"{final_answer}\n\n### 💡 다음에 물어볼 수 있는 질문들\n{ref.remove_separators(followups)}"
        ).strip()
        final_answer = ref.insert_sentence_linebreaks(final_answer)
        final_answer = ref.normalize_korean_spacing(final_answer)
        placeholder.markdown(final_answer)

    ref.add_message("assistant", final_answer)

    # 자동 저장: 대화 후 세션을 저장합니다.
    try:
        ref.auto_save_current_session(supabase, llm_for_title=ref.get_llm(model_name, temperature=0.3))
        ref.refresh_sessions_cache(supabase)
    except Exception as e:
        ref.LOGGER.warning("auto_save failed: %s", e)


if __name__ == "__main__":
    main()


# test
