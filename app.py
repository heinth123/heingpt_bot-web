import os
import requests
from flask import Flask, render_template_string, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "heingpt_super_secret_key_2026")

# ----------------- CONFIGURATION -----------------
GROQ_API_KEY = os.environ.get("GROQ_API_KEY") or "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"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-120b"

# Database Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL", "sqlite:///heingpt.db")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ----------------- DATABASE MODELS -----------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    display_name = db.Column(db.String(150), default="")
    password = db.Column(db.String(200), nullable=False)
    ai_memory = db.Column(db.Text, default="")
    chats = db.relationship('Chat', backref='user', lazy=True, cascade="all, delete-orphan")

class Chat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), default="New Chat")
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    messages = db.relationship('Message', backref='chat', lazy=True, cascade="all, delete-orphan")

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('chat.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False) # 'user' or 'assistant'
    content = db.Column(db.Text, nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()

# ----------------- AI FUNCTION -----------------
def ask_groq(history):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": history
    }
    try:
        response = requests.post(GROQ_API_URL, json=payload, headers=headers, timeout=20)
        data = response.json()
        if "choices" in data and len(data["choices"]) > 0:
            return data["choices"][0]["message"]["content"]
        return f"Groq Error: {data.get('error', {}).get('message', 'Unknown error')}"
    except Exception as e:
        return f"Connection Exception: {e}"

# ----------------- HTML TEMPLATES (Gemini Style UI + Settings Modal) -----------------
BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HeinGPT</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
</head>
<body class="bg-[#131314] text-[#e3e3e3] h-screen flex overflow-hidden font-sans">
    {% block content %}{% endblock %}
</body>
</html>
"""

AUTH_TEMPLATE = BASE_TEMPLATE.replace("{% block content %}{% endblock %}", """
    <div class="m-auto bg-[#1e1f20] p-8 rounded-2xl shadow-2xl w-96 border border-[#333537]">
        <div class="text-center mb-6">
            <h1 class="text-3xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">HeinGPT</h1>
            <p class="text-sm text-gray-400 mt-1">Your personal AI workspace</p>
        </div>
        {% with messages = get_flashed_messages() %}
            {% if messages %}
                <div class="bg-red-500/20 border border-red-500 text-red-300 p-3 rounded-lg mb-4 text-sm">{{ messages[0] }}</div>
            {% endif %}
        {% endwith %}
        <form method="POST" class="space-y-4">
            <div>
                <label class="block text-xs uppercase font-bold text-gray-400 mb-1">Username</label>
                <input type="text" name="username" required class="w-full bg-[#131314] border border-[#444] rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500">
            </div>
            <div>
                <label class="block text-xs uppercase font-bold text-gray-400 mb-1">Password</label>
                <input type="password" name="password" required class="w-full bg-[#131314] border border-[#444] rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500">
            </div>
            <button type="submit" class="w-full bg-blue-600 hover:bg-blue-500 text-white font-semibold py-2.5 rounded-lg transition">{{ title }}</button>
        </form>
        <p class="text-center text-sm text-gray-400 mt-4">
            {{ alt_text | safe }}
        </p>
    </div>
""")

CHAT_TEMPLATE = BASE_TEMPLATE.replace("{% block content %}{% endblock %}", """
    <!-- Sidebar -->
    <div id="sidebar" class="w-72 bg-[#1e1f20] flex flex-col border-r border-[#333537] transition-all duration-300">
        <div class="p-4 flex items-center justify-between">
            <a href="/new" class="flex items-center gap-3 bg-[#2d2e30] hover:bg-[#3c3d40] px-4 py-2.5 rounded-full text-sm font-medium transition w-full border border-[#444]">
                <i class="fa-solid fa-plus text-blue-400"></i> New Chat
            </a>
        </div>
        <div class="flex-1 overflow-y-auto px-3 space-y-1">
            <div class="text-xs font-semibold text-gray-400 px-3 py-2 uppercase">Recent Chats</div>
            {% for c in chats %}
                <a href="/chat/{{ c.id }}" class="flex items-center justify-between px-3 py-2.5 rounded-lg text-sm truncate hover:bg-[#2d2e30] transition group {{ 'bg-[#2d2e30] text-white font-medium' if active_chat and active_chat.id == c.id else 'text-gray-300' }}">
                    <span class="truncate pr-2"><i class="fa-regular fa-message mr-2 text-gray-400"></i>{{ c.title }}</span>
                    <form action="/delete/{{ c.id }}" method="POST" class="opacity-0 group-hover:opacity-100 transition">
                        <button type="submit" class="text-gray-400 hover:text-red-400 p-1"><i class="fa-solid fa-trash-can"></i></button>
                    </form>
                </a>
            {% endfor %}
        </div>
        
        <!-- User Profile & Settings / Logout bar -->
        <div class="p-4 border-t border-[#333537] flex items-center justify-between">
            <div class="flex items-center gap-3 truncate">
                <div class="w-9 h-9 rounded-full bg-blue-600 flex items-center justify-center font-bold text-white uppercase">
                    {{ current_user.display_name[0] if current_user.display_name else current_user.username[0] }}
                </div>
                <span class="text-sm font-medium truncate">{{ current_user.display_name if current_user.display_name else current_user.username }}</span>
            </div>
            <div class="flex items-center gap-1">
                <button onclick="openSettings()" class="text-gray-400 hover:text-white p-2 transition" title="Settings"><i class="fa-solid fa-gear"></i></button>
                <a href="/logout" class="text-gray-400 hover:text-red-400 p-2 transition" title="Log Out"><i class="fa-solid fa-arrow-right-from-bracket"></i></a>
            </div>
        </div>
    </div>

    <!-- Main Chat Area -->
    <div class="flex-1 flex flex-col bg-[#131314] relative">
        <div class="h-14 border-b border-[#333537] flex items-center px-6 justify-between bg-[#1e1f20]/50 backdrop-blur">
            <span class="font-semibold text-lg bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">HeinGPT ⚡</span>
            <span class="text-xs bg-blue-500/10 text-blue-400 px-3 py-1 rounded-full border border-blue-500/20 font-medium">Groq 120B</span>
        </div>

        <div id="chat-container" class="flex-1 overflow-y-auto p-6 space-y-6">
            {% if not active_chat or not active_chat.messages %}
                <div class="h-full flex flex-col items-center justify-center text-center max-w-md mx-auto">
                    <div class="w-16 h-16 rounded-2xl bg-gradient-to-tr from-blue-500 to-purple-600 flex items-center justify-center text-3xl mb-4 shadow-lg shadow-blue-500/20">⚡</div>
                    <h2 class="text-2xl font-bold text-white mb-2">Hello, {{ current_user.display_name if current_user.display_name else current_user.username }}!</h2>
                    <p class="text-gray-400 text-sm">How can I help you build, code, or explore today?</p>
                </div>
            {% else %}
                {% for msg in active_chat.messages %}
                    {% if msg.role == 'user' %}
                        <div class="flex justify-end">
                            <div class="bg-[#2d2e30] text-white px-5 py-3.5 rounded-2xl max-w-2xl text-sm leading-relaxed shadow-sm">{{ msg.content }}</div>
                        </div>
                    {% else %}
                        <div class="flex gap-4 max-w-3xl">
                            <div class="w-8 h-8 rounded-full bg-gradient-to-tr from-blue-500 to-purple-600 flex-shrink-0 flex items-center justify-center text-xs font-bold text-white">AI</div>
                            <div class="text-gray-200 text-sm leading-relaxed pt-1 whitespace-pre-wrap">{{ msg.content }}</div>
                        </div>
                    {% endif %}
                {% endfor %}
            {% endif %}
        </div>

        <!-- Input Box -->
        <div class="p-4 bg-[#131314]">
            <div class="max-w-3xl mx-auto">
                <form id="chat-form" class="bg-[#1e1f20] border border-[#333537] rounded-2xl p-3 flex items-center gap-3 shadow-lg focus-within:border-blue-500 transition">
                    <input type="text" id="user-input" placeholder="Ask HeinGPT anything..." required class="flex-1 bg-transparent border-none text-white focus:outline-none px-2 text-sm">
                    <button type="submit" id="send-btn" class="w-9 h-9 rounded-xl bg-blue-600 hover:bg-blue-500 flex items-center justify-center text-white transition"><i class="fa-solid fa-arrow-up text-sm"></i></button>
                </form>
                <div class="text-center text-[11px] text-gray-500 mt-2">HeinGPT can make mistakes. Built with Groq AI.</div>
            </div>
        </div>
    </div>

    <!-- SETTINGS MODAL -->
    <div id="settings-modal" class="fixed inset-0 bg-black/70 backdrop-blur-sm hidden items-center justify-center z-50 p-4">
        <div class="bg-[#1e1f20] border border-[#333537] rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
            <div class="p-5 border-b border-[#333537] flex items-center justify-between">
                <h3 class="text-lg font-bold text-white flex items-center gap-2"><i class="fa-solid fa-gear text-blue-400"></i> Settings & Hz Hub</h3>
                <button onclick="closeSettings()" class="text-gray-400 hover:text-white p-1"><i class="fa-solid fa-xmark text-lg"></i></button>
            </div>
            
            <div class="p-6 overflow-y-auto space-y-6 flex-1">
                <form action="/update-settings" method="POST" class="space-y-4">
                    <div class="text-xs font-bold text-blue-400 uppercase tracking-wider">Account Preferences</div>
                    <div>
                        <label class="block text-xs font-medium text-gray-400 mb-1">Display Name</label>
                        <input type="text" name="display_name" value="{{ current_user.display_name }}" class="w-full bg-[#131314] border border-[#333537] rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-gray-400 mb-1">New Password (leave blank to keep current)</label>
                        <input type="password" name="new_password" placeholder="••••••••" class="w-full bg-[#131314] border border-[#333537] rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500">
                    </div>

                    <div class="pt-2 text-xs font-bold text-blue-400 uppercase tracking-wider">AI Memory</div>
                    <div>
                        <label class="block text-xs font-medium text-gray-400 mb-1">What should HeinGPT know about you?</label>
                        <textarea name="ai_memory" rows="3" placeholder="e.g. I am 12 years old, love coding, and building apps!" class="w-full bg-[#131314] border border-[#333537] rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500">{{ current_user.ai_memory }}</textarea>
                    </div>

                    <button type="submit" class="w-full bg-blue-600 hover:bg-blue-500 text-white font-semibold py-2 rounded-lg text-sm transition">Save Changes</button>
                </form>

                <!-- MORE FROM HZ SECTION -->
                <div class="pt-4 border-t border-[#333537]">
                    <div class="text-xs font-bold text-purple-400 uppercase tracking-wider mb-3">More from Hz Network</div>
                    <div class="space-y-2">
                        <a href="https://minecraft-portal.onrender.com/" target="_blank" class="flex items-center justify-between p-3 rounded-xl bg-[#131314] hover:bg-[#252628] border border-[#333537] transition group">
                            <div class="flex items-center gap-3">
                                <span class="text-2xl">⛏️</span>
                                <div>
                                    <div class="text-sm font-semibold text-white group-hover:text-blue-400 transition">Minecraft Community</div>
                                    <div class="text-xs text-gray-400">Explore servers, builds, and chat with players</div>
                                </div>
                            </div>
                            <i class="fa-solid fa-arrow-up-right-from-square text-gray-500 text-xs"></i>
                        </a>
                        <!-- Future Hz apps can be added here easily! -->
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const chatContainer = document.getElementById('chat-container');
        chatContainer.scrollTop = chatContainer.scrollHeight;
        const chatId = "{{ active_chat.id if active_chat else '' }}";

        function openSettings() {
            document.getElementById('settings-modal').classList.remove('hidden');
            document.getElementById('settings-modal').classList.add('flex');
        }

        function closeSettings() {
            document.getElementById('settings-modal').classList.remove('flex');
            document.getElementById('settings-modal').classList.add('hidden');
        }

        document.getElementById('chat-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const inputField = document.getElementById('user-input');
            const message = inputField.value.trim();
            if (!message) return;
            inputField.value = '';

            chatContainer.innerHTML += `
                <div class="flex justify-end">
                    <div class="bg-[#2d2e30] text-white px-5 py-3.5 rounded-2xl max-w-2xl text-sm leading-relaxed shadow-sm">${message}</div>
                </div>
            `;
            chatContainer.scrollTop = chatContainer.scrollHeight;

            try {
                const res = await fetch('/send', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ message, chat_id: chatId })
                });
                const data = await res.json();
                if (data.success) {
                    if (!chatId && data.new_chat_id) {
                        window.location.href = `/chat/${data.new_chat_id}`;
                        return;
                    }
                    chatContainer.innerHTML += `
                        <div class="flex gap-4 max-w-3xl mt-4">
                            <div class="w-8 h-8 rounded-full bg-gradient-to-tr from-blue-500 to-purple-600 flex-shrink-0 flex items-center justify-center text-xs font-bold text-white">AI</div>
                            <div class="text-gray-200 text-sm leading-relaxed pt-1 whitespace-pre-wrap">${data.reply}</div>
                        </div>
                    `;
                    chatContainer.scrollTop = chatContainer.scrollHeight;
                }
            } catch (err) {
                console.error(err);
            }
        });
    </script>
