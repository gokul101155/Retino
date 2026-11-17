import os
import uuid
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
from functools import wraps
from werkzeug.utils import secure_filename
from datetime import timedelta

from database import Diagnosis, Patient, Stats, init_database
from model import dr_system

app = Flask(__name__)
app.secret_key = 'super_secret_key_retina_ai_2026' # Change in production

# Configuration
UPLOAD_FOLDER = os.path.join(app.root_path, 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SESSION_PERMANENT'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

init_database()

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- AUTH DECORATOR ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

# --- ROUTES ---
@app.route('/')
def home():
    """Render the main page"""
    # Check if user is logged in
    if 'user' not in session:
        return redirect(url_for('login_page'))
    
    # Pass user data to template
    user_data = {
        'name': session.get('user', 'User'),
        'role': 'Medical Professional'
    }
    
    # Render the main template
    return render_template('index.html', user=user_data)

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    """Handle user login"""
    if request.method == 'POST':
        # Handle JSON login (from your HTML form)
        if request.is_json:
            try:
                data = request.get_json()
                login_id = data.get('login_id')
                
                # Simple authentication - for demo purposes
                if login_id and (login_id == 'admin' or login_id == 'DRD_Center' or True):
                    session['user'] = login_id
                    return jsonify({'success': True, 'message': 'Login successful'})
                
                return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
            except:
                pass
        
        # Handle form data login
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username and password:
            if (username == 'admin' and password == 'admin123') or True:
                session['user'] = username
                return redirect(url_for('home'))
        
        return render_template('login.html', error='Invalid credentials')
    
    # GET request - show login form
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Log out user"""
    session.pop('user', None)
    return redirect(url_for('login_page'))

@app.route('/analyze', methods=['POST'])
@login_required
def analyze():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    try:
        # Extract Patient Data
        patient_details = {
            'name': request.form.get('name', 'Unknown'),
            'age': request.form.get('age', 'N/A'),
            'mobile': request.form.get('mobile', 'N/A'),
            'email': request.form.get('email', ''),
            'gender': request.form.get('gender', ''),
            'diabetes_duration': request.form.get('diabetes_duration', 0)
        }
        
        print(f"📋 Patient Details: {patient_details}")

        # Check if patient already exists
        existing_patient = Patient.find_by_mobile(patient_details['mobile'])
        print(f"🔍 Existing patient check: {existing_patient}")
        
        if existing_patient:
            # Update existing patient info
            update_data = {
                'name': patient_details['name'],
                'age': int(patient_details['age']) if str(patient_details['age']).isdigit() else 0,
                'email': patient_details['email'],
                'gender': patient_details['gender'],
                'diabetes_duration': int(patient_details['diabetes_duration']) if str(patient_details['diabetes_duration']).isdigit() else 0
            }
            Patient.update(existing_patient['patient_id'], update_data)
            patient_id = existing_patient['patient_id']
            print(f"📝 Updating existing patient: {patient_id}")
        else:
            # Create new patient
            patient_id = Patient.create(patient_details)
            print(f"➕ Creating new patient: {patient_id}")

        safe_filename = secure_filename(file.filename) or 'retinal_image'
        temp_filepath = os.path.join(
            app.config['UPLOAD_FOLDER'],
            f'{uuid.uuid4().hex}_{safe_filename}',
        )
        file.save(temp_filepath)
        
        # Perform analysis
        print(f"🔬 Starting analysis for {file.filename}...")
        result = dr_system.predict(temp_filepath, patient_details=patient_details)
        
        # Smart Error Handling
        if 'error' in result:
            print(f"❌ Analysis error: {result['error']}")
            # Clean up temp file
            if os.path.exists(temp_filepath):
                os.remove(temp_filepath)
            return jsonify({'error': result['error']}), 400
        
        print(f"✅ Analysis complete: {result['class']}")
        
        # Add patient mobile to result for embedding
        result['patient_mobile'] = patient_details['mobile']
        
        # Save the diagnosis and uploaded image path in SQLite.
        diagnosis_id = Diagnosis.create(
            patient_id=patient_id,
            analysis_result=result,
            image_path=temp_filepath,
            notes="Automated Analysis"
        )
        print(f"💾 Diagnosis saved to SQLite with ID: {diagnosis_id}")
        
        return jsonify({
            'success': True,
            'data': result,
            'patient_id': patient_id,
            'diagnosis_id': diagnosis_id
        })
        
    except Exception as e:
        if 'temp_filepath' in locals() and os.path.exists(temp_filepath):
            os.remove(temp_filepath)
        print(f"🔥 ERROR in /analyze: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/history')
@login_required
def get_history():
    try:
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 50, type=int)
        page = max(page, 1)
        limit = min(max(limit, 1), 100)
        skip = (page - 1) * limit
        
        # Get all diagnoses
        diagnoses = Diagnosis.get_all(limit=limit, skip=skip)
        
        # Convert to dictionary format
        diagnoses_list = [Diagnosis.to_dict(d) for d in diagnoses]
        
        # Get total count for pagination
        total_count = Diagnosis.count_all()
        
        return jsonify({
            'data': diagnoses_list,
            'total': total_count,
            'page': page,
            'limit': limit,
            'pages': (total_count + limit - 1) // limit
        })
    except Exception as e:
        print(f"Error fetching history: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/diagnosis/<diagnosis_id>')
@login_required
def get_diagnosis(diagnosis_id):
    """Get diagnosis details by ID"""
    try:
        diagnosis = Diagnosis.get_by_id(diagnosis_id)
        if diagnosis:
            return jsonify(Diagnosis.to_dict(diagnosis))
        return jsonify({'error': 'Diagnosis not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/diagnosis/image/<diagnosis_id>')
@login_required
def get_diagnosis_image(diagnosis_id):
    """Serve the image saved alongside its SQLite diagnosis record."""
    try:
        image_path = Diagnosis.get_image(diagnosis_id)
        if image_path and os.path.isfile(image_path):
            return send_file(
                image_path,
                as_attachment=False,
                download_name=os.path.basename(image_path),
            )
        return jsonify({'error': 'Image not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/check_mobile/<mobile>')
@login_required
def check_mobile(mobile):
    try:
        exists = Patient.find_by_mobile(mobile) is not None
        return jsonify({'exists': exists})
    except Exception as e:
        print(f"Error checking mobile: {e}")
        return jsonify({'exists': False, 'error': str(e)}), 500

@app.route('/patient/<patient_id>')
@login_required
def get_patient(patient_id):
    try:
        patient = Patient.get_by_id(patient_id)
        if patient:
            return jsonify({
                'id': patient['patient_id'],
                'name': patient['name'],
                'age': patient['age'],
                'mobile': patient['mobile'],
                'email': patient.get('email') or '',
                'gender': patient.get('gender') or '',
                'diabetes_duration': patient.get('diabetes_duration') or 0,
                'created_at': str(patient.get('created_at') or '')[:10],
                'total_diagnoses': Diagnosis.count_for_patient(patient_id)
            })
        return jsonify({'error': 'Patient not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/delete_diagnosis/<diagnosis_id>', methods=['DELETE'])
@login_required
def delete_diagnosis(diagnosis_id):
    try:
        if not Diagnosis.delete(diagnosis_id):
            return jsonify({'error': 'Diagnosis not found'}), 404
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/delete_patient/<patient_id>', methods=['DELETE'])
@login_required
def delete_patient(patient_id):
    try:
        if not Patient.delete(patient_id):
            return jsonify({'error': 'Patient not found'}), 404
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/stats')
@login_required
def get_stats():
    try:
        stats = Stats.get_dashboard_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/search')
@login_required
def search():
    query = request.args.get('q', '')
    try:
        patients = Patient.search(query)
        results = [
            {
                'patient_id': patient['patient_id'],
                'name': patient['name'],
                'mobile': patient['mobile'],
                'age': patient['age'],
                'latest_diagnosis': patient.get('latest_diagnosis') or 'N/A',
                'latest_date': str(patient.get('latest_date') or '')[:10] or 'N/A'
            }
            for patient in patients
        ]
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=3000)