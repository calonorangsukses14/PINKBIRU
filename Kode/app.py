from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func
import os
import json

# --- KONFIGURASI APP ---
app = Flask(__name__, static_folder='static')
app.secret_key = 'rahasia_negara_ratbook_secure_key_v3_final'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 

# --- KONFIGURASI SUPABASE (POSTGRESQL) ---
db_uri = 'postgresql://postgres.dabpevtundqjxiwenpyo:ratbook123@aws-1-ap-southeast-1.pooler.supabase.com:6543/postgres'

# Fix untuk SQLAlchemy: ubah 'postgres://' jadi 'postgresql://'
app.config['SQLALCHEMY_DATABASE_URI'] = db_uri.replace("postgres://", "postgresql://")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Konfigurasi Upload Folder
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static', 'uploads')

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

db = SQLAlchemy(app)

# --- MODEL DATABASE ---

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), nullable=False, unique=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False) 
    normal_balance = db.Column(db.String(10), nullable=False) 
    
    def to_dict(self):
        return {
            'id': self.id, 'code': self.code, 'name': self.name,
            'category': self.category, 'normal_balance': self.normal_balance
        }

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    qty = db.Column(db.Float, default=0)
    avg_cost = db.Column(db.Float, default=0) 
    
    def to_dict(self):
        return {
            'id': self.id, 'code': self.code, 'name': self.name,
            'qty': self.qty, 'avg_cost': self.avg_cost,
            'total_value': self.qty * self.avg_cost
        }

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    due_date = db.Column(db.Date, nullable=True)
    description = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(50), default="Umum") 
    proof_file = db.Column(db.String(200), nullable=True)
    
    entries = db.relationship('JournalEntry', backref='transaction', cascade="all, delete-orphan")

    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date.strftime('%Y-%m-%d'),
            'due_date': self.due_date.strftime('%Y-%m-%d') if self.due_date else None,
            'description': self.description,
            'type': self.type,
            'proof': self.proof_file,
            'entries': [e.to_dict() for e in self.entries]
        }

class JournalEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transaction.id'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    
    debit = db.Column(db.Float, default=0)
    credit = db.Column(db.Float, default=0)
    sub_ledger_name = db.Column(db.String(100), nullable=True)
    
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=True)
    qty = db.Column(db.Float, default=0) 
    
    account = db.relationship('Account')
    product = db.relationship('Product')

    def to_dict(self):
        return {
            'account_id': self.account_id,
            'account_name': self.account.name,
            'account_code': self.account.code,
            'account_category': self.account.category,
            'debit': self.debit,
            'credit': self.credit,
            'sub_name': self.sub_ledger_name,
            'product_name': self.product.name if self.product else None,
            'qty': self.qty
        }

