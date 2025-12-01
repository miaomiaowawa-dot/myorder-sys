from flask import Blueprint, render_template, request, jsonify,current_app
import pymysql
from datetime import datetime
from flask_login import current_user

# 创建订单管理蓝图
order_bp = Blueprint('orders', __name__, url_prefix='/orders')  

# 数据库配置
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '1234',
    'database': 'plorder',
    'charset': 'utf8mb4'
}

def get_db_connection():
    """获取数据库连接"""
    return pymysql.connect(**db_config)

@order_bp.route('/all')
def list_all():
    """显示全部订单页面"""
    return render_template('orders/all_orders.html')

@order_bp.route('/pending')
def list_pending():
    """显示待使用订单页面"""
    return render_template('orders/pending_orders.html')

@order_bp.route('/started')
def list_started():
    """显示已开始订单页面"""
    return render_template('orders/started_orders.html')

@order_bp.route('/used')
def list_used():
    """显示已完结订单页面"""
    return render_template('orders/used_orders.html')


@order_bp.route('/cancel')
def list_cancel():
    """显示已完结订单页面"""
    return render_template('orders/cancel_orders.html')

@order_bp.route('/api/orders')
def get_orders_data():
    """获取订单数据的API接口"""
    try:
        # 获取查询参数
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 15, type=int)
        search = request.args.get('search', '')
        status_filter = request.args.get('status', '')
        
        # 计算分页
        offset = (page - 1) * limit
        
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        # 构建查询条件 - 使用列表安全构建
        where_conditions = []
        params = []
        
        # 搜索条件
        if search:
            where_conditions.append("""
                (order_id LIKE %s OR 
                 order_info LIKE %s OR 
                 order_remark LIKE %s)
            """)
            search_term = f"%{search}%"
            params.extend([search_term, search_term, search_term])
        
        # 状态过滤条件
        if status_filter:
            where_conditions.append("order_status = %s")
            params.append(status_filter)
        
        # 构建安全的 WHERE 子句
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)
        else:
            where_clause = ""
        
        print(f"WHERE子句: {where_clause}")  # 调试日志
        print(f"参数: {params}")  # 调试日志
        
        # 查询总数 - 使用参数化查询
        count_query = f"SELECT COUNT(*) as total FROM order_list {where_clause}"
        cursor.execute(count_query, params)
        total_result = cursor.fetchone()
        total = total_result['total'] if total_result else 0
        
        # 查询订单数据 - 使用参数化查询
        query = f"""
            SELECT 
                order_id,
                order_info,
                order_price,
                order_disprice,
                order_buytime,
                order_status,
                order_remark
            FROM order_list 
            {where_clause}
            ORDER BY order_id DESC 
            LIMIT %s OFFSET %s
        """
        
        # 添加分页参数
        query_params = params + [limit, offset]
        
        print(f"执行查询: {query}")  # 调试日志
        print(f"查询参数: {query_params}")  # 调试日志
        
        cursor.execute(query, query_params)
        orders = cursor.fetchall()
        
        print(f"查询到 {len(orders)} 条记录")  # 调试日志
        
        # 格式化数据
        for order in orders:
            if order['order_buytime']:
                order['order_buytime'] = order['order_buytime'].strftime('%Y-%m-%d %H:%M:%S')
            else:
                order['order_buytime'] = '-'
                
            # 处理空值
            order['order_id'] = order['order_id'] or '-'
            order['order_info'] = order['order_info'] or '-'
            order['order_remark'] = order['order_remark'] or '-'
            order['order_price'] = str(order['order_price']) if order['order_price'] is not None else '-'
            order['order_disprice'] = str(order['order_disprice']) if order['order_disprice'] is not None else '-'
            
            # 添加状态显示
            order['status_text'] = get_status_text(order['order_status'])
            order['status_color'] = get_status_color(order['order_status'])
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'code': 0,
            'msg': '成功',
            'count': total,
            'data': orders
        })
        
    except Exception as e:
        print(f"API错误: {str(e)}")
        import traceback
        print(f"详细错误: {traceback.format_exc()}")  # 打印完整堆栈跟踪
        
        return jsonify({
            'code': 1,
            'msg': f'获取数据失败: {str(e)}',
            'count': 0,
            'data': []
        })
