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

app = Flask(__name__)

# --- CONFIGURATION ---
PROJECT_ID = "macro-chef-app"
LOCATION = "us-central1"

# 1. SECURITY CONFIGURATION
# Needed for session cookies (Generate a random string for this in env vars)
app.secret_key = os.environ.get('SECRET_KEY', 'dev_key_only_change_in_prod')

# Access Control List
# We split the string "user1@gmail.com,user2@gmail.com" into a Python list
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

# Email Config (Set these in Cloud Run Variables later)
SENDER_EMAIL = os.environ.get('SENDER_EMAIL')
SENDER_PASSWORD = os.environ.get('SENDER_PASSWORD')


# Initialize the Client using Vertex AI (Project Credentials)
try:
    client = genai.Client(
        vertexai=True, 
        project=PROJECT_ID, 
        location=LOCATION
    )
    print(f"✅ Google Gen AI Client Connected (Vertex AI Mode)")
except Exception as e:
    print(f"⚠️ Client Init Error: {e}")
    client = None

# --- PYDANTIC MODELS FOR STRUCTURED OUTPUT ---
class IngredientItem(BaseModel):
    name: str = Field(description="The name of the ingredient")
    cals: float = Field(description="The estimated calories for this ingredient at the specified weight")

class MacroCalculationResponse(BaseModel):
    items: List[IngredientItem] = Field(description="List of ingredients with their calorie estimates")
    total_cals: float = Field(description="Total calories across all ingredients")


# --- HELPER: LOGIN DECORATOR ---
# This function runs before every route we want to protect
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = session.get('user')
        
        # 1. Not logged in? -> Send to Google
        if not user:
            return redirect(url_for('login'))
        
        # 2. Not on the Guest List? -> 403 Error
        if user['email'] not in ALLOWED_USERS:
            return render_template('index.html', 
                                   recipe=f"<h3 class='text-danger'>⛔ Access Denied</h3><p>User {user['email']} is not authorized.</p>", 
                                   active_tab='chef')
        
        # 3. Allowed? -> Run the actual function
        return f(*args, **kwargs)
    return decorated_function


# --- AUTH ROUTES ---

