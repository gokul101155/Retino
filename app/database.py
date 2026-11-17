import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime


DATABASE_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'retina_ai.db')


@contextmanager
def _connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_database():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    with _connection() as connection:
        connection.executescript('''
            CREATE TABLE IF NOT EXISTS patients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id VARCHAR(20) NOT NULL UNIQUE,
                name VARCHAR(100) NOT NULL,
                age INTEGER NOT NULL,
                mobile VARCHAR(15) NOT NULL UNIQUE,
                email VARCHAR(100),
                gender VARCHAR(10),
                diabetes_duration INTEGER,
                created_at DATETIME,
                updated_at DATETIME
            );
            CREATE TABLE IF NOT EXISTS diagnoses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id VARCHAR(20) NOT NULL,
                date DATETIME,
                diagnosis_class VARCHAR(50) NOT NULL,
                severity_index INTEGER NOT NULL,
                progression_risk FLOAT NOT NULL,
                probabilities JSON NOT NULL,
                image_path VARCHAR(500),
                notes TEXT,
                analysis_duration FLOAT,
                model_version VARCHAR(50),
                FOREIGN KEY (patient_id) REFERENCES patients (patient_id)
            );
            CREATE INDEX IF NOT EXISTS ix_diagnoses_patient_id ON diagnoses (patient_id);
            CREATE INDEX IF NOT EXISTS ix_diagnoses_date ON diagnoses (date);
            CREATE INDEX IF NOT EXISTS ix_diagnoses_class ON diagnoses (diagnosis_class);
        ''')


def _as_dict(row):
    return dict(row) if row else None


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


