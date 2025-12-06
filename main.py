from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import psycopg2  # 替换 pymysql
from psycopg2 import pool  # 连接池支持
from psycopg2.extras import DictCursor  # 字典游标
import hashlib
import os
import sys
from datetime import datetime
from order_bp import order_bp
from exeitem_bp import exeitem_bp
import ssl
import urllib.parse

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

# ==================== PostgreSQL 数据库配置 ====================
def get_db_config():
    """获取数据库配置，优先使用环境变量"""
    # 从环境变量获取完整的DATABASE_URL（Render自动提供）
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        # 确保URL格式正确（postgresql:// 而非 postgres://）
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        
        return database_url
    else:
        # 备用：使用单独的环境变量构建配置
        return {
            'host': os.environ.get('DB_HOST', 'localhost'),
            'user': os.environ.get('DB_USER', 'postgres'),
            'password': os.environ.get('DB_PASSWORD', ''),
            'database': os.environ.get('DB_NAME', 'plorder'),
            'port': os.environ.get('DB_PORT', '5432'),
            'sslmode': 'require'  # 对于云数据库必须
        }

# 创建数据库连接池（提高性能，避免频繁连接）
db_pool = None

def init_db_pool():
    """初始化数据库连接池"""
    global db_pool
    try:
        config = get_db_config()
        
        if isinstance(config, str):  # DATABASE_URL 格式
            print(f"使用DATABASE_URL连接: {config[:50]}...")  
            
            # 解析DATABASE_URL
            parsed_url = urllib.parse.urlparse(config)
            
            # 提取连接参数
            db_params = {
                'host': parsed_url.hostname,
                'database': parsed_url.path[1:],  
                'user': parsed_url.username,
                'password': parsed_url.password,
                'port': parsed_url.port or 5432,
            }
            
            # 对于云数据库，强制SSL
            if 'render.com' in db_params['host']:
                db_params['sslmode'] = 'require'
                
                # 创建SSL上下文，不验证证书（Render有时证书验证会失败）
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                db_params['sslrootcert'] = None
                
                # 对于psycopg2，使用不同的SSL处理方式
                # 使用连接字符串而不是参数
                conn_string = f"host={db_params['host']} dbname={db_params['database']} user={db_params['user']} password={db_params['password']} port={db_params['port']} sslmode=require"
                db_pool = psycopg2.pool.SimpleConnectionPool(
                    1,  # 最小连接数
                    10,  # 最大连接数
                    dsn=conn_string  # 使用连接字符串
                )
            else:
                # 本地数据库
                db_pool = psycopg2.pool.SimpleConnectionPool(
                    1,  # 最小连接数
                    10,  # 最大连接数
                    **db_params
                )
                
        else:  # 字典格式配置
            print("使用字典配置连接数据库...")
            # 对于云数据库，强制SSL
            if 'render.com' in config.get('host', ''):
                config['sslmode'] = 'require'
                
            db_pool = psycopg2.pool.SimpleConnectionPool(
                1,  # 最小连接数
                10,  # 最大连接数
                **config
            )
        
        print("数据库连接池创建成功")
        
    except Exception as e:
        print(f"连接池创建失败: {e}")
        db_pool = None
        # 尝试直接连接测试
        test_direct_connection()

def test_direct_connection():
    """测试直接连接"""
    try:
        config = get_db_config()
        if isinstance(config, str):
            print("测试直接连接...")
            conn = psycopg2.connect(config, sslmode='require')
            cursor = conn.cursor()
            cursor.execute('SELECT 1')
            result = cursor.fetchone()
            print(f"直接连接测试成功: {result}")
            cursor.close()
            conn.close()
        else:
            config['sslmode'] = 'require'
            conn = psycopg2.connect(**config)
            cursor = conn.cursor()
            cursor.execute('SELECT 1')
            result = cursor.fetchone()
            print(f"直接连接测试成功: {result}")
            cursor.close()
            conn.close()
    except Exception as e:
        print(f"直接连接测试失败: {e}")

# 初始化连接池
init_db_pool()

def get_db_connection():
    """获取数据库连接（使用连接池或直接连接）"""
    try:
        if db_pool:
            conn = db_pool.getconn()
            # 设置搜索路径
            with conn.cursor() as cursor:
                cursor.execute('SET search_path TO public')
            return conn
        else:
            # 回退到普通连接
            config = get_db_config()
            if isinstance(config, str):
                # 对于DATABASE_URL，添加SSL模式
                if '?' in config:
                    conn_string = config + '&sslmode=require'
                else:
                    conn_string = config + '?sslmode=require'
                conn = psycopg2.connect(conn_string)
            else:
                config['sslmode'] = 'require'
                conn = psycopg2.connect(**config)
            
            with conn.cursor() as cursor:
                cursor.execute('SET search_path TO public')
            return conn
            
    except Exception as e:
        print(f"数据库连接失败: {e}")
        # 尝试重新初始化连接池
        if not db_pool:
            init_db_pool()
            if db_pool:
                return get_db_connection()
        raise

