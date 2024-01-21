import asyncio
import inspect
import json
import random
import string

import jwt as jwtlib
import quart

from . import database as db
from . import model as m

app = quart.Quart(__name__)
# TODO: make this dev-server only
app.config['TEMPLATES_AUTO_RELOAD'] = True

THIS_SID = 1  # TODO: validate server id

ok = None

# this maps pre-tokens to async queues that
# will eventually yield the jwt token.
queues: dict[str, list[asyncio.Queue]] = {}

observers: dict[str, list[asyncio.Queue]] = {}


# == sessions =================================================


def random_string(length=32):
    return ''.join(random.choice(string.ascii_letters) for _ in range(length))


def get_session(skey: str) -> dict | None:
    # TODO: update the timestamp in the 'seen' column
    rows = db.query('select * from sessions where skey=?', [skey])
    return json.loads(rows[0]['data']) if rows else None


def new_session(sid: int, uid: int) -> str:
    skey = random_string()
    db.commit("""
        insert into sessions (skey, sid, uid, data) values (?, ?, ?, ?)
        """, [skey, sid, uid, '{"uid": %i}' % uid])
    return skey


class PleaseLogin(Exception):
    """raised when a request requires a user to be logged in"""


def require_uid(f0):
    """supplies the uid from the request, or raises PleaseLogin"""
    async def f(*a, **kw):
        # uid can come from cookie or jwt
        skey = quart.request.cookies.get('sess', '')
        if skey:
            uid = (get_session(skey) or {}).get('uid')
        else:
            jsn = await quart.request.json
            if not jsn:
                raise PleaseLogin
            if not (jwt := jsn.get('jwt')):
                raise LookupError('no jwt given')
            r = db.query('select uid from tokens where jwt=?', [jwt])
            if not r: raise LookupError('unrecognized jwt')
            uid = r[0]['uid']
        if not uid:
            raise PleaseLogin
        return await f0(uid=uid, *a, **kw)
    f.__name__ = f0.__name__
    return f


@app.errorhandler(PleaseLogin)
async def handle_please_login(_e):
    html = await quart.render_template('please_login.html')
    return html   # htmx didn't show content when status 401


# == websocket notifications ==================================

async def notify(code, data, wrap=True):
    data = f'<span id="test-detail">{data}</span>' if wrap else data
    for o in observers.get(code, []):
        await o.put(data)


async def notify_state(code, state, focus):
    data = dict(state=state, focus=focus, code=code)
    html = await quart.render_template('state.html', data=data)
    await notify(code, html, wrap=False)


JWT_OBJ = jwtlib.JWT()
JWT_KEY = jwtlib.jwk_from_pem(open('tanco_auth_key.pem', 'rb').read())

# == platonic apps ============================================
# mini web framework to wrap htmx fragments in a layout
# and also allow fetching raw json with .json suffix


def htmx_fragment(f0):
    async def f(*a, **kw):
        body = (await f0(*a, **kw)) if inspect.iscoroutinefunction(f0) else f0(*a, **kw)
        qr = quart.request
        if qr.headers.get('HX-Request'):
            return body
        else:
            return await quart.render_template('index.html', body=body)
    f.__name__ = f0.__name__
    return f


def platonic(route, template, hx=True):
    """allows an endpoint that returns data to serve html or json,
    depending on the presence of the string '.json' in the url"""
    def decorator(f0):
        async def fp(*a, **kw):
            data = (await f0(*a, **kw)) if inspect.iscoroutinefunction(f0) else f0(*a, **kw)
            if quart.request.path.endswith('.json'):
                return data
            else:
                return await quart.render_template(template, data=data, url=quart.request.path)

        async def fj(*a, **kw):
            return await fp(*a, **kw)

        @htmx_fragment
        async def fhx(*a, **kw):
            return await fp(*a, **kw)

        fp.__name__ = f0.__name__
        fhx.__name__ = f0.__name__
        fj.__name__ = f0.__name__ + '_json'
        app.route(route)(fhx if hx else fp)
        app.route(route + '.json')(fj)
        return fp
    return decorator

