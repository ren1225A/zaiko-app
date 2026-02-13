from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'  # 本番環境では変更してください

DATABASE = 'zaiko2.db'

# データベース接続
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# ログイン必須デコレーター
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# 店主権限チェックデコレーター
def owner_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if session.get('role') != 'owner':
            flash('この操作は店主のみ可能です', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# ログイン画面
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        name = request.form['name']
        role = request.form['role']
        
        conn = get_db()
        user = conn.execute('SELECT * FROM USERS WHERE name = ? AND role = ?', (name, role)).fetchone()
        
        if user:
            session['user_id'] = user['user_id']
            session['name'] = user['name']
            session['role'] = user['role']
            flash(f'ようこそ、{name}さん！', 'success')
            return redirect(url_for('index'))
        else:
            # ユーザーが存在しない場合は新規作成
            cursor = conn.execute('INSERT INTO USERS (name, role) VALUES (?, ?)', (name, role))
            conn.commit()
            user_id = cursor.lastrowid
            
            session['user_id'] = user_id
            session['name'] = name
            session['role'] = role
            flash(f'新しいユーザー {name} を作成しました', 'success')
            return redirect(url_for('index'))
    
    return render_template('login.html')

# ログアウト
@app.route('/logout')
def logout():
    session.clear()
    flash('ログアウトしました', 'info')
    return redirect(url_for('login'))

# メイン画面（在庫一覧）
@app.route('/')
@login_required
def index():
    conn = get_db()
    
    # カテゴリー一覧を取得
    categories = conn.execute('SELECT * FROM CATEGORIES ORDER BY display_order, category_id').fetchall()
    
    # カテゴリーごとの品目を取得
    items_by_category = {}
    for category in categories:
        items = conn.execute('''
            SELECT i.*, s.name as supplier_name 
            FROM ITEMS i
            LEFT JOIN SUPPLIERS s ON i.supplier_id = s.supplier_id
            WHERE i.is_active = 1 AND i.category_id = ?
            ORDER BY i.display_order, i.item_id
        ''', (category['category_id'],)).fetchall()
        items_by_category[category['category_id']] = items
    
    # 通知チェック
    notifications = conn.execute('''
        SELECT n.*, i.name as item_name
        FROM NOTIFICATIONS n
        JOIN ITEMS i ON n.item_id = i.item_id
        WHERE n.is_resolved = 0
        ORDER BY n.triggered_at DESC
    ''').fetchall()
    
    conn.close()
    return render_template('index.html', categories=categories, items_by_category=items_by_category, notifications=notifications)

# 品目追加（店主のみ）
@app.route('/add_item', methods=['GET', 'POST'])
@owner_required
def add_item():
    if request.method == 'POST':
        name = request.form['name']
        unit = request.form['unit']
        min_threshold = float(request.form['min_threshold'])
        supplier_id = request.form.get('supplier_id')
        category_id = request.form.get('category_id')
        
        if not supplier_id:
            supplier_id = None
        
        if not category_id:
            category_id = None
        
        conn = get_db()
        conn.execute('''
            INSERT INTO ITEMS (name, unit, current_quantity, min_threshold, supplier_id, category_id, created_by)
            VALUES (?, ?, 0, ?, ?, ?, ?)
        ''', (name, unit, min_threshold, supplier_id, category_id, session['user_id']))
        conn.commit()
        conn.close()
        
        flash(f'品目「{name}」を追加しました', 'success')
        return redirect(url_for('index'))
    
    # 仕入先リスト取得
    conn = get_db()
    suppliers = conn.execute('SELECT * FROM SUPPLIERS ORDER BY name').fetchall()
    categories = conn.execute('SELECT * FROM CATEGORIES ORDER BY display_order, category_id').fetchall()
    conn.close()
    
    return render_template('add_item.html', suppliers=suppliers, categories=categories)

# 在庫増減
@app.route('/update_stock/<int:item_id>', methods=['POST'])
@login_required
def update_stock(item_id):
    quantity_delta = float(request.form['quantity_delta'])
    reason = request.form['reason']
    note = request.form.get('note', '')
    
    conn = get_db()
    
    # 在庫更新
    item = conn.execute('SELECT * FROM ITEMS WHERE item_id = ?', (item_id,)).fetchone()
    new_quantity = item['current_quantity'] + quantity_delta
    
    conn.execute('UPDATE ITEMS SET current_quantity = ?, updated_at = ? WHERE item_id = ?',
                 (new_quantity, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), item_id))
    
    # 取引記録
    conn.execute('''
        INSERT INTO STOCK_TRANSACTIONS (item_id, quantity_delta, reason, note, user_id)
        VALUES (?, ?, ?, ?, ?)
    ''', (item_id, quantity_delta, reason, note, session['user_id']))
    
    # 閾値チェック → 通知作成
    if new_quantity < item['min_threshold']:
        # 未解決の同じ品目の通知がなければ作成
        existing = conn.execute('''
            SELECT * FROM NOTIFICATIONS 
            WHERE item_id = ? AND is_resolved = 0
        ''', (item_id,)).fetchone()
        
        if not existing:
            conn.execute('''
                INSERT INTO NOTIFICATIONS (item_id, type, threshold_at_time, quantity_at_time)
                VALUES (?, 'low_stock', ?, ?)
            ''', (item_id, item['min_threshold'], new_quantity))
    
    conn.commit()
    conn.close()
    
    flash(f'在庫を更新しました（変化: {quantity_delta:+g} {item["unit"]}）', 'success')
    return redirect(url_for('index'))

