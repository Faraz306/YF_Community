
import streamlit as st
import sqlite3 as sql
import bcrypt
from PIL import Image
from google import genai

YF = Image.open("YF.png")

st.set_page_config(
    page_title="YF Coding/Chatting Community",
    page_icon=YF,
    layout="wide"
)


def get_community_db():
    conn = sql.connect("yf_database.db", check_same_thread=False)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    return conn


def get_accounts_db():
    conn = sql.connect("yf_accounts.db", check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS usernames (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE COLLATE NOCASE NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS passwords (
            user_id INTEGER PRIMARY KEY,
            password_hash TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES usernames(id) ON DELETE CASCADE
        )
    """)

    conn.commit()
    return conn


def get_ai_db():
    conn = sql.connect("yf_ai_chats.db", check_same_thread=False)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            role TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    return conn


community_db = get_community_db()
community_db.close()

accounts_db = get_accounts_db()
accounts_db.close()

ai_db = get_ai_db()
ai_db.close()


def validate_password(password):
    if len(password) < 12:
        return False, "Password must contain at least 12 characters."

    if len(password.encode("utf-8")) > 72:
        return False, "Password is too long. Please choose a shorter password."

    if not any(c.isupper() for c in password):
        return False, "Password needs at least one uppercase letter."

    if not any(c.islower() for c in password):
        return False, "Password needs at least one lowercase letter."

    if not any(c.isdigit() for c in password):
        return False, "Password needs at least one number."

    if not any(not c.isalnum() for c in password):
        return False, "Password needs at least one symbol."

    return True, "Password is valid."


def signup(username, password):
    username = username.strip()

    if not username:
        return False, "Please enter a username."

    valid, message = validate_password(password)

    if not valid:
        return False, message

    password_hash = bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("ascii")

    conn = get_accounts_db()

    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO usernames (username) VALUES (?)",
                (username,)
            )

            user_id = cursor.lastrowid

            conn.execute(
                "INSERT INTO passwords (user_id, password_hash) VALUES (?, ?)",
                (user_id, password_hash)
            )

        return True, "Account created successfully."

    except sql.IntegrityError:
        return False, "This username is already taken."

    finally:
        conn.close()


def login(username, password):
    conn = get_accounts_db()

    try:
        result = conn.execute("""
            SELECT passwords.password_hash
            FROM usernames
            JOIN passwords ON usernames.id = passwords.user_id
            WHERE usernames.username = ?
        """, (username.strip(),)).fetchone()

        if result is None:
            return False

        return bcrypt.checkpw(
            password.encode("utf-8"),
            result[0].encode("ascii")
        )

    finally:
        conn.close()


def save_message(username, message):
    conn = get_community_db()

    try:
        conn.execute(
            "INSERT INTO messages (username, message) VALUES (?, ?)",
            (username, message)
        )
        conn.commit()
    finally:
        conn.close()


def get_messages():
    conn = get_community_db()

    try:
        return conn.execute("""
            SELECT username, message, created_at
            FROM messages
            ORDER BY id DESC
            LIMIT 200
        """).fetchall()[::-1]
    finally:
        conn.close()


def save_ai_message(username, role, message):
    conn = get_ai_db()

    try:
        conn.execute("""
            INSERT INTO chat_history (username, role, message)
            VALUES (?, ?, ?)
        """, (username, role, message))

        conn.commit()
    finally:
        conn.close()


def get_ai_history(username):
    conn = get_ai_db()

    try:
        return conn.execute("""
            SELECT role, message, created_at
            FROM chat_history
            WHERE username = ?
            ORDER BY id ASC
        """, (username,)).fetchall()
    finally:
        conn.close()


def generate_ai_response(api_key, username, prompt):
    client = genai.Client(api_key=api_key)

    history = get_ai_history(username)

    contents = []

    for role, message, created_at in history[-30:]:
        contents.append({
            "role": role,
            "parts": [{"text": message}]
        })

    contents.append({
        "role": "user",
        "parts": [{"text": prompt}]
    })

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents
    )

    return response.text


if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "username" not in st.session_state:
    st.session_state.username = ""


if not st.session_state.logged_in:

    st.title("YF Coding/Chatting Community")
    st.divider()

    left, right = st.columns(2)

    with left:
        st.image(YF, width=250)
        st.caption("Welcome to the YF Community!")

    with right:
        choice = st.radio(
            "Account",
            ["Login", "Sign Up"],
            horizontal=True
        )

        if choice == "Sign Up":
            name = st.text_input("Username", key="signup_name")

            password = st.text_input(
                "Password",
                type="password",
                key="signup_password"
            )

            confirm_password = st.text_input(
                "Confirm Password",
                type="password"
            )

            st.caption(
                "Minimum 12 characters, with uppercase, lowercase, "
                "number and symbol. Maximum 72 characters."
            )

            if st.button("Create Account", use_container_width=True):

                if password != confirm_password:
                    st.error("Passwords do not match.")

                else:
                    success, message = signup(name, password)

                    if success:
                        st.session_state.logged_in = True
                        st.session_state.username = name.strip()
                        st.rerun()
                    else:
                        st.error(message)

        else:
            name = st.text_input("Username", key="login_name")

            password = st.text_input(
                "Password",
                type="password",
                key="login_password"
            )

            if st.button("Login", use_container_width=True):

                if login(name, password):
                    st.session_state.logged_in = True
                    st.session_state.username = name.strip()
                    st.rerun()
                else:
                    st.error("Incorrect username or password.")


else:

    st.image(YF, width=100)
    st.title("YF Community")
    st.write(f"Welcome, **{st.session_state.username}**!")

    if st.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.rerun()

    chat_tab, ai_tab = st.tabs([
        "YF Chatting server",
        "YF AI"
    ])

    with chat_tab:

        st.subheader("YF Coding and Cool apps + Robotics")

        @st.fragment(run_every="2s")
        def community_chat():

            messages = get_messages()

            for username, message, created_at in messages:

                if username.casefold() == st.session_state.username.casefold():
                    with st.chat_message("user"):
                        st.caption(f"You · {created_at}")
                        st.write(message)

                else:
                    with st.chat_message("assistant"):
                        st.caption(f"{username} · {created_at}")
                        st.write(message)

            new_message = st.chat_input(
                "Message the YF Community...",
                key="community_input"
            )

            if new_message and new_message.strip():
                save_message(
                    st.session_state.username,
                    new_message.strip()
                )
                st.rerun()

        community_chat()

        with ai_tab:

            st.subheader("YF AI")

            api_key = st.text_input(
                "Google Gemini API Key",
                type="password",
                key="yf_ai_api_key"
            )

            st.divider()

            username = st.session_state.username

            history = get_ai_history(username)

            for role, message, created_at in history:
                if role == "user":
                    with st.chat_message("user"):
                        st.caption(f"You · {created_at}")
                        st.write(message)
                else:
                    with st.chat_message("assistant"):
                        st.caption(f"YF AI · {created_at}")
                        st.write(message)

            prompt = st.chat_input(
                "Ask YF AI anything...",
                key="yf_ai_input"
            )

            if prompt and prompt.strip():

                if not api_key:
                    st.error("Enter your Gemini API key first.")

                else:
                    try:
                        client = genai.Client(api_key=api_key)

                        instructions = f"""
    You are YF AI, the official AI assistant of the YF ecosystem.

    IDENTITY:
    Your name is YF AI.
    You are part of the YF ecosystem.
    You are currently assisting the user: {username}.

    MAIN INSTRUCTIONS:
    1. Be helpful, intelligent, friendly and respectful.
    2. Answer questions accurately.
    3. Help with Python, programming, robotics, technology,
       science, mathematics and app development.
    4. Explain complicated topics step by step.
    5. When providing code, make it complete and runnable
       whenever appropriate.
    6. Never claim that you performed an action you did not perform.
    7. Never invent information.
    8. Maintain context throughout the conversation.
    9. Understand follow-up questions using previous messages.
    10. Keep responses relevant to the user's question.

    CONTEXT RULES:
    Use the conversation history supplied below.
    Remember the earlier questions and answers in this conversation.
    Do not treat every new message as an unrelated conversation.
    """

                        contents = []

                        for role, message, created_at in history[-30:]:
                            contents.append({
                                "role": "user" if role == "user" else "model",
                                "parts": [{"text": message}]
                            })

                        contents.append({
                            "role": "user",
                            "parts": [{"text": prompt.strip()}]
                        })

                        with st.spinner("YF AI is thinking..."):

                            response = client.models.generate_content(
                                model="gemini-3.8-flash",
                                contents=contents,
                                config={
                                    "system_instruction": instructions,
                                    "temperature": 0.7
                                }
                            )

                        answer = response.text

                        if not answer:
                            st.error("YF AI returned an empty response.")

                        else:
                            save_ai_message(
                                username,
                                "user",
                                prompt.strip()
                            )

                            save_ai_message(
                                username,
                                "model",
                                answer
                            )

                            st.rerun()

                    except Exception as e:
                        st.error("YF AI generation failed:")
                        st.exception(e)