# --- SEEDING DATA ---
def seed_data():
    if not User.query.filter_by(username='admin').first():
        u = User(username='admin', email='admin@ratbook.com')
        u.set_password('admin')
        db.session.add(u)
        db.session.commit()
        print(">>> User Admin Created.")

    if Account.query.first(): return

    def create_acc(code, name):
        c = str(code)
        cat = 'ASET'
        norm = 'debit'
        
        if c.startswith('1'): cat = 'ASET'
        elif c.startswith('2'): cat = 'KEWAJIBAN'; norm = 'credit'
        elif c.startswith('3'): cat = 'MODAL'; norm = 'credit'
        elif c.startswith('4'): cat = 'PENDAPATAN'; norm = 'credit'
        elif c.startswith('5'): cat = 'HPP'
        elif c.startswith('6'): cat = 'BEBAN'
        
        if 'Akumulasi' in name: norm = 'credit'
        
        return Account(code=c, name=name, category=cat, normal_balance=norm)

    raw_data = [
        ('10000', 'ASET'), ('11000', 'Aset Lancar'), 
        ('11100', 'Kas dan Setara Kas'), ('11101', 'Kas Kecil'), ('11102', 'Kas Bank'),
        ('11200', 'Piutang'), ('11201', 'Piutang Usaha'),
        ('12000', 'Perlengkapan'), ('12101', 'Perlengkapan Delivery Box'), ('12102', 'Perlengkapan ATK'), ('12103', 'Perlengkapan Gabah'),
        ('13000', 'Persediaan'), ('13101', 'Persediaan Pakanpur'),
        ('13200', 'Aset Biologis- RAT'), ('13201', 'Aset Biologis Indukan Rat'), ('13202', 'Aset Biologis Small Rat'), ('13203', 'Aset Biologis Medium Rat'), ('13204', 'Aset Biologis Dewasa Rat'),
        ('13300', 'Aset Biologis ASF'), ('13301', 'Aset Biologis Indukan ASF'), ('13302', 'Aset Biologis Small ASF'), ('13303', 'Aset Biologis Medium ASF'), ('13304', 'Aset Biologis Dewasa ASF'),
        ('13400', 'Aset Biologis Mencit'), ('13401', 'Aset Biologis Indukan Mencit'), ('13402', 'Aset Biologis Small Mencit'), ('13403', 'Aset Biologis Medium Mencit'), ('13404', 'Aset Biologis Dewasa Mencit'),
        ('13405', 'Aset Biologis Mencit Pinkies'), ('13406', 'Aset Biologis Mencit Pinbul'), ('13407', 'Aset Biologis Mencit Jumper'), ('13408', 'Aset Biologis Mencit Afkir'),
        ('14000', 'Aset Tetap'),
        ('14100', 'Peralatan Box Besar'), ('14101', 'Akumulasi Penyusutan Peralatan Box Besar'),
        ('14200', 'Peralatan Box Kecil'), ('14201', 'Akumulasi Penyusutan Peralatan Box Kecil'),
        ('14300', 'Peralatan Rak'), ('14301', 'Akumulasi Penyusutan Peralatan Rak'),
        ('14400', 'Peralatan Makan Minum'), ('14401', 'Akumulasi Penyusutan Peralatan Makan Minum'),
        ('14500', 'Peralatan Blower'), ('14501', 'Akumulasi Penyusutan Peralatan Blower'),
        ('14600', 'Kendaraan Motor (4 tahun)'), ('14601', 'Akumulasi Penyusutan Kendaraan'),
        ('20000', 'LIABILITAS'), ('21000', 'Liabilitas Lancar'), ('21101', 'Utang Usaha'),
        ('30000', 'EKUITAS'), ('31000', 'Modal Pemilik'), ('31101', 'Modal Pemilik'),
        ('40000', 'PENDAPATAN'), ('41000', 'Pendapatan penjualan'), ('41101', 'Penjualan Tikus'), ('42000', 'Pendapatan lain-lain'),
        ('50000', 'HPP'), ('51000', 'HPP tikus terjual'),
        ('60000', 'BEBAN'), ('61000', 'Beban Pakan'), ('62000', 'Beban listrik dan air'), ('63000', 'Beban mortalitas aset biologis'), ('64000', 'Beban ATK'), ('65000', 'Beban Penyusutan Aset Tetap'), ('66000', 'Beban Kebersihan')
    ]

    accs = [create_acc(code, name) for code, name in raw_data]
    db.session.bulk_save_objects(accs)
    db.session.commit()
    print(">>> Database Seeded with Complete Chart of Accounts.")

# --- ROUTES AUTH ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        form_type = request.form.get('form_type')
        if form_type == 'login':
            email = request.form.get('email')
            password = request.form.get('password')
            user = User.query.filter((User.email==email) | (User.username==email)).first()
            if user and user.check_password(password):
                session['user_id'] = user.id
                session['username'] = user.username
                return redirect(url_for('dashboard'))
            else:
                return render_template('login.html', error="Email atau Password Salah")
        elif form_type == 'register':
            email = request.form.get('email')
            username = request.form.get('new_username')
            password = request.form.get('new_password')
            if User.query.filter((User.email==email) | (User.username==username)).first():
                 return render_template('login.html', error="Email/Username sudah terdaftar!")
            new_user = User(email=email, username=username)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            return render_template('login.html', success="Registrasi Sukses! Silakan Login.")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def dashboard():
    if 'user_id' not in session: return redirect(url_for('login'))
    return render_template('dashboard.html', username=session['username'])