# 通知解決
@app.route('/resolve_notification/<int:notification_id>')
@login_required
def resolve_notification(notification_id):
    conn = get_db()
    conn.execute('UPDATE NOTIFICATIONS SET is_resolved = 1 WHERE notification_id = ?', (notification_id,))
    conn.commit()
    conn.close()
    
    flash('通知を解決しました', 'info')
    return redirect(url_for('index'))

# 履歴表示
@app.route('/history')
@login_required
def history():
    conn = get_db()
    transactions = conn.execute('''
        SELECT st.*, i.name as item_name, i.unit, u.name as user_name
        FROM STOCK_TRANSACTIONS st
        JOIN ITEMS i ON st.item_id = i.item_id
        JOIN USERS u ON st.user_id = u.user_id
        ORDER BY st.created_at DESC
        LIMIT 100
    ''').fetchall()
    conn.close()
    
    return render_template('history.html', transactions=transactions)
# 品目削除（店主のみ・論理削除）
@app.route('/delete_item/<int:item_id>', methods=['POST'])
@owner_required
def delete_item(item_id):
    conn = get_db()
    
    # 品目名を取得（メッセージ用）
    item = conn.execute('SELECT name FROM ITEMS WHERE item_id = ?', (item_id,)).fetchone()
    
    if item:
        # 論理削除（is_active を 0 に設定）
        conn.execute('UPDATE ITEMS SET is_active = 0 WHERE item_id = ?', (item_id,))
        conn.commit()
        flash(f'品目「{item["name"]}」を削除しました', 'success')
    else:
        flash('品目が見つかりませんでした', 'error')
    
    conn.close()
    return redirect(url_for('index'))

# ゴミ箱（削除済み品目一覧・店主のみ）
@app.route('/trash')
@owner_required
def trash():
    conn = get_db()
    deleted_items = conn.execute('''
        SELECT i.*, s.name as supplier_name 
        FROM ITEMS i
        LEFT JOIN SUPPLIERS s ON i.supplier_id = s.supplier_id
        WHERE i.is_active = 0
        ORDER BY i.updated_at DESC
    ''').fetchall()
    conn.close()
    
    return render_template('trash.html', items=deleted_items)