def close_db_connection(conn):
    """释放连接回连接池"""
    try:
        if db_pool and conn:
            db_pool.putconn(conn)
        elif conn:
            conn.close()
    except Exception as e:
        print(f"释放连接失败: {e}")
        try:
            conn.close()
        except:
            pass

# ==================== 用户模型 ====================
class User(UserMixin):
    def __init__(self, id, username, role):
        self.id = id
        self.username = username
        self.role = role

@login_manager.user_loader
def load_user(user_id):
    """加载用户"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        cursor.close()
        close_db_connection(conn)

        if user_data:
            return User(user_data['id'], user_data['username'], user_data['role'])
        return None
    except Exception as e:
        print(f"加载用户失败: {e}")
        return None

# ==================== 路由定义 ====================
@app.route('/')
def index():
    """首页 - 添加移动端检测"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    # 检查是否为移动设备
    user_agent = request.headers.get('User-Agent', '').lower()
    is_mobile = any(device in user_agent for device in ['mobile', 'android', 'iphone', 'ipad'])
    
    return render_template('login.html', is_mobile=is_mobile)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """登录页面"""
    if current_user.is_authenticated:
        flash('您已经登录了', 'info')
        return redirect(url_for('dashboard'))
    
    # 移动端检测
    user_agent = request.headers.get('User-Agent', '').lower()
    is_mobile = any(device in user_agent for device in ['mobile', 'android', 'iphone', 'ipad'])
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username:
            flash('请输入用户名', 'error')
            return render_template('login.html', is_mobile=is_mobile)
        
        if not password:
            flash('请输入密码', 'error')
            return render_template('login.html', is_mobile=is_mobile)
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=DictCursor)
            
        
            cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s", 
                          (username, password))
            user = cursor.fetchone()
            cursor.close()
            close_db_connection(conn)
            
            if user:
                user_obj = User(user['id'], user['username'], user['role'])
                login_user(user_obj)
                flash(f'欢迎回来，{username}！', 'success')
                
                next_page = request.args.get('next')
                if next_page:
                    return redirect(next_page)
                return redirect(url_for('dashboard'))
            else:
                flash('用户名或密码错误', 'error')
                return render_template('login.html', is_mobile=is_mobile)
                
        except Exception as e:
            print(f"登录过程出错: {e}")
            flash('系统错误，请稍后重试', 'error')
            return render_template('login.html', is_mobile=is_mobile)
    
    return render_template('login.html', is_mobile=is_mobile)

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
    """控制台页面 - 移动端适配"""
    # 移动端检测
    user_agent = request.headers.get('User-Agent', '').lower()
    is_mobile = any(device in user_agent for device in ['mobile', 'android', 'iphone', 'ipad'])
    
    return render_template('dashboard.html', now=datetime.now(), is_mobile=is_mobile)

# ==================== 移动端优化中间件 ====================
@app.before_request
def before_request():
    """在每个请求前执行，添加移动端标记"""
    if not hasattr(request, 'is_mobile'):
        user_agent = request.headers.get('User-Agent', '').lower()
        request.is_mobile = any(device in user_agent for device in ['mobile', 'android', 'iphone', 'ipad'])

@app.context_processor
def inject_variables():
    """向所有模板注入常用变量"""
    return {
        'now': datetime.now(),
        'is_mobile': getattr(request, 'is_mobile', False),
        'current_user': current_user
    }

# ==================== 错误处理 ====================
@app.errorhandler(404)
def not_found(error):
    return render_template('404.html', is_mobile=getattr(request, 'is_mobile', False)), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html', is_mobile=getattr(request, 'is_mobile', False)), 500

@app.errorhandler(403)
def forbidden(error):
    return render_template('403.html', is_mobile=getattr(request, 'is_mobile', False)), 403

@app.route('/about')
@login_required
def about():
    """关于系统页面"""
    return render_template('about.html', is_mobile=getattr(request, 'is_mobile', False))

@app.route('/health')
def health():
    """健康检查端点"""
    try:
        # 测试数据库连接
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT 1')
        result = cursor.fetchone()
        cursor.close()
        close_db_connection(conn)
        
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'timestamp': datetime.now().isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'database': 'disconnected',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

# ==================== 应用关闭时清理连接池 ====================
@app.teardown_appcontext
def close_connections(exception):
    """应用关闭时清理数据库连接"""
    try:
        if db_pool:
            db_pool.closeall()
    except Exception as e:
        print(f"关闭连接池失败: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
