from flask import Flask, jsonify, Response, request
from flask_cors import CORS
import requests
import os

app = Flask(__name__)
application = app
handler = app
CORS(app)

CEIPAL_API_KEY  = 'f10390a9b03e7a58669692d8e0993899d15f57f5984d1de7e1'
CEIPAL_EMAIL    = 'it@inteliblue.com'
CEIPAL_PASSWORD = 'Inteliblue@2026'
CEIPAL_BASE     = 'https://api.ceipal.com/v2'

ceipal_token = None

def get_ceipal_token():
    global ceipal_token
    url = f"{CEIPAL_BASE}/createAuthtoken/"
    res = requests.post(url, json={
        'email': CEIPAL_EMAIL,
        'password': CEIPAL_PASSWORD,
        'apiKey': CEIPAL_API_KEY
    }, headers={'Content-Type': 'application/json'}, timeout=15)
    if res.status_code == 200 and res.text.strip():
        data = res.json()
        ceipal_token = data.get('access_token')
        return ceipal_token
    return None

def ceipal_get(endpoint, params=None):
    global ceipal_token
    if not ceipal_token:
        get_ceipal_token()
    url = f"{CEIPAL_BASE}/{endpoint}"
    headers = {'Authorization': f'Bearer {ceipal_token}', 'Content-Type': 'application/json'}
    res = requests.get(url, headers=headers, params=params, timeout=15)
    if res.status_code == 401:
        get_ceipal_token()
        headers['Authorization'] = f'Bearer {ceipal_token}'
        res = requests.get(url, headers=headers, params=params, timeout=15)
    if res.text.strip():
        return res.json()
    return {}

def parse_skills(skills_raw):
    if not skills_raw:
        return []
    if isinstance(skills_raw, list):
        return [s.strip().lower() for s in skills_raw if s.strip()]
    return [s.strip().lower() for s in str(skills_raw).split(',') if s.strip()]

def compute_score(candidate_skills, job_skills):
    if not candidate_skills or not job_skills:
        return None  # Can't compute without both
    matched = sum(1 for js in job_skills if any(
        js in cs or cs in js for cs in candidate_skills
    ))
    return round((matched / len(job_skills)) * 100)

@app.route('/')
def index():
    with open(os.path.join(os.path.dirname(__file__), 'index.html'), 'r') as f:
        return Response(f.read(), mimetype='text/html')

@app.route('/api/debug')
def debug():
    try:
        token = get_ceipal_token()
        return jsonify({'token_ok': bool(token)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/jobs')
def get_jobs():
    try:
        data = ceipal_get('getJobPostingsList/')
        jobs = data.get('data') or data.get('results') or []
        mapped = []
        for j in jobs:
            mapped.append({
                'id': j.get('id', ''),
                'title': j.get('position_title') or j.get('public_job_title', ''),
                'location': f"{j.get('city','')} {j.get('state','')}".strip(),
                'type': j.get('employment_type', 'Full-Time'),
                'auth': j.get('work_authorization', ''),
                'status': j.get('job_status', ''),
                'skills': parse_skills(j.get('skills', ''))
            })
        return jsonify({'success': True, 'jobs': mapped})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/job/<job_id>')
def get_job_details(job_id):
    try:
        data = ceipal_get(f'getJobPostingDetails/{job_id}')
        skills = parse_skills(data.get('skills', ''))
        return jsonify({
            'success': True,
            'id': data.get('id', ''),
            'title': data.get('position_title') or data.get('public_job_title', ''),
            'location': f"{data.get('city','')} {data.get('state','')}".strip(),
            'type': data.get('employment_type', 'Full-Time'),
            'auth': data.get('work_authorization', 'All authorizations'),
            'experience': data.get('experience', ''),
            'skills': skills,
            'description': data.get('requisition_description') or data.get('public_job_desc', '')
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/candidates')
def get_candidates():
    try:
        job_id = request.args.get('job_id')
        
        # Fetch job details if job_id provided
        job_skills = []
        job_info = {}
        if job_id:
            job_data = ceipal_get(f'getJobPostingDetails/{job_id}')
            job_skills = parse_skills(job_data.get('skills', ''))
            job_info = {
                'title': job_data.get('position_title') or job_data.get('public_job_title', 'Open Position'),
                'location': f"{job_data.get('city','')} {job_data.get('state','')}".strip(),
                'type': job_data.get('employment_type', 'Full-Time'),
                'auth': job_data.get('work_authorization', 'All authorizations'),
                'experience': job_data.get('experience', '3+ years'),
                'skills': job_skills,
                'description': job_data.get('requisition_description') or job_data.get('public_job_desc', '')
            }

        # Fetch candidates
        data = ceipal_get('getApplicantsList/')
        all_candidates = data.get('data') or data.get('results') or (data if isinstance(data, list) else [])

        mapped = []
        for c in all_candidates:
            candidate_skills = parse_skills(c.get('skills') or c.get('skill_set', ''))

            # Compute real score if job selected, else profile completeness
            if job_id and job_skills:
                score = compute_score(candidate_skills, job_skills)
                if score is None:
                    score = 70  # default if no skills data
            else:
                # Profile completeness score
                score = 60
                if c.get('mobile_number') or c.get('other_phone'): score += 12
                if c.get('email'): score += 10
                if c.get('city') or c.get('state'): score += 8
                if c.get('total_experience'): score += 8
                if candidate_skills: score += 7

            # Filter out below 70%
            if score < 70:
                continue

            mapped.append({
                'id': c.get('id') or c.get('applicant_id', ''),
                'name': f"{c.get('firstname','')} {c.get('lastname','')}".strip() or c.get('consultant_name', 'Unknown'),
                'email': c.get('email') or c.get('email_address_1', ''),
                'phone': c.get('mobile_number') or c.get('other_phone', ''),
                'location': f"{c.get('city','')} {c.get('state','')}".strip(),
                'status': c.get('applicant_status', ''),
                'source': c.get('source') or 'Ceipal',
                'skills': candidate_skills,
                'experience': str(c.get('total_experience', '')),
                'job_title': c.get('job_title') or c.get('applicant_status') or 'Candidate',
                'matched_at': c.get('created_at', ''),
                'score': min(score, 100),
                'job': job_info if job_id else {
                    'title': 'Select a job to see match score',
                    'location': '',
                    'type': 'Full-Time',
                    'auth': 'All authorizations',
                    'experience': '3+ years',
                    'skills': [],
                    'description': 'Select a job requisition from the dropdown to see accurate match scores.'
                }
            })

        # Sort by score descending
        mapped.sort(key=lambda x: x['score'], reverse=True)

        return jsonify({'success': True, 'candidates': mapped, 'total': len(mapped), 'job_skills_count': len(job_skills)})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/requisitions')
def get_requisitions():
    try:
        data = ceipal_get('getJobPostingsList/')
        jobs = data.get('data') or data.get('results') or []
        mapped = [{'id': j.get('id',''), 'title': j.get('position_title') or j.get('public_job_title',''), 'status': j.get('job_status','')} for j in jobs]
        return jsonify({'success': True, 'requisitions': mapped})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