""")

# ----------------- ROUTES -----------------
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('new_chat'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            login_user(user)
            return redirect(url_for('new_chat'))
        flash('Invalid username or password!')
    return render_template_string(AUTH_TEMPLATE, title="Log In", alt_text='Don\'t have an account? <a href="/register" class="text-blue-400 hover:underline">Sign up</a>')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        if User.query.filter_by(username=username).first():
            flash('Username already exists!')
        else:
            hashed_pw = generate_password_hash(request.form['password'], method='pbkdf2:sha256')
            new_user = User(username=username, display_name=username, password=hashed_pw)
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)
            return redirect(url_for('new_chat'))
    return render_template_string(AUTH_TEMPLATE, title="Sign Up", alt_text='Already have an account? <a href="/login" class="text-blue-400 hover:underline">Log in</a>')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/update-settings', methods=['POST'])
@login_required
def update_settings():
    display_name = request.form.get('display_name')
    new_password = request.form.get('new_password')
    ai_memory = request.form.get('ai_memory')

    if display_name:
        current_user.display_name = display_name
    if ai_memory is not None:
        current_user.ai_memory = ai_memory
    if new_password:
        current_user.password = generate_password_hash(new_password, method='pbkdf2:sha256')

    db.session.commit()
    flash('Settings updated successfully!')
    return redirect(request.referrer or url_for('new_chat'))

@app.route('/new')
@login_required
def new_chat():
    chats = Chat.query.filter_by(user_id=current_user.id).order_by(Chat.id.desc()).all()
    return render_template_string(CHAT_TEMPLATE, chats=chats, active_chat=None)

@app.route('/chat/<int:chat_id>')
@login_required
def view_chat(chat_id):
    chats = Chat.query.filter_by(user_id=current_user.id).order_by(Chat.id.desc()).all()
    active_chat = Chat.query.get_or_404(chat_id)
    if active_chat.user_id != current_user.id:
        return redirect(url_for('new_chat'))
    return render_template_string(CHAT_TEMPLATE, chats=chats, active_chat=active_chat)

@app.route('/delete/<int:chat_id>', methods=['POST'])
@login_required
def delete_chat(chat_id):
    chat = Chat.query.get_or_404(chat_id)
    if chat.user_id == current_user.id:
        db.session.delete(chat)
        db.session.commit()
    return redirect(url_for('new_chat'))

@app.route('/send', methods=['POST'])
@login_required
def send_message():
    data = request.get_json()
    user_msg = data.get('message')
    chat_id = data.get('chat_id')

    if not user_msg:
        return jsonify({'success': False})

    if not chat_id:
        title = user_msg[:30] + "..." if len(user_msg) > 30 else user_msg
        chat = Chat(title=title, user_id=current_user.id)
        db.session.add(chat)
        db.session.commit()
        chat_id = chat.id
    else:
        chat = Chat.query.get_or_404(chat_id)
        if chat.user_id != current_user.id:
            return jsonify({'success': False})

    db.session.add(Message(chat_id=chat.id, role='user', content=user_msg))
    db.session.commit()

    # Build history with AI Memory injection
    system_prompt = f"You are HeinGPT, a friendly, intelligent AI assistant built by Hudson. Use emojis and be engaging!"
    if current_user.ai_memory:
        system_prompt += f"\n\nHere is what you know about the user (User Memory):\n{current_user.ai_memory}"

    history = [{"role": "system", "content": system_prompt}]
    for m in chat.messages:
        history.append({"role": m.role, "content": m.content})

    ai_reply = ask_groq(history)

    db.session.add(Message(chat_id=chat.id, role='assistant', content=ai_reply))
    db.session.commit()

    return jsonify({'success': True, 'reply': ai_reply, 'new_chat_id': chat.id})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
