import os
import json
from flask import Flask, render_template, request
from google import genai
from google.genai import types

app = Flask(__name__)

# --- CONFIGURATION ---
PROJECT_ID = "macro-chef-app"
LOCATION = "us-central1"

try:
    client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
    print(f"✅ Google Gen AI Client Connected")
except Exception as e:
    print(f"⚠️ Client Init Error: {e}")
    client = None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate-recipe', methods=['POST'])
def generate_recipe():
    # ... (Keep existing Recipe Logic same as before) ...
    if not client: return render_template('index.html', recipe="Error: Client not connected")
    
    ingredients = request.form.get('ingredients')
    prompt = f"""
    You are a helpful nutrition chef. User ingredients: {ingredients}.
    Create one creative recipe formatted as clean HTML (using Bootstrap classes).
    Structure: <h3>Name, <ul> Ingredients, <ol> Steps.
    """
    try:
        response = client.models.generate_content(model="gemini-2.0-flash-exp", contents=prompt)
        clean_html = response.text.replace("```html", "").replace("```", "")
        return render_template('index.html', recipe=clean_html)
    except Exception as e:
        return render_template('index.html', recipe=f"Error: {str(e)}")


# --- NEW UPDATED MATH LOGIC ---
@app.route('/calculate-macros', methods=['POST'])
def calculate_macros():
    if not client:
        return render_template('index.html', math_result="<p class='text-danger'>Error: AI Client not connected.</p>")

    try:
        # 1. Get Lists from Form
        names = request.form.getlist('names[]')
        weights = request.form.getlist('weights[]')
        final_weight = float(request.form.get('final_weight'))

        # Combine into a string for the AI to read
        # Format: "Chicken: 500g, Rice: 200g"
        ingredient_list_str = ", ".join([f"{n}: {w}g" for n, w in zip(names, weights) if n and w])

        # 2. Ask Gemini to do the Calorie Lookup (The "Database")
        prompt = f"""
        I have these raw ingredients: {ingredient_list_str}.
        
        Task: Estimate the total calories for each specific weight provided.
        Return ONLY a JSON object. No markdown. No intro text.
        
        Format:
        {{
            "items": [
                {{ "name": "Chicken", "cals": 825 }},
                {{ "name": "Rice", "cals": 700 }}
            ],
            "total_cals": 1525
        }}
        """

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json" 
            )
        )
        
        # 3. Parse AI Response
        data = json.loads(response.text)
        total_raw_cals = data['total_cals']
        items = data['items']

        # 4. Do The Rigid Math (Python side)
        # Density = Total Calories / Final Cooked Weight
        density = total_raw_cals / final_weight
        
        # 5. Generate Output HTML
        rows_html = ""
        for item in items:
            rows_html += f"<tr><td>{item['name']}</td><td>{item['cals']}</td></tr>"

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
        
        return render_template('index.html', math_result=result_html)

    except Exception as e:
        return render_template('index.html', math_result=f"<div class='alert alert-danger'>Error: {str(e)}</div>")

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))