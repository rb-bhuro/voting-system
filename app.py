import sqlite3
from flask import Flask, g, jsonify, request
from flask_mail import Mail, Message
import random
from datetime import datetime, timedelta
from flask_cors import CORS
import os 

app = Flask(__name__)
DATABASE = 'database.db'


CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)


app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'omrangani99@gmail.com'
app.config['MAIL_PASSWORD'] = 'kgdg alxx mmch gqwa'  

mail = Mail(app)


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db:
        db.close()


@app.route('/init-db', methods=['GET'])
def init_db():
    try:
        db = get_db()
        with open('schema.sql', 'r') as f:
            db.executescript(f.read())
        return jsonify({'status': 'success', 'message': 'Database initialized'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/')
def home():
    return 'Voting System API is running!'

@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        print("Register data received:", data)  

        name = data.get('name')
        email = data.get('email')
        phone = data.get('phone')

        if not all([name, email, phone]):
            return jsonify({'status': 'error', 'message': 'Missing required fields'}), 400

        db = get_db()
        cursor = db.cursor()

        cursor.execute('SELECT COUNT(*) as count FROM users')
        user_count = cursor.fetchone()['count']

        cursor.execute('SELECT * FROM users WHERE email = ? OR phone = ?', (email, phone))
        user = cursor.fetchone()

        if user:
            cursor.execute('UPDATE users SET name = ? WHERE id = ?', (name, user['id']))
            db.commit()
            user_id = user['id']
        else:
            is_admin = 1 if user_count == 0 else 0
            cursor.execute(
                'INSERT INTO users (name, email, phone, is_admin) VALUES (?, ?, ?, ?)',
                (name, email, phone, is_admin)
            )
            db.commit()
            user_id = cursor.lastrowid

        return jsonify({'status': 'success', 'user_id': user_id})

    except Exception as e:
        print("Error in /register:", e) 
        return jsonify({'status': 'error', 'message': 'An unexpected error occurred'}), 500



@app.route('/check-admin')
def check_admin():
    email = request.args.get('email')
    if not email:
        return jsonify({'status': 'error', 'message': 'Email is required'}), 400

    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT is_admin FROM users WHERE email = ?', (email,))
    user = cursor.fetchone()

    if not user or user['is_admin'] != 1:
        return jsonify({'status': 'error', 'message': 'User is not an admin'}), 403

    return jsonify({'status': 'success', 'message': 'Admin verified'})


@app.route('/get-user-role', methods=['POST'])
def get_user_role():
    email = request.get_json().get('email')
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT is_admin FROM users WHERE email = ?', (email,))
    user = cursor.fetchone()

    if not user:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    return jsonify({'status': 'success', 'is_admin': user['is_admin']})
@app.route('/get-user', methods=['POST', 'OPTIONS'])
def get_user():
    if request.method == 'OPTIONS':
        return '', 200 
    
    data = request.get_json()
    email = data.get('email')

    if not email:
        return jsonify({'status': 'error', 'message': 'Email is required'}), 400

    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
    user = cursor.fetchone()

    if not user:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    return jsonify({'status': 'success', 'user_id': user['id']})



@app.route('/send-otp', methods=['POST'])
def send_otp():
    data = request.get_json()
    email = data.get('email')

    if not email:
        return jsonify({'status': 'error', 'message': 'Email is required'}), 400

    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
    user = cursor.fetchone()

    if not user:
   
        cursor.execute('INSERT INTO users (name, email, phone, is_admin) VALUES (?, ?, ?, ?)',
                       ('New User', email, '', 0))
        db.commit()
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()

    otp = str(random.randint(100000, 999999))
    expiry = datetime.now() + timedelta(minutes=5)

    try:
        cursor.execute('DELETE FROM otp_codes WHERE user_id = ?', (user['id'],))
        cursor.execute('INSERT INTO otp_codes (user_id, otp_code, expires_at) VALUES (?, ?, ?)',
                       (user['id'], otp, expiry))
        db.commit()
        print(f"✅ OTP stored for user_id={user['id']}: {otp} (expires {expiry})")
    except Exception as e:
        print("❌ Failed to store OTP:", e)
        return jsonify({'status': 'error', 'message': 'Database error while storing OTP'}), 500

    try:
        msg = Message('Your OTP Code', sender=app.config['MAIL_USERNAME'], recipients=[email])
        msg.body = f'Your OTP is: {otp}. It expires in 5 minutes.'
        mail.send(msg)
        return jsonify({'status': 'success', 'message': 'OTP sent to email'})
    except Exception as e:
        print("❌ Failed to send email:", e)
        return jsonify({'status': 'error', 'message': str(e)})



@app.route('/verify-otp', methods=['POST'])
def verify_otp():
    data = request.get_json()
    email = data.get('email')
    otp_input = data.get('otp')

    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
    user = cursor.fetchone()

    if not user:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    cursor.execute('SELECT * FROM otp_codes WHERE user_id = ?', (user['id'],))
    otp_record = cursor.fetchone()
    if not otp_record:
        return jsonify({'status': 'error', 'message': 'OTP not found'}), 404

    try:
        expires_at = datetime.strptime(otp_record['expires_at'], '%Y-%m-%d %H:%M:%S.%f')
    except:
        expires_at = datetime.strptime(otp_record['expires_at'], '%Y-%m-%d %H:%M:%S')

    if datetime.now() > expires_at:
        return jsonify({'status': 'error', 'message': 'OTP expired'}), 410

    if otp_input != otp_record['otp_code']:
        return jsonify({'status': 'error', 'message': 'Incorrect OTP'}), 401

    cursor.execute('UPDATE users SET is_verified = 1 WHERE id = ?', (user['id'],))
    cursor.execute('DELETE FROM otp_codes WHERE user_id = ?', (user['id'],))
    db.commit()

    return jsonify({'status': 'success', 'message': 'OTP verified'})



@app.route('/create-election', methods=['POST'])
def create_election():
    data = request.get_json()
    title = data.get('title')
    description = data.get('description')
    start_time = data.get('start_time')
    end_time = data.get('end_time')

    if not title or not start_time or not end_time:
        return jsonify({'status': 'error', 'message': 'Missing fields'}), 400

    db = get_db()
    cursor = db.cursor()
    cursor.execute('INSERT INTO elections (title, description, start_time, end_time) VALUES (?, ?, ?, ?)', (title, description, start_time, end_time))
    db.commit()
    return jsonify({'status': 'success', 'message': 'Election created'})


@app.route('/edit-election/<int:election_id>', methods=['PUT'])
def edit_election(election_id):
    data = request.get_json()
    title = data.get('title')
    description = data.get('description')
    start_time = data.get('start_time')
    end_time = data.get('end_time')

    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        UPDATE elections
        SET title = ?, description = ?, start_time = ?, end_time = ?
        WHERE id = ?
    ''', (title, description, start_time, end_time, election_id))
    db.commit()
    return jsonify({'status': 'success', 'message': 'Election updated'})

@app.route('/delete-election/<int:election_id>', methods=['DELETE'])
def delete_election(election_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute('DELETE FROM votes WHERE election_id = ?', (election_id,))
    cursor.execute('DELETE FROM candidates WHERE election_id = ?', (election_id,))
    cursor.execute('DELETE FROM elections WHERE id = ?', (election_id,))
    db.commit()
    return jsonify({'status': 'success', 'message': 'Election deleted'})

@app.route('/elections', methods=['GET'])
def get_elections():
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM elections ORDER BY start_time DESC')
    elections = [dict(row) for row in cursor.fetchall()]
    return jsonify({'status': 'success', 'elections': elections})




@app.route('/add-candidate', methods=['POST'])
def add_candidate():
    data = request.get_json()
    db = get_db()
    cursor = db.cursor()
    cursor.execute('INSERT INTO candidates (election_id, name, party, image_url) VALUES (?, ?, ?, ?)',
                   (data['election_id'], data['name'], data.get('party'), data.get('image_url')))
    db.commit()
    return jsonify({'status': 'success', 'message': 'Candidate added'})


@app.route('/edit-candidate/<int:candidate_id>', methods=['PUT'])
def edit_candidate(candidate_id):
    data = request.get_json()
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        UPDATE candidates
        SET name = ?, party = ?, image_url = ?
        WHERE id = ?
    ''', (data['name'], data.get('party'), data.get('image_url'), candidate_id))
    db.commit()
    return jsonify({'status': 'success', 'message': 'Candidate updated'})


@app.route('/delete-candidate/<int:candidate_id>', methods=['DELETE'])
def delete_candidate(candidate_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute('DELETE FROM votes WHERE candidate_id = ?', (candidate_id,))
    cursor.execute('DELETE FROM candidates WHERE id = ?', (candidate_id,))
    db.commit()
    return jsonify({'status': 'success', 'message': 'Candidate deleted'})

@app.route('/candidates/<int:election_id>', methods=['GET'])
def get_candidates(election_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM candidates WHERE election_id = ?', (election_id,))
    candidates = [dict(row) for row in cursor.fetchall()]
    return jsonify({'status': 'success', 'candidates': candidates})



from pytz import timezone  

@app.route('/vote', methods=['POST'])
def vote():
    data = request.get_json()
    user_id = data.get('user_id')
    election_id = data.get('election_id')
    candidate_id = data.get('candidate_id')

    db = get_db()
    cursor = db.cursor()

    cursor.execute('SELECT is_verified FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    if not user or user['is_verified'] == 0:
        return jsonify({'status': 'error', 'message': 'User not verified'}), 403

    cursor.execute('SELECT * FROM elections WHERE id = ?', (election_id,))
    election = cursor.fetchone()

    def parse_datetime(dt_str):
        for fmt in (
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M:%S.%f',
            '%Y-%m-%dT%H:%M',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M:%S.%f'
        ):
            try:
                return datetime.strptime(dt_str, fmt)
            except:
                continue
        raise ValueError("Unknown datetime format")

    start = parse_datetime(election['start_time'])
    end = parse_datetime(election['end_time'])

 
    IST = timezone('Asia/Kolkata')
    if start.tzinfo is None:
        start = IST.localize(start)
    if end.tzinfo is None:
        end = IST.localize(end)

    now_ist = datetime.now(IST)


    print(f"[DEBUG] start: {start}, end: {end}, now: {now_ist}")

    if not (start <= now_ist <= end):
        return jsonify({'status': 'error', 'message': 'Election not active'}), 403

    cursor.execute('SELECT * FROM votes WHERE user_id = ? AND election_id = ?', (user_id, election_id))
    if cursor.fetchone():
        return jsonify({'status': 'error', 'message': 'Already voted'}), 403

    cursor.execute('INSERT INTO votes (user_id, election_id, candidate_id) VALUES (?, ?, ?)', (user_id, election_id, candidate_id))
    db.commit()
    return jsonify({'status': 'success', 'message': 'Vote submitted'})



@app.route('/results/<int:election_id>', methods=['GET'])
def election_results(election_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM elections WHERE id = ?', (election_id,))
    election = cursor.fetchone()

    cursor.execute('''
        SELECT c.id, c.name, c.party, COUNT(v.id) as votes
        FROM candidates c
        LEFT JOIN votes v ON c.id = v.candidate_id AND v.election_id = ?
        WHERE c.election_id = ?
        GROUP BY c.id
        ORDER BY votes DESC
    ''', (election_id, election_id))
    results = [dict(row) for row in cursor.fetchall()]
    return jsonify({'status': 'success', 'election': election['title'], 'results': results})


@app.route('/user-info', methods=['GET'])
def user_info():
    email = request.args.get('email')
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT id, name, email, is_admin FROM users WHERE email = ?', (email,))
    user = cursor.fetchone()
    if not user:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404
    return jsonify({'status': 'success', 'user': dict(user)})

@app.route('/admin/election-votes', methods=['GET'])
def admin_election_votes():
    db = get_db()
    cursor = db.cursor()

  
    cursor.execute('SELECT id, title FROM elections')
    elections = cursor.fetchall()
    result = []

    for election in elections:
        election_id = election['id']
        cursor.execute('SELECT COUNT(*) AS total_votes FROM votes WHERE election_id = ?', (election_id,))
        total_votes = cursor.fetchone()['total_votes']

        cursor.execute('''
            SELECT c.name, c.party, COUNT(v.id) AS votes
            FROM candidates c
            LEFT JOIN votes v ON c.id = v.candidate_id AND v.election_id = ?
            WHERE c.election_id = ?
            GROUP BY c.id
            ORDER BY votes DESC
        ''', (election_id, election_id))
        candidates = [dict(row) for row in cursor.fetchall()]

        result.append({
            'election_title': election['title'],
            'total_votes': total_votes,
            'candidates': candidates
        })

    return jsonify({'status': 'success', 'data': result})

@app.route('/vote-summary', methods=['GET'])
def vote_summary():
    db = get_db()
    cursor = db.cursor()

    cursor.execute('SELECT id, title FROM elections')
    elections = cursor.fetchall()

    summary = []

    for election in elections:
        election_id = election['id']
        title = election['title']

        
        cursor.execute('SELECT COUNT(*) as total_votes FROM votes WHERE election_id = ?', (election_id,))
        total_votes = cursor.fetchone()['total_votes']

      
        cursor.execute('''
            SELECT c.name, c.party, COUNT(v.id) as vote_count
            FROM candidates c
            LEFT JOIN votes v ON c.id = v.candidate_id
            WHERE c.election_id = ?
            GROUP BY c.id
            ORDER BY vote_count DESC
        ''', (election_id,))
        candidates = [dict(row) for row in cursor.fetchall()]

        summary.append({
            'election_title': title,
            'total_votes': total_votes,
            'candidates': candidates
        })

    return jsonify({'status': 'success', 'summary': summary})



if __name__ == '__main__':
   port = int(os.environ.get("PORT", 5000))
   app.run(host='0.0.0.0', port=port)