def get_status_text(status):
    """获取状态显示文本"""
    status_map = {
        'pending': '待使用',
        'started': '已开始', 
        'used': '已完成',
        'cancel': '已取消'
    }
    return status_map.get(status, status)

def get_status_color(status):
    """获取状态颜色"""
    color_map = {
        'pending': 'orange',
        'started': 'blue',
        'used': 'green',
        'cancel': 'red'
    }
    return color_map.get(status, 'gray')

@order_bp.route('/api/order/<order_id>')
def get_order_detail(order_id):
    """获取单个订单详情"""  # 修复：正确的缩进
    try:
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        query = """
            SELECT 
                order_id,
                order_info,
                order_price,
                order_disprice,
                order_buytime,
                order_status,
                order_remark
            FROM order_list 
            WHERE order_id = %s
        """
        cursor.execute(query, (order_id,))
        order = cursor.fetchone()
        
        if order and order['order_buytime']:
            order['order_buytime'] = order['order_buytime'].strftime('%Y-%m-%d %H:%M:%S')
        
        conn.close()
        
        if order:
            return jsonify({
                'code': 0,
                'msg': '成功',
                'data': order
            })
        else:
            return jsonify({
                'code': 1,
                'msg': '订单不存在'
            })
            
    except Exception as e:
        return jsonify({
            'code': 1,
            'msg': f'获取订单详情失败: {str(e)}'
        })

@order_bp.route('/api/dashboard-stats')
def dashboard_stats():
    """获取仪表盘统计数据"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        # 1. 总订单数
        cursor.execute("SELECT COUNT(*) as total FROM order_list")
        total_orders = cursor.fetchone()['total']
        
        # 2. 总金额（所有订单的折扣金额）
        cursor.execute("SELECT COALESCE(SUM(order_disprice), 0) as total FROM order_list")
        total_amount = float(cursor.fetchone()['total'])
        
        # 3. 待使用订单数量
        cursor.execute("SELECT COUNT(*) as total FROM order_list WHERE order_status = 'pending'")
        pending_orders = cursor.fetchone()['total']
        
        # 4. 已消费金额 = used订单总金额 + started订单中已使用的项目金额
        # used订单总金额
        cursor.execute("SELECT COALESCE(SUM(order_disprice), 0) as total FROM order_list WHERE order_status = 'used'")
        used_amount = float(cursor.fetchone()['total'])
        
        # started订单中已使用的项目金额
        cursor.execute("""
            SELECT COALESCE(SUM(i.item_price), 0) as total 
            FROM order_list ol 
            JOIN item i ON ol.order_id = i.record_id 
            WHERE ol.order_status = 'started'
        """)
        started_consumed = float(cursor.fetchone()['total'])
        
        consumed_amount = used_amount + started_consumed
        
        # 5. 最近订单
        cursor.execute("""
            SELECT order_id, order_info, order_price, order_disprice, order_status, order_buytime
            FROM order_list 
            ORDER BY order_buytime DESC 
            LIMIT 5
        """)
        recent_orders = cursor.fetchall()
        
        # 处理最近订单数据
        processed_orders = []
        for order in recent_orders:
            status_color = {
                'pending': 'orange',
                'started': 'blue', 
                'used': 'green',
                'cancelled': 'gray'
            }.get(order['order_status'], 'gray')
            
            status_text = {
                'pending': '待使用',
                'started': '进行中',
                'used': '已完成', 
                'cancelled': '已取消'
            }.get(order['order_status'], '未知')
            
            processed_orders.append({
                'order_id': order['order_id'],
                'order_info': order['order_info'],
                'order_price': float(order['order_price']) if order['order_price'] else 0,
                'order_disprice': float(order['order_disprice']) if order['order_disprice'] else 0,
                'order_buytime': order['order_buytime'].strftime('%Y-%m-%d') if order['order_buytime'] else '-',
                'status_color': status_color,
                'status_text': status_text
            })
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'code': 0,
            'data': {
                'total_orders': total_orders,
                'total_amount': total_amount,
                'pending_orders': pending_orders,
                'consumed_amount': consumed_amount,
                'recent_orders': processed_orders
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"获取仪表盘数据失败: {str(e)}")
        return jsonify({
            'code': 1,
            'msg': f'获取数据失败: {str(e)}'
        })

@order_bp.route('/api/service-trend')
def service_trend():
    """获取服务趋势数据（一年12个月的服务数量）"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        # 获取当前年份
        current_year = datetime.now().year
        
        # 查询每个月服务数量
        query = """
            SELECT 
                MONTH(exetime) as month,
                COUNT(*) as count
            FROM item 
            WHERE YEAR(exetime) = %s
            GROUP BY MONTH(exetime)
            ORDER BY month
        """
        cursor.execute(query, (current_year,))
        monthly_data = cursor.fetchall()
        
        # 创建12个月的数据，没有数据的月份为0
        months = ['1月', '2月', '3月', '4月', '5月', '6月', 
                 '7月', '8月', '9月', '10月', '11月', '12月']
        counts = [0] * 12
        
        for data in monthly_data:
            month_index = data['month'] - 1  # 月份从1开始，数组从0开始
            if 0 <= month_index < 12:
                counts[month_index] = data['count']
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'code': 0,
            'data': {
                'months': months,
                'counts': counts
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"获取服务趋势失败: {str(e)}")
        return jsonify({
            'code': 1,
            'msg': f'获取服务趋势失败: {str(e)}'
        })

