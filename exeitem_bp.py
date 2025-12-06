from flask import Blueprint, render_template, request, jsonify, current_app
from datetime import datetime
from flask_login import current_user
import psycopg2
from psycopg2.extras import DictCursor

# 创建项目执行蓝图
exeitem_bp = Blueprint('exeitem_bp', __name__, url_prefix='/item')

def get_db_connection():
    """获取数据库连接 - 使用主应用的连接池"""
    from main import DatabasePool
    return DatabasePool.get_connection()

def close_db_connection(conn):
    """关闭数据库连接"""
    from main import DatabasePool
    DatabasePool.return_connection(conn)

@exeitem_bp.route('/all')
def exeitem_all():
    """显示所有执行项目页面"""
    return render_template('item/exeitems.html')

@exeitem_bp.route('/api/items')
def get_all_items():
    """获取所有执行项目"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)

        query = """
            SELECT exetime, item_name, item_price, item_remark 
            FROM item
            ORDER BY exetime DESC
        """

        cursor.execute(query)
        items = cursor.fetchall()

        # 按日期分组并计算总价
        grouped_items = {}

        for item in items:
            # PostgreSQL 的日期时间处理
            if item['exetime']:
                if isinstance(item['exetime'], datetime):
                    date_str = item['exetime'].strftime('%Y-%m-%d')
                else:
                    date_str = str(item['exetime'])[:10]  # 取前10个字符作为日期
            else:
                date_str = '未知日期'

            if date_str not in grouped_items:
                grouped_items[date_str] = {
                    'items': [],
                    'total_price': 0
                }
            
            # 添加当前item到分组
            item_price = float(item['item_price']) if item['item_price'] is not None else 0
            grouped_items[date_str]['items'].append({
                'item_name': item['item_name'] or '未命名',
                'item_price': item_price,
                'item_remark': item['item_remark'] or ''
            })

            # 累加总价
            grouped_items[date_str]['total_price'] += item_price

        # 转换为前端易处理的列表格式
        result = [
            {
                'date': date,
                'items': group['items'],
                'total_price': round(group['total_price'], 2)  # 保留两位小数
            }
            for date, group in grouped_items.items()
        ]
        
        cursor.close()
        close_db_connection(conn)

        return jsonify({
            'code': 0,
            'data': result
        })

    except Exception as e:
        current_app.logger.error(f"获取数据失败: {str(e)}")
        return jsonify({
            'code': 1,
            'msg': f'获取数据失败: {str(e)}'
        })

@exeitem_bp.route('/api/started_items')
def get_started_items():
    """获取所有started状态的订单进度"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # 首先获取所有started状态的订单
        order_query = """
            SELECT order_id, order_info, order_price, order_disprice
            FROM order_list 
            WHERE order_status = 'started'
            ORDER BY order_id
        """
        cursor.execute(order_query)
        started_orders = cursor.fetchall()

        result = []
        
        for order in started_orders:
            order_id = order['order_id']
            
            # 获取这个订单对应的所有item（已执行的）
            item_query = """
                SELECT item_id, item_name, item_price, item_remark, exetime
                FROM item 
                WHERE record_id = %s
                ORDER BY exetime DESC
            """
            cursor.execute(item_query, (order_id,))
            order_items = cursor.fetchall()
            
            # 计算已使用金额和项目数量（处理None值）
            used_amount = 0
            for item in order_items:
                if item['item_price'] is not None:
                    used_amount += float(item['item_price'])
            used_count = len(order_items)
            
            # 处理订单价格中的None值
            order_price = float(order['order_price']) if order['order_price'] is not None else 0
            order_disprice = float(order['order_disprice']) if order['order_disprice'] is not None else 0
            
            # 根据订单折扣价和已使用金额计算剩余金额
            remaining_amount = order_disprice - used_amount
            remaining_amount = max(remaining_amount, 0)  # 确保不为负数
            
            # 估算剩余项目数量（基于平均价格）
            if used_count > 0 and used_amount > 0:
                avg_price = used_amount / used_count
                estimated_remaining_count = round(remaining_amount / avg_price) if avg_price > 0 else 0
            else:
                estimated_remaining_count = 0
            
            # 计算完成进度百分比
            if order_disprice > 0:
                progress_percentage = round((used_amount / order_disprice) * 100, 1)
            else:
                progress_percentage = 0
            
            # 格式化最近项目
            recent_items = []
            for item in order_items[:12]:  # 显示最近12个项目
                recent_items.append({
                    'item_id': item['item_id'],
                    'item_name': item['item_name'] or '未命名',
                    'item_price': float(item['item_price']) if item['item_price'] is not None else 0,
                    'item_remark': item['item_remark'] or '',
                    'exetime': item['exetime'].strftime('%Y-%m-%d %H:%M') if item['exetime'] else '-'
                })
            
            result.append({
                'order_id': order_id,
                'order_info': order['order_info'] or '未命名订单',
                'order_price': order_price,
                'order_disprice': order_disprice,
                'used_amount': round(used_amount, 2),
                'used_count': used_count,
                'remaining_amount': round(remaining_amount, 2),
                'estimated_remaining_count': estimated_remaining_count,
                'progress_percentage': progress_percentage,
                'recent_items': recent_items
            })
        
        cursor.close()
        close_db_connection(conn)

        return jsonify({
            'code': 0,
            'data': result
        })

    except Exception as e:
        current_app.logger.error(f"获取进行中订单失败: {str(e)}")
        return jsonify({
            'code': 1,
            'msg': f'获取进行中订单失败: {str(e)}'
        })

