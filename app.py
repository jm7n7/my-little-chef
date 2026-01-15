import os
from flask import Flask, render_template, request
from google import genai
from google.genai import types

app = Flask(__name__)

# --- CONFIGURATION ---
# PROJECT ID is required for Vertex AI (ADC) mode
PROJECT_ID = "macro-chef-app"
LOCATION = "us-central1"

# Initialize the Client using Vertex AI (Project Credentials)
# This uses the Cloud Run Service Account automatically. No API Key needed.
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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate-recipe', methods=['POST'])
def generate_recipe():
    if not client:
        return render_template('index.html', recipe="<p class='text-danger'>Error: AI Client not connected.</p>")

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
        # SYNTAX UPDATE: The new SDK uses client.models.generate_content
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        
        # Clean up any markdown formatting if the model adds it
        clean_html = response.text.replace("```html", "").replace("```", "")
        return render_template('index.html', recipe=clean_html)
        
    except Exception as e:
        return render_template('index.html', recipe=f"<p class='text-danger'>AI Error: {str(e)}</p>")

@app.route('/calculate-macros', methods=['POST'])
def calculate_macros():
    try:
        raw_cals = float(request.form.get('raw_cals'))
        cooked_weight = float(request.form.get('cooked_weight'))
        
        if cooked_weight == 0:
            return render_template('index.html', error="Cooked weight cannot be zero.")

        density = raw_cals / cooked_weight
        s100 = round(density * 100)
        s200 = round(density * 200)
        s300 = round(density * 300)
        
        result_html = f"""
        <div class="alert alert-success">
            <h4 class="alert-heading">📊 Results</h4>
            <p><strong>Calorie Density:</strong> {density:.3f} cal/gram</p>
            <hr>
            <h5>Serving Cheat Sheet:</h5>
            <ul>
                <li><strong>100g</strong> serving = {s100} calories</li>
                <li><strong>200g</strong> serving = {s200} calories</li>
                <li><strong>300g</strong> serving = {s300} calories</li>
            </ul>
            <p class="mb-0 text-muted"><small>Total Batch: {int(raw_cals)} cal / {int(cooked_weight)}g</small></p>
        </div>
        """
        
        return render_template('index.html', math_result=result_html)
        
    except ValueError:
        return render_template('index.html', error="Please enter valid numbers.")

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))