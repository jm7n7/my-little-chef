import os
from flask import Flask

app = Flask(__name__)

@app.route('/')
def hello_world():
    return 'Macro Chef Agent is Alive! The pipeline works.'

if __name__ == "__main__":
    # This is for local testing only. 
    # When deployed, Gunicorn (in the Dockerfile) will run the app.
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))