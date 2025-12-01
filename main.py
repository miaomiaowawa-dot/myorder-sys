from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import pymysql
import hashlib
import os
import sys
from datetime import datetime
from order_bp import order_bp
from exeitem_bp import exeitem_bp


app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or 'dev-secret-key-123'
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-123')

# 注册蓝图
app.register_blueprint(order_bp)
app.register_blueprint(exeitem_bp)

# Flask-Login 配置
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = '请先登录'
login_manager.login_message_category = 'warning'

# 数据库配置
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '1234',
    'database': 'plorder',
    'charset': 'utf8mb4'
}
def get_db_config():
    return {
        'host': os.environ.get('DB_HOST', 'localhost'),
        'user': os.environ.get('DB_USER', 'root'),
        'password': os.environ.get('DB_PASSWORD', '1234'),
        'database': os.environ.get('DB_NAME', 'plorder'),
        'charset': 'utf8mb4'
    }

def get_db_connection():
    return pymysql.connect(**get_db_config())
class User(UserMixin):
    def __init__(self, id, username, role):
        self.id = id
        self.username = username
        self.role = role

@login_manager.user_loader
def load_user(user_id):
    """加载用户"""
    try:
        conn = pymysql.connect(**db_config)
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        cursor.close()
        conn.close()

        if user_data:
            return User(user_data['id'], user_data['username'], user_data['role'])
        return None
    except Exception as e:
        print(f"加载用户失败: {e}")
        return None

def get_db_connection():
    """获取数据库连接"""
    try:
        return pymysql.connect(**db_config)
    except pymysql.Error as e:
        print(f"数据库连接失败: {e}")
        raise

@app.route('/')
def index():
    """首页"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """登录页面"""
    # 如果用户已经登录，直接跳转到首页
    if current_user.is_authenticated:
        flash('您已经登录了', 'info')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        # 输入验证
        if not username:
            flash('请输入用户名', 'error')
            return render_template('login.html')
        
        if not password:
            flash('请输入密码', 'error')
            return render_template('login.html')
        
        try:
            # 数据库验证
            conn = get_db_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s", 
                          (username, password))
            user = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if user:
                # 登录成功
                user_obj = User(user['id'], user['username'], user['role'])
                login_user(user_obj)
                flash(f'欢迎回来，{username}！', 'success')
                
                # 检查是否有重定向页面
                next_page = request.args.get('next')
                if next_page:
                    return redirect(next_page)
                return redirect(url_for('dashboard'))
            else:
                flash('用户名或密码错误', 'error')
                return render_template('login.html')
                
        except Exception as e:
            print(f"登录过程出错: {e}")
            flash('系统错误，请稍后重试', 'error')
            return render_template('login.html')
    
    # GET 请求 - 显示登录页面
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """退出登录"""
    logout_user()
    flash('您已成功退出登录', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    """控制台页面"""
    return render_template('dashboard.html',now=datetime.now())

# 错误处理
@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

@app.errorhandler(403)
def forbidden(error):
    return render_template('403.html'), 403

'''@app.context_processor
def utility_processor():
    """向所有模板注入常用变量"""
    def current_time():
        return datetime.now()
    
    return dict(now=current_time)'''

@app.route('/about')
@login_required
def about():
    """关于系统页面"""
    return render_template('about.html')

if __name__ == '__main__':
    #app.run(debug=True, host='0.0.0.0', port=5000)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)