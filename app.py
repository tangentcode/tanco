import flask
import sqlite3

SDB_PATH = 'rogo.sdb'  # TODO: make this configurable
app = flask.Flask(__name__)
ok = None


def rel(sql):
    dbc = sqlite3.connect(SDB_PATH)
    cur = dbc.execute(sql)
    cols = [x[0] for x in cur.description]
    return [{k: v for k, v in zip(cols, vals)}
            for vals in cur.fetchall()]


@app.route('/')
def index():
    return flask.render_template('index.html')


@app.route('/about')
def about():
    return flask.render_template('about.html')


def list_challenges_data():
    return rel("""
        select c.name, c.title,
          (select count(*) from tests t 
            where t.chal_id = c.id) as num_tests
        from challenges c""")


@app.route('/c:json')
def list_challenges_json():
    return list_challenges_data()


@app.route('/c')
def list_challenges():
    return flask.render_template('challenges.html',
                                 data=list_challenges_data())

@app.route('/c/<name>')
def show_challenge(name):
    data = [x for x in list_challenges_data()
            if x['name'] == name]
    flask.abort(404) if not data else ok
    return flask.render_template('challenge.html', data=data[0])


if __name__ == '__main__':
    app.run()