@exeitem_bp.route('/progress')
def order_progress():
    """显示订单进度页面"""
    return render_template('item/started_items.html')

@exeitem_bp.route('/api/orders')
def get_orders():
    """获取所有订单"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        
        # 只查询pending或started状态的订单
        cursor.execute("""
            SELECT order_id, order_info, order_status 
            FROM order_list 
            WHERE order_status IN ('pending', 'started')
            ORDER BY order_status, order_id DESC
        """)
        orders = cursor.fetchall()
        
        cursor.close()
        close_db_connection(conn)
        
        return jsonify({
            'code': 0,
            'data': orders
        })
        
    except Exception as e:
        current_app.logger.error(f"获取订单列表失败: {str(e)}")
        return jsonify({
            'code': 1,
            'msg': f'获取订单列表失败: {str(e)}'
        })

@exeitem_bp.route('/api/order_services/<int:order_id>')
def get_order_services(order_id):
    """获取订单对应的服务项目"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        
        query = """
            SELECT 
                s.service_id,
                s."desc" as service_desc,
                s.package,
                s.type,
                s.part
            FROM order_service os
            JOIN service s ON os.service_id = s.service_id
            WHERE os.order_id = %s
        """
        cursor.execute(query, (order_id,))
        services = cursor.fetchall()
        
        cursor.close()
        close_db_connection(conn)
        
        return jsonify({
            'code': 0,
            'data': services
        })
        
    except Exception as e:
        current_app.logger.error(f"获取订单服务失败: {str(e)}")
        return jsonify({
            'code': 1,
            'msg': f'获取订单服务失败: {str(e)}'
        })

