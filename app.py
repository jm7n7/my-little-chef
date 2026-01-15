import os
from flask import Flask, render_template, request
import vertexai
from vertexai.generative_models import GenerativeModel

app = Flask(__name__)

# --- CONFIGURATION ---
# TODO: Double check this matches your actual Project ID
PROJECT_ID = "macro-chef-app" 
LOCATION = "us-central1"

# Initialize Vertex AI
# We wrap this in a try/except so the app doesn't crash locally if credentials aren't found
try:
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    model = GenerativeModel("gemini-1.5-flash-001")
    print("✅ Vertex AI Connected")
except Exception as e:
    print(f"⚠️ Vertex AI Error: {e}")
    model = None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate-recipe', methods=['POST'])
def generate_recipe():
    if not model:
        return render_template('index.html', recipe="<p class='text-danger'>Error: AI Model not connected.</p>")

    ingredients = request.form.get('ingredients')
    
    # PROMPT ENGINEERING
    # We ask for HTML directly to make the frontend look professional.
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
        response = model.generate_content(prompt)
        # We use .text to get the string, stripping any accidental markdown code blocks
        clean_html = response.text.replace("```html", "").replace("```", "")
        return render_template('index.html', recipe=clean_html)
    except Exception as e:
        return render_template('index.html', recipe=f"<p>AI Error: {str(e)}</p>")

@app.route('/calculate-macros', methods=['POST'])
def calculate_macros():
    try:
        # Get data from form
        raw_cals = float(request.form.get('raw_cals'))
        cooked_weight = float(request.form.get('cooked_weight'))
        
        if cooked_weight == 0:
            return render_template('index.html', error="Cooked weight cannot be zero.")

        # 1. Calculate Density (Calories per 1 gram)
        density = raw_cals / cooked_weight
        
        # 2. Generate Cheat Sheet
        s100 = round(density * 100)
        s200 = round(density * 200)
        s300 = round(density * 300)
        
        # Format the result HTML
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