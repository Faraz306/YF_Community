
import os
import sqlite3 as sql
import bcrypt
import streamlit as st

from pathlib import Path
from PIL import Image
from google import genai


# ============================================================
# 1. CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="YF Community",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded"
)

APP_DIR = Path(__file__).resolve().parent

# Optional persistent directory:
# Set YF_DATA_DIR as an environment variable when deploying.
DATA_DIR = Path(
    os.environ.get("YF_DATA_DIR", str(APP_DIR))
).expanduser().resolve()

DATA_DIR.mkdir(parents=True, exist_ok=True)

ACCOUNT_DB = DATA_DIR / "yf_accounts.db"
COMMUNITY_DB = DATA_DIR / "yf_database.db"
AI_DB = DATA_DIR / "yf_ai_chats.db"

try:
    YF_LOGO = Image.open(APP_DIR / "YF.png")
except Exception:
    YF_LOGO = None


# ============================================================
# 2. MODERN INTERFACE
# ============================================================

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    .stApp {
        background:
            radial-gradient(ellipse at 10% 0%, #172554 0%, transparent 35%),
            radial-gradient(ellipse at 90% 100%, #312e81 0%, transparent 30%),
            #080c18;
        color: #f1f5f9;
    }

    [data-testid="stSidebar"] {
        background: #0d1425;
        border-right: 1px solid #25324a;
    }

    .hero {
        padding: 35px;
        border-radius: 22px;
        background: linear-gradient(135deg, #172554, #312e81, #111827);
        border: 1px solid #384b83;
        margin-bottom: 25px;
    }

    .hero h1 {
        font-size: 42px;
        font-weight: 800;
        color: white;
        margin-bottom: 8px;
    }

    .hero p {
        color: #cbd5e1;
        font-size: 16px;
    }

    .glass-card {
        padding: 25px;
        background: rgba(20, 30, 52, 0.85);
        border: 1px solid #334155;
        border-radius: 18px;
        margin-bottom: 15px;
    }

    .feature-title {
        font-size: 20px;
        font-weight: 700;
        color: #e2e8f0;
    }

    .muted {
        color: #94a3b8;
        font-size: 14px;
    }

    .stButton > button {
        border-radius: 11px;
        min-height: 43px;
        font-weight: 700;
        border: 1px solid #4756a8;
        background: linear-gradient(135deg, #4f46e5, #6366f1);
        color: white;
        transition: 0.2s ease;
    }

    .stButton > button:hover {
        border-color: #a5b4fc;
        background: linear-gradient(135deg, #4338ca, #4f46e5);
        transform: translateY(-2px);
    }

    .stTextInput input {
        border-radius: 10px;
        background: #111827;
        border: 1px solid #334155;
        color: white;
    }

    .stTabs [data-baseweb="tab"] {
        font-weight: 700;
    }

    .stTabs [aria-selected="true"] {
        color: #a5b4fc;
    }

    [data-testid="stChatMessage"] {
        border: 1px solid #26354d;
        border-radius: 15px;
        background: rgba(20, 30, 52, 0.7);
        padding: 12px;
    }

    hr {
        border-color: #273449;
    }

    #MainMenu, footer {
        visibility: hidden;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
# 3. DATABASE CONNECTIONS
# ============================================================

def connect_db(path):
    conn = sql.connect(
        str(path),
        timeout=30,
        check_same_thread=False
    )

    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")

    return conn


def get_accounts_db():
    conn = connect_db(ACCOUNT_DB)

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
            FOREIGN KEY (user_id)
                REFERENCES usernames(id)
                ON DELETE CASCADE
        )
    """)

    conn.commit()
    return conn


def get_community_db():
    conn = connect_db(COMMUNITY_DB)

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


def get_ai_db():
    conn = connect_db(AI_DB)

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


# Initialize all databases.
for database_function in (
    get_accounts_db,
    get_community_db,
    get_ai_db
):
    connection = database_function()
    connection.close()


# ============================================================
# 4. ACCOUNT VALIDATION
# ============================================================

def validate_password(password):

    if len(password) < 12:
        return False, "Use at least 12 characters."

    if len(password.encode("utf-8")) > 72:
        return False, "Password exceeds bcrypt's 72-byte limit."

    if not any(c.isupper() for c in password):
        return False, "Add at least one uppercase letter."

    if not any(c.islower() for c in password):
        return False, "Add at least one lowercase letter."

    if not any(c.isdigit() for c in password):
        return False, "Add at least one number."

    if not any(not c.isalnum() for c in password):
        return False, "Add at least one symbol."

    return True, "Password accepted."


# ============================================================
# 5. SIGNUP
# ============================================================

def signup(username, password):

    username = username.strip()

    if not username:
        return False, "Username cannot be empty."

    if len(username) > 30:
        return False, "Username must be 30 characters or fewer."

    if any(c.isspace() for c in username):
        return False, "Username cannot contain spaces."

    if not all(c.isalnum() or c in "_-" for c in username):
        return False, "Use only letters, numbers, _ and -."

    valid, message = validate_password(password)

    if not valid:
        return False, message

    password_hash = bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=12)
    ).decode("ascii")

    conn = get_accounts_db()

    try:
        with conn:

            cursor = conn.execute("""
                INSERT INTO usernames (username)
                VALUES (?)
            """, (username,))

            user_id = cursor.lastrowid

            conn.execute("""
                INSERT INTO passwords (user_id, password_hash)
                VALUES (?, ?)
            """, (user_id, password_hash))

        return True, "Your YF account has been created!"

    except sql.IntegrityError:
        return False, "That username is already registered."

    except sql.Error:
        return False, "Database error while creating your account."

    finally:
        conn.close()


# ============================================================
# 6. LOGIN
# ============================================================

def login(username, password):

    username = username.strip()

    if not username or not password:
        return False

    conn = get_accounts_db()

    try:
        result = conn.execute("""
            SELECT passwords.password_hash
            FROM usernames
            INNER JOIN passwords
                ON usernames.id = passwords.user_id
            WHERE usernames.username = ? COLLATE NOCASE
        """, (username,)).fetchone()

        if result is None:
            return False

        stored_hash = result[0]

        return bcrypt.checkpw(
            password.encode("utf-8"),
            stored_hash.encode("ascii")
        )

    except (ValueError, TypeError, sql.Error):
        return False

    finally:
        conn.close()


# ============================================================
# 7. COMMUNITY CHAT DATABASE
# ============================================================

def save_message(username, message):

    conn = get_community_db()

    try:
        conn.execute("""
            INSERT INTO messages (username, message)
            VALUES (?, ?)
        """, (username, message))

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


# ============================================================
# 8. YF AI DATABASE
# ============================================================

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


# ============================================================
# 9. SESSION STATE
# ============================================================

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "username" not in st.session_state:
    st.session_state.username = ""


# ============================================================
# 10. AUTHENTICATION INTERFACE
# ============================================================

def authentication_page():

    st.markdown("""
    <div class="hero">
        <h1>🌐 YF COMMUNITY</h1>
        <p>Connect. Code. Create. Build the future together.</p>
    </div>
    """, unsafe_allow_html=True)

    left, right = st.columns([1.1, 1], gap="large")

    with left:

        if YF_LOGO:
            st.image(YF_LOGO, width=230)

        st.markdown("""
        <div class="glass-card">
            <div class="feature-title">Welcome to YF.</div>
            <p class="muted">
                Your community for programming, robotics,
                technology, creativity and AI.
            </p>
            <hr>
            <p>💻 Programming discussions</p>
            <p>🤖 Robotics projects</p>
            <p>🚀 Cool applications</p>
            <p>🧠 YF AI assistant</p>
            <p>🌍 Community conversations</p>
        </div>
        """, unsafe_allow_html=True)

    with right:

        st.markdown(
            '<div class="glass-card">',
            unsafe_allow_html=True
        )

        choice = st.radio(
            "YOUR ACCOUNT",
            ["Login", "Create Account"],
            horizontal=True,
            key="auth_choice"
        )

        if choice == "Login":

            st.subheader("Welcome back!")

            name = st.text_input(
                "Username",
                key="login_name"
            )

            password = st.text_input(
                "Password",
                type="password",
                key="login_password"
            )

            if st.button("Login to YF Community", use_container_width=True):

                if login(name, password):

                    st.session_state.logged_in = True
                    st.session_state.username = name.strip()

                    st.success("Login successful!")
                    st.rerun()

                else:
                    st.error("Incorrect username or password.")

        else:

            st.subheader("Join YF Community")

            name = st.text_input(
                "Choose a username",
                key="signup_name"
            )

            password = st.text_input(
                "Create a password",
                type="password",
                key="signup_password"
            )

            confirm = st.text_input(
                "Confirm password",
                type="password",
                key="signup_confirm"
            )

            st.caption(
                "12+ characters, uppercase, lowercase, "
                "number and symbol. Maximum 72 UTF-8 bytes."
            )

            if st.button("Create My Account", use_container_width=True):

                if password != confirm:
                    st.error("Passwords do not match.")

                else:

                    success, message = signup(name, password)

                    if success:

                        st.success(message)

                        st.session_state.logged_in = True
                        st.session_state.username = name.strip()

                        st.rerun()

                    else:
                        st.error(message)

        st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# 11. COMMUNITY CHAT
# ============================================================

def community_chat():

    st.markdown("### 💬 YF Community Chat")

    st.caption("Share coding ideas, robotics projects and discoveries.")

    @st.fragment(run_every="2s")
    def chat_fragment():

        messages = get_messages()

        if not messages:
            st.info("No messages yet. Start the conversation!")

        for username, message, created_at in messages:

            is_me = (
                username.casefold()
                == st.session_state.username.casefold()
            )

            with st.chat_message(
                "user" if is_me else "assistant"
            ):

                st.caption(
                    f"{'You' if is_me else username} · {created_at}"
                )

                st.write(message)

        new_message = st.chat_input(
            "Message YF Community...",
            key="community_input"
        )

        if new_message and new_message.strip():

            save_message(
                st.session_state.username,
                new_message.strip()
            )

            st.rerun()

    chat_fragment()


# ============================================================
# 12. YF AI
# ============================================================

def yf_ai():

    st.markdown("### 🧠 YF AI")

    st.caption("Your intelligent assistant inside YF Community.")

    api_key = st.text_input(
        "Google Gemini API Key",
        type="password",
        key="yf_ai_api_key"
    )

    st.divider()

    username = st.session_state.username
    history = get_ai_history(username)

    for role, message, created_at in history:

        with st.chat_message(
            "user" if role == "user" else "assistant"
        ):

            st.caption(
                f"{'You' if role == 'user' else 'YF AI'} · {created_at}"
            )

            st.write(message)

    prompt = st.chat_input(
        "Ask YF AI anything...",
        key="yf_ai_input"
    )

    if prompt and prompt.strip():

        if not api_key:
            st.error("Please enter your Gemini API key.")

        else:

            instructions = f"""
You are YF AI, the official assistant of YF Community.

Your name is YF AI.
You are assisting: {username}.

Your responsibilities:
1. Help with Python and programming.
2. Help with robotics and electronics.
3. Explain science and mathematics.
4. Help users develop applications.
5. Give complete runnable code when appropriate.
6. Be friendly, accurate and respectful.
7. Never invent information.
8. Never claim to perform actions you did not perform.
9. Maintain the supplied conversation context.
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

            try:

                with st.spinner("YF AI is thinking..."):

                    client = genai.Client(api_key=api_key)

                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
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

            except Exception as error:

                st.error("YF AI generation failed.")

                st.exception(error)


# ============================================================
# 13. MAIN COMMUNITY DASHBOARD
# ============================================================

def dashboard():

    with st.sidebar:

        if YF_LOGO:
            st.image(YF_LOGO, width=120)

        st.markdown("## YF Community")

        st.divider()

        st.markdown("### 👤 Account")

        st.success(
            f"Logged in as {st.session_state.username}"
        )

        st.caption("YF Community Member")

        if st.button("Logout", use_container_width=True):

            st.session_state.logged_in = False
            st.session_state.username = ""

            st.rerun()

        st.divider()

        st.caption("YF ECOSYSTEM")
        st.caption("Connect • Create • Innovate")


    st.markdown("""
    <div class="hero">
        <h1>Welcome to YF.</h1>
        <p>Your space to code, chat, learn and innovate.</p>
    </div>
    """, unsafe_allow_html=True)

    chat_tab, ai_tab = st.tabs([
        "💬 Community Chat",
        "🧠 YF AI"
    ])

    with chat_tab:
        community_chat()

    with ai_tab:
        yf_ai()


# ============================================================
# 14. APPLICATION ENTRY POINT
# ============================================================

if st.session_state.logged_in:
    dashboard()
else:
    authentication_page()