@exeitem_bp.route('/api/add', methods=['POST'])
def add_exeitem():
    """添加服务执行记录"""
    conn = None
    try:
        data = request.get_json()
        
        # 验证必要字段
        required_fields = ['record_id', 'service_id', 'item_name', 'item_price', 'exetime']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'code': 1, 'msg': f'缺少必要字段: {field}'})
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. 验证选择的service_id确实属于这个订单
        validate_query = """
            SELECT COUNT(*) as count 
            FROM order_service 
            WHERE order_id = %s AND service_id = %s
        """
        cursor.execute(validate_query, (int(data['record_id']), int(data['service_id'])))
        validation_result = cursor.fetchone()
        
        if validation_result['count'] == 0:
            return jsonify({
                'code': 1, 
                'msg': '选择的服务不属于该订单'
            })
        
        # 2. 获取服务详细信息，用于填充item记录
        service_query = """
            SELECT s."desc", s.package, s.type, s.part, s.service_remark
            FROM service s
            WHERE s.service_id = %s
        """
        cursor.execute(service_query, (int(data['service_id']),))
        service_info = cursor.fetchone()
        
        # 3. 如果用户没有填写item_name，使用服务描述作为默认值
        item_name = data['item_name']
        if not item_name and service_info:
            item_name = service_info['desc']
        
        # 4. 插入执行记录
        query = """
            INSERT INTO item (record_id, service_id, item_name, item_price, item_remark, exetime)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING item_id
        """
        cursor.execute(query, (
            int(data['record_id']),
            int(data['service_id']),
            item_name,
            float(data['item_price']),
            data.get('item_remark', ''),
            data['exetime']
        ))
        
        item_id = cursor.fetchone()[0]
        
        # 5. 更新order_service表中的完成数量
        update_service_query = """
            UPDATE order_service 
            SET completed_quantity = COALESCE(completed_quantity, 0) + 1
            WHERE order_id = %s AND service_id = %s
        """
        cursor.execute(update_service_query, (data['record_id'], data['service_id']))
        
        # 6. 检查并更新服务状态
        check_status_query = """
            UPDATE order_service 
            SET service_status = CASE 
                WHEN completed_quantity >= quantity THEN 'used'
                WHEN completed_quantity > 0 THEN 'started'
                ELSE 'pending'
            END
            WHERE order_id = %s AND service_id = %s
        """
        cursor.execute(check_status_query, (data['record_id'], data['service_id']))
        
        # 7. 更新订单状态
        update_order_status(conn, data['record_id'])
        
        conn.commit()
        cursor.close()
        
        return jsonify({
            'code': 0,
            'msg': '服务记录添加成功',
            'data': {'item_id': item_id}
        })
        
    except Exception as e:
        if conn:
            conn.rollback()
        current_app.logger.error(f"添加服务记录失败: {str(e)}")
        return jsonify({
            'code': 1,
            'msg': f'添加服务记录失败: {str(e)}'
        })
    finally:
        if conn:
            close_db_connection(conn)

def update_order_status(conn, order_id):
    """更新订单状态"""
    cursor = conn.cursor()
    
    try:
        # 1. 获取当前订单状态
        cursor.execute("SELECT order_status FROM order_list WHERE order_id = %s", (order_id,))
        current_order = cursor.fetchone()
        if not current_order:
            return
        current_status = current_order[0]
        
        # 2. 检查订单中所有服务的完成情况 - 使用 'used' 作为完成状态
        check_query = """
            SELECT 
                COUNT(*) as total_services,
                SUM(CASE WHEN service_status = 'used' THEN 1 ELSE 0 END) as used_services,
                SUM(CASE WHEN service_status = 'pending' THEN 1 ELSE 0 END) as pending_services,
                SUM(CASE WHEN service_status = 'started' THEN 1 ELSE 0 END) as started_services
            FROM order_service 
            WHERE order_id = %s
        """
        cursor.execute(check_query, (order_id,))
        result = cursor.fetchone()
        
        total_services = result[0] or 0
        used_services = result[1] or 0
        pending_services = result[2] or 0
        started_services = result[3] or 0
        
        # 3. 根据完成情况更新订单状态
        new_order_status = None
        
        if used_services == total_services:
            # 所有服务都完成 -> used
            new_order_status = 'used'
        elif used_services > 0 or started_services > 0:
            # 有服务完成或进行中 -> started
            new_order_status = 'started'
        elif pending_services == total_services:
            # 所有服务都未完成 -> pending
            new_order_status = 'pending'
        
        # 4. 更新订单状态
        if new_order_status and new_order_status != current_status:
            update_query = "UPDATE order_list SET order_status = %s WHERE order_id = %s"
            cursor.execute(update_query, (new_order_status, order_id))
            
            # 记录状态变更日志
            current_app.logger.info(f"订单 {order_id} 状态从 {current_status} 变更为 {new_order_status}")

    except Exception as e:
        current_app.logger.error(f"更新订单状态失败: {str(e)}")
        raise e
    finally:
        cursor.close()

@exeitem_bp.route('/add')
def add_exeitem_page():
    """添加服务记录页面"""
    return render_template('item/add_exeitem.html')

@exeitem_bp.route('/to_use_services')
def to_use_services():
    """显示所有待使用服务页面"""
    return render_template('item/to_use_services.html')

