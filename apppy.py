app.py
# app.py
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.mysql import insert
import pandas as pd
import io
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'mysql+pymysql://user:pass@localhost/dbname')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class User(db.Model):
    __tablename__ = 'users'
    user_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)

class FinancialRecord(db.Model):
    __tablename__ = 'financial_records'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    year = db.Column(db.SmallInteger, nullable=False)
    month = db.Column(db.SmallInteger, nullable=False)
    category = db.Column(db.String(100))
    amount = db.Column(db.Numeric(15,2), nullable=False)
    note = db.Column(db.Text)

# simple helper to upsert record (replace on same user/year/month)
def upsert_record(session, rec):
    stmt = insert(FinancialRecord).values(**rec)
    upd = {c.name: stmt.inserted[c.name] for c in FinancialRecord.__table__.columns if c.name not in ('id',)}
    stmt = stmt.on_duplicate_key_update(**upd)
    session.execute(stmt)

@app.route('/upload', methods=['POST'])
def upload():
    """
    Expects multipart/form-data with:
      - file: Excel file
      - user_name: string (or user_id)
      - year: integer
    Excel expected: columns like "Month", "Amount", "Category", "Note"
    Month can be name (Jan) or number.
    """
    file = request.files.get('file')
    user_name = request.form.get('user_name')
    year = request.form.get('year', type=int)
    if not file or not user_name or not year:
        return jsonify({'error': 'file, user_name and year are required'}), 400

    # get or create user
    user = User.query.filter_by(name=user_name).first()
    if not user:
        user = User(name=user_name)
        db.session.add(user)
        db.session.commit()

    # read excel into pandas
    try:
        in_mem = io.BytesIO(file.read())
        df = pd.read_excel(in_mem)    # uses openpyxl engine for .xlsx
    except Exception as e:
        return jsonify({'error': 'failed to read excel', 'details': str(e)}), 400

    # normalize expected columns
    colmap = {c.lower().strip(): c for c in df.columns}
    # try to find month and amount columns
    # Accept columns named Month, Amount, Category, Note (case-insensitive)
    def find_col(k):
        for key in df.columns:
            if key.strip().lower() == k:
                return key
        return None

    month_col = find_col('month') or find_col('monthname') or find_col('m')
    amount_col = find_col('amount') or find_col('value') or find_col('amt')
    category_col = find_col('category')
    note_col = find_col('note')

    if month_col is None or amount_col is None:
        return jsonify({'error': 'Excel must contain Month and Amount columns'}), 400

    records_upserted = 0
    for _, row in df.iterrows():
        raw_month = row[month_col]
        # convert month to int 1..12
        try:
            if pd.isna(raw_month):
                continue
            if isinstance(raw_month, (int, float)):
                month = int(raw_month)
            else:
                # try parse month name
                month = pd.to_datetime(str(raw_month), format='%b', errors='coerce')
                if pd.isna(month):
                    month = pd.to_datetime(str(raw_month), format='%B', errors='coerce')
                if pd.isna(month):
                    # fallback: try parse as date
                    month = pd.to_datetime(str(raw_month), errors='coerce')
                if pd.isna(month):
                    continue
                month = int(month.month)
        except Exception:
            continue

        try:
            amount = float(row[amount_col])
        except Exception:
            continue

        rec = {
            'user_id': user.user_id,
            'year': int(year),
            'month': int(month),
            'category': str(row[category_col]) if category_col in df.columns and not pd.isna(row[category_col]) else None,
            'amount': round(float(amount), 2),
            'note': str(row[note_col]) if note_col in df.columns and not pd.isna(row[note_col]) else None
        }
        upsert_record(db.session, rec)
        records_upserted += 1

    db.session.commit()
    return jsonify({'status': 'ok', 'upserted': records_upserted})

@app.route('/records', methods=['GET'])
def get_records():
    """GET /records?user_name=...&year=2025
       returns list of monthly records and aggregated totals by month
    """
    user_name = request.args.get('user_name')
    year = request.args.get('year', type=int)
    if not user_name or not year:
        return jsonify({'error': 'user_name and year required'}), 400
    user = User.query.filter_by(name=user_name).first()
    if not user:
        return jsonify({'data': [], 'monthly': []})

    rows = FinancialRecord.query.filter_by(user_id=user.user_id, year=year).order_by(FinancialRecord.month).all()
    data = [{
        'month': r.month, 'amount': float(r.amount), 'category': r.category, 'note': r.note
    } for r in rows]

    # prepare monthly totals (0..12)
    monthly = [0.0]*12
    for r in data:
        if 1 <= r['month'] <= 12:
            monthly[r['month']-1] += r['amount']

    return jsonify({'data': data, 'monthly': monthly})

if __name__ == '__main__':
    app.run(debug=True)

