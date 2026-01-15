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
    # Default to Chef tab on first load
    return render_template('index.html', active_tab='chef')

@app.route('/generate-recipe', methods=['POST'])
def generate_recipe():
    if not client: return render_template('index.html', recipe="Error: Client not connected", active_tab='chef')
    
    ingredients = request.form.get('ingredients')
    prompt = f"""
    You are a helpful nutrition chef. User ingredients: {ingredients}.
    Create one creative recipe formatted as clean HTML (using Bootstrap classes).
    Structure: <h3>Name, <ul> Ingredients, <ol> Steps.
    """
    try:
        response = client.models.generate_content(model="gemini-2.0-flash-exp", contents=prompt)
        clean_html = response.text.replace("```html", "").replace("```", "")
        # STAY ON CHEF TAB
        return render_template('index.html', recipe=clean_html, active_tab='chef')
    except Exception as e:
        return render_template('index.html', recipe=f"Error: {str(e)}", active_tab='chef')


@app.route('/calculate-macros', methods=['POST'])
def calculate_macros():
    # FORCE MATH TAB TO BE ACTIVE
    if not client:
        return render_template('index.html', math_result="<p class='text-danger'>Error: AI Client not connected.</p>", active_tab='math')

    try:
        names = request.form.getlist('names[]')
        weights = request.form.getlist('weights[]')
        final_weight_str = request.form.get('final_weight')

        if not final_weight_str:
            return render_template('index.html', math_result="<div class='alert alert-danger'>Please enter a final weight.</div>", active_tab='math')
            
        try:
            final_weight = float(final_weight_str)
        except Exception:
            return render_template('index.html', math_result="<div class='alert alert-danger'>Invalid final weight. Please enter a number.</div>", active_tab='math')

        ingredient_list_str = ", ".join([f"{n}: {w}g" for n, w in zip(names, weights) if n and w])

        prompt = f"""
        I have these raw ingredients: {ingredient_list_str}.
        Task: Estimate the total calories of each ingredient for the specific weight provided.
        Return ONLY a JSON object. No markdown.
        Format: {{ "items": [ {{ "name": "Chicken", "cals": 825 }} ], "total_cals": 1525 }}
        """

        response = client.models.generate_content(
            model="gemini-2.5-flash", 
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        
        data = json.loads(response.text)
        total_raw_cals = data['total_cals']

        # Ensure total_raw_cals is numeric
        try:
            total_raw_cals = float(total_raw_cals)
        except Exception:
            return render_template(
                'index.html', 
                math_result=f"<div class='alert alert-danger'>Error: Returned calories value is not a number: {total_raw_cals}</div>", 
                active_tab='math'
            )

        items = data['items']

        density = total_raw_cals / final_weight if final_weight > 0 else 0
        
        rows_html = ""
        for item in items:
            # Ensure cals is displayed as number
            try:
                cals_val = float(item['cals'])
            except Exception:
                cals_val = item['cals']
            rows_html += f"<tr><td>{item['name']}</td><td>{cals_val}</td></tr>"

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
        
        # STAY ON MATH TAB
        return render_template('index.html', math_result=result_html, active_tab='math')

    except Exception as e:
        return render_template('index.html', math_result=f"<div class='alert alert-danger'>Error: {str(e)}</div>", active_tab='math')

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))