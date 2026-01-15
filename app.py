import os
import json
import smtplib
from functools import wraps
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, render_template, request, session, redirect, url_for
from google import genai
from google.genai import types
from authlib.integrations.flask_client import OAuth
from pydantic import BaseModel, Field
from typing import List
# NEW IMPORT: Fixes the HTTP/HTTPS confusion on Cloud Run
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)

# --- CRITICAL FIX FOR CLOUD RUN OAUTH ---
# This tells Flask to trust the HTTPS headers coming from Cloud Run
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# --- CONFIGURATION ---
PROJECT_ID = "macro-chef-app"
LOCATION = "us-central1"

# 1. SECURITY CONFIGURATION
app.secret_key = os.environ.get('SECRET_KEY', 'dev_key_only_change_in_prod')

# Enforce secure cookies (fixes the redirect loop)
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
)

# Access Control List
ALLOWED_USERS = os.environ.get('ALLOWED_USERS', '').split(',')

# OAuth Config
app.config['GOOGLE_CLIENT_ID'] = os.environ.get('GOOGLE_CLIENT_ID')
app.config['GOOGLE_CLIENT_SECRET'] = os.environ.get('GOOGLE_CLIENT_SECRET')

oauth = OAuth(app)
google = oauth.register(
    name='google',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# Email Config
SENDER_EMAIL = os.environ.get('SENDER_EMAIL')
SENDER_PASSWORD = os.environ.get('SENDER_PASSWORD')

# Initialize Vertex AI
try:
    client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
    print(f"✅ Google Gen AI Client Connected")
except Exception as e:
    print(f"⚠️ Client Init Error: {e}")
    client = None

# --- PYDANTIC MODELS ---
class IngredientItem(BaseModel):
    name: str = Field(description="The name of the ingredient")
    cals: float = Field(description="The estimated calories for this ingredient at the specified weight")

class MacroCalculationResponse(BaseModel):
    items: List[IngredientItem] = Field(description="List of ingredients with their calorie estimates")
    total_cals: float = Field(description="Total calories across all ingredients")

# --- LOGIN DECORATOR ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = session.get('user')
        if not user:
            return redirect(url_for('login'))
        if user['email'] not in ALLOWED_USERS:
            return render_template('index.html', 
                                   recipe=f"<h3 class='text-danger'>⛔ Access Denied</h3><p>User {user['email']} is not authorized.</p>", 
                                   active_tab='chef', user=None)
        return f(*args, **kwargs)
    return decorated_function

# --- ROUTES ---

@app.route('/login')
def login():
    # Force HTTPS for the callback URL
    redirect_uri = url_for('auth', _external=True, _scheme='https')
    return google.authorize_redirect(redirect_uri)

@app.route('/auth/callback')
def auth():
    token = google.authorize_access_token()
    user_info = token.get('userinfo')
    session['user'] = user_info
    return redirect('/')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

@app.route('/')
@login_required
def index():
    return render_template('index.html', active_tab='chef', user=session.get('user'))

@app.route('/generate-recipe', methods=['POST'])
@login_required
def generate_recipe():
    if not client: return render_template('index.html', recipe="Error: AI Client not connected", active_tab='chef', user=session.get('user'))
    ingredients = request.form.get('ingredients')
    prompt = f"""
    You are a helpful nutrition chef. User ingredients: {ingredients}.
    Create one creative recipe formatted as clean HTML (using Bootstrap classes).
    Structure: <h3>Name, <ul> Ingredients, <ol> Steps.
    """
    try:
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        clean_html = response.text.replace("```html", "").replace("```", "")
        return render_template('index.html', recipe=clean_html, active_tab='chef', user=session.get('user'))
    except Exception as e:
        return render_template('index.html', recipe=f"AI Error: {str(e)}", active_tab='chef', user=session.get('user'))

@app.route('/email-recipe', methods=['POST'])
@login_required
def email_recipe():
    recipient = request.form.get('user_email')
    recipe_content = request.form.get('recipe_content')
    
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        return render_template('index.html', recipe=recipe_content, email_status="⚠️ Email creds missing.", active_tab='chef', user=session.get('user'))

    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = recipient
        msg['Subject'] = "🍽️ Your Recipe from Chez Macro Chef"
        email_body = f"<html><body>{recipe_content}<hr><small>Generated by Macro Chef</small></body></html>"
        msg.attach(MIMEText(email_body, 'html'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        return render_template('index.html', recipe=recipe_content, email_status="✅ Sent!", active_tab='chef', user=session.get('user'))
    except Exception as e:
        return render_template('index.html', recipe=recipe_content, email_status=f"❌ Error: {str(e)}", active_tab='chef', user=session.get('user'))

@app.route('/calculate-macros', methods=['POST'])
@login_required
def calculate_macros():
    if not client: return render_template('index.html', math_result="Error: Client not connected", active_tab='math', user=session.get('user'))

    try:
        names = request.form.getlist('names[]')
        weights = request.form.getlist('weights[]')
        final_weight_str = request.form.get('final_weight')
        if not final_weight_str: return render_template('index.html', math_result="Enter final weight", active_tab='math', user=session.get('user'))
            
        final_weight = float(final_weight_str)
        ingredient_list_str = ", ".join([f"{n}: {w}g" for n, w in zip(names, weights) if n and w])

        prompt = f"""
        Ingredients: {ingredient_list_str}.
        Task: Use Google Search to estimate calories.
        """
        response = client.models.generate_content(
            model="gemini-2.5-flash", 
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                response_mime_type="application/json",
                response_schema=MacroCalculationResponse,
            )
        )
        
        if not hasattr(response, 'parsed') or response.parsed is None:
            if not response.text: raise ValueError("Empty AI response")
            validated_data = MacroCalculationResponse(**json.loads(response.text))
        else:
            validated_data = response.parsed
        
        total_raw_cals = validated_data.total_cals
        items = validated_data.items
        density = total_raw_cals / final_weight if final_weight > 0 else 0
        
        rows_html = "".join([f"<tr><td>{i.name}</td><td>{int(i.cals)}</td></tr>" for i in items])
        result_html = f"""
        <div class="alert alert-success">
            <h4 class="alert-heading">📊 Result</h4>
            <table class="table table-sm"><thead><tr><th>Item</th><th>Cals</th></tr></thead><tbody>{rows_html}</tbody><tfoot><tr><th>Total</th><th>{total_raw_cals}</th></tr></tfoot></table>
            <hr><h2 class="text-center" style="color:#2A9D8F;">{density:.3f} <small class="text-muted" style="font-size:0.4em">cal/g</small></h2>
        </div>
        """
        return render_template('index.html', math_result=result_html, active_tab='math', user=session.get('user'))

    except Exception as e:
        return render_template('index.html', math_result=f"Error: {str(e)}", active_tab='math', user=session.get('user'))

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))