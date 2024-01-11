import random
import string
import asyncio

import quart
import jwt as jwtlib

from .database import query

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
    return query("""
        select c.name, c.title,
          (select count(*) from tests t
            where t.chid = c.id) as num_tests
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


def make_pre_token():
    res = ''.join(random.choice(string.ascii_letters) for _ in range(32))
    return make_pre_token() if res in queues else res


@app.route('/auth/pre', methods=['POST'])
def post_auth_pre():
    pre = make_pre_token()
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
    return {'token': f'{pre}->{jwt}'}


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
