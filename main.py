from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import psycopg2
from psycopg2 import pool
from psycopg2.extras import DictCursor
import os
import sys
from datetime import datetime
from order_bp import order_bp
from exeitem_bp import exeitem_bp
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

# ==================== 数据库连接池管理 ====================
class DatabasePool:
    """简化的数据库连接池管理器"""
    _pool = None
    
    @classmethod
    def init_pool(cls):
        """初始化连接池"""
        try:
            database_url = os.environ.get('DATABASE_URL')
            
            if not database_url:
                print("⚠️ DATABASE_URL not found, using local config")
                # 本地开发配置
                connection_string = "host=localhost dbname=plorder user=postgres password='' port=5432"
            else:
                # 修复URL格式
                if database_url.startswith('postgres://'):
                    database_url = database_url.replace('postgres://', 'postgresql://')
                
                # 确保有SSL参数
                if 'sslmode=' not in database_url:
                    if '?' in database_url:
                        database_url += '&sslmode=require'
                    else:
                        database_url += '?sslmode=require'
                
                connection_string = database_url
            
            print(f"🔄 Creating connection pool...")
            
            # 创建连接池 - 关键修复：使用dsn参数
            cls._pool = psycopg2.pool.SimpleConnectionPool(
                minconn=1,
                maxconn=10,
                dsn=connection_string  # 使用dsn参数传递连接字符串
            )
            
            # 测试连接
            conn = cls._pool.getconn()
            cursor = conn.cursor()
            cursor.execute('SELECT 1')
            cursor.fetchone()
            cursor.close()
            cls._pool.putconn(conn)
            
            print("✅ Database connection pool initialized successfully")
            
        except Exception as e:
            print(f"❌ Failed to initialize connection pool: {e}")
            cls._pool = None
    
    @classmethod
    def get_connection(cls):
        """获取数据库连接"""
        if cls._pool is None:
            cls.init_pool()
        
        if cls._pool is None:
            # 连接池初始化失败，尝试直接连接
            return cls._get_direct_connection()
        
        try:
            return cls._pool.getconn()
        except Exception as e:
            print(f"⚠️ Failed to get connection from pool: {e}")
            # 回退到直接连接
            return cls._get_direct_connection()
    
    @classmethod
    def return_connection(cls, conn):
        """归还连接"""
        if cls._pool and conn:
            try:
                cls._pool.putconn(conn)
            except Exception as e:
                print(f"⚠️ Failed to return connection to pool: {e}")
                try:
                    conn.close()
                except:
                    pass
        elif conn:
            try:
                conn.close()
            except:
                pass
    
    @classmethod
    def _get_direct_connection(cls):
        """直接连接数据库（备用方案）"""
        try:
            database_url = os.environ.get('DATABASE_URL')
            
            if database_url:
                # 修复URL格式
                if database_url.startswith('postgres://'):
                    database_url = database_url.replace('postgres://', 'postgresql://')
                
                if 'sslmode=' not in database_url:
                    if '?' in database_url:
                        database_url += '&sslmode=require'
                    else:
                        database_url += '?sslmode=require'
                
                conn = psycopg2.connect(database_url)
            else:
                # 本地开发
                conn = psycopg2.connect(
                    host='localhost',
                    database='plorder',
                    user='postgres',
                    password='',
                    port=5432
                )
            
            print("📡 Using direct database connection (fallback)")
            return conn
        except Exception as e:
            print(f"❌ Direct connection also failed: {e}")
            raise
    
    @classmethod
    def close_all(cls):
        """关闭所有连接"""
        if cls._pool:
            try:
                cls._pool.closeall()
                print("🔒 Connection pool closed")
            except Exception as e:
                print(f"⚠️ Error closing pool: {e}")

# 应用启动时初始化连接池
DatabasePool.init_pool()

# 简化连接获取函数
def get_db_connection():
    """获取数据库连接"""
    return DatabasePool.get_connection()

def close_db_connection(conn):
    """释放数据库连接"""
    DatabasePool.return_connection(conn)

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

# ==================== 辅助函数 ====================
def is_mobile_request():
    """检测是否为移动设备"""
    user_agent = request.headers.get('User-Agent', '').lower()
    mobile_keywords = ['mobile', 'android', 'iphone', 'ipad']
    return any(keyword in user_agent for keyword in mobile_keywords)

# ==================== 路由定义 ====================
@app.route('/')
def index():
    """首页"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('login.html', is_mobile=is_mobile_request())

@app.route('/login', methods=['GET', 'POST'])
def login():
    """登录页面"""
    if current_user.is_authenticated:
        flash('您已经登录了', 'info')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            flash('请输入用户名和密码', 'error')
            return render_template('login.html', is_mobile=is_mobile_request())
        
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
                return redirect(request.args.get('next') or url_for('dashboard'))
            else:
                flash('用户名或密码错误', 'error')
                
        except Exception as e:
            print(f"登录出错: {e}")
            flash('系统错误，请稍后重试', 'error')
    
    return render_template('login.html', is_mobile=is_mobile_request())

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
    return render_template('dashboard.html', now=datetime.now(), is_mobile=is_mobile_request())

@app.route('/about')
@login_required
def about():
    """关于系统页面"""
    return render_template('about.html', is_mobile=is_mobile_request())

@app.route('/health')
def health():
    """健康检查端点"""
    try:
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

# ==================== 错误处理 ====================
@app.errorhandler(404)
def not_found(error):
    return render_template('404.html', is_mobile=is_mobile_request()), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html', is_mobile=is_mobile_request()), 500

@app.errorhandler(403)
def forbidden(error):
    return render_template('403.html', is_mobile=is_mobile_request()), 403

# ==================== 上下文处理器 ====================
@app.context_processor
def inject_variables():
    """向所有模板注入常用变量"""
    return {
        'now': datetime.now(),
        'is_mobile': is_mobile_request(),
        'current_user': current_user
    }

# ==================== 应用关闭处理 ====================
import atexit

@atexit.register
def cleanup():
    """应用退出时清理连接池"""
    DatabasePool.close_all()

# Flask teardown 处理
@app.teardown_appcontext
def teardown_db(exception):
    """请求结束时自动关闭数据库连接"""
    # Flask 会自动处理请求上下文，这里主要做清理
    pass

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