# -------------------------------------------------------------


@app.route('/')
async def index():
    return await quart.render_template('index.html')


@app.route('/about')
@htmx_fragment
async def about():
    return await quart.render_template('about.html')


@platonic('/me', 'me.html')
@require_uid
async def me(uid):
    data = db.query("""
        select u.username
        from users u
        where u.id=?
        """, [uid])[0]
    data['attempts'] = db.query("""
        select a.ts, c.name as c_name, c.title, a.code
        from attempts a, challenges c, users u
        where a.chid=c.id and u.id=? and a.uid=u.id
        """, [uid])
    return data


@platonic('/c', 'challenges.html')
def list_challenges():
    return db.query("""
        select c.id, c.name, c.title
        from challenges c""")


@platonic('/c/<name>', 'challenge.html')
async def show_challenge(name):
    data = db.query("""
        select c.id, c.name, c.title,
          (select count(*) from tests t
           where t.chid = c.rowid) as num_tests
        from challenges c
        where name=?
        """, [name])
    quart.abort(404) if not data else ok
    return data[0]


@app.route('/c/<name>/attempt', methods=['POST'])
@require_uid
async def attempt_challenge(name, uid):
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


@platonic('/a/<code>', 'attempt.html')
@require_uid
async def show_attempt(code, uid):
    # TODO: trap IndexError if no attempt found
    data = db.query("""
        select a.code, a.state, t.name as focus, c.name as c_name, u.username as u_name
        from challenges c, users u, attempts a left join tests t on a.focus = t.id
        where a.code = (:code) and u.id = (:uid)
        """, {'code': code, 'uid': uid})[0]
    data['state'] = m.AttemptState[data['state'].capitalize()]
    data['progress'] = db.query("""
        select t.name as t_name, p.ts from attempts a, tests t, progress p
        where a.code = (:code) and a.id = p.aid and p.tid = t.id
        """, [code])
    return data


@app.websocket('/a/<code>/live')
# TODO: @require_uid (raises RuntimeError: Not within a request context)
async def attempt_live(code):
    ws = quart.websocket
    q = asyncio.Queue()
    global observers
    observers.setdefault(code, []).append(q)
    try:
        await ws.send('')
        while True:
            html = await q.get()
            await ws.send(html)
    except asyncio.CancelledError:
        observers[code].remove(q)


@platonic('/a/<code>/t/<name>', 'test.html')
@require_uid
async def show_test(**kw):
    # TODO: make sure the user has either passed the test or it is their next test
    data = db.query("""
        select t.name, t.head, t.body, t.ilines,
           t.olines
        from attempts a, tests t        
        where a.chid = t.chid and a.uid = (:uid)
          and a.code = (:code) and t.name=(:name)
        """, kw)[0]
    return data


@app.route('/a/<code>/next', methods=['POST'])
@require_uid
async def next_tests_for_attempt(code, uid):
    state, focus = db.set_attempt_state(uid, code, m.Transition.Next)
    await notify_state(code, state, focus)
    rows = db.get_next_tests(code, uid)
    # hide the answers for now:
    for row in rows:
        row['olines'] = None
    return rows


@app.route('/a/<code>/pass', methods=['POST'])
@require_uid
async def send_attempt_pass(code, uid):
    state, focus = db.set_attempt_state(uid, code, m.Transition.Pass)
    assert not focus, 'all tests passed so focus should be empty'
    await notify_state(code, state, focus='')
    await notify(code, await quart.render_template('pass.html'))
    return ['ok']