# --- API ROUTES ---
@app.route('/api/dashboard-stats')
def dashboard_stats():
    start = request.args.get('start', date.today().strftime('%Y-%m-01')) 
    end = request.args.get('end', date.today().strftime('%Y-%m-%d'))
    s_date = datetime.strptime(start, '%Y-%m-%d').date()
    e_date = datetime.strptime(end, '%Y-%m-%d').date()

    entries = db.session.query(
        Account.category, 
        func.sum(JournalEntry.debit).label('total_debit'),
        func.sum(JournalEntry.credit).label('total_credit')
    ).join(Account).join(Transaction).filter(
        Transaction.date.between(s_date, e_date)
    ).group_by(Account.category).all()

    summary = {'income': 0, 'expense': 0, 'cogs': 0, 'net_profit': 0}
    for cat, dr, cr in entries:
        dr = dr or 0; cr = cr or 0
        if cat == 'PENDAPATAN': summary['income'] += (cr - dr)
        elif cat == 'BEBAN': summary['expense'] += (dr - cr)
        elif cat == 'HPP': summary['cogs'] += (dr - cr)

    summary['net_profit'] = summary['income'] - summary['expense'] - summary['cogs']

    overdue = Transaction.query.filter(Transaction.due_date < date.today(), Transaction.due_date != None).order_by(Transaction.due_date).limit(5).all()
    alerts = [{'date': t.date.strftime('%d-%m'), 'desc': t.description, 'days': (date.today() - t.due_date).days} for t in overdue]

    return jsonify({'summary': summary, 'alerts': alerts})

@app.route('/api/accounts', methods=['GET', 'POST'])
def handle_accounts():
    if request.method == 'POST':
        d = request.json
        try:
            new_acc = Account(code=d['code'], name=d['name'], category=d['category'], normal_balance=d['normal_balance'])
            db.session.add(new_acc)
            db.session.commit()
            return jsonify({'msg': 'Success'})
        except Exception as e: return jsonify({'error': str(e)}), 400
    accs = Account.query.order_by(Account.code).all()
    return jsonify([a.to_dict() for a in accs])

@app.route('/api/accounts/<int:id>', methods=['PUT', 'DELETE'])
def manage_single_account(id):
    acc = Account.query.get(id)
    if not acc: return jsonify({'error': 'Not Found'}), 404
    if request.method == 'DELETE':
        db.session.delete(acc)
        db.session.commit()
        return jsonify({'msg': 'Deleted'})
    if request.method == 'PUT':
        d = request.json
        acc.code = d['code']
        acc.name = d['name']
        acc.category = d['category']
        acc.normal_balance = d['normal_balance']
        db.session.commit()
        return jsonify({'msg': 'Updated'})

@app.route('/api/products', methods=['GET', 'POST'])
def handle_products():
    if request.method == 'POST':
        d = request.json
        try:
            p = Product(code=d['code'], name=d['name'], qty=d['qty'], avg_cost=d['cost'])
            db.session.add(p)
            db.session.commit()
            return jsonify({'msg': 'Product Created'})
        except: return jsonify({'error': 'Gagal'}), 400
    prods = Product.query.order_by(Product.name).all()
    return jsonify([p.to_dict() for p in prods])