# 品目復元（ゴミ箱から戻す・店主のみ）
@app.route('/restore_item/<int:item_id>', methods=['POST'])
@owner_required
def restore_item(item_id):
    conn = get_db()
    
    # 品目名を取得（メッセージ用）
    item = conn.execute('SELECT name FROM ITEMS WHERE item_id = ?', (item_id,)).fetchone()
    
    if item:
        # 復元（is_active を 1 に設定）
        conn.execute('UPDATE ITEMS SET is_active = 1, updated_at = ? WHERE item_id = ?',
                     (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), item_id))
        conn.commit()
        flash(f'品目「{item["name"]}」を復元しました', 'success')
    else:
        flash('品目が見つかりませんでした', 'error')
    
    conn.close()
    return redirect(url_for('trash'))

# 品目完全削除（ゴミ箱から完全に削除・店主のみ）
@app.route('/permanent_delete/<int:item_id>', methods=['POST'])
@owner_required
def permanent_delete(item_id):
    conn = get_db()
    
    # 品目名を取得（メッセージ用）
    item = conn.execute('SELECT name FROM ITEMS WHERE item_id = ?', (item_id,)).fetchone()
    
    if item:
        # 完全削除（物理削除）
        conn.execute('DELETE FROM ITEMS WHERE item_id = ?', (item_id,))
        conn.commit()
        flash(f'品目「{item["name"]}」を完全に削除しました', 'info')
    else:
        flash('品目が見つかりませんでした', 'error')
    
    conn.close()
    return redirect(url_for('trash'))
