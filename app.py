import flask
import sqlite3
import asyncio
import jwt as jwtlib

SDB_PATH = 'rogo.sdb'  # TODO: make this configurable
app = flask.Flask(__name__)
ok = None

# this maps pre-tokens to async queues that
# will eventually yield the jwt token.
queues = {}

JWT_OBJ = jwtlib.JWT()
JWT_KEY = jwtlib.jwk_from_pem(open('rogo_auth_key.pem', 'rb').read())


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
        select c.name, c.description as title,
          (select count(*) from tests t 
            where t.chid = c.id) as num_tests
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


@app.route('/login', methods=['GET'])
def get_login():
    return flask.render_template('login.html')


# == Authentication for Command Line Client ===

@app.route('/auth/login', methods=['GET'])
def get_auth_login():
    data = {'pre': flask.request.args.get('pre', '??')}
    return flask.render_template('login.html', **data)


@app.route('/auth/pre', methods=['GET'])
def get_auth_pre():
    return """
    <form method="POST" action="/auth/pre">
        <input type="submit" value="get pre-token">
    </form>
    """


@app.route('/auth/pre', methods=['POST'])
def post_auth_pre():
    pre = 'PRE' # TODO: random string
    assert pre not in queues, "repeated pre-token"
    queues[pre] = asyncio.Queue()
    return {'token': pre}


@app.route('/auth/jwt', methods=['GET'])
def get_auth_jwt():
    return """
    <form method="POST" action="/auth/jwt">
        <label for="pre">pre-token:</label>
        <input type="text" name="pre">
        <input type="submit" value="get jwt-token">
    </form>"""


@app.route('/auth/jwt', methods=['POST'])
async def post_auth_jwt():
    req = flask.request
    pre = req.json.get('pre') if req.is_json else req.form.get('pre')
    if pre not in queues:
        return f"pre-token not found: {pre}"
    jwt = await queues[pre].get()
    return {'token': f'{pre}->{jwt}'}


@app.route('/auth/success', methods=['POST'])
def post_auth_success():
    pre = flask.request.form.get('preToken')
    ac0 = flask.request.form.get('accessToken')
    acc = JWT_OBJ.decode(ac0, do_verify=False)
    # TODO: validate acc against auth provider (firebase)
    # (otherwise attacker could just send any token)

    data = {'uid': acc['sub'], 'eml': acc['email']}
    jwt = JWT_OBJ.encode(data, JWT_KEY, alg='RS256')
    try:
        q = queues[pre]
        q.put_nowait(jwt)
    except KeyError:
        return f"pre-token not found: {pre}"
    except asyncio.QueueFull:
        return "pre-token already used"
    return """
    <h1>Success!</h1>
    <p>You have successfully logged in.</p>
    <p>You can close this browser tab.</p>
    """


if __name__ == '__main__':
    app.run(host='localhost', port=5000)
