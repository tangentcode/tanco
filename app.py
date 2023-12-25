from flask import Flask, render_template, make_response, abort
import json

app = Flask(__name__)


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')


def list_challenges_data():
    return [dict(id=x[0], title=x[1], num_tests=x[2]) for x in [
        ('lt', 'learntris', 10),
        ('rogo', 'rogo client test suite', 5003030),
        ('other', 'some other course', 4)]]

@app.route('/c:json')
def list_challenges_json():
    res = make_response(json.dumps(list_challenges_data()))
    res.headers['content-type'] = 'application/json'
    return res


@app.route('/c')
def list_challenges():
    return render_template('challenges.html',
                           data=list_challenges_data())

@app.route('/c/<name>')
def show_challenge(name):
    data = [x for x in list_challenges_data()
            if x['id'] == name]
    if not data: abort(404)
    return render_template('challenge.html', data=data[0])



if __name__ == '__main__':
    app.run()