@app.route('/login')
def login():
    # Sends user to Google to sign in
    redirect_uri = url_for('auth', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/auth/callback')
def auth():
    # Google sends them back here with a token
    token = google.authorize_access_token()
    user_info = token.get('userinfo')
    
    # Save user info to the session (cookie)
    session['user'] = user_info
    return redirect('/')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')


# --- APP ROUTES ---

@app.route('/')
@login_required
def index():
    # Defaults to the Chef tab
    return render_template('index.html', active_tab='chef', user=session.get('user'))

# --- TAB 1: AI CHEF LOGIC ---
@app.route('/generate-recipe', methods=['POST'])
@login_required
def generate_recipe():
    if not client: 
        return render_template('index.html', recipe="<p class='text-danger'>Error: AI Client not connected.</p>", active_tab='chef', user=session.get('user'))

    ingredients = request.form.get('ingredients')
    
    prompt = f"""
    You are a helpful nutrition chef. The user has these ingredients: {ingredients}.
    
    Create one creative recipe using these ingredients.
    Format your response as a clean HTML <div> (do not use markdown ```html tags, just the raw html).
    Use Bootstrap classes where possible (e.g., <h5 class="text-primary">).
    
    Structure:
    1. <h3> Creative Recipe Name
    2. <ul> Ingredient list (mark what might be missing)
    3. <ol> Simple step-by-step instructions
    4. <small> Estimated protein/carb balance
    """
    
    try:
        # Using 2.5 Flash for speed and creativity
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        
        # Clean up any markdown formatting if the model adds it
        clean_html = response.text.replace("```html", "").replace("```", "")
        
        return render_template('index.html', recipe=clean_html, active_tab='chef', user=session.get('user'))
        
    except Exception as e:
        return render_template('index.html', recipe=f"<p class='text-danger'>AI Error: {str(e)}</p>", active_tab='chef', user=session.get('user'))

# --- TAB 1 EXTENSION: EMAIL LOGIC ---
@app.route('/email-recipe', methods=['POST'])
@login_required
def email_recipe():
    recipient = request.form.get('user_email')
    recipe_content = request.form.get('recipe_content') # Retreive HTML from hidden field
    
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        return render_template('index.html', recipe=recipe_content, email_status="⚠️ Server Error: Email credentials not configured.", active_tab='chef', user=session.get('user'))

    try:
        # Create the email
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = recipient
        msg['Subject'] = "🍽️ Your Recipe from Chez Macro Chef"

        # Attach the HTML body
        email_body = f"""
        <html>
            <body>
                <h2>Bon Appétit!</h2>
                <p>Here is the recipe you generated:</p>
                <hr>
                {recipe_content}
                <hr>
                <p><small>Generated by Macro Chef AI Agent</small></p>
            </body>
        </html>
        """
        msg.attach(MIMEText(email_body, 'html'))

        # Send via Gmail SMTP
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls() # Secure the connection
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()

        return render_template('index.html', recipe=recipe_content, email_status="✅ Recipe sent successfully!", active_tab='chef', user=session.get('user'))

    except Exception as e:
        return render_template('index.html', recipe=recipe_content, email_status=f"❌ Failed to send: {str(e)}", active_tab='chef', user=session.get('user'))

# --- TAB 2: MACRO MATH LOGIC ---
@app.route('/calculate-macros', methods=['POST'])
@login_required
def calculate_macros():
    # Force Math tab to stay active
    if not client:
        return render_template('index.html', math_result="<p class='text-danger'>Error: AI Client not connected.</p>", active_tab='math', user=session.get('user'))

    try:
        # 1. Get Lists from Form
        names = request.form.getlist('names[]')
        weights = request.form.getlist('weights[]')
        final_weight_str = request.form.get('final_weight')
        
        if not final_weight_str:
            return render_template('index.html', math_result="<div class='alert alert-danger'>Please enter a final weight.</div>", active_tab='math', user=session.get('user'))
            
        final_weight = float(final_weight_str)

        # Combine into a string for the AI to read
        ingredient_list_str = ", ".join([f"{n}: {w}g" for n, w in zip(names, weights) if n and w])

        # 2. Ask Gemini to do the Calorie Lookup (The "Database")
        prompt = f"""
        I have these raw ingredients: {ingredient_list_str}.
        
        Task: Use the Internet to estimate the total calories for each specific weight provided.
        Typically, you search for how many calories are in the raw food per 100 grams.
        You take the user provided weight, and multiply that with the amount of calories per 100 grams, then divide by 100.
        This formula gives you the amount of calories of that ingredient for the user.
        """

        # Use Pydantic model for structured output - more robust than JSON parsing
        response = client.models.generate_content(
            model="gemini-2.5-flash", 
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(
                    google_search=types.GoogleSearch()
                    )
                ],
                response_mime_type="application/json",
                response_schema=MacroCalculationResponse,
            )
        )
        
        # 3. Parse AI Response using Pydantic
        if not hasattr(response, 'parsed') or response.parsed is None:
            # Fallback: try to parse manually if .parsed is not available
            if not response.text or response.text.strip() == "":
                raise ValueError("AI returned an empty response. Please try again.")
            try:
                response_data = json.loads(response.text)
                validated_data = MacroCalculationResponse(**response_data)
            except json.JSONDecodeError as e:
                raise ValueError(f"AI response was not valid JSON: {str(e)}. Response: {response.text[:200]}")
            except Exception as e:
                raise ValueError(f"Failed to validate AI response: {str(e)}. Response: {response.text[:200]}")
        else:
            # Use the parsed Pydantic model directly
            validated_data = response.parsed
        
        total_raw_cals = validated_data.total_cals
        items = validated_data.items

        # 4. Do The Rigid Math (Python side)
        # Avoid division by zero
        density = total_raw_cals / final_weight if final_weight > 0 else 0
        
        # 5. Generate Output HTML
        rows_html = ""
        for item in items:
            rows_html += f"<tr><td>{item.name}</td><td>{int(item.cals)}</td></tr>"

        result_html = f"""
        <div class="alert alert-success">
            <h4 class="alert-heading">📊 Analysis Complete</h4>
            <table class="table table-sm table-borderless">
                <thead><tr><th>Ingredient</th><th>Est. Cals</th></tr></thead>
                <tbody>{rows_html}</tbody>
                <tfoot class="border-top"><tr><th>Total Raw</th><th>{total_raw_cals}</th></tr></tfoot>
            </table>
            
            <hr>
            <div class="text-center">
                <h2 style="color: #2A9D8F;">{density:.3f}</h2>
                <p class="text-muted">Calories per Gram</p>
            </div>
            
            <div class="bg-white p-3 rounded border">
                <strong>Serving Cheat Sheet:</strong>
                <ul class="mb-0">
                    <li>150g Serving = <strong>{round(density * 150)}</strong> cals</li>
                    <li>200g Serving = <strong>{round(density * 200)}</strong> cals</li>
                    <li>300g Serving = <strong>{round(density * 300)}</strong> cals</li>
                </ul>
            </div>
        </div>
        """
        
        return render_template('index.html', math_result=result_html, active_tab='math', user=session.get('user'))

    except Exception as e:
        return render_template('index.html', math_result=f"<div class='alert alert-danger'>Error: {str(e)}</div>", active_tab='math', user=session.get('user'))

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))