# 获取所有服务的API
@order_bp.route('/api/services')
def get_services():
    """获取所有服务项目"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        cursor.execute("SELECT service_id, `desc`, package, type, part FROM service ORDER BY `desc`")
        services = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'code': 0,
            'data': services
        })
        
    except Exception as e:
        current_app.logger.error(f"获取服务列表失败: {str(e)}")
        return jsonify({
            'code': 1,
            'msg': f'获取服务列表失败: {str(e)}'
        })

# 添加订单的API
@order_bp.route('/api/add', methods=['POST'])
def add_order():
    """添加新订单"""
    try:
        data = request.get_json()
        
        # 验证必要字段
        required_fields = ['order_info', 'order_price', 'order_disprice', 'order_status']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'code': 1, 'msg': f'缺少必要字段: {field}'})
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 插入订单基本信息
        order_query = """
            INSERT INTO order_list (order_info, order_price, order_disprice, order_status, order_remark, order_buytime)
            VALUES (%s, %s, %s, %s, %s, NOW())
        """
        cursor.execute(order_query, (
            data['order_info'],
            float(data['order_price']),
            float(data['order_disprice']),
            data['order_status'],
            data.get('order_remark', '')
        ))
        
        order_id = cursor.lastrowid
        
        # 插入关联的服务项目
        if data.get('services'):
            service_query = """
                INSERT INTO order_service (order_id, service_id, quantity, service_status)
                VALUES (%s, %s, %s, 'pending')
            """
            for service in data['services']:
                cursor.execute(service_query, (
                    order_id,
                    service['service_id'],
                    service.get('quantity', 1)
                ))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            'code': 0,
            'msg': '订单添加成功',
            'data': {'order_id': order_id}
        })
        
    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
        current_app.logger.error(f"添加订单失败: {str(e)}")
        return jsonify({
            'code': 1,
            'msg': f'添加订单失败: {str(e)}'
        })

# 添加订单页面路由
@order_bp.route('/add')
def add_order_page():
    """添加订单页面"""
    return render_template('orders/add_order.html')