@exeitem_bp.route('/api/to_use_services')
def get_to_use_services():
    """获取所有待使用服务（pending和started订单）"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        
        # 查询pending和started状态的订单及其服务详情
        query = """
            SELECT 
                ol.order_id,
                ol.order_info,
                ol.order_status as order_status,
                ol.order_buytime,
                s.service_id,
                s."desc" as service_desc,
                s.package,
                s.type,
                s.part,
                os.service_status,
                os.quantity,
                os.completed_quantity,
                (os.quantity - COALESCE(os.completed_quantity, 0)) as remaining_quantity,
                (SELECT COUNT(*) FROM item i WHERE i.record_id = ol.order_id AND i.service_id = s.service_id) as used_count
            FROM order_list ol
            JOIN order_service os ON ol.order_id = os.order_id
            JOIN service s ON os.service_id = s.service_id
            WHERE ol.order_status IN ('pending', 'started')
            ORDER BY 
                ol.order_status DESC,
                ol.order_id,
                s.service_id
        """
        cursor.execute(query)
        results = cursor.fetchall()
        
        # 按订单分组处理数据
        orders = {}
        for item in results:
            order_id = item['order_id']
            if order_id not in orders:
                # 格式化日期
                order_buytime = item['order_buytime']
                if order_buytime:
                    if isinstance(order_buytime, datetime):
                        order_buytime_str = order_buytime.strftime('%Y-%m-%d %H:%M')
                    else:
                        order_buytime_str = str(order_buytime)[:19]
                else:
                    order_buytime_str = '-'
                
                orders[order_id] = {
                    'order_id': order_id,
                    'order_info': item['order_info'] or '未命名订单',
                    'order_status': item['order_status'],
                    'order_buytime': order_buytime_str,
                    'services': []
                }
            
            # 查询该服务下所有的item记录
            item_query = """
                SELECT item_id, item_name, item_price, exetime, item_remark
                FROM item 
                WHERE record_id = %s AND service_id = %s
                ORDER BY exetime DESC
            """
            cursor.execute(item_query, (order_id, item['service_id']))
            item_records = cursor.fetchall()
            
            # 格式化item记录
            formatted_item_records = []
            for item_record in item_records:
                exetime = item_record['exetime']
                if exetime:
                    if isinstance(exetime, datetime):
                        exetime_str = exetime.strftime('%Y-%m-%d %H:%M')
                    else:
                        exetime_str = str(exetime)[:19]
                else:
                    exetime_str = '-'
                
                formatted_item_records.append({
                    'item_id': item_record['item_id'],
                    'item_name': item_record['item_name'] or '未命名',
                    'item_price': float(item_record['item_price']) if item_record['item_price'] is not None else 0,
                    'exetime': exetime_str,
                    'item_remark': item_record['item_remark'] or ''
                })
            
            # 计算服务使用状态
            service_status = item['service_status'] or 'pending'
            used_count = item['used_count'] or 0
            total_quantity = item['quantity'] or 1
            completed_quantity = item['completed_quantity'] or 0
            remaining = item['remaining_quantity'] or total_quantity
            
            # 确定显示状态
            display_status = service_status
            if service_status == 'started' and used_count > 0:
                display_status = 'used'
            
            # 计算进度
            progress = 0
            if total_quantity > 0:
                progress = round((completed_quantity / total_quantity) * 100, 1)
            
            orders[order_id]['services'].append({
                'service_id': item['service_id'],
                'service_desc': item['service_desc'] or '未命名服务',
                'package': item['package'] or '',
                'type': item['type'] or '',
                'part': item['part'] or '',
                'service_status': service_status,
                'display_status': display_status,
                'quantity': total_quantity,
                'completed_quantity': completed_quantity,
                'remaining_quantity': remaining,
                'used_count': used_count,
                'item_records': formatted_item_records,
                'progress': progress
            })
        
        # 转换为列表
        orders_list = list(orders.values())
        
        cursor.close()
        close_db_connection(conn)
        
        return jsonify({
            'code': 0,
            'data': orders_list
        })
        
    except Exception as e:
        current_app.logger.error(f"获取待使用服务失败: {str(e)}")
        return jsonify({
            'code': 1,
            'msg': f'获取待使用服务失败: {str(e)}'
        })