# 統計・レポート
@app.route('/statistics')
@login_required
def statistics():
    conn = get_db()
    
    # パラメータ取得（月選択・期間選択）
    selected_period = request.args.get('period', 'current_month')  # current_month, 3months, 6months, 9months, 1year
    selected_month = request.args.get('month', '')  # 2026-02 形式
    
    # 期間の計算
    if selected_period == 'current_month':
        start_date = "date('now', 'start of month')"
        period_label = "今月"
    elif selected_period == '3months':
        start_date = "date('now', '-3 months')"
        period_label = "過去3ヶ月"
    elif selected_period == '6months':
        start_date = "date('now', '-6 months')"
        period_label = "過去6ヶ月"
    elif selected_period == '9months':
        start_date = "date('now', '-9 months')"
        period_label = "過去9ヶ月"
    elif selected_period == '1year':
        start_date = "date('now', '-1 year')"
        period_label = "過去1年"
    elif selected_month:
        # 特定の月が選択された場合
        start_date = f"date('{selected_month}-01')"
        period_label = selected_month.replace('-', '年') + '月'
    else:
        start_date = "date('now', 'start of month')"
        period_label = "今月"
    
    # 利用可能な月のリスト取得（過去12ヶ月）
    available_months = conn.execute('''
        SELECT DISTINCT strftime('%Y-%m', created_at) as month
        FROM STOCK_TRANSACTIONS
        WHERE created_at >= date('now', '-12 months')
        ORDER BY month DESC
    ''').fetchall()
    
    # 1. 月別使用量（過去6ヶ月）
    monthly_usage = conn.execute('''
        SELECT 
            strftime('%Y-%m', st.created_at) as month,
            i.name as item_name,
            SUM(CASE WHEN st.quantity_delta < 0 THEN ABS(st.quantity_delta) ELSE 0 END) as usage
        FROM STOCK_TRANSACTIONS st
        JOIN ITEMS i ON st.item_id = i.item_id
        WHERE st.created_at >= date('now', '-6 months')
        AND st.reason IN ('使用', '廃棄')
        GROUP BY month, i.name
        ORDER BY month DESC
    ''').fetchall()
    
    # 2. カテゴリー別在庫割合
    category_stock = conn.execute('''
        SELECT 
            c.name as category_name,
            COUNT(i.item_id) as item_count,
            SUM(i.current_quantity) as total_quantity
        FROM CATEGORIES c
        LEFT JOIN ITEMS i ON c.category_id = i.category_id AND i.is_active = 1
        GROUP BY c.category_id, c.name
        ORDER BY item_count DESC
    ''').fetchall()
    
    # 3. よく使う品目ランキング（選択期間）
    if selected_month:
        # 特定の月
        top_items_query = f'''
            SELECT 
                i.name as item_name,
                i.unit,
                SUM(CASE WHEN st.quantity_delta < 0 THEN ABS(st.quantity_delta) ELSE 0 END) as total_usage,
                COUNT(*) as transaction_count
            FROM STOCK_TRANSACTIONS st
            JOIN ITEMS i ON st.item_id = i.item_id
            WHERE strftime('%Y-%m', st.created_at) = '{selected_month}'
            AND st.reason IN ('使用', '廃棄')
            GROUP BY i.item_id, i.name, i.unit
            ORDER BY total_usage DESC
            LIMIT 10
        '''
    else:
        top_items_query = f'''
            SELECT 
                i.name as item_name,
                i.unit,
                SUM(CASE WHEN st.quantity_delta < 0 THEN ABS(st.quantity_delta) ELSE 0 END) as total_usage,
                COUNT(*) as transaction_count
            FROM STOCK_TRANSACTIONS st
            JOIN ITEMS i ON st.item_id = i.item_id
            WHERE st.created_at >= {start_date}
            AND st.reason IN ('使用', '廃棄')
            GROUP BY i.item_id, i.name, i.unit
            ORDER BY total_usage DESC
            LIMIT 10
        '''
    
    top_items = conn.execute(top_items_query).fetchall()
    
    # 3-2. 単位ごとの使用量ランキング
    units_ranking = {}
    all_units = conn.execute('SELECT DISTINCT unit FROM ITEMS WHERE is_active = 1 AND unit IS NOT NULL').fetchall()
    
    for unit_row in all_units:
        unit = unit_row['unit']
        
        if selected_month:
            items_query = f'''
                SELECT 
                    i.name as item_name,
                    i.unit,
                    SUM(CASE WHEN st.quantity_delta < 0 THEN ABS(st.quantity_delta) ELSE 0 END) as total_usage,
                    COUNT(*) as transaction_count
                FROM STOCK_TRANSACTIONS st
                JOIN ITEMS i ON st.item_id = i.item_id
                WHERE strftime('%Y-%m', st.created_at) = '{selected_month}'
                AND st.reason IN ('使用', '廃棄')
                AND i.unit = ?
                GROUP BY i.item_id, i.name, i.unit
                ORDER BY total_usage DESC
                LIMIT 5
            '''
        else:
            items_query = f'''
                SELECT 
                    i.name as item_name,
                    i.unit,
                    SUM(CASE WHEN st.quantity_delta < 0 THEN ABS(st.quantity_delta) ELSE 0 END) as total_usage,
                    COUNT(*) as transaction_count
                FROM STOCK_TRANSACTIONS st
                JOIN ITEMS i ON st.item_id = i.item_id
                WHERE st.created_at >= {start_date}
                AND st.reason IN ('使用', '廃棄')
                AND i.unit = ?
                GROUP BY i.item_id, i.name, i.unit
                ORDER BY total_usage DESC
                LIMIT 5
            '''
        
        items = conn.execute(items_query, (unit,)).fetchall()
        
        if items:
            units_ranking[unit] = items
    
    # 4. 在庫アラート（閾値120%以下）
    low_stock_items = conn.execute('''
        SELECT 
            i.name as item_name,
            i.current_quantity,
            i.min_threshold,
            i.unit,
            ROUND((i.current_quantity * 100.0 / i.min_threshold), 1) as percentage
        FROM ITEMS i
        WHERE i.is_active = 1 
        AND i.current_quantity <= (i.min_threshold * 1.2)
        ORDER BY percentage ASC
    ''').fetchall()
    
    # 5. 期間の統計サマリー
    if selected_month:
        summary_query = f'''
            SELECT 
                COUNT(DISTINCT CASE WHEN quantity_delta > 0 THEN item_id END) as items_received,
                COUNT(DISTINCT CASE WHEN quantity_delta < 0 THEN item_id END) as items_used,
                SUM(CASE WHEN quantity_delta > 0 THEN quantity_delta ELSE 0 END) as total_received,
                SUM(CASE WHEN quantity_delta < 0 THEN ABS(quantity_delta) ELSE 0 END) as total_used
            FROM STOCK_TRANSACTIONS
            WHERE strftime('%Y-%m', created_at) = '{selected_month}'
        '''
    else:
        summary_query = f'''
            SELECT 
                COUNT(DISTINCT CASE WHEN quantity_delta > 0 THEN item_id END) as items_received,
                COUNT(DISTINCT CASE WHEN quantity_delta < 0 THEN item_id END) as items_used,
                SUM(CASE WHEN quantity_delta > 0 THEN quantity_delta ELSE 0 END) as total_received,
                SUM(CASE WHEN quantity_delta < 0 THEN ABS(quantity_delta) ELSE 0 END) as total_used
            FROM STOCK_TRANSACTIONS
            WHERE created_at >= {start_date}
        '''
    
    monthly_summary = conn.execute(summary_query).fetchone()
    
    conn.close()
    
    return render_template('statistics.html', 
                         monthly_usage=monthly_usage,
                         category_stock=category_stock,
                         top_items=top_items,
                         units_ranking=units_ranking,
                         low_stock_items=low_stock_items,
                         monthly_summary=monthly_summary,
                         available_months=available_months,
                         selected_period=selected_period,
                         selected_month=selected_month,
                         period_label=period_label)
    
    # 1. 月別使用量（過去6ヶ月）
    monthly_usage = conn.execute('''
        SELECT 
            strftime('%Y-%m', st.created_at) as month,
            i.name as item_name,
            SUM(CASE WHEN st.quantity_delta < 0 THEN ABS(st.quantity_delta) ELSE 0 END) as usage
        FROM STOCK_TRANSACTIONS st
        JOIN ITEMS i ON st.item_id = i.item_id
        WHERE st.created_at >= date('now', '-6 months')
        AND st.reason IN ('使用', '廃棄')
        GROUP BY month, i.name
        ORDER BY month DESC
    ''').fetchall()
    
    # 2. カテゴリー別在庫割合
    category_stock = conn.execute('''
        SELECT 
            c.name as category_name,
            COUNT(i.item_id) as item_count,
            SUM(i.current_quantity) as total_quantity
        FROM CATEGORIES c
        LEFT JOIN ITEMS i ON c.category_id = i.category_id AND i.is_active = 1
        GROUP BY c.category_id, c.name
        ORDER BY item_count DESC
    ''').fetchall()
    
    # 3. よく使う品目ランキング（今月）
    top_items = conn.execute('''
        SELECT 
            i.name as item_name,
            i.unit,
            SUM(CASE WHEN st.quantity_delta < 0 THEN ABS(st.quantity_delta) ELSE 0 END) as total_usage,
            COUNT(*) as transaction_count
        FROM STOCK_TRANSACTIONS st
        JOIN ITEMS i ON st.item_id = i.item_id
        WHERE st.created_at >= date('now', 'start of month')
        AND st.reason IN ('使用', '廃棄')
        GROUP BY i.item_id, i.name, i.unit
        ORDER BY total_usage DESC
        LIMIT 10
    ''').fetchall()
    
    # 3-2. 単位ごとの使用量ランキング
    units_ranking = {}
    all_units = conn.execute('SELECT DISTINCT unit FROM ITEMS WHERE is_active = 1 AND unit IS NOT NULL').fetchall()
    
    for unit_row in all_units:
        unit = unit_row['unit']
        items = conn.execute('''
            SELECT 
                i.name as item_name,
                i.unit,
                SUM(CASE WHEN st.quantity_delta < 0 THEN ABS(st.quantity_delta) ELSE 0 END) as total_usage,
                COUNT(*) as transaction_count
            FROM STOCK_TRANSACTIONS st
            JOIN ITEMS i ON st.item_id = i.item_id
            WHERE st.created_at >= date('now', 'start of month')
            AND st.reason IN ('使用', '廃棄')
            AND i.unit = ?
            GROUP BY i.item_id, i.name, i.unit
            ORDER BY total_usage DESC
            LIMIT 5
        ''', (unit,)).fetchall()
        
        if items:
            units_ranking[unit] = items
    
    # 4. 在庫アラート（閾値80%以下）
    low_stock_items = conn.execute('''
        SELECT 
            i.name as item_name,
            i.current_quantity,
            i.min_threshold,
            i.unit,
            ROUND((i.current_quantity * 100.0 / i.min_threshold), 1) as percentage
        FROM ITEMS i
        WHERE i.is_active = 1 
        AND i.current_quantity <= (i.min_threshold * 1.2)
        ORDER BY percentage ASC
    ''').fetchall()
    
    # 5. 今月の統計サマリー
    monthly_summary = conn.execute('''
        SELECT 
            COUNT(DISTINCT CASE WHEN quantity_delta > 0 THEN item_id END) as items_received,
            COUNT(DISTINCT CASE WHEN quantity_delta < 0 THEN item_id END) as items_used,
            SUM(CASE WHEN quantity_delta > 0 THEN quantity_delta ELSE 0 END) as total_received,
            SUM(CASE WHEN quantity_delta < 0 THEN ABS(quantity_delta) ELSE 0 END) as total_used
        FROM STOCK_TRANSACTIONS
        WHERE created_at >= date('now', 'start of month')
    ''').fetchone()
    
    conn.close()
    
    return render_template('statistics.html', 
                         monthly_usage=monthly_usage,
                         category_stock=category_stock,
                         top_items=top_items,
                         units_ranking=units_ranking,
                         low_stock_items=low_stock_items,
                         monthly_summary=monthly_summary)
