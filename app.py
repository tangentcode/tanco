from flask import Flask, render_template, make_response, abort
import json
import sqlite3

SDB_PATH = 'rogo.sdb'  # TODO: make this configurable
app = Flask(__name__)
ok = None

def rel(sql):
    dbc = sqlite3.connect(SDB_PATH)
    cur = dbc.execute(sql)
    cols = [x[0] for x in cur.description]
    return [{k: v for k, v in zip(cols, vals)}
            for vals in cur.fetchall()]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')


def list_challenges_data():
    return rel("""
        select c.name, c.title,
          (select count(*) from tests t 
            where t.chal_id = c.id) as num_tests
        from challenges c""")

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
            if x['name'] == name]
    abort(404) if not data else ok
    return render_template('challenge.html', data=data[0])


if __name__ == '__main__':
    app.run()