class Patient:
    @staticmethod
    def create(patient_data):
        patient_id = f"PID-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.utcnow().isoformat(sep=' ', timespec='seconds')
        with _connection() as connection:
            connection.execute(
                '''INSERT INTO patients
                   (patient_id, name, age, mobile, email, gender, diabetes_duration, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    patient_id,
                    patient_data.get('name') or 'Unknown',
                    _as_int(patient_data.get('age')),
                    patient_data.get('mobile') or '',
                    patient_data.get('email') or '',
                    patient_data.get('gender') or '',
                    _as_int(patient_data.get('diabetes_duration')),
                    now,
                    now,
                ),
            )
        return patient_id

    @staticmethod
    def find_by_mobile(mobile):
        with _connection() as connection:
            row = connection.execute(
                'SELECT * FROM patients WHERE mobile = ?', (mobile,)
            ).fetchone()
        return _as_dict(row)

    @staticmethod
    def get_by_id(patient_id):
        with _connection() as connection:
            row = connection.execute(
                'SELECT * FROM patients WHERE patient_id = ?', (patient_id,)
            ).fetchone()
        return _as_dict(row)

    @staticmethod
    def update(patient_id, update_data):
        fields = ('name', 'age', 'email', 'gender', 'diabetes_duration')
        values = {field: update_data[field] for field in fields if field in update_data}
        if not values:
            return False
        values['updated_at'] = datetime.utcnow().isoformat(sep=' ', timespec='seconds')
        assignments = ', '.join(f'{field} = ?' for field in values)
        with _connection() as connection:
            cursor = connection.execute(
                f'UPDATE patients SET {assignments} WHERE patient_id = ?',
                (*values.values(), patient_id),
            )
        return cursor.rowcount > 0

    @staticmethod
    def count_diagnoses(patient_id):
        with _connection() as connection:
            row = connection.execute(
                'SELECT COUNT(*) AS count FROM diagnoses WHERE patient_id = ?',
                (patient_id,),
            ).fetchone()
        return row['count']

    @staticmethod
    def delete(patient_id):
        with _connection() as connection:
            connection.execute('DELETE FROM diagnoses WHERE patient_id = ?', (patient_id,))
            cursor = connection.execute(
                'DELETE FROM patients WHERE patient_id = ?', (patient_id,)
            )
        return cursor.rowcount > 0

    @staticmethod
    def search(query, limit=20):
        pattern = f'%{query}%'
        with _connection() as connection:
            rows = connection.execute(
                '''SELECT p.*,
                          (SELECT diagnosis_class FROM diagnoses d
                           WHERE d.patient_id = p.patient_id
                           ORDER BY d.date DESC, d.id DESC LIMIT 1) AS latest_diagnosis,
                          (SELECT date FROM diagnoses d
                           WHERE d.patient_id = p.patient_id
                           ORDER BY d.date DESC, d.id DESC LIMIT 1) AS latest_date
                   FROM patients p
                   WHERE p.name LIKE ? COLLATE NOCASE
                      OR p.mobile LIKE ? COLLATE NOCASE
                      OR p.patient_id LIKE ? COLLATE NOCASE
                   ORDER BY p.name COLLATE NOCASE
                   LIMIT ?''',
                (pattern, pattern, pattern, limit),
            ).fetchall()
        return [dict(row) for row in rows]


class Diagnosis:
    @staticmethod
    def create(patient_id, analysis_result, image_path=None, notes='Automated Analysis'):
        now = datetime.utcnow().isoformat(sep=' ', timespec='seconds')
        with _connection() as connection:
            cursor = connection.execute(
                '''INSERT INTO diagnoses
                   (patient_id, date, diagnosis_class, severity_index, progression_risk,
                    probabilities, image_path, notes, model_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    patient_id,
                    now,
                    analysis_result['class'],
                    analysis_result['severity_index'],
                    analysis_result['progression_risk'],
                    json.dumps(analysis_result['probabilities']),
                    image_path,
                    notes,
                    'v3.0',
                ),
            )
            diagnosis_id = cursor.lastrowid
        return str(diagnosis_id)

    @staticmethod
    def get_all(limit=100, skip=0):
        with _connection() as connection:
            rows = connection.execute(
                '''SELECT d.*, p.name AS patient_name, p.age AS patient_age,
                          p.mobile AS patient_mobile, p.email AS patient_email,
                          p.gender AS patient_gender
                   FROM diagnoses d
                   LEFT JOIN patients p ON p.patient_id = d.patient_id
                   ORDER BY d.date DESC, d.id DESC
                   LIMIT ? OFFSET ?''',
                (limit, skip),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def count_all():
        with _connection() as connection:
            row = connection.execute('SELECT COUNT(*) AS count FROM diagnoses').fetchone()
        return row['count']

    @staticmethod
    def count_for_patient(patient_id):
        with _connection() as connection:
            row = connection.execute(
                'SELECT COUNT(*) AS count FROM diagnoses WHERE patient_id = ?',
                (patient_id,),
            ).fetchone()
        return row['count']

    @staticmethod
    def get_by_id(diagnosis_id):
        try:
            numeric_id = int(diagnosis_id)
        except (TypeError, ValueError):
            return None
        with _connection() as connection:
            row = connection.execute(
                '''SELECT d.*, p.name AS patient_name, p.age AS patient_age,
                          p.mobile AS patient_mobile, p.email AS patient_email,
                          p.gender AS patient_gender
                   FROM diagnoses d
                   LEFT JOIN patients p ON p.patient_id = d.patient_id
                   WHERE d.id = ?''',
                (numeric_id,),
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def get_image(diagnosis_id):
        diagnosis = Diagnosis.get_by_id(diagnosis_id)
        return diagnosis.get('image_path') if diagnosis else None

    @staticmethod
    def delete(diagnosis_id):
        try:
            numeric_id = int(diagnosis_id)
        except (TypeError, ValueError):
            return False
        with _connection() as connection:
            row = connection.execute(
                'SELECT image_path FROM diagnoses WHERE id = ?', (numeric_id,)
            ).fetchone()
            if not row:
                return False
            connection.execute('DELETE FROM diagnoses WHERE id = ?', (numeric_id,))
        image_path = row['image_path']
        if image_path and os.path.isfile(image_path):
            os.remove(image_path)
        return True

    @staticmethod
    def to_dict(diagnosis):
        if not diagnosis:
            return None
        date_value = diagnosis.get('date') or ''
        try:
            date_value = datetime.fromisoformat(date_value).strftime('%Y-%m-%d %H:%M')
        except (TypeError, ValueError):
            date_value = str(date_value)
        return {
            'id': str(diagnosis['id']),
            'patient_id': diagnosis.get('patient_id', ''),
            'date': date_value,
            'diagnosis': diagnosis.get('diagnosis_class', ''),
            'severity_index': diagnosis.get('severity_index', 0),
            'risk': diagnosis.get('progression_risk', 0),
            'probabilities': json.loads(diagnosis.get('probabilities') or '{}'),
            'image_filename': os.path.basename(diagnosis['image_path'])
            if diagnosis.get('image_path') else None,
            'notes': diagnosis.get('notes', ''),
            'patient': {
                'name': diagnosis.get('patient_name') or 'Unknown',
                'age': diagnosis.get('patient_age') or 'N/A',
                'mobile': diagnosis.get('patient_mobile') or 'N/A',
                'email': diagnosis.get('patient_email') or '',
                'gender': diagnosis.get('patient_gender') or '',
            },
        }


class Stats:
    @staticmethod
    def get_dashboard_stats():
        now = datetime.utcnow()
        month_index = now.year * 12 + now.month - 1 - 5
        start_year, start_month_index = divmod(month_index, 12)
        start_date = datetime(start_year, start_month_index + 1, 1).strftime('%Y-%m-%d')
        with _connection() as connection:
            total_patients = connection.execute(
                'SELECT COUNT(*) FROM patients'
            ).fetchone()[0]
            total_diagnoses = connection.execute(
                'SELECT COUNT(*) FROM diagnoses'
            ).fetchone()[0]
            class_rows = connection.execute(
                '''SELECT diagnosis_class, COUNT(*) AS count
                   FROM diagnoses GROUP BY diagnosis_class ORDER BY count DESC'''
            ).fetchall()
            month_rows = connection.execute(
                '''SELECT strftime('%Y-%m', date) AS month, COUNT(*) AS count
                   FROM diagnoses
                   WHERE date >= ?
                   GROUP BY month
                   ORDER BY month''',
                (start_date,),
            ).fetchall()
        return {
            'total_patients': total_patients,
            'total_diagnoses': total_diagnoses,
            'class_distribution': {
                row['diagnosis_class']: row['count'] for row in class_rows
            },
            'monthly_trend': [
                {'month': row['month'], 'count': row['count']} for row in month_rows
            ],
        }