@app.route('/api/products/<int:id>', methods=['PUT', 'DELETE'])
def manage_single_product(id):
    p = Product.query.get(id)
    if not p: return jsonify({'error': 'Not Found'}), 404

    if request.method == 'DELETE':
        db.session.delete(p)
        db.session.commit()
        return jsonify({'msg': 'Deleted'})

    if request.method == 'PUT':
        d = request.json
        p.code = d['code']
        p.name = d['name']
        p.qty = float(d['qty'])
        p.avg_cost = float(d['cost'])
        db.session.commit()
        return jsonify({'msg': 'Updated'})

@app.route('/api/transactions', methods=['GET', 'POST'])
def handle_transactions():
    if request.method == 'POST':
        try:
            date_val = datetime.strptime(request.form['date'], '%Y-%m-%d')
            due_date = None
            if request.form.get('due_date'):
                due_date = datetime.strptime(request.form['due_date'], '%Y-%m-%d')

            filename = None
            if 'proof' in request.files:
                file = request.files['proof']
                if file.filename != '':
                    filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

            new_trans = Transaction(
                date=date_val, due_date=due_date, 
                description=request.form['description'], 
                type=request.form.get('type', 'Umum'), proof_file=filename
            )
            db.session.add(new_trans)
            db.session.flush()

            lines = json.loads(request.form['lines_json'])
            for line in lines:
                acc_id = int(line['accountId'])
                debit = float(line['debit'])
                credit = float(line['credit'])
                prod_id = line.get('productId')
                qty = float(line.get('qty', 0))
                
                if prod_id and qty > 0:
                    product = Product.query.get(prod_id)
                    inv_list = json.loads(request.form.get('inventory_json', '[]'))
                    inv_item = next((item for item in inv_list if str(item['product_id']) == str(prod_id)), None)
                    
                    if request.form.get('type') == 'Pembelian' and inv_item:
                        total_buy = float(inv_item['total'])
                        old_val = product.qty * product.avg_cost
                        new_qty = product.qty + qty
                        product.avg_cost = (old_val + total_buy) / new_qty if new_qty > 0 else 0
                        product.qty = new_qty
                    elif request.form.get('type') == 'Penjualan':
                        product.qty -= qty

                entry = JournalEntry(
                    transaction_id=new_trans.id, account_id=acc_id,
                    debit=debit, credit=credit,
                    sub_ledger_name=line.get('subName', ''),
                    product_id=prod_id if prod_id else None, qty=qty
                )
                db.session.add(entry)

            db.session.commit()
            return jsonify({'msg': 'Sukses'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

    start = request.args.get('start')
    end = request.args.get('end')
    query = Transaction.query.order_by(Transaction.date.desc(), Transaction.id.desc())
    if start and end:
        s_date = datetime.strptime(start, '%Y-%m-%d')
        e_date = datetime.strptime(end, '%Y-%m-%d')
        query = query.filter(Transaction.date.between(s_date, e_date))
    return jsonify([t.to_dict() for t in query.all()])

@app.route('/api/transactions/<int:id>', methods=['DELETE'])
def delete_transaction(id):
    t = Transaction.query.get(id)
    if t:
        db.session.delete(t)
        db.session.commit()
        return jsonify({'msg': 'Deleted'})
    return jsonify({'error': 'Not Found'}), 404

# --- API LAPORAN LENGKAP (UPDATED LOGIC PEMBANTU) ---
@app.route('/api/reports/all')
def financial_report():
    start = request.args.get('start')
    end = request.args.get('end')
    
    query = JournalEntry.query.join(Transaction)
    if start and end:
        s_date = datetime.strptime(start, '%Y-%m-%d').date()
        e_date = datetime.strptime(end, '%Y-%m-%d').date()
        query = query.filter(Transaction.date.between(s_date, e_date))
    
    entries = query.all()
    
    ledger = {}
    ap_ledger = {} 
    ar_ledger = {} 
    summary = {'income':0, 'expense':0, 'cogs':0, 'asset':0, 'liability':0, 'equity':0}
    monthly_agg = {} 

    for e in entries:
        cat = e.account.category
        val = (e.debit - e.credit) if e.account.normal_balance == 'debit' else (e.credit - e.debit)
        
        if e.account_id not in ledger:
            ledger[e.account_id] = {'id': e.account_id, 'code':e.account.code, 'name':e.account.name, 'category':cat, 'balance':0, 'normal_balance': e.account.normal_balance, 'entries':[]}
        ledger[e.account_id]['balance'] += val
        
        desc_full = e.transaction.description
        if e.product: desc_full += f" ({e.product.name} x{e.qty})"

        ledger[e.account_id]['entries'].append({
            'date':e.transaction.date.strftime('%Y-%m-%d'), 
            'desc': desc_full, 
            'debit':e.debit, 'credit':e.credit
        })

        if cat == 'PENDAPATAN': summary['income'] += e.credit
        elif cat == 'BEBAN': summary['expense'] += e.debit
        elif cat == 'HPP': summary['cogs'] += e.debit
        
        m_key = e.transaction.date.strftime('%Y-%m')
        if m_key not in monthly_agg: monthly_agg[m_key] = {'inc':0, 'exp':0}
        if cat == 'PENDAPATAN': monthly_agg[m_key]['inc'] += e.credit
        if cat in ['BEBAN', 'HPP']: monthly_agg[m_key]['exp'] += e.debit

        # --- LOGIC BUKU PEMBANTU (REVISED) ---
        if e.sub_ledger_name:
            item = {'date':e.transaction.date.strftime('%Y-%m-%d'), 'desc':e.transaction.description, 'debit':e.debit, 'credit':e.credit, 'due': e.transaction.due_date.strftime('%Y-%m-%d') if e.transaction.due_date else '-'}
            
            # UTANG: Kategori KEWAJIBAN atau Kode mulai '2' atau Nama mengandung 'Utang'
            if e.account.category == 'KEWAJIBAN' or e.account.code.startswith('2') or 'Utang' in e.account.name: 
                if e.sub_ledger_name not in ap_ledger: ap_ledger[e.sub_ledger_name] = {'balance':0, 'entries':[]}
                ap_ledger[e.sub_ledger_name]['balance'] += (e.credit - e.debit)
                ap_ledger[e.sub_ledger_name]['entries'].append(item)
            
            # PIUTANG: Kode mulai '112' (Sesuai COA Ndan) atau Nama mengandung 'Piutang'
            elif e.account.code.startswith('112') or 'Piutang' in e.account.name: 
                if e.sub_ledger_name not in ar_ledger: ar_ledger[e.sub_ledger_name] = {'balance':0, 'entries':[]}
                ar_ledger[e.sub_ledger_name]['balance'] += (e.debit - e.credit)
                ar_ledger[e.sub_ledger_name]['entries'].append(item)

    chart_data = {'labels': sorted(monthly_agg.keys()), 'income': [], 'expense': []}
    for k in chart_data['labels']:
        chart_data['income'].append(monthly_agg[k]['inc'])
        chart_data['expense'].append(monthly_agg[k]['exp'])

    net_profit = summary['income'] - (summary['expense'] + summary['cogs'])
    
    bs_query = JournalEntry.query.join(Transaction)
    if end:
        bs_end = datetime.strptime(end, '%Y-%m-%d').date()
        bs_query = bs_query.filter(Transaction.date <= bs_end)
    
    for e in bs_query.all():
        cat = e.account.category
        if cat == 'ASET': summary['asset'] += (e.debit - e.credit)
        elif cat == 'KEWAJIBAN': summary['liability'] += (e.credit - e.debit)
        elif cat == 'MODAL': summary['equity'] += (e.credit - e.debit)
    
    return jsonify({
        'summary': summary, 'net_profit': net_profit,
        'ledger': list(ledger.values()),
        'ap_ledger': ap_ledger, 'ar_ledger': ar_ledger,
        'chart': chart_data
    })

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        seed_data()
    app.run(debug=True, port=5000)