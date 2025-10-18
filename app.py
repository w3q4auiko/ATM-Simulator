from unittest import result
from flask import Flask, render_template, request, redirect, url_for, session
import mysql.connector

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # 用于 session 数据加密，保障安全

# 数据库连接配置，存储 MySQL 数据库的连接信息
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'admin',
    'database': 'atm'
}

# 默认首页跳转到登录页
@app.route('/')
def index():
    return redirect(url_for('login'))

# 登录功能
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # 获取表单中输入的卡号和密码
        card_number = request.form.get('card_number')
        pin = request.form.get('pin')

        # 连接数据库验证用户
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE card_number=%s AND pin=%s", (card_number, pin))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user:
            # 登录成功后保存会话信息，session 存储当前用户的卡号和姓名
            session['card_number'] = user['card_number']
            session['user_name'] = user['user_name']
            return redirect(url_for('menu'))
        else:
            # 登录失败提示错误信息
            return render_template('login.html', error="卡号或密码错误")

    return render_template('login.html')

# 主菜单页，验证用户是否已登录
@app.route('/menu')
def menu():
    if 'card_number' not in session:
        return redirect(url_for('login'))  # 未登录时跳转到登录页
    return render_template('menu.html', name=session['user_name'])  # 显示用户名

# 存款功能
@app.route('/deposit', methods=['GET', 'POST'])
def deposit():
    if 'card_number' not in session:
        return redirect(url_for('login'))  # 未登录时跳转到登录页

    if request.method == 'POST':
        try:
            # 获取并转换存款金额
            amount = float(request.form.get('amount', 0))
            if amount <= 0:
                return render_template('deposit.html', error="存入金额必须大于0！")

            # 数据库更新余额并记录交易
            conn = mysql.connector.connect(**db_config)
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET balance = balance + %s WHERE card_number = %s", (amount, session['card_number']))
            cursor.execute("INSERT INTO transactions (card_number, type, amount) VALUES (%s, '存款', %s)",
                           (session['card_number'], amount))
            conn.commit()

            # 查询最新余额
            cursor.execute("SELECT balance FROM users WHERE card_number = %s", (session['card_number'],))
            balance = cursor.fetchone()[0]
            cursor.close()
            conn.close()

            return render_template('deposit.html', success=f"存款成功 ¥{amount:.2f}，当前余额: ¥{balance:.2f}")
        except ValueError:
            return render_template('deposit.html', error="请输入存款金额")

    return render_template('deposit.html')

# 取款功能
@app.route('/withdraw', methods=['GET', 'POST'])
def withdraw():
    if 'card_number' not in session:
        return redirect(url_for('login'))  # 未登录时跳转到登录页

    if request.method == 'POST':
        try:
            # 获取并转换取款金额
            amount = float(request.form.get('amount', 0))
            if amount <= 0:
                return render_template('withdraw.html', error="取出金额必须大于0！")

            conn = mysql.connector.connect(**db_config)
            cursor = conn.cursor(dictionary=True)

            # 获取当前余额
            cursor.execute("SELECT balance FROM users WHERE card_number = %s", (session['card_number'],))
            user = cursor.fetchone()

            # 判断余额是否充足
            if not user or amount > user['balance']:
                cursor.close()
                conn.close()
                return render_template('withdraw.html', error="余额不足")

            # 更新余额并插入交易记录
            cursor.execute("UPDATE users SET balance = balance - %s WHERE card_number = %s", (amount, session['card_number']))
            cursor.execute("INSERT INTO transactions (card_number, type, amount) VALUES (%s, '取款', %s)",
                           (session['card_number'], amount))
            conn.commit()

            # 查询最新余额
            cursor.execute("SELECT balance FROM users WHERE card_number = %s", (session['card_number'],))
            balance = cursor.fetchone()['balance']
            cursor.close()
            conn.close()

            return render_template('withdraw.html', success=f"取款成功 ¥{amount:.2f}，当前余额: ¥{balance:.2f}")
        except ValueError:
            return render_template('withdraw.html', error="请输入取款金额")

    return render_template('withdraw.html')