@app.route('/a/<code>/fail', methods=['POST'])
@require_uid
async def send_attempt_fail(code, uid):
    # TODO: validate the jwt
    jsn = await quart.request.json
    tr_data = jsn.get('result')
    tr = m.TestResult.from_data(tr_data)
    try:
        tn = jsn['test_name']
        t = db.get_attempt_test(uid, code, tn)
    except KeyError:
        return 'unknown test', 400
    except LookupError:
        return 'unknown test or attempt', 400
    state, focus = db.set_attempt_state(uid, code, m.Transition.Fail, failing_test=tn)
    await notify_state(code, state, focus)
    html = await quart.render_template('result.html', test=t, result=tr)
    await notify(code, html)
    return ['ok']


@app.route('/a/<code>/check/<test_name>', methods=['POST'])
@require_uid
async def check_test_for_attempt(code, test_name, uid):
    actual = (await quart.request.json).get('actual')
    if actual is None:
        return "bad request: no 'actual' field in post", 400

    # fetch the expected output
    # TODO: update to allow arbitrary validation rules
    try:
        t = db.get_attempt_test(uid, code, test_name)
    except LookupError:
        return 'unknown test or attempt', 404

    r = t.check_output(actual)
    print('test result:', r.to_data())

    if r.is_pass():
        db.save_progress(code, test_name, True)

    if obs := observers.get(code, []):
        html = await quart.render_template('result.html', test=t, result=r, actual=actual)
        for o in obs:
            await o.put(html)
    return r.to_data()


# == Website Authentication ===================================

@app.route('/whoami', methods=['GET'])
async def get_whoami():
    skey = quart.request.cookies.get('sess', '')
    uid = (get_session(skey) or {}).get('uid') if skey else None
    data = db.query('select username from users where id=?', [uid])[0] if uid else {}
    return await quart.render_template('whoami.html', uid=uid, data=data)


@app.route('/login', methods=['GET'])
async def get_login():
    return await quart.render_template('login.html')


@app.route('/login/success', methods=['POST'])
async def post_login_success():
    frm = await quart.request.form
    uid, _ = decode_access_token(frm.get('accessToken'))
    key = new_session(THIS_SID, uid)
    whence = frm.get('whence') or '/'  # could be there but blank
    res = quart.redirect(whence)
    res.set_cookie('sess', key)
    return res


# == Authentication for Command Line Client ===================

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
    assert pre in queues, f'pre-token not found: {pre}'
    print(f'awaiting jwt for pre[{pre}]:')
    jwt = await queues[pre].get()
    del queues[pre]
    print(f'jwt for pre[{pre}]:', jwt)
    return {'token': jwt}


def decode_access_token(acc0):
    """returns uid, token_data"""
    # TODO: validate acc against auth provider (firebase)
    # (otherwise attacker could just send any token)
    acc = JWT_OBJ.decode(acc0, do_verify=False)
    # TODO: move this to a real signup process
    # TODO: use real usernames
    authid = acc['sub']
    username = acc['email']
    uid = db.uid_from_tokendata(THIS_SID, authid, username)
    token_data = {'authid': authid, 'username': username}
    return uid, token_data


@app.route('/auth/success', methods=['POST'])
async def post_auth_success():
    frm = await quart.request.form
    uid, data = decode_access_token(frm.get('accessToken'))
    # TODO: validate the jwt
    jwt = JWT_OBJ.encode(data, JWT_KEY, alg='RS256')

    db.commit('insert into tokens (uid, jwt) values (?, ?)',
              [uid, jwt])

    # now tell jwt to the listening command line client
    pre = frm.get('preToken')
    try:
        q = queues[pre]
        print('queues[pre]:', q)
        print('jwt:', jwt)
        q.put_nowait(jwt)
    except KeyError:
        return f'pre-token not found: {pre}', 500
    except asyncio.QueueFull:
        return 'pre-token already used', 500
    return """
    <h1>Success!</h1>
    <p>You have successfully logged in.</p>
    <p>You can close this browser tab.</p>
    """


if __name__ == '__main__':
    app.run(host='localhost', port=5000)
