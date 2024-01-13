import random
import string
import asyncio

import quart
import jwt as jwtlib

from . import database as db

app = quart.Quart(__name__)
ok = None

# this maps pre-tokens to async queues that
# will eventually yield the jwt token.
queues = {}

JWT_OBJ = jwtlib.JWT()
JWT_KEY = jwtlib.jwk_from_pem(open('rogo_auth_key.pem', 'rb').read())


@app.route('/')
async def index():
    return await quart.render_template('index.html')


@app.route('/about')
async def about():
    return await quart.render_template('about.html')


def list_challenges_data():
    return db.query("""
        select c.id, c.name, c.title,
          (select count(*) from tests t
            where t.chid = c.rowid) as num_tests
        from challenges c""")


@app.route('/c:json')
def list_challenges_json():
    return list_challenges_data()


@app.route('/c')
async def list_challenges():
    data = list_challenges_data()
    return await quart.render_template('challenges.html', data=data)


@app.route('/c/<name>')
async def show_challenge(name):
    data = [x for x in list_challenges_data()
            if x['name'] == name]
    quart.abort(404) if not data else ok
    return await quart.render_template('challenge.html', data=data[0])


async def uid_from_request():
    f = await quart.request.form
    if not (j := f.get('jwt')):
        raise LookupError('no jwt given')
    r = db.query('select uid from tokens where jwt=?', [j])
    if not r: raise LookupError('unrecognized jwt')
    return r[0]['uid']


@app.route('/c/<name>/attempt', methods=['POST'])
async def attempt_challenge(name):
    if not (uid := (await uid_from_request())):
        return "log in first.", 403   # TODO: pretty 403 error
    try:
        [row] = db.query('select id from challenges where name=?', [name])
        chid = row['id']
    except ValueError:
        raise LookupError(f'invalid challenge: {name!r}')
    code = random_string()
    db.commit("""
        insert into attempts (uid, chid, code) values (?, ?, ?)
        """, [uid, chid, code])
    return {'aid': code}


@app.route('/a/<code>/next', methods=['POST'])
async def next_tests_for_attempt(code):
    # TODO: make sure you're only looking at attempts you're allowed to see
    # otherwise you could spam server with invalid codes for centuries
    # until a code worked, and then see the ultra-secret next test case. :)
    print('attempt code:', code)
    import json
    rows = db.get_next_tests(code)
    # hide the answers for now:
    for row in rows:
        row['olines'] = None
    print('next tests:', json.dumps(rows))
    return rows


@app.route('/login', methods=['GET'])
async def get_login():
    return await quart.render_template('login.html')


# == Authentication for Command Line Client ===

@app.route('/auth/login', methods=['GET'])
async def get_auth_login():
    data = {'pre': quart.request.args.get('pre', '??')}
    return await quart.render_template('login.html', **data)


@app.route('/auth/pre', methods=['GET'])
def get_auth_pre():
    return """
    <form method="POST" action="/auth/pre">
        <input type="submit" value="get pre-token">
    </form>
    """


def random_string(length=32):
    res = ''.join(random.choice(string.ascii_letters) for _ in range(length))
    return random_string() if res in queues else res


@app.route('/auth/pre', methods=['POST'])
def post_auth_pre():
    pre = random_string()
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
    req = quart.request
    pre = (await req.json).get('pre') if req.is_json else (await req.form).get('pre')
    assert pre in queues, f"pre-token not found: {pre}"
    print(f'awaiting jwt for pre[{pre}]:')
    jwt = await queues[pre].get()
    del queues[pre]
    print(f'jwt for pre[{pre}]:', jwt)
    return {'token': jwt}


@app.route('/auth/success', methods=['POST'])
async def post_auth_success():
    frm = await quart.request.form
    pre = frm.get('preToken')
    ac0 = frm.get('accessToken')
    acc = JWT_OBJ.decode(ac0, do_verify=False)
    # TODO: validate acc against auth provider (firebase)
    # (otherwise attacker could just send any token)

    data = {'uid': acc['sub'], 'eml': acc['email']}
    jwt = JWT_OBJ.encode(data, JWT_KEY, alg='RS256')

    # TODO: move this to a real signup process
    sid = 1  # TODO: validate server
    # TODO: use real usernames
    uid = db.commit("""
      replace into users (sid, authid, username)
      values (?, ?, ?)
      """, [1, acc['sub'], acc['email']])
    db.commit("insert into tokens (uid, jwt) values (?, ?)",
              [uid, jwt])

    # now tell jwt to the listening command line client
    try:
        q = queues[pre]
        print("queues[pre]:", q)
        print("jwt:", jwt)
        q.put_nowait(jwt)
    except KeyError:
        return f"pre-token not found: {pre}", 500
    except asyncio.QueueFull:
        return "pre-token already used", 500
    return """
    <h1>Success!</h1>
    <p>You have successfully logged in.</p>
    <p>You can close this browser tab.</p>
    """


if __name__ == '__main__':
    app.run(host='localhost', port=5000)
