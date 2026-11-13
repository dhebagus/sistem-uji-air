import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, flash, session
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'royalti_air_minum_secret_key_2026'
DB_PATH = os.path.join(os.path.dirname(__file__), 'toko_royalti.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Create Tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cabang (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama_cabang TEXT NOT NULL,
            alamat TEXT NOT NULL,
            kota TEXT NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            nama_lengkap TEXT NOT NULL,
            cabang_id INTEGER,
            FOREIGN KEY (cabang_id) REFERENCES cabang(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS uji_air (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cabang_id INTEGER NOT NULL,
            tanggal TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ph REAL NOT NULL,
            tds REAL NOT NULL,
            suhu REAL,
            keterangan TEXT NOT NULL,
            petugas_id INTEGER NOT NULL,
            catatan TEXT,
            FOREIGN KEY (cabang_id) REFERENCES cabang(id),
            FOREIGN KEY (petugas_id) REFERENCES user(id)
        )
    ''')
    
    # Seed default cabang if empty
    cursor.execute('SELECT COUNT(*) FROM cabang')
    if cursor.fetchone()[0] == 0:
        cursor.executemany('INSERT INTO cabang (nama_cabang, alamat, kota) VALUES (?, ?, ?)', [
            ('Cabang Utama Pusat', 'Jl. Sudirman No. 12', 'Tangerang'),
            ('Cabang Cimone', 'Jl. Proklamasi No. 45', 'Tangerang'),
            ('Cabang Ciledug', 'Jl. HOS Cokroaminoto No. 8', 'Tangerang')
        ])
        
    # Seed default user if empty
    cursor.execute('SELECT COUNT(*) FROM user')
    if cursor.fetchone()[0] == 0:
        cursor.executemany('INSERT INTO user (username, password, role, nama_lengkap, cabang_id) VALUES (?, ?, ?, ?, ?)', [
            ('owner', generate_password_hash('owner123'), 'owner', 'Bapak Owner Royalti', None),
            ('admin', generate_password_hash('admin123'), 'admin', 'Admin Sistem', None),
            ('staff1', generate_password_hash('staff123'), 'staff', 'Petugas Cabang Utama', 1),
            ('staff2', generate_password_hash('staff123'), 'staff', 'Petugas Cabang Cimone', 2)
        ])
        
    conn.commit()
    conn.close()

init_db()

# Decorators for authentication
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Silakan login terlebih dahulu.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*roles):
    def decorator(f):
        from functools import wraps
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            if session['role'] not in roles:
                flash('Anda tidak memiliki hak akses ke halaman ini.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db()
        user = conn.execute('SELECT * FROM user WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['nama_lengkap'] = user['nama_lengkap']
            session['cabang_id'] = user['cabang_id']
            flash(f'Selamat datang, {user["nama_lengkap"]}!', 'success')
            return redirect(url_for('dashboard'))
        flash('Username atau password salah.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Anda telah logout.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db()
    user_id = session['user_id']
    role = session['role']
    cabang_id_user = session.get('cabang_id')
    
    user = conn.execute('SELECT * FROM user WHERE id = ?', (user_id,)).fetchone()
    
    if role == 'staff':
        uji_list = conn.execute('''
            SELECT u.*, c.nama_cabang, us.nama_lengkap as nama_petugas 
            FROM uji_air u 
            JOIN cabang c ON u.cabang_id = c.id 
            JOIN user us ON u.petugas_id = us.id 
            WHERE u.cabang_id = ? 
            ORDER BY u.tanggal DESC
        ''', (cabang_id_user,)).fetchall()
    else:
        uji_list = conn.execute('''
            SELECT u.*, c.nama_cabang, us.nama_lengkap as nama_petugas 
            FROM uji_air u 
            JOIN cabang c ON u.cabang_id = c.id 
            JOIN user us ON u.petugas_id = us.id 
            ORDER BY u.tanggal DESC
        ''').fetchall()
        
    total_uji = len(uji_list)
    layak_count = sum(1 for u in uji_list if u['keterangan'] == 'Layak')
    tidak_layak_count = total_uji - layak_count
    total_cabang = conn.execute('SELECT COUNT(*) FROM cabang').fetchone()[0]
    
    conn.close()
    
    return render_template('dashboard.html', user=user, uji_list=uji_list[:10], 
                           total_uji=total_uji, layak_count=layak_count, 
                           tidak_layak_count=tidak_layak_count, total_cabang=total_cabang)

@app.route('/input-uji', methods=['GET', 'POST'])
@login_required
@role_required('staff')
def input_uji():
    conn = get_db()
    user = conn.execute('SELECT u.*, c.nama_cabang FROM user u LEFT JOIN cabang c ON u.cabang_id = c.id WHERE u.id = ?', (session['user_id'],)).fetchone()
    cabang_list = conn.execute('SELECT * FROM cabang').fetchall()
    
    if request.method == 'POST':
        try:
            cabang_id = int(request.form['cabang_id']) if user['role'] != 'staff' else user['cabang_id']
            ph = float(request.form['ph'])
            tds = float(request.form['tds'])
            suhu = float(request.form['suhu']) if request.form['suhu'] else None
            catatan = request.form.get('catatan', '')
            
            # Standar Air Minum: pH 6.5 - 8.5, TDS < 500 ppm
            if 6.5 <= ph <= 8.5 and tds < 500:
                keterangan = 'Layak'
            else:
                keterangan = 'Tidak Layak'
                
            conn.execute('''
                INSERT INTO uji_air (cabang_id, ph, tds, suhu, keterangan, petugas_id, catatan)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (cabang_id, ph, tds, suhu, keterangan, user['id'], catatan))
            conn.commit()
            conn.close()
            flash(f'Data uji berhasil disimpan. Status: {keterangan}', 'success')
            return redirect(url_for('laporan'))
        except Exception as e:
            conn.close()
            flash(f'Terjadi kesalahan: {str(e)}', 'danger')
            
    conn.close()
    return render_template('input_uji.html', user=user, cabang_list=cabang_list)

@app.route('/laporan')
@login_required
def laporan():
    conn = get_db()
    user = conn.execute('SELECT * FROM user WHERE id = ?', (session['user_id'],)).fetchone()
    cabang_id = request.args.get('cabang_id', type=int)
    
    if user['role'] == 'staff':
        uji_list = conn.execute('''
            SELECT u.*, c.nama_cabang, us.nama_lengkap as nama_petugas 
            FROM uji_air u 
            JOIN cabang c ON u.cabang_id = c.id 
            JOIN user us ON u.petugas_id = us.id 
            WHERE u.cabang_id = ? 
            ORDER BY u.tanggal DESC
        ''', (user['cabang_id'],)).fetchall()
    elif cabang_id:
        uji_list = conn.execute('''
            SELECT u.*, c.nama_cabang, us.nama_lengkap as nama_petugas 
            FROM uji_air u 
            JOIN cabang c ON u.cabang_id = c.id 
            JOIN user us ON u.petugas_id = us.id 
            WHERE u.cabang_id = ? 
            ORDER BY u.tanggal DESC
        ''', (cabang_id,)).fetchall()
    else:
        uji_list = conn.execute('''
            SELECT u.*, c.nama_cabang, us.nama_lengkap as nama_petugas 
            FROM uji_air u 
            JOIN cabang c ON u.cabang_id = c.id 
            JOIN user us ON u.petugas_id = us.id 
            ORDER BY u.tanggal DESC
        ''').fetchall()
        
    cabang_list = conn.execute('SELECT * FROM cabang').fetchall()
    conn.close()
    
    return render_template('laporan.html', user=user, uji_list=uji_list, cabang_list=cabang_list, selected_cabang=cabang_id)

@app.route('/cabang', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'owner')
def cabang():
    conn = get_db()
    user = conn.execute('SELECT * FROM user WHERE id = ?', (session['user_id'],)).fetchone()
    
    if request.method == 'POST' and user['role'] == 'admin':
        nama = request.form['nama_cabang']
        alamat = request.form['alamat']
        kota = request.form['kota']
        conn.execute('INSERT INTO cabang (nama_cabang, alamat, kota) VALUES (?, ?, ?)', (nama, alamat, kota))
        conn.commit()
        conn.close()
        flash('Cabang baru berhasil ditambahkan.', 'success')
        return redirect(url_for('cabang'))
        
    cabang_list = conn.execute('SELECT * FROM cabang').fetchall()
    conn.close()
    return render_template('cabang.html', user=user, cabang_list=cabang_list)

@app.route('/users', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def users():
    conn = get_db()
    user = conn.execute('SELECT * FROM user WHERE id = ?', (session['user_id'],)).fetchone()
    
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])
        role = request.form['role']
        nama_lengkap = request.form['nama_lengkap']
        cabang_id = request.form.get('cabang_id', type=int) if role == 'staff' else None
        
        existing = conn.execute('SELECT * FROM user WHERE username = ?', (username,)).fetchone()
        if existing:
            flash('Username sudah digunakan.', 'danger')
        else:
            conn.execute('''
                INSERT INTO user (username, password, role, nama_lengkap, cabang_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (username, password, role, nama_lengkap, cabang_id))
            conn.commit()
            flash('User baru berhasil ditambahkan.', 'success')
        conn.close()
        return redirect(url_for('users'))
        
    user_list = conn.execute('''
        SELECT u.*, c.nama_cabang FROM user u LEFT JOIN cabang c ON u.cabang_id = c.id
    ''').fetchall()
    cabang_list = conn.execute('SELECT * FROM cabang').fetchall()
    conn.close()
    return render_template('users.html', user=user, user_list=user_list, cabang_list=cabang_list)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
