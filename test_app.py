from flask import Flask, render_template
app = Flask(__name__)
app.secret_key = 'test'

@app.route('/')
def index():
    return "Flask 正常运行"

@app.route('/test-dashboard')
def test_dashboard():
    return render_template('dashboard.html')

if __name__ == '__main__':
    app.run(debug=True)