# カテゴリー管理（店主のみ）
@app.route('/categories')
@owner_required
def categories():
    conn = get_db()
    categories = conn.execute('SELECT * FROM CATEGORIES ORDER BY display_order, category_id').fetchall()
    conn.close()
    return render_template('categories.html', categories=categories)

# カテゴリー追加（店主のみ）
@app.route('/add_category', methods=['POST'])
@owner_required
def add_category():
    name = request.form['name']
    icon_filename = request.form.get('icon_filename', '')
    
    conn = get_db()
    conn.execute('INSERT INTO CATEGORIES (name, icon_path) VALUES (?, ?)', (name, icon_filename))
    conn.commit()
    conn.close()
    
    flash(f'カテゴリー「{name}」を追加しました', 'success')
    return redirect(url_for('categories'))

# カテゴリー削除（店主のみ・論理削除ではなく物理削除）
@app.route('/delete_category/<int:category_id>', methods=['POST'])
@owner_required
def delete_category(category_id):
    conn = get_db()
    
    # カテゴリーに紐づく品目があるかチェック
    items_count = conn.execute('SELECT COUNT(*) as count FROM ITEMS WHERE category_id = ? AND is_active = 1', 
                                (category_id,)).fetchone()
    
    if items_count['count'] > 0:
        flash('このカテゴリーには品目が登録されています。先に品目を削除または移動してください。', 'error')
    else:
        category = conn.execute('SELECT name FROM CATEGORIES WHERE category_id = ?', (category_id,)).fetchone()
        if category:
            conn.execute('DELETE FROM CATEGORIES WHERE category_id = ?', (category_id,))
            conn.commit()
            flash(f'カテゴリー「{category["name"]}」を削除しました', 'success')
    
    conn.close()
    return redirect(url_for('categories'))

# 品目のカテゴリー変更（店主のみ）
@app.route('/change_category/<int:item_id>', methods=['POST'])
@owner_required
def change_category(item_id):
    new_category_id = request.form['category_id']
    
    conn = get_db()
    item = conn.execute('SELECT name FROM ITEMS WHERE item_id = ?', (item_id,)).fetchone()
    category = conn.execute('SELECT name FROM CATEGORIES WHERE category_id = ?', (new_category_id,)).fetchone()
    
    if item and category:
        conn.execute('UPDATE ITEMS SET category_id = ? WHERE item_id = ?', (new_category_id, item_id))
        conn.commit()
        flash(f'「{item["name"]}」を「{category["name"]}」に移動しました', 'success')
    
    conn.close()
    return redirect(url_for('index'))
if __name__ == '__main__':
    app.run(debug=True)
    