# 转账功能
@app.route('/transfer', methods=['GET', 'POST'])
def transfer():
    if 'card_number' not in session:
        return redirect(url_for('login'))  # 未登录时跳转到登录页

    error = None
    success = None

    if request.method == 'POST':
        target_card = request.form.get('target_card')  # 获取转账卡号
        confirm_name = request.form.get('confirm_name')  # 获取确认姓名
        amount = request.form.get('amount')  # 获取转账金额

        try:
            conn = mysql.connector.connect(**db_config)
            cursor = conn.cursor()

            # 查询收款人姓名
            cursor.execute("SELECT user_name FROM users WHERE card_number = %s", (target_card,))
            result = cursor.fetchone()

            if result:
                real_name = result[0]

                if str(target_card).strip() == str(session['card_number']).strip():
                    error = "不能向本人账户转账！"
                elif confirm_name.strip() != real_name:
                    error = "收款人姓名与卡号不匹配，转账失败"
                else:
                    amount = float(amount)
                    if amount <= 0:
                        error = "请输入有效金额"
                    else:
                        # 查询当前用户余额
                        cursor.execute("SELECT balance FROM users WHERE card_number = %s", (session['card_number'],))
                        my_balance = cursor.fetchone()[0]

                        if my_balance >= amount:
                            # 扣除本人余额
                            cursor.execute("UPDATE users SET balance = balance - %s WHERE card_number = %s",
                                           (amount, session['card_number']))
                            # 增加对方余额
                            cursor.execute("UPDATE users SET balance = balance + %s WHERE card_number = %s",
                                           (amount, target_card))

                            # 记录转出
                            cursor.execute("INSERT INTO transactions (card_number, type, amount, target_card) VALUES (%s, '转账', %s, %s)",
                                           (session['card_number'], amount, target_card))
                            # 记录转入
                            cursor.execute("INSERT INTO transactions (card_number, type, amount, target_card) VALUES (%s, '转入', %s, %s)",
                                           (target_card, amount, session['card_number']))

                            conn.commit()
                            success = f"成功转账 ¥{amount:.2f} 给 {real_name}"
                        else:
                            error = "余额不足"
            else:
                error = "卡号不存在或无效"

            cursor.close()
            conn.close()

        except Exception as e:
            error = f"发生错误：{str(e)}"

    return render_template('transfer.html', error=error, success=success)

# 账户管理功能
@app.route('/management', methods=['GET', 'POST'])
def management():
    if 'card_number' not in session:
        return redirect(url_for('login'))  # 未登录时跳转到登录页
    return render_template('management.html')

# 修改密码功能
@app.route('/change', methods=['GET', 'POST'])
def change():
    if 'card_number' not in session:
        return redirect(url_for('login'))  # 未登录跳转

    card_number = session['card_number']
    error = None
    success = None

    if request.method == 'POST':
        old_password = request.form['old_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        # 校验新密码是否为6位数字
        if len(new_password) != 6 or not new_password.isdigit():
            error = '新密码必须为6位数字！'
        elif new_password != confirm_password:
            error = '两次输入的密码不一致！'
        else:
            conn = mysql.connector.connect(**db_config)
            cursor = conn.cursor(dictionary=True)

            # 查询当前用户的原密码
            cursor.execute("SELECT pin FROM users WHERE card_number = %s", (card_number,))
            user = cursor.fetchone()

            if not user or user['pin'] != old_password:
                error = '旧密码不正确！'
            else:
                cursor.execute("UPDATE users SET pin = %s WHEREx card_number = %s", (new_password, card_number))
                conn.commit()
                success = '密码修改成功！'

            cursor.close()
            conn.close()

    return render_template('ment/change.html', error=error, success=success)


# 账户余额查询功能
@app.route('/balance')
def balance():
    if 'card_number' not in session:
        return redirect(url_for('login'))  # 未登录时跳转到登录页

    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE card_number = %s", (session['card_number'],))
    balance = cursor.fetchone()[0]
    cursor.close()
    conn.close()

    return render_template('ment/balance.html', balance=balance)

# 交易记录分页查询功能
@app.route('/record')
def record():
    if 'card_number' not in session:
        return redirect(url_for('login'))  # 未登录时跳转到登录页

    # 获取当前页码，默认为1
    page = int(request.args.get('page', 1))
    per_page = 6  # 每页显示条数
    offset = (page - 1) * per_page

    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)

    # 查询总记录数
    cursor.execute("SELECT COUNT(*) AS total FROM transactions WHERE card_number = %s", (session['card_number'],))
    total_records = cursor.fetchone()['total']
    total_pages = (total_records + per_page - 1) // per_page  # 向上取整

    # 获取当前页的记录
    cursor.execute("""
        SELECT id, type, amount, target_card, timestamp
        FROM transactions
        WHERE card_number = %s
        ORDER BY timestamp DESC
        LIMIT %s OFFSET %s
    """, (session['card_number'], per_page, offset))
    records = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('ment/record.html', records=records, page=page, total_pages=total_pages)

# 设置交易限额功能
@app.route('/limit', methods=['GET', 'POST'])
def limit():
    return render_template('ment/limit.html')

# 退出登录，清空 session
@app.route('/logout')
def logout():
    session.clear()  # 清空会话信息
    return redirect(url_for('login'))  # 重定向到登